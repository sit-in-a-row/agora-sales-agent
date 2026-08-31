# Agora Sales Agent Web App v1.6

AI Summit Seoul & EXPO 2026 방문자 데이터를 대상으로 회사 리서치, lead scoring, deterministic follow-up email, Human Review, Notion 영속 저장을 제공하는 로컬 FastAPI 웹앱이다.

## v1.6 핵심

### 1. Research와 Email Generation 완전 분리

Account Researcher는 회사 규모, 매출, 임직원, 상장/투자, 주력 사업, RTC/AI 적용 가능성 등을 적극적으로 조사한다. 그러나 이 결과는 영업담당자의 참고 자료이며 **메일 본문에 자동 삽입되지 않는다.**

메일은 `app/pipeline/email_template.py`의 deterministic template renderer가 생성한다.

자동 치환되는 값은 원칙적으로 다음뿐이다.

- 회사명
- 담당자명
- 원본 데이터에서 확인된 직책

회사별 실제 영업 맥락이나 use case는 결과 상세창의 메일 textarea에서 사람이 직접 추가/수정한다.

최종 가이드 원문은 다음 파일에 있다.

```text
docs/email_guides/agora_deterministic_template_guide.md
```

### 2. Fixed mail policy

기본 메일에는 다음 정책이 적용된다.

- `아고라(Agora Inc., NASDAQ: API)의 한국 매니저 박세빈` 직함 명시
- AI Summit 부스 방문 감사 유지
- Agora RTC / API / SDK / 250+ 데이터센터 소개 유지
- Conversational AI 소개 유지
- 회사 리서치 자동 삽입 금지
- 구매팀/조달 담당 여부를 직접 묻는 qualification 문구 금지
- CTA는 전화 또는 직접 방문 소개 중심
- `편하신 시간을 알려주시면 일정에 맞춰 찾아뵙고 인사드리겠습니다.` 방향 유지
- `감사합니다` 중복 금지
- 기본 서명: `박세빈 / Sales Manager | Agora 드림`

Quality / Normal / Trash 모두 메일을 생성한다.

### 3. Notion 영업 DB 연동

v1.6은 생성된 회사 리서치와 메일을 Notion에 저장하고 다음 실행에서 재사용할 수 있다.

기본 DB URL은 UI에 미리 입력되어 있다.

```text
https://app.notion.com/p/3cdcd049963380f794a8faea1bedcab5?v=3cdcd04996338020a2dc000cfd5ee330
```

현재 앱이 사용하는 주요 DB property:

```text
이름
회사명
Company Key
Lead Key
담당자
이메일
직함
기업 종류
분류
Lead Score
영업가치
최근 매출
임직원
상장
투자
메일 제목
저장 상태
Last Synced
```

긴 Company Research와 Email Draft, 앱 재사용용 state는 각 database row의 Notion page 본문에 저장한다.

#### 상태 의미

```text
메일 저장됨
= 동일 회사 + 동일 담당자(이메일 우선, 없으면 이름)의 기존 결과가 존재
→ OpenAI 재생성 없이 Notion에서 바로 로드

회사 조사 있음
= 회사는 기존에 조사했지만 현재 담당자의 저장 메일은 없음
→ 기존 Company Research를 재사용하고 현재 담당자용 scoring/draft 생성

미생성
= 저장된 회사/lead 없음
→ 새 Research + scoring + draft 생성
```

동일 회사의 다른 담당자에게 이전 담당자 메일을 재사용하지 않는 것이 중요하다.

### 4. Notion API Key 설정

로컬 앱은 ChatGPT의 Notion 연결과 별개로 **사용자의 Notion Integration API Key**를 사용한다.

1. Notion Integration을 생성하고 API Key를 발급한다.
2. 위 Sales DB를 해당 Integration에 Share/Connect한다.
3. v1.6 웹의 `Notion API Key` 칸에 Key를 입력한다.
4. `연결 테스트`를 누른다.
5. `생성 결과 자동 저장`을 켜두면 새 결과가 자동 upsert 된다.
6. `기존 회사 Research 재사용`을 켜두면 동일 회사의 웹 리서치를 반복하지 않는다.

Notion Key는 서버의 run 파일이나 결과 artifact에 기록하지 않는다. `이 브라우저에 Key 저장`을 직접 체크한 경우에만 browser `localStorage`에 저장한다.

### 5. 메일 수정 → Notion 동시 업데이트

결과 상세창에서 제목/메일 본문을 직접 수정하고 `수정 내용 저장`을 누르면:

- 현재 로컬 run 결과 수정
- CSV/XLSX/JSON/Artifacts 재생성
- Notion 연결 시 동일 row도 `MANUAL_EDITED` 상태로 업데이트

Notion에서 불러온 기존 메일 역시 같은 textarea에서 수정한 뒤 Notion에 다시 저장할 수 있다.

### 6. 새로고침 복구

브라우저 localStorage에는 다음 UI 상태를 보존한다.

- preset / 실행범위 / max lead / concurrency
- 선택 row
- preview cache
- current backend job id
- filter / section
- Notion DB URL / 옵션
- OpenAI/Notion Key는 각각 `이 브라우저에 Key 저장`을 체크한 경우만

원본 Excel 파일 자체는 브라우저 보안상 새로고침 뒤 자동 복구할 수 없다. 다만 선택 대상이 모두 `메일 저장됨` 상태라면 원본 파일 없이 Notion 결과만 다시 불러올 수 있다.

## Preset

새 Final workbook의 `Impt` 시트 `기업 종류` 기준으로 다음 preset을 지원한다.

```text
Impt (all)
Impt (대기업)
Impt (중견기업)
Impt (스타트업)
Impt (대기업 + 중견기업)
Impt (대기업 + 스타트업)
Impt (중견기업 + 스타트업)
Main
원본 sheet 직접 선택
```

## 실행

macOS / Linux:

```bash
cd agora_sales_agent_webapp_v1_6
bash setup_and_run.sh
```

또는 실행권한이 유지된 경우:

```bash
./setup_and_run.sh
```

처음 설치 후:

```bash
./run.sh
```

서버는 기본적으로 `http://127.0.0.1:8000`을 사용한다. 8000 포트에 이전 Agora 서버가 남아 있으면 8001~8010 중 빈 포트를 자동 선택한다.

화면 우측 상단에 다음이 보여야 한다.

```text
Backend v1.6.0 연결됨
```

## 권장 첫 실행

```text
1. OpenAI API Key 입력
2. Notion API Key 입력
3. Notion 연결 테스트
4. Final workbook 업로드
5. Impt (대기업) 등 preset 선택
6. 2~5개 row 체크
7. 현재 표와 Notion 대조
8. 선택 Row 분석 시작
9. 결과 상세창에서 Research 확인
10. 메일 textarea에 필요한 회사 맥락을 사람이 직접 추가
11. 수정 내용 저장 → Notion까지 동기화 확인
```

## Notion 저장 실패 시

Notion 동기화 실패는 전체 pipeline을 실패시키지 않는다. 로컬 결과는 그대로 유지하고 UI/log에 Notion 저장 실패 이유를 표시한다.

주로 확인할 항목:

- Notion API Key가 올바른지
- Database를 Integration에 Share했는지
- Database URL이 올바른지
- 네트워크 연결이 가능한지

## 주요 디렉터리

```text
app/
  main.py
  notion_store.py
  pipeline/
    orchestrator.py
    email_template.py
    workbook.py
  static/
    index.html
    app.js
    styles.css

docs/
  email_guides/
    agora_deterministic_template_guide.md

runs/{job_id}/
  03_research/
  07_drafts/
  09_api_trace/
  10_notion_sync/
  output/
```

## 보안 메모

- OpenAI API Key와 Notion API Key를 코드에 하드코딩하지 않는다.
- 서버 run artifact에는 두 Key를 저장하지 않는다.
- browser 저장은 사용자가 각 `Key 저장` checkbox를 명시적으로 켠 경우에만 사용한다.
- Notion에는 회사/담당자/이메일과 리서치/메일이 저장될 수 있으므로 DB 접근 권한은 영업 데이터 기준으로 관리한다.
