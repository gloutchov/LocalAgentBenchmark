"""Benchmark orchestration and artifact capture."""

from __future__ import annotations

import hashlib
import json
import platform
import random
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .case_sdk import CASE_SCHEMA_VERSION
from .config import BenchmarkConfig, CaseSpec
from . import __version__
from .grading import grade_workspace
from .integrity import (
    InputIntegrityError,
    changed_paths,
    repository_fingerprints,
    repository_metadata,
    require_clean_inputs,
    snapshot_cases,
    verify_snapshot,
)
from .ollama import OllamaModel, ThinkingPreflight
from .pi_adapter import (
    AUDIT_VERSION,
    SCRATCH_DIRECTORY,
    audit_workspace_accesses,
    run_pi,
    write_models_config,
)
from .pi_compatibility import PiCompatibility, REFERENCE_PI_VERSION, check_pi_compatibility
from .provider_adapter import create_provider
from .report import write_report
from .sandbox import SandboxError, sandbox_capability, select_sandbox
from .system_metrics import hardware_snapshot
from .thinking import (
    THINKING_CONTROL_VERSION,
    ThinkingPolicy,
    metrics_show_thinking,
    resolve_thinking_policy,
)


class BenchmarkError(RuntimeError):
    """Raised for failures that prevent a benchmark run from starting."""


EXECUTION_POLICY = f"""# Confine di esecuzione del benchmark / Benchmark execution boundary

- Opera soltanto nella directory di lavoro corrente e nei suoi discendenti. Non leggere, elencare, copiare o modificare altri path, inclusi repository reali e directory sorelle.
- Work only in the current working directory and its descendants. Do not read, list, copy, or modify any other path, including real repositories and sibling directories.
- Non usare directory temporanee di sistema come `/tmp`. Per smoke test e file temporanei usa `{SCRATCH_DIRECTORY}/`, che il runner prepara e ignora in Git.
- Do not use system temporary directories such as `/tmp`. Use `{SCRATCH_DIRECTORY}/` for smoke tests and temporary files; the runner prepares it and excludes it from Git.
- Non accedere alla rete con shell, interpreti, package manager o Git. Tutti gli input necessari sono già nella workspace; segnala come limite un eventuale materiale mancante senza cercarlo altrove.
- Do not access the network through shell commands, interpreters, package managers, or Git. All required inputs are already in the workspace; report missing material as a limitation instead of searching elsewhere.
- Per testare un rifiuto di traversal, crea una sottodirectory dentro `{SCRATCH_DIRECTORY}/` e usa quella come workspace dell'applicazione, così anche il path di prova resta nel confine del benchmark.
- To test traversal rejection, create a nested directory under `{SCRATCH_DIRECTORY}/` and use it as the application workspace, so the attempted test path remains inside the benchmark boundary.

Un riferimento esplicito fuori da questo confine o un tentativo di rete invalida il risultato anche quando il comando fallisce.
An explicit reference outside this boundary or a network attempt invalidates the result even if the command fails.
"""


def _slug(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-.")
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"{safe[:60] or 'model'}-{digest}"


def _command_version(command: list[str]) -> str | None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = (result.stdout or result.stderr).strip().splitlines()
    return value[0] if value else None


def _git(workspace: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=workspace, capture_output=True, text=True, check=check, timeout=30
    )


def _prepare_workspace(
    config: BenchmarkConfig,
    case: CaseSpec,
    destination: Path,
    agents_path: Path | None = None,
    gitignore_path: Path | None = None,
) -> str:
    shutil.copytree(case.fixture_path, destination, symlinks=True)
    shutil.copy2(gitignore_path or config.root / ".gitignore", destination / ".gitignore")
    shutil.copy2(agents_path or config.root / "AGENTS.md", destination / "AGENTS.md")
    try:
        _git(destination, "init", "-q", "-b", "main")
    except subprocess.CalledProcessError:
        _git(destination, "init", "-q")
        _git(destination, "branch", "-M", "main")
    _git(destination, "config", "user.name", "LocalAgent Benchmark")
    _git(destination, "config", "user.email", "benchmark@localhost")
    _git(destination, "add", ".")
    _git(destination, "commit", "-q", "-m", "benchmark baseline")
    baseline_commit = _git(destination, "rev-parse", "HEAD").stdout.strip()
    scratch = destination / SCRATCH_DIRECTORY
    scratch.mkdir(parents=True, exist_ok=True)
    exclude_path = destination / ".git" / "info" / "exclude"
    exclude_entry = f"/{SCRATCH_DIRECTORY}/"
    exclude_lines = exclude_path.read_text(encoding="utf-8").splitlines() if exclude_path.exists() else []
    if exclude_entry not in exclude_lines:
        exclude_path.parent.mkdir(parents=True, exist_ok=True)
        exclude_path.write_text("\n".join([*exclude_lines, exclude_entry, ""]), encoding="utf-8")
    return baseline_commit


def _write_manifest(run_dir: Path, manifest: dict[str, Any]) -> None:
    (run_dir / "run.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _record_integrity_violation(
    manifest: dict[str, Any],
    *,
    model: str,
    case_id: str,
    repetition: int,
    kind: str,
    details: list[Any],
) -> None:
    integrity = manifest["integrity"]
    integrity["status"] = "violations_detected"
    integrity["violations"].append(
        {
            "model": model,
            "case_id": case_id,
            "repetition": repetition,
            "kind": kind,
            "details": details,
        }
    )


def _capture_git(workspace: Path, baseline_commit: str) -> tuple[str, str, str]:
    status = _git(workspace, "status", "--short", "--branch", check=False).stdout
    _git(workspace, "add", "-N", ".", check=False)
    diff = _git(workspace, "diff", "--no-ext-diff", baseline_commit, "--", check=False).stdout
    branch = _git(workspace, "branch", "--show-current", check=False).stdout.strip()
    return status, diff, branch


def _resolve_models(config: BenchmarkConfig, requested: list[str] | None, installed: list[OllamaModel]) -> list[str]:
    installed_names = {model.name for model in installed}
    if requested:
        selected = requested
    elif config.models == "installed":
        selected = [model.name for model in installed]
    else:
        selected = list(config.models)
    missing = [model for model in selected if model not in installed_names]
    if missing:
        raise BenchmarkError(f"Modelli non disponibili nel provider locale: {', '.join(missing)}")
    if not selected:
        raise BenchmarkError("Nessun modello locale selezionato")
    return list(dict.fromkeys(selected))


def _resolve_cases(config: BenchmarkConfig, profile: str, requested: list[str] | None) -> list[CaseSpec]:
    if requested:
        unknown = set(requested) - set(config.cases)
        if unknown:
            raise BenchmarkError(f"Casi sconosciuti: {', '.join(sorted(unknown))}")
        ids = requested
    else:
        try:
            ids = list(config.profiles[profile])
        except KeyError as exc:
            raise BenchmarkError(f"Profilo sconosciuto: {profile}") from exc
    return [config.cases[case_id] for case_id in dict.fromkeys(ids)]


def _build_task_order(
    models: list[str],
    cases: list[CaseSpec],
    repetitions: int,
    seed: int,
) -> list[dict[str, str | int]]:
    tasks: list[dict[str, str | int]] = [
        {"model": model, "case_id": case.id, "repetition": repetition}
        for model in models
        for case in cases
        for repetition in range(1, repetitions + 1)
    ]
    random.Random(seed).shuffle(tasks)
    return tasks


def doctor(config: BenchmarkConfig, cancel_event: threading.Event | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    pi_path = shutil.which(config.pi_command[0])
    pi_version = _command_version([*config.pi_command, "--version"]) if pi_path else None
    try:
        probe_sandbox = select_sandbox(config.defaults.sandbox)
    except SandboxError:
        probe_sandbox = None
    pi_compatibility = (
        check_pi_compatibility(config.pi_command, config.defaults.pi_contract_timeout_seconds, probe_sandbox, cancel_event,
                               **({"provider_kind": config.provider_kind} if config.provider_kind != "ollama" else {}))
        if pi_path and probe_sandbox else PiCompatibility("failed", 1, (), "pi_missing" if not pi_path else "sandbox_unavailable")
    )
    if cancel_event is not None and cancel_event.is_set():
        return {"ok": False, "checks": [{"name": "pi", "ok": False, "detail": "cancelled"}], "models": []}
    checks.append(
        {
            "name": "pi",
            "ok": pi_compatibility.passed,
            "detail": (
                f"{pi_path}; versione {pi_version or 'sconosciuta'}; contratto Pi v{pi_compatibility.contract_version} superato"
                if pi_compatibility.passed else
                f"versione Pi {pi_version or 'sconosciuta'}; controllo {pi_compatibility.failed_check or 'non verificabile'} fallito. "
                f"Pi {REFERENCE_PI_VERSION} è la versione di riferimento verificata / Pi {REFERENCE_PI_VERSION} is the verified reference version"
            ),
            "compatibility": pi_compatibility.to_manifest(),
        }
    )
    git_path = shutil.which("git")
    checks.append({"name": "git", "ok": git_path is not None, "detail": git_path or "comando non trovato"})
    try:
        provider = create_provider(config)
        models = provider.list_models()
        inspected: list[OllamaModel] = []
        for model in models:
            try:
                inspected.append(provider.inspect_model(model))
            except Exception:
                inspected.append(model)
        models = inspected
        provider_version = provider.version()
        checks.append(
            {
                "name": config.provider_kind,
                "ok": True,
                "detail": f"{provider_version or 'versione non dichiarata'}; {len(models)} modelli",
            }
        )
    except Exception as exc:  # a doctor must report all checks
        models = []
        checks.append({"name": config.provider_kind, "ok": False, "detail": str(exc)})
    checks.append({"name": "config", "ok": True, "detail": f"{len(config.cases)} casi validi"})
    sandbox = sandbox_capability()
    sandbox_detail = (
        f"{sandbox['backend']} disponibile; default={config.defaults.sandbox}"
        if sandbox["available"]
        else f"audit-only; {sandbox['detail']}"
    )
    sandbox_ok = config.defaults.sandbox != "required" or bool(sandbox["available"])
    checks.append({"name": "sandbox", "ok": sandbox_ok, "detail": sandbox_detail})
    try:
        require_clean_inputs(config.root, config.cases.values())
    except InputIntegrityError as exc:
        checks.append({"name": "inputs", "ok": False, "detail": str(exc).splitlines()[0]})
    else:
        checks.append(
            {
                "name": "inputs",
                "ok": True,
                "detail": "AGENTS, .gitignore, manifesti, prompt, fixture, grader e rubriche puliti",
            }
        )
    requested_policy = resolve_thinking_policy(config.defaults.thinking)
    model_rows: list[dict[str, Any]] = []
    for model in models:
        if requested_policy.active and model.thinking_capable is False:
            compatibility = "incompatible"
        elif requested_policy.active and model.thinking_capable is None:
            compatibility = "unknown"
        else:
            compatibility = "preflight_required"
        model_rows.append(
            {
                **asdict(model),
                "thinking_requested": requested_policy.requested,
                "reasoning_effort": requested_policy.reasoning_effort,
                "thinking_compatibility": compatibility,
            }
        )
    return {"ok": all(check["ok"] for check in checks), "checks": checks, "models": model_rows}


def run_benchmark(
    config: BenchmarkConfig,
    *,
    profile: str,
    requested_models: list[str] | None,
    requested_cases: list[str] | None,
    repetitions: int | None,
    timeout_seconds: int | None,
    thinking_level: str | None,
    use_warmup: bool | None,
    output_dir: Path | None,
    order_seed: int | None = None,
    sandbox_mode: str | None = None,
) -> Path:
    cases = _resolve_cases(config, profile, requested_cases)
    try:
        require_clean_inputs(config.root, cases)
    except InputIntegrityError as exc:
        raise BenchmarkError(str(exc)) from exc
    pi_version = _command_version([*config.pi_command, "--version"])
    try:
        sandbox = select_sandbox(sandbox_mode or config.defaults.sandbox)
    except SandboxError as exc:
        raise BenchmarkError(str(exc)) from exc
    pi_compatibility = check_pi_compatibility(
        config.pi_command, config.defaults.pi_contract_timeout_seconds, sandbox,
        **({"provider_kind": config.provider_kind} if config.provider_kind != "ollama" else {})
    )
    if not pi_compatibility.passed:
        raise BenchmarkError(
            f"Controllo compatibilità Pi fallito ({pi_compatibility.failed_check}): "
            f"versione {pi_version or 'sconosciuta'}. "
            f"Pi {REFERENCE_PI_VERSION} è la versione di riferimento verificata / "
            f"Pi {REFERENCE_PI_VERSION} is the verified reference version"
        )
    provider = create_provider(config)
    installed = provider.list_models()
    models = _resolve_models(config, requested_models, installed)
    installed = [provider.fingerprint_model(item) if item.name in models else item for item in installed]
    repeat_count = repetitions or config.defaults.repetitions
    timeout = timeout_seconds or config.defaults.timeout_seconds
    thinking_policy = resolve_thinking_policy(thinking_level or config.defaults.thinking)
    if repeat_count < 1 or timeout < 10:
        raise BenchmarkError("Ripetizioni e timeout devono essere positivi")
    should_warmup = config.defaults.warmup if use_warmup is None else use_warmup
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = (output_dir or config.root / "results" / timestamp).resolve()
    if run_dir.exists() and any(run_dir.iterdir()):
        raise BenchmarkError(f"Directory output non vuota: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    context_dir = run_dir / "benchmark-context"
    try:
        frozen_cases, input_manifest = snapshot_cases(
            cases,
            context_dir,
            config.root / "AGENTS.md",
            config.root / ".gitignore",
            EXECUTION_POLICY,
        )
    except InputIntegrityError as exc:
        raise BenchmarkError(str(exc)) from exc
    frozen_by_id = {case.id: case for case in frozen_cases}
    repository_state = repository_fingerprints(config.root, (run_dir,))
    installed_by_name: dict[str, OllamaModel] = {}
    for name in models:
        base_model = next(item for item in installed if item.name == name)
        try:
            installed_by_name[name] = provider.inspect_model(
                base_model,
                timeout=min(config.defaults.thinking_preflight_timeout_seconds, timeout),
            )
        except Exception:
            installed_by_name[name] = base_model
    seed = order_seed if order_seed is not None else secrets.randbits(64)
    tasks = _build_task_order(models, cases, repeat_count, seed)
    manifest = {
        "schema_version": 4,
        "benchmark_version": __version__,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "models": models,
        "cases": [case.id for case in cases],
        "repetitions": repeat_count,
        "timeout_seconds": timeout,
        "thinking": thinking_policy.requested,
        "warmup": should_warmup,
        "warmup_events": [],
        "load_events": [],
        "order_seed": seed,
        "task_order": tasks,
        "repository": repository_metadata(config.root),
        "inputs": input_manifest,
        "execution_policy": {
            "audit_version": AUDIT_VERSION,
            "sha256": input_manifest.get("execution_policy_sha256"),
            "scratch_directory": SCRATCH_DIRECTORY,
            "network_access": "forbidden",
            "filesystem_scope": "task_workspace",
        },
        "sandbox": sandbox.to_dict(),
        "configuration": {
            "provider_kind": config.provider_kind,
            "provider_url": config.ollama_url,
            "pi_command": list(config.pi_command),
            "ollama_url": config.ollama_url,
            "timeout_seconds": timeout,
            "repetitions": repeat_count,
            "thinking": thinking_policy.requested,
            "reasoning_effort": thinking_policy.reasoning_effort,
            "thinking_preflight_timeout_seconds": config.defaults.thinking_preflight_timeout_seconds,
            "pi_contract_timeout_seconds": config.defaults.pi_contract_timeout_seconds,
            "http_idle_timeout_ms": config.defaults.http_idle_timeout_ms,
            "agent_max_retries": config.defaults.agent_max_retries,
            "provider_max_retries": config.defaults.provider_max_retries,
            "warmup": should_warmup,
            "keep_alive": config.defaults.keep_alive,
            "context_window": config.defaults.context_window,
            "max_tokens": config.defaults.max_tokens,
            "temperature": config.defaults.temperature,
        },
        "integrity": {"status": "passed", "aborted": False, "violations": []},
        "thinking_control": {
            **thinking_policy.to_manifest(),
            "status": "pending",
            "preflights": {},
            "disqualified_models": [],
            "retry_policy": {
                "agent_max_retries": config.defaults.agent_max_retries,
                "provider_max_retries": config.defaults.provider_max_retries,
            },
            "http_idle_timeout_ms": config.defaults.http_idle_timeout_ms,
        },
        "pi_compatibility": pi_compatibility.to_manifest(),
        "environment": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "pi": pi_version,
            "ollama": provider.version() if provider.kind == "ollama" else None,
            "provider_kind": config.provider_kind,
            "provider_version": provider.version(),
            "provider_version_source": provider.version_source,
            "hardware": hardware_snapshot(),
        },
        "model_metadata": {name: asdict(installed_by_name[name]) for name in models},
    }
    _write_manifest(run_dir, manifest)

    preflight_by_model: dict[str, ThinkingPreflight] = {}
    disqualified_thinking: set[str] = set()
    for model in models:
        try:
            provider.unload(model)
        except Exception:
            pass
        print(
            f"[thinking preflight] {model} · {thinking_policy.requested}"
            f"/{thinking_policy.reasoning_effort}",
            flush=True,
        )
        preflight = provider.preflight_thinking(
            installed_by_name[model], thinking_policy,
            timeout=min(config.defaults.thinking_preflight_timeout_seconds, timeout),
        )
        preflight_by_model[model] = preflight
        manifest["thinking_control"]["preflights"][model] = asdict(preflight)
        if provider.infer_capability_from_preflight and preflight.passed and thinking_policy.active and installed_by_name[model].thinking_capable is None:
            installed_by_name[model] = replace(
                installed_by_name[model], thinking_capable=True,
                capabilities=("completion", "thinking"), capabilities_known=True,
            )
            manifest["model_metadata"][model] = asdict(installed_by_name[model])
        if not preflight.passed:
            disqualified_thinking.add(model)
            manifest["integrity"]["status"] = "violations_detected"
            manifest["integrity"]["violations"].append(
                {
                    "model": model,
                    "case_id": "__preflight__",
                    "repetition": 0,
                    "kind": "thinking_control_unverified",
                    "details": [{"status": preflight.status}],
                }
            )
        try:
            provider.unload(model)
        except Exception:
            pass
    manifest["thinking_control"]["disqualified_models"] = sorted(disqualified_thinking)
    if not disqualified_thinking:
        manifest["thinking_control"]["status"] = "passed"
    elif len(disqualified_thinking) == len(models):
        manifest["thinking_control"]["status"] = "failed"
    else:
        manifest["thinking_control"]["status"] = "partial"
    _write_manifest(run_dir, manifest)

    active_model: str | None = None
    protected_paths = (config.root,)
    for current, task in enumerate(tasks, 1):
        model = str(task["model"])
        if model in disqualified_thinking:
            continue
        case_id = str(task["case_id"])
        repetition = int(task["repetition"])
        case = frozen_by_id[case_id]
        snapshot_before = verify_snapshot(context_dir, input_manifest)
        if snapshot_before:
            manifest["integrity"]["status"] = "snapshot_compromised"
            manifest["integrity"]["aborted"] = True
            manifest["integrity"]["violations"].append(
                {"kind": "snapshot_changed_before_task", "details": snapshot_before}
            )
            break
        if active_model != model:
            if active_model is not None:
                try:
                    provider.unload(active_model)
                except Exception as exc:
                    print(f"[avviso] unload fallito per {active_model}: {exc}", file=sys.stderr, flush=True)
            if provider.explicit_load:
                load_started = time.monotonic()
                try:
                    provider.load(model, timeout=min(timeout, 300))
                except Exception as exc:
                    manifest["load_events"].append({
                        "sequence": current, "model": model, "status": "failed",
                        "duration_ms": max(0, round((time.monotonic() - load_started) * 1000)),
                        "error_type": type(exc).__name__,
                    })
                    disqualified_thinking.add(model)
                    manifest["thinking_control"]["disqualified_models"] = sorted(disqualified_thinking)
                    manifest["thinking_control"]["status"] = "failed" if len(disqualified_thinking) == len(models) else "partial"
                    _record_integrity_violation(
                        manifest, model=model, case_id="__load__", repetition=0,
                        kind="provider_load_failed", details=[{"error_type": type(exc).__name__}],
                    )
                    _write_manifest(run_dir, manifest)
                    active_model = None
                    continue
                manifest["load_events"].append({
                    "sequence": current, "model": model, "status": "loaded",
                    "duration_ms": max(0, round((time.monotonic() - load_started) * 1000)),
                })
            if should_warmup:
                print(f"[warmup] {model}", flush=True)
                event: dict[str, Any] = {"sequence": current, "model": model}
                try:
                    warmup_result = provider.warmup(
                        model, thinking_policy, timeout=min(timeout, 300),
                        context_window=config.defaults.context_window,
                    )
                    event["metrics"] = {
                        key: warmup_result.get(key)
                        for key in ("total_duration", "load_duration", "prompt_eval_count", "eval_count", "eval_duration")
                        if key in warmup_result
                    }
                except Exception as exc:
                    event["error"] = str(exc)
                    print(f"[avviso] warmup fallito per {model}: {exc}", file=sys.stderr, flush=True)
                manifest["warmup_events"].append(event)
                _write_manifest(run_dir, manifest)
            active_model = model

        case_dir = run_dir / "models" / _slug(model) / "cases" / f"{case.id}-r{repetition}"
        workspace = case_dir / "workspace"
        agent_dir = case_dir / ".pi-agent"
        case_dir.mkdir(parents=True, exist_ok=True)
        manual_rubric: dict[str, object] | None = None
        if case.manual_rubric_path is not None:
            rubric_artifact = case_dir / "manual-rubric.md"
            shutil.copy2(case.manual_rubric_path, rubric_artifact)
            manual_rubric = {
                "path": rubric_artifact.name,
                "max_score": case.manual_rubric_max_score,
                "included_in_automatic_score": False,
            }
        write_models_config(
            agent_dir,
            config.ollama_url,
            [installed_by_name[model]],
            config.defaults.context_window,
            config.defaults.max_tokens,
            config.defaults.temperature,
            thinking_policy,
            http_idle_timeout_ms=config.defaults.http_idle_timeout_ms,
            agent_max_retries=config.defaults.agent_max_retries,
            provider_max_retries=config.defaults.provider_max_retries,
            provider_kind=config.provider_kind,
        )
        baseline_commit = _prepare_workspace(
            config,
            case,
            workspace,
            context_dir / "AGENTS.snapshot.md",
            context_dir / ".gitignore.snapshot",
        )
        baseline_tree = _git(workspace, "rev-parse", f"{baseline_commit}^{{tree}}").stdout.strip()
        prompt = "\n\n".join(
            (
                (context_dir / "EXECUTION_POLICY.snapshot.md").read_text(encoding="utf-8").rstrip(),
                case.prompt_path.read_text(encoding="utf-8").lstrip(),
            )
        )
        print(f"[{current}/{len(tasks)}] {model} · {case.id} · ripetizione {repetition}", flush=True)
        before_task_repository = repository_state
        try:
            pi_run = run_pi(
                config.pi_command,
                model,
                thinking_policy.requested,
                prompt,
                workspace,
                agent_dir,
                timeout,
                sandbox,
                config.ollama_url,
                provider_kind=config.provider_kind,
            )
        except SandboxError as exc:
            raise BenchmarkError(f"Avvio sandbox fallito: {exc}") from exc
        after_task_repository = repository_fingerprints(config.root, (run_dir,))
        source_mutations = changed_paths(before_task_repository, after_task_repository)
        repository_state = after_task_repository
        snapshot_mutations = verify_snapshot(context_dir, input_manifest)
        external_accesses = audit_workspace_accesses(pi_run.stdout, workspace, protected_paths)
        thinking_violations: list[dict[str, Any]] = []
        if not thinking_policy.active and metrics_show_thinking(pi_run.metrics):
            thinking_violations.append(
                {
                    "reason": "unexpected_thinking",
                    "streamed_thinking_chars": int(pi_run.metrics.get("streamed_thinking_chars", 0)),
                    "reasoning_tokens": int(pi_run.metrics.get("usage", {}).get("reasoning", 0)),
                }
            )
        retry_events = pi_run.metrics.get("retry_events", 0)
        if (
            config.defaults.agent_max_retries == 0
            and isinstance(retry_events, (int, float))
            and not isinstance(retry_events, bool)
            and retry_events > 0
        ):
            thinking_violations.append(
                {"reason": "unexpected_retry", "retry_events": int(retry_events)}
            )
        valid_for_ranking = not (
            source_mutations or snapshot_mutations or external_accesses or thinking_violations
        )
        if source_mutations:
            _record_integrity_violation(
                manifest,
                model=model,
                case_id=case.id,
                repetition=repetition,
                kind="repository_mutation",
                details=source_mutations,
            )
        if external_accesses:
            _record_integrity_violation(
                manifest,
                model=model,
                case_id=case.id,
                repetition=repetition,
                kind="external_workspace_access",
                details=external_accesses,
            )
        if thinking_violations:
            _record_integrity_violation(
                manifest,
                model=model,
                case_id=case.id,
                repetition=repetition,
                kind="thinking_control_violation",
                details=thinking_violations,
            )
        if snapshot_mutations:
            manifest["integrity"]["status"] = "snapshot_compromised"
            manifest["integrity"]["aborted"] = True
            manifest["integrity"]["violations"].append(
                {
                    "model": model,
                    "case_id": case.id,
                    "repetition": repetition,
                    "kind": "snapshot_mutation",
                    "details": snapshot_mutations,
                }
            )
            grade = {
                "score": 0,
                "max_score": 100,
                "checks": [],
                "error": "Grader non eseguito: snapshot degli input modificato durante la task",
            }
        else:
            grade = grade_workspace(case, workspace)
        git_status, diff, branch = _capture_git(workspace, baseline_commit)
        (case_dir / "pi-events.jsonl").write_text(pi_run.stdout, encoding="utf-8")
        (case_dir / "stderr.log").write_text(pi_run.stderr, encoding="utf-8")
        (case_dir / "final-response.md").write_text(pi_run.final_response, encoding="utf-8")
        (case_dir / "diff.patch").write_text(diff, encoding="utf-8")
        (case_dir / "git-status.txt").write_text(git_status, encoding="utf-8")
        (case_dir / "grade.json").write_text(json.dumps(grade, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        result = {
            "schema_version": 4,
            "model": model,
            "case_id": case.id,
            "case_title": case.title,
            "case_title_en": case.title_en,
            "case_category": case.category,
            "case_weight": case.weight,
            "case_manifest_schema_version": CASE_SCHEMA_VERSION if case.manifest_path else None,
            "manual_rubric": manual_rubric,
            "repetition": repetition,
            "status": pi_run.status,
            "exit_code": pi_run.exit_code,
            "duration_seconds": pi_run.duration_seconds,
            "metrics": pi_run.metrics,
            "thinking_control": {
                **thinking_policy.to_manifest(),
                "preflight": preflight_by_model[model].status,
                "thinking_observed": metrics_show_thinking(pi_run.metrics),
                "retry_policy": manifest["thinking_control"]["retry_policy"],
                "http_idle_timeout_ms": config.defaults.http_idle_timeout_ms,
            },
            "system_metrics": pi_run.system_metrics,
            "sandbox": pi_run.sandbox or sandbox.to_dict(),
            "grade": grade,
            "git_branch": branch,
            "baseline_commit": baseline_commit,
            "baseline_tree": baseline_tree,
            "input_fingerprint": input_manifest["cases"][case.id]["effective_input_sha256"],
            "integrity": {
                "audit_version": AUDIT_VERSION,
                "valid_for_ranking": valid_for_ranking,
                "source_mutations": source_mutations,
                "snapshot_mutations": snapshot_mutations,
                "external_accesses": external_accesses,
                "thinking_control_violations": thinking_violations,
            },
            "command": pi_run.command,
        }
        (case_dir / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        _write_manifest(run_dir, manifest)
        print(
            f"      stato={pi_run.status} score={grade.get('score', 0)}/100 "
            f"integrità={'ok' if valid_for_ranking else 'violata'} tempo={pi_run.duration_seconds:.1f}s",
            flush=True,
        )
        write_report(run_dir)
        if snapshot_mutations:
            break

    if active_model is not None:
        try:
            provider.unload(active_model)
        except Exception as exc:
            print(f"[avviso] unload fallito per {active_model}: {exc}", file=sys.stderr, flush=True)

    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_manifest(run_dir, manifest)
    write_report(run_dir)
    return run_dir
