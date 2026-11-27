"""Validate the single resident chat model reported by coli serve."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .model_bundle import ModelBundle


MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@-]{0,254}")


def valid_model_id(value: Any) -> bool:
    return (
        isinstance(value, str) and bool(MODEL_ID.fullmatch(value)) and "://" not in value
        and not re.match(r"^[A-Za-z]:/", value)
        and not any(part in {"", ".", ".."} for part in value.split("/"))
    )


def resident_chat_model(items: Any) -> dict[str, Any] | None:
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        return None
    model = items[0]
    capabilities = model.get("capabilities")
    if (model.get("object") != "model" or not valid_model_id(model.get("id"))
            or not isinstance(capabilities, list) or "chat" not in capabilities):
        return None
    return model


def resident_context(model: dict[str, Any]) -> int | None:
    """Colibrì reports the same window under two aliases; reject conflicting values."""
    values = [model[key] for key in ("context_length", "max_model_len") if key in model]
    if not values or not all(type(value) is int and value > 0 and value == values[0] for value in values):
        return None
    return values[0]


@dataclass(frozen=True)
class ColibriSettings:
    revision: str | None
    engine: str | None
    quantization: str | None
    kv_slots: int | None
    kv_persistence: str
    model_bundles: dict[str, ModelBundle]

    @classmethod
    def parse(cls, value: Any) -> ColibriSettings:
        if not isinstance(value, dict) or set(value) - {
            "revision", "engine", "quantization", "kv_slots", "kv_persistence", "model_bundles",
        }:
            raise ValueError("Impostazioni Colibrì non valide / Invalid Colibrì settings")
        revision = value.get("revision")
        if revision is not None and (not isinstance(revision, str) or not re.fullmatch(r"[a-f0-9]{40}", revision)):
            raise ValueError("Colibrì richiede una revisione Git completa / Colibrì requires a full Git revision")
        engine = value.get("engine")
        quantization = value.get("quantization")
        for name, token in (("engine", engine), ("quantization", quantization)):
            if token is not None and (not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", token)):
                raise ValueError(f"Colibrì {name}: etichetta non valida / invalid label")
        slots = value.get("kv_slots")
        if slots is not None and (type(slots) is not int or not 1 <= slots <= 16):
            raise ValueError("Colibrì kv_slots: 1..16")
        persistence = value.get("kv_persistence", "unknown")
        if persistence not in ("enabled", "disabled", "unknown"):
            raise ValueError("Colibrì kv_persistence: enabled, disabled, unknown")
        bundles = value.get("model_bundles", {})
        if not isinstance(bundles, dict) or not all(valid_model_id(model) for model in bundles):
            raise ValueError("Colibrì model_bundles non valido / Invalid model_bundles")
        return cls(revision, engine, quantization, slots, persistence,
                   {model: ModelBundle.parse(bundle) for model, bundle in bundles.items()})

    def to_manifest(self) -> dict[str, Any]:
        return {
            "revision": self.revision, "engine": self.engine,
            "quantization": self.quantization, "kv_slots": self.kv_slots,
            "kv_persistence": self.kv_persistence, "context_compaction": "off",
            "metadata_source": "configuration",
        }
