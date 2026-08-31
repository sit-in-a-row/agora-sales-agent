# Lead Scoring Rubric v1

## Proposed weighting

| Axis | Max | 핵심 질문 |
|---|---:|---|
| Account Potential | 25 | 한국에서 실제 영업 가치가 큰 account인가? |
| Contact Influence | 20 | 이 방문자/그룹이 도입·평가·vendor 선택에 영향력이 있는가? |
| Declared Intent | 20 | 행사 데이터에서 구체적 구매/도입 관심이 보이는가? |
| Agora Product Fit | 20 | Agora의 실제 capability와 구체적으로 맞는가? |
| Recent Business Trigger | 10 | 지금 연락할 이유가 되는 최근 signal이 있는가? |
| Evidence Quality | 5 | 판단 근거가 얼마나 검증·현지화돼 있는가? |

## 1. Account Potential 0–25

High:
- substantive Korea operation
- enterprise / high-value mid-market
- product/service와 real-time/AI interaction relevance
- budget/scale potential

Medium:
- 규모는 작지만 성장성·도입 가능성이 있음
- 특정 use case가 매우 구체적

Low:
- 실체/사업규모 불명
- B2B 구매 가능성이 낮음

`대기업=25` 같은 lookup 금지.

## 2. Contact Influence 0–20

High:
- executive / director / head
- buyer / procurement / platform owner
- vendor evaluation influence

Medium:
- manager / lead / senior specialist
- 관련 digital/IT/operation team
- practical evaluator / internal champion 가능

Low:
- unrelated individual contributor
- student / intern / job seeker
- company affiliation 불명확

직함은 context와 함께 해석.

## 3. Declared Intent 0–20

Strong:
- buyer
- Agora-related category를 여러 개 명시
- CRM/customer service/sales/AI platform 등 구체적 use case
- 같은 팀 여러 명의 근접 방문

Weak:
- 일반 관람
- 업계동향만
- broad “AI 관심” 외 구체성 없음

## 4. Agora Product Fit 0–20

High:
- 1~2개의 명확한 pain/workflow
- relevant Agora product
- 가까운 actual case

Low:
- AI와 관계는 있으나 Agora real-time interaction layer와 직접 관계 없음

## 5. Recent Trigger 0–10

High:
- 최근 12~18개월 Korea initiative / hiring / partnership / launch
- role/function과 직접 관련

Low:
- parent company global trend뿐
- 오래된 일반 기사

## 6. Evidence Quality 0–5

5:
- official/local/recent sources
- company size와 recent signal이 모두 well-supported

0–2:
- local evidence 거의 없음
- ambiguous entity / weak secondary sources

## Proposed classification

- QUALITY: 75–100
- NORMAL: 45–74
- TRASH: 0–44

### Confidence overlay
Quality 후보라도 classification confidence < 0.70이면:
- `review_level=HIGH_TOUCH`
- supplemental research 고려
- 자동 확정으로 취급하지 않음

## Score consistency validator

Orchestrator가:
`sum(axis scores) == total_score`
검증.

classification threshold와 output이 불일치하면 1회 re-score 또는 manual review.
