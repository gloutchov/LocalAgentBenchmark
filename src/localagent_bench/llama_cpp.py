"""llama.cpp router model discovery and lifecycle adapter."""

from __future__ import annotations

import time

from . import providers as shared
from .ollama import OllamaModel
from .providers import LocalProvider, ProviderError


class LlamaCppProvider(LocalProvider):
    def list_models(self, *, with_digest: bool = False) -> list[OllamaModel]:
        path = "/models"
        items = shared._request(self.url, path).get("data")
        if not isinstance(items, list):
            raise ProviderError(f"Elenco modelli non valido da {path}")
        models: list[OllamaModel] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("id")
            if not isinstance(name, str) or not name or len(name) > 256:
                continue
            models.append(self._model_from_item(
                item, name, item.get("size"), {}, with_digest=with_digest,
            ))
        return sorted(models, key=lambda model: model.name.casefold())

    def load(self, model: str, *, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        result = shared._request(self.url, "/models/load", {"model": model}, timeout=timeout)
        if result.get("success") is not True:
            raise ProviderError("llama-server non ha confermato il caricamento del modello")
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProviderError("llama-server: caricamento del modello scaduto")
            models = shared._request(self.url, "/models", timeout=min(5.0, remaining)).get("data")
            if not isinstance(models, list):
                raise ProviderError("llama-server: stato dei modelli non valido")
            entry = next((item for item in models if isinstance(item, dict) and item.get("id") == model), None)
            status = entry.get("status") if entry is not None else None
            value = status.get("value") if isinstance(status, dict) else None
            if isinstance(status, dict) and status.get("failed") is True:
                raise ProviderError("llama-server: il processo del modello è terminato durante il caricamento")
            if value == "loaded":
                return
            if value not in {"loading", "unloaded"}:
                raise ProviderError("llama-server: caricamento del modello non riuscito")
            time.sleep(min(0.25, max(0, deadline - time.monotonic())))

    def unload(self, model: str, *, timeout: float = 30) -> None:
        deadline = time.monotonic() + timeout
        result = shared._request(self.url, "/models/unload", {"model": model}, timeout=timeout)
        if result.get("success") is not True:
            raise ProviderError("llama-server non ha confermato lo scaricamento del modello")
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProviderError("llama-server: scaricamento del modello scaduto")
            models = shared._request(self.url, "/models", timeout=min(5.0, remaining)).get("data")
            if not isinstance(models, list):
                raise ProviderError("llama-server: stato dei modelli non valido")
            entry = next((item for item in models if isinstance(item, dict) and item.get("id") == model), None)
            status = entry.get("status") if entry is not None else None
            value = status.get("value") if isinstance(status, dict) else None
            if value == "unloaded":
                return
            if isinstance(status, dict) and status.get("failed") is True:
                raise ProviderError("llama-server: il processo del modello è terminato durante lo scaricamento")
            if value not in {"loading", "loaded", "sleeping", "unloading"}:
                raise ProviderError("llama-server: scaricamento del modello non riuscito")
            time.sleep(min(0.25, max(0, deadline - time.monotonic())))
