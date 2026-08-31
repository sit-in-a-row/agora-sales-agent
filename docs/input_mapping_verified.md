# 첨부 workbook 기준 입력 매핑 검증

검증 파일: `AI Summit Seoul & Expo 2026_visitors_fixed(1).xlsx`

## 실제 시트 구조

- `Main (701명)` — 701 data rows
- `Not Important (68명)` — formula spill cached value 없음
- `Impt_B2B (51 + 10 명)` — cached data 일부 존재
- `Impt_B2C (541명)` — formula spill cached value 없음
- `분류 외 (33명)` — formula spill cached value 없음
- `분류 기준` — 분류 기준 373 rows

웹앱의 `Auto`는 `Impt_B2C` cached row가 비어 있으므로 `Main + 분류 기준`의 B2C 회사 목록으로 **541건을 복원**한다.

## 확인한 logical fields

| Logical | Actual header |
|---|---|
| visited_at | 방문시간 |
| attendee_name | 성명 |
| phone | 휴대폰 |
| email | 이메일 |
| company | 회사명/소속 |
| department | 부서 |
| job_title | 직함 |
| visitor_role | 개인 구분 |
| region | 지역 |
| industry | 업종분류 |
| seniority_band | 직위 |
| function | 담당부서 |
| product_interests | 관심품목 |
| industry_ai | 산업별 AI 솔루션 |
| business_ai | AI 비즈니스 솔루션 |
| genai | 생성형 AI & 콘텐츠 혁신 |
| ai_platform | AI 플랫폼 & 인프라 |
| event_interests | 관심 부대행사 |
| visit_purpose | 참관목적 |
| acquisition_channel | 전시회 주요 인지경로 |
| attendee_type | 등록구분 |

회사명 자체의 semantic normalization은 이 B2C 복원 단계가 아니라 그 뒤 Entity Resolver가 수행한다.
