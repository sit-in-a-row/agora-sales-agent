# v1.4

## Account Research 강화

- Executive Summary 3~5 bullets
- 공식 회사명 / 한 줄 소개
- 최근 매출 history + OFFICIAL/ESTIMATE 구분
- 상장 여부 / 거래소 / ticker
- 한국 임직원 snapshot
- 스타트업/비상장 기업 투자유치 정보
- 주력 사업 3~5개
- `Commercial Attractiveness` VERY_HIGH/HIGH/MEDIUM/LOW/UNKNOWN
- 최근 Korea business signals
- Agora RTC 적용 가능성 최대 3개
- Agora AI 적용 가능성 최대 3개
- 매 research마다 Agora 공식 홈페이지/Documentation의 현재 제품 확인 지시
- source ledger 검증 범위를 revenue/funding/business/opportunity까지 확대

## UI

- 결과 table에 `사업가치` column 추가
- Lead 상세창 Account Research를 구조화 card UI로 변경
- 매출 / 임직원 / 상장 / 투자 정보를 한눈에 표시
- RTC / AI 적용 가능성을 나란히 표시

## Email Draft 직접 수정

- 상세창 Email Draft를 `<textarea>` + subject `<input>`으로 변경
- 사용자가 기업 맥락/유즈케이스/문구를 직접 수정 가능
- `수정 내용 저장` API 추가
- 수동 수정본을 `07_drafts/manual_edits.json`, `*.manual.md`, `*.manual.json`에 저장
- 최종 CSV/XLSX/JSON/artifacts.zip에 즉시 반영
- 자동 생성 초안 원본은 별도 파일로 보존
- AI Reviewer가 이미 실행된 후 수정하면 UI에 review-outdated 상태를 표시할 수 있도록 flag 저장
