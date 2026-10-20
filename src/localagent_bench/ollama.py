"""Small Ollama HTTP client using only the Python standard library."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from typing import Any

from .thinking import ThinkingPolicy


class OllamaError(RuntimeError):
    """Raised when the local Ollama service cannot satisfy a request."""


@dataclass(frozen=True)
class OllamaModel:
    name: str
    size: int | None
    digest: str | None
    modified_at: str | None
    details: dict[str, Any]
    capabilities: tuple[str, ...] = ()
    capabilities_known: bool = False
    thinking_capable: bool | None = None


@dataclass(frozen=True)
class ThinkingPreflight:
    """Safe metadata from a provider control probe; response content is discarded."""

    status: str
    requested: str
    reasoning_effort: str
    thinking_capable: bool | None
    thinking_observed: bool
    reasoning_chars: int
    reasoning_tokens: int | None
    duration_ms: int

    @property
    def passed(self) -> bool:
        return self.status == "passed"


def _safe_model_details(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, Any] = {}
    for key in ("parent_model", "format", "family", "parameter_size", "quantization_level"):
        item = value.get(key)
        if isinstance(item, str) and item.strip() and len(item) <= 128:
            output[key] = item
    families = value.get("families")
    if isinstance(families, list):
        output["families"] = [
            item for item in families if isinstance(item, str) and item.strip() and len(item) <= 128
        ][:32]
    return output


def _request(url: str, path: str, payload: dict[str, Any] | None = None, timeout: int = 30) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{url.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OllamaError(f"Ollama non raggiungibile su {url}: {exc}") from exc


def list_models(url: str) -> list[OllamaModel]:
    raw = _request(url, "/api/tags")
    models = raw.get("models", []) if isinstance(raw, dict) else []
    result: list[OllamaModel] = []
    for item in models:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        result.append(
            OllamaModel(
                name=item["name"],
                size=item.get("size") if isinstance(item.get("size"), int) else None,
                digest=item.get("digest") if isinstance(item.get("digest"), str) else None,
                modified_at=item.get("modified_at") if isinstance(item.get("modified_at"), str) else None,
                details=_safe_model_details(item.get("details")),
            )
        )
    return sorted(result, key=lambda model: model.name.casefold())


def inspect_model(url: str, model: OllamaModel, timeout: int = 30) -> OllamaModel:
    """Attach whitelisted `/api/show` capabilities to a model summary."""
    raw = _request(url, "/api/show", {"model": model.name}, timeout=timeout)
    if not isinstance(raw, dict):
        raise OllamaError(f"Risposta /api/show non valida per {model.name}")
    raw_capabilities = raw.get("capabilities")
    if not isinstance(raw_capabilities, list):
        return replace(
            model,
            capabilities=(),
            capabilities_known=False,
            thinking_capable=None,
        )
    capabilities = tuple(
        dict.fromkeys(
            item.strip().lower()
            for item in raw_capabilities
            if isinstance(item, str) and item.strip() and len(item.strip()) <= 64
        )
    )
    return replace(
        model,
        capabilities=capabilities,
        capabilities_known=True,
        thinking_capable="thinking" in capabilities,
    )


def version(url: str) -> str | None:
    raw = _request(url, "/api/version")
    return raw.get("version") if isinstance(raw, dict) and isinstance(raw.get("version"), str) else None


def _reasoning_length(value: Any) -> int:
    if isinstance(value, str):
        return len(value)
    if isinstance(value, list):
        return sum(_reasoning_length(item) for item in value)
    if isinstance(value, dict):
        return sum(_reasoning_length(item) for item in value.values())
    return 0


def preflight_thinking(
    url: str,
    model: OllamaModel,
    policy: ThinkingPolicy,
    *,
    timeout: int,
) -> ThinkingPreflight:
    """Verify one model/control pair through Ollama's OpenAI-compatible endpoint."""
    started = time.monotonic()

    def outcome(
        status: str,
        *,
        observed: bool = False,
        chars: int = 0,
        tokens: int | None = None,
    ) -> ThinkingPreflight:
        return ThinkingPreflight(
            status=status,
            requested=policy.requested,
            reasoning_effort=policy.reasoning_effort,
            thinking_capable=model.thinking_capable,
            thinking_observed=observed,
            reasoning_chars=chars,
            reasoning_tokens=tokens,
            duration_ms=max(0, round((time.monotonic() - started) * 1000)),
        )

    if policy.active and model.thinking_capable is not True:
        return outcome(
            "unsupported_capability" if model.thinking_capable is False else "unknown_capability"
        )
    try:
        raw = _request(
            url,
            "/v1/chat/completions",
            {
                "model": model.name,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Solve this constraint problem, then reply with only the final three-digit "
                            "number: its digits are distinct, their sum is 11, the tens digit is twice "
                            "the units digit, and the hundreds digit is three more than the units digit."
                        ),
                    }
                ],
                "stream": False,
                "temperature": 0,
                "max_tokens": 96,
                "reasoning_effort": policy.reasoning_effort,
            },
            timeout=timeout,
        )
    except OllamaError:
        return outcome("provider_error")
    if not isinstance(raw, dict):
        return outcome("invalid_response")
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return outcome("invalid_response")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return outcome("invalid_response")
    chars = sum(
        _reasoning_length(message.get(key))
        for key in ("reasoning", "reasoning_content", "reasoning_details", "thinking")
    )
    usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
    details = (
        usage.get("completion_tokens_details")
        if isinstance(usage.get("completion_tokens_details"), dict)
        else {}
    )
    raw_tokens = details.get("reasoning_tokens", usage.get("reasoning_tokens"))
    tokens = (
        int(raw_tokens)
        if isinstance(raw_tokens, (int, float)) and not isinstance(raw_tokens, bool) and raw_tokens >= 0
        else None
    )
    observed = chars > 0 or (tokens is not None and tokens > 0)
    if not policy.active and observed:
        return outcome("unexpected_thinking", observed=True, chars=chars, tokens=tokens)
    if policy.active and not observed:
        return outcome("thinking_not_observed", chars=chars, tokens=tokens)
    return outcome("passed", observed=observed, chars=chars, tokens=tokens)


def warmup(
    url: str,
    model: str,
    keep_alive: str,
    timeout: int,
    policy: ThinkingPolicy,
) -> dict[str, Any]:
    raw = _request(
        url,
        "/api/generate",
        {
            "model": model,
            "prompt": "Reply with exactly: OK",
            "stream": False,
            "keep_alive": keep_alive,
            "think": policy.native_think,
            "options": {"temperature": 0, "num_predict": 8},
        },
        timeout=timeout,
    )
    return raw if isinstance(raw, dict) else {}


def unload(url: str, model: str) -> None:
    _request(
        url,
        "/api/generate",
        {"model": model, "keep_alive": 0},
        timeout=30,
    )


class OllamaProvider:
    """Adapt the existing Ollama functions without changing their request flow."""

    kind = "ollama"
    explicit_load = False
    infer_capability_from_preflight = False
    version_source = "api"

    def __init__(self, url: str, keep_alive: str):
        self.url = url
        self.keep_alive = keep_alive

    def list_models(self) -> list[OllamaModel]:
        return list_models(self.url)

    def fingerprint_model(self, model: OllamaModel) -> OllamaModel:
        return model

    def inspect_model(self, model: OllamaModel, *, timeout: int = 30) -> OllamaModel:
        return inspect_model(self.url, model, timeout=timeout)

    def version(self) -> str | None:
        return version(self.url)

    def load(self, model: str, *, timeout: float) -> None:
        # Native Ollama loading remains part of warmup.
        return None

    def unload(self, model: str, *, timeout: float = 30) -> None:
        unload(self.url, model)

    def preflight_thinking(
        self, model: OllamaModel, policy: ThinkingPolicy, *, timeout: int
    ) -> ThinkingPreflight:
        return preflight_thinking(self.url, model, policy, timeout=timeout)

    def warmup(
        self, model: str, policy: ThinkingPolicy, *, timeout: int, context_window: int
    ) -> dict[str, Any]:
        return warmup(self.url, model, self.keep_alive, timeout, policy)
