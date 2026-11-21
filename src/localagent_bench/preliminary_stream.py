"""Bounded OpenAI-compatible streaming probes on the configured loopback only."""
from __future__ import annotations

import json
import math
import re
import socket
import threading
import time
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request

from .providers import _OPENER, ProviderError
from .preliminary_suite import PreliminarySettings
from .thinking import ThinkingPolicy


def _number(value: Any) -> float | None:
    return float(value) if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def _visible(text: str) -> str:
    # Remove both complete and incomplete inline reasoning, including a split opening tag.
    text = re.sub(r'<think>.*?(?:</think>|$)', '', text, flags=re.S | re.I)
    return re.sub(r'<(?:t(?:h(?:i(?:n(?:k)?)?)?)?)?$', '', text, flags=re.I)


def measure(url: str, model: str, prompt: str, policy: ThinkingPolicy,
            options: PreliminarySettings, *, temperature: float, seed: int) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'} or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ProviderError('preliminary_endpoint')
    payload = {'model': model, 'messages': [{'role': 'user', 'content': prompt}],
               'stream': True, 'stream_options': {'include_usage': True},
               'reasoning_effort': policy.reasoning_effort, 'temperature': temperature,
               'max_tokens': options.max_tokens, 'seed': seed}
    request = Request(url + '/v1/chat/completions', data=json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json'}, method='POST')
    started = time.monotonic()
    content, buffer = '', b''
    first = last = previous = None
    gaps: list[float] = []
    seen_chars = total = 0
    usage: dict[str, Any] = {}
    reasoning = False
    finish = None
    done = False
    decode = None
    with _OPENER.open(request, timeout=options.timeout_seconds) as response:
        # A socket shutdown interrupts even a slow-drip body. No retries or redirects.
        def expire() -> None:
            sock = getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None)
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        timer = threading.Timer(max(.001, options.timeout_seconds - (time.monotonic() - started)), expire)
        timer.daemon = True
        timer.start()
        try:
            while not done:
                if time.monotonic() - started >= options.timeout_seconds:
                    raise TimeoutError('preliminary_timeout')
                block = response.read1(min(4096, options.max_event_bytes))
                if not block:
                    break
                total += len(block)
                if total > options.max_response_bytes:
                    raise ProviderError('preliminary_payload_limit')
                buffer += block
                while b'\n' in buffer:
                    raw, buffer = buffer.split(b'\n', 1)
                    if len(raw) > options.max_event_bytes:
                        raise ProviderError('preliminary_event_limit')
                    raw = raw.strip()
                    if not raw or raw.startswith(b':'):
                        continue
                    if not raw.startswith(b'data:'):
                        raise ProviderError('preliminary_stream_protocol')
                    raw = raw[5:].strip()
                    if raw == b'[DONE]':
                        done = True
                        break
                    event = json.loads(raw)
                    if not isinstance(event, dict) or 'error' in event:
                        raise ProviderError('preliminary_stream_protocol')
                    now = time.monotonic()
                    if isinstance(event.get('usage'), dict):
                        usage = event['usage']
                    timings = event.get('timings')
                    if isinstance(timings, dict):
                        decode = _number(timings.get('predicted_per_second'))
                    choices = event.get('choices', [])
                    if not isinstance(choices, list):
                        raise ProviderError('preliminary_stream_protocol')
                    for choice in choices:
                        if not isinstance(choice, dict) or not isinstance(choice.get('delta', {}), dict):
                            raise ProviderError('preliminary_stream_protocol')
                        delta = choice.get('delta', {})
                        reasoning |= any(bool(delta.get(k)) for k in ('reasoning', 'reasoning_content', 'reasoning_details', 'thinking'))
                        text = delta.get('content')
                        if text is not None and not isinstance(text, str):
                            raise ProviderError('preliminary_stream_protocol')
                        if text:
                            content += text
                            reasoning |= bool(re.search(r'<think>', content, re.I))
                            visible = _visible(content)
                            if len(visible.strip()) > seen_chars:
                                first = now if first is None else first
                                if previous is not None:
                                    gaps.append(now - previous)
                                previous = last = now
                                seen_chars = len(visible.strip())
                        if choice.get('finish_reason') is not None:
                            finish = choice['finish_reason']
                if len(buffer) > options.max_event_bytes:
                    raise ProviderError('preliminary_event_limit')
        finally:
            timer.cancel()
    duration = time.monotonic() - started
    if duration >= options.timeout_seconds:
        raise TimeoutError('preliminary_timeout')
    if not done or finish not in {'stop', 'length'}:
        raise ProviderError('preliminary_incomplete_stream')
    details = usage.get('completion_tokens_details', {})
    reasoning |= bool(details.get('reasoning_tokens', 0)) if isinstance(details, dict) else False
    tokens = _number(usage.get('completion_tokens'))
    answer = _visible(content).strip()
    return {'duration_seconds': round(duration, 6),
            'first_answer_seconds': round(first - started, 6) if first is not None else None,
            'output_tokens': tokens,
            'output_tokens_per_second': round(tokens / duration, 6) if tokens is not None and duration > 0 else None,
            'decode_tokens_per_second': decode,
            'max_chunk_gap_seconds': round(max(gaps), 6) if gaps else None,
            'answer_chars': len(answer), 'answer': answer,
            'thinking_observed': reasoning, 'truncated': finish == 'length'}
