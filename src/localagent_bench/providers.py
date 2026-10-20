"""Shared HTTP and thinking behavior for local provider adapters."""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path
from typing import Any

from .ollama import OllamaModel, ThinkingPreflight
from .thinking import ThinkingPolicy


class ProviderError(RuntimeError):
    """A local provider did not satisfy the benchmark protocol."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request: Any, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        raise ProviderError("Redirect del provider locale rifiutato")


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def _request(url: str, path: str, payload: dict[str, Any] | None = None, *, timeout: float = 30) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{url}{path}", data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            if response.status != 200:
                raise ProviderError(f"Endpoint locale {path}: HTTP {response.status}")
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ProviderError(f"Risposta troppo grande da {path}")
            result = json.loads(raw)
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"Endpoint locale {path}: HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise ProviderError(f"Endpoint locale {path} non disponibile: {type(exc).__name__}") from exc
    if not isinstance(result, dict):
        raise ProviderError(f"Risposta non valida da {path}")
    return result


def _reasoning_length(value: Any) -> int:
    if isinstance(value, str):
        return len(value)
    if isinstance(value, list):
        return sum(_reasoning_length(item) for item in value)
    if isinstance(value, dict):
        return sum(_reasoning_length(item) for item in value.values())
    return 0


class LocalProvider:
    explicit_load = True
    infer_capability_from_preflight = True
    version_source = "configuration"

    def __new__(cls, kind: str, *args: object, **kwargs: object) -> LocalProvider:
        if cls is LocalProvider:
            if kind == "lmstudio":
                from .lmstudio import LMStudioProvider

                cls = LMStudioProvider
            elif kind == "llama_cpp":
                from .llama_cpp import LlamaCppProvider

                cls = LlamaCppProvider
            else:
                raise ProviderError(f"Provider non supportato: {kind}")
        return super().__new__(cls)

    def __init__(self, kind: str, url: str, model_files: dict[str, Path] | None = None,
                 runtime_version: str | None = None, context_window: int = 32768):
        if kind not in {"lmstudio", "llama_cpp"}:
            raise ProviderError(f"Provider non supportato: {kind}")
        self.kind = kind
        self.url = url.rstrip("/")
        self.model_files = model_files or {}
        self.runtime_version = runtime_version
        self.context_window = context_window

    def list_models(self, *, with_digest: bool = False) -> list[OllamaModel]:
        raise NotImplementedError

    def _model_from_item(
        self, item: dict[str, Any], name: str, size: Any,
        details: dict[str, Any], *, with_digest: bool,
    ) -> OllamaModel:
        safe_size = size if isinstance(size, int) and not isinstance(size, bool) and size >= 0 else None
        capabilities = item.get("capabilities")
        reasoning = capabilities.get("reasoning") if isinstance(capabilities, dict) else None
        options = reasoning.get("allowed_options") if isinstance(reasoning, dict) else None
        thinking = (
            any(option in {"on", "low", "medium", "high"} for option in options)
            if isinstance(options, list) else None
        )
        if with_digest and name in self.model_files:
            details["digest_source"] = "configured_gguf_file"
        return OllamaModel(
            name, safe_size, self._digest(name) if with_digest else None, None, details,
            ("completion", "thinking") if thinking else ("completion",),
            thinking is not None, thinking,
        )

    def _digest(self, model: str) -> str | None:
        path = self.model_files.get(model)
        if path is None:
            return None
        if not path.is_file() or path.suffix.lower() != ".gguf":
            raise ProviderError(f"GGUF configurato non valido per {model}")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def fingerprint_model(self, model: OllamaModel) -> OllamaModel:
        digest = self._digest(model.name)
        details = dict(model.details)
        if digest is not None:
            details["digest_source"] = "configured_gguf_file"
        return replace(model, digest=digest, details=details)

    def inspect_model(self, model: OllamaModel, *, timeout: int = 30) -> OllamaModel:
        return model

    def version(self) -> str | None:
        # Neither local API promises a stable machine-readable server version.
        return self.runtime_version

    def preflight_thinking(self, model: OllamaModel, policy: ThinkingPolicy, *, timeout: int) -> ThinkingPreflight:
        started = time.monotonic()
        def outcome(status: str, observed: bool = False, chars: int = 0, tokens: int | None = None) -> ThinkingPreflight:
            return ThinkingPreflight(status, policy.requested, policy.reasoning_effort,
                                     model.thinking_capable, observed, chars, tokens,
                                     max(0, round((time.monotonic() - started) * 1000)))
        if policy.active and model.thinking_capable is False:
            return outcome("unsupported_capability")
        try:
            self.load(model.name, timeout=timeout)
            raw = _request(self.url, "/v1/chat/completions", {
                "model": model.name,
                "messages": [{"role": "user", "content": (
                    "Solve this constraint problem, then reply with only the final three-digit number: "
                    "its digits are distinct, their sum is 11, the tens digit is twice the units digit, "
                    "and the hundreds digit is three more than the units digit."
                )}],
                "stream": False, "temperature": 0, "max_tokens": 96,
                "reasoning_effort": policy.reasoning_effort,
            }, timeout=timeout)
        except ProviderError:
            return outcome("provider_error")
        choices = raw.get("choices")
        message = choices[0].get("message") if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            return outcome("invalid_response")
        chars = sum(_reasoning_length(message.get(key)) for key in ("reasoning", "reasoning_content", "reasoning_details", "thinking"))
        content = message.get("content")
        if isinstance(content, str):
            chars += sum(len(match.group(1)) for match in re.finditer(r"<think>(.*?)</think>", content, re.DOTALL | re.IGNORECASE))
        usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
        token_details = usage.get("completion_tokens_details") if isinstance(usage.get("completion_tokens_details"), dict) else {}
        raw_tokens = token_details.get("reasoning_tokens", usage.get("reasoning_tokens"))
        tokens = raw_tokens if isinstance(raw_tokens, int) and not isinstance(raw_tokens, bool) and raw_tokens >= 0 else None
        observed = chars > 0 or (tokens is not None and tokens > 0)
        if not policy.active and observed:
            return outcome("unexpected_thinking", True, chars, tokens)
        if policy.active and not observed:
            return outcome("thinking_not_observed", False, chars, tokens)
        return outcome("passed", observed, chars, tokens)

    def warmup(self, model: str, policy: ThinkingPolicy, *, timeout: int, context_window: int) -> dict[str, Any]:
        return _request(self.url, "/v1/chat/completions", {
            "model": model, "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "stream": False, "temperature": 0, "max_tokens": 8,
            "reasoning_effort": policy.reasoning_effort,
        }, timeout=timeout)

    def load(self, model: str, *, timeout: float) -> None:
        raise NotImplementedError

    def unload(self, model: str, *, timeout: float = 30) -> None:
        raise NotImplementedError
