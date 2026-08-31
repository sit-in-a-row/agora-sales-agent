# OpenAI API implementation notes

검증일: 2026-08-28

## 사용 방식

- Responses API
- GPT-5.6 Luna / Terra / Sol
- `client.responses.parse(..., text_format=PydanticModel)` Structured Outputs
- Account Research / ambiguous entity resolution에서 hosted `web_search`
- `include=["web_search_call.action.sources"]`로 source ledger 확보
- `store=False`

## Model routing

- Entity Resolver: `gpt-5.6-luna`
- Web Entity Resolver: `gpt-5.6-terra`
- Account Research: `gpt-5.6-terra`
- Lead Scoring: `gpt-5.6-terra`
- Sales Strategy: `gpt-5.6-terra`
- Writer: `gpt-5.6-terra`
- Normal Reviewer: `gpt-5.6-terra`
- Quality Reviewer: `gpt-5.6-sol`

## Official references

- https://developers.openai.com/api/docs/models
- https://developers.openai.com/api/docs/guides/latest-model
- https://developers.openai.com/api/reference/cli/resources/responses/methods/create
- https://github.com/openai/openai-python/blob/main/examples/responses/structured_outputs.py

## Validation policy

Researcher output의 evidence URL을 실제 web-search source ledger와 비교한다.
ledger에 없는 URL은 제거하고 confidence를 낮추며, 최대 한 번 targeted retry한다.
