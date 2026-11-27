"""Preloaded Unsloth GGUF models behind the trusted authenticated host gateway.

The gateway verifies an inference-only API key before forwarding generation.
No API key, model-management request or provider-hosted tool reaches this adapter.
"""

from __future__ import annotations

import re
import time
from dataclasses import replace
from typing import Any

from . import providers as shared
from .ollama import OllamaModel, ThinkingPreflight
from .provider_checks import verify_tool_call
from .providers import ContextWindowMismatch, LocalProvider, ProviderError
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
                details["context_length_source"] = "api"
            else:
                details["context_length"] = None
                details["context_length_source"] = "unknown"
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
        current = next((item for item in self._models(timeout=timeout) if item.name == model), None)
        if current is None:
            raise ProviderError(
                "Unsloth: modello non residente; caricarlo manualmente / model not resident; load manually"
            )
        context = current.details.get("context_length")
        if type(context) is int and context < self.context_window:
            raise ContextWindowMismatch(
                f"context_window_mismatch: Unsloth contesto residente {context}, richiesto {self.context_window} / "
                "resident context is smaller than the requested context window"
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
        try:
            result = super().preflight_thinking(model, policy, timeout=timeout)
        except ContextWindowMismatch:
            return ThinkingPreflight(
                "context_window_mismatch", policy.requested, policy.reasoning_effort,
                model.thinking_capable, False, 0, None,
                max(0, round((time.monotonic() - started) * 1000)),
            )
        if not result.passed:
            return result
        return verify_tool_call(self.url, model, policy, result, started=started, timeout=timeout)

    def warmup(self, model: str, policy: ThinkingPolicy, *, timeout: int, context_window: int) -> dict[str, Any]:
        started = time.monotonic()
        self.load(model, timeout=timeout)
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            raise ProviderError("Unsloth: warmup scaduto / warmup timed out")
        result = super().warmup(model, policy, timeout=remaining, context_window=context_window)
        # Preserve the shared response fields consumed by existing orchestration.
        return {**result, "lifecycle_mode": self.lifecycle_mode}
