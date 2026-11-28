"""Reduce a local session manifest to its public dashboard status."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .dashboard_app import DashboardAppError, resolve_run_directories
from .dashboard_data import PROVIDERS, PUBLIC_CASE_ID, SESSION_ID, _number, build_dashboard_data
from .guided import MANIFEST_NAME, GuidedError, _read_object
from .colibri_protocol import valid_model_id

PHASE_STATUSES = ("completed", "excluded", "cancelled", "failed")
REASONS = ("model_wait_timeout", "model_unavailable", "provider_or_preflight_failed",
           "incompatible_run", "partial_run", "invalid_report", "phase_failed", "thinking_unverified",
           "task_failed", "timeout", "thinking_control", "integrity", "incomplete", "not_ranked")


def load_session_dashboard(path: Path, *, root: Path, results: Path) -> tuple[dict, dict]:
    resolved = path.resolve()
    identity = resolved.parent.name
    if (
        path.is_symlink() or resolved.name != MANIFEST_NAME or not SESSION_ID.fullmatch(identity)
        or resolved.parent.parent != results.resolve()
    ):
        raise DashboardAppError("Manifesto sessione fuori dai risultati / Session manifest outside results")
    try:
        manifest = _read_object(resolved, root=root)
    except GuidedError as exc:
        raise DashboardAppError("Manifesto sessione non valido / Invalid session manifest") from exc

    dashboard = manifest.get("dashboard")
    paths = dashboard.get("run_directories") if isinstance(dashboard, dict) else None
    phases = manifest.get("phases")
    status = manifest.get("status")
    if (
        manifest.get("mode") != "multi_provider" or manifest.get("schema_version") != 1
        or not isinstance(paths, list) or not paths or not isinstance(phases, list)
        or status not in ("completed", "partial", "failed", "cancelled")
        or dashboard.get("status") == "invalidated"
    ):
        raise DashboardAppError("Nessun run di sessione disponibile / No session runs available")
    candidates = []
    for raw in paths:
        if not isinstance(raw, str):
            raise DashboardAppError("Percorso run di sessione non valido / Invalid session run path")
        relative = Path(raw)
        if relative.is_absolute() or ".." in relative.parts or (root / relative).resolve().parent != resolved.parent:
            raise DashboardAppError("Run fuori dalla sessione / Run outside session")
        candidates.append(root / relative)
    runs = resolve_run_directories(candidates, root=root)
    dataset = build_dashboard_data(runs)
    if any(run.get("session_id") != identity for run in dataset["runs"]):
        raise DashboardAppError("Identità sessione incoerente / Session identity mismatch")
    return dataset, {"id": identity, "status": status, "phases": _public_phases(phases)}


def _public_phases(phases: list[Any]) -> list[dict]:
    public = []
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        provider, profile, status = (phase.get(key) for key in ("provider", "profile", "status"))
        models = phase.get("models")
        if (provider not in PROVIDERS or not isinstance(profile, str) or not PUBLIC_CASE_ID.fullmatch(profile)
                or status not in PHASE_STATUSES or not isinstance(models, list)):
            continue
        reason = phase.get("reason")
        failures = {}
        for entry in phase.get("exclusions", []) if isinstance(phase.get("exclusions"), list) else ():
            if isinstance(entry, dict) and valid_model_id(entry.get("model")) and entry.get("reason") in REASONS:
                failures[entry["model"]] = entry["reason"]
        for model in models:
            if not valid_model_id(model):
                continue
            public.append({
                "provider": provider, "profile": profile, "model": model, "status": status,
                "reason": failures.get(model) or (reason if reason in REASONS else None),
                "manual_wait_seconds": _number(phase.get("manual_wait_seconds"), minimum=0),
            })
    return public
