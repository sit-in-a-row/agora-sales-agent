# v1.1 changes

- Fixed noisy Pydantic serializer warnings from dumping the generic ParsedResponse object.
- Added API request/response observability via SSE and JSONL trace.
- Added B2B-first workbook source selection.
- Added B2B reconstruction from the workbook's actual formulas/rules.
- Added quick mode: default 6 leads, low reasoning effort for research/scoring/strategy, no supplemental research, no AI review/rewrite.
- Quality leads always remain human-review required.
- Added browser API transcript panel with system prompt, payload, structured output, web sources, usage and latency.
