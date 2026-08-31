# Evidence Ledger

Researcher의 factual output은 모두 evidence ID로 관리.

예:
```json
{
  "evidence_id": "EV_LV_003",
  "claim": "한국에서 ... 프로젝트를 발표",
  "url": "...",
  "title": "...",
  "publisher": "...",
  "published_date": "2026-05-01",
  "source_quality": "PRIMARY_OFFICIAL"
}
```

## Web tool source validation

Responses API call 시:
`include=["web_search_call.action.sources"]`

로 source list를 보존.

Orchestrator validator:
- Researcher가 출력한 모든 `evidence.url`
- 실제 web-search returned sources

를 대조.

source list에 없는 URL:
- evidence invalid
- targeted retry 1회
- 계속 실패 → 해당 evidence 제거 + confidence 감소

## Downstream

Scorer:
- evidence IDs만 참조

Strategist:
- evidence IDs 선택

Writer:
- 선택된 evidence 밖의 prospect factual claim 금지

Reviewer:
- 메일 factual claim과 evidence refs 비교
