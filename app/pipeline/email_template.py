from __future__ import annotations

from dataclasses import dataclass

from app.models import EmailDraft, LeadUnit


DEFAULT_SENDER_NAME = "박세빈"
DEFAULT_SENDER_ROLE_KR = "한국 매니저"
DEFAULT_SIGNATURE_ROLE = "Sales Manager | Agora"


@dataclass(slots=True)
class TemplateSlots:
    company_name: str
    recipient_name: str = ""
    recipient_title: str = ""
    human_company_context: str = ""
    sender_name: str = DEFAULT_SENDER_NAME
    sender_role_kr: str = DEFAULT_SENDER_ROLE_KR


def _clean(value: str | None) -> str:
    return " ".join(str(value or "").split()).strip()


def slots_from_lead(
    lead: LeadUnit,
    *,
    sender_name: str = "",
    sender_title: str = "",
    human_company_context: str = "",
) -> TemplateSlots:
    """Build only verified deterministic slots from source data.

    v1.6 deliberately does NOT transfer Account Research, strategy, inferred use cases,
    product recommendations, references, or procurement assumptions into the email.
    Company-specific context can only come from explicit human input/editing.
    """
    company = _clean(lead.canonical_company_name) or "귀사"
    recipient = ""
    recipient_title = ""
    if lead.members:
        recipient = _clean(lead.members[0].attendee_name)
        recipient_title = _clean(lead.members[0].job_title)
    return TemplateSlots(
        company_name=company,
        recipient_name=recipient,
        recipient_title=recipient_title,
        human_company_context=_clean(human_company_context),
        sender_name=_clean(sender_name) or DEFAULT_SENDER_NAME,
        sender_role_kr=_clean(sender_title) or DEFAULT_SENDER_ROLE_KR,
    )


def _recipient_label(name: str, title: str) -> tuple[str, str]:
    if name and title:
        label = f"{name} {title}님"
        return f"{label}께,", f"{label} 안녕하세요!"
    if name:
        label = f"{name} 담당자님"
        return f"{label}께,", f"{label} 안녕하세요!"
    return "담당자님께,", "담당자님 안녕하세요!"


def render_deterministic_email(lead: LeadUnit, slots: TemplateSlots) -> EmailDraft:
    company = _clean(slots.company_name) or "귀사"
    name = _clean(slots.recipient_name)
    title = _clean(slots.recipient_title)
    to_line, hello_line = _recipient_label(name, title)

    subject_primary = f"실시간 소통 플랫폼(CPaaS), Agora에서 인사 드립니다. ({company})"
    subject_event = f"[AI Summit Seoul & EXPO 2026] Agora에서 인사 드립니다. ({company})"

    greeting = f"{to_line}\n\n{hello_line}"
    blocks: list[str] = [greeting]

    blocks.append(
        "지난 AI Summit Seoul & EXPO 2026 아고라 부스에 방문해주셔서 감사합니다.\n\n"
        f"저는 아고라(Agora Inc., NASDAQ: API)의 {slots.sender_role_kr} {slots.sender_name}입니다.\n\n"
        "당시 짧게 소개드렸던 저희 회사와 솔루션을 다시 한번 소개드리고 싶어 연락드립니다."
    )

    blocks.append(
        "아고라는 전 세계 실시간 소통(Real-Time Communication) 기술을 제공하는 기업으로, "
        "고객사가 별도의 실시간 통신 인프라를 직접 구축하지 않아도 영상 및 음성 통화, "
        "텍스트 메시징, 라이브 스트리밍 등 실시간 소통 기능을 애플리케이션에 손쉽게 "
        "내장할 수 있도록 API와 SDK 형태로 제공합니다.\n\n"
        "또한 세계 전역 250개 이상의 데이터센터를 기반으로 글로벌 네트워크를 운영하며, "
        "전 세계 다양한 지역에서 안정적인 초저지연 실시간 통신 환경을 지원합니다."
    )

    blocks.append(
        "지난해부터 아고라는 실시간 대화형 AI(Conversational AI) 기술을 기반으로 "
        "실시간 AI 통번역, AICC, AIoT Device Kit 등 다양한 AI 솔루션을 개발 및 공급하고 있습니다."
    )

    # Only explicit human-authored context may enter this block.
    if _clean(slots.human_company_context):
        blocks.append(_clean(slots.human_company_context))

    blocks.append(
        "아고라는 글로벌 실시간 통신 인프라와 더불어 긴밀한 기술지원을 제공하고 있어, "
        "향후 관련 실시간 소통 또는 AI 기능을 검토하실 기회가 있다면 아고라 솔루션도 "
        "함께 살펴봐주시면 감사하겠습니다."
    )

    blocks.append(
        "전화로 간단히 말씀드리거나 직접 사무실로 방문해 아고라의 솔루션과 다양한 적용 사례를 "
        "소개드릴 기회가 있으면 좋겠습니다.\n\n"
        "편하신 시간을 알려주시면 일정에 맞춰 찾아뵙고 인사드리겠습니다.\n\n"
        "궁금하신 점이 있으시면 언제든 편하게 연락 주시기 바랍니다.\n\n"
        "감사합니다."
    )

    signature = f"{slots.sender_name}\n{DEFAULT_SIGNATURE_ROLE} 드림"
    blocks.append(signature)

    full_email = "\n\n".join(blocks).strip()
    body = "\n\n".join(blocks[1:-1]).strip()
    closing = "\n\n".join(blocks[-2:]).strip()

    return EmailDraft(
        lead_id=lead.lead_id,
        subject_primary=subject_primary,
        subject_alternatives=[subject_event, subject_primary],
        greeting=greeting,
        body=body,
        closing=closing,
        full_email=full_email,
        prospect_evidence_ids_used=[],
        agora_doc_ids_used=[],
        agora_claim_ids_used=[],
    )
