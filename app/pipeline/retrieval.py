from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from app.config import KNOWLEDGE_DIR
from app.models import CompanyResearch, LeadUnit, RetrievedDoc, RetrievalBundle


DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "luxury_retail": ["retail", "리테일", "유통", "럭셔리", "luxury", "fashion", "패션", "crm", "customer experience", "고객관리"],
    "bfsi": ["금융", "은행", "보험", "fintech", "bfsi", "금융서비스", "kyc", "verification"],
    "education": ["교육", "대학", "학교", "education", "university", "tutoring", "학습"],
    "aiot_robotics": ["제조", "robot", "로봇", "iot", "aiot", "device", "디바이스", "hardware", "하드웨어"],
    "market_research": ["리서치", "survey", "조사", "시장조사", "설문"],
    "sales_marketing": ["영업", "marketing", "마케팅", "sales", "buyer", "바이어", "crm"],
}


def _parse_listish(value: str | None) -> str:
    return value or ""


def _parse_frontmatter(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    meta: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip()
    return meta


def _infer_category(path: Path) -> str:
    parts = {p.lower() for p in path.parts}
    if "04_cases" in parts or "cases" in parts:
        return "case"
    if "03_products" in parts or "products" in parts:
        return "product"
    if "01_company" in parts:
        return "company"
    if "05_sales" in parts:
        return "sales"
    return "other"


def _safe_doc_id(path: Path, prefix: str = "CUSTOM") -> str:
    stem = re.sub(r"[^A-Za-z0-9가-힣]+", "_", path.stem).strip("_").upper() or "DOC"
    return f"{prefix}_{stem}"


class CorpusRetriever:
    """Lightweight retrieval over Markdown/TXT corpus.

    v1.2 intentionally discovers files at runtime. `document_index.csv` remains useful,
    but is no longer a required manual maintenance step when a new case is added.
    """

    def __init__(self, root: Path = KNOWLEDGE_DIR, additional_roots: list[Path] | None = None):
        self.root = root
        self.additional_roots = [Path(p) for p in (additional_roots or []) if Path(p).exists()]
        self.index = self._load_and_discover_index()
        quick_path = root / "00_meta" / "quick_retrieval_map.json"
        self.quick = json.loads(quick_path.read_text(encoding="utf-8")) if quick_path.exists() else {}
        self.by_doc_id = {row["doc_id"]: row for row in self.index if row.get("doc_id")}

    def _load_and_discover_index(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        seen_paths: set[str] = set()
        index_path = self.root / "00_meta" / "document_index.csv"
        if index_path.exists():
            with index_path.open(encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    rel = row.get("path") or ""
                    if not rel:
                        continue
                    abs_path = self.root / rel
                    row = dict(row)
                    row["_abs_path"] = str(abs_path)
                    rows.append(row)
                    seen_paths.add(str(abs_path.resolve()) if abs_path.exists() else str(abs_path))

        # Discover any new .md/.txt files in base corpus and user-provided per-run case roots.
        roots = [(self.root, "BASE")] + [(r, "CUSTOM") for r in self.additional_roots]
        for scan_root, prefix in roots:
            if not scan_root.exists():
                continue
            for path in sorted([*scan_root.rglob("*.md"), *scan_root.rglob("*.txt")]):
                key = str(path.resolve())
                if key in seen_paths:
                    continue
                meta = _parse_frontmatter(path)
                doc_id = meta.get("doc_id") or _safe_doc_id(path, prefix)
                category = meta.get("category") or _infer_category(path)
                market = meta.get("market") or ("KR" if "korea" in {p.lower() for p in path.parts} else "")
                priority = meta.get("retrieval_priority") or ("high" if category == "case" else "medium")
                tags = meta.get("tags") or path.stem.replace("_", " ")
                source_ids = meta.get("source_ids") or ""
                try:
                    rel = str(path.relative_to(self.root)) if self.root in path.parents else str(path)
                except Exception:
                    rel = str(path)
                rows.append({
                    "doc_id": doc_id,
                    "path": rel,
                    "category": category,
                    "market": market,
                    "priority": priority,
                    "tags": tags,
                    "source_ids": source_ids,
                    "_abs_path": str(path),
                    "_dynamic": "1",
                })
                seen_paths.add(key)
        return rows

    def _lead_text(self, lead: LeadUnit, research: CompanyResearch) -> str:
        pieces = [lead.canonical_company_name, lead.canonical_department or "", research.business_summary]
        for m in lead.members:
            pieces.extend([
                m.industry or "", m.function or "", m.product_interests or "",
                m.industry_ai or "", m.business_ai or "", m.genai or "",
                m.ai_platform or "", m.visit_purpose or "", m.visitor_role or "",
            ])
        pieces.extend(s.topic + " " + s.summary for s in research.recent_signals)
        return " ".join(pieces).lower()

    def _domains(self, text: str) -> list[str]:
        scored = []
        for domain, kws in DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in kws if kw.lower() in text)
            if score:
                scored.append((score, domain))
        return [d for _, d in sorted(scored, reverse=True)[:2]]

    def retrieve(self, lead: LeadUnit, research: CompanyResearch) -> RetrievalBundle:
        text = self._lead_text(lead, research)
        requested_ids: list[str] = ["CLAIMS_GUARDRAILS", "CURRENT_STRATEGY_2026", "KOREA_BUSINESS_CONTEXT"]
        for domain in self._domains(text):
            item = self.quick.get(domain, {})
            for key in ("company_docs", "product_docs", "case_docs"):
                requested_ids.extend(item.get(key, []))

        score_by_id: dict[str, float] = {}
        tokens = set(re.findall(r"[A-Za-z0-9가-힣_]+", text))
        for row in self.index:
            doc_id = row.get("doc_id")
            if not doc_id or doc_id == "README":
                continue
            tags = set(re.findall(r"[A-Za-z0-9가-힣_]+", _parse_listish(row.get("tags")).lower()))
            score = len(tokens & tags) * 2.0
            market = (row.get("market") or "").upper()
            if market == "KR":
                score += 2.5
            if (row.get("priority") or "").lower() == "critical":
                score += 2
            elif (row.get("priority") or "").lower() == "high":
                score += 1
            if row.get("_dynamic") == "1" and (row.get("category") or "") == "case":
                # Newly added cases should have a fair chance to surface, but still need semantic overlap.
                score += 1.5
            if score > 0:
                score_by_id[doc_id] = score

        ordered: list[str] = []
        for doc_id in requested_ids:
            if doc_id not in ordered:
                ordered.append(doc_id)
        for doc_id, _ in sorted(score_by_id.items(), key=lambda kv: kv[1], reverse=True):
            if doc_id not in ordered:
                ordered.append(doc_id)

        caps = {"company": 2, "company_strategy": 2, "product": 3, "case": 3, "guardrail": 1, "sales": 2, "sales_synthesis": 2, "other": 1}
        used: dict[str, int] = {}
        docs: list[RetrievedDoc] = []
        for doc_id in ordered:
            row = self.by_doc_id.get(doc_id)
            if not row:
                continue
            category = row.get("category") or "other"
            cap = caps.get(category, 1)
            if used.get(category, 0) >= cap:
                continue
            abs_raw = row.get("_abs_path")
            path = Path(abs_raw) if abs_raw else self.root / row["path"]
            if not path.exists():
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue
            docs.append(RetrievedDoc(
                doc_id=doc_id, path=str(path), category=category,
                market=row.get("market"), priority=row.get("priority"),
                content=content[:12000], score=score_by_id.get(doc_id, 100 if doc_id in requested_ids else 0),
            ))
            used[category] = used.get(category, 0) + 1
            if len(docs) >= 11:
                break

        return RetrievalBundle(lead_id=lead.lead_id, docs=docs, doc_ids=[d.doc_id for d in docs])

    @staticmethod
    def compact_context(bundle: RetrievalBundle, max_chars: int = 30000) -> str:
        chunks = []
        used = 0
        for doc in bundle.docs:
            chunk = f"\n\n### DOC {doc.doc_id} | category={doc.category} | market={doc.market or 'n/a'} | priority={doc.priority or 'n/a'}\n{doc.content.strip()}"
            if used + len(chunk) > max_chars:
                break
            chunks.append(chunk)
            used += len(chunk)
        return "".join(chunks)
