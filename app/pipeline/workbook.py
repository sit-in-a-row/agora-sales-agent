from __future__ import annotations

import csv
import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.models import VisitorRecord
from app.pipeline.xlsx_io import XlsxBook, count_data_rows

FIELD_ALIASES: dict[str, list[str]] = {
    "visited_at": ["방문시간", "방문 시간", "visit time", "visited_at"],
    "attendee_name": ["성명", "이름", "name", "attendee_name"],
    "phone": ["휴대폰", "전화번호", "phone", "mobile"],
    "email": ["이메일", "email", "e-mail"],
    "company": ["회사명/소속", "회사명", "소속", "company", "organization"],
    "department": ["부서", "department", "team"],
    "job_title": ["직함", "직책", "job title", "title"],
    "visitor_role": ["개인 구분", "개인구분", "visitor role"],
    "region": ["지역", "region"],
    "industry": ["업종분류", "업종", "industry"],
    "seniority_band": ["직위", "seniority", "position level"],
    "function": ["담당부서", "담당 부서", "function"],
    "product_interests": ["관심품목", "관심 품목", "product interests"],
    "industry_ai": ["산업별 AI 솔루션", "산업별ai솔루션"],
    "business_ai": ["AI 비즈니스 솔루션", "ai비즈니스솔루션"],
    "genai": ["생성형 AI & 콘텐츠 혁신", "생성형ai&콘텐츠혁신"],
    "ai_platform": ["AI 플랫폼 & 인프라", "ai플랫폼&인프라"],
    "event_interests": ["관심 부대행사", "관심부대행사"],
    "visit_purpose": ["참관목적", "참관 목적", "visit purpose"],
    "acquisition_channel": ["전시회 주요 인지경로", "인지경로"],
    "attendee_type": ["등록구분", "등록 구분", "attendee type"],
    "company_size": ["기업 종류", "기업종류", "회사 규모", "기업 규모", "company size", "company_size"],
}

def _header_key(value: Any) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"[\s_\-/]+", "", unicodedata.normalize("NFKC", text)).lower()

ALIAS_LOOKUP = {_header_key(alias): logical for logical, aliases in FIELD_ALIASES.items() for alias in aliases}

def light_company_key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", "" if value is None else str(value)).lower().strip()
    return re.sub(r"[\s\.,·'\"`~!@#$%^&*_=+|:;?/\\\-]+", "", text)

def stable_id(prefix: str, *parts: Any) -> str:
    raw = "\x1f".join("" if p is None else str(p) for p in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:14]}"

def row_is_empty(values: Iterable[Any]) -> bool:
    return all(v is None or str(v).strip() == "" for v in values)

def find_sheet_name(names: list[str], prefix: str) -> str | None:
    key = prefix.replace(" ", "").lower()
    return next((n for n in names if n.replace(" ", "").lower().startswith(key)), None)

def find_impt_sheet_name(names: list[str]) -> str | None:
    """Find the combined Impt sheet, excluding legacy Impt_B2B / Impt_B2C sheets."""
    for name in names:
        compact = name.replace(" ", "").lower()
        if compact.startswith("impt_b2b") or compact.startswith("impt_b2c"):
            continue
        if compact == "impt" or compact.startswith("impt("):
            return name
    return None

@dataclass(slots=True)
class WorkbookInspection:
    filename: str
    file_type: str
    sheets: list[dict[str, Any]]
    suggested_source_mode: str
    suggested_source_label: str
    logical_headers: dict[str, str]
    estimated_records: int
    notes: list[str]
    company_size_counts: dict[str, int] | None = None
    def as_dict(self) -> dict[str, Any]:
        return {k:getattr(self,k) for k in self.__dataclass_fields__}

class WorkbookParser:
    def inspect(self, path: Path) -> WorkbookInspection:
        if path.suffix.lower() == ".csv":
            records, mapping = self._read_csv(path)
            return WorkbookInspection(path.name, "csv", [], "csv", "CSV", mapping, len(records), [], {})
        with XlsxBook(path) as wb:
            names = wb.sheetnames
            sheets = [{"name": n, "data_rows": count_data_rows(wb.rows(n))} for n in names]
            main = find_sheet_name(names, "Main")
            impt = find_impt_sheet_name(names)
            notes: list[str] = []

            # v1.5 default: use the new combined Impt sheet when present.
            source_mode = "impt_all" if impt else "main"
            source_label = impt or main or names[0]
            estimated = count_data_rows(wb.rows(source_label))

            size_counts: dict[str, int] = {}
            if impt:
                impt_records = self._read_sheet(wb, impt)
                for record in impt_records:
                    key = (record.company_size or "미분류").strip() or "미분류"
                    size_counts[key] = size_counts.get(key, 0) + 1
                if size_counts:
                    ordered = [f"{k} {size_counts[k]}건" for k in ("대기업", "중견기업", "스타트업", "미분류") if k in size_counts]
                    notes.append("Impt 기업 종류: " + " / ".join(ordered))

            headers_source = impt or main or names[0]
            headers = wb.rows(headers_source)[0] if wb.rows(headers_source) else []
            return WorkbookInspection(
                path.name, "xlsx", sheets, source_mode, source_label,
                self._map_headers(headers), estimated, notes, size_counts
            )

    def load_records(self,path:Path,source_mode:str="auto") -> tuple[list[VisitorRecord],dict[str,Any]]:
        if path.suffix.lower()==".csv":
            records,mapping=self._read_csv(path)
            return records,{"source":"CSV","mapping":mapping,"notes":[]}
        with XlsxBook(path) as wb:
            names=wb.sheetnames
            main=find_sheet_name(names,"Main")
            impt=find_impt_sheet_name(names)
            notes=[]

            if source_mode=="auto":
                source_mode="impt_all" if impt else ("main" if main else f"sheet:{names[0]}")

            impt_modes = {
                "impt_all": None,
                "impt_large": {"대기업"},
                "impt_mid": {"중견기업"},
                "impt_startup": {"스타트업"},
                "impt_large_mid": {"대기업", "중견기업"},
                "impt_large_startup": {"대기업", "스타트업"},
                "impt_mid_startup": {"중견기업", "스타트업"},
            }

            if source_mode in impt_modes:
                if not impt:
                    raise ValueError("Impt 시트를 찾지 못했습니다.")
                records=self._read_sheet(wb,impt)
                allowed=impt_modes[source_mode]
                if allowed is not None:
                    records=[r for r in records if (r.company_size or "").strip() in allowed]
                    labels=" + ".join([x for x in ("대기업","중견기업","스타트업") if x in allowed])
                    notes.append(f"Impt 기업 종류 필터: {labels} → {len(records)}건")
                    source_label=f"{impt} · {labels}"
                else:
                    notes.append(f"Impt 전체 {len(records)}건")
                    source_label=impt
            elif source_mode=="main":
                if not main:
                    raise ValueError("Main 시트를 찾지 못했습니다.")
                records=self._read_sheet(wb,main)
                source_label=main
            elif source_mode.startswith("sheet:"):
                name=source_mode.split(":",1)[1]
                if name not in names:
                    raise ValueError(f"시트를 찾지 못했습니다: {name}")
                records=self._read_sheet(wb,name)
                source_label=name
            else:
                raise ValueError(f"지원하지 않는 source_mode: {source_mode}")
            mapping=self._map_headers(self._headers(wb,impt or main or names[0]))
            return records,{"source":source_label,"mapping":mapping,"notes":notes}

    def _headers(self,wb:XlsxBook,name:str)->list[Any]:
        rows=wb.rows(name); return list(rows[0]) if rows else []
    def _map_headers(self,headers:Iterable[Any])->dict[str,str]:
        out={}
        for h in headers:
            logical=ALIAS_LOOKUP.get(_header_key(h))
            if logical and h is not None: out[logical]=str(h)
        return out
    def _read_sheet(self,wb:XlsxBook,name:str)->list[VisitorRecord]:
        all_rows=wb.rows(name); headers=list(all_rows[0]) if all_rows else []; rows=[r for r in all_rows[1:] if not row_is_empty(r)]
        return self._records_from_rows(headers,rows,name)
    def _records_from_rows(self,headers:list[Any],rows:Iterable[Iterable[Any]],source_sheet:str)->list[VisitorRecord]:
        header_text=["" if h is None else str(h).strip() for h in headers]
        logical_by_index={i:ALIAS_LOOKUP[_header_key(h)] for i,h in enumerate(header_text) if _header_key(h) in ALIAS_LOOKUP}
        out=[]
        for offset,row in enumerate(rows,start=2):
            vals=list(row)
            if row_is_empty(vals): continue
            raw={header_text[i] or f"col_{i+1}": vals[i] if i<len(vals) else None for i in range(len(header_text))}
            logical={name:None for name in FIELD_ALIASES}
            for i,name in logical_by_index.items():
                if i<len(vals): logical[name]=None if vals[i] is None else str(vals[i]).strip()
            vid=stable_id("VIS",source_sheet,offset,logical.get("attendee_name"),logical.get("email"),logical.get("company"),logical.get("visited_at"))
            out.append(VisitorRecord(visitor_id=vid,raw_row_number=offset,source_sheet=source_sheet,raw=raw,**logical))
        return out
    def _derive_b2b_rows(self, wb:XlsxBook, main_name:str, criteria_name:str) -> tuple[list[list[Any]],dict[str,int]]:
        """Recreate the workbook's B2B composition.

        Block 1: companies in 분류 기준 `Impt_B2B` column.
        Block 2: educational orgs in `Not Important` company column where department/title/visitor-role
                 contains one of the role keywords from the adjacent role column.

        The workbook title says `51 + 10`, but the current criteria can evolve. We therefore report
        the count produced by the *current* rules rather than hard-coding the title.
        """
        core = self._derive_segment_rows(wb, main_name, criteria_name, "Impt_B2B")
        main_rows = wb.rows(main_name)
        crit_rows = wb.rows(criteria_name)
        if not main_rows or not crit_rows:
            return core, {"core":len(core),"education_role":0}
        headers = main_rows[0]
        logical_idx = {
            ALIAS_LOOKUP.get(_header_key(h)): i
            for i,h in enumerate(headers)
            if ALIAS_LOOKUP.get(_header_key(h))
        }
        company_idx = logical_idx.get("company")
        if company_idx is None:
            return core, {"core":len(core),"education_role":0}

        # Criteria A/B correspond to Not Important company + role rules in this workbook.
        education_orgs = {
            light_company_key(r[0]) for r in crit_rows[2:]
            if len(r)>0 and r[0] is not None and str(r[0]).strip()
        }
        role_keywords = [
            unicodedata.normalize("NFKC", str(r[1])).strip().lower() for r in crit_rows[2:]
            if len(r)>1 and r[1] is not None and str(r[1]).strip()
        ]
        role_fields = [logical_idx.get("department"), logical_idx.get("job_title"), logical_idx.get("visitor_role")]
        education_rows: list[list[Any]] = []
        for row in main_rows[1:]:
            if row_is_empty(row) or company_idx >= len(row):
                continue
            if light_company_key(row[company_idx]) not in education_orgs:
                continue
            parts=[]
            for i in role_fields:
                if i is not None and i < len(row) and row[i] is not None:
                    parts.append(unicodedata.normalize("NFKC", str(row[i])).lower())
            text=" ".join(parts)
            if text and any(keyword in text for keyword in role_keywords):
                education_rows.append(row)

        # Dedupe exact Main rows in case future criteria overlap.
        combined=[]
        seen=set()
        for row in core + education_rows:
            key=tuple("" if v is None else str(v) for v in row)
            if key not in seen:
                seen.add(key)
                combined.append(row)
        return combined,{"core":len(core),"education_role":len(education_rows)}

    def _derive_segment_rows(self,wb:XlsxBook,main_name:str,criteria_name:str,segment_header:str)->list[list[Any]]:
        main_rows=wb.rows(main_name); crit_rows=wb.rows(criteria_name)
        if not main_rows or not crit_rows: return []
        crit_header=crit_rows[0]; col_idx=next((i for i,v in enumerate(crit_header) if _header_key(v)==_header_key(segment_header)),None)
        if col_idx is None: return []
        allowed={light_company_key(r[col_idx]) for r in crit_rows[2:] if col_idx<len(r) and r[col_idx] is not None and str(r[col_idx]).strip()}
        if not allowed: return []
        headers=main_rows[0]; company_idx=next((i for i,h in enumerate(headers) if ALIAS_LOOKUP.get(_header_key(h))=="company"),None)
        if company_idx is None: return []
        return [r for r in main_rows[1:] if not row_is_empty(r) and company_idx<len(r) and light_company_key(r[company_idx]) in allowed]
    def _read_csv(self,path:Path)->tuple[list[VisitorRecord],dict[str,str]]:
        raw=path.read_text(encoding="utf-8-sig",errors="replace"); rows=list(csv.reader(raw.splitlines()))
        if not rows:return [],{}
        return self._records_from_rows(rows[0],rows[1:],"CSV"),self._map_headers(rows[0])
