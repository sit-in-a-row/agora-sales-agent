from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

NOTION_VERSION = "2026-03-11"
MACHINE_MARKER = "AGORA_SALES_AGENT_STATE_V1_6"


class NotionStoreError(RuntimeError):
    pass


def normalize_key(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower().strip()
    return "".join(ch for ch in text if ch.isalnum())


def company_key(company: str | None) -> str:
    return normalize_key(company)


def lead_key(company: str | None, email: str | None = None, name: str | None = None) -> str:
    ck = company_key(company)
    identity = normalize_key(email) or normalize_key(name)
    return f"{ck}::{identity}" if identity else ck


def parse_database_id(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise NotionStoreError("Notion Database URL을 입력하세요.")
    # Accept raw UUID / compact 32-char ID or a normal Notion URL.
    compact = re.sub(r"[^0-9a-fA-F]", "", value)
    if len(compact) == 32 and not value.lower().startswith(("http://", "https://")):
        return compact
    try:
        path = urlparse(value).path
    except Exception as exc:
        raise NotionStoreError("Notion Database URL 형식을 확인하세요.") from exc
    candidates = re.findall(r"[0-9a-fA-F]{32}", path.replace("-", ""))
    if candidates:
        return candidates[-1]
    # app.notion.com/p/<32hex> 형태
    bits = [b for b in path.split("/") if b]
    for bit in reversed(bits):
        c = re.sub(r"[^0-9a-fA-F]", "", bit)
        if len(c) == 32:
            return c
    raise NotionStoreError("Database ID를 URL에서 찾지 못했습니다.")


def _plain_text(prop: dict[str, Any] | None) -> str:
    if not prop:
        return ""
    ptype = prop.get("type")
    if ptype in {"title", "rich_text"}:
        return "".join(x.get("plain_text") or x.get("text", {}).get("content", "") for x in prop.get(ptype, [])).strip()
    if ptype == "email":
        return str(prop.get("email") or "")
    if ptype == "select":
        return str((prop.get("select") or {}).get("name") or "")
    if ptype == "number":
        return "" if prop.get("number") is None else str(prop.get("number"))
    if ptype == "date":
        return str((prop.get("date") or {}).get("start") or "")
    return ""


def _rt(text: str) -> dict[str, Any]:
    return {"type": "text", "text": {"content": text}}


def _rich_chunks(text: str, chunk: int = 1900) -> list[dict[str, Any]]:
    text = str(text or "")
    if not text:
        return []
    return [_rt(text[i:i + chunk]) for i in range(0, len(text), chunk)]


def _paragraph(text: str) -> dict[str, Any]:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rich_chunks(text)}}


def _heading(text: str, level: int = 2) -> dict[str, Any]:
    kind = f"heading_{max(1, min(3, level))}"
    return {"object": "block", "type": kind, kind: {"rich_text": [_rt(text)]}}


def _bullet(text: str) -> dict[str, Any]:
    return {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _rich_chunks(text)}}


def _code(text: str, language: str = "plain text") -> dict[str, Any]:
    return {"object": "block", "type": "code", "code": {"rich_text": _rich_chunks(text), "language": language}}


def _truncate(text: Any, n: int = 1900) -> str:
    s = str(text or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


@dataclass(slots=True)
class NotionRecord:
    page_id: str
    page_url: str
    company: str
    company_key: str
    lead_key: str
    contact: str
    email: str
    title: str
    classification: str
    score: float | None
    commercial: str
    status: str
    last_synced: str
    subject: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "page_url": self.page_url,
            "company": self.company,
            "company_key": self.company_key,
            "lead_key": self.lead_key,
            "contact": self.contact,
            "email": self.email,
            "title": self.title,
            "classification": self.classification,
            "score": self.score,
            "commercial": self.commercial,
            "status": self.status,
            "last_synced": self.last_synced,
            "subject": self.subject,
        }


class NotionSalesStore:
    def __init__(self, api_key: str, database_url: str, timeout: float = 30.0):
        if not (api_key or "").strip():
            raise NotionStoreError("Notion API Key를 입력하세요.")
        self.api_key = api_key.strip()
        self.database_url = database_url.strip()
        self.database_id = parse_database_id(self.database_url)
        self.timeout = timeout
        self._data_source_id: str | None = None
        self._record_cache: list[NotionRecord] | None = None

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, *, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        last_response: httpx.Response | None = None
        for attempt in range(4):
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.request(method, f"https://api.notion.com{path}", headers=self.headers, json=json_body)
            last_response = r
            if r.status_code < 400:
                if not r.content:
                    return {}
                return r.json()
            # Notion enforces workspace rate limits. Respect Retry-After and retry
            # transient server failures so a multi-lead sync does not collapse.
            if r.status_code == 429 and attempt < 3:
                try:
                    delay = max(0.5, float(r.headers.get("Retry-After", "1")))
                except Exception:
                    delay = 1.0
                await asyncio.sleep(delay)
                continue
            if r.status_code in {500, 502, 503, 504} and attempt < 3:
                await asyncio.sleep(0.6 * (2 ** attempt))
                continue
            break

        assert last_response is not None
        r = last_response
        try:
            payload = r.json()
            msg = payload.get("message") or payload.get("code") or r.text
        except Exception:
            msg = r.text
        if r.status_code == 404:
            msg = f"{msg} — 해당 Database를 Notion Integration에 Share했는지 확인하세요."
        raise NotionStoreError(f"Notion API {r.status_code}: {msg}")

    async def resolve(self) -> tuple[str, str]:
        db = await self._request("GET", f"/v1/databases/{self.database_id}")
        sources = db.get("data_sources") or []
        if not sources:
            raise NotionStoreError("Database 안에서 사용할 Data Source를 찾지 못했습니다.")
        self._data_source_id = str(sources[0].get("id") or "")
        if not self._data_source_id:
            raise NotionStoreError("Data Source ID를 확인하지 못했습니다.")
        return self.database_id, self._data_source_id

    async def test_connection(self) -> dict[str, Any]:
        _, dsid = await self.resolve()
        ds = await self._request("GET", f"/v1/data_sources/{dsid}")
        props = ds.get("properties") or {}
        return {
            "ok": True,
            "database_id": self.database_id,
            "data_source_id": dsid,
            "data_source_name": "".join(x.get("plain_text", "") for x in ds.get("title", [])) or "Notion DB",
            "properties": list(props.keys()),
            "notion_version": NOTION_VERSION,
        }

    async def _dsid(self) -> str:
        if not self._data_source_id:
            await self.resolve()
        assert self._data_source_id
        return self._data_source_id

    async def query_all(self) -> list[dict[str, Any]]:
        dsid = await self._dsid()
        results: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            body: dict[str, Any] = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            data = await self._request("POST", f"/v1/data_sources/{dsid}/query", json_body=body)
            results.extend(data.get("results") or [])
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
            if not cursor:
                break
        return results

    async def query_property_equals(self, prop: str, kind: str, value: str) -> list[dict[str, Any]]:
        dsid = await self._dsid()
        body = {
            "page_size": 100,
            "filter": {"property": prop, kind: {"equals": value}},
        }
        data = await self._request("POST", f"/v1/data_sources/{dsid}/query", json_body=body)
        return data.get("results") or []

    def page_to_record(self, page: dict[str, Any]) -> NotionRecord:
        p = page.get("properties") or {}
        score_raw = _plain_text(p.get("Lead Score"))
        try:
            score = float(score_raw) if score_raw != "" else None
        except Exception:
            score = None
        return NotionRecord(
            page_id=str(page.get("id") or ""),
            page_url=str(page.get("url") or ""),
            company=_plain_text(p.get("회사명")) or _plain_text(p.get("이름")),
            company_key=_plain_text(p.get("Company Key")),
            lead_key=_plain_text(p.get("Lead Key")),
            contact=_plain_text(p.get("담당자")),
            email=_plain_text(p.get("이메일")),
            title=_plain_text(p.get("직함")),
            classification=_plain_text(p.get("분류")),
            score=score,
            commercial=_plain_text(p.get("영업가치")),
            status=_plain_text(p.get("저장 상태")),
            last_synced=_plain_text(p.get("Last Synced")),
            subject=_plain_text(p.get("메일 제목")),
        )

    async def index(self, *, refresh: bool = True) -> list[NotionRecord]:
        if self._record_cache is None or refresh:
            self._record_cache = [self.page_to_record(p) for p in await self.query_all()]
        return list(self._record_cache)

    async def find_exact(self, key: str) -> NotionRecord | None:
        if not key:
            return None
        if self._record_cache is not None:
            return next((r for r in self._record_cache if r.lead_key == key), None)
        rows = await self.query_property_equals("Lead Key", "rich_text", key)
        return self.page_to_record(rows[0]) if rows else None

    async def find_company(self, key: str) -> NotionRecord | None:
        if not key:
            return None
        if self._record_cache is not None:
            return next((r for r in self._record_cache if r.company_key == key), None)
        rows = await self.query_property_equals("Company Key", "rich_text", key)
        return self.page_to_record(rows[0]) if rows else None

    async def _block_children(self, page_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            path = f"/v1/blocks/{page_id}/children?page_size=100"
            if cursor:
                path += f"&start_cursor={cursor}"
            data = await self._request("GET", path)
            out.extend(data.get("results") or [])
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
            if not cursor:
                break
        return out

    async def load_state(self, page_id: str) -> dict[str, Any]:
        blocks = await self._block_children(page_id)
        for block in reversed(blocks):
            if block.get("type") != "code":
                continue
            code = block.get("code") or {}
            text = "".join(x.get("plain_text") or x.get("text", {}).get("content", "") for x in code.get("rich_text", []))
            if not text.startswith(MACHINE_MARKER):
                continue
            raw = text[len(MACHINE_MARKER):].lstrip("\n")
            try:
                data = json.loads(raw)
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}
        return {}

    async def load_record(self, record: NotionRecord) -> dict[str, Any]:
        state = await self.load_state(record.page_id)
        return {"record": record.as_dict(), "state": state, "lead": state.get("public_lead")}

    def _properties(self, lead: dict[str, Any], *, page_title: str | None = None, status: str | None = None) -> dict[str, Any]:
        members = lead.get("members") or []
        first = members[0] if members else {}
        company = str(lead.get("company") or "Unknown").strip()
        contact = str(first.get("name") or "").strip()
        email = str(first.get("email") or "").strip()
        title = str(first.get("title") or "").strip()
        ckey = company_key(company)
        lkey = lead_key(company, email, contact)
        cls = str(lead.get("classification") or "").upper()
        company_size_raw = str(lead.get("company_size") or first.get("company_size") or "").strip()
        allowed_sizes = {"대기업", "중견기업", "스타트업", "미분류"}
        size = next((x for x in allowed_sizes if x in company_size_raw), "미분류") if company_size_raw else "미분류"
        research = lead.get("research") or {}
        commercial = (research.get("commercial_attractiveness") or {}).get("level") or "UNKNOWN"
        revenues = research.get("revenue_history") or []
        revenue = ""
        if revenues:
            rr = revenues[0] or {}
            revenue = " ".join(str(rr.get(k) or "") for k in ("year", "amount_text", "scope") if rr.get(k))
            if not revenue:
                revenue = _truncate(json.dumps(rr, ensure_ascii=False), 500)
        employees = research.get("employee_snapshot") or ""
        listing = " / ".join(str(x) for x in [research.get("listing_status"), research.get("listing_market"), research.get("ticker")] if x)
        funding = research.get("funding") or {}
        investment = " / ".join(str(x) for x in [funding.get("cumulative_funding"), funding.get("latest_round")] if x)
        draft = lead.get("draft") or {}
        subject = draft.get("subject_primary") or ""
        title_value = page_title or (f"{company} · {contact}" if contact else company)
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        props: dict[str, Any] = {
            "이름": {"type": "title", "title": _rich_chunks(_truncate(title_value, 500))},
            "회사명": {"type": "rich_text", "rich_text": _rich_chunks(_truncate(company))},
            "Company Key": {"type": "rich_text", "rich_text": _rich_chunks(ckey)},
            "Lead Key": {"type": "rich_text", "rich_text": _rich_chunks(lkey)},
            "담당자": {"type": "rich_text", "rich_text": _rich_chunks(_truncate(contact))},
            "직함": {"type": "rich_text", "rich_text": _rich_chunks(_truncate(title))},
            "기업 종류": {"type": "select", "select": {"name": size}},
            "영업가치": {"type": "select", "select": {"name": commercial if commercial in {"VERY_HIGH", "HIGH", "MEDIUM", "LOW", "UNKNOWN"} else "UNKNOWN"}},
            "최근 매출": {"type": "rich_text", "rich_text": _rich_chunks(_truncate(revenue))},
            "임직원": {"type": "rich_text", "rich_text": _rich_chunks(_truncate(employees))},
            "상장": {"type": "rich_text", "rich_text": _rich_chunks(_truncate(listing))},
            "투자": {"type": "rich_text", "rich_text": _rich_chunks(_truncate(investment))},
            "메일 제목": {"type": "rich_text", "rich_text": _rich_chunks(_truncate(subject))},
            "저장 상태": {"type": "select", "select": {"name": status or ("MANUAL_EDITED" if draft.get("manual_edit") else "GENERATED")}},
            "Last Synced": {"type": "date", "date": {"start": now}},
        }
        if email:
            props["이메일"] = {"type": "email", "email": email}
        else:
            props["이메일"] = {"type": "email", "email": None}
        if cls in {"QUALITY", "NORMAL", "TRASH"}:
            props["분류"] = {"type": "select", "select": {"name": cls}}
        score = lead.get("total_score")
        if isinstance(score, (int, float)):
            props["Lead Score"] = {"type": "number", "number": score}
        return props

    def _human_blocks(self, lead: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
        research = lead.get("research") or {}
        draft = lead.get("draft") or {}
        blocks: list[dict[str, Any]] = [
            _heading("Company Research", 2),
        ]
        for item in research.get("executive_summary") or []:
            blocks.append(_bullet(str(item)))
        if research:
            commercial = research.get("commercial_attractiveness") or {}
            blocks += [
                _heading("Commercial Attractiveness", 3),
                _paragraph(f"{commercial.get('level', 'UNKNOWN')} — {commercial.get('headline', '')}"),
                _paragraph("최근 매출: " + (
                    " / ".join(str((research.get('revenue_history') or [{}])[0].get(k) or "") for k in ("year", "amount_text", "scope") if (research.get('revenue_history') or [{}])[0].get(k))
                    if isinstance((research.get('revenue_history') or [{}])[0], dict)
                    else _truncate((research.get('revenue_history') or ['공개 정보 확인 어려움'])[0], 1500)
                )),
                _paragraph(f"임직원: {research.get('employee_snapshot') or '공개 정보 확인 어려움'}"),
                _paragraph(f"상장: {' / '.join(str(x) for x in [research.get('listing_status'), research.get('listing_market'), research.get('ticker')] if x) or '해당 없음 / 공개 정보 확인 어려움'}"),
            ]
            businesses = research.get("main_businesses") or []
            if businesses:
                blocks.append(_heading("주력 사업", 3))
                for b in businesses[:5]:
                    if isinstance(b, dict):
                        blocks.append(_bullet(str(b.get("name") or b.get("business") or b)))
                    else:
                        blocks.append(_bullet(str(b)))
            for heading, key in (("Agora RTC 적용 가능성", "rtc_opportunities"), ("Agora AI 적용 가능성", "ai_opportunities")):
                opps = research.get(key) or []
                blocks.append(_heading(heading, 3))
                if not opps:
                    blocks.append(_paragraph("뚜렷한 적용 기회 확인 어려움"))
                for o in opps[:3]:
                    if isinstance(o, dict):
                        service = o.get("service_or_workflow") or o.get("service") or o.get("application_service") or o.get("title") or "Use Case"
                        product = o.get("recommended_product") or o.get("agora_product") or ""
                        idea = o.get("idea") or o.get("application_idea") or o.get("rationale") or ""
                        blocks.append(_bullet(f"{service} | {product} | {idea}"))
                    else:
                        blocks.append(_bullet(str(o)))
        blocks += [
            _heading("Email Draft", 2),
            _paragraph(f"제목: {draft.get('subject_primary') or ''}"),
            _code(str(draft.get("full_email") or ""), "plain text"),
            _heading("Agent State", 2),
            _code(MACHINE_MARKER + "\n" + json.dumps(state, ensure_ascii=False, default=str), "json"),
        ]
        return blocks

    async def _replace_children(self, page_id: str, children: list[dict[str, Any]]) -> None:
        existing = await self._block_children(page_id)
        for block in existing:
            bid = block.get("id")
            if bid:
                await self._request("DELETE", f"/v1/blocks/{bid}")
        # Append max 100 blocks per request.
        for i in range(0, len(children), 100):
            await self._request("PATCH", f"/v1/blocks/{page_id}/children", json_body={"children": children[i:i + 100]})

    async def upsert_lead(self, lead: dict[str, Any], *, raw_state: dict[str, Any] | None = None, force_status: str | None = None) -> dict[str, Any]:
        members = lead.get("members") or []
        first = members[0] if members else {}
        lkey = lead_key(lead.get("company"), first.get("email"), first.get("name"))
        existing = await self.find_exact(lkey)
        previous_state: dict[str, Any] = {}
        if existing:
            previous_state = await self.load_state(existing.page_id)
        state = dict(previous_state)
        if raw_state:
            state.update(raw_state)
        state.update({
            "schema_version": "1.6",
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "public_lead": lead,
        })
        props = self._properties(lead, status=force_status)
        blocks = self._human_blocks(lead, state)
        if existing:
            page = await self._request("PATCH", f"/v1/pages/{existing.page_id}", json_body={"properties": props})
            await self._replace_children(existing.page_id, blocks)
            rec = self.page_to_record(page)
            if self._record_cache is not None:
                self._record_cache = [rec if r.page_id == rec.page_id else r for r in self._record_cache]
            return {"action": "updated", "record": rec.as_dict(), "state": state}
        dsid = await self._dsid()
        body = {
            "parent": {"type": "data_source_id", "data_source_id": dsid},
            "properties": props,
            "children": blocks,
        }
        page = await self._request("POST", "/v1/pages", json_body=body)
        rec = self.page_to_record(page)
        if self._record_cache is not None:
            self._record_cache.append(rec)
        return {"action": "created", "record": rec.as_dict(), "state": state}

    async def match_rows(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        index = await self.index()
        exact: dict[str, NotionRecord] = {r.lead_key: r for r in index if r.lead_key}
        companies: dict[str, NotionRecord] = {}
        for r in index:
            if r.company_key and r.company_key not in companies:
                companies[r.company_key] = r
        matches: dict[str, Any] = {}
        for row in rows:
            vid = str(row.get("visitor_id") or "")
            ck = company_key(row.get("company"))
            lk = lead_key(row.get("company"), row.get("email"), row.get("name"))
            if lk and lk in exact:
                rec = exact[lk]
                matches[vid] = {"match": "EXACT", **rec.as_dict()}
            elif ck and ck in companies:
                rec = companies[ck]
                matches[vid] = {"match": "COMPANY", **rec.as_dict()}
            else:
                matches[vid] = {"match": "NONE", "company_key": ck, "lead_key": lk}
        return {"total_saved": len(index), "matches": matches}
