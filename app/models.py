from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class SeniorityLevel(str, Enum):
    EXECUTIVE = "EXECUTIVE"
    DIRECTOR_HEAD = "DIRECTOR_HEAD"
    MANAGER_LEAD = "MANAGER_LEAD"
    SPECIALIST_IC = "SPECIALIST_IC"
    ENTRY_INTERN_STUDENT = "ENTRY_INTERN_STUDENT"
    UNKNOWN = "UNKNOWN"


class EntityResolutionItem(BaseModel):
    record_key: str
    company_raw: str
    department_raw: str | None = None
    canonical_company_name: str | None = None
    local_entity_name: str | None = None
    company_name_ko: str | None = None
    company_name_en: str | None = None
    market_scope: str | None = None
    website_domain: str | None = None
    parent_company: str | None = None
    canonical_department: str | None = None
    department_family: str | None = None
    role_family: str | None = None
    seniority_level: SeniorityLevel = SeniorityLevel.UNKNOWN
    identity_status: Literal["RESOLVED", "AMBIGUOUS", "UNKNOWN"]
    resolver_confidence: float = Field(ge=0, le=1)
    needs_web_resolution: bool = False
    ambiguity_reason: str | None = None


class EntityResolutionBatch(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    results: list[EntityResolutionItem]


class EvidenceItem(BaseModel):
    evidence_id: str
    claim: str
    url: str
    title: str
    publisher: str | None = None
    published_date: str | None = None
    source_type: str = "web"
    source_quality: Literal[
        "PRIMARY_OFFICIAL", "REGULATORY", "REPUTABLE_MEDIA",
        "RECRUITING_OR_JOB", "SECONDARY", "UNKNOWN"
    ] = "UNKNOWN"


class LocalPresence(BaseModel):
    korea_role: str | None = None
    korea_entity_name: str | None = None
    korea_employee_count: int | None = Field(default=None, ge=0)
    korea_employee_range: str | None = None
    korea_revenue: str | None = None
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = []


class CompanyScale(BaseModel):
    category: Literal["GLOBAL_ENTERPRISE", "LARGE", "MID", "SMALL", "MICRO", "UNKNOWN"]
    basis: str
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = []




class RevenueRecord(BaseModel):
    year: str
    amount_text: str
    scope: str | None = None
    source_kind: Literal["OFFICIAL", "ESTIMATE", "SECONDARY", "UNKNOWN"] = "UNKNOWN"
    evidence_ids: list[str] = []


class FundingInfo(BaseModel):
    applicable: bool = False
    cumulative_funding: str | None = None
    latest_round: str | None = None
    major_investors: list[str] = []
    note: str | None = None
    evidence_ids: list[str] = []


class BusinessLine(BaseModel):
    name: str
    description: str | None = None
    evidence_ids: list[str] = []


class AgoraOpportunity(BaseModel):
    rank: int = Field(ge=1, le=3)
    service_or_workflow: str
    recommended_product: str
    idea: str
    fit_confidence: float = Field(ge=0, le=1)
    company_evidence_ids: list[str] = []
    agora_evidence_ids: list[str] = []


class CommercialAttractiveness(BaseModel):
    level: Literal["VERY_HIGH", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]
    headline: str
    reasons: list[str] = Field(default_factory=list, max_length=5)
    evidence_ids: list[str] = []


class AgoraProductCheck(BaseModel):
    checked: bool = False
    summary: str | None = None
    official_source_urls: list[str] = []

class BusinessSignal(BaseModel):
    signal_id: str
    date: str | None = None
    topic: str
    summary: str
    korea_relevance: Literal["DIRECT_KOREA", "KOREA_RELEVANT", "GLOBAL_CONTEXT_ONLY"]
    department_tags: list[str] = []
    sales_relevance: float = Field(ge=0, le=1)
    evidence_ids: list[str] = []


class CompanyResearch(BaseModel):
    schema_version: Literal["1.1"] = "1.1"
    company_id: str
    canonical_company_name: str
    official_company_name: str | None = None
    one_line_description: str
    research_scope: str
    executive_summary: list[str] = Field(default_factory=list, min_length=3, max_length=5)
    local_presence: LocalPresence
    company_scale: CompanyScale
    listing_status: str | None = None
    listing_market: str | None = None
    ticker: str | None = None
    employee_snapshot: str | None = None
    revenue_history: list[RevenueRecord] = Field(default_factory=list, max_length=5)
    funding: FundingInfo = Field(default_factory=FundingInfo)
    main_businesses: list[BusinessLine] = Field(default_factory=list, max_length=5)
    commercial_attractiveness: CommercialAttractiveness
    business_summary: str
    rtc_opportunities: list[AgoraOpportunity] = Field(default_factory=list, max_length=3)
    ai_opportunities: list[AgoraOpportunity] = Field(default_factory=list, max_length=3)
    agora_product_check: AgoraProductCheck = Field(default_factory=AgoraProductCheck)
    recent_signals: list[BusinessSignal] = []
    evidence: list[EvidenceItem] = []
    unknowns: list[str] = []
    research_confidence: float = Field(ge=0, le=1)


class SupplementalResearch(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    lead_id: str
    summary: str
    recent_signals: list[BusinessSignal] = []
    evidence: list[EvidenceItem] = []
    confidence: float = Field(ge=0, le=1)


class Axis25(BaseModel):
    score: int = Field(ge=0, le=25)
    reason: str
    evidence_refs: list[str] = []


class Axis20(BaseModel):
    score: int = Field(ge=0, le=20)
    reason: str
    evidence_refs: list[str] = []


class Axis10(BaseModel):
    score: int = Field(ge=0, le=10)
    reason: str
    evidence_refs: list[str] = []


class Axis5(BaseModel):
    score: int = Field(ge=0, le=5)
    reason: str
    evidence_refs: list[str] = []


class ScoreAxes(BaseModel):
    account_potential: Axis25
    contact_influence: Axis20
    declared_intent: Axis20
    agora_fit: Axis20
    recent_trigger: Axis10
    evidence_quality: Axis5


class LeadScore(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    lead_id: str
    axes: ScoreAxes
    total_score: int = Field(ge=0, le=100)
    classification: Literal["QUALITY", "NORMAL", "TRASH"]
    classification_confidence: float = Field(ge=0, le=1)
    positive_signals: list[str] = []
    negative_signals: list[str] = []
    uncertainties: list[str] = []
    classification_rationale: str
    supplemental_research_recommended: bool = False
    supplemental_research_queries: list[str] = Field(default_factory=list, max_length=3)
    review_level: Literal["HIGH_TOUCH", "STANDARD", "NONE"]


class LeadScoreBatch(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    scores: list[LeadScore]


class SalesStrategy(BaseModel):
    schema_version: Literal["1.1"] = "1.1"
    lead_id: str
    outreach_mode: Literal["GROUP", "REPRESENTATIVE_FIRST", "INDIVIDUAL"]
    recipient_plan: str
    primary_angle: str
    secondary_angle: str | None = None
    customer_hypothesis: str
    why_now: str
    agora_value_proposition: str

    # Approved writer slots. The Email Writer may word these naturally, but may not
    # invent or replace their factual content. Empty lists must stay empty.
    company_context: list[str] = Field(default_factory=list, max_length=3)
    use_case_context: list[str] = Field(default_factory=list, max_length=3)
    selected_features: list[str] = Field(default_factory=list, max_length=3)
    selected_ai_points: list[str] = Field(default_factory=list, max_length=3)
    selected_value_points: list[str] = Field(default_factory=list, max_length=3)
    selected_references: list[str] = Field(default_factory=list, max_length=2)

    product_doc_ids: list[str] = Field(default_factory=list, max_length=3)
    case_doc_ids: list[str] = Field(default_factory=list, max_length=2)
    prospect_evidence_ids: list[str] = Field(default_factory=list, max_length=4)
    agora_claim_ids: list[str] = Field(default_factory=list, max_length=4)
    cta: str
    avoid_claims: list[str] = []
    email_brief: str


class EmailDraft(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    lead_id: str
    language: Literal["ko", "en"] = "ko"
    subject_primary: str
    subject_alternatives: list[str] = Field(min_length=2, max_length=3)
    greeting: str
    body: str
    closing: str
    full_email: str
    prospect_evidence_ids_used: list[str] = []
    agora_doc_ids_used: list[str] = []
    agora_claim_ids_used: list[str] = []


class ReviewIssue(BaseModel):
    type: Literal[
        "UNSUPPORTED_CLAIM", "SOURCE_MISMATCH", "OVERCLAIM", "GENERIC_COPY",
        "WEAK_PERSONALIZATION", "WRONG_TONE", "WRONG_SENIORITY_TONE",
        "POOR_CTA", "TOO_LONG", "OTHER"
    ]
    severity: Literal["MINOR", "MAJOR", "CRITICAL"]
    description: str


class ReviewDimensions(BaseModel):
    factual_grounding: int = Field(ge=0, le=25)
    account_relevance: int = Field(ge=0, le=20)
    product_fit: int = Field(ge=0, le=15)
    personalization: int = Field(ge=0, le=15)
    persuasion_clarity: int = Field(ge=0, le=10)
    tone: int = Field(ge=0, le=10)
    cta: int = Field(ge=0, le=5)


class SalesReview(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    lead_id: str
    dimensions: ReviewDimensions
    total_score: int = Field(ge=0, le=100)
    decision: Literal["PASS", "REWRITE", "HUMAN_REVIEW"]
    issues: list[ReviewIssue] = []
    unsupported_claims: list[str] = []
    revision_instructions: str | None = None
    classification_recheck_flag: bool = False
    human_review_reasons: list[str] = []


class VisitorRecord(BaseModel):
    visitor_id: str
    raw_row_number: int
    visited_at: str | None = None
    attendee_name: str | None = None
    phone: str | None = None
    email: str | None = None
    company: str | None = None
    department: str | None = None
    job_title: str | None = None
    visitor_role: str | None = None
    region: str | None = None
    industry: str | None = None
    seniority_band: str | None = None
    function: str | None = None
    product_interests: str | None = None
    industry_ai: str | None = None
    business_ai: str | None = None
    genai: str | None = None
    ai_platform: str | None = None
    event_interests: str | None = None
    visit_purpose: str | None = None
    acquisition_channel: str | None = None
    attendee_type: str | None = None
    company_size: str | None = None
    source_sheet: str | None = None
    raw: dict[str, Any] = {}


class ResolvedVisitor(VisitorRecord):
    company_id: str | None = None
    canonical_company_name: str | None = None
    canonical_department: str | None = None
    department_family: str | None = None
    role_family: str | None = None
    seniority_level: SeniorityLevel = SeniorityLevel.UNKNOWN
    entity_confidence: float = 0.0


class LeadUnit(BaseModel):
    lead_id: str
    company_id: str
    canonical_company_name: str
    canonical_department: str | None = None
    lead_unit_type: Literal["INDIVIDUAL", "GROUP"]
    member_ids: list[str]
    members: list[ResolvedVisitor]
    group_time_start: str | None = None
    group_time_end: str | None = None


class RetrievedDoc(BaseModel):
    doc_id: str
    path: str
    category: str
    market: str | None = None
    priority: str | None = None
    content: str
    score: float = 0


class RetrievalBundle(BaseModel):
    lead_id: str
    docs: list[RetrievedDoc]
    doc_ids: list[str]


class LeadRuntime(BaseModel):
    lead: LeadUnit
    research: CompanyResearch | None = None
    retrieval: RetrievalBundle | None = None
    score: LeadScore | None = None
    strategy: SalesStrategy | None = None
    draft: EmailDraft | None = None
    review: SalesReview | None = None
    human_review_status: Literal["REQUIRED", "PENDING", "APPROVED", "REJECTED", "NOT_REQUIRED"] = "PENDING"
    human_review_note: str | None = None
