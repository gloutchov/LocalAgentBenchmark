"""Configuration loading and validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .case_sdk import (
    CaseSpec,
    CaseValidationError,
    discover_case_manifests,
    resolve_cases_directory,
    safe_case_id,
)
from .sandbox import SANDBOX_MODES
from .thinking import THINKING_LEVELS


class ConfigError(ValueError):
    """Raised when benchmark configuration is invalid."""


@dataclass(frozen=True)
class Defaults:
    timeout_seconds: int
    repetitions: int
    thinking: str
    thinking_preflight_timeout_seconds: int
    pi_contract_timeout_seconds: int
    http_idle_timeout_ms: int
    agent_max_retries: int
    provider_max_retries: int
    warmup: bool
    keep_alive: str
    context_window: int
    max_tokens: int
    temperature: float
    sandbox: str


@dataclass(frozen=True)
class DashboardSettings:
    assets_directory: Path
    results_directory: Path
    snapshot_source: Path
    host: str
    port: int
    open_browser: bool


@dataclass(frozen=True)
class GuidedSettings:
    profiles: tuple[str, str, str]
    promotion_limits: tuple[int, int]
    preferences_file: Path


@dataclass(frozen=True)
class BenchmarkConfig:
    root: Path
    ollama_url: str
    pi_command: tuple[str, ...]
    models: str | tuple[str, ...]
    defaults: Defaults
    profiles: dict[str, tuple[str, ...]]
    cases: dict[str, CaseSpec]
    cases_directory: Path
    dashboard: DashboardSettings
    guided: GuidedSettings | None


def _require(mapping: dict[str, Any], key: str, expected: type) -> Any:
    value = mapping.get(key)
    if not isinstance(value, expected):
        raise ConfigError(f"'{key}' deve essere di tipo {expected.__name__}")
    return value


def _repository_path(root: Path, value: Any, *, key: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"'{key}' deve essere una stringa relativa non vuota")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ConfigError(f"'{key}' deve essere un path relativo dentro il repository")
    resolved = (root / candidate).resolve()
    if resolved != root and root not in resolved.parents:
        raise ConfigError(f"'{key}' deve restare dentro il repository")
    return resolved


def load_config(path: Path) -> BenchmarkConfig:
    path = path.resolve()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Impossibile leggere {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("La radice di benchmark.json deve essere un oggetto")
    if raw.get("version") != 1:
        raise ConfigError("Versione configurazione non supportata (attesa: 1)")

    root = path.parent
    ollama = _require(raw, "ollama", dict)
    ollama_url = _require(ollama, "url", str).rstrip("/")
    parsed_url = urlparse(ollama_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ConfigError("ollama.url deve essere un URL HTTP(S) valido")

    pi = _require(raw, "pi", dict)
    pi_command_raw = _require(pi, "command", list)
    if not pi_command_raw or not all(isinstance(item, str) and item for item in pi_command_raw):
        raise ConfigError("pi.command deve contenere almeno una stringa non vuota")

    defaults_raw = _require(raw, "defaults", dict)
    defaults = Defaults(
        timeout_seconds=int(defaults_raw.get("timeout_seconds", 1200)),
        repetitions=int(defaults_raw.get("repetitions", 1)),
        thinking=str(defaults_raw.get("thinking", "off")),
        thinking_preflight_timeout_seconds=int(
            defaults_raw.get("thinking_preflight_timeout_seconds", 300)
        ),
        pi_contract_timeout_seconds=int(defaults_raw.get("pi_contract_timeout_seconds", 30)),
        http_idle_timeout_ms=int(defaults_raw.get("http_idle_timeout_ms", 0)),
        agent_max_retries=int(defaults_raw.get("agent_max_retries", 0)),
        provider_max_retries=int(defaults_raw.get("provider_max_retries", 0)),
        warmup=bool(defaults_raw.get("warmup", True)),
        keep_alive=str(defaults_raw.get("keep_alive", "15m")),
        context_window=int(defaults_raw.get("context_window", 32768)),
        max_tokens=int(defaults_raw.get("max_tokens", 8192)),
        temperature=float(defaults_raw.get("temperature", 0)),
        sandbox=str(defaults_raw.get("sandbox", "audit")),
    )
    if defaults.timeout_seconds < 10 or defaults.repetitions < 1:
        raise ConfigError("timeout_seconds deve essere >= 10 e repetitions >= 1")
    if defaults.thinking not in THINKING_LEVELS:
        raise ConfigError("Livello thinking non valido")
    if defaults.thinking_preflight_timeout_seconds < 10:
        raise ConfigError("thinking_preflight_timeout_seconds deve essere >= 10")
    if not 10 <= defaults.pi_contract_timeout_seconds <= 300:
        raise ConfigError("pi_contract_timeout_seconds deve essere tra 10 e 300")
    if (
        defaults.http_idle_timeout_ms < 0
        or defaults.agent_max_retries < 0
        or defaults.provider_max_retries < 0
    ):
        raise ConfigError("Timeout e retry thinking devono essere >= 0")
    if defaults.context_window < 4096 or defaults.max_tokens < 256:
        raise ConfigError("context_window o max_tokens troppo piccoli")
    if defaults.sandbox not in SANDBOX_MODES:
        raise ConfigError(f"defaults.sandbox deve essere uno tra: {', '.join(SANDBOX_MODES)}")

    models_raw = raw.get("models", "installed")
    if models_raw == "installed":
        models: str | tuple[str, ...] = "installed"
    elif isinstance(models_raw, list) and models_raw and all(isinstance(m, str) and m for m in models_raw):
        models = tuple(models_raw)
    else:
        raise ConfigError("models deve essere 'installed' o una lista non vuota")

    cases_raw = raw.get("cases")
    if isinstance(cases_raw, dict):
        unknown = sorted(set(cases_raw) - {"directory"})
        if unknown:
            raise ConfigError(f"Campi sconosciuti in cases: {', '.join(unknown)}")
        try:
            cases_directory = resolve_cases_directory(root, cases_raw.get("directory", "cases"))
            cases = discover_case_manifests(cases_directory)
        except CaseValidationError as exc:
            raise ConfigError(str(exc)) from exc
    elif isinstance(cases_raw, list):
        # Compatibility for pre-0.4 configurations. New cases should use case.json discovery.
        cases_directory = (root / "cases").resolve()
        cases = {}
        for item in cases_raw:
            if not isinstance(item, dict):
                raise ConfigError("Ogni caso legacy deve essere un oggetto")
            case_id = _require(item, "id", str)
            if not safe_case_id(case_id) or case_id in cases:
                raise ConfigError(f"ID caso non valido o duplicato: {case_id!r}")
            directory = (cases_directory / case_id).resolve()
            if directory.parent != cases_directory:
                raise ConfigError(f"Il caso esce da cases/: {case_id}")
            title = _require(item, "title", str)
            spec = CaseSpec(
                id=case_id,
                title=title,
                title_en=str(item.get("title_en", title)),
                category=_require(item, "category", str),
                weight=float(item.get("weight", 1)),
                directory=directory,
                prompt_path=directory / "prompt.md",
                fixture_path=directory / "fixture",
                grader_path=directory / "grader.py",
            )
            if spec.weight <= 0:
                raise ConfigError(f"Peso non valido per {case_id}")
            for required_path in (spec.prompt_path, spec.fixture_path, spec.grader_path):
                if not required_path.exists():
                    raise ConfigError(f"File del caso mancante: {required_path}")
            cases[case_id] = spec
    else:
        raise ConfigError("cases deve essere un oggetto di discovery o una lista legacy")

    profiles_raw = _require(raw, "profiles", dict)
    profiles: dict[str, tuple[str, ...]] = {}
    for name, ids in profiles_raw.items():
        if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids):
            raise ConfigError(f"Profilo non valido: {name}")
        unknown = set(ids) - set(cases)
        if unknown:
            raise ConfigError(f"Casi sconosciuti nel profilo {name}: {', '.join(sorted(unknown))}")
        profiles[name] = tuple(ids)
    if "standard" not in profiles:
        raise ConfigError("È richiesto il profilo 'standard'")

    dashboard_raw = raw.get("dashboard", {})
    if not isinstance(dashboard_raw, dict):
        raise ConfigError("'dashboard' deve essere di tipo dict")
    unknown_dashboard = sorted(
        set(dashboard_raw)
        - {"assets_directory", "results_directory", "snapshot_source", "host", "port", "open_browser"}
    )
    if unknown_dashboard:
        raise ConfigError(f"Campi sconosciuti in dashboard: {', '.join(unknown_dashboard)}")
    dashboard_host = dashboard_raw.get("host", "127.0.0.1")
    if dashboard_host != "127.0.0.1":
        raise ConfigError("dashboard.host deve essere 127.0.0.1")
    dashboard_port = dashboard_raw.get("port", 0)
    if isinstance(dashboard_port, bool) or not isinstance(dashboard_port, int) or not 0 <= dashboard_port <= 65535:
        raise ConfigError("dashboard.port deve essere un intero tra 0 e 65535")
    dashboard_open_browser = dashboard_raw.get("open_browser", True)
    if not isinstance(dashboard_open_browser, bool):
        raise ConfigError("dashboard.open_browser deve essere booleano")
    dashboard = DashboardSettings(
        assets_directory=_repository_path(
            root,
            dashboard_raw.get("assets_directory", "dashboard"),
            key="dashboard.assets_directory",
        ),
        results_directory=_repository_path(
            root,
            dashboard_raw.get("results_directory", "results"),
            key="dashboard.results_directory",
        ),
        snapshot_source=_repository_path(
            root,
            dashboard_raw.get("snapshot_source", "cases/results_dashboard/fixture/dashboard-data.json"),
            key="dashboard.snapshot_source",
        ),
        host=dashboard_host,
        port=dashboard_port,
        open_browser=dashboard_open_browser,
    )

    guided: GuidedSettings | None = None
    if "guided" in raw:
        guided_raw = raw["guided"]
        if not isinstance(guided_raw, dict):
            raise ConfigError("'guided' deve essere di tipo dict")
        unknown_guided = sorted(
            set(guided_raw) - {"profiles", "promotion_limits", "preferences_file"}
        )
        if unknown_guided:
            raise ConfigError(f"Campi sconosciuti in guided: {', '.join(unknown_guided)}")
        guided_profiles_raw = guided_raw.get("profiles", ["smoke", "standard", "full"])
        if guided_profiles_raw != ["smoke", "standard", "full"]:
            raise ConfigError("guided.profiles deve essere esattamente: smoke, standard, full")
        missing_guided_profiles = [name for name in guided_profiles_raw if name not in profiles]
        if missing_guided_profiles:
            raise ConfigError(
                "Profili guidati mancanti: " + ", ".join(missing_guided_profiles)
            )
        for profile_name in guided_profiles_raw:
            if "results_dashboard" in profiles[profile_name]:
                raise ConfigError(
                    f"Il profilo guidato {profile_name} non può includere results_dashboard"
                )
        promotion_limits_raw = guided_raw.get("promotion_limits", [4, 2])
        if (
            not isinstance(promotion_limits_raw, list)
            or len(promotion_limits_raw) != 2
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 1
                for value in promotion_limits_raw
            )
        ):
            raise ConfigError("guided.promotion_limits deve contenere due interi positivi")
        if promotion_limits_raw[1] > promotion_limits_raw[0]:
            raise ConfigError(
                "guided.promotion_limits deve essere decrescente (per esempio 4, 2)"
            )
        guided = GuidedSettings(
            profiles=tuple(guided_profiles_raw),  # type: ignore[arg-type]
            promotion_limits=tuple(promotion_limits_raw),  # type: ignore[arg-type]
            preferences_file=_repository_path(
                root,
                guided_raw.get(
                    "preferences_file", ".localagent-benchmark/guided-preferences.json"
                ),
                key="guided.preferences_file",
            ),
        )

    return BenchmarkConfig(
        root=root,
        ollama_url=ollama_url,
        pi_command=tuple(pi_command_raw),
        models=models,
        defaults=defaults,
        profiles=profiles,
        cases=cases,
        cases_directory=cases_directory,
        dashboard=dashboard,
        guided=guided,
    )
