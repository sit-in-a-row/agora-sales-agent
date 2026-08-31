# Changelog v1.6

## Deterministic mail v2

- 최종 `Agora B2B Follow-up Email Deterministic Guide` 반영.
- Account Research 결과의 email 자동 삽입 제거.
- sender 본문 직함을 `한국 매니저 박세빈`으로 고정.
- AI 소개, sales bridge, 전화/방문 CTA, 간결한 signature를 최신 피드백에 맞게 변경.
- 수신 회사별 맥락은 사람이 결과 textarea에서 직접 수정하도록 유지.
- 구매팀/조달 담당 범위를 묻는 문구를 deterministic template에서 제거.
- Quality / Normal / Trash 모두 draft 생성 유지.

## Notion persistence

- Notion API Key / Database URL UI 추가.
- Key 브라우저 저장은 opt-in.
- Notion 연결 테스트 / 현재 preview 대조 추가.
- preview status: `메일 저장됨 / 회사 조사 있음 / 미생성`.
- 동일 Lead 저장본은 Notion에서 즉시 load하고 OpenAI 재생성 생략.
- 동일 회사의 다른 담당자는 기존 Company Research만 재사용.
- 신규 run 완료 시 Research / Score / Draft를 Notion page로 자동 upsert.
- 메일 textarea 수정 저장 시 local exports와 Notion을 함께 업데이트.
- Notion sync failure는 local pipeline을 중단시키지 않도록 best-effort 처리.
- Notion API key는 run artifact/job state에 기록하지 않음.

## Frontend/session

- Notion panel과 status badge 추가.
- exact Notion 저장본만 선택한 경우 Excel/OpenAI Key 없이 재조회 가능.
- v1.5 UI 설정을 v1.6으로 1회 migration.
- local cache clear 대상에 optional stored Notion key 포함.
- Notion-loaded Quality card의 동작하지 않는 local review 버튼 대신 상세/Notion 링크 표시.

## Tests

- Python compile.
- frontend JavaScript syntax check.
- workbook + DEMO pipeline smoke test.
- deterministic drafts for all processed classifications check.
- in-memory Notion create/update/load/exact/company/new matching test.
