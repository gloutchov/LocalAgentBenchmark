"""Core orchestration for the non-terminal benchmark funnel."""

from __future__ import annotations

import json
import math
import os
import random
import re
import secrets
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from . import __version__
from .config import BenchmarkConfig
from .dashboard_data import DashboardDataError, build_dashboard_data
from .guided_process import (
    GuidedProcessError,
    ManagedProcessRunner,
    ProcessResult,
    python_executable,
    start_detached,
)
from .runner import doctor
from .sandbox import SANDBOX_MODES, SandboxError, select_sandbox
from .thinking import THINKING_LEVELS


MANIFEST_NAME = "guided-run.json"
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,254}$")
TASK_PATTERN = re.compile(
    r"^\[(?P<current>\d+)/(?P<total>\d+)\] (?P<model>.+?) · (?P<case>.+?) · ripetizione (?P<repeat>\d+)$"
)


class GuidedError(RuntimeError):
    """A user-actionable guided-flow error with a stable category."""

    def __init__(
        self, code: str, message: str, *, context: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = context


class GuidedCancelled(GuidedError):
    def __init__(self) -> None:
        super().__init__("cancelled", "Percorso annullato dall'utente")


@dataclass(frozen=True)
class PhaseOutcome:
    profile: str
    run_directory: Path
    leaderboard: tuple[dict[str, Any], ...]
    promoted: tuple[str, ...]
    exclusions: tuple[dict[str, str], ...]


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def validate_model_name(name: str) -> str:
    if not isinstance(name, str) or not MODEL_PATTERN.fullmatch(name):
        raise GuidedError("invalid_model", f"Nome modello non sicuro o non supportato: {name!r}")
    return name


def _read_object(path: Path, *, root: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not _inside(resolved, root.resolve()) or path.is_symlink() or not path.is_file():
        raise GuidedError("invalid_artifact", f"Artefatto mancante o fuori progetto: {path.name}")
    if path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise GuidedError("invalid_artifact", f"Artefatto troppo grande: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GuidedError("invalid_artifact", f"Artefatto JSON non valido: {path.name}") from exc
    if not isinstance(value, dict):
        raise GuidedError("invalid_artifact", f"Artefatto JSON non valido: {path.name}")
    return value


def _public_leaderboard(rows: Any, expected_models: set[str]) -> tuple[dict[str, Any], ...]:
    if not isinstance(rows, list):
        raise GuidedError("invalid_report", "Leaderboard ufficiale mancante")
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    numeric_fields = (
        "overall_score",
        "quality_score",
        "completion_rate",
        "median_duration_seconds",
    )
    for raw in rows:
        if not isinstance(raw, dict):
            raise GuidedError("invalid_report", "Riga leaderboard non valida")
        model = raw.get("model")
        if not isinstance(model, str) or model not in expected_models or model in seen:
            raise GuidedError("invalid_report", "Modello leaderboard inatteso o duplicato")
        clean: dict[str, Any] = {"model": model}
        for field in numeric_fields:
            value = raw.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise GuidedError("invalid_report", f"Valore leaderboard non valido: {field}")
            clean[field] = value
        seen.add(model)
        output.append(clean)
    return tuple(output)


def select_promoted(
    leaderboard: tuple[dict[str, Any], ...], limit: int
) -> tuple[str, ...]:
    """Preserve the official report order instead of duplicating its tie-break rules."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise GuidedError("invalid_limit", "Limite di promozione non valido")
    return tuple(str(row["model"]) for row in leaderboard[:limit])


def evaluate_phase(
    run_directory: Path,
    *,
    root: Path,
    expected_profile: str,
    expected_models: list[str],
    promotion_limit: int | None,
    process_returncode: int,
) -> PhaseOutcome:
    """Validate one completed phase and consume its official leaderboard order."""
    resolved_run = run_directory.resolve()
    if not _inside(resolved_run, root.resolve()) or run_directory.is_symlink():
        raise GuidedError("unsafe_output", "La directory del run deve restare nel progetto")
    manifest = _read_object(run_directory / "run.json", root=root)
    report = _read_object(run_directory / "report.json", root=root)
    if manifest.get("profile") != expected_profile:
        raise GuidedError("incompatible_run", "Il profilo registrato non coincide con la fase")
    if manifest.get("models") != expected_models:
        raise GuidedError("incompatible_run", "I modelli registrati non coincidono con la selezione")
    if not isinstance(manifest.get("finished_at"), str) or not manifest["finished_at"]:
        raise GuidedError("partial_run", "Il run non risulta completato")
    integrity_manifest = manifest.get("integrity")
    if isinstance(integrity_manifest, dict) and integrity_manifest.get("aborted") is True:
        raise GuidedError("partial_run", "Il run è stato interrotto per integrità")
    report_run = report.get("run")
    if not isinstance(report_run, dict) or report_run.get("profile") != expected_profile:
        raise GuidedError("incompatible_run", "Profilo incoerente nel report")
    thinking = report_run.get("thinking_control")
    if not isinstance(thinking, dict) or thinking.get("status") not in {"passed", "partial", "failed"}:
        raise GuidedError("thinking_unverified", "Controllo thinking non verificato")
    results = report.get("results")
    if not isinstance(results, list):
        raise GuidedError("invalid_report", "Risultati ufficiali mancanti")
    expected_set = set(expected_models)
    failed_models: set[str] = set()
    for item in results:
        if not isinstance(item, dict):
            raise GuidedError("invalid_report", "Risultato ufficiale non valido")
        model = item.get("model")
        status = item.get("status")
        if not isinstance(model, str) or model not in expected_set:
            raise GuidedError("invalid_report", "Modello inatteso nei risultati ufficiali")
        if not isinstance(status, str) or not status:
            raise GuidedError("invalid_report", "Stato task non valido")
        if status != "ok":
            failed_models.add(model)
    integrity = report.get("integrity")
    if not isinstance(integrity, dict):
        raise GuidedError("invalid_report", "Riepilogo integrità mancante")
    disqualified_raw = integrity.get("disqualified_models", [])
    incomplete_raw = integrity.get("incomplete_models", [])
    if not isinstance(disqualified_raw, list) or not isinstance(incomplete_raw, list):
        raise GuidedError("invalid_report", "Esclusioni del report non valide")
    disqualified = {item for item in disqualified_raw if isinstance(item, str)}
    incomplete = {item for item in incomplete_raw if isinstance(item, str)}
    thinking_disqualified_raw = manifest.get("thinking_control", {}).get(
        "disqualified_models", []
    ) if isinstance(manifest.get("thinking_control"), dict) else []
    thinking_disqualified = {
        item for item in thinking_disqualified_raw if isinstance(item, str)
    }
    unexpected_incomplete = incomplete - thinking_disqualified
    if unexpected_incomplete:
        raise GuidedError("partial_run", "Il run contiene modelli incompleti non esclusi")
    leaderboard = _public_leaderboard(report.get("leaderboard"), expected_set)
    ranked = {str(row["model"]) for row in leaderboard}
    if ranked & disqualified:
        raise GuidedError("invalid_report", "La leaderboard include modelli esclusi")
    exclusions: list[dict[str, str]] = []
    for model in expected_models:
        if model in ranked and model not in failed_models:
            continue
        if model in thinking_disqualified:
            reason = "thinking_control"
        elif model in incomplete:
            reason = "incomplete"
        elif model in disqualified:
            reason = "integrity"
        elif model in failed_models:
            reason = "task_failed"
        else:
            reason = "not_ranked"
        exclusions.append({"model": model, "reason": reason})
    if process_returncode not in {0, 1}:
        raise GuidedError("phase_failed", f"La fase è terminata con codice {process_returncode}")
    if process_returncode == 1 and not exclusions:
        raise GuidedError("phase_failed", "La fase ha segnalato un errore senza esclusioni verificabili")
    eligible_models = expected_set - disqualified - incomplete - failed_models
    eligible_leaderboard = tuple(
        row for row in leaderboard if str(row["model"]) in eligible_models
    )
    promoted = (
        select_promoted(eligible_leaderboard, promotion_limit)
        if promotion_limit is not None
        else ()
    )
    return PhaseOutcome(
        profile=expected_profile,
        run_directory=resolved_run,
        leaderboard=leaderboard,
        promoted=promoted,
        exclusions=tuple(exclusions),
    )


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise GuidedError("unsafe_output", "Il percorso deve restare nel progetto") from exc


def _write_manifest(path: Path, payload: dict[str, Any], *, root: Path) -> None:
    resolved = path.resolve()
    if not _inside(resolved, root.resolve()) or path.is_symlink():
        raise GuidedError("unsafe_output", "Il manifesto deve restare nel progetto")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def _manifest_run_directories(payload: dict[str, Any]) -> list[Any]:
    dashboard = payload.get("dashboard")
    if isinstance(dashboard, dict):
        recorded = dashboard.get("run_directories")
        if isinstance(recorded, list) and recorded:
            return recorded
    available: list[Any] = []
    phases = payload.get("phases")
    if not isinstance(phases, list):
        return available
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        profile = phase.get("profile")
        directory = phase.get("run_directory")
        if profile in {"smoke", "standard", "full"} and isinstance(directory, str):
            available.append(directory)
    return available


def _error_from_doctor(payload: dict[str, Any]) -> GuidedError:
    checks = payload.get("checks", [])
    failed = [item for item in checks if isinstance(item, dict) and not item.get("ok")]
    names = {str(item.get("name")) for item in failed}
    detail = "; ".join(str(item.get("detail", "")) for item in failed)
    if "ollama" in names:
        return GuidedError("ollama_unavailable", detail or "Ollama non raggiungibile")
    if "pi" in names:
        return GuidedError("pi_unavailable", detail or "Pi non disponibile")
    if "inputs" in names:
        return GuidedError("dirty_inputs", detail or "Input protetti non puliti")
    if "sandbox" in names:
        return GuidedError("sandbox_unavailable", detail or "Sandbox richiesto non disponibile")
    return GuidedError("prerequisites", detail or "Prerequisiti non soddisfatti")


class GuidedOrchestrator:
    """Run smoke → standard → full while recording every transition."""

    def __init__(
        self,
        config: BenchmarkConfig,
        config_path: Path,
        *,
        process_runner: ManagedProcessRunner | None = None,
        doctor_function: Callable[[BenchmarkConfig], dict[str, Any]] = doctor,
        dashboard_builder: Callable[[list[Path]], dict[str, Any]] = build_dashboard_data,
        dashboard_starter: Callable[..., Any] = start_detached,
    ) -> None:
        self.config = config
        if config.guided is None:
            raise GuidedError(
                "guided_config_missing",
                "La sezione guided è obbligatoria per il percorso rapido",
            )
        self.guided = config.guided
        self.config_path = config_path.resolve()
        self.process_runner = process_runner or ManagedProcessRunner()
        self.doctor_function = doctor_function
        self.dashboard_builder = dashboard_builder
        self.dashboard_starter = dashboard_starter
        self.cancel_event = threading.Event()
        self.manifest_path: Path | None = None

    def discover(self) -> dict[str, Any]:
        parsed = urlparse(self.config.ollama_url)
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise GuidedError("remote_ollama", "Il percorso guidato accetta soltanto Ollama locale")
        self.cancel_event.clear()
        payload = (
            self.doctor_function(self.config, cancel_event=self.cancel_event)
            if self.doctor_function is doctor else self.doctor_function(self.config)
        )
        if self.cancel_event.is_set():
            raise GuidedError("cancelled", "Controllo prerequisiti annullato")
        if not isinstance(payload, dict):
            raise GuidedError("prerequisites", "Risposta doctor non valida")
        models = payload.get("models")
        if not isinstance(models, list):
            raise GuidedError("prerequisites", "Elenco modelli non valido")
        for item in models:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                raise GuidedError("prerequisites", "Elenco modelli non valido")
            validate_model_name(item["name"])
        if not payload.get("ok"):
            error = _error_from_doctor(payload)
            error.context = payload
            raise error
        if not models:
            raise GuidedError("no_models", "Nessun modello Ollama locale rilevato")
        return payload

    def settings_summary(self, *, thinking: str | None = None, sandbox: str | None = None) -> dict[str, Any]:
        defaults = self.config.defaults
        return {
            "profiles": list(self.guided.profiles),
            "promotion_limits": list(self.guided.promotion_limits),
            "ollama_url": self.config.ollama_url,
            "pi_command": list(self.config.pi_command),
            "thinking": thinking if thinking is not None else defaults.thinking,
            "sandbox": sandbox if sandbox is not None else defaults.sandbox,
            "timeout_seconds": defaults.timeout_seconds,
            "repetitions": defaults.repetitions,
            "warmup": defaults.warmup,
            "keep_alive": defaults.keep_alive,
            "context_window": defaults.context_window,
            "max_tokens": defaults.max_tokens,
            "temperature": defaults.temperature,
            "thinking_preflight_timeout_seconds": defaults.thinking_preflight_timeout_seconds,
            "http_idle_timeout_ms": defaults.http_idle_timeout_ms,
            "agent_max_retries": defaults.agent_max_retries,
            "provider_max_retries": defaults.provider_max_retries,
            "results_directory": _relative(self.config.dashboard.results_directory, self.config.root),
        }

    def cancel(self) -> None:
        self.cancel_event.set()

    def _session_directory(self) -> Path:
        results = self.config.dashboard.results_directory.resolve()
        if not _inside(results, self.config.root.resolve()):
            raise GuidedError("unsafe_output", "La directory risultati deve restare nel progetto")
        results.mkdir(parents=True, exist_ok=True)
        for _ in range(20):
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            candidate = results / f"guided-{stamp}-{secrets.token_hex(3)}"
            try:
                candidate.mkdir()
            except FileExistsError:
                continue
            if candidate.is_symlink():
                raise GuidedError("unsafe_output", "Directory sessione non valida")
            return candidate
        raise GuidedError("output_exists", "Impossibile creare una directory sessione distinta")

    def _benchmark_command(
        self, profile: str, models: list[str], seed: int, output: Path,
        *, thinking: str | None = None, sandbox: str | None = None,
    ) -> list[str]:
        safe_models = [validate_model_name(model) for model in models]
        if not safe_models:
            raise GuidedError("no_candidates", "Nessun modello disponibile per la fase")
        if output.exists():
            raise GuidedError("output_exists", f"La directory {output.name} esiste già")
        return [
            python_executable(),
            str(self.config.root / "benchmark.py"),
            "--config",
            str(self.config_path),
            "run",
            "--profile",
            profile,
            "--models",
            *safe_models,
            "--seed",
            str(seed),
            "--output",
            str(output),
            "--thinking",
            thinking if thinking is not None else self.config.defaults.thinking,
            "--sandbox",
            sandbox if sandbox is not None else self.config.defaults.sandbox,
        ]

    def _dashboard_command(self, run_directories: list[Path]) -> list[str]:
        if not 1 <= len(run_directories) <= 3 or len(set(run_directories)) != len(
            run_directories
        ):
            raise GuidedError(
                "dashboard_failed", "La dashboard richiede da uno a tre run distinti"
            )
        return [
            python_executable(),
            str(self.config.root / "dashboard.py"),
            "--config",
            str(self.config_path),
            *[str(path) for path in run_directories],
        ]

    def _emit_line(
        self,
        profile: str,
        line: str,
        callback: Callable[[dict[str, Any]], None] | None,
    ) -> None:
        if callback is None:
            return
        event: dict[str, Any] = {"type": "output", "profile": profile, "line": line}
        match = TASK_PATTERN.match(line)
        if match:
            event.update(
                {
                    "type": "task",
                    "current": int(match.group("current")),
                    "total": int(match.group("total")),
                    "model": match.group("model"),
                    "case": match.group("case"),
                    "repetition": int(match.group("repeat")),
                }
            )
        elif line.startswith("[thinking preflight] "):
            event["type"] = "preflight"
            event["model"] = line.removeprefix("[thinking preflight] ").split(" · ", 1)[0]
        elif line.startswith("[warmup] "):
            event["type"] = "warmup"
            event["model"] = line.removeprefix("[warmup] ")
        callback(event)

    def run(
        self,
        selected_models: list[str],
        discovery: dict[str, Any],
        *,
        thinking: str | None = None,
        sandbox: str | None = None,
        callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> Path:
        if self.cancel_event.is_set():
            self.cancel_event.clear()
        available = {
            item["name"]
            for item in discovery.get("models", [])
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        selected = list(dict.fromkeys(validate_model_name(name) for name in selected_models))
        if not selected:
            raise GuidedError("no_models", "Selezionare almeno un modello")
        missing = [name for name in selected if name not in available]
        if missing:
            raise GuidedError("model_unavailable", f"Modelli non più disponibili: {', '.join(missing)}")
        if not discovery.get("ok"):
            raise _error_from_doctor(discovery)

        thinking_mode = thinking if thinking is not None else self.config.defaults.thinking
        sandbox_mode = sandbox if sandbox is not None else self.config.defaults.sandbox
        if thinking_mode not in THINKING_LEVELS:
            raise GuidedError("invalid_setting", "Modalità thinking non valida")
        if sandbox_mode not in SANDBOX_MODES:
            raise GuidedError("invalid_setting", "Modalità sandbox non valida")
        try:
            select_sandbox(sandbox_mode)
        except SandboxError as exc:
            raise GuidedError("sandbox_unavailable", str(exc)) from exc

        session = self._session_directory()
        self.manifest_path = session / MANIFEST_NAME
        base_seed = secrets.randbits(64)
        seed_source = random.Random(base_seed)
        phase_seeds = {
            profile: seed_source.getrandbits(64) for profile in self.guided.profiles
        }
        discovered = []
        for item in discovery["models"]:
            discovered.append(
                {
                    key: item.get(key)
                    for key in (
                        "name",
                        "size",
                        "digest",
                        "modified_at",
                        "capabilities",
                        "capabilities_known",
                        "thinking_capable",
                    )
                }
            )
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "benchmark_version": __version__,
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "session_directory": _relative(session, self.config.root),
            "discovered_models": discovered,
            "selected_models": selected,
            "base_seed": base_seed,
            "settings": self.settings_summary(thinking=thinking_mode, sandbox=sandbox_mode),
            "phases": [],
            "transitions": [],
            "dashboard": {"status": "pending", "run_directories": []},
            "error": None,
        }
        _write_manifest(self.manifest_path, manifest, root=self.config.root)
        current_models = selected
        completed_runs: list[Path] = []
        profiles = self.guided.profiles
        limits: tuple[int | None, ...] = (
            self.guided.promotion_limits[0],
            self.guided.promotion_limits[1],
            None,
        )
        try:
            for index, (profile, limit) in enumerate(zip(profiles, limits, strict=True), 1):
                if self.cancel_event.is_set():
                    raise GuidedCancelled()
                output = session / profile
                phase_record: dict[str, Any] = {
                    "profile": profile,
                    "status": "running",
                    "models": list(current_models),
                    "seed": phase_seeds[profile],
                    "run_directory": _relative(output, self.config.root),
                    "leaderboard": [],
                    "exclusions": [],
                    "promoted": [],
                }
                manifest["phases"].append(phase_record)
                _write_manifest(self.manifest_path, manifest, root=self.config.root)
                if callback:
                    callback(
                        {
                            "type": "phase",
                            "profile": profile,
                            "index": index,
                            "total": len(profiles),
                            "models": list(current_models),
                            "run_directory": phase_record["run_directory"],
                        }
                    )
                command = self._benchmark_command(
                    profile, current_models, phase_seeds[profile], output,
                    thinking=thinking_mode, sandbox=sandbox_mode,
                )
                result: ProcessResult = self.process_runner.run(
                    command,
                    cwd=self.config.root,
                    cancel_event=self.cancel_event,
                    on_line=lambda line, active=profile: self._emit_line(
                        active, line, callback
                    ),
                )
                if result.cancelled or self.cancel_event.is_set():
                    phase_record["status"] = "cancelled"
                    _write_manifest(self.manifest_path, manifest, root=self.config.root)
                    raise GuidedCancelled()
                if not (output / "run.json").is_file() or not (output / "report.json").is_file():
                    detail = next(
                        (line for line in reversed(result.output_tail) if line.strip()),
                        f"codice {result.returncode}",
                    )
                    raise GuidedError(
                        "phase_failed",
                        f"La fase {profile} non ha prodotto artefatti completi: {detail}",
                    )
                outcome = evaluate_phase(
                    output,
                    root=self.config.root,
                    expected_profile=profile,
                    expected_models=current_models,
                    promotion_limit=limit,
                    process_returncode=result.returncode,
                )
                phase_record.update(
                    {
                        "status": "completed",
                        "leaderboard": list(outcome.leaderboard),
                        "exclusions": list(outcome.exclusions),
                        "promoted": list(outcome.promoted),
                    }
                )
                completed_runs.append(output.resolve())
                manifest["dashboard"] = {
                    "status": "available",
                    "run_directories": [
                        _relative(path, self.config.root) for path in completed_runs
                    ],
                }
                if limit is not None:
                    manifest["transitions"].append(
                        {
                            "from": profile,
                            "to": profiles[index],
                            "limit": limit,
                            "selected": list(outcome.promoted),
                            "excluded": list(outcome.exclusions),
                        }
                    )
                    if not outcome.promoted:
                        raise GuidedError(
                            "no_candidates",
                            f"Nessun modello classificabile dopo la fase {profile}",
                        )
                    current_models = list(outcome.promoted)
                _write_manifest(self.manifest_path, manifest, root=self.config.root)

            try:
                self.dashboard_builder(completed_runs)
                self.dashboard_starter(
                    self._dashboard_command(completed_runs), cwd=self.config.root
                )
            except (DashboardDataError, GuidedProcessError, OSError) as exc:
                manifest["dashboard"] = {
                    "status": "failed",
                    "run_directories": [
                        _relative(path, self.config.root) for path in completed_runs
                    ],
                    "error": str(exc),
                }
                raise GuidedError("dashboard_failed", str(exc)) from exc
            manifest["dashboard"] = {
                "status": "opened",
                "run_directories": [
                    _relative(path, self.config.root) for path in completed_runs
                ],
            }
            manifest["status"] = "completed"
            manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
            _write_manifest(self.manifest_path, manifest, root=self.config.root)
            if callback:
                callback({"type": "completed", "manifest": _relative(self.manifest_path, self.config.root)})
            return self.manifest_path
        except GuidedError as exc:
            manifest["status"] = "cancelled" if exc.code == "cancelled" else "failed"
            if manifest["phases"] and manifest["phases"][-1].get("status") == "running":
                manifest["phases"][-1]["status"] = manifest["status"]
            manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
            manifest["error"] = {"code": exc.code, "message": str(exc)}
            _write_manifest(self.manifest_path, manifest, root=self.config.root)
            raise
        except (GuidedProcessError, OSError) as exc:
            wrapped = GuidedError("phase_failed", str(exc))
            manifest["status"] = "failed"
            if manifest["phases"] and manifest["phases"][-1].get("status") == "running":
                manifest["phases"][-1]["status"] = "failed"
            manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
            manifest["error"] = {"code": wrapped.code, "message": str(wrapped)}
            _write_manifest(self.manifest_path, manifest, root=self.config.root)
            raise wrapped from exc

    def reopen_dashboard(self, manifest_path: Path) -> None:
        payload = _read_object(manifest_path, root=self.config.root)
        raw_directories = _manifest_run_directories(payload)
        if not 1 <= len(raw_directories) <= 3:
            raise GuidedError(
                "dashboard_failed", "Nessun run disponibile per la dashboard"
            )
        runs: list[Path] = []
        for value in raw_directories:
            if not isinstance(value, str):
                raise GuidedError("dashboard_failed", "Percorso run non valido")
            candidate = Path(value)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise GuidedError("dashboard_failed", "Percorso run non confinato")
            resolved = (self.config.root / candidate).resolve()
            if not _inside(resolved, self.config.root.resolve()):
                raise GuidedError("dashboard_failed", "Percorso run non confinato")
            runs.append(resolved)
        try:
            self.dashboard_builder(runs)
            self.dashboard_starter(self._dashboard_command(runs), cwd=self.config.root)
        except (DashboardDataError, GuidedProcessError, OSError) as exc:
            raise GuidedError("dashboard_failed", str(exc)) from exc


def find_latest_manifest(config: BenchmarkConfig) -> Path | None:
    results = config.dashboard.results_directory
    if not results.is_dir():
        return None
    candidates: list[Path] = []
    for path in results.glob(f"guided-*/{MANIFEST_NAME}"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            payload = _read_object(path, root=config.root)
        except GuidedError:
            continue
        run_directories = _manifest_run_directories(payload)
        if 1 <= len(run_directories) <= 3:
            candidates.append(path)
    return max(candidates, key=lambda path: path.stat().st_mtime, default=None)


__all__ = [
    "GuidedCancelled",
    "GuidedError",
    "GuidedOrchestrator",
    "MANIFEST_NAME",
    "PhaseOutcome",
    "evaluate_phase",
    "find_latest_manifest",
    "select_promoted",
    "validate_model_name",
]
