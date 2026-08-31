# Reviewer Rubric v1

| Dimension | Max |
|---|---:|
| Factual grounding | 25 |
| Account relevance | 20 |
| Product fit | 15 |
| Personalization | 15 |
| Persuasion / clarity | 10 |
| Tone | 10 |
| CTA | 5 |

## Proposed thresholds

Quality lead:
- PASS >= 88
- 82–87: rewrite
- <82: rewrite or human review depending issues

Normal lead:
- PASS >= 82
- 75–81: rewrite
- <75: human review if rewrite fails

## Critical overrides
Any critical unsupported claim:
- PASS 불가

After one rewrite:
- remaining MAJOR/CRITICAL factual issue → HUMAN_REVIEW

## Reviewer is not second scorer
Reviewer는 lead score를 다시 산정하지 않음.

다만:
`classification_recheck_flag=true`
를 낼 수 있음.

예:
Scorer는 Quality인데 research와 draft가 사실상 fit이 없음.
이 경우 사람이 routing을 확인.
