"""Build a privacy-bounded dataset for the offline results dashboard."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from collections import defaultdict
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable


DASHBOARD_SCHEMA_VERSION = 3
SUPPORTED_DASHBOARD_SCHEMA_VERSIONS = {1, 2, 3}
SUPPORTED_RUN_SCHEMA_VERSIONS = {2, 3, 4}
SUPPORTED_REPORT_SCHEMA_VERSIONS = {2, 3, 4}
MAX_SOURCE_BYTES = 32 * 1024 * 1024
PROFILE_ORDER = ("smoke", "standard", "full", "thinking", "showcase")
FUNNEL_PIPELINE = ("smoke", "standard", "full")
RUN_FIELDS = {
    "id",
    "profile",
    "benchmark_version",
    "started_at",
    "finished_at",
    "provenance",
    "sandbox",
    "integrity",
    "thinking_control",
    "participants",
    "leaderboard",
    "tasks",
    "exclusions",
}
SCHEMA_2_RUN_FIELDS = RUN_FIELDS - {"exclusions"}
LEGACY_RUN_FIELDS = SCHEMA_2_RUN_FIELDS - {"thinking_control"}
EXCLUSION_FIELDS = {"model", "reason", "case_id"}
EXCLUSION_REASONS = {
    "thinking_observed_off", "thinking_unverified", "workspace_boundary",
    "repository_mutation", "snapshot_mutation", "integrity_other",
}
PUBLIC_CASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
PROVENANCE_FIELDS = {
    "run_schema_version",
    "report_schema_version",
    "run_sha256",
    "report_sha256",
    "repository_commit",
}
SANDBOX_FIELDS = {
    "backend",
    "enforced",
    "filesystem_isolation",
    "process_isolation",
    "network_isolation",
}
INTEGRITY_FIELDS = {"status", "disqualified_models"}
THINKING_CONTROL_FIELDS = {"version", "status", "requested", "reasoning_effort", "source"}
LEADERBOARD_FIELDS = {
    "rank",
    "model",
    "overall_score",
    "quality_score",
    "completion_rate",
    "speed_score",
    "token_efficiency_score",
    "median_duration_seconds",
    "median_output_tokens",
    "median_cpu_seconds",
    "median_energy_joules",
    "score_stddev",
    "successful_tasks",
    "total_tasks",
    "case_scores",
}
TASK_FIELDS = {
    "model",
    "case_id",
    "case_title",
    "case_title_en",
    "category",
    "repetition",
    "status",
    "state",
    "score",
    "max_score",
    "duration_seconds",
    "output_tokens",
    "tool_calls",
    "tool_errors",
    "cpu_seconds",
    "energy_joules",
    "integrity_valid",
}
FUNNEL_FIELDS = {
    "profile",
    "run_ids",
    "participants",
    "new_participants",
    "next_profile",
    "continued_to_next",
    "not_run_in_next",
}


class DashboardDataError(ValueError):
    """Raised when dashboard sources or output violate the export contract."""


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _load_object(path: Path) -> tuple[dict[str, Any], str]:
    try:
        if path.is_symlink():
            raise DashboardDataError(f"La sorgente dashboard non può essere un symlink: {path}")
        size = path.stat().st_size
        if size > MAX_SOURCE_BYTES:
            raise DashboardDataError(
                f"Sorgente dashboard troppo grande: {path.name} (massimo {MAX_SOURCE_BYTES} byte)"
            )
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except DashboardDataError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DashboardDataError(f"Impossibile leggere {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DashboardDataError(f"La radice di {path} deve essere un oggetto JSON")
    return payload, hashlib.sha256(raw).hexdigest()


def _text(value: Any, *, default: str = "", maximum: int = 256) -> str:
    if not isinstance(value, str):
        return default
    cleaned = value.strip()
    if not cleaned or len(cleaned) > maximum or any(ord(character) < 32 for character in cleaned):
        return default
    if cleaned.startswith("/") or PureWindowsPath(cleaned).is_absolute():
        return default
    return cleaned


def _number(value: Any, *, minimum: float | None = None) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if not math.isfinite(numeric) or (minimum is not None and numeric < minimum):
        return None
    return int(value) if isinstance(value, int) else round(numeric, 6)


def _boolean(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _integer(value: Any, *, minimum: int = 0) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        return None
    return value


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(label for item in value if (label := _text(item))))


def _require_exact_fields(value: Any, fields: set[str], *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise DashboardDataError(f"Campi non validi in {label}")
    return value


def _validate_public_string_list(value: Any, *, label: str, maximum: int = 256) -> None:
    if not isinstance(value, list) or any(_text(item, maximum=maximum) != item for item in value):
        raise DashboardDataError(f"{label} deve contenere stringhe pubbliche valide")
    if len(value) != len(set(value)):
        raise DashboardDataError(f"{label} contiene duplicati")


def _valid_public_text(value: Any, *, maximum: int = 256, nullable: bool = False) -> bool:
    return (nullable and value is None) or _text(value, maximum=maximum) == value


def _valid_nullable_number(value: Any) -> bool:
    return value is None or _number(value, minimum=0) is not None


def _valid_nullable_integer(value: Any) -> bool:
    return value is None or _integer(value) is not None


def _sanitize_case_scores(value: Any) -> dict[str, float | int]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, float | int] = {}
    for raw_case, raw_score in sorted(value.items(), key=lambda item: str(item[0])):
        case_id = _text(raw_case, maximum=64)
        score = _number(raw_score, minimum=0)
        if case_id and score is not None:
            output[case_id] = score
    return output


def _sanitize_leaderboard(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    output: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        model = _text(raw.get("model"))
        if not model:
            continue
        row = {
            "rank": len(output) + 1,
            "model": model,
            "overall_score": _number(raw.get("overall_score"), minimum=0),
            "quality_score": _number(raw.get("quality_score"), minimum=0),
            "completion_rate": _number(raw.get("completion_rate"), minimum=0),
            "speed_score": _number(raw.get("speed_score"), minimum=0),
            "token_efficiency_score": _number(raw.get("token_efficiency_score"), minimum=0),
            "median_duration_seconds": _number(raw.get("median_duration_seconds"), minimum=0),
            "median_output_tokens": _number(raw.get("median_output_tokens"), minimum=0),
            "median_cpu_seconds": _number(raw.get("median_cpu_seconds"), minimum=0),
            "median_energy_joules": _number(raw.get("median_energy_joules"), minimum=0),
            "score_stddev": _number(raw.get("score_stddev"), minimum=0),
            "successful_tasks": _integer(raw.get("successful_tasks")),
            "total_tasks": _integer(raw.get("total_tasks")),
            "case_scores": _sanitize_case_scores(raw.get("case_scores")),
        }
        output.append(row)
    return output


def _task_state(status: str, score: float | int | None, valid_for_ranking: bool | None) -> str:
    if valid_for_ranking is False:
        return "integrity_excluded"
    if status == "timeout":
        return "timeout"
    if status != "ok":
        return "error"
    if score is None:
        return "missing_score"
    return "passed" if float(score) >= 60 else "below_threshold"


def _sanitize_tasks(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    output: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        model = _text(raw.get("model"))
        case_id = _text(raw.get("case_id"), maximum=64)
        if not model or not case_id:
            continue
        grade = raw.get("grade") if isinstance(raw.get("grade"), dict) else {}
        metrics = raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {}
        usage = metrics.get("usage") if isinstance(metrics.get("usage"), dict) else {}
        system = raw.get("system_metrics") if isinstance(raw.get("system_metrics"), dict) else {}
        process = system.get("process") if isinstance(system.get("process"), dict) else {}
        energy = system.get("energy") if isinstance(system.get("energy"), dict) else {}
        integrity = raw.get("integrity") if isinstance(raw.get("integrity"), dict) else {}
        status = _text(raw.get("status"), default="unknown", maximum=32)
        score = _number(grade.get("score"), minimum=0)
        valid_for_ranking = _boolean(integrity.get("valid_for_ranking"))
        task = {
            "model": model,
            "case_id": case_id,
            "case_title": _text(raw.get("case_title"), default=case_id, maximum=200),
            "case_title_en": _text(raw.get("case_title_en"), default=case_id, maximum=200),
            "category": _text(raw.get("case_category"), default="unknown", maximum=64),
            "repetition": _integer(raw.get("repetition"), minimum=1) or 1,
            "status": status,
            "state": _task_state(status, score, valid_for_ranking),
            "score": score,
            "max_score": _number(grade.get("max_score"), minimum=0),
            "duration_seconds": _number(raw.get("duration_seconds"), minimum=0),
            "output_tokens": _integer(usage.get("output")),
            "tool_calls": _integer(metrics.get("tool_calls")),
            "tool_errors": _integer(metrics.get("tool_errors")),
            "cpu_seconds": None,
            "energy_joules": None,
            "integrity_valid": valid_for_ranking,
        }
        if process.get("available") is True:
            user_seconds = _number(process.get("user_seconds"), minimum=0)
            system_seconds = _number(process.get("system_seconds"), minimum=0)
            if user_seconds is not None and system_seconds is not None:
                task["cpu_seconds"] = round(float(user_seconds) + float(system_seconds), 6)
        if energy.get("available") is True:
            task["energy_joules"] = _number(energy.get("energy_joules"), minimum=0)
        output.append(task)
    return output


def _sanitize_thinking_control(manifest: dict[str, Any], report_run: dict[str, Any]) -> dict[str, Any]:
    raw = report_run.get("thinking_control")
    if not isinstance(raw, dict):
        raw = manifest.get("thinking_control")
    if not isinstance(raw, dict):
        raw = {}
    config = manifest.get("config") if isinstance(manifest.get("config"), dict) else {}
    requested = _text(raw.get("requested"), maximum=32) or _text(config.get("thinking"), maximum=32)
    version = _integer(raw.get("version")) or 0
    if version < 1:
        return {
            "version": 0,
            "status": "unverified",
            "requested": requested or "unknown",
            "reasoning_effort": None,
            "source": "legacy_unverified",
        }
    return {
        "version": version,
        "status": _text(raw.get("status"), default="unverified", maximum=64),
        "requested": requested or "unknown",
        "reasoning_effort": _text(raw.get("reasoning_effort"), maximum=32) or None,
        "source": _text(raw.get("source"), default="unknown", maximum=64),
    }


def _sanitize_exclusions(
    manifest: dict[str, Any], report_integrity: dict[str, Any], disqualified: list[str]
) -> list[dict[str, str | None]]:
    thinking = manifest.get("thinking_control") if isinstance(manifest.get("thinking_control"), dict) else {}
    preflights = thinking.get("preflights") if isinstance(thinking.get("preflights"), dict) else {}
    requested = thinking.get("requested")
    violations = report_integrity.get("violations")
    by_model: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
    if isinstance(violations, list):
        kinds = {
            "external_workspace_access": "workspace_boundary",
            "repository_mutation": "repository_mutation",
            "snapshot_mutation": "snapshot_mutation",
        }
        for item in violations:
            if not isinstance(item, dict):
                continue
            model = _text(item.get("model"))
            kind = item.get("kind")
            reason = kinds.get(kind) if isinstance(kind, str) else None
            if kind == "thinking_control_violation":
                details = item.get("details")
                observed_off = (
                    requested == "off" and isinstance(details, list)
                    and any(isinstance(detail, dict) and detail.get("reason") == "unexpected_thinking" for detail in details)
                )
                reason = "thinking_observed_off" if observed_off else "thinking_unverified"
            case_id = _text(item.get("case_id"), maximum=64) or None
            if case_id and not PUBLIC_CASE_ID.fullmatch(case_id):
                case_id = None
            if model in disqualified and reason:
                by_model[model].append((reason, case_id))
    output: list[dict[str, str | None]] = []
    for model in disqualified:
        preflight = preflights.get(model) if isinstance(preflights.get(model), dict) else {}
        if requested == "off" and preflight.get("status") == "unexpected_thinking":
            by_model[model].insert(0, ("thinking_observed_off", None))
        elif model in _string_list(thinking.get("disqualified_models")):
            by_model[model].insert(0, ("thinking_unverified", None))
        seen: set[tuple[str, str | None]] = set()
        for reason, case_id in by_model[model] or [("integrity_other", None)]:
            if (reason, case_id) not in seen:
                output.append({"model": model, "reason": reason, "case_id": case_id})
                seen.add((reason, case_id))
    return output


def _profile_order(profiles: Iterable[str]) -> list[str]:
    available = set(profiles)
    ordered = [profile for profile in PROFILE_ORDER if profile in available]
    ordered.extend(sorted(available - set(PROFILE_ORDER)))
    return ordered


def _build_funnel(runs: list[dict[str, Any]], profile_order: list[str]) -> list[dict[str, Any]]:
    run_ids: dict[str, list[str]] = defaultdict(list)
    participants: dict[str, set[str]] = defaultdict(set)
    for run in runs:
        profile = run["profile"]
        run_ids[profile].append(run["id"])
        participants[profile].update(run["participants"])
    funnel_order = [profile for profile in FUNNEL_PIPELINE if profile in profile_order]
    funnel: list[dict[str, Any]] = []
    for index, profile in enumerate(funnel_order):
        current = participants[profile]
        previous = participants[funnel_order[index - 1]] if index else set()
        next_profile = funnel_order[index + 1] if index + 1 < len(funnel_order) else None
        following = participants[next_profile] if next_profile else set()
        funnel.append(
            {
                "profile": profile,
                "run_ids": sorted(run_ids[profile]),
                "participants": sorted(current),
                "new_participants": sorted(current - previous) if index else sorted(current),
                "next_profile": next_profile,
                "continued_to_next": sorted(current & following) if next_profile else [],
                "not_run_in_next": sorted(current - following) if next_profile else [],
            }
        )
    return funnel


def build_dashboard_data(run_dirs: Iterable[Path]) -> dict[str, Any]:
    """Load report artifacts and return a strictly whitelisted dashboard dataset."""
    resolved_dirs = [Path(path).resolve() for path in run_dirs]
    if not resolved_dirs:
        raise DashboardDataError("Indicare almeno una directory di run")
    if len(set(resolved_dirs)) != len(resolved_dirs):
        raise DashboardDataError("Le directory di run devono essere distinte")

    runs: list[dict[str, Any]] = []
    run_ids: set[str] = set()
    for run_dir in resolved_dirs:
        if not run_dir.is_dir():
            raise DashboardDataError(f"Directory di run mancante: {run_dir}")
        manifest, run_sha256 = _load_object(run_dir / "run.json")
        report, report_sha256 = _load_object(run_dir / "report.json")
        run_schema = manifest.get("schema_version")
        report_schema = report.get("schema_version")
        if isinstance(run_schema, bool) or run_schema not in SUPPORTED_RUN_SCHEMA_VERSIONS:
            raise DashboardDataError(f"Schema run non supportato in {run_dir.name}: {run_schema!r}")
        if isinstance(report_schema, bool) or report_schema not in SUPPORTED_REPORT_SCHEMA_VERSIONS:
            raise DashboardDataError(f"Schema report non supportato in {run_dir.name}: {report_schema!r}")
        report_run = report.get("run") if isinstance(report.get("run"), dict) else {}
        manifest_profile = _text(manifest.get("profile"), maximum=64)
        report_profile = _text(report_run.get("profile"), maximum=64)
        if manifest_profile and report_profile and manifest_profile != report_profile:
            raise DashboardDataError(f"Profilo incoerente fra run e report: {run_dir.name}")
        profile = report_profile or manifest_profile
        if not profile:
            raise DashboardDataError(f"Profilo mancante nel run: {run_dir.name}")
        run_id = _text(run_dir.name, maximum=120)
        if not run_id or run_id in run_ids:
            raise DashboardDataError(f"ID run non valido o duplicato: {run_dir.name!r}")
        run_ids.add(run_id)

        leaderboard = _sanitize_leaderboard(report.get("leaderboard"))
        tasks = _sanitize_tasks(report.get("results"))
        report_integrity = report.get("integrity") if isinstance(report.get("integrity"), dict) else {}
        disqualified = _string_list(report_integrity.get("disqualified_models"))
        participants = set(_string_list(manifest.get("models")))
        participants.update(row["model"] for row in leaderboard)
        participants.update(task["model"] for task in tasks)
        participants.update(disqualified)
        repository = manifest.get("repository") if isinstance(manifest.get("repository"), dict) else {}
        sandbox = report_run.get("sandbox") if isinstance(report_run.get("sandbox"), dict) else {}
        if not sandbox:
            sandbox = manifest.get("sandbox") if isinstance(manifest.get("sandbox"), dict) else {}
        runs.append(
            {
                "id": run_id,
                "profile": profile,
                "benchmark_version": _text(manifest.get("benchmark_version"), default="unknown", maximum=32),
                "started_at": _text(manifest.get("started_at"), maximum=64) or None,
                "finished_at": _text(manifest.get("finished_at"), maximum=64) or None,
                "provenance": {
                    "run_schema_version": run_schema,
                    "report_schema_version": report_schema,
                    "run_sha256": run_sha256,
                    "report_sha256": report_sha256,
                    "repository_commit": _text(repository.get("commit"), maximum=128) or None,
                },
                "sandbox": {
                    "backend": _text(sandbox.get("backend"), default="unknown", maximum=64),
                    "enforced": bool(sandbox.get("enforced") is True),
                    "filesystem_isolation": bool(sandbox.get("filesystem_isolation") is True),
                    "process_isolation": bool(sandbox.get("process_isolation") is True),
                    "network_isolation": bool(sandbox.get("network_isolation") is True),
                },
                "integrity": {
                    "status": _text(report_integrity.get("status"), default="not_recorded", maximum=64),
                    "disqualified_models": disqualified,
                },
                "thinking_control": _sanitize_thinking_control(manifest, report_run),
                "participants": sorted(participants),
                "leaderboard": leaderboard,
                "tasks": tasks,
                "exclusions": _sanitize_exclusions(manifest, report_integrity, disqualified),
            }
        )

    order = _profile_order(run["profile"] for run in runs)
    profile_index = {profile: index for index, profile in enumerate(order)}
    runs.sort(key=lambda run: (profile_index[run["profile"]], run["id"]))
    dataset = {
        "schema_version": DASHBOARD_SCHEMA_VERSION,
        "profile_order": order,
        "runs": runs,
        "funnel": _build_funnel(runs, order),
    }
    validate_dashboard_data(dataset)
    return dataset


def validate_dashboard_data(dataset: Any) -> None:
    """Validate the public dashboard dataset shape without external packages."""
    if (
        not isinstance(dataset, dict)
        or isinstance(dataset.get("schema_version"), bool)
        or dataset.get("schema_version") not in SUPPORTED_DASHBOARD_SCHEMA_VERSIONS
    ):
        raise DashboardDataError("Dataset dashboard non valido o schema non supportato")
    if set(dataset) != {"schema_version", "profile_order", "runs", "funnel"}:
        raise DashboardDataError("Campi radice del dataset dashboard non validi")
    dashboard_schema = dataset["schema_version"]
    profiles = dataset.get("profile_order")
    runs = dataset.get("runs")
    funnel = dataset.get("funnel")
    if not isinstance(profiles, list) or not profiles:
        raise DashboardDataError("profile_order deve contenere profili validi")
    _validate_public_string_list(profiles, label="profile_order", maximum=64)
    if not isinstance(runs, list) or not runs:
        raise DashboardDataError("runs deve contenere almeno un run")
    ids: set[str] = set()
    for run in runs:
        expected_run_fields = (
            RUN_FIELDS if dashboard_schema >= 3 else
            SCHEMA_2_RUN_FIELDS if dashboard_schema == 2 else LEGACY_RUN_FIELDS
        )
        run = _require_exact_fields(run, expected_run_fields, label="run dashboard")
        if _text(run.get("id"), maximum=120) != run.get("id"):
            raise DashboardDataError("Run dashboard non valido")
        if run["id"] in ids:
            raise DashboardDataError(f"ID run duplicato: {run['id']}")
        ids.add(run["id"])
        if run.get("profile") not in profiles:
            raise DashboardDataError(f"Profilo run non dichiarato: {run.get('profile')!r}")
        for key, maximum in (("benchmark_version", 32), ("started_at", 64), ("finished_at", 64)):
            if not _valid_public_text(run.get(key), maximum=maximum, nullable=key != "benchmark_version"):
                raise DashboardDataError(f"{key} non valido nel run {run['id']}")
        provenance = _require_exact_fields(
            run.get("provenance"), PROVENANCE_FIELDS, label=f"provenance di {run['id']}"
        )
        if (
            _integer(provenance["run_schema_version"], minimum=1) not in SUPPORTED_RUN_SCHEMA_VERSIONS
            or _integer(provenance["report_schema_version"], minimum=1) not in SUPPORTED_REPORT_SCHEMA_VERSIONS
        ):
            raise DashboardDataError(f"Versione di provenienza non valida nel run {run['id']}")
        for key in ("run_sha256", "report_sha256"):
            value = provenance[key]
            if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise DashboardDataError(f"Hash di provenienza non valido nel run {run['id']}")
        if not _valid_public_text(provenance["repository_commit"], maximum=128, nullable=True):
            raise DashboardDataError(f"Commit di provenienza non valido nel run {run['id']}")
        sandbox = _require_exact_fields(run.get("sandbox"), SANDBOX_FIELDS, label=f"sandbox di {run['id']}")
        if not _valid_public_text(sandbox["backend"], maximum=64) or any(
            not isinstance(sandbox[key], bool)
            for key in ("enforced", "filesystem_isolation", "process_isolation", "network_isolation")
        ):
            raise DashboardDataError(f"Sandbox non valida nel run {run['id']}")
        integrity = _require_exact_fields(
            run.get("integrity"), INTEGRITY_FIELDS, label=f"integrity di {run['id']}"
        )
        if not _valid_public_text(integrity["status"], maximum=64):
            raise DashboardDataError(f"Integrità non valida nel run {run['id']}")
        _validate_public_string_list(run.get("participants"), label=f"participants di {run['id']}")
        _validate_public_string_list(
            integrity.get("disqualified_models"), label=f"disqualified_models di {run['id']}"
        )
        if dashboard_schema >= 2:
            thinking = _require_exact_fields(
                run.get("thinking_control"),
                THINKING_CONTROL_FIELDS,
                label=f"thinking_control di {run['id']}",
            )
            if (
                _integer(thinking["version"]) is None
                or not _valid_public_text(thinking["status"], maximum=64)
                or not _valid_public_text(thinking["requested"], maximum=32)
                or not _valid_public_text(thinking["reasoning_effort"], maximum=32, nullable=True)
                or not _valid_public_text(thinking["source"], maximum=64)
            ):
                raise DashboardDataError(f"Controllo thinking non valido nel run {run['id']}")
        if dashboard_schema >= 3:
            exclusions = run.get("exclusions")
            if not isinstance(exclusions, list):
                raise DashboardDataError(f"Esclusioni non valide nel run {run['id']}")
            for exclusion in exclusions:
                exclusion = _require_exact_fields(exclusion, EXCLUSION_FIELDS, label=f"esclusione di {run['id']}")
                if (
                    not _valid_public_text(exclusion["model"])
                    or exclusion["model"] not in integrity["disqualified_models"]
                    or exclusion["reason"] not in EXCLUSION_REASONS
                    or (exclusion["case_id"] is not None and (
                        not isinstance(exclusion["case_id"], str)
                        or not PUBLIC_CASE_ID.fullmatch(exclusion["case_id"])
                    ))
                ):
                    raise DashboardDataError(f"Esclusione non valida nel run {run['id']}")
        if not isinstance(run.get("leaderboard"), list) or not isinstance(run.get("tasks"), list):
            raise DashboardDataError(f"Leaderboard o task non valide nel run {run['id']}")
        for row in run["leaderboard"]:
            row = _require_exact_fields(row, LEADERBOARD_FIELDS, label=f"leaderboard di {run['id']}")
            numeric_fields = LEADERBOARD_FIELDS - {
                "rank",
                "model",
                "successful_tasks",
                "total_tasks",
                "case_scores",
            }
            if (
                _integer(row["rank"], minimum=1) is None
                or not _valid_public_text(row["model"])
                or any(not _valid_nullable_number(row[key]) for key in numeric_fields)
                or not _valid_nullable_integer(row["successful_tasks"])
                or not _valid_nullable_integer(row["total_tasks"])
                or not isinstance(row.get("case_scores"), dict)
                or any(
                    not _valid_public_text(case_id, maximum=64) or _number(score, minimum=0) is None
                    for case_id, score in row["case_scores"].items()
                )
            ):
                raise DashboardDataError(f"case_scores non valido nel run {run['id']}")
        for task in run["tasks"]:
            task = _require_exact_fields(task, TASK_FIELDS, label=f"task di {run['id']}")
            if (
                any(
                    not _valid_public_text(task[key], maximum=maximum)
                    for key, maximum in (
                        ("model", 256),
                        ("case_id", 64),
                        ("case_title", 200),
                        ("case_title_en", 200),
                        ("category", 64),
                        ("status", 32),
                    )
                )
                or task["state"]
                not in {"passed", "below_threshold", "timeout", "error", "missing_score", "integrity_excluded"}
                or _integer(task["repetition"], minimum=1) is None
                or any(
                    not _valid_nullable_number(task[key])
                    for key in ("score", "max_score", "duration_seconds", "cpu_seconds", "energy_joules")
                )
                or any(
                    not _valid_nullable_integer(task[key]) for key in ("output_tokens", "tool_calls", "tool_errors")
                )
                or (task["integrity_valid"] is not None and not isinstance(task["integrity_valid"], bool))
            ):
                raise DashboardDataError(f"Task non valida nel run {run['id']}")
    funnel_profiles = [item.get("profile") for item in funnel if isinstance(item, dict)] if isinstance(funnel, list) else []
    expected_funnel_profiles = (
        profiles if dashboard_schema == 1 else [profile for profile in FUNNEL_PIPELINE if profile in profiles]
    )
    if not isinstance(funnel, list) or funnel_profiles != expected_funnel_profiles:
        raise DashboardDataError("Funnel non coerente con profile_order")
    for stage in funnel:
        stage = _require_exact_fields(stage, FUNNEL_FIELDS, label="funnel")
        if stage["profile"] not in profiles or (stage["next_profile"] is not None and stage["next_profile"] not in profiles):
            raise DashboardDataError("Profili non validi nel funnel")
        for key in ("run_ids", "participants", "new_participants", "continued_to_next", "not_run_in_next"):
            _validate_public_string_list(stage.get(key), label=f"{key} del funnel", maximum=256)


def write_dashboard_data(
    run_dirs: Iterable[Path],
    output_path: Path,
    *,
    workspace_root: Path | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Write a validated dataset atomically without modifying source run directories."""
    resolved_dirs = [Path(path).resolve() for path in run_dirs]
    output = Path(output_path).resolve()
    if workspace_root is not None:
        root = workspace_root.resolve()
        if not _inside(output, root) or any(not _inside(run_dir, root) for run_dir in resolved_dirs):
            raise DashboardDataError("Input e output dashboard devono restare nella root del progetto")
    if any(_inside(output, run_dir) for run_dir in resolved_dirs):
        raise DashboardDataError("L'output dashboard non può modificare una directory sorgente")
    if output.exists() and not overwrite:
        raise DashboardDataError(f"Output già esistente: {output}; usare --force per sostituirlo")
    dataset = build_dashboard_data(resolved_dirs)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            json.dump(dataset, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, output)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)
    return dataset
