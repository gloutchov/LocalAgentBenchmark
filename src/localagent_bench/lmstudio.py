"""LM Studio model discovery and lifecycle adapter."""

from __future__ import annotations

from typing import Any

from . import providers as shared
from .ollama import OllamaModel
from .providers import LocalProvider, ProviderError


class LMStudioProvider(LocalProvider):
    def list_models(self, *, with_digest: bool = False) -> list[OllamaModel]:
        path = "/api/v1/models"
        items = shared._request(self.url, path).get("models")
        if not isinstance(items, list):
            raise ProviderError(f"Elenco modelli non valido da {path}")
        models: list[OllamaModel] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("key")
            if not isinstance(name, str) or not name or len(name) > 256 or item.get("type") != "llm":
                continue
            details: dict[str, Any] = {}
            for source, dest in (("format", "format"), ("architecture", "family")):
                value = item.get(source)
                if isinstance(value, str) and len(value) <= 128:
                    details[dest] = value
            quant = item.get("quantization")
            if isinstance(quant, dict) and isinstance(quant.get("name"), str):
                details["quantization_level"] = quant["name"][:128]
            models.append(self._model_from_item(
                item, name, item.get("size_bytes"), details, with_digest=with_digest,
            ))
        return sorted(models, key=lambda model: model.name.casefold())

    def load(self, model: str, *, timeout: float) -> None:
        result = shared._request(
            self.url, "/api/v1/models/load",
            {"model": model, "context_length": self.context_window}, timeout=timeout,
        )
        if result.get("status") != "loaded":
            raise ProviderError("LM Studio non ha confermato il caricamento del modello")

    def unload(self, model: str, *, timeout: float = 30) -> None:
        models = shared._request(self.url, "/api/v1/models").get("models", [])
        for item in models if isinstance(models, list) else []:
            if isinstance(item, dict) and item.get("key") == model:
                for instance in item.get("loaded_instances", []):
                    if isinstance(instance, dict) and isinstance(instance.get("id"), str):
                        shared._request(
                            self.url, "/api/v1/models/unload", {"instance_id": instance["id"]},
                        )
