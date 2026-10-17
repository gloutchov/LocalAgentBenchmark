"""Statistical comparison across compatible benchmark runs."""

from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ComparisonError(ValueError):
    """Raised when run artifacts are missing or not comparable."""


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ComparisonError(f"Impossibile leggere {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ComparisonError(f"Oggetto JSON atteso in {path}")
    return value


def _input_signature(manifest: dict[str, Any], report: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    cases = manifest.get("inputs", {}).get("cases", {})
    if isinstance(cases, dict):
        signature = []
        for case_id, metadata in cases.items():
            fingerprint = metadata.get("effective_input_sha256") if isinstance(metadata, dict) else None
            if isinstance(fingerprint, str) and fingerprint:
                signature.append((str(case_id), fingerprint))
        if signature:
            return tuple(sorted(signature))
    fallback: dict[str, str] = {}
    for result in report.get("results", []):
        if not isinstance(result, dict):
            continue
        case_id = result.get("case_id")
        fingerprint = result.get("input_fingerprint")
        if isinstance(case_id, str) and isinstance(fingerprint, str) and fingerprint:
            fallback[case_id] = fingerprint
    return tuple(sorted(fallback.items()))


def _compatibility_signature(manifest: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    sandbox = manifest.get("sandbox", {})
    if not isinstance(sandbox, dict):
        sandbox = {}
    environment = manifest.get("environment", {})
    if not isinstance(environment, dict):
        environment = {}
    hardware = environment.get("hardware", {})
    if not isinstance(hardware, dict):
        hardware = {}
    configuration = manifest.get("configuration", {})
    if not isinstance(configuration, dict):
        configuration = {}
    policy = manifest.get("execution_policy", {})
    if not isinstance(policy, dict):
        policy = {}
    report_integrity = report.get("integrity", {})
    if not isinstance(report_integrity, dict):
        report_integrity = {}
    thinking_control = manifest.get("thinking_control", {})
    if not isinstance(thinking_control, dict):
        thinking_control = {}
    retry_policy = thinking_control.get("retry_policy", {})
    if not isinstance(retry_policy, dict):
        retry_policy = {}
    model_metadata = manifest.get("model_metadata", {})
    capability_signature: list[tuple[str, bool | None, tuple[str, ...]]] = []
    if isinstance(model_metadata, dict):
        for model, raw in sorted(model_metadata.items(), key=lambda item: str(item[0])):
            details = raw if isinstance(raw, dict) else {}
            raw_capabilities = details.get("capabilities", [])
            capabilities = (
                tuple(sorted(str(item) for item in raw_capabilities if isinstance(item, str)))
                if isinstance(raw_capabilities, (list, tuple))
                else ()
            )
            capable = details.get("thinking_capable")
            capability_signature.append(
                (str(model), capable if isinstance(capable, bool) else None, capabilities)
            )
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        cases = sorted({str(item.get("case_id")) for item in report.get("results", []) if isinstance(item, dict)})
    return {
        "run_schema_version": manifest.get("schema_version"),
        "benchmark_version": manifest.get("benchmark_version"),
        "profile": manifest.get("profile"),
        "cases": tuple(str(item) for item in cases),
        "inputs": _input_signature(manifest, report),
        "sandbox_backend": sandbox.get("backend", "audit-only"),
        "sandbox_enforced": bool(sandbox.get("enforced", False)),
        "execution_policy_sha256": policy.get("sha256"),
        "audit_version": report_integrity.get("audit_version", policy.get("audit_version")),
        "timeout_seconds": configuration.get("timeout_seconds", manifest.get("timeout_seconds")),
        "repetitions": configuration.get("repetitions", manifest.get("repetitions")),
        "thinking": configuration.get("thinking", manifest.get("thinking")),
        "thinking_control_version": thinking_control.get("version", 0),
        "thinking_control_status": thinking_control.get("status", "unverified"),
        "reasoning_effort": thinking_control.get("reasoning_effort"),
        "thinking_control_source": thinking_control.get("source", "legacy_unverified"),
        "agent_max_retries": retry_policy.get(
            "agent_max_retries", configuration.get("agent_max_retries")
        ),
        "provider_max_retries": retry_policy.get(
            "provider_max_retries", configuration.get("provider_max_retries")
        ),
        "http_idle_timeout_ms": thinking_control.get(
            "http_idle_timeout_ms", configuration.get("http_idle_timeout_ms")
        ),
        "pi_version": environment.get("pi"),
        "pi_contract_version": (manifest.get("pi_compatibility") or {}).get("contract_version", 0),
        "pi_contract_status": (manifest.get("pi_compatibility") or {}).get("status", "unverified"),
        "ollama_version": environment.get("ollama"),
        "model_capabilities": tuple(capability_signature),
        "warmup": configuration.get("warmup", manifest.get("warmup")),
        "context_window": configuration.get("context_window"),
        "max_tokens": configuration.get("max_tokens"),
        "temperature": configuration.get("temperature"),
        "platform": environment.get("platform"),
        "machine": hardware.get("machine"),
        "logical_cpu_count": hardware.get("logical_cpu_count"),
    }


def _distribution(
    values: list[float],
    *,
    lower_bound: float | None = None,
    upper_bound: float | None = None,
) -> dict[str, float | int]:
    count = len(values)
    mean = statistics.fmean(values)
    stddev = statistics.stdev(values) if count > 1 else 0.0
    margin = 1.96 * stddev / math.sqrt(count) if count > 1 else 0.0
    low = mean - margin
    high = mean + margin
    if lower_bound is not None:
        low = max(lower_bound, low)
    if upper_bound is not None:
        high = min(upper_bound, high)
    return {
        "count": count,
        "mean": round(mean, 4),
        "median": round(statistics.median(values), 4),
        "stddev": round(stddev, 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "ci95_low": round(low, 4),
        "ci95_high": round(high, 4),
    }


def build_comparison(run_dirs: list[Path]) -> dict[str, Any]:
    if not run_dirs:
        raise ComparisonError("Specificare almeno una directory di run")
    resolved_dirs = [raw_path.resolve() for raw_path in run_dirs]
    if len(set(resolved_dirs)) != len(resolved_dirs):
        raise ComparisonError("Ogni directory di run può essere specificata una sola volta")
    if len({path.name for path in resolved_dirs}) != len(resolved_dirs):
        raise ComparisonError("Le directory di run devono avere nomi distinti")
    loaded: list[tuple[Path, dict[str, Any], dict[str, Any]]] = []
    for run_dir in resolved_dirs:
        manifest = _load_object(run_dir / "run.json")
        report = _load_object(run_dir / "report.json")
        if report.get("schema_version") not in {2, 3, 4}:
            raise ComparisonError(f"Schema report non supportato in {run_dir.name}")
        loaded.append((run_dir, manifest, report))

    reference = _compatibility_signature(loaded[0][1], loaded[0][2])
    mismatches: list[dict[str, Any]] = []
    for run_dir, manifest, report in loaded[1:]:
        current = _compatibility_signature(manifest, report)
        differing = sorted(key for key in reference if current.get(key) != reference.get(key))
        if differing:
            mismatches.append({"run": run_dir.name, "fields": differing})
    if mismatches:
        detail = "; ".join(f"{item['run']}: {', '.join(item['fields'])}" for item in mismatches)
        raise ComparisonError(f"Run non comparabili ({detail})")

    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    digests: dict[str, set[str]] = defaultdict(set)
    disqualified_by_run: dict[str, list[str]] = {}
    for run_dir, manifest, report in loaded:
        integrity = report.get("integrity", {})
        disqualified = integrity.get("disqualified_models", []) if isinstance(integrity, dict) else []
        disqualified_by_run[run_dir.name] = [str(item) for item in disqualified]
        metadata = manifest.get("model_metadata", {})
        if isinstance(metadata, dict):
            for model, details in metadata.items():
                digest = details.get("digest") if isinstance(details, dict) else None
                if isinstance(digest, str) and digest:
                    digests[str(model)].add(digest)
        for row in report.get("leaderboard", []):
            if isinstance(row, dict) and isinstance(row.get("model"), str):
                samples[row["model"]].append(row)
    changed_models = sorted(model for model, values in digests.items() if len(values) > 1)
    if changed_models:
        raise ComparisonError("Digest Ollama divergente per: " + ", ".join(changed_models))

    metrics = (
        "overall_score",
        "quality_score",
        "completion_rate",
        "speed_score",
        "token_efficiency_score",
        "median_duration_seconds",
        "median_output_tokens",
        "median_cpu_seconds",
        "median_energy_joules",
    )
    bounded_percentages = {
        "overall_score",
        "quality_score",
        "completion_rate",
        "speed_score",
        "token_efficiency_score",
    }
    models: list[dict[str, Any]] = []
    for model, rows in samples.items():
        distributions: dict[str, Any] = {}
        for metric in metrics:
            values = [float(row[metric]) for row in rows if isinstance(row.get(metric), (int, float))]
            if metric in bounded_percentages:
                distributions[metric] = _distribution(values, lower_bound=0, upper_bound=100) if values else None
            else:
                distributions[metric] = _distribution(values, lower_bound=0) if values else None
        models.append(
            {
                "model": model,
                "run_count": len(rows),
                "present_in_all_runs": len(rows) == len(loaded),
                "model_digest": next(iter(digests.get(model, ())), None),
                "metrics": distributions,
            }
        )
    models.sort(
        key=lambda item: (
            -float((item["metrics"].get("overall_score") or {}).get("mean", 0)),
            str(item["model"]),
        )
    )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_runs": [run_dir.name for run_dir, _manifest, _report in loaded],
        "compatibility": reference,
        "disqualified_models_by_run": disqualified_by_run,
        "models": models,
        "notes": {
            "ci95": "Intervallo normale approssimato, limitato al dominio naturale della metrica; con pochi run descrive l'incertezza ma non sostituisce più ripetizioni.",
            "missing_models": "Un modello assente o escluso in un run non riceve un campione per quel run.",
        },
    }


def render_comparison_markdown(comparison: dict[str, Any]) -> str:
    lines = [
        "# LocalAgent Benchmark – confronto multi-run",
        "",
        "Run: " + ", ".join(f"`{name}`" for name in comparison.get("source_runs", [])),
        "",
        "| # | Modello | Run validi | Totale medio ± σ | Qualità media | Completamento | Tempo mediano medio | Energia media |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for index, item in enumerate(comparison.get("models", []), 1):
        metrics = item.get("metrics", {})
        overall = metrics.get("overall_score") or {}
        quality = metrics.get("quality_score") or {}
        completion = metrics.get("completion_rate") or {}
        duration = metrics.get("median_duration_seconds") or {}
        energy = metrics.get("median_energy_joules") or {}
        energy_text = f"{energy['mean']:.2f} J" if "mean" in energy else "n/d"
        lines.append(
            f"| {index} | `{item['model']}` | {item['run_count']} | "
            f"{overall.get('mean', 0):.2f} ± {overall.get('stddev', 0):.2f} | "
            f"{quality.get('mean', 0):.2f} | {completion.get('mean', 0):.1f}% | "
            f"{duration.get('mean', 0):.2f}s | {energy_text} |"
        )
    if not comparison.get("models"):
        lines.append("| – | Nessun modello classificabile | – | – | – | – | – | – |")
    lines.extend(
        [
            "",
            "I run vengono confrontati solo se versione, parametri, profilo, casi, fingerprint degli input, digest modello, audit, backend sandbox e hardware registrato coincidono. "
            "Gli intervalli al 95% sono approssimazioni normali e vanno interpretati con cautela quando i campioni sono pochi.",
            "",
        ]
    )
    return "\n".join(lines)


def write_comparison(run_dirs: list[Path], output_dir: Path) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ComparisonError(f"Directory output non vuota: {output_dir}")
    comparison = build_comparison(run_dirs)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "comparison.json").write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "COMPARISON.md").write_text(render_comparison_markdown(comparison), encoding="utf-8")
    return comparison
