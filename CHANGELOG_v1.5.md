# v1.5

## 1. Deterministic email generation

- 사용자가 제공한 `Agora 영업 메일 Deterministic Template Guide`를 기본 메일 정책으로 채택.
- Email Draft는 더 이상 LLM 자유작성으로 생성하지 않음.
- Python deterministic renderer가 fixed block을 그대로 유지하고 predefined slot만 치환.
- 기본 자동 실행에서는 `company_name`, `recipient_name`만 source data에서 채움.
- company context / use case / feature / AI / reference / value point는 외부 입력이 없으면 Optional Block 전체 삭제.
- 생성 후 상세 모달 textarea에서 사람이 직접 수정하고 저장 가능.
- `250+ 데이터센터`, CTA, 발신자 signature 등은 제공된 deterministic template 문구를 그대로 사용.

## 2. Quality / Normal / Trash 모두 메일 생성

- 기존 v1.4는 Trash를 Strategy/Draft 대상에서 제외했음.
- v1.5는 score가 생성된 **모든 lead**를 Strategy 및 Draft 단계로 보냄.
- 따라서 Quality / Normal / Trash 모두 `subject + email_body`가 생성됨.
- Quality는 기존 정책대로 무조건 사람 최종 검수.
- Full review mode에서 Reviewer가 REWRITE를 요청하더라도 fixed template을 AI가 다시 쓰지 않으며 사람 검수 대상으로 전환.

## 3. 새 `Impt (600명)` workbook 구조 지원

업로드된 `Final_AI_Summit_Seoul&Expo_2026 (1).xlsx` 기준:

- `Impt (600명)`
- `기업 종류` 컬럼 인식
- 대기업: 204
- 중견기업: 32
- 스타트업: 360
- 미분류: 4

## 4. 신규 Preset

- Main
- Impt (all)
- Impt (대기업)
- Impt (중견기업)
- Impt (스타트업)
- Impt (대기업 + 중견기업)
- Impt (대기업 + 스타트업)
- Impt (중견기업 + 스타트업)

`Impt (all)`은 미분류 포함 전체를 사용.
규모별 preset은 `기업 종류` 값이 선택 카테고리에 해당하는 row만 사용.

## 5. Preview UI

- 미리보기 table에 `기업 종류` 컬럼 추가.
- workbook 검사 후 preset label에 현재 row count 자동 표시.
- 회사 규모도 table 검색 대상에 포함.

## 6. Version / cache

- Backend `1.5.0`
- static cache bust `?v=1.5.0`
- localStorage namespace `agoraSales.v1.5.*`
