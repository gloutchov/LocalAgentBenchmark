"""Preloaded Unsloth GGUF models behind the trusted authenticated host gateway.

The gateway verifies an inference-only API key before forwarding generation.
No API key, model-management request or provider-hosted tool reaches this adapter.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import replace
from typing import Any

from . import providers as shared
from .ollama import OllamaModel, ThinkingPreflight
from .providers import LocalProvider, ProviderError
from .thinking import ThinkingPolicy


class UnslothProvider(LocalProvider):
    """A resident model is verified, never silently loaded or unloaded."""

    explicit_load = True
    lifecycle_mode = "preloaded_manual"
    policy_source = "inference_only_key_probe"

    def _policy(self, *, timeout: float) -> None:
        # This route belongs to our host gateway, not to the Unsloth API. The
        # gateway proves the key's scope using the real authenticated API.
        policy = shared._request(self.url, "/benchmark/unsloth-policy", timeout=timeout)
        if policy.get("inference_only") is not True:
            raise ProviderError(
                "Unsloth: policy inference-only non verificata / inference-only policy unverified"
            )

    @staticmethod
    def _model_id(value: Any) -> bool:
        return (
            isinstance(value, str)
            and 0 < len(value) <= 256
            and value == value.strip()
            and not any(ord(char) < 32 or ord(char) == 127 for char in value)
            and not value.startswith("/")
            and "\\" not in value
            and "://" not in value
            and not re.match(r"^[A-Za-z]:/", value)
            and not any(part in {".", ".."} for part in value.split("/"))
        )

    def _models(self, *, timeout: float, with_digest: bool = False) -> list[OllamaModel]:
        started = time.monotonic()
        self._policy(timeout=timeout)
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            raise ProviderError("Unsloth: verifica modello scaduta / model verification timed out")
        items = shared._request(self.url, "/v1/models", timeout=remaining).get("data")
        if not isinstance(items, list):
            raise ProviderError("Unsloth: elenco modelli non valido / invalid model list")
        models: list[OllamaModel] = []
        names: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("id")
            if (
                not self._model_id(name)
                or item.get("owned_by") != "unsloth-studio"
                or item.get("loaded") is not True
                or item.get("task") not in (None, "text-generation")
            ):
                continue
            if name in names:
                raise ProviderError("Unsloth: ID modello duplicato / duplicate model ID")
            names.add(name)
            quant = item.get("quant")
            api_gguf = (
                isinstance(quant, str) and 0 < len(quant) <= 128
                and quant == quant.strip()
                and not any(ord(char) < 32 or ord(char) == 127 for char in quant)
            )
            mapped = self.model_files.get(name)
            configured_gguf = mapped is not None and mapped.suffix.lower() == ".gguf"
            if not api_gguf and not configured_gguf:
                continue
            details: dict[str, Any] = {
                "format": "gguf",
                "format_source": "api_quant" if api_gguf else "configured_gguf_file",
                "lifecycle_mode": self.lifecycle_mode,
                "server_tools_policy": self.policy_source,
            }
            if api_gguf:
                details["quantization_level"] = quant
            context = item.get("context_length")
            if isinstance(context, int) and not isinstance(context, bool) and context > 0:
                details["context_length"] = context
            models.append(self._model_from_item(
                item, name, item.get("size_bytes"), details, with_digest=with_digest,
            ))
        return sorted(models, key=lambda model: model.name.casefold())

    def list_models(self, *, with_digest: bool = False) -> list[OllamaModel]:
        return self._models(timeout=30, with_digest=with_digest)

    def inspect_model(self, model: OllamaModel, *, timeout: int = 30) -> OllamaModel:
        current = next((item for item in self._models(timeout=timeout) if item.name == model.name), None)
        if current is None:
            raise ProviderError(
                "Unsloth: precaricare manualmente il GGUF locale / manually preload the local GGUF"
            )
        return replace(
            model, details={**model.details, **current.details}, capabilities=current.capabilities,
            capabilities_known=current.capabilities_known, thinking_capable=current.thinking_capable,
        )

    def load(self, model: str, *, timeout: float) -> dict[str, str]:
        if not any(item.name == model for item in self._models(timeout=timeout)):
            raise ProviderError(
                "Unsloth: modello non residente; caricarlo manualmente / model not resident; load manually"
            )
        return {"status": "resident_verified", "mode": self.lifecycle_mode}

    def unload(self, model: str, *, timeout: float = 30) -> dict[str, str]:
        # An inference-only credential cannot mutate residency. Returning an
        # explicit unavailable state lets orchestration record honest cleanup.
        return {"status": "not_supported", "mode": self.lifecycle_mode}

    def preflight_thinking(
        self, model: OllamaModel, policy: ThinkingPolicy, *, timeout: int
    ) -> ThinkingPreflight:
        started = time.monotonic()
        result = super().preflight_thinking(model, policy, timeout=timeout)
        if not result.passed:
            return result
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            return replace(result, status="tool_calling_not_verified")
        # Only inert client tools are offered. Their returned arguments are
        # validated as JSON; nothing in a model answer is executed.
        try:
            response = shared._request(self.url, "/v1/chat/completions", {
                "model": model.name,
                "messages": [{"role": "user", "content": "Call benchmark_probe with value 7."}],
                "tools": [{"type": "function", "function": {
                    "name": "benchmark_probe", "description": "Return a synthetic integer; no execution.",
                    "parameters": {"type": "object", "properties": {"value": {"type": "integer"}},
                                   "required": ["value"], "additionalProperties": False},
                }}],
                "tool_choice": {"type": "function", "function": {"name": "benchmark_probe"}},
                "temperature": 0, "max_tokens": 96, "stream": False,
                "reasoning_effort": policy.reasoning_effort,
            }, timeout=remaining)
        except ProviderError:
            return replace(result, status="tool_calling_not_verified")
        choices = response.get("choices")
        message = choices[0].get("message") if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            return replace(result, status="tool_calling_not_verified")
        reasoning_chars = sum(shared._reasoning_length(message.get(key)) for key in (
            "reasoning", "reasoning_content", "reasoning_details", "thinking",
        ))
        content = message.get("content")
        if isinstance(content, str):
            reasoning_chars += sum(len(match.group(1)) for match in re.finditer(
                r"<think>(.*?)(?:</think>|$)", content, re.S | re.I,
            ))
            if re.search(r"<think>", content, re.I):
                reasoning_chars = max(1, reasoning_chars)
        usage = response.get("usage")
        token_details = usage.get("completion_tokens_details") if isinstance(usage, dict) else None
        reasoning_tokens = token_details.get("reasoning_tokens") if isinstance(token_details, dict) else None
        if reasoning_tokens is None and isinstance(usage, dict):
            reasoning_tokens = usage.get("reasoning_tokens")
        if type(reasoning_tokens) is not int or reasoning_tokens < 0:
            reasoning_tokens = None
        observed = reasoning_chars > 0 or (
            isinstance(reasoning_tokens, int) and not isinstance(reasoning_tokens, bool) and reasoning_tokens > 0
        )
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

    def warmup(self, model: str, policy: ThinkingPolicy, *, timeout: int, context_window: int) -> dict[str, Any]:
        started = time.monotonic()
        self.load(model, timeout=timeout)
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            raise ProviderError("Unsloth: warmup scaduto / warmup timed out")
        result = super().warmup(model, policy, timeout=remaining, context_window=context_window)
        # Preserve the shared response fields consumed by existing orchestration.
        return {**result, "lifecycle_mode": self.lifecycle_mode}
