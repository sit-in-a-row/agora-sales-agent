from __future__ import annotations

import asyncio
import csv
import json
import os
import shutil
import time
import uuid
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import RUNS_DIR, STATIC_DIR, RunOptions
from app.job_store import STORE, JobState
from app.notion_store import NotionSalesStore, NotionStoreError, company_key
from app.pipeline.orchestrator import run_pipeline
from app.pipeline.workbook import WorkbookParser
from app.pipeline.xlsx_io import write_simple_xlsx

APP_VERSION = "1.6.0-vercel" if os.getenv("VERCEL") else "1.6.0"
app = FastAPI(title="Agora Sales Lead Intelligence", version=APP_VERSION)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
parser = WorkbookParser()


@app.middleware("http")
async def disable_frontend_cache(request, call_next):
    """Avoid stale index/app.js mismatches after local version upgrades."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


def _sync_live_outputs(job) -> None:
    """Keep downloadable CSV/XLSX/JSON aligned with web-side human edits/reviews."""
    out = job.run_dir / "output"
    final_path = out / "final_leads.csv"
    if not final_path.exists():
        return
    with final_path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return
    fields = list(rows[0].keys())
    for row in rows:
        live = job.leads.get(row.get("lead_id", ""))
        if not live:
            continue
        row["human_review_status"] = live.get("human_review_status", row.get("human_review_status", ""))
        row["needs_human_review"] = "NO" if live.get("human_review_status") == "APPROVED" else "YES" if live.get("human_review_status") in {"REQUIRED", "PENDING"} else row.get("needs_human_review", "NO")
        draft = live.get("draft") or {}
        if draft:
            row["subject"] = draft.get("subject_primary", row.get("subject", ""))
            row["email_body"] = draft.get("full_email", row.get("email_body", ""))

    def write_csv(path, subset):
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader(); w.writerows(subset)

    write_csv(final_path, rows)
    write_csv(out / "quality_sales.csv", [r for r in rows if r.get("classification") == "QUALITY"])
    write_csv(out / "normal_sales.csv", [r for r in rows if r.get("classification") == "NORMAL"])
    write_csv(out / "trash_accounts.csv", [r for r in rows if r.get("classification") == "TRASH"])
    manual = [r for r in rows if r.get("needs_human_review") == "YES"]
    write_csv(out / "manual_review.csv", manual)
    write_simple_xlsx(out / "final_leads.xlsx", [
        ("All", rows),
        ("Quality", [r for r in rows if r.get("classification") == "QUALITY"]),
        ("Normal", [r for r in rows if r.get("classification") == "NORMAL"]),
        ("Trash", [r for r in rows if r.get("classification") == "TRASH"]),
        ("Manual Review", manual),
    ], fields)
    (out / "final_leads.json").write_text(json.dumps(job.leads, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    artifact_zip = out / "artifacts.zip"
    try:
        artifact_zip.unlink(missing_ok=True)
        with zipfile.ZipFile(artifact_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for path in job.run_dir.rglob("*"):
                if path.is_file() and path != artifact_zip:
                    z.write(path, arcname=str(path.relative_to(job.run_dir)))
    except Exception:
        pass


# backwards-compatible alias for the existing review endpoint
def _sync_human_review_outputs(job) -> None:
    _sync_live_outputs(job)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "service": "agora-sales-agent", "version": APP_VERSION, "deployment_mode": "vercel" if os.getenv("VERCEL") else "local"}


async def _save_upload(file: UploadFile, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)


@app.post("/api/inspect")
async def inspect_upload(file: UploadFile = File(...)) -> JSONResponse:
    suffix = Path(file.filename or "upload.xlsx").suffix.lower()
    if suffix not in {".xlsx", ".csv"}:
        raise HTTPException(400, "현재 .xlsx / .csv만 지원합니다.")
    temp_dir = RUNS_DIR / "_inspect" / uuid.uuid4().hex[:12]
    temp_path = temp_dir / (file.filename or f"upload{suffix}")
    try:
        await _save_upload(file, temp_path)
        result = parser.inspect(temp_path)
        return JSONResponse(result.as_dict())
    except Exception as exc:
        raise HTTPException(400, f"파일을 읽지 못했습니다: {exc}") from exc
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/preview")
async def preview_upload(
    file: UploadFile = File(...),
    source_mode: str = Form("impt_all"),
    limit: int = Form(1000),
) -> JSONResponse:
    suffix = Path(file.filename or "upload.xlsx").suffix.lower()
    if suffix not in {".xlsx", ".csv"}:
        raise HTTPException(400, "현재 .xlsx / .csv만 지원합니다.")
    temp_dir = RUNS_DIR / "_preview" / uuid.uuid4().hex[:12]
    temp_path = temp_dir / (file.filename or f"upload{suffix}")
    try:
        await _save_upload(file, temp_path)
        records, meta = parser.load_records(temp_path, source_mode)
        records = records[:max(1, min(5000, int(limit)))]
        preview = []
        for r in records:
            interests = " | ".join(x for x in [
                r.product_interests, r.industry_ai, r.business_ai, r.genai, r.ai_platform,
                r.event_interests, r.visit_purpose
            ] if x)
            preview.append({
                "visitor_id": r.visitor_id,
                "row_number": r.raw_row_number,
                "visited_at": r.visited_at,
                "name": r.attendee_name,
                "company": r.company,
                "department": r.department,
                "job_title": r.job_title,
                "visitor_role": r.visitor_role,
                "seniority": r.seniority_band,
                "company_size": r.company_size,
                "industry": r.industry,
                "function": r.function,
                "email": r.email,
                "interests": interests,
            })
        return JSONResponse({
            "source": meta.get("source"),
            "notes": meta.get("notes", []),
            "total_records": len(records),
            "records": preview,
        })
    except Exception as exc:
        raise HTTPException(400, f"미리보기를 만들지 못했습니다: {exc}") from exc
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


class NotionConnectionRequest(BaseModel):
    api_key: str
    database_url: str


class NotionMatchRequest(NotionConnectionRequest):
    rows: list[dict] = []


class NotionLoadRequest(NotionConnectionRequest):
    page_ids: list[str] = []


class NotionDirectDraftRequest(NotionConnectionRequest):
    page_id: str
    subject: str
    full_email: str


class NotionDirectReviewRequest(NotionConnectionRequest):
    page_id: str
    status: str
    note: str | None = None


@app.post("/api/notion/test")
async def notion_test(body: NotionConnectionRequest) -> JSONResponse:
    try:
        store = NotionSalesStore(body.api_key, body.database_url)
        return JSONResponse(await store.test_connection())
    except NotionStoreError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/notion/match")
async def notion_match(body: NotionMatchRequest) -> JSONResponse:
    try:
        store = NotionSalesStore(body.api_key, body.database_url)
        return JSONResponse(await store.match_rows(body.rows[:5000]))
    except NotionStoreError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/notion/load")
async def notion_load(body: NotionLoadRequest) -> JSONResponse:
    try:
        store = NotionSalesStore(body.api_key, body.database_url)
        index = {r.page_id: r for r in await store.index()}
        records = [index[pid] for pid in body.page_ids[:500] if pid in index]
        sem = asyncio.Semaphore(2)

        async def load_one(record):
            async with sem:
                return await store.load_record(record)

        items = await asyncio.gather(*(load_one(record) for record in records)) if records else []
        return JSONResponse({"items": items})
    except NotionStoreError as exc:
        raise HTTPException(400, str(exc)) from exc



@app.post("/api/notion/import")
async def notion_import_artifact(
    file: UploadFile = File(...),
    notion_api_key: str = Form(...),
    notion_database_url: str = Form(...),
) -> JSONResponse:
    """Backfill v1.x final_leads.json / artifacts.zip into the configured Notion DB."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".json", ".zip"}:
        raise HTTPException(400, "final_leads.json 또는 artifacts.zip만 지원합니다.")
    raw = await file.read()
    if len(raw) > 100 * 1024 * 1024:
        raise HTTPException(400, "Import 파일이 100MB를 초과합니다.")
    try:
        research_raw_by_company: dict[str, dict] = {}
        if suffix == ".zip":
            import io
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                names = zf.namelist()
                candidates = [n for n in names if n.endswith("output/final_leads.json")]
                if not candidates:
                    candidates = [n for n in names if n.endswith("final_leads.json")]
                if not candidates:
                    raise HTTPException(400, "ZIP 안에서 final_leads.json을 찾지 못했습니다.")
                payload = json.loads(zf.read(candidates[0]).decode("utf-8"))
                for n in names:
                    if "/03_research/companies/" not in f"/{n}" or not n.endswith(".json"):
                        continue
                    try:
                        r = json.loads(zf.read(n).decode("utf-8"))
                        ck = company_key(r.get("canonical_company_name"))
                        if ck:
                            research_raw_by_company[ck] = r
                    except Exception:
                        continue
        else:
            payload = json.loads(raw.decode("utf-8"))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"기존 결과 파일을 읽지 못했습니다: {exc}") from exc

    if isinstance(payload, dict):
        # final_leads.json is normally {lead_id: public_lead}. Also accept a single lead.
        if payload.get("lead_id") and payload.get("company"):
            leads = [payload]
        else:
            leads = [v for v in payload.values() if isinstance(v, dict) and v.get("company")]
    elif isinstance(payload, list):
        leads = [v for v in payload if isinstance(v, dict) and v.get("company")]
    else:
        leads = []
    if not leads:
        raise HTTPException(400, "Import 가능한 lead 결과를 찾지 못했습니다.")
    if len(leads) > 2000:
        raise HTTPException(400, "한 번에 최대 2,000 lead까지 import할 수 있습니다.")

    try:
        store = NotionSalesStore(notion_api_key, notion_database_url, timeout=45.0)
        await store.resolve()
        await store.index(refresh=True)
        results, errors = [], []
        for i, lead in enumerate(leads, start=1):
            try:
                raw_state = {}
                rr = research_raw_by_company.get(company_key(lead.get("company")))
                if rr:
                    raw_state["research_raw"] = rr
                result = await store.upsert_lead(lead, raw_state=raw_state or None)
                results.append({"lead_id": lead.get("lead_id"), "company": lead.get("company"), "action": result.get("action"), "page_url": (result.get("record") or {}).get("page_url")})
            except Exception as exc:
                errors.append({"lead_id": lead.get("lead_id"), "company": lead.get("company"), "error": str(exc)})
        return JSONResponse({"ok": len(errors) == 0, "total": len(leads), "synced": len(results), "failed": len(errors), "results": results, "errors": errors[:50]})
    except NotionStoreError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.put("/api/notion/pages/{page_id}/draft")
async def notion_direct_draft(page_id: str, body: NotionDirectDraftRequest) -> JSONResponse:
    if page_id != body.page_id:
        raise HTTPException(400, "page_id mismatch")
    subject = (body.subject or "").strip()
    full_email = (body.full_email or "").strip()
    if not subject or not full_email:
        raise HTTPException(400, "제목과 메일 본문을 모두 입력하세요.")
    try:
        store = NotionSalesStore(body.api_key, body.database_url)
        records = {r.page_id: r for r in await store.index()}
        rec = records.get(page_id)
        if not rec:
            raise HTTPException(404, "Notion record not found")
        loaded = await store.load_record(rec)
        lead = loaded.get("lead") or {}
        if not lead.get("draft"):
            raise HTTPException(409, "Notion에 저장된 Draft를 찾지 못했습니다.")
        lead["draft"]["subject_primary"] = subject
        lead["draft"]["full_email"] = full_email
        lead["draft"]["manual_edit"] = True
        lead["draft"]["manual_edit_saved_at"] = time.time()
        lead["loaded_from_notion"] = True
        result = await store.upsert_lead(lead, force_status="MANUAL_EDITED")
        lead["notion"] = {**(result.get("record") or {}), "sync_action": result.get("action")}
        return JSONResponse({"ok": True, "lead": lead, "notion": result})
    except NotionStoreError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/notion/pages/{page_id}/human-review")
async def notion_direct_human_review(page_id: str, body: NotionDirectReviewRequest) -> JSONResponse:
    if page_id != body.page_id:
        raise HTTPException(400, "page_id mismatch")
    status = (body.status or "").strip().upper()
    if status not in {"APPROVED", "REJECTED", "PENDING"}:
        raise HTTPException(400, "status must be APPROVED / REJECTED / PENDING")
    try:
        store = NotionSalesStore(body.api_key, body.database_url)
        records = {r.page_id: r for r in await store.index()}
        rec = records.get(page_id)
        if not rec:
            raise HTTPException(404, "Notion record not found")
        loaded = await store.load_record(rec)
        lead = loaded.get("lead") or {}
        if not lead:
            raise HTTPException(409, "Notion에 저장된 Lead state를 찾지 못했습니다.")
        lead["human_review_status"] = status
        lead["human_review_note"] = body.note or ""
        lead["human_review_saved_at"] = time.time()
        lead["loaded_from_notion"] = True
        result = await store.upsert_lead(lead)
        lead["notion"] = {**(result.get("record") or {}), "sync_action": result.get("action")}
        return JSONResponse({"ok": True, "lead": lead, "notion": result})
    except NotionStoreError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/run-stream")
async def run_stream(
    file: UploadFile = File(...),
    api_key: str = Form(""),
    source_mode: str = Form("auto"),
    max_leads: int = Form(0),
    demo_mode: bool = Form(False),
    quick_mode: bool = Form(True),
    sender_name: str = Form("박세빈"),
    sender_title: str = Form("한국 매니저"),
    sender_signature: str = Form("박세빈 (Sebin Park)"),
    concurrency: int = Form(4),
    selected_visitor_ids: str = Form("[]"),
    excluded_visitor_ids: str = Form("[]"),
    email_style_reference: str = Form(""),
    notion_api_key: str = Form(""),
    notion_database_url: str = Form(""),
    notion_auto_sync: bool = Form(True),
    notion_reuse_research: bool = Form(True),
    case_files: list[UploadFile] | None = File(None),
) -> StreamingResponse:
    """Run one bounded batch inside the same HTTP streaming request.

    This is the Vercel-safe execution path: no in-memory job lookup or second SSE
    connection is required. Notion is the durable source of truth after completion.
    """
    suffix = Path(file.filename or "upload.xlsx").suffix.lower()
    if suffix not in {".xlsx", ".csv"}:
        raise HTTPException(400, "현재 .xlsx / .csv만 지원합니다.")
    if not demo_mode and not api_key.strip():
        raise HTTPException(400, "OpenAI API Key를 입력하세요. Demo 모드는 key 없이 가능합니다.")

    job_id = "stream-" + uuid.uuid4().hex[:12]
    run_dir = RUNS_DIR / job_id
    input_dir = run_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    input_path = input_dir / ("visitors" + suffix)
    await _save_upload(file, input_path)

    custom_case_dir = run_dir / "knowledge_overrides" / "cases"
    for case_file in (case_files or []):
        if not case_file or not case_file.filename:
            continue
        case_suffix = Path(case_file.filename).suffix.lower()
        if case_suffix not in {".md", ".txt"}:
            continue
        custom_case_dir.mkdir(parents=True, exist_ok=True)
        await _save_upload(case_file, custom_case_dir / Path(case_file.filename).name)

    def parse_ids(raw: str) -> list[str]:
        try:
            x = json.loads(raw or "[]")
            return [str(v) for v in x if v] if isinstance(x, list) else []
        except Exception:
            return []

    options = RunOptions(
        source_mode=source_mode,
        max_leads=max(0, int(max_leads)),
        demo_mode=bool(demo_mode),
        quick_mode=bool(quick_mode),
        sender_name=sender_name,
        sender_title=sender_title,
        sender_signature=sender_signature,
        concurrency=max(1, min(8, int(concurrency))),
        selected_visitor_ids=parse_ids(selected_visitor_ids),
        excluded_visitor_ids=parse_ids(excluded_visitor_ids),
        email_style_reference=email_style_reference or "",
    )
    notion_config = None
    if notion_api_key.strip() and notion_database_url.strip():
        notion_config = {
            "api_key": notion_api_key.strip(),
            "database_url": notion_database_url.strip(),
            "auto_sync": bool(notion_auto_sync),
            "reuse_research": bool(notion_reuse_research),
        }

    job = JobState(job_id=job_id, run_dir=run_dir)
    queue: asyncio.Queue[dict] = asyncio.Queue()
    seq = 0

    def emit_stream(event_type: str, payload: dict) -> None:
        nonlocal seq
        event = {"id": seq, "type": event_type, "ts": time.time(), **payload}
        seq += 1
        job.events.append(event)
        try:
            queue.put_nowait(event)
        except Exception:
            pass
        job.changed.set()

    job.emit = emit_stream  # type: ignore[method-assign]
    job.emit("created", {"job_id": job_id, "deployment_mode": "stream"})

    def sse(event: dict) -> str:
        payload = {k: v for k, v in event.items() if k not in {"id", "type"}}
        return f"id: {event['id']}\nevent: {event['type']}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"

    async def generate():
        task = asyncio.create_task(run_pipeline(job, input_path, api_key.strip(), options, notion_config=notion_config))
        terminal = {"completed", "cancelled", "error"}
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=12.0)
                    yield sse(event)
                    if event.get("type") in terminal and task.done():
                        break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    if task.done() and queue.empty():
                        break
            await task
        except asyncio.CancelledError:
            job.cancel_requested = True
            if not task.done():
                task.cancel()
            raise
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except Exception:
                    pass
            shutil.rmtree(run_dir, ignore_errors=True)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/jobs")
async def create_job(
    file: UploadFile = File(...),
    api_key: str = Form(""),
    source_mode: str = Form("auto"),
    max_leads: int = Form(0),
    demo_mode: bool = Form(False),
    quick_mode: bool = Form(True),
    sender_name: str = Form("박세빈"),
    sender_title: str = Form("한국 매니저"),
    sender_signature: str = Form("박세빈 (Sebin Park)"),
    concurrency: int = Form(4),
    selected_visitor_ids: str = Form("[]"),
    excluded_visitor_ids: str = Form("[]"),
    email_style_reference: str = Form(""),
    notion_api_key: str = Form(""),
    notion_database_url: str = Form(""),
    notion_auto_sync: bool = Form(True),
    notion_reuse_research: bool = Form(True),
    case_files: list[UploadFile] | None = File(None),
) -> JSONResponse:
    suffix = Path(file.filename or "upload.xlsx").suffix.lower()
    if suffix not in {".xlsx", ".csv"}:
        raise HTTPException(400, "현재 .xlsx / .csv만 지원합니다.")
    if not demo_mode and not api_key.strip():
        raise HTTPException(400, "OpenAI API Key를 입력하세요. Demo 모드는 key 없이 가능합니다.")

    job_id = uuid.uuid4().hex[:12]
    run_dir = RUNS_DIR / job_id
    input_dir = run_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "visitors" + suffix
    input_path = input_dir / safe_name
    await _save_upload(file, input_path)

    custom_case_dir = run_dir / "knowledge_overrides" / "cases"
    saved_cases = []
    for case_file in (case_files or []):
        if not case_file or not case_file.filename:
            continue
        case_suffix = Path(case_file.filename).suffix.lower()
        if case_suffix not in {".md", ".txt"}:
            continue
        custom_case_dir.mkdir(parents=True, exist_ok=True)
        target = custom_case_dir / Path(case_file.filename).name
        await _save_upload(case_file, target)
        saved_cases.append(target.name)

    try:
        selected_ids = json.loads(selected_visitor_ids or "[]")
        if not isinstance(selected_ids, list):
            selected_ids = []
        selected_ids = [str(x) for x in selected_ids if x]
    except Exception:
        selected_ids = []
    try:
        excluded_ids = json.loads(excluded_visitor_ids or "[]")
        if not isinstance(excluded_ids, list):
            excluded_ids = []
        excluded_ids = [str(x) for x in excluded_ids if x]
    except Exception:
        excluded_ids = []

    job = STORE.create(job_id, run_dir)
    job.emit("created", {"job_id": job_id})
    options = RunOptions(
        source_mode=source_mode,
        max_leads=max(0, int(max_leads)),
        demo_mode=bool(demo_mode),
        quick_mode=bool(quick_mode),
        sender_name=sender_name.strip(),
        sender_title=sender_title.strip(),
        sender_signature=sender_signature.strip() or "박세빈 (Sebin Park)",
        concurrency=max(1, min(8, int(concurrency))),
        selected_visitor_ids=selected_ids,
        excluded_visitor_ids=excluded_ids,
        email_style_reference=(email_style_reference or "")[:30000],
    )

    # Secret keys are captured only by this task and are never written to disk/job state.
    notion_config = {
        "api_key": notion_api_key.strip(),
        "database_url": notion_database_url.strip(),
        "auto_sync": bool(notion_auto_sync),
        "reuse_research": bool(notion_reuse_research),
    } if notion_api_key.strip() and notion_database_url.strip() else None
    asyncio.create_task(run_pipeline(job, input_path, api_key.strip(), options, notion_config=notion_config))
    return JSONResponse({"job_id": job_id, "events_url": f"/api/jobs/{job_id}/events"})


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> JSONResponse:
    job = STORE.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return JSONResponse({
        "job_id": job.job_id,
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "message": job.message,
        "error": job.error,
        "summary": job.summary,
        "leads": list(job.leads.values()),
        "last_event_id": len(job.events) - 1,
    })


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str, after: int = Query(-1)) -> StreamingResponse:
    job = STORE.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    async def stream():
        cursor = max(0, int(after) + 1)
        terminal = {"completed", "failed", "cancelled"}
        while True:
            while cursor < len(job.events):
                event = job.events[cursor]
                cursor += 1
                payload = json.dumps(event, ensure_ascii=False, default=str)
                yield f"id: {event['id']}\nevent: {event['type']}\ndata: {payload}\n\n"
            if job.status in terminal and cursor >= len(job.events):
                break
            job.changed.clear()
            try:
                await asyncio.wait_for(job.changed.wait(), timeout=15)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/jobs/{job_id}/api-trace")
async def get_api_trace(job_id: str) -> JSONResponse:
    job = STORE.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    path = job.run_dir / "09_api_trace" / "api_trace.json"
    if not path.exists():
        return JSONResponse({"items": []})
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        items = []
    return JSONResponse({"items": items})


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> JSONResponse:
    job = STORE.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job.cancel_requested = True
    job.emit("log", {"level": "warning", "message": "취소 요청을 받았습니다. 현재 API call 이후 중단됩니다."})
    return JSONResponse({"ok": True})


class HumanReviewRequest(BaseModel):
    status: str
    note: str | None = None


@app.post("/api/jobs/{job_id}/leads/{lead_id}/human-review")
async def human_review(job_id: str, lead_id: str, body: HumanReviewRequest) -> JSONResponse:
    job = STORE.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if lead_id not in job.leads:
        raise HTTPException(404, "Lead not found")
    status = body.status.upper()
    if status not in {"APPROVED", "REJECTED", "REQUIRED"}:
        raise HTTPException(400, "status must be APPROVED / REJECTED / REQUIRED")
    lead = job.leads[lead_id]
    lead["human_review_status"] = status
    lead["human_review_note"] = body.note
    review_dir = job.run_dir / "08_reviews"
    review_dir.mkdir(parents=True, exist_ok=True)
    state_path = review_dir / "human_review_status.json"
    current = {}
    if state_path.exists():
        try:
            current = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            current = {}
    current[lead_id] = {"status": status, "note": body.note}
    state_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    _sync_human_review_outputs(job)
    job.emit("lead_update", {"lead": lead, "summary": job.summary})
    return JSONResponse({"ok": True, "lead": lead})


class DraftEditRequest(BaseModel):
    subject: str
    full_email: str
    notion_api_key: str | None = None
    notion_database_url: str | None = None
    sync_to_notion: bool = True


@app.put("/api/jobs/{job_id}/leads/{lead_id}/draft")
async def edit_draft(job_id: str, lead_id: str, body: DraftEditRequest) -> JSONResponse:
    job = STORE.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    lead = job.leads.get(lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    if not lead.get("draft"):
        raise HTTPException(409, "아직 Email Draft가 생성되지 않았습니다.")

    subject = (body.subject or "").strip()
    full_email = (body.full_email or "").strip()
    if not subject or not full_email:
        raise HTTPException(400, "제목과 메일 본문을 모두 입력하세요.")
    if len(subject) > 300 or len(full_email) > 20000:
        raise HTTPException(400, "메일이 허용 길이를 초과했습니다.")

    saved_at = time.time()
    lead["draft"]["subject_primary"] = subject
    lead["draft"]["full_email"] = full_email
    lead["draft"]["manual_edit"] = True
    lead["draft"]["manual_edit_saved_at"] = saved_at
    if lead.get("review"):
        lead["review_outdated_by_manual_edit"] = True

    draft_dir = job.run_dir / "07_drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    edits_path = draft_dir / "manual_edits.json"
    try:
        edits = json.loads(edits_path.read_text(encoding="utf-8")) if edits_path.exists() else {}
        if not isinstance(edits, dict): edits = {}
    except Exception:
        edits = {}
    edits[lead_id] = {"subject": subject, "full_email": full_email, "saved_at": saved_at}
    edits_path.write_text(json.dumps(edits, ensure_ascii=False, indent=2), encoding="utf-8")
    (draft_dir / f"{lead_id}.manual.md").write_text(f"# {subject}\n\n{full_email}\n", encoding="utf-8")
    (draft_dir / f"{lead_id}.manual.json").write_text(json.dumps(lead["draft"], ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    _sync_live_outputs(job)
    notion_result = None
    if body.sync_to_notion and (body.notion_api_key or "").strip() and (body.notion_database_url or "").strip():
        try:
            store = NotionSalesStore(body.notion_api_key or "", body.notion_database_url or "")
            notion_result = await store.upsert_lead(lead, force_status="MANUAL_EDITED")
            lead["notion"] = {**(notion_result.get("record") or {}), "sync_action": notion_result.get("action")}
        except NotionStoreError as exc:
            lead["notion_sync_error"] = str(exc)
    job.emit("lead_update", {"lead": lead, "summary": job.summary})
    return JSONResponse({"ok": True, "lead": lead, "notion": notion_result})


@app.get("/api/jobs/{job_id}/download/{filename}")
async def download(job_id: str, filename: str) -> FileResponse:
    job = STORE.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    allowed = {
        "final_leads.csv": job.run_dir / "output" / "final_leads.csv",
        "final_leads.xlsx": job.run_dir / "output" / "final_leads.xlsx",
        "quality_sales.csv": job.run_dir / "output" / "quality_sales.csv",
        "normal_sales.csv": job.run_dir / "output" / "normal_sales.csv",
        "trash_accounts.csv": job.run_dir / "output" / "trash_accounts.csv",
        "manual_review.csv": job.run_dir / "output" / "manual_review.csv",
        "artifacts.zip": job.run_dir / "output" / "artifacts.zip",
        "api_trace.json": job.run_dir / "09_api_trace" / "api_trace.json",
        "api_trace.jsonl": job.run_dir / "09_api_trace" / "api_trace.jsonl",
    }
    path = allowed.get(filename)
    if not path or not path.exists():
        raise HTTPException(404, "File not available yet")
    media = "application/zip" if path.suffix == ".zip" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if path.suffix == ".xlsx" else "application/json" if path.suffix == ".json" else "application/x-ndjson" if path.suffix == ".jsonl" else "text/csv"
    return FileResponse(path, filename=filename, media_type=media)
