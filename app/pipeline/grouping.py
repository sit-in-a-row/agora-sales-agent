from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from typing import Iterable

from app.models import LeadUnit, ResolvedVisitor


KOREAN_DT_RE = re.compile(
    r"(?P<y>\d{4})[-./](?P<m>\d{1,2})[-./](?P<d>\d{1,2})\s*"
    r"(?:(?P<ampm>오전|오후)\s*)?(?P<h>\d{1,2}):(?P<mi>\d{2})(?::(?P<s>\d{2}))?"
)


def parse_visit_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    m = KOREAN_DT_RE.search(text)
    if m:
        hour = int(m.group("h"))
        ampm = m.group("ampm")
        if ampm == "오후" and hour < 12:
            hour += 12
        elif ampm == "오전" and hour == 12:
            hour = 0
        return datetime(
            int(m.group("y")), int(m.group("m")), int(m.group("d")),
            hour, int(m.group("mi")), int(m.group("s") or 0),
        )
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def _lead_id(company_id: str, member_ids: Iterable[str]) -> str:
    raw = company_id + "|" + "|".join(sorted(member_ids))
    return "LEAD_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:14]


def build_lead_units(visitors: list[ResolvedVisitor], window_minutes: int = 20) -> list[LeadUnit]:
    """Precision-first grouping: same company + non-empty same canonical department + time window."""
    by_company: dict[str, list[ResolvedVisitor]] = {}
    for v in visitors:
        if not v.company_id or not v.canonical_company_name:
            # unresolved entries remain individual under a synthetic company bucket
            cid = v.company_id or f"UNRESOLVED_{v.visitor_id}"
        else:
            cid = v.company_id
        by_company.setdefault(cid, []).append(v)

    units: list[LeadUnit] = []
    window = timedelta(minutes=window_minutes)

    for company_id, company_visitors in by_company.items():
        # Candidates with missing department never group.
        candidates = sorted(company_visitors, key=lambda v: parse_visit_datetime(v.visited_at) or datetime.max)
        used: set[str] = set()
        for i, visitor in enumerate(candidates):
            if visitor.visitor_id in used:
                continue
            dt = parse_visit_datetime(visitor.visited_at)
            dept = (visitor.canonical_department or "").strip()
            group = [visitor]
            if dt and dept:
                for other in candidates[i + 1:]:
                    if other.visitor_id in used:
                        continue
                    other_dt = parse_visit_datetime(other.visited_at)
                    other_dept = (other.canonical_department or "").strip()
                    if not other_dt:
                        continue
                    if other_dt - dt > window:
                        break
                    if other_dept and other_dept.casefold() == dept.casefold():
                        group.append(other)
            for member in group:
                used.add(member.visitor_id)

            canonical_company = visitor.canonical_company_name or visitor.company or "Unknown"
            dts = [parse_visit_datetime(m.visited_at) for m in group]
            dts = [d for d in dts if d]
            lid = _lead_id(company_id, [m.visitor_id for m in group])
            units.append(LeadUnit(
                lead_id=lid,
                company_id=company_id,
                canonical_company_name=canonical_company,
                canonical_department=dept or None,
                lead_unit_type="GROUP" if len(group) > 1 else "INDIVIDUAL",
                member_ids=[m.visitor_id for m in group],
                members=group,
                group_time_start=min(dts).isoformat() if dts else None,
                group_time_end=max(dts).isoformat() if dts else None,
            ))
    return sorted(units, key=lambda u: (u.canonical_company_name.casefold(), u.group_time_start or ""))
