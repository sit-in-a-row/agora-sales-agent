from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import shutil
import time
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


from app.agents.mock_provider import MockProvider
from app.agents.prompts import REWRITE_PROMPT, SUPPLEMENTAL_RESEARCH_PROMPT, load_prompt
from app.agents.provider import OpenAIProvider, normalize_url
from app.config import DEFAULT_CONFIG, RunOptions
from app.job_store import JobState
from app.notion_store import NotionSalesStore, NotionStoreError, company_key
from app.models import (
    CompanyResearch, EmailDraft, EntityResolutionBatch, LeadRuntime, LeadScore,
    LeadScoreBatch, LeadUnit, ResolvedVisitor, SalesReview, SalesStrategy,
    SupplementalResearch, VisitorRecord,
)
from app.pipeline.grouping import build_lead_units
from app.pipeline.email_template import render_deterministic_email, slots_from_lead
from app.pipeline.retrieval import CorpusRetriever
from app.pipeline.workbook import WorkbookParser, stable_id
from app.pipeline.xlsx_io import write_simple_xlsx


STAGE_BASE = {
    "ingest": 2,
    "entity": 5,
    "group": 17,
    "research": 20,
    "retrieval": 45,
    "score": 50,
    "strategy": 66,
    "draft": 76,
    "review": 87,
    "export": 97,
}

STAGE_SPAN = {
    "entity": 12,
    "research": 25,
    "retrieval": 5,
    "score": 16,
    "strategy": 10,
    "draft": 11,
    "review": 10,
    "export": 3,
}


def _json_dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(data, "model_dump"):
        data = data.model_dump(mode="json")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _csv_write(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows and not fieldnames:
        path.write_text("", encoding="utf-8-sig")
        return
    if fieldnames is None:
        keys: list[str] = []
        for row in rows:
            for k in row:
                if k not in keys:
                    keys.append(k)
        fieldnames = keys
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(_safe_text(v) for v in value if v is not None)
    return str(value)


def _interest_text(v: VisitorRecord) -> str:
    fields = [
        v.visitor_role, v.industry, v.seniority_band, v.function, v.product_interests,
        v.industry_ai, v.business_ai, v.genai, v.ai_platform, v.event_interests,
        v.visit_purpose, v.attendee_type,
    ]
    return " | ".join(str(x) for x in fields if x)


def _lead_summary(lead: LeadUnit) -> dict[str, Any]:
    return {
        "lead_id": lead.lead_id,
        "lead_unit_type": lead.lead_unit_type,
        "canonical_company_name": lead.canonical_company_name,
        "canonical_department": lead.canonical_department,
        "member_count": len(lead.members),
        "group_time_start": lead.group_time_start,
        "group_time_end": lead.group_time_end,
        "members": [
            {
                "visitor_id": v.visitor_id,
                "attendee_name": v.attendee_name,
                "department": v.canonical_department or v.department,
                "job_title": v.job_title,
                "seniority_level": v.seniority_level.value,
                "role_family": v.role_family,
                "visitor_role": v.visitor_role,
                "company_size_label": v.company_size,
                "industry": v.industry,
                "function": v.function,
                "interests": _interest_text(v),
                "email_domain": (v.email or "").split("@")[-1] if v.email and "@" in v.email else None,
            }
            for v in lead.members
        ],
    }


def _runtime_public(rt: LeadRuntime) -> dict[str, Any]:
    lead = rt.lead
    score = rt.score
    draft = rt.draft
    review = rt.review
    evidence = rt.research.evidence if rt.research else []
    research_public = None
    if rt.research:
        research_public = {
            "summary": rt.research.business_summary,
            "official_company_name": rt.research.official_company_name,
            "one_line_description": rt.research.one_line_description,
            "executive_summary": rt.research.executive_summary,
            "confidence": rt.research.research_confidence,
            "local_presence": rt.research.local_presence.model_dump(mode="json"),
            "company_scale": rt.research.company_scale.model_dump(mode="json"),
            "listing_status": rt.research.listing_status,
            "listing_market": rt.research.listing_market,
            "ticker": rt.research.ticker,
            "employee_snapshot": rt.research.employee_snapshot,
            "revenue_history": [x.model_dump(mode="json") for x in rt.research.revenue_history],
            "funding": rt.research.funding.model_dump(mode="json"),
            "main_businesses": [x.model_dump(mode="json") for x in rt.research.main_businesses],
            "commercial_attractiveness": rt.research.commercial_attractiveness.model_dump(mode="json"),
            "rtc_opportunities": [x.model_dump(mode="json") for x in rt.research.rtc_opportunities],
            "ai_opportunities": [x.model_dump(mode="json") for x in rt.research.ai_opportunities],
            "agora_product_check": rt.research.agora_product_check.model_dump(mode="json"),
            "signals": [x.model_dump(mode="json") for x in rt.research.recent_signals],
            "evidence": [e.model_dump(mode="json") for e in evidence],
            "unknowns": rt.research.unknowns,
        }
    return {
        "lead_id": lead.lead_id,
        "lead_unit_type": lead.lead_unit_type,
        "company": lead.canonical_company_name,
        "department": lead.canonical_department,
        "company_size": ", ".join(dict.fromkeys([m.company_size for m in lead.members if m.company_size])),
        "member_count": len(lead.members),
        "members": [
            {
                "name": m.attendee_name,
                "email": m.email,
                "title": m.job_title,
                "department": m.canonical_department or m.department,
                "seniority": m.seniority_level.value,
                "company_size": m.company_size,
                "interests": _interest_text(m),
            }
            for m in lead.members
        ],
        "classification": score.classification if score else "PENDING",
        "total_score": score.total_score if score else None,
        "classification_confidence": score.classification_confidence if score else None,
        "score_axes": score.axes.model_dump(mode="json") if score else None,
        "score_rationale": score.classification_rationale if score else None,
        "positive_signals": score.positive_signals if score else [],
        "negative_signals": score.negative_signals if score else [],
        "uncertainties": score.uncertainties if score else [],
        "research": research_public,
        "retrieval_doc_ids": rt.retrieval.doc_ids if rt.retrieval else [],
        "strategy": rt.strategy.model_dump(mode="json") if rt.strategy else None,
        "draft": draft.model_dump(mode="json") if draft else None,
        "review": review.model_dump(mode="json") if review else None,
        "human_review_status": rt.human_review_status,
        "human_review_note": rt.human_review_note,
    }


def _update_summary(job: JobState, runtimes: dict[str, LeadRuntime]) -> None:
    counts = {"total": len(runtimes), "quality": 0, "normal": 0, "trash": 0, "manual": 0}
    for rt in runtimes.values():
        if rt.score:
            cls = rt.score.classification.lower()
            if cls in counts:
                counts[cls] += 1
        if rt.human_review_status in {"REQUIRED", "PENDING"} and rt.score and rt.score.classification == "QUALITY":
            counts["manual"] += 1
        elif rt.human_review_status == "REQUIRED":
            counts["manual"] += 1
    job.summary = counts


def _manual_draft_edits(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "07_drafts" / "manual_edits.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _emit_lead(job: JobState, rt: LeadRuntime) -> None:
    public = _runtime_public(rt)
    edit = _manual_draft_edits(job.run_dir).get(rt.lead.lead_id)
    if edit and public.get("draft"):
        public["draft"]["subject_primary"] = edit.get("subject", public["draft"].get("subject_primary"))
        public["draft"]["full_email"] = edit.get("full_email", public["draft"].get("full_email"))
        public["draft"]["manual_edit"] = True
        public["draft"]["manual_edit_saved_at"] = edit.get("saved_at")
        public["review_outdated_by_manual_edit"] = bool(public.get("review"))
    job.leads[rt.lead.lead_id] = public
    job.emit("lead_update", {"lead": public, "summary": job.summary})


def _progress(job: JobState, stage: str, current: int, total: int, label: str) -> None:
    base = STAGE_BASE[stage]
    span = STAGE_SPAN.get(stage, 0)
    ratio = 1.0 if total <= 0 else min(1.0, current / total)
    job.set_progress(base + span * ratio, label, f"{current}/{total}" if total else "")


def _company_id(name: str | None, raw: str | None) -> str:
    return stable_id("COM", (name or raw or "UNKNOWN").casefold())


def _validate_research_sources(research: CompanyResearch, sources: list[dict[str, Any]]) -> tuple[CompanyResearch, list[str]]:
    source_urls = {normalize_url(s.get("url", "")) for s in sources if s.get("url")}
    if not source_urls:
        research.research_confidence = min(research.research_confidence, 0.45)
        research.unknowns.append("web_search source ledger를 확인하지 못함")
        research.agora_product_check.checked = False
        return research, [e.evidence_id for e in research.evidence]

    invalid_ids: list[str] = []
    valid_evidence = []
    for e in research.evidence:
        if normalize_url(e.url) in source_urls:
            valid_evidence.append(e)
        else:
            invalid_ids.append(e.evidence_id)

    valid_ids = {e.evidence_id for e in valid_evidence}
    research.evidence = valid_evidence

    def keep(ids: list[str]) -> list[str]:
        return [eid for eid in ids if eid in valid_ids]

    if invalid_ids:
        research.recent_signals = [s for s in research.recent_signals if not s.evidence_ids or any(eid in valid_ids for eid in s.evidence_ids)]
        research.local_presence.evidence_ids = keep(research.local_presence.evidence_ids)
        research.company_scale.evidence_ids = keep(research.company_scale.evidence_ids)
        for row in research.revenue_history:
            row.evidence_ids = keep(row.evidence_ids)
        research.funding.evidence_ids = keep(research.funding.evidence_ids)
        for item in research.main_businesses:
            item.evidence_ids = keep(item.evidence_ids)
        research.commercial_attractiveness.evidence_ids = keep(research.commercial_attractiveness.evidence_ids)
        for item in research.rtc_opportunities + research.ai_opportunities:
            item.company_evidence_ids = keep(item.company_evidence_ids)
            item.agora_evidence_ids = keep(item.agora_evidence_ids)
        research.research_confidence = min(research.research_confidence, 0.65)
        research.unknowns.append(f"source ledger와 일치하지 않은 evidence 제거: {', '.join(invalid_ids)}")

    checked_urls = [u for u in research.agora_product_check.official_source_urls if normalize_url(u) in source_urls]
    if len(checked_urls) != len(research.agora_product_check.official_source_urls):
        research.unknowns.append("Agora product check URL 일부가 web source ledger와 불일치하여 제거됨")
    research.agora_product_check.official_source_urls = checked_urls
    if not checked_urls:
        research.agora_product_check.checked = False
        research.agora_product_check.summary = (research.agora_product_check.summary or "") + " / 공식 Agora URL source ledger 확인 필요"

    return research, invalid_ids


def _enforce_score_policy(score: LeadScore, cfg: dict[str, Any]) -> LeadScore:
    total = (
        score.axes.account_potential.score + score.axes.contact_influence.score +
        score.axes.declared_intent.score + score.axes.agora_fit.score +
        score.axes.recent_trigger.score + score.axes.evidence_quality.score
    )
    score.total_score = total
    quality = int(cfg["quality_threshold"])
    normal = int(cfg["normal_threshold"])
    expected = "QUALITY" if total >= quality else "NORMAL" if total >= normal else "TRASH"
    if score.classification != expected:
        score.uncertainties.append(f"모델 classification {score.classification}을 고정 threshold에 따라 {expected}로 교정")
        score.classification = expected
    score.review_level = "HIGH_TOUCH" if expected == "QUALITY" else "STANDARD" if expected == "NORMAL" else "NONE"
    return score


async def run_pipeline(
    job: JobState,
    input_path: Path,
    api_key: str,
    options: RunOptions,
    notion_config: dict[str, Any] | None = None,
) -> None:
    run_dir = job.run_dir
    trace_path = run_dir / "09_api_trace" / "api_trace.jsonl"
    trace_json_path = run_dir / "09_api_trace" / "api_trace.json"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    api_trace_records: list[dict[str, Any]] = []

    def on_api_trace(payload: dict[str, Any]) -> None:
        # Durable files keep the full request/response. SSE gets a clipped copy so
        # a very large prompt cannot freeze the browser transcript panel. API key is never part of payload.
        event_payload = {**payload, "ts": time.time()}
        try:
            api_trace_records.append(event_payload)
            with trace_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event_payload, ensure_ascii=False, default=str) + "\n")
            _json_dump(trace_json_path, api_trace_records)
        except Exception:
            pass

        def clip(value: Any, limit: int = 60000) -> Any:
            try:
                raw = json.dumps(value, ensure_ascii=False, default=str)
            except Exception:
                raw = str(value)
            if len(raw) <= limit:
                return value
            return {"_truncated_for_live_ui": True, "_original_chars": len(raw), "preview": raw[:limit] + "\n… [full content is preserved in api_trace.json]"}

        live_payload = dict(event_payload)
        if "system_prompt" in live_payload:
            live_payload["system_prompt"] = clip(live_payload["system_prompt"], 30000)
        if "user_payload" in live_payload:
            live_payload["user_payload"] = clip(live_payload["user_payload"], 60000)
        if "parsed" in live_payload:
            live_payload["parsed"] = clip(live_payload["parsed"], 60000)
        job.emit("api_trace", live_payload)

    provider = MockProvider(trace_callback=on_api_trace) if options.demo_mode else OpenAIProvider(api_key, trace_callback=on_api_trace)
    parser = WorkbookParser()
    custom_case_dir = run_dir / "knowledge_overrides" / "cases"
    retriever = CorpusRetriever(additional_roots=[custom_case_dir] if custom_case_dir.exists() else [])
    cfg = DEFAULT_CONFIG
    notion_store: NotionSalesStore | None = None
    if notion_config and notion_config.get("api_key") and notion_config.get("database_url"):
        try:
            notion_store = NotionSalesStore(str(notion_config["api_key"]), str(notion_config["database_url"]))
            await notion_store.resolve()
            await notion_store.index(refresh=True)  # one DB scan; later lookup/upsert uses the in-memory index
            job.emit("log", {"level": "info", "message": "Notion DB 연결 확인 완료 · 기존 index 로드 / Research 재사용 / 결과 동기화 준비"})
        except Exception as exc:
            notion_store = None
            job.emit("log", {"level": "warning", "message": f"Notion 연결을 사용할 수 없습니다. Pipeline은 계속 실행합니다: {exc}"})

    try:
        job.status = "running"
        job.set_progress(1, "입력 파일 확인", "파일을 읽고 있습니다.")
        records, input_meta = parser.load_records(input_path, options.source_mode)
        if options.selected_visitor_ids:
            selected = set(options.selected_visitor_ids)
            before = len(records)
            records = [r for r in records if r.visitor_id in selected]
            input_meta["selection"] = {"requested": len(selected), "matched": len(records), "source_records": before}
            job.emit("log", {"level": "info", "message": f"선택 row 모드: {before}명 중 {len(records)}명만 처리"})
        if options.excluded_visitor_ids:
            excluded = set(options.excluded_visitor_ids)
            before_exclude = len(records)
            records = [r for r in records if r.visitor_id not in excluded]
            input_meta["notion_exclusion"] = {"requested": len(excluded), "excluded": before_exclude - len(records)}
            job.emit("log", {"level": "info", "message": f"Notion 기존 메일 {before_exclude - len(records)}명 제외 · 신규 대상 {len(records)}명"})
        if not records:
            raise ValueError("처리할 방문자 row가 없습니다. 선택 row와 현재 preset이 일치하는지 확인하세요.")
        _json_dump(run_dir / "input" / "input_meta.json", input_meta)
        _json_dump(run_dir / "input" / "records.json", [r.model_dump(mode="json") for r in records])
        if options.email_style_reference.strip():
            (run_dir / "input" / "email_style_reference.txt").write_text(options.email_style_reference, encoding="utf-8")
        job.emit("log", {"level": "info", "message": f"입력 {len(records)}명 로드 — {input_meta['source']}"})
        job.set_progress(4, "입력 완료", f"{len(records)}명")
        if job.cancel_requested:
            raise asyncio.CancelledError()

        # 1. Entity resolution — unique triples, batched.
        unique: dict[str, dict[str, Any]] = {}
        record_key_for_visitor: dict[str, str] = {}
        for r in records:
            key = stable_id("ER", r.company or "", r.department or "", r.job_title or "")
            record_key_for_visitor[r.visitor_id] = key
            unique.setdefault(key, {
                "record_key": key,
                "company_raw": r.company or "",
                "department_raw": r.department,
                "title_raw": r.job_title,
                "seniority_raw": r.seniority_band,
                "role_context": r.visitor_role,
            })
        unique_rows = list(unique.values())
        entity_results: dict[str, Any] = {}
        batch_size = 30
        batches = [unique_rows[i:i+batch_size] for i in range(0, len(unique_rows), batch_size)]
        for bi, batch in enumerate(batches, start=1):
            result = await provider.parse(
                model=cfg["models"]["entity"], system_prompt=load_prompt("entity"),
                user_payload={"records": batch}, response_model=EntityResolutionBatch,
                reasoning_effort="low", prompt_cache_key="agora-entity-v1", trace_label="Entity Resolver",
            )
            for item in result.parsed.results:
                entity_results[item.record_key] = item
            _progress(job, "entity", bi, len(batches), "회사·부서·직책 해석")

        # Web fallback only for ambiguous entities.
        if options.quick_mode:
            # Preview mode avoids expensive web fallback for merely medium-confidence aliases.
            # Company Research still performs a web-grounded identity check afterwards.
            ambiguous = [x for x in entity_results.values() if x.identity_status == "UNKNOWN" or (x.needs_web_resolution and x.resolver_confidence < 0.45)]
        else:
            ambiguous = [x for x in entity_results.values() if x.needs_web_resolution or x.identity_status != "RESOLVED" or x.resolver_confidence < 0.65]
        for idx, item in enumerate(ambiguous, start=1):
            payload = {
                "records": [{
                    "record_key": item.record_key,
                    "company_raw": item.company_raw,
                    "department_raw": item.department_raw,
                    "title_raw": None,
                    "first_pass": item.model_dump(mode="json"),
                }]
            }
            web_result = await provider.parse(
                model=cfg["models"]["entity_web"], system_prompt=load_prompt("entity_web"),
                user_payload=payload, response_model=EntityResolutionBatch,
                reasoning_effort="low", web_search=True, require_web=True,
                prompt_cache_key="agora-entity-web-v1", trace_label="Entity Resolver · Web",
            )
            if web_result.parsed.results:
                entity_results[item.record_key] = web_result.parsed.results[0]
            job.emit("log", {"level": "info", "message": f"애매한 회사명 추가 확인 {idx}/{len(ambiguous)}"})

        resolved: list[ResolvedVisitor] = []
        for r in records:
            ent = entity_results[record_key_for_visitor[r.visitor_id]]
            canonical = ent.canonical_company_name or ent.local_entity_name or r.company or "Unknown"
            cid = _company_id(canonical, r.company)
            resolved.append(ResolvedVisitor(
                **r.model_dump(),
                company_id=cid,
                canonical_company_name=canonical,
                canonical_department=ent.canonical_department or r.department,
                department_family=ent.department_family,
                role_family=ent.role_family,
                seniority_level=ent.seniority_level,
                entity_confidence=ent.resolver_confidence,
            ))
        _json_dump(run_dir / "01_entities" / "resolved_entities.json", {
            k: v.model_dump(mode="json") for k, v in entity_results.items()
        })
        _json_dump(run_dir / "01_entities" / "resolved_visitors.json", [v.model_dump(mode="json") for v in resolved])

        # 2. Grouping
        leads = build_lead_units(resolved, int(cfg["grouping_window_minutes"]))
        lead_limit = 0 if options.selected_visitor_ids else (options.max_leads if options.max_leads and options.max_leads > 0 else (8 if options.quick_mode else 0))
        if lead_limit:
            leads = leads[:lead_limit]
            mode_label = "빠른 미리보기" if options.quick_mode else "테스트 제한"
            job.emit("log", {"level": "warning", "message": f"{mode_label}: 첫 {len(leads)}개 lead만 처리"})
        runtimes = {lead.lead_id: LeadRuntime(lead=lead) for lead in leads}
        _json_dump(run_dir / "02_groups" / "lead_units.json", [l.model_dump(mode="json") for l in leads])
        _update_summary(job, runtimes)
        job.set_progress(19, "방문 그룹 정리 완료", f"{len(leads)} lead units")
        job.emit("summary", {"summary": job.summary})
        if job.cancel_requested:
            raise asyncio.CancelledError()

        # 3. Research: once per company represented in selected leads.
        by_company_leads: dict[str, list[LeadUnit]] = defaultdict(list)
        for lead in leads:
            by_company_leads[lead.company_id].append(lead)
        company_research: dict[str, CompanyResearch] = {}
        sem = asyncio.Semaphore(max(1, options.concurrency))

        # v1.6: when the company already exists in Notion, reuse its full raw
        # CompanyResearch object. This avoids repeating web research for a new
        # contact at an already researched account. Exact previously generated
        # leads are loaded/skipped by the frontend before this job starts.
        if notion_store and notion_config and notion_config.get("reuse_research", True):
            for cid, company_leads in by_company_leads.items():
                company = company_leads[0].canonical_company_name
                try:
                    rec = await notion_store.find_company(company_key(company))
                    if not rec:
                        continue
                    state = await notion_store.load_state(rec.page_id)
                    raw = state.get("research_raw") if isinstance(state, dict) else None
                    if not raw:
                        continue
                    cached = CompanyResearch.model_validate(raw)
                    cached.company_id = cid
                    cached.canonical_company_name = company
                    company_research[cid] = cached
                    _json_dump(run_dir / "03_research" / "notion_cache" / f"{cid}.json", cached)
                    job.emit("log", {"level": "info", "message": f"Notion Research 재사용: {company}"})
                except Exception as exc:
                    job.emit("log", {"level": "warning", "message": f"Notion Research 재사용 실패({company}) · 웹 리서치로 진행: {exc}"})

        async def research_company(cid: str, company_leads: list[LeadUnit], idx: int, total: int) -> None:
            async with sem:
                members = [m for l in company_leads for m in l.members]
                company = company_leads[0].canonical_company_name
                payload = {
                    "company_id": cid,
                    "canonical_company_name": company,
                    "market": "South Korea",
                    "recent_horizon_months": int(cfg["research_horizon_months"]),
                    "represented_departments": sorted({m.canonical_department or m.department or "" for m in members if m.canonical_department or m.department}),
                    "represented_roles": sorted({m.job_title or "" for m in members if m.job_title}),
                    "attendee_interest_context": sorted({_interest_text(m) for m in members if _interest_text(m)})[:30],
                    "instruction": "한국 local entity를 우선하되 매출/상장/임직원/투자규모 등 money signal과 실제 Agora RTC/AI 적용 가능성을 함께 조사하세요. Agora 제품은 이번 실행 시점의 공식 홈페이지/Documentation을 웹에서 직접 확인하세요.",
                }
                attempts = 0
                last_result = None
                while attempts < 2:
                    attempts += 1
                    result = await provider.parse(
                        model=cfg["models"]["research"], system_prompt=load_prompt("research"),
                        user_payload=payload, response_model=CompanyResearch,
                        reasoning_effort="low" if options.quick_mode else "medium", web_search=True, require_web=True,
                        prompt_cache_key="agora-research-v1.6", trace_label="Account Researcher",
                    )
                    research = result.parsed
                    research.company_id = cid
                    research.canonical_company_name = company
                    research, invalid = _validate_research_sources(research, result.sources)
                    last_result = (research, result, invalid)
                    if not invalid or options.demo_mode:
                        break
                    payload["source_validation_note"] = "이전 결과에서 web_search source ledger에 없는 URL이 검출되었습니다. 이번에는 실제 검색에서 확인한 URL만 evidence.url에 사용하세요."
                assert last_result is not None
                research, result, invalid = last_result
                company_research[cid] = research
                _json_dump(run_dir / "03_research" / "companies" / f"{cid}.json", research)
                _json_dump(run_dir / "03_research" / "raw_sources" / f"{cid}.json", {
                    "sources": result.sources, "usage": result.usage, "invalid_evidence_ids": invalid
                })
                md = [f"# {company}\n", "## Executive Summary"]
                md.extend([f"- {x}" for x in research.executive_summary])
                md += [
                    "\n## Commercial Attractiveness",
                    f"- **{research.commercial_attractiveness.level}** — {research.commercial_attractiveness.headline}",
                    *[f"- {x}" for x in research.commercial_attractiveness.reasons],
                    "\n## Company",
                    f"- 공식명: {research.official_company_name or research.canonical_company_name}",
                    f"- 한 줄 소개: {research.one_line_description}",
                    f"- 상장: {research.listing_status or '공개 정보 확인 어려움'} {research.listing_market or ''} {research.ticker or ''}".strip(),
                    f"- 임직원: {research.employee_snapshot or research.local_presence.korea_employee_range or '공개 정보 확인 어려움'}",
                    "\n## Revenue",
                ]
                md.extend([f"- {x.year}: {x.amount_text} ({x.scope or 'scope n/a'}, {x.source_kind})" for x in research.revenue_history] or ["- 공개 정보 확인 어려움"])
                md += ["\n## Main Businesses"]
                md.extend([f"- **{x.name}** — {x.description or ''}" for x in research.main_businesses])
                md += ["\n## Agora RTC Opportunities"]
                md.extend([f"- {x.rank}. **{x.service_or_workflow}** → {x.recommended_product}: {x.idea}" for x in research.rtc_opportunities] or ["- 뚜렷한 RTC 적용 기회 확인 어려움"])
                md += ["\n## Agora AI Opportunities"]
                md.extend([f"- {x.rank}. **{x.service_or_workflow}** → {x.recommended_product}: {x.idea}" for x in research.ai_opportunities] or ["- 뚜렷한 AI 적용 기회 확인 어려움"])
                md += ["\n## Recent signals"]
                for sig in research.recent_signals:
                    md.append(f"- **{sig.topic}** ({sig.date or 'date n/a'}): {sig.summary}")
                md.append("\n## Sources")
                for ev in research.evidence:
                    md.append(f"- [{ev.title}]({ev.url}) — {ev.claim}")
                (run_dir / "03_research" / "companies" / f"{cid}.md").write_text("\n".join(md), encoding="utf-8")
                _progress(job, "research", idx, total, "회사 리서치")
                job.emit("log", {"level": "info", "message": f"리서치 완료: {company}"})

        research_tasks = []
        missing_research = [(cid, company_leads) for cid, company_leads in by_company_leads.items() if cid not in company_research]
        total_companies = len(missing_research)
        for idx, (cid, company_leads) in enumerate(missing_research, start=1):
            research_tasks.append(asyncio.create_task(research_company(cid, company_leads, idx, total_companies)))
        if research_tasks:
            await asyncio.gather(*research_tasks)
        elif company_research:
            job.set_progress(45, "회사 리서치", "선택 기업 Research를 Notion에서 재사용했습니다.")
        if job.cancel_requested:
            raise asyncio.CancelledError()

        # 4. Retrieval
        for idx, rt in enumerate(runtimes.values(), start=1):
            research = company_research[rt.lead.company_id]
            rt.research = research
            rt.retrieval = retriever.retrieve(rt.lead, research)
            _json_dump(run_dir / "04_retrieval" / f"{rt.lead.lead_id}.json", rt.retrieval)
            _progress(job, "retrieval", idx, len(runtimes), "Agora 자료 매칭")

        # 5. Scoring — cross-company batches. Each lead carries its own company research.
        # This materially reduces API round-trips while preserving evidence context.
        score_rts = list(runtimes.values())
        score_batches = [score_rts[i:i+6] for i in range(0, len(score_rts), 6)]

        async def score_batch(batch: list[LeadRuntime], idx: int, total: int) -> None:
            async with sem:
                payload_leads = []
                for rt in batch:
                    payload_leads.append({
                        **_lead_summary(rt.lead),
                        "company_research": company_research[rt.lead.company_id].model_dump(mode="json"),
                        "agora_context": retriever.compact_context(rt.retrieval, max_chars=16000 if options.quick_mode else 18000),
                    })
                result = await provider.parse(
                    model=cfg["models"]["scoring"], system_prompt=load_prompt("scoring"),
                    user_payload={
                        "leads": payload_leads,
                        "fixed_weights": {"account_potential":25,"contact_influence":20,"declared_intent":20,"agora_fit":20,"recent_trigger":10,"evidence_quality":5},
                        "thresholds": {"quality":75,"normal":45},
                    },
                    response_model=LeadScoreBatch, reasoning_effort="low" if options.quick_mode else "medium",
                    prompt_cache_key="agora-scorer-v1.6", trace_label="Lead Scorer",
                )
                score_map = {score.lead_id: _enforce_score_policy(score, cfg) for score in result.parsed.scores}
                for rt in batch:
                    score = score_map.get(rt.lead.lead_id)
                    if not score:
                        raise RuntimeError(f"Scorer가 lead_id를 누락했습니다: {rt.lead.lead_id}")
                    rt.score = score
                    rt.human_review_status = "REQUIRED" if score.classification == "QUALITY" else "NOT_REQUIRED"
                    _json_dump(run_dir / "05_scores" / f"{rt.lead.lead_id}.json", score)
                    _update_summary(job, runtimes)
                    _emit_lead(job, rt)
                _progress(job, "score", idx, total, "Lead scoring")

        score_tasks = [asyncio.create_task(score_batch(batch, idx, len(score_batches))) for idx, batch in enumerate(score_batches, start=1)]
        if score_tasks:
            await asyncio.gather(*score_tasks)

        # Optional supplemental research & re-score for high-potential uncertain leads.
        supplemental_candidates = [] if options.quick_mode else [
            rt for rt in runtimes.values()
            if rt.score and rt.score.supplemental_research_recommended and rt.score.total_score >= 70
            and rt.score.supplemental_research_queries
        ]
        if options.quick_mode:
            job.emit("log", {"level":"info", "message":"빠른 미리보기: supplemental research는 생략합니다."})
        for idx, rt in enumerate(supplemental_candidates, start=1):
            payload = {
                "lead_id": rt.lead.lead_id,
                "company": rt.lead.canonical_company_name,
                "department": rt.lead.canonical_department,
                "queries": rt.score.supplemental_research_queries[:3],
                "existing_research": rt.research.model_dump(mode="json"),
            }
            sup_result = await provider.parse(
                model=cfg["models"]["research"], system_prompt=SUPPLEMENTAL_RESEARCH_PROMPT,
                user_payload=payload, response_model=SupplementalResearch,
                reasoning_effort="medium", web_search=True, require_web=True,
                prompt_cache_key="agora-supplement-v1", trace_label="Supplemental Research",
            )
            _json_dump(run_dir / "03_research" / "supplemental" / f"{rt.lead.lead_id}.json", {
                "research": sup_result.parsed.model_dump(mode="json"), "sources": sup_result.sources
            })
            rescored = await provider.parse(
                model=cfg["models"]["scoring"], system_prompt=load_prompt("scoring"),
                user_payload={
                    "company_research": rt.research.model_dump(mode="json"),
                    "supplemental_research": sup_result.parsed.model_dump(mode="json"),
                    "leads": [{**_lead_summary(rt.lead), "agora_context": retriever.compact_context(rt.retrieval, 18000)}],
                    "fixed_weights": {"account_potential":25,"contact_influence":20,"declared_intent":20,"agora_fit":20,"recent_trigger":10,"evidence_quality":5},
                    "thresholds": {"quality":75,"normal":45},
                },
                response_model=LeadScoreBatch, reasoning_effort="medium", prompt_cache_key="agora-scorer-v1.6", trace_label="Lead Scorer · Re-score",
            )
            if rescored.parsed.scores:
                rt.score = _enforce_score_policy(rescored.parsed.scores[0], cfg)
                rt.human_review_status = "REQUIRED" if rt.score.classification == "QUALITY" else "NOT_REQUIRED"
                _json_dump(run_dir / "05_scores" / f"{rt.lead.lead_id}.json", rt.score)
                _update_summary(job, runtimes)
                _emit_lead(job, rt)
            job.emit("log", {"level":"info", "message":f"보완 리서치 {idx}/{len(supplemental_candidates)} 완료"})

        if job.cancel_requested:
            raise asyncio.CancelledError()

        active = [rt for rt in runtimes.values() if rt.score]

        # 6. Strategy
        async def make_strategy(rt: LeadRuntime, idx: int, total: int) -> None:
            async with sem:
                result = await provider.parse(
                    model=cfg["models"]["strategy"], system_prompt=load_prompt("strategy"),
                    user_payload={
                        "lead": _lead_summary(rt.lead),
                        "lead_score": rt.score.model_dump(mode="json"),
                        "company_research": rt.research.model_dump(mode="json"),
                        "agora_retrieval": retriever.compact_context(rt.retrieval, 26000),
                        "retrieval_doc_ids": rt.retrieval.doc_ids,
                        "dynamic_corpus_instruction": "retrieval corpus는 고정 목록이 아닙니다. 새 case 문서가 추가될 수 있으므로 doc_id의 익숙함이 아니라 실제 내용, factuality, source, prospect relevance로 판단하세요.",
                    },
                    response_model=SalesStrategy, reasoning_effort="low" if options.quick_mode else "medium",
                    prompt_cache_key="agora-strategy-v1.6", trace_label="Sales Strategist",
                )
                rt.strategy = result.parsed
                _json_dump(run_dir / "06_strategy" / f"{rt.lead.lead_id}.json", rt.strategy)
                _emit_lead(job, rt)
                _progress(job, "strategy", idx, total, "영업 전략 생성")

        await asyncio.gather(*[
            asyncio.create_task(make_strategy(rt, idx, len(active)))
            for idx, rt in enumerate(active, start=1)
        ]) if active else None

        # 7. Draft — deterministic template for QUALITY / NORMAL / TRASH alike
        # v1.6 keeps the LLM writer out of the default path; research never auto-enters the email.
        # The model may research/score/strategize, but the email itself is rendered
        # from the user-approved fixed template and externally supplied slots only.
        async def make_draft(rt: LeadRuntime, idx: int, total: int) -> None:
            slots = slots_from_lead(
                rt.lead,
                sender_name=options.sender_name,
                sender_title=options.sender_title,
            )
            rt.draft = render_deterministic_email(rt.lead, slots)
            _json_dump(run_dir / "07_drafts" / f"{rt.lead.lead_id}.json", rt.draft)
            (run_dir / "07_drafts").mkdir(parents=True, exist_ok=True)
            (run_dir / "07_drafts" / f"{rt.lead.lead_id}.md").write_text(
                f"# {rt.draft.subject_primary}\n\n{rt.draft.full_email}\n", encoding="utf-8"
            )
            _emit_lead(job, rt)
            _progress(job, "draft", idx, total, "Deterministic 메일 생성")

        for idx, rt in enumerate(active, start=1):
            await make_draft(rt, idx, len(active))

        # 8. Review — deterministic email is never auto-rewritten
        # Quick Preview intentionally stops after a real API-generated draft.
        # Quality leads still require human review, satisfying the user's policy while
        # avoiding the expensive reviewer/rewrite loop during fast B2B exploration.
        if options.quick_mode:
            job.emit("log", {"level":"info", "message":"빠른 미리보기: Deterministic 초안을 즉시 표시하고 AI Reviewer를 생략합니다. Quality는 사람 검수 필수입니다."})
            for rt in active:
                rt.human_review_status = "REQUIRED" if rt.score.classification == "QUALITY" else "NOT_REQUIRED"
                _emit_lead(job, rt)
        else:
            async def review_rt(rt: LeadRuntime, idx: int, total: int) -> None:
                async with sem:
                    model = cfg["models"]["review_quality"] if rt.score.classification == "QUALITY" else cfg["models"]["review_normal"]
                    result = await provider.parse(
                        model=model, system_prompt=load_prompt("review"),
                        user_payload={
                            "lead_id": rt.lead.lead_id,
                            "classification": rt.score.classification,
                            "lead": _lead_summary(rt.lead),
                            "company_research": rt.research.model_dump(mode="json"),
                            "strategy": rt.strategy.model_dump(mode="json"),
                            "draft": rt.draft.model_dump(mode="json"),
                            "deterministic_template": True,
                            "fixed_blocks_must_not_be_rewritten": True,
                            "agora_retrieval": retriever.compact_context(rt.retrieval, 20000),
                            "pass_threshold": 88 if rt.score.classification == "QUALITY" else 82,
                            "email_style_reference": options.email_style_reference[:12000] if options.email_style_reference else "",
                        },
                        response_model=SalesReview, reasoning_effort="medium",
                        prompt_cache_key="agora-review-v1.6", trace_label="Sales Reviewer",
                    )
                    rt.review = result.parsed

                if rt.review.decision == "REWRITE":
                    # Fixed template blocks may not be rewritten by the LLM. A requested
                    # rewrite therefore becomes a human-review item instead of another
                    # generation call.
                    rt.review.human_review_reasons.append(
                        "Deterministic template 보호: AI rewrite 대신 사람이 직접 Draft textarea에서 수정해야 합니다."
                    )

                if rt.score.classification == "QUALITY":
                    rt.human_review_status = "REQUIRED"  # user's explicit policy
                elif rt.review.decision in {"HUMAN_REVIEW", "REWRITE"}:
                    rt.human_review_status = "REQUIRED"
                else:
                    rt.human_review_status = "NOT_REQUIRED"

                _json_dump(run_dir / "08_reviews" / f"{rt.lead.lead_id}.json", rt.review)
                _update_summary(job, runtimes)
                _emit_lead(job, rt)
                _progress(job, "review", idx, total, "메일 검수")

            await asyncio.gather(*[
                asyncio.create_task(review_rt(rt, idx, len(active)))
                for idx, rt in enumerate(active, start=1)
            ]) if active else None

        # Emit trash records at least once after all stages.
        for rt in runtimes.values():
            if rt.score and rt.score.classification == "TRASH":
                _emit_lead(job, rt)

        # 9. Notion persistence. A Notion failure must never discard the local
        # pipeline result, so each lead is independently best-effort synced.
        if notion_store and notion_config and notion_config.get("auto_sync", True):
            job.set_progress(96, "Notion 동기화", "Research / Lead Score / Draft 저장")
            notion_log = run_dir / "10_notion_sync" / "notion_sync.jsonl"
            notion_log.parent.mkdir(parents=True, exist_ok=True)
            for idx, rt in enumerate(runtimes.values(), start=1):
                if not rt.draft:
                    continue
                public = _runtime_public(rt)
                raw_state = {
                    "lead_raw": rt.lead.model_dump(mode="json"),
                    "research_raw": rt.research.model_dump(mode="json") if rt.research else None,
                    "score_raw": rt.score.model_dump(mode="json") if rt.score else None,
                    "strategy_raw": rt.strategy.model_dump(mode="json") if rt.strategy else None,
                    "draft_raw": rt.draft.model_dump(mode="json") if rt.draft else None,
                    "review_raw": rt.review.model_dump(mode="json") if rt.review else None,
                }
                try:
                    result = await notion_store.upsert_lead(public, raw_state=raw_state)
                    notion_meta = {**(result.get("record") or {}), "sync_action": result.get("action")}
                    public["notion"] = notion_meta
                    job.leads[rt.lead.lead_id] = public
                    job.emit("lead_update", {"lead": public, "summary": job.summary})
                    log_row = {"lead_id": rt.lead.lead_id, "company": rt.lead.canonical_company_name, "ok": True, "notion": notion_meta}
                    job.emit("log", {"level": "info", "message": f"Notion 저장 {idx}/{len(runtimes)}: {rt.lead.canonical_company_name}"})
                except Exception as exc:
                    public["notion_sync_error"] = str(exc)
                    job.leads[rt.lead.lead_id] = public
                    log_row = {"lead_id": rt.lead.lead_id, "company": rt.lead.canonical_company_name, "ok": False, "error": str(exc)}
                    job.emit("log", {"level": "warning", "message": f"Notion 저장 실패({rt.lead.canonical_company_name}) · 로컬 결과는 유지됨: {exc}"})
                with notion_log.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(log_row, ensure_ascii=False, default=str) + "\n")

        # 10. Export
        job.set_progress(97, "결과 파일 생성", "CSV / XLSX / ZIP")
        export_outputs(run_dir, runtimes)
        _update_summary(job, runtimes)
        job.status = "completed"
        job.completed_at = time.time()
        finish_label = "빠른 미리보기 완료" if options.quick_mode else "완료"
        job.set_progress(100, finish_label, f"Quality {job.summary['quality']} / Normal {job.summary['normal']} / Trash {job.summary['trash']}")
        job.emit("completed", {"summary": job.summary, "downloads": {
            "final_csv": f"/api/jobs/{job.job_id}/download/final_leads.csv",
            "xlsx": f"/api/jobs/{job.job_id}/download/final_leads.xlsx",
            "artifacts": f"/api/jobs/{job.job_id}/download/artifacts.zip",
        }})
    except asyncio.CancelledError:
        job.status = "cancelled"
        job.set_progress(job.progress, "취소됨", "사용자가 실행을 취소했습니다.")
        job.emit("cancelled", {})
    except Exception as exc:
        job.status = "failed"
        job.error = f"{type(exc).__name__}: {exc}"
        job.emit("error", {"message": job.error})
        job.set_progress(job.progress, "오류", job.error)
    finally:
        try:
            await provider.close()
        except Exception:
            pass


def _final_row(rt: LeadRuntime) -> dict[str, Any]:
    lead, score = rt.lead, rt.score
    members = lead.members
    emails = [m.email for m in members if m.email]
    names = [m.attendee_name for m in members if m.attendee_name]
    axes = score.axes if score else None
    return {
        "lead_id": lead.lead_id,
        "lead_unit_type": lead.lead_unit_type,
        "company": lead.canonical_company_name,
        "department": lead.canonical_department or "",
        "company_size": ", ".join(dict.fromkeys([m.company_size for m in members if m.company_size])),
        "member_count": len(members),
        "recipient_names": ", ".join(names),
        "recipient_emails": ", ".join(emails),
        "classification": score.classification if score else "",
        "total_score": score.total_score if score else "",
        "classification_confidence": score.classification_confidence if score else "",
        "account_potential": axes.account_potential.score if axes else "",
        "contact_influence": axes.contact_influence.score if axes else "",
        "declared_intent": axes.declared_intent.score if axes else "",
        "agora_fit": axes.agora_fit.score if axes else "",
        "recent_trigger": axes.recent_trigger.score if axes else "",
        "evidence_quality": axes.evidence_quality.score if axes else "",
        "research_confidence": rt.research.research_confidence if rt.research else "",
        "commercial_value": rt.research.commercial_attractiveness.level if rt.research else "",
        "commercial_value_headline": rt.research.commercial_attractiveness.headline if rt.research else "",
        "listing_status": rt.research.listing_status if rt.research else "",
        "listing_market": rt.research.listing_market if rt.research else "",
        "ticker": rt.research.ticker if rt.research else "",
        "latest_revenue": (f"{rt.research.revenue_history[0].year}: {rt.research.revenue_history[0].amount_text}" if rt.research and rt.research.revenue_history else ""),
        "employee_snapshot": rt.research.employee_snapshot if rt.research else "",
        "funding_snapshot": (rt.research.funding.cumulative_funding or rt.research.funding.latest_round or rt.research.funding.note or "") if rt.research else "",
        "primary_sales_angle": rt.strategy.primary_angle if rt.strategy else "",
        "outreach_mode": rt.strategy.outreach_mode if rt.strategy else "",
        "subject": rt.draft.subject_primary if rt.draft else "",
        "email_body": rt.draft.full_email if rt.draft else "",
        "review_score": rt.review.total_score if rt.review else "",
        "review_decision": rt.review.decision if rt.review else "",
        "human_review_status": rt.human_review_status,
        "needs_human_review": "YES" if rt.human_review_status in {"REQUIRED", "PENDING"} else "NO",
        "short_rationale": score.classification_rationale if score else "",
    }


def export_outputs(run_dir: Path, runtimes: dict[str, LeadRuntime]) -> None:
    out = run_dir / "output"
    out.mkdir(parents=True, exist_ok=True)
    manual_edits = _manual_draft_edits(run_dir)
    for lead_id, edit in manual_edits.items():
        rt = runtimes.get(lead_id)
        if rt and rt.draft:
            rt.draft.subject_primary = edit.get("subject", rt.draft.subject_primary)
            rt.draft.full_email = edit.get("full_email", rt.draft.full_email)
    rows = [_final_row(rt) for rt in runtimes.values()]
    fields = list(rows[0].keys()) if rows else ["lead_id"]
    _csv_write(out / "final_leads.csv", rows, fields)
    for cls, filename in (("QUALITY", "quality_sales.csv"), ("NORMAL", "normal_sales.csv"), ("TRASH", "trash_accounts.csv")):
        subset = [r for r in rows if r.get("classification") == cls]
        _csv_write(out / filename, subset, fields)
    manual = [r for r in rows if r.get("needs_human_review") == "YES"]
    _csv_write(out / "manual_review.csv", manual, fields)
    _json_dump(out / "final_leads.json", {
        lead_id: _runtime_public(rt) for lead_id, rt in runtimes.items()
    })

    # Human-review XLSX without external spreadsheet dependency.
    write_simple_xlsx(
        out / "final_leads.xlsx",
        [
            ("All", rows),
            ("Quality", [r for r in rows if r.get("classification") == "QUALITY"]),
            ("Normal", [r for r in rows if r.get("classification") == "NORMAL"]),
            ("Trash", [r for r in rows if r.get("classification") == "TRASH"]),
            ("Manual Review", manual),
        ],
        fields,
    )

    # Package all artifacts except original upload to minimize accidental PII duplication in nested ZIP.
    artifact_zip = out / "artifacts.zip"
    with zipfile.ZipFile(artifact_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for path in run_dir.rglob("*"):
            if not path.is_file() or path == artifact_zip:
                continue
            z.write(path, arcname=str(path.relative_to(run_dir)))
