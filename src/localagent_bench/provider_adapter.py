"""Common provider operations consumed by the benchmark runner."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from .ollama import OllamaModel, OllamaProvider, ThinkingPreflight
from .providers import LocalProvider
from .thinking import ThinkingPolicy

if TYPE_CHECKING:
    from .config import BenchmarkConfig


class ProviderAdapter(Protocol):
    kind: str
    explicit_load: bool
    infer_capability_from_preflight: bool
    version_source: str

    def list_models(self) -> list[OllamaModel]: ...

    def fingerprint_model(self, model: OllamaModel) -> OllamaModel: ...

    def inspect_model(self, model: OllamaModel, *, timeout: int = 30) -> OllamaModel: ...

    def version(self) -> str | None: ...

    def load(self, model: str, *, timeout: float) -> None: ...

    def unload(self, model: str, *, timeout: float = 30) -> None: ...

    def preflight_thinking(
        self, model: OllamaModel, policy: ThinkingPolicy, *, timeout: int
    ) -> ThinkingPreflight: ...

    def warmup(
        self, model: str, policy: ThinkingPolicy, *, timeout: int, context_window: int
    ) -> dict[str, Any]: ...


def create_provider(config: BenchmarkConfig) -> ProviderAdapter:
    if config.provider_kind == "ollama":
        return OllamaProvider(config.ollama_url, config.defaults.keep_alive)
    return LocalProvider(
        config.provider_kind,
        config.ollama_url,
        config.model_files,
        config.provider_version,
        config.defaults.context_window,
    )
