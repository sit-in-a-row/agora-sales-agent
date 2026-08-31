from __future__ import annotations

import asyncio
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.notion_store import NotionRecord, NotionSalesStore, company_key, lead_key, parse_database_id


class FakeNotionStore(NotionSalesStore):
    def __init__(self):
        super().__init__("secret_test", "https://app.notion.com/p/3cdcd049963380f794a8faea1bedcab5")
        self._data_source_id = "ds123"
        self.pages: dict[str, dict] = {}
        self.children: dict[str, list[dict]] = {}
        self.seq = 0

    async def _request(self, method, path, *, json_body=None):  # type: ignore[override]
        if method == "POST" and path == "/v1/data_sources/ds123/query":
            rows = list(self.pages.values())
            filt = (json_body or {}).get("filter")
            if filt:
                prop = filt.get("property")
                kind, cond = next((k, v) for k, v in filt.items() if k != "property")
                expected = cond.get("equals")
                def val(page):
                    p = page["properties"].get(prop) or {}
                    if kind == "rich_text":
                        return "".join(x.get("text", {}).get("content", "") for x in p.get("rich_text", []))
                    return ""
                rows = [r for r in rows if val(r) == expected]
            return {"results": deepcopy(rows), "has_more": False, "next_cursor": None}
        if method == "POST" and path == "/v1/pages":
            self.seq += 1
            pid = f"page-{self.seq}"
            page = {"id": pid, "url": f"https://notion.test/{pid}", "properties": deepcopy(json_body["properties"])}
            self.pages[pid] = page
            self.children[pid] = []
            for idx, b in enumerate(json_body.get("children") or []):
                bb = deepcopy(b); bb["id"] = f"{pid}-b{idx}"; self.children[pid].append(bb)
            return deepcopy(page)
        if method == "PATCH" and path.startswith("/v1/pages/"):
            pid = path.split("/")[-1]
            self.pages[pid]["properties"] = deepcopy(json_body["properties"])
            return deepcopy(self.pages[pid])
        if method == "GET" and path.startswith("/v1/blocks/") and "/children" in path:
            pid = path.split("/")[3]
            return {"results": deepcopy(self.children.get(pid, [])), "has_more": False}
        if method == "DELETE" and path.startswith("/v1/blocks/"):
            bid = path.split("/")[-1]
            for pid, blocks in self.children.items():
                self.children[pid] = [b for b in blocks if b.get("id") != bid]
            return {}
        if method == "PATCH" and path.startswith("/v1/blocks/") and path.endswith("/children"):
            pid = path.split("/")[3]
            start = len(self.children.setdefault(pid, []))
            for i, b in enumerate(json_body.get("children") or []):
                bb = deepcopy(b); bb["id"] = f"{pid}-b{start+i}"; self.children[pid].append(bb)
            return {"results": []}
        raise AssertionError((method, path, json_body))


def sample_lead():
    return {
        "lead_id": "LEAD_X",
        "company": "고려대학교의료원",
        "company_size": "대기업",
        "members": [{"name": "지청원", "email": "ji@example.com", "title": "팀장", "company_size": "대기업"}],
        "classification": "QUALITY",
        "total_score": 82,
        "research": {
            "executive_summary": ["요약1", "요약2", "요약3"],
            "commercial_attractiveness": {"level": "HIGH", "headline": "영업가치 높음"},
            "revenue_history": [{"year": "2025", "amount_text": "1,000억원", "scope": "연결"}],
            "employee_snapshot": "1,000명+",
            "listing_status": "비상장",
            "listing_market": None,
            "ticker": None,
            "funding": {"cumulative_funding": None, "latest_round": None},
            "main_businesses": [{"name": "의료서비스", "description": "병원"}],
            "rtc_opportunities": [{"service_or_workflow": "원격상담", "recommended_product": "Video Calling", "idea": "상담"}],
            "ai_opportunities": [{"service_or_workflow": "상담 안내", "recommended_product": "Conversational AI", "idea": "안내"}],
        },
        "draft": {
            "subject_primary": "실시간 소통 플랫폼(CPaaS), Agora에서 인사 드립니다. (고려대학교의료원)",
            "full_email": "지청원 팀장님께,\n\n테스트 메일",
        },
    }


async def main():
    assert parse_database_id("https://app.notion.com/p/3cdcd049963380f794a8faea1bedcab5?v=x") == "3cdcd049963380f794a8faea1bedcab5"
    assert company_key(" 고려대학교의료원 ") == company_key("고려대학교의료원")
    assert lead_key("A", "x@y.com", "홍길동") == lead_key("A", "x@y.com", "다른이름")

    s = FakeNotionStore()
    lead = sample_lead()
    raw_state = {"research_raw": {"company_id": "C1", "canonical_company_name": "고려대학교의료원"}}
    created = await s.upsert_lead(lead, raw_state=raw_state)
    assert created["action"] == "created"
    rec = await s.find_exact(lead_key("고려대학교의료원", "ji@example.com", "지청원"))
    assert rec and rec.company == "고려대학교의료원"
    loaded = await s.load_record(rec)
    assert loaded["lead"]["draft"]["full_email"].endswith("테스트 메일")
    assert loaded["state"]["research_raw"]["company_id"] == "C1"

    lead["draft"]["full_email"] = "수정 메일"
    updated = await s.upsert_lead(lead, force_status="MANUAL_EDITED")
    assert updated["action"] == "updated"
    rec2 = await s.find_exact(lead_key("고려대학교의료원", "ji@example.com", "지청원"))
    assert rec2 and rec2.status == "MANUAL_EDITED"
    loaded2 = await s.load_record(rec2)
    assert loaded2["lead"]["draft"]["full_email"] == "수정 메일"

    matches = await s.match_rows([
        {"visitor_id": "1", "company": "고려대학교의료원", "email": "ji@example.com", "name": "지청원"},
        {"visitor_id": "2", "company": "고려대학교의료원", "email": "new@example.com", "name": "다른 사람"},
        {"visitor_id": "3", "company": "새 회사", "email": "new@new.com", "name": "신규"},
    ])
    assert matches["matches"]["1"]["match"] == "EXACT"
    assert matches["matches"]["2"]["match"] == "COMPANY"
    assert matches["matches"]["3"]["match"] == "NONE"
    print("NOTION STORE PASS")


if __name__ == "__main__":
    asyncio.run(main())
