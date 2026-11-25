"""Host-only authenticated provider lifetime, shared by CLI and guided phases."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, replace
from typing import Iterator

from .config import BenchmarkConfig
from .provider_auth import resolve_credential
from .provider_gateway import ProviderGateway


@contextmanager
def provider_session(config: BenchmarkConfig) -> Iterator[BenchmarkConfig]:
    if config.provider_kind != "unsloth":
        yield config
        return
    # The original config and manifests hold references/status only. Pi receives
    # the gateway URL and its usual dummy key, never the real credential.
    secret = resolve_credential(config.provider_auth_ref or "", prompt=config.provider_auth_prompt)
    gguf_ids = tuple(name for name, path in (config.model_files or {}).items() if path.suffix.lower() == ".gguf")
    with ProviderGateway(config.ollama_url, secret, gguf_model_ids=gguf_ids,
                         **asdict(config.provider_transport)) as gateway:
        yield replace(config, ollama_url=gateway.url, provider_origin_url=config.ollama_url)


def provider_origin(config: BenchmarkConfig) -> str:
    return config.provider_origin_url or config.ollama_url
