"""Inert tool-call verification shared by resident local adapters."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import replace
from typing import Any

from . import providers as shared
from .ollama import OllamaModel, ThinkingPreflight
from .providers import ProviderError
from .thinking import ThinkingPolicy


def _streamed_tool_response(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{url}/v1/chat/completions", json.dumps(payload).encode(),
        {"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    deadline = time.monotonic() + timeout
    text: dict[str, list[str]] = {"content": [], "reasoning_content": [], "reasoning": [], "thinking": []}
    fragments: dict[str, list[str]] = {"name": [], "arguments": []}
    call_id = call_type = finish = None
    usage: dict[str, Any] = {}
    size = 0
    done = False
    try:
        with shared._OPENER.open(request, timeout=timeout) as response:
            if response.headers.get_content_type() != "text/event-stream":
                raise ProviderError("Flusso del tool non valido / Invalid tool stream")
            while time.monotonic() < deadline:
                line = response.readline(65537)
                size += len(line)
                if len(line) > 65536 or size > 1048576:
                    raise ProviderError("Flusso del tool troppo grande / Tool stream too large")
                if not line:
                    break
                if not line.startswith(b"data:"):
                    continue
                data = line[5:].strip()
                if data == b"[DONE]":
                    done = True
                    break
                frame = json.loads(data)
                if not isinstance(frame, dict):
                    raise ValueError("invalid frame")
                if isinstance(frame.get("usage"), dict):
                    usage = frame["usage"]
                choices = frame.get("choices", [])
                if not choices:
                    continue
                if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
                    raise ValueError("invalid choices")
                choice = choices[0]
                finish = choice.get("finish_reason") or finish
                delta = choice.get("delta") or {}
                for field in text:
                    value = delta.get(field)
                    if isinstance(value, str):
                        text[field].append(value)
                calls = delta.get("tool_calls") or []
                if not calls:
                    continue
                if not isinstance(calls, list) or len(calls) != 1 or not isinstance(calls[0], dict):
                    raise ValueError("invalid calls")
                call = calls[0]
                if call.get("index") != 0:
                    raise ValueError("invalid call index")
                call_id = call.get("id") or call_id
                call_type = call.get("type") or call_type
                function = call.get("function") or {}
                for field in fragments:
                    value = function.get(field)
                    if isinstance(value, str):
                        fragments[field].append(value)
    except urllib.error.HTTPError as exc:
        exc.close()
        raise ProviderError("Tool stream HTTP non disponibile / Tool stream HTTP unavailable") from None
    except (OSError, ValueError, AttributeError, TypeError) as exc:
        raise ProviderError("Flusso del tool non valido / Invalid tool stream") from None
    if not done:
        raise ProviderError("Flusso del tool incompleto / Incomplete tool stream")
    message: dict[str, Any] = {field: "".join(values) for field, values in text.items()}
    if finish == "tool_calls":
        message["tool_calls"] = [{"id": call_id, "type": call_type,
                                  "function": {field: "".join(values) for field, values in fragments.items()}}]
    return {"choices": [{"message": message}], "usage": usage}


def verify_tool_call(
    url: str, model: OllamaModel, policy: ThinkingPolicy,
    result: ThinkingPreflight, *, started: float, timeout: float, streamed: bool = False,
) -> ThinkingPreflight:
    remaining = timeout - (time.monotonic() - started)
    if remaining <= 0:
        return replace(result, status="tool_calling_not_verified")
    # Only inert client tools are offered. Their returned arguments are
    # validated as JSON; nothing in a model answer is executed.
    prompt = ("Call benchmark_probe now with integer value 7. Use the tool instead of writing an answer."
              if streamed else "Call benchmark_probe with value 7.")
    payload = {
        "model": model.name,
        "messages": [{"role": "user", "content": prompt}],
        "tools": [{"type": "function", "function": {
            "name": "benchmark_probe", "description": "Return a synthetic integer; no execution.",
            "parameters": {"type": "object", "properties": {"value": {"type": "integer"}},
                           "required": ["value"], "additionalProperties": False},
        }}],
        "tool_choice": "auto" if streamed else {"type": "function", "function": {"name": "benchmark_probe"}},
        "temperature": 0, "max_tokens": 128 if streamed else 96, "stream": streamed,
        "reasoning_effort": policy.reasoning_effort,
    }
    try:
        response = (_streamed_tool_response(url, payload, remaining) if streamed
                    else shared._request(url, "/v1/chat/completions", payload, timeout=remaining))
    except ProviderError:
        return replace(result, status="tool_calling_not_verified")
    choices = response.get("choices")
    message = choices[0].get("message") if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return replace(result, status="tool_calling_not_verified")
    observed, reasoning_chars, reasoning_tokens = shared.observed_reasoning(message, response.get("usage"))
    if not policy.active and observed:
        return replace(result, status="unexpected_thinking", thinking_observed=True,
                       reasoning_chars=reasoning_chars, reasoning_tokens=reasoning_tokens)
    calls = message.get("tool_calls")
    valid = False
    if isinstance(calls, list) and len(calls) == 1 and isinstance(calls[0], dict):
        call = calls[0]
        function = call.get("function")
        if (call.get("type") == "function" and isinstance(call.get("id"), str)
            and 0 < len(call["id"]) <= 256 and isinstance(function, dict)
            and function.get("name") == "benchmark_probe"):
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                try:
                    parsed = json.loads(arguments)
                    valid = (
                        isinstance(parsed, dict) and set(parsed) == {"value"}
                        and type(parsed["value"]) is int and parsed["value"] == 7
                    )
                except (ValueError, TypeError):
                    pass
    return replace(
        result, status="passed" if valid else "tool_calling_not_verified",
        duration_ms=max(0, round((time.monotonic() - started) * 1000)),
    )
