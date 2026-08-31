# v1.2 Changelog

## 1. API Live Transcript UI
- trace가 올 때 전체 DOM을 재렌더링하지 않고 append-only 방식으로 변경.
- 화면에는 최근 250개 trace만 유지해 브라우저 성능 저하 방지.
- transcript 영역 고정 viewport + stable scrollbar + overscroll containment 적용.
- `자동 따라가기` on/off 추가.
- 긴 Structured Output / prompt는 각 card 내부 scroll로 분리.
- 화면의 `지우기`는 UI만 비우고 서버 기록은 유지.

## 2. Durable API transcript
각 run에 다음 두 파일을 생성:
- `09_api_trace/api_trace.json` — 전체 JSON array
- `09_api_trace/api_trace.jsonl` — append-only NDJSON

웹에서도 `API Transcript JSON` 다운로드 가능.

## 3. Browser session persistence
localStorage에 저장:
- source preset / run scope
- concurrency / max lead
- sender 정보
- quick/demo setting
- email style reference
- selected row IDs
- preview table cache
- current backend job ID
- current navigation/filter state

새로고침 후 backend job이 살아 있으면:
- job progress
- current leads
- API trace
- result/review 화면
을 다시 불러오고 실행 중이면 SSE에 재연결.

API Key는 기본적으로 저장하지 않음. 사용자가 `이 브라우저에 Key 저장`을 켠 경우에만 localStorage 저장.

`브라우저 캐시 지우기` 버튼으로 위 상태 전체 삭제 가능.

## 4. Dataset preview + row-selected execution
업로드 직후 API를 돌리지 않음.

1. workbook inspect
2. preset 선택
3. parsed CSV-like table preview
4. 필요한 row checkbox 선택
5. 선택 row만 pipeline 실행

Preset:
- B2B 우선
- B2B core
- B2C
- Main
- Auto
- workbook에 실제 존재하는 원본 sheet들

선택 row 모드에서는 `max_leads`로 다시 임의 truncate하지 않음.

## 5. Email style reference
- 과거 발송메일을 textarea에 붙여넣거나 `.txt/.md/.csv/.eml` 파일에서 불러오기.
- Writer는 factual content를 복사하지 않고:
  - 격식
  - 문장/문단 길이
  - 전체 길이
  - 인사/마무리
  - 확인 요청 / CTA 강도
  만 학습하도록 prompt 강화.
- Reviewer도 style adherence를 Tone/Personalization/Clarity에 반영.

## 6. Dynamic Agora cases
- `knowledge` 폴더의 새 `.md/.txt`를 runtime에 자동 discovery.
- `document_index.csv` 수동 갱신 없이 frontmatter를 읽어 retrieval candidate로 편입.
- 웹에서 실행별 custom case `.md/.txt` 여러 개 업로드 가능.
- 신규 doc_id 자체가 아니라 실제 source/factuality/case_status/relevance를 기준으로 Scorer/Strategist/Writer/Reviewer가 판단하도록 prompt 수정.
