from __future__ import annotations

import hashlib
import random
from typing import Any, TypeVar

from pydantic import BaseModel

from app.agents.provider import ProviderResult
from app.models import (
    Axis10, Axis20, Axis25, Axis5, AgoraOpportunity, AgoraProductCheck, BusinessLine,
    BusinessSignal, CommercialAttractiveness, CompanyResearch, CompanyScale, EmailDraft,
    EntityResolutionBatch, EntityResolutionItem, EvidenceItem, FundingInfo, LeadScore,
    LeadScoreBatch, LocalPresence, RevenueRecord, ReviewDimensions, SalesReview,
    SalesStrategy, SupplementalResearch,
)

T = TypeVar("T", bound=BaseModel)


class MockProvider:
    """API key 없이 UI / pipeline을 검증하기 위한 deterministic mock provider."""

    def __init__(self, trace_callback=None):
        self.trace_callback = trace_callback

    def _trace(self, payload):
        if self.trace_callback:
            try:
                self.trace_callback(payload)
            except Exception:
                pass

    def _score_seed(self, text: str) -> int:
        return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)

    async def parse(
        self,
        *,
        model: str,
        system_prompt: str,
        user_payload: Any,
        response_model: type[T],
        reasoning_effort: str = "low",
        web_search: bool = False,
        require_web: bool = False,
        prompt_cache_key: str | None = None,
        trace_label: str | None = None,
    ) -> ProviderResult:
        label = trace_label or prompt_cache_key or response_model.__name__
        self._trace({'phase':'request','call_id':'demo','agent':label,'model':model,'reasoning_effort':reasoning_effort,'web_search':web_search,'system_prompt':system_prompt,'user_payload':user_payload,'demo':True})
        if response_model is EntityResolutionBatch:
            rows = user_payload.get("records", [])
            items = []
            for row in rows:
                company = (row.get("company_raw") or "Unknown").strip()
                dept = (row.get("department_raw") or "").strip() or None
                title = (row.get("title_raw") or "").lower()
                if any(k in title for k in ["대표", "ceo", "전무", "상무", "vp", "부사장"]):
                    seniority = "EXECUTIVE"
                elif any(k in title for k in ["director", "head", "부장", "팀장", "이사"]):
                    seniority = "DIRECTOR_HEAD"
                elif any(k in title for k in ["manager", "과장", "차장", "lead"]):
                    seniority = "MANAGER_LEAD"
                elif any(k in title for k in ["intern", "인턴", "student", "학생"]):
                    seniority = "ENTRY_INTERN_STUDENT"
                else:
                    seniority = "SPECIALIST_IC"
                items.append(EntityResolutionItem(
                    record_key=row["record_key"], company_raw=company, department_raw=dept,
                    canonical_company_name=company, local_entity_name=company,
                    company_name_ko=company if any(ord(c) > 127 for c in company) else None,
                    company_name_en=company if company.isascii() else None,
                    market_scope="South Korea", website_domain=None,
                    canonical_department=dept, department_family=dept,
                    role_family=row.get("title_raw") or None, seniority_level=seniority,
                    identity_status="RESOLVED", resolver_confidence=0.90,
                    needs_web_resolution=False, ambiguity_reason=None,
                ))
            parsed = EntityResolutionBatch(results=items)
        elif response_model is CompanyResearch:
            company = user_payload.get("canonical_company_name", "Unknown")
            cid = user_payload.get("company_id", "company")
            source_url = "https://example.com/mock-source"
            ev = EvidenceItem(
                evidence_id=f"EV_{cid}_1", claim=f"{company} 관련 mock business signal",
                url=source_url, title="Mock source", publisher="Mock",
                published_date="2026-08-01", source_quality="PRIMARY_OFFICIAL",
            )
            parsed = CompanyResearch(
                company_id=cid, canonical_company_name=company, official_company_name=company,
                one_line_description=f"{company}의 DEMO 기업 설명",
                research_scope="DEMO MODE — 실제 웹 검색이 아닙니다.",
                executive_summary=[
                    f"{company} DEMO 기업 리서치",
                    "DEMO 기준 대형 account로 가정",
                    "최근 Digital / AI 관심 signal 존재",
                    "Agora RTC / AI 적용 가능성은 실제 실행에서 웹 근거로 확인 필요",
                ],
                local_presence=LocalPresence(
                    korea_role="DEMO local operation", korea_entity_name=company,
                    korea_employee_range="100~499명 (DEMO)", confidence=0.7, evidence_ids=[ev.evidence_id],
                ),
                company_scale=CompanyScale(
                    category="LARGE", basis="DEMO", confidence=0.7,
                    evidence_ids=[ev.evidence_id],
                ),
                listing_status="DEMO 확인 필요", listing_market=None, ticker=None,
                employee_snapshot="한국 임직원 100~499명 (DEMO)",
                revenue_history=[RevenueRecord(year="2025", amount_text="약 1,000억원 (DEMO)", scope="한국", source_kind="UNKNOWN", evidence_ids=[ev.evidence_id])],
                funding=FundingInfo(applicable=False, note="상장/대기업 가정 DEMO", evidence_ids=[]),
                main_businesses=[BusinessLine(name="Core Business", description="DEMO main business", evidence_ids=[ev.evidence_id])],
                commercial_attractiveness=CommercialAttractiveness(
                    level="HIGH", headline="규모·구매력 관점에서 영업 가치 높은 DEMO account",
                    reasons=["대형 account 가정", "Digital/AI 관심 signal"], evidence_ids=[ev.evidence_id],
                ),
                business_summary=f"{company}의 DEMO research 결과입니다.",
                rtc_opportunities=[AgoraOpportunity(rank=1, service_or_workflow="DEMO 고객 접점", recommended_product="Video Calling / Voice Calling", idea="실시간 고객 상호작용", fit_confidence=0.75, company_evidence_ids=[ev.evidence_id], agora_evidence_ids=[])],
                ai_opportunities=[AgoraOpportunity(rank=1, service_or_workflow="DEMO 고객 문의", recommended_product="Conversational AI", idea="Voice AI 기반 고객 응대", fit_confidence=0.72, company_evidence_ids=[ev.evidence_id], agora_evidence_ids=[])],
                agora_product_check=AgoraProductCheck(checked=True, summary="DEMO에서는 실제 공식 제품 웹 확인 생략", official_source_urls=[]),
                recent_signals=[BusinessSignal(
                    signal_id=f"SIG_{cid}_1", date="2026-08-01", topic="Digital / AI",
                    summary="DEMO MODE business signal", korea_relevance="DIRECT_KOREA",
                    department_tags=["Digital"], sales_relevance=0.8,
                    evidence_ids=[ev.evidence_id],
                )],
                evidence=[ev], unknowns=[], research_confidence=0.75,
            )
        elif response_model is LeadScoreBatch:
            scores = []
            for lead in user_payload.get("leads", []):
                lid = lead["lead_id"]
                text = str(lead)
                seed = self._score_seed(text)
                rng = random.Random(seed)
                ap = rng.randint(16, 25)
                ci = rng.randint(8, 20)
                di = rng.randint(8, 20)
                af = rng.randint(10, 20)
                rt = rng.randint(3, 10)
                eq = 4
                total = ap + ci + di + af + rt + eq
                cls = "QUALITY" if total >= 75 else "NORMAL" if total >= 45 else "TRASH"
                scores.append(LeadScore(
                    lead_id=lid,
                    axes={
                        "account_potential": Axis25(score=ap, reason="DEMO", evidence_refs=[]),
                        "contact_influence": Axis20(score=ci, reason="DEMO", evidence_refs=[]),
                        "declared_intent": Axis20(score=di, reason="DEMO", evidence_refs=[]),
                        "agora_fit": Axis20(score=af, reason="DEMO", evidence_refs=[]),
                        "recent_trigger": Axis10(score=rt, reason="DEMO", evidence_refs=[]),
                        "evidence_quality": Axis5(score=eq, reason="DEMO", evidence_refs=[]),
                    },
                    total_score=total, classification=cls,
                    classification_confidence=0.82,
                    positive_signals=["DEMO positive signal"], negative_signals=[], uncertainties=[],
                    classification_rationale="DEMO MODE classification",
                    supplemental_research_recommended=False,
                    supplemental_research_queries=[],
                    review_level="HIGH_TOUCH" if cls == "QUALITY" else "STANDARD" if cls == "NORMAL" else "NONE",
                ))
            parsed = LeadScoreBatch(scores=scores)
        elif response_model is SupplementalResearch:
            parsed = SupplementalResearch(
                lead_id=user_payload["lead_id"], summary="DEMO supplemental research",
                recent_signals=[], evidence=[], confidence=0.7,
            )
        elif response_model is SalesStrategy:
            lead = user_payload["lead"]
            parsed = SalesStrategy(
                lead_id=lead["lead_id"], outreach_mode="GROUP" if lead.get("lead_unit_type") == "GROUP" else "INDIVIDUAL",
                recipient_plan="DEMO recipient plan", primary_angle="행사 후속 재소개",
                secondary_angle=None, customer_hypothesis="DEMO hypothesis",
                why_now="AI Summit Agora 부스 방문 후속 연락",
                agora_value_proposition="Agora의 RTC 및 Conversational AI 역량을 큰 범주에서 재소개",
                company_context=[f"{lead.get('canonical_company_name','귀사')}와 Agora가 함께 살펴볼 수 있는 접점"],
                use_case_context=[],
                selected_features=[],
                selected_ai_points=[],
                selected_value_points=["API/SDK 기반 실시간 커뮤니케이션 기능 적용"],
                selected_references=[],
                product_doc_ids=user_payload.get("retrieval_doc_ids", [])[:2],
                case_doc_ids=[], prospect_evidence_ids=[], agora_claim_ids=[],
                cta="편하신 일정에 간단한 화상 또는 방문 미팅", avoid_claims=[],
                email_brief="행사 방문 감사 → Agora 큰 범주 소개 → 승인된 회사 맥락 → 부담 낮은 미팅 제안",
            )
        elif response_model is EmailDraft:
            lead = user_payload["lead"]
            company = lead.get("canonical_company_name", "귀사")
            name = (lead.get("members") or [{}])[0].get("attendee_name") or "담당자"
            slots = user_payload.get("approved_writer_slots") or {}
            company_context = (slots.get("company_context") or [""])[0]
            context_sentence = f"\n\n{company_context}과 관련해 아고라의 기술을 함께 살펴볼 수 있는 부분이 있을 것으로 생각합니다." if company_context else ""
            sender_name = user_payload.get("sender_name") or "담당자"
            body = (
                f"{name} 담당자님 안녕하세요.\n\n"
                "지난 AI Summit Seoul & EXPO 2026 아고라 부스에 방문해주셔서 감사합니다. "
                "당시 짧게 소개드렸던 아고라의 제품과 솔루션을 다시 한번 소개드리고자 연락드립니다.\n\n"
                f"전 세계 실시간 소통 기술을 제공하는 아고라(Agora Inc., NASDAQ: API)의 한국 담당자 {sender_name}입니다. "
                "아고라는 음성·영상통화, 라이브 스트리밍, 텍스트 메시징 등 실시간 소통 기능을 API와 SDK 형태로 제공하고 있으며, Conversational AI 영역으로도 기술을 확장하고 있습니다."
                f"{context_sentence}\n\n"
                "관련해 간단히 이야기 나눠보실 수 있다면 편하신 일정 말씀 부탁드립니다."
            )
            closing = user_payload.get("sender_signature") or "Agora 드림"
            parsed = EmailDraft(
                lead_id=lead["lead_id"], subject_primary="AI Summit Seoul & EXPO 2026 방문 감사 및 아고라 소개",
                subject_alternatives=["[AI Summit Seoul & EXPO 2026] 아고라 솔루션 관련 연락드립니다", "실시간 소통 및 AI 솔루션 관련 연락드립니다 - Agora"],
                greeting=f"{name} 담당자님 안녕하세요.", body=body, closing=closing,
                full_email=body + "\n\n" + closing,
                prospect_evidence_ids_used=(user_payload.get("approved_source_refs") or {}).get("prospect_evidence_ids", []),
                agora_doc_ids_used=(user_payload.get("approved_source_refs") or {}).get("agora_doc_ids", []),
                agora_claim_ids_used=(user_payload.get("approved_source_refs") or {}).get("agora_claim_ids", []),
            )
        elif response_model is SalesReview:
            lead_id = user_payload["lead_id"]
            dims = ReviewDimensions(
                factual_grounding=24, account_relevance=18, product_fit=14,
                personalization=13, persuasion_clarity=9, tone=9, cta=5,
            )
            parsed = SalesReview(
                lead_id=lead_id, dimensions=dims, total_score=92, decision="PASS",
                issues=[], unsupported_claims=[], revision_instructions=None,
                classification_recheck_flag=False, human_review_reasons=[],
            )
        else:
            raise RuntimeError(f"MockProvider does not support {response_model}")

        raw = {"demo": True}
        sources = [{"url": "https://example.com/mock-source", "title": "Mock source", "type": "url"}] if web_search else []
        self._trace({'phase':'response','call_id':'demo','agent':label,'model':model,'parsed':parsed.model_dump(mode='json'),'sources':sources,'usage':{},'demo':True})
        return ProviderResult(parsed=parsed, raw=raw, sources=sources, usage={})

    async def close(self) -> None:
        return None
