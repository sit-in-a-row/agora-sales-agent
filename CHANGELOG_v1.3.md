# v1.3

## 1. Mandatory Agora email writing guide
- `docs/email_guides/agora_sales_email_style_guide.md` 내장.
- Email Writer system prompt 호출 시 guide 전체를 자동 결합.
- guide의 tone/structure/event follow-up/CTA/slot discipline을 mandatory rule로 적용.
- guide 안의 factual example/숫자는 독립 evidence로 취급하지 않음.

## 2. Strategist → Writer approved slots
SalesStrategy schema v1.1에 다음 필드 추가:
- `company_context`
- `use_case_context`
- `selected_features`
- `selected_ai_points`
- `selected_value_points`
- `selected_references`

Writer는 이 슬롯 밖에서 구체 유즈케이스/제품/AI 포인트/reference를 새로 선택하지 않도록 변경.

## 3. Frontend `Cannot set properties of null` 방어
- inspect / preview / launch / progress text update를 null-safe helper로 변경.
- start button의 `firstChild.textContent` 접근을 제거하고 명시적 `#startBtnLabel` 사용.
- frontend runtime error diagnostic 추가.

## 4. Stale frontend cache 방지
- `/` 및 `/static/*`에 `Cache-Control: no-store` 적용.
- CSS/JS URL에 `?v=1.3.0` cache-busting.
- health badge에 Backend v1.3.0 표시.

## 5. 이전 서버 충돌 방지
- 8000 port가 이미 사용 중이면 8001~8010 중 빈 port를 자동 선택.
- 예전 Agora 서버가 8000에서 살아 있어 구버전 UI가 열리는 문제 방지.
- 실제 실행 URL을 terminal에 명확히 출력하고 해당 URL을 browser로 open.

## 6. macOS 실행권한
- `setup_and_run.sh`, `run.sh` executable bit 포함.
- 권한이 풀리는 환경에서도 `bash setup_and_run.sh`로 실행 가능.
