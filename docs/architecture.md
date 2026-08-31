# Architecture

## High-level

```text
CSV
 │
 ▼
[0] Ingest & Validate                         deterministic
 │
 ▼
[1] Entity Resolution                        LLM
 │  └─ ambiguous only → web-assisted resolve LLM + Web
 ▼
[2] Lead Unit Grouping                       deterministic
 │
 ▼
[3] Company Research                         LLM + Web
 │  └─ one base research per company
 ▼
[4] Agora Context Retrieval                  deterministic candidate ranking
 │
 ▼
[5] Lead Scoring                             LLM
 │
 ├─ Trash  ──────────────────────────────► STOP / export
 │
 ├─ Normal
 │
 └─ Quality
 │      └─ low confidence / missing trigger
 │          → optional supplemental research (max 1)
 ▼
[6] Sales Strategy                           LLM
 ▼
[7] Email Draft                              LLM
 ▼
[8] Sales Review                             LLM
 │
 ├─ PASS
 ├─ REWRITE → Writer once → Reviewer once
 └─ HUMAN_REVIEW
 ▼
[9] Final Export                             deterministic
```

## Why this granularity

### 합친 것
- 회사 규모 조사 + 최근 관심동향 조사 → `Account Researcher`
- 영업부장 + 담당임원 중복 검수 → `Sales Reviewer` 1개

### Agent로 만들지 않은 것
- grouping
- cache
- retrieval index
- thresholds/routing
- final export

이들은 자연어 reasoning보다 reproducibility가 중요함.

## State boundary

각 Agent는 자연어로 다음 Agent에게 “대화”하지 않는다.

모든 handoff는:
- Structured Output JSON
- stable evidence IDs
- stable document IDs

로만 이루어진다.

## No autonomous free-running loop

- 각 stage는 orchestrator가 명시적으로 실행
- 재시도 한도 존재
- rewrite는 최대 1회
- research supplement도 최대 1회
- 무한 agent loop 금지
