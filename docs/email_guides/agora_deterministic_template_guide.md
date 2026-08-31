# Agora B2B Follow-up Email Deterministic Guide

## 1. 목적

본 문서는 **AI Summit Seoul & EXPO 2026 아고라 부스 방문자에게 발송하는 후속 영업 메일**의 최종 작성 기준을 정의한다.

핵심 원칙은 다음과 같다.

> **Research Agent는 회사에 대해 충분히 조사한다.**  
> **Email Writer는 그 리서치 내용을 자동으로 메일에 넣지 않는다.**  
> **메일은 고정 템플릿을 기반으로 작성하고, 회사별 구체 맥락은 사람이 직접 입력한다.**

즉 시스템은 다음 구조를 따른다.

```text
Account Research
    ↓
영업담당자가 회사 정보 / 영업가치 / 적용 가능성 확인
    ↓
사람이 필요 시 회사별 Custom Context 직접 입력
    ↓
Deterministic Email Template
    +
수신자 정보
    +
Human-Written Custom Context
    ↓
최소한의 문법 조정
    ↓
최종 메일
```

메일 전체를 LLM이 새롭게 설계하거나 다시 작성하지 않는다.

---

# 2. Agent 역할 분리

## 2.1 Account Researcher

Account Researcher는 다음을 적극적으로 조사할 수 있다.

- 회사 규모
- 매출
- 임직원 수
- 상장 여부
- 투자 유치
- 주요 사업
- 최근 사업 동향
- 한국 내 사업 및 조직
- Agora RTC 적용 가능성
- Agora AI 적용 가능성
- 영업가치 / Commercial Attractiveness

이 결과는 **영업담당자의 판단을 위한 자료**다.

Researcher가 찾아낸 회사 정보, Use Case, Agora 제품 추천, Reference는 Email Writer에 자동 삽입하지 않는다.

---

## 2.2 Email Writer

Email Writer는 다음 역할만 수행한다.

```text
Fixed Template
+
회사명
+
수신자명
+
확인된 직책
+
사람이 직접 작성한 회사별 문장
↓
최종 이메일
```

Email Writer가 수행하지 않는 작업:

```text
회사명만 보고 유즈케이스 생성
회사 업종만 보고 제품 추천
Research 결과를 본문에 자동 삽입
레퍼런스 고객 자동 선택
구매 담당 여부 추론
구매 의사결정권 확인 문구 생성
새로운 고객 니즈 생성
새로운 영업 논리 생성
메일 전체 자유 재작성
```

---

# 3. 메일 기본 구조

모든 메일은 기본적으로 아래 순서를 따른다.

```text
1. 제목
2. 수신자 호칭
3. 행사 방문 감사
4. 발신자 + 직함 소개
5. Agora 기본 회사 소개
6. Agora Conversational AI 소개
7. [OPTIONAL] Human-Written Company Context
8. Agora 기본 영업 연결 문장
9. 전화 / 방문 미팅 제안
10. 마무리
11. 서명
```

---

# 4. 제목

기본 제목:

```text
실시간 소통 플랫폼(CPaaS), Agora에서 인사 드립니다. ({회사명})
```

행사 맥락을 제목에 직접 넣고 싶은 경우:

```text
[AI Summit Seoul & EXPO 2026] Agora에서 인사 드립니다. ({회사명})
```

별도 지시가 없는 한 제목을 새로 창작하지 않는다.

---

# 5. 수신자 호칭

## 5.1 이름과 직책이 모두 확인되는 경우

```text
{담당자 이름} {직책}님께,

{담당자 이름} {직책}님 안녕하세요!
```

예:

```text
지청원 팀장님께,

지청원 팀장님 안녕하세요!
```

## 5.2 이름은 있으나 직책이 불확실한 경우

```text
{담당자 이름} 담당자님께,

{담당자 이름} 담당자님 안녕하세요!
```

## 5.3 이름이 없는 경우

```text
{회사명} 담당자님께,

담당자님 안녕하세요!
```

### 규칙

- 직책은 원본 방문자 데이터에서 명확히 확인되는 경우에만 사용한다.
- `Manager`, `Lead`, `Specialist` 등을 한국식 직급으로 임의 변환하지 않는다.
- 직책이 불확실하면 `담당자님`을 사용한다.

---

# 6. Fixed Opening Block

다음 문장은 기본적으로 고정한다.

```text
지난 AI Summit Seoul & EXPO 2026 아고라 부스에 방문해주셔서 감사합니다.

저는 아고라(Agora Inc., NASDAQ: API)의 한국 매니저 박세빈입니다.

당시 짧게 소개드렸던 저희 회사와 솔루션을 다시 한번 소개드리고 싶어 연락드립니다.
```

## 중요 규칙

다음 표현은 사용하지 않는다.

```text
저는 아고라(Agora Inc., NASDAQ: API)의 박세빈입니다.
```

반드시 본문 안에서 발신자 직함을 포함한다.

```text
아고라(Agora Inc., NASDAQ: API)의 한국 매니저 박세빈입니다.
```

또한:

- 행사 방문 감사 문장을 삭제하지 않는다.
- 콜드 아웃바운드 형식으로 변경하지 않는다.
- 오프닝에서 회사별 니즈를 추론하지 않는다.

---

# 7. Fixed Agora Company Introduction Block

다음 내용은 기본적으로 고정한다.

```text
아고라는 전 세계 실시간 소통(Real-Time Communication) 기술을 제공하는 기업으로, 고객사가 별도의 실시간 통신 인프라를 직접 구축하지 않아도 영상 및 음성 통화, 텍스트 메시징, 라이브 스트리밍 등 실시간 소통 기능을 애플리케이션에 손쉽게 내장할 수 있도록 API와 SDK 형태로 제공합니다.

또한 세계 전역 250개 이상의 데이터센터를 기반으로 글로벌 네트워크를 운영하며, 전 세계 다양한 지역에서 안정적인 초저지연 실시간 통신 환경을 지원합니다.
```

고정 핵심 요소:

```text
Real-Time Communication
영상 및 음성 통화
텍스트 메시징
라이브 스트리밍
API / SDK
별도 실시간 통신 인프라 구축 부담 감소
250+ 데이터센터
글로벌 실시간 통신
```

### 문단 처리

- 제품 설명을 지나치게 여러 줄로 쪼개지 않는다.
- 이메일 본문에서는 1~2개의 자연스러운 문단으로 유지한다.
- 모델이 이 문단의 영업 논리를 재구성하지 않는다.
- 명백한 오탈자나 문법 오류 외에는 자유롭게 다시 쓰지 않는다.

---

# 8. Fixed AI Introduction Block

AI Summit 방문자 대상이라는 점을 고려해 다음 문장을 기본 블록으로 사용한다.

```text
지난해부터 아고라는 실시간 대화형 AI(Conversational AI) 기술을 기반으로 실시간 AI 통번역, AICC, AIoT Device Kit 등 다양한 AI 솔루션을 개발 및 공급하고 있습니다.
```

### 규칙

- 이 문단은 Agora의 큰 사업 방향만 설명한다.
- 수신 회사에 맞는 구체 AI Use Case를 자동 생성하지 않는다.
- 수신 회사에 맞는 AI 솔루션을 자동 선택하지 않는다.

예를 들어 다음 문장은 사람이 입력하지 않았다면 자동 생성하면 안 된다.

```text
귀사의 예약 변경 및 FAQ 업무에 Voice AI를 적용할 수 있습니다.
```

---

# 9. Human-Written Company Context Block

회사별 구체적인 사업 맥락이나 Use Case는 **사람이 직접 작성한다.**

웹 UI에서 다음과 같은 별도 입력 영역을 제공하는 것을 전제로 한다.

```text
[회사별 추가 문구 - 선택사항]

________________________________________________

________________________________________________

________________________________________________
```

예:

```text
고려대학교의료원의 디지털 헬스케어 사업과 관련해,
향후 실시간 영상 상담이나 AI 기반 커뮤니케이션 기능을 검토하실 기회가 있다면
아고라의 기술도 함께 살펴볼 수 있을 것으로 생각합니다.
```

또는 더 구체적인 실제 영업 맥락을 사람이 직접 작성할 수 있다.

### 처리 규칙

```text
human_company_context 값 있음
→ 해당 문단 삽입

human_company_context 값 없음
→ 전체 블록 삭제
```

Email Writer는 이 영역의:

- 회사 사실
- 고객 니즈
- Use Case
- 제품
- 적용 시나리오
- Reference

를 새로 생성하지 않는다.

사람이 입력한 문장에 대해서만 아래의 최소 편집을 허용한다.

```text
조사 수정
어미 수정
띄어쓰기
문장 연결
쉼표 위치 조정
명백한 중복 제거
명백한 문법 오류 수정
```

---

# 10. Research 결과의 메일 자동 삽입 금지

Account Researcher가 다음 정보를 찾아냈더라도:

```text
회사 신규 프로젝트
디지털 전환 전략
AI 투자
CRM 전략
병원 신설
채용 확대
특정 서비스
Agora 적용 Use Case
```

Email Writer가 이를 자동으로 본문에 넣으면 안 된다.

잘못된 흐름:

```text
Account Researcher
    ↓
회사 정보 발견
    ↓
Email Writer가 자동 삽입
```

올바른 흐름:

```text
Account Researcher
    ↓
영업담당자가 화면에서 확인
    ↓
메일에 쓸 내용 선택
    ↓
사람이 직접 Custom Context에 입력
    ↓
Email Writer가 문법만 정리
```

---

# 11. Default Sales Bridge

Human-Written Company Context가 없더라도 메일이 자연스럽게 영업 제안으로 이어지도록 아래 문장을 기본적으로 사용할 수 있다.

권장 기본형:

```text
아고라는 글로벌 실시간 통신 인프라와 더불어 긴밀한 기술지원을 제공하고 있어, 향후 관련 실시간 소통 또는 AI 기능을 검토하실 기회가 있다면 아고라 솔루션도 함께 살펴봐주시면 감사하겠습니다.
```

내부적으로 사용 승인이 된 경우 다음과 같이 보다 적극적인 표현을 사용할 수 있다.

```text
전 세계 최고 수준의 RTC 기술력과 더불어 긴밀한 기술지원을 통해 API를 보다 빠르고 편리하게 활용할 수 있는 아고라 솔루션도 향후 관련 기능을 검토하실 때 함께 살펴봐주시면 감사하겠습니다.
```

### 규칙

- 회사별 사업을 억지로 연결하지 않는다.
- 자동으로 특정 제품을 추천하지 않는다.
- 자동으로 특정 Use Case를 넣지 않는다.

---

# 12. 구매팀 / 조달 qualification 문장 금지

첫 후속 메일에서는 다음과 같은 qualification 질문을 기본적으로 사용하지 않는다.

```text
구매팀에서 관여하시는 범위를 확인드릴 수 있을까요?

관련 솔루션 조달 담당자를 연결해주실 수 있을까요?

구매 의사결정권이 있으신가요?

예산 담당 부서를 알려주실 수 있을까요?

담당 부서가 따로 있다면 연결 부탁드립니다.
```

이유:

- 첫 후속 메일에서 지나치게 직접적임
- 상대방에게 일을 요청하는 인상을 줄 수 있음
- 관계 형성보다 qualification이 먼저 보임
- 구매 의사결정권을 캐묻는 인상을 줄 수 있음

영업 qualification은 이후 실제 대화나 미팅 과정에서 진행한다.

---

# 13. Fixed CTA Block

기본 CTA는 **“전화하거나 직접 찾아뵙겠다”**는 방향으로 작성한다.

권장형:

```text
전화로 간단히 말씀드리거나 직접 사무실로 방문해 아고라의 솔루션과 다양한 적용 사례를 소개드릴 기회가 있으면 좋겠습니다.

편하신 시간을 알려주시면 일정에 맞춰 찾아뵙고 인사드리겠습니다.
```

또는:

```text
전화 통화 또는 사무실로 방문하여 보다 자세히 저희 솔루션과 적용 사례를 소개드릴 기회가 있으면 좋겠습니다.

미팅 가능한 시간을 알려주시면 일정에 맞춰 찾아뵙고 인사드리겠습니다.
```

### 피해야 할 CTA

```text
15분 정도 미팅 가능하실까요?
구매 검토 여부를 알려주세요.
관련 담당자를 연결해주세요.
구매팀에서 관여하시는 범위를 확인하고 싶습니다.
```

---

# 14. 마무리

`감사합니다`를 반복하지 않는다.

권장 순서:

```text
전화로 간단히 말씀드리거나 직접 사무실로 방문해 아고라의 솔루션과 다양한 적용 사례를 소개드릴 기회가 있으면 좋겠습니다.

편하신 시간을 알려주시면 일정에 맞춰 찾아뵙고 인사드리겠습니다.

궁금하신 점이 있으시면 언제든 편하게 연락 주시기 바랍니다.

감사합니다.
```

잘못된 예:

```text
... 찾아뵙고 인사드리겠습니다.
감사합니다.

궁금하신 점이 있으시면 편하게 연락 주시기 바랍니다.

감사합니다.
```

---

# 15. Fixed Signature Block

Email Writer가 생성하는 기본 서명은 다음으로 고정한다.

```text
박세빈
Sales Manager | Agora 드림
```

전화번호, 이메일, 회사 슬로건 등 상세 서명이 필요하면 Outlook 또는 실제 메일 시스템의 signature 기능으로 별도 처리하는 것을 권장한다.

---

# 16. 최종 Deterministic Skeleton

```text
제목: 실시간 소통 플랫폼(CPaaS), Agora에서 인사 드립니다. ({회사명})


{담당자 이름} {직책}님께,

{담당자 이름} {직책}님 안녕하세요!

지난 AI Summit Seoul & EXPO 2026 아고라 부스에 방문해주셔서 감사합니다.

저는 아고라(Agora Inc., NASDAQ: API)의 한국 매니저 박세빈입니다.

당시 짧게 소개드렸던 저희 회사와 솔루션을 다시 한번 소개드리고 싶어 연락드립니다.


아고라는 전 세계 실시간 소통(Real-Time Communication) 기술을 제공하는 기업으로, 고객사가 별도의 실시간 통신 인프라를 직접 구축하지 않아도 영상 및 음성 통화, 텍스트 메시징, 라이브 스트리밍 등 실시간 소통 기능을 애플리케이션에 손쉽게 내장할 수 있도록 API와 SDK 형태로 제공합니다.

또한 세계 전역 250개 이상의 데이터센터를 기반으로 글로벌 네트워크를 운영하며, 전 세계 다양한 지역에서 안정적인 초저지연 실시간 통신 환경을 지원합니다.


지난해부터 아고라는 실시간 대화형 AI(Conversational AI) 기술을 기반으로 실시간 AI 통번역, AICC, AIoT Device Kit 등 다양한 AI 솔루션을 개발 및 공급하고 있습니다.


[OPTIONAL: HUMAN-WRITTEN COMPANY CONTEXT]

{사람이 직접 작성한 회사별 추가 문장}


아고라는 글로벌 실시간 통신 인프라와 더불어 긴밀한 기술지원을 제공하고 있어, 향후 관련 실시간 소통 또는 AI 기능을 검토하실 기회가 있다면 아고라 솔루션도 함께 살펴봐주시면 감사하겠습니다.


전화로 간단히 말씀드리거나 직접 사무실로 방문해 아고라의 솔루션과 다양한 적용 사례를 소개드릴 기회가 있으면 좋겠습니다.

편하신 시간을 알려주시면 일정에 맞춰 찾아뵙고 인사드리겠습니다.

궁금하신 점이 있으시면 언제든 편하게 연락 주시기 바랍니다.

감사합니다.

박세빈
Sales Manager | Agora 드림
```

---

# 17. Optional Block 처리 규칙

```text
human_company_context 없음
→ HUMAN-WRITTEN COMPANY CONTEXT BLOCK 삭제
```

빈 placeholder를 출력하지 않는다.

잘못된 출력:

```text
{사람이 직접 작성한 회사별 추가 문장}
```

올바른 처리:

```text
해당 문단 전체 삭제
```

---

# 18. Agent Input Schema

권장 입력값은 다음과 같이 최소화한다.

```yaml
company_name: ""
recipient_name: ""
recipient_title: ""

human_company_context: ""

extra_instruction: ""
```

### 자동 입력 가능

```text
company_name
recipient_name
recipient_title
```

### 사람 입력만 허용

```text
human_company_context
```

`extra_instruction`은 특정 메일에 한해 사람이 Fixed Block 변경을 명시적으로 요청할 때만 사용한다.

---

# 19. Agent Processing Rule

```text
STEP 1
입력값 확인

STEP 2
Fixed Skeleton 불러오기

STEP 3
회사명 / 수신자명 / 확인된 직책 치환

STEP 4
human_company_context 확인

STEP 5
값이 있으면 Human-Written Context 삽입
값이 없으면 해당 Block 삭제

STEP 6
최소한의 조사 / 어미 / 문법 조정

STEP 7
Research 결과가 자동 삽입되지 않았는지 확인

STEP 8
새로운 Use Case / 제품 / Reference / 고객 니즈가 생성되지 않았는지 확인

STEP 9
구매팀 / 조달 / 담당자 연결 요청이 자동 생성되지 않았는지 확인

STEP 10
"감사합니다" 중복 확인

STEP 11
Fixed Block이 임의로 재작성되지 않았는지 확인

STEP 12
최종 메일 출력
```

---

# 20. System Prompt

```text
You generate deterministic follow-up emails for Agora.

All recipients visited the Agora booth at
AI Summit Seoul & EXPO 2026.

This is NOT a cold outbound email.

Your job is NOT to design a sales strategy.

Your job is NOT to analyze the recipient company.

Your job is NOT to select a use case.

Your job is NOT to recommend an Agora product.

Your job is NOT to select a reference customer.

Your job is NOT to qualify the recipient's purchasing authority.

Use the fixed Agora follow-up template.

Automatically fill only:
- company_name
- recipient_name
- verified recipient_title

Company-specific business context may only be included
when the human user explicitly supplies it through
human_company_context.

Never transfer Account Research results into the email automatically.

Do not ask whether the recipient is responsible for procurement.

Do not ask the recipient to introduce a purchasing owner,
procurement team, budget owner, or responsible department by default.

The preferred CTA is:
- a brief phone conversation, or
- an in-person visit to introduce Agora solutions and cases.

Explicitly identify the sender in the body as:

"아고라(Agora Inc., NASDAQ: API)의 한국 매니저 박세빈"

Preserve:
- the event follow-up opening
- the Agora company introduction
- the RTC/API/SDK description
- the global network paragraph
- the Conversational AI introduction
- the default sales bridge
- the CTA
- the signature

unless the human user explicitly requests a change.

If human_company_context is empty,
omit that block entirely.

If recipient_title is uncertain,
use "담당자님" rather than inventing or translating a title.

Prefer omission over inference.

Do not duplicate "감사합니다."

Do not invent:
- company facts
- use cases
- Agora product recommendations
- reference customers
- customer needs
- procurement roles
- performance claims
- industry-specific sales narratives

Only make minimal grammatical edits required
after deterministic slot substitution.

The final email must remain structurally close
to the fixed template.
```

---

# 21. Email Writer와 Researcher의 최종 관계

```text
              ┌───────────────────────┐
              │   Account Researcher  │
              │                       │
              │ 매출 / 임직원 / 투자  │
              │ 최근 동향             │
              │ RTC / AI Opportunity  │
              │ Commercial Value      │
              └──────────┬────────────┘
                         │
                         ▼
              ┌───────────────────────┐
              │    Human Sales Rep    │
              │                       │
              │ 결과 확인             │
              │ 사용할 맥락 선택      │
              │ 직접 Custom 문장 작성 │
              └──────────┬────────────┘
                         │
                         ▼
              ┌───────────────────────┐
              │ Deterministic Writer  │
              │                       │
              │ Fixed Template        │
              │ + Recipient Info      │
              │ + Human Context       │
              └──────────┬────────────┘
                         │
                         ▼
                   Final Email
```

---

# 22. 최종 검수 체크리스트

메일 생성 후 반드시 확인한다.

## Event

- [ ] AI Summit Seoul & EXPO 2026 부스 방문 감사가 들어갔는가?
- [ ] 콜드 아웃바운드처럼 보이지 않는가?

## Sender

- [ ] 본문에 `한국 매니저 박세빈`이 명시되어 있는가?

## Agora Introduction

- [ ] RTC / API / SDK 기본 설명이 유지되는가?
- [ ] 글로벌 네트워크 설명이 유지되는가?
- [ ] Conversational AI 기본 소개가 유지되는가?

## Company Context

- [ ] 회사별 구체적 내용은 사람이 직접 제공한 내용인가?
- [ ] Researcher의 결과가 자동으로 들어가지 않았는가?
- [ ] 회사 니즈나 Use Case를 Agent가 새로 만들지 않았는가?

## Sales

- [ ] 구매팀 관여 범위를 묻지 않는가?
- [ ] 담당자 연결을 기본적으로 요청하지 않는가?
- [ ] 구매 의사결정권을 직접 묻지 않는가?

## CTA

- [ ] 전화 또는 방문 소개를 자연스럽게 제안하는가?
- [ ] 편한 일정을 알려달라는 정도의 low-friction CTA인가?

## Drafting

- [ ] `감사합니다`가 중복되지 않는가?
- [ ] 불필요하게 긴 회사 분석이 없는가?
- [ ] Fixed Block이 임의로 재작성되지 않았는가?
- [ ] 확인되지 않은 사실이나 수치가 추가되지 않았는가?

---

# 23. 핵심 원칙 요약

```text
Research Agent
= 많이 조사한다.

Human Sales Rep
= 무엇을 메일에 쓸지 결정한다.

Email Writer
= 고정된 메일에 필요한 값만 넣는다.
```

가장 중요한 원칙:

> **Research와 Email Generation을 분리한다.**

> **회사별 영업 맥락은 사람이 통제한다.**

> **Email Writer는 새로운 영업전략을 만들지 않는다.**

> **첫 후속 메일은 구매 qualification이 아니라 관계 형성과 미팅 기회 확보에 집중한다.**

> **가능하면 “찾아뵙고 소개드리겠다”는 방향으로 CTA를 구성한다.**
