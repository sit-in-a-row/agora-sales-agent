---
doc_id: META_RETRIEVAL_CONVENTIONS
category: meta
market: global
retrieval_priority: critical
factuality: policy
source_ids: []
tags: []
last_verified: 2026-08-28
---

# Retrieval conventions

## Evidence hierarchy
1. SEC filing
2. Agora Investor Relations
3. Agora official product/security pages
4. Agora Korea official release
5. Agora official customer case
6. corpus sales synthesis

## Minimum context
- company docs: max 2
- filing: max 1
- products: max 2
- Korea cases: max 2
- global cases: max 2
- guardrail: always 1

## Fact labels
- verified_fact
- customer_reported_outcome
- sales_safe_synthesis
- hypothesis

## Korea-first
한국 prospect는 한국 deployment/partnership → 같은 산업 global case → generic capability 순으로 evidence를 선택.

## Prohibited
- source 없는 ROI
- 다른 고객 KPI를 prospect 예상치로 단정
- MOU/pilot을 상용 성과로 변환
- future target을 current capability로 표현
- 근거 없는 절대 비교
