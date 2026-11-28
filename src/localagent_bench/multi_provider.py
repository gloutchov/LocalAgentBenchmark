"""Sequential multi-provider sessions over the existing guided runner."""

from __future__ import annotations

import random
import secrets
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import __version__
from .config import BenchmarkConfig, select_provider
from .case_sdk import safe_case_id
from .colibri_protocol import valid_model_id
from .dashboard_data import DashboardDataError
from .guided import (
    MANIFEST_NAME, GuidedCancelled, GuidedError, GuidedOrchestrator,
    _read_object, _relative, _write_manifest, evaluate_phase, evaluate_preliminary,
    validate_model_name,
)
from .guided_process import GuidedProcessError, python_executable
from .integrity import fingerprint_tree, repository_fingerprints, repository_metadata
from .runner import EXECUTION_POLICY
from .sandbox import SANDBOX_MODES, SandboxError, select_sandbox
from .session_inputs import CONTEXT_NAME, SESSION_PREFIX, freeze_session_inputs
from .thinking import THINKING_LEVELS

RESIDENT_PROVIDERS = {"unsloth", "colibri"}


@dataclass(frozen=True)
class ModelSelection:
    provider: str
    model: str

    @classmethod
    def parse(cls, value: str) -> ModelSelection:
        provider, delimiter, model = value.partition("=")
        if not provider or not delimiter or not valid_model_id(model):
            raise GuidedError("invalid_model", "Usa PROVIDER=MODELLO / Use PROVIDER=MODEL")
        return cls(provider, validate_model_name(model))


def declared_models(config: BenchmarkConfig) -> tuple[str, ...]:
    """Only explicit local mappings fill the gaps in a resident server's catalog."""
    if config.provider_kind == "unsloth":
        return tuple(model for model in (config.model_files or ()) if valid_model_id(model))
    if config.provider_kind == "colibri" and config.colibri is not None:
        return tuple(config.colibri.model_bundles)
    return ()


def session_dashboard_command(config: BenchmarkConfig, config_path: Path, manifest: Path) -> list[str]:
    return [
        python_executable(), str(config.root / "dashboard.py"), "--config", str(config_path),
        "--session", str(manifest),
    ]


class MultiProviderSession:
    def __init__(self, guided: GuidedOrchestrator) -> None:
        self.guided = guided
        self.config = guided.config
        self.cancel_event = guided.cancel_event
        self.resume_event = threading.Event()
        self.manifest_path: Path | None = None

    def cancel(self) -> None:
        self.cancel_event.set()
        self.resume_event.set()

    def resume(self) -> None:
        self.resume_event.set()

    def _groups(self, selections: list[ModelSelection]) -> list[tuple[str, list[str]]]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for selection in dict.fromkeys(selections):
            provider = select_provider(self.config, selection.provider)
            grouped[provider.provider_kind].append(validate_model_name(selection.model))
        if len(grouped) < 2:
            raise GuidedError("invalid_setting", "Seleziona almeno due provider / Select at least two providers")
        return [(kind, group) for kind, models in grouped.items()
                for group in ([[model] for model in models] if kind in RESIDENT_PROVIDERS else [models])]

    def _check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise GuidedCancelled()

    def _catalog(self, provider: GuidedOrchestrator) -> list[dict[str, Any]] | None:
        # Doctor preserves the Pi/protected-input gates before reading credentials.
        try:
            return provider.discover(cancel_event=self.cancel_event)["models"]
        except GuidedError:
            self._check_cancelled()
            return None

    def _resident_ready(self, provider: GuidedOrchestrator, model: str) -> tuple[bool, bool]:
        catalog = self._catalog(provider)
        if catalog is None:
            return False, False
        for row in catalog:
            if row["name"] == model:
                context = (row.get("details") or {}).get("context_length")
                ready = ((type(context) is int and context >= provider.config.defaults.context_window)
                         or (context is None and provider.config.provider_kind == "unsloth"))
                return True, ready
        return True, False

    def _wait_for_resident(
        self, provider: GuidedOrchestrator, model: str,
        callback: Callable[[dict[str, Any]], None] | None, check_inputs: Callable[[], None],
    ) -> tuple[bool, float | None]:
        reachable, ready = self._resident_ready(provider, model)
        if ready:
            return True, None
        if callback is None or (not reachable and model not in declared_models(provider.config)):
            return False, None
        started = time.monotonic()
        timeout = self.guided.guided.model_wait_timeout_seconds
        deadline = started + timeout
        try:
            while (remaining := deadline - time.monotonic()) > 0:
                self.resume_event.clear()
                callback({"type": "model_wait", "provider": provider.config.provider_kind,
                          "model": model, "seconds": max(1, round(remaining))})
                while (remaining := deadline - time.monotonic()) > 0:
                    if self.resume_event.wait(min(remaining, 0.5)):
                        break
                    check_inputs()
                self._check_cancelled()
                check_inputs()
                if remaining <= 0:
                    break
                callback({"type": "model_check", "provider": provider.config.provider_kind, "model": model})
                _, ready = self._resident_ready(provider, model)
                if ready and time.monotonic() <= deadline:
                    return True, round(time.monotonic() - started, 3)
            return False, round(time.monotonic() - started, 3)
        finally:
            callback({"type": "model_wait_done"})

    def run(
        self, selections: list[ModelSelection], *, thinking: str | None = None,
        sandbox: str | None = None, preliminary: bool | None = None,
        profile: str | None = None, seed: int | None = None, open_dashboard: bool = True,
        callback: Callable[[dict[str, Any]], None] | None = None, wait_for_manual: bool = True,
    ) -> Path:
        self._check_cancelled()
        groups = self._groups(selections)
        thinking = thinking if thinking is not None else self.config.defaults.thinking
        sandbox = sandbox if sandbox is not None else self.config.defaults.sandbox
        if thinking not in THINKING_LEVELS or sandbox not in SANDBOX_MODES:
            raise GuidedError("invalid_setting", "Impostazioni thinking o sandbox non valide / Invalid thinking or sandbox settings")
        try:
            select_sandbox(sandbox)
        except SandboxError as exc:
            raise GuidedError("sandbox_unavailable", str(exc)) from exc

        guided = self.guided.guided
        include_preliminary = guided.preliminary if preliminary is None else preliminary
        profiles = (profile,) if profile else (("preliminary",) if include_preliminary else ()) + guided.profiles
        if any(not safe_case_id(name) or name not in self.config.profiles for name in profiles):
            raise GuidedError("invalid_setting", "Profilo non configurato / Profile not configured")
        if "preliminary" in profiles and self.config.preliminary is None:
            raise GuidedError("invalid_setting", "Preliminary non configurato / Preliminary not configured")
        base_seed = seed if seed is not None else secrets.randbits(64)
        randomizer = random.Random(base_seed)
        seeds = {name: randomizer.getrandbits(64) for name in profiles}
        if profile:
            seeds[profile] = base_seed
        limits = dict(zip(guided.profiles[:2], guided.promotion_limits, strict=True)) if not profile else {}
        session = self.guided._session_directory(SESSION_PREFIX)
        self.manifest_path = session / MANIFEST_NAME
        initial_repository = repository_fingerprints(self.config.root, (session,))
        repository = repository_metadata(self.config.root)
        initial_commit = repository["commit"]
        config_hash = fingerprint_tree(self.guided.config_path)
        snapshot_hash = freeze_session_inputs(self.config, session, profiles, EXECUTION_POLICY)

        completed_artifacts: dict[Path, str] = {}

        def check_inputs() -> None:
            self._check_cancelled()
            context = session / CONTEXT_NAME
            if (context.is_symlink() or fingerprint_tree(context) != snapshot_hash
                    or fingerprint_tree(self.guided.config_path) != config_hash
                    or repository_fingerprints(self.config.root, (session,)) != initial_repository
                    or repository_metadata(self.config.root)["commit"] != initial_commit
                    or any(fingerprint_tree(path) != digest for path, digest in completed_artifacts.items())):
                raise GuidedError("session_inputs_changed", "Snapshot o repository modificato / Snapshot or repository changed")

        payload = {
            "schema_version": 1, "benchmark_version": __version__, "mode": "multi_provider",
            "session_directory": _relative(session, self.config.root), "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None,
            "selected_models": [{"provider": item.provider, "model": item.model}
                                for item in dict.fromkeys(selections)],
            "base_seed": base_seed, "phase_seeds": seeds, "input_sha256": snapshot_hash,
            "configuration_sha256": config_hash,
            "repository_commit": initial_commit, "repository_dirty": repository["dirty"], "settings": self.guided.settings_summary(thinking=thinking, sandbox=sandbox),
            "phases": [], "dashboard": {"status": "pending", "run_directories": []}, "error": None,
        }
        # The summary contains user settings and relative artifact references only.
        for key in ("ollama_url", "provider_kind", "provider_url", "pi_command"):
            payload["settings"].pop(key)
        payload["settings"]["profiles"] = list(profiles)

        def save() -> None:
            _write_manifest(self.manifest_path, payload, root=self.config.root)

        runs: list[Path] = []
        save()
        try:
            check_inputs()
            for index, (kind, models) in enumerate(groups):
                selected = select_provider(self.config, kind)
                selected = replace(selected, defaults=replace(selected.defaults, sandbox=sandbox))
                provider = GuidedOrchestrator(selected, self.guided.config_path, provider_override=True,
                                              process_runner=self.guided.process_runner,
                                              doctor_function=self.guided.doctor_function)
                for level, name in enumerate(profiles, 1):
                    check_inputs()
                    output = session / f"{session.name.removeprefix(SESSION_PREFIX)}-{index + 1:03}-{kind}-{name}"
                    phase = {
                        "provider": kind, "profile": name, "models": models, "status": "running",
                        "seed": seeds[name], "run_directory": _relative(output, self.config.root),
                    }
                    payload["phases"].append(phase)
                    save()
                    if callback:
                        callback({"type": "phase", "index": index * len(profiles) + level,
                                  "total": len(groups) * len(profiles), **phase})
                    not_available = []
                    if kind in RESIDENT_PROVIDERS:
                        def notify(event: dict[str, Any]) -> None:
                            if event["type"] == "model_wait":
                                phase["manual_load_requested"] = True
                                save()
                            callback(event)

                        ready, waiting = self._wait_for_resident(
                            provider, models[0], notify if wait_for_manual and callback else None, check_inputs,
                        )
                        phase["manual_wait_seconds"] = waiting
                        if not ready:
                            phase.update(status="excluded", reason="model_wait_timeout" if waiting is not None else "model_unavailable")
                            save()
                            break
                    elif level == 1:
                        catalog = self._catalog(provider)
                        available = {row["name"] for row in catalog or ()}
                        not_available = [{"model": model, "reason": "model_unavailable"}
                                         for model in models if model not in available]
                        models = [model for model in models if model in available]
                        if not models:
                            phase.update(status="excluded", reason="model_unavailable" if catalog is not None
                                         else "provider_or_preflight_failed")
                            save()
                            break
                    check_inputs()
                    command = provider._benchmark_command(name, models, seeds[name], output, thinking=thinking, sandbox=sandbox)
                    command.extend(("--session-input-hash", snapshot_hash))
                    result = self.guided.process_runner.run(
                        command, cwd=self.config.root, cancel_event=self.cancel_event,
                        on_line=lambda line: provider._emit_line(name, line, callback),
                    )
                    if result.cancelled:
                        raise GuidedCancelled()
                    check_inputs()
                    try:
                        outcome = self._outcome(output, kind, name, models, limits.get(name), result.returncode,
                                                seeds[name], snapshot_hash)
                    except GuidedError as exc:
                        phase.update(status="excluded", reason=exc.code)
                        save()
                        break
                    for name_of_artifact in ("run.json", "report.json"):
                        artifact = output / name_of_artifact
                        completed_artifacts[artifact] = fingerprint_tree(artifact)
                    runs.append(output)
                    payload["dashboard"].update(status="available", run_directories=[_relative(run, self.config.root) for run in runs])
                    phase.update(status="completed", exclusions=not_available + list(outcome.exclusions),
                                 promoted=list(outcome.promoted))
                    save()
                    if name == "preliminary" or name in limits:
                        models = list(outcome.promoted)
                        if not models:
                            break

            check_inputs()
            if not runs:
                raise GuidedError("no_candidates", "Nessun run completo / No completed run")
            excluded = any(phase["status"] == "excluded" or phase.get("exclusions") for phase in payload["phases"])
            payload["status"] = "partial" if excluded else "completed"
            payload["finished_at"] = datetime.now(timezone.utc).isoformat()
            save()
            if open_dashboard:
                try:
                    self.guided.dashboard_builder(runs)
                    self.guided.dashboard_starter(
                        session_dashboard_command(self.config, self.guided.config_path, self.manifest_path),
                        cwd=self.config.root,
                    )
                except (DashboardDataError, GuidedProcessError, OSError) as exc:
                    raise GuidedError("dashboard_failed", "Impossibile aprire la dashboard / Cannot open dashboard") from exc
                payload["dashboard"]["status"] = "opened"
        except (GuidedError, KeyboardInterrupt, GuidedProcessError, OSError) as exc:
            code = exc.code if isinstance(exc, GuidedError) else "cancelled" if isinstance(exc, KeyboardInterrupt) else "phase_failed"
            payload["status"] = "cancelled" if code == "cancelled" else "failed"
            payload["error"] = {"code": code}
            if payload["phases"] and payload["phases"][-1]["status"] == "running":
                payload["phases"][-1]["status"] = payload["status"]
            if code == "session_inputs_changed":
                payload["dashboard"] = {"status": "invalidated", "run_directories": []}
            raise
        finally:
            payload["finished_at"] = datetime.now(timezone.utc).isoformat()
            save()
        return self.manifest_path

    def _outcome(self, output: Path, provider: str, profile: str, models: list[str],
                 limit: int | None, returncode: int, seed: int, snapshot_hash: str):
        root = self.config.root
        if not (output / "run.json").is_file() or not (output / "report.json").is_file():
            raise GuidedError("provider_or_preflight_failed", "Run non prodotto / Run not produced")
        manifest = _read_object(output / "run.json", root=root)
        if (
            manifest.get("session") != {"id": output.parent.name, "input_sha256": snapshot_hash}
            or manifest.get("configuration", {}).get("provider_kind") != provider
            or manifest.get("order_seed") != seed
        ):
            raise GuidedError("incompatible_run", "Provenienza run incoerente / Inconsistent run provenance")
        if profile == "preliminary":
            return evaluate_preliminary(output, root=root, expected_models=models, process_returncode=returncode)
        outcome = evaluate_phase(output, root=root, expected_profile=profile, expected_models=models,
                                 promotion_limit=limit, process_returncode=returncode)
        if any(row["reason"] == "task_failed" for row in outcome.exclusions):
            report = _read_object(output / "report.json", root=root)
            timed_out = {row["model"] for row in report["results"] if row["status"] == "timeout"}
            outcome = replace(outcome, exclusions=tuple(
                {**row, "reason": "timeout"} if row["reason"] == "task_failed" and row["model"] in timed_out else row
                for row in outcome.exclusions
            ))
        return outcome
