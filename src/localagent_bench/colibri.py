"""Resident Colibrì adapter behind the bounded host gateway."""
from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

from . import providers as shared
from .colibri_protocol import ColibriSettings, resident_chat_model, resident_context
from .model_bundle import ModelBundleError
from .ollama import OllamaModel, ThinkingPreflight
from .provider_checks import verify_tool_call
from .providers import ContextWindowMismatch, LocalProvider, ProviderError
from .thinking import ThinkingPolicy


class ColibriProvider(LocalProvider):
    lifecycle_mode = "preloaded_manual"
    infer_capability_from_preflight = False

    def __init__(self, url: str, runtime_version: str | None, context_window: int,
                 settings: ColibriSettings):
        super().__init__("colibri", url, runtime_version=runtime_version, context_window=context_window)
        self.settings = settings
        self._bundle_identity: dict[str, dict[str, tuple[int, ...]]] = {}

    def _resident(self, timeout: float) -> OllamaModel:
        model = resident_chat_model(shared._request(self.url, "/v1/models", timeout=timeout).get("data"))
        if model is None:
            raise ProviderError("Colibrì: atteso un modello chat residente / expected one resident chat model")
        return self._model_from_item(
            model, model["id"], model.get("size_bytes"),
            {"context_length": resident_context(model), "context_length_source": "api",
             "lifecycle_mode": self.lifecycle_mode},
            with_digest=False,
        )

    def list_models(self, *, with_digest: bool = False) -> list[OllamaModel]:
        model = self._resident(30)
        return [self.fingerprint_model(model) if with_digest else model]

    def fingerprint_model(self, model: OllamaModel) -> OllamaModel:
        bundle = self.settings.model_bundles.get(model.name)
        if bundle is None:
            return model
        try:
            manifest, identity = bundle.fingerprint()
        except ModelBundleError as exc:
            raise ProviderError(str(exc)) from None
        self._bundle_identity[model.name] = identity
        return replace(model, digest=manifest["fingerprint_sha256"],
                       details={**model.details, "model_bundle": manifest})

    def verify_model_bundle(self, model: str) -> None:
        identity = self._bundle_identity.get(model)
        if identity is not None:
            self.settings.model_bundles[model].verify(identity)

    def load(self, model: str, *, timeout: float) -> dict[str, str]:
        self.verify_model_bundle(model)
        resident = self._resident(timeout)
        if resident.name != model:
            raise ProviderError("Colibrì: modello non residente / model not resident")
        context = resident.details.get("context_length")
        if context is None or context < self.context_window:
            raise ContextWindowMismatch(
                "Colibrì: contesto residente insufficiente o non verificabile / insufficient or unverifiable context"
            )
        return {"status": "resident_verified", "mode": self.lifecycle_mode}

    def unload(self, model: str, *, timeout: float = 30) -> dict[str, str]:
        return {"status": "not_supported", "mode": self.lifecycle_mode}

    def preflight_thinking(
        self, model: OllamaModel, policy: ThinkingPolicy, *, timeout: int,
    ) -> ThinkingPreflight:
        started = time.monotonic()

        def failure(status: str) -> ThinkingPreflight:
            return ThinkingPreflight(status, policy.requested, policy.reasoning_effort,
                                     model.thinking_capable, False, 0, None,
                                     round((time.monotonic() - started) * 1000))

        # The observed presence of reasoning alone cannot prove the effective
        # level on engines that map OpenAI requests to a smaller native set.
        if policy.active:
            return failure("thinking_level_unverified")
        try:
            result = super().preflight_thinking(model, policy, timeout=timeout)
        except ContextWindowMismatch:
            return failure("context_window_mismatch")
        except ModelBundleError:
            return failure("provider_model_bundle_changed")
        if not result.passed:
            return result
        return verify_tool_call(self.url, model, policy, result, started=started, timeout=timeout, streamed=True)

    def warmup(self, model: str, policy: ThinkingPolicy, *, timeout: int, context_window: int) -> dict[str, Any]:
        result = super().warmup(model, policy, timeout=timeout, context_window=context_window)
        choices = result.get("choices")
        message = choices[0].get("message") if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
        if not isinstance(message, dict) or shared.observed_reasoning(message, result.get("usage"))[0]:
            raise ProviderError("Colibrì: risposta warmup o thinking non valido / invalid warmup response or thinking")
        return result
