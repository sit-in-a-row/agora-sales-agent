from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, TypeVar
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)
TraceCallback = Callable[[dict[str, Any]], None]


@dataclass(slots=True)
class ProviderResult:
    parsed: BaseModel
    raw: dict[str, Any]
    sources: list[dict[str, Any]]
    usage: dict[str, Any]


class ProviderError(RuntimeError):
    pass


def normalize_url(url: str) -> str:
    try:
        parts = urlsplit(url.strip())
        path = parts.path.rstrip('/') or '/'
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ''))
    except Exception:
        return url.strip().rstrip('/')


def _dump_no_warnings(obj: Any) -> Any:
    """Serialize SDK/Pydantic objects without the noisy generic ParsedResponse warnings.

    openai.responses.parse() returns a generic ParsedResponse. Serializing the entire
    generic object with Pydantic 2.13 can emit PydanticSerializationUnexpectedValue
    warnings even though output_parsed is valid. We only serialize the pieces we need.
    """
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _dump_no_warnings(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_dump_no_warnings(v) for v in obj]
    if hasattr(obj, 'model_dump'):
        try:
            return obj.model_dump(mode='json', warnings=False, exclude_none=True)
        except TypeError:
            # Older Pydantic versions may not expose warnings=.
            return obj.model_dump(mode='json', exclude_none=True)
    return str(obj)


def extract_web_sources(raw: Any) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            url = node.get('url')
            if isinstance(url, str) and url.startswith(('http://', 'https://')):
                key = normalize_url(url)
                found.setdefault(key, {
                    'url': url,
                    'title': node.get('title') or node.get('name') or '',
                    'type': node.get('type') or 'url',
                })
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(raw)
    return list(found.values())


def extract_usage(raw: dict[str, Any]) -> dict[str, Any]:
    usage = raw.get('usage') or {}
    return usage if isinstance(usage, dict) else {}


def _clip_for_live_ui(value: Any, max_chars: int = 60000) -> tuple[Any, bool]:
    """Keep SSE payloads responsive while preserving full semantic content in most calls."""
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    if len(text) <= max_chars:
        return value, False
    return {
        '_truncated': True,
        '_original_chars': len(text),
        'preview': text[:max_chars] + '\n… [live transcript truncated]',
    }, True


class OpenAIProvider:
    def __init__(self, api_key: str, trace_callback: TraceCallback | None = None):
        try:
            from openai import AsyncOpenAI
        except Exception as exc:
            raise ProviderError('정식 OpenAI Python SDK가 필요합니다. `pip install -r requirements.txt`를 실행하세요.') from exc
        self.client = AsyncOpenAI(api_key=api_key)
        self.trace_callback = trace_callback

    def _trace(self, payload: dict[str, Any]) -> None:
        if not self.trace_callback:
            return
        try:
            self.trace_callback(payload)
        except Exception:
            # Observability must never break the actual API pipeline.
            pass

    async def parse(
        self,
        *,
        model: str,
        system_prompt: str,
        user_payload: Any,
        response_model: type[T],
        reasoning_effort: str = 'low',
        web_search: bool = False,
        require_web: bool = False,
        prompt_cache_key: str | None = None,
        trace_label: str | None = None,
    ) -> ProviderResult:
        kwargs: dict[str, Any] = {
            'model': model,
            'store': False,
            'reasoning': {'effort': reasoning_effort},
            'input': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': json.dumps(user_payload, ensure_ascii=False, default=str)},
            ],
            'text_format': response_model,
        }
        if prompt_cache_key:
            kwargs['prompt_cache_key'] = prompt_cache_key
        if web_search:
            kwargs['tools'] = [{'type': 'web_search'}]
            kwargs['include'] = ['web_search_call.action.sources']
            kwargs['tool_choice'] = 'required' if require_web else 'auto'

        call_id = f"api_{uuid.uuid4().hex[:10]}"
        label = trace_label or prompt_cache_key or response_model.__name__
        self._trace({
            'phase': 'request',
            'call_id': call_id,
            'agent': label,
            'model': model,
            'reasoning_effort': reasoning_effort,
            'web_search': web_search,
            'require_web': require_web,
            'system_prompt': system_prompt,
            'user_payload': user_payload,
        })

        last: Exception | None = None
        for attempt in range(1, 4):
            started = time.perf_counter()
            try:
                if attempt > 1:
                    self._trace({
                        'phase': 'retry',
                        'call_id': call_id,
                        'agent': label,
                        'model': model,
                        'attempt': attempt,
                    })
                response = await self.client.responses.parse(**kwargs)
                parsed = getattr(response, 'output_parsed', None)
                if parsed is None:
                    raise ProviderError('Structured output을 파싱하지 못했습니다.')

                # Do NOT model_dump() the entire generic ParsedResponse. That was the
                # source of the long PydanticSerializationUnexpectedValue warnings.
                output_items = _dump_no_warnings(getattr(response, 'output', []))
                usage = _dump_no_warnings(getattr(response, 'usage', None)) or {}
                raw = {
                    'id': getattr(response, 'id', None),
                    'model': getattr(response, 'model', model),
                    'status': getattr(response, 'status', None),
                    'output': output_items,
                    'usage': usage,
                }
                sources = extract_web_sources(raw)
                parsed_payload = _dump_no_warnings(parsed)
                self._trace({
                    'phase': 'response',
                    'call_id': call_id,
                    'agent': label,
                    'model': model,
                    'attempt': attempt,
                    'duration_sec': round(time.perf_counter() - started, 3),
                    'parsed': parsed_payload,
                    'sources': sources,
                    'usage': usage,
                    'response_id': raw.get('id'),
                })
                return ProviderResult(parsed=parsed, raw=raw, sources=sources, usage=usage)
            except Exception as exc:
                last = exc
                self._trace({
                    'phase': 'error',
                    'call_id': call_id,
                    'agent': label,
                    'model': model,
                    'attempt': attempt,
                    'duration_sec': round(time.perf_counter() - started, 3),
                    'error_type': type(exc).__name__,
                    'message': str(exc),
                })
                if attempt < 3:
                    await asyncio.sleep(min(2 ** (attempt - 1), 4))

        raise last or ProviderError('OpenAI API call failed')

    async def close(self) -> None:
        close = getattr(self.client, 'close', None)
        if close:
            maybe = close()
            if asyncio.iscoroutine(maybe):
                await maybe
