# Agora Corpus Retrieval Policy

Vector DB 없음.

## Inputs
- lead industry
- department family
- attendee interest tags
- company research signal topics
- classification

## Candidate ranking — deterministic

`document_index.csv`를 이용.

제안 weight:
- exact tag overlap: +3
- market KR match: +4
- category `case` + Korea: +3
- priority critical: +2
- priority high: +1
- quick_retrieval_map explicit recommendation: +5

## Always include
For Normal / Quality:
- CLAIMS_GUARDRAILS
- COMPANY_PROFILE or CURRENT_STRATEGY_2026 중 최소 1

For Korea prospect:
- KOREA_BUSINESS_CONTEXT

## Max context
Scorer:
- company docs 2
- product docs 2
- case docs 2
- guardrail 1

Strategist:
- company docs 2
- product docs 3
- cases 2
- sales policy 2
- guardrail 1

## Semantic flexibility
Deterministic retrieval은 “최종 판단”이 아니라 candidate selection.

Lead Scorer / Strategist가 문서 내용을 읽고 실제 fit을 의미론적으로 판단.

## Future product data
사용자가 product knowledge를 추가할 때:
각 `.md`에 최소 frontmatter:
- doc_id
- category
- market
- tags
- source_ids
- retrieval_priority

만 유지하면 동일 retrieval engine에 연결 가능.
