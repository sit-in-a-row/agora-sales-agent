# Agora Sales Retrieval Dataset v1

Agora, Inc. (NASDAQ: API)의 영업용 Agentic Workflow를 위한 Markdown retrieval corpus.

목적:
- Agora의 회사/제품/최신 전략을 정확히 설명
- 한국 내 실제 business signal과 고객 사례를 우선 활용
- 산업/직무별로 적절한 사례와 제품을 retrieval
- Writer가 사실을 만들지 않도록 sales-safe claim과 guardrail 제공

## SEC filing 주의

Agora, Inc.는 foreign private issuer이므로 10-K/10-Q가 아니라:
- Annual: Form 20-F
- Quarterly/current: Form 6-K 및 earnings materials

를 중심으로 본다.

본 v1은 FY2025 Form 20-F, 2026 Q1/Q2 최신 실적자료를 반영했다.

## Retrieval 순서

1. prospect의 industry / department / visitor interest / Korea-market signal 확인
2. `01_company`에서 1~2개 문서
3. `03_products`에서 relevant product 1~2개
4. 한국 prospect면 `04_cases/korea` 우선
5. 필요한 경우 동일 산업 global case 1~2개
6. `01_company/claims_and_guardrails.md` 항상 포함
7. customer KPI는 반드시 해당 customer case로 귀속

## 구조

```text
00_meta/       source registry, index, retrieval rules
01_company/    profile, 2026 strategy, Korea context, guardrails
02_filings/    2025 20-F, 2026 Q1/Q2 summaries
03_products/   product/capability docs
04_cases/      Korea + global customer/partnership cases
05_sales/      claim library, mapping, writer contract
06_examples/   retrieval examples
```
