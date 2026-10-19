"""Aggregate benchmark results into machine- and human-readable reports."""

from __future__ import annotations

import json
import statistics
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .pi_adapter import AUDIT_VERSION, audit_workspace_accesses


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def _fmt_seconds(value: float) -> str:
    minutes, seconds = divmod(int(round(value)), 60)
    return f"{minutes}m {seconds:02d}s" if minutes else f"{seconds}s"


def _load_results(run_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    possible_root = run_dir.parent.parent
    protected_paths = (possible_root,) if (possible_root / "benchmark.json").is_file() else ()
    for path in sorted(run_dir.glob("models/*/cases/*/result.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            payload["_path"] = str(path.relative_to(run_dir))
            if not payload.get("baseline_tree") and isinstance(payload.get("baseline_commit"), str):
                workspace = path.parent / "workspace"
                try:
                    tree = subprocess.run(
                        ["git", "rev-parse", f"{payload['baseline_commit']}^{{tree}}"],
                        cwd=workspace,
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=30,
                    ).stdout.strip()
                except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
                    tree = ""
                if tree:
                    payload["baseline_tree"] = tree
            integrity = payload.get("integrity")
            if not isinstance(integrity, dict):
                integrity = {}
            events_path = path.parent / "pi-events.jsonl"
            if integrity.get("audit_version") != AUDIT_VERSION and events_path.is_file():
                events = events_path.read_text(encoding="utf-8", errors="replace")
                findings = audit_workspace_accesses(events, path.parent / "workspace", protected_paths)
                source_mutations = integrity.get("source_mutations", [])
                snapshot_mutations = integrity.get("snapshot_mutations", [])
                thinking_violations = integrity.get("thinking_control_violations", [])
                integrity.update(
                    {
                        "audit_version": AUDIT_VERSION,
                        "valid_for_ranking": not (
                            source_mutations
                            or snapshot_mutations
                            or findings
                            or thinking_violations
                        ),
                        "source_mutations": source_mutations,
                        "snapshot_mutations": snapshot_mutations,
                        "external_accesses": findings,
                        "reaudited_from_events": True,
                    }
                )
                payload["integrity"] = integrity
            results.append(payload)
    return results


def _load_manifest(run_dir: Path) -> dict[str, Any]:
    try:
        payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _mismatched_models(
    results: list[dict[str, Any]],
    field: str,
) -> tuple[list[str], set[str]]:
    values_by_case: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for item in results:
        value = item.get(field)
        if isinstance(value, str) and value:
            values_by_case[str(item.get("case_id", "unknown"))].append(
                (str(item.get("model", "unknown")), value)
            )
    mismatched_cases: list[str] = []
    disqualified: set[str] = set()
    for case_id, entries in values_by_case.items():
        counts = Counter(value for _, value in entries)
        if len(counts) <= 1:
            continue
        mismatched_cases.append(case_id)
        highest = max(counts.values())
        majority = [value for value, count in counts.items() if count == highest]
        if len(majority) == 1:
            disqualified.update(model for model, value in entries if value != majority[0])
        else:
            disqualified.update(model for model, _ in entries)
    return sorted(mismatched_cases), disqualified


def _integrity_summary(
    manifest: dict[str, Any],
    results: list[dict[str, Any]],
) -> tuple[dict[str, Any], set[str]]:
    explicit_invalid = [
        item for item in results if item.get("integrity", {}).get("valid_for_ranking") is False
    ]
    disqualified = {str(item.get("model", "unknown")) for item in explicit_invalid}
    thinking_control = manifest.get("thinking_control", {})
    if isinstance(thinking_control, dict):
        recorded = thinking_control.get("disqualified_models", [])
        if isinstance(recorded, list):
            disqualified.update(str(model) for model in recorded if isinstance(model, str))
    input_mismatches, input_disqualified = _mismatched_models(results, "input_fingerprint")
    baseline_mismatches, baseline_disqualified = _mismatched_models(results, "baseline_tree")
    mismatched_cases = set(input_mismatches) | set(baseline_mismatches)
    disqualified.update(input_disqualified)
    disqualified.update(baseline_disqualified)

    incomplete_models: list[str] = []
    task_order = manifest.get("task_order")
    if isinstance(task_order, list):
        expected: dict[str, int] = defaultdict(int)
        actual: dict[str, int] = defaultdict(int)
        for task in task_order:
            if isinstance(task, dict):
                expected[str(task.get("model", "unknown"))] += 1
        for item in results:
            actual[str(item.get("model", "unknown"))] += 1
        incomplete_models = sorted(model for model, count in expected.items() if actual.get(model, 0) != count)
        disqualified.update(incomplete_models)

    manifest_integrity = manifest.get("integrity", {})
    derived_violations: dict[tuple[str, str, int, str], dict[str, Any]] = {}
    superseded_manifest_keys: set[tuple[str, str, int, str]] = set()
    violation_fields = (
        ("source_mutations", "repository_mutation"),
        ("snapshot_mutations", "snapshot_mutation"),
        ("external_accesses", "external_workspace_access"),
        ("thinking_control_violations", "thinking_control_violation"),
    )
    for item in results:
        item_integrity = item.get("integrity", {})
        if not isinstance(item_integrity, dict):
            continue
        for field, kind in violation_fields:
            key = (
                str(item.get("model", "unknown")),
                str(item.get("case_id", "unknown")),
                int(item.get("repetition", 1)),
                kind,
            )
            if item_integrity.get("audit_version") == AUDIT_VERSION:
                superseded_manifest_keys.add(key)
            details = item_integrity.get(field, [])
            if not details:
                continue
            derived_violations[key] = {
                "model": key[0],
                "case_id": key[1],
                "repetition": key[2],
                "kind": kind,
                "details": details,
            }
    manifest_violations = manifest_integrity.get("violations", []) if isinstance(manifest_integrity, dict) else []
    if isinstance(manifest_violations, list):
        for violation in manifest_violations:
            if not isinstance(violation, dict):
                continue
            key = (
                str(violation.get("model", "unknown")),
                str(violation.get("case_id", "unknown")),
                int(violation.get("repetition", 1)),
                str(violation.get("kind", "unknown")),
            )
            if key not in superseded_manifest_keys:
                derived_violations.setdefault(key, violation)
    current_violations = list(derived_violations.values())
    manifest_status = manifest_integrity.get("status") if isinstance(manifest_integrity, dict) else None
    if manifest_status == "snapshot_compromised":
        status = manifest_status
    elif disqualified or mismatched_cases or current_violations:
        status = "violations_detected"
    elif manifest:
        status = "passed"
    else:
        status = "not_recorded"
    summary = {
        "audit_version": AUDIT_VERSION,
        "status": status,
        "disqualified_models": sorted(disqualified),
        "invalid_results": [
            {
                "model": item.get("model"),
                "case_id": item.get("case_id"),
                "repetition": item.get("repetition", 1),
            }
            for item in explicit_invalid
        ],
        "input_mismatches": input_mismatches,
        "baseline_mismatches": baseline_mismatches,
        "incomplete_models": incomplete_models,
        "violations": current_violations,
    }
    return summary, disqualified


def build_report(run_dir: Path) -> dict[str, Any]:
    results = _load_results(run_dir)
    manifest = _load_manifest(run_dir)
    integrity, disqualified_models = _integrity_summary(manifest, results)
    rankable_results = [
        item for item in results if str(item.get("model", "unknown")) not in disqualified_models
    ]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in rankable_results:
        grouped[str(result.get("model", "unknown"))].append(result)

    eligible = [
        item
        for item in rankable_results
        if item.get("status") == "ok" and float(item.get("grade", {}).get("score", 0)) >= 60
    ]
    fastest_by_case: dict[tuple[str, int], float] = {}
    fewest_tokens_by_case: dict[tuple[str, int], int] = {}
    for item in eligible:
        key = (str(item.get("case_id")), int(item.get("repetition", 1)))
        duration = float(item.get("duration_seconds", 0))
        tokens = int(item.get("metrics", {}).get("usage", {}).get("output", 0))
        if duration > 0:
            fastest_by_case[key] = min(fastest_by_case.get(key, duration), duration)
        if tokens > 0:
            fewest_tokens_by_case[key] = min(fewest_tokens_by_case.get(key, tokens), tokens)

    leaderboard: list[dict[str, Any]] = []
    for model, items in grouped.items():
        weighted_scores: list[tuple[float, float]] = []
        durations: list[float] = []
        output_tokens: list[float] = []
        cpu_seconds: list[float] = []
        energy_joules: list[float] = []
        speed_ratios: list[float] = []
        token_ratios: list[float] = []
        completed = 0
        for item in items:
            score = float(item.get("grade", {}).get("score", 0))
            weight = float(item.get("case_weight", 1))
            weighted_scores.append((score, weight))
            duration = float(item.get("duration_seconds", 0))
            durations.append(duration)
            tokens = int(item.get("metrics", {}).get("usage", {}).get("output", 0))
            if tokens:
                output_tokens.append(float(tokens))
            recorded_system_metrics = item.get("system_metrics")
            if not isinstance(recorded_system_metrics, dict):
                recorded_system_metrics = {}
            process_metrics = recorded_system_metrics.get("process", {})
            if isinstance(process_metrics, dict) and process_metrics.get("available"):
                cpu_seconds.append(
                    float(process_metrics.get("user_seconds", 0))
                    + float(process_metrics.get("system_seconds", 0))
                )
            energy_metrics = recorded_system_metrics.get("energy", {})
            if isinstance(energy_metrics, dict) and energy_metrics.get("available"):
                energy_value = energy_metrics.get("energy_joules")
                if isinstance(energy_value, (int, float)):
                    energy_joules.append(float(energy_value))
            if item.get("status") == "ok" and score >= 60:
                completed += 1
                key = (str(item.get("case_id")), int(item.get("repetition", 1)))
                fastest = fastest_by_case.get(key)
                fewest = fewest_tokens_by_case.get(key)
                if fastest and duration:
                    speed_ratios.append(min(1.0, fastest / duration) * 100)
                if fewest and tokens:
                    token_ratios.append(min(1.0, fewest / tokens) * 100)
        denominator = sum(weight for _, weight in weighted_scores)
        quality = sum(score * weight for score, weight in weighted_scores) / denominator if denominator else 0
        completion = completed / len(items) * 100 if items else 0
        speed = _mean(speed_ratios)
        token_efficiency = _mean(token_ratios)
        overall = 0.80 * quality + 0.10 * completion + 0.05 * speed + 0.05 * token_efficiency
        scores = [score for score, _ in weighted_scores]
        case_scores: dict[str, list[float]] = defaultdict(list)
        for item in items:
            case_scores[str(item.get("case_id", "unknown"))].append(float(item.get("grade", {}).get("score", 0)))
        leaderboard.append(
            {
                "model": model,
                "overall_score": round(overall, 2),
                "quality_score": round(quality, 2),
                "completion_rate": round(completion, 2),
                "speed_score": round(speed, 2),
                "token_efficiency_score": round(token_efficiency, 2),
                "median_duration_seconds": round(_median(durations), 3),
                "median_output_tokens": round(_median(output_tokens), 1),
                "median_cpu_seconds": round(_median(cpu_seconds), 3) if cpu_seconds else None,
                "median_energy_joules": round(_median(energy_joules), 6) if energy_joules else None,
                "score_stddev": round(statistics.pstdev(scores), 2) if len(scores) > 1 else 0.0,
                "successful_tasks": completed,
                "total_tasks": len(items),
                "case_scores": {case_id: round(_mean(values), 2) for case_id, values in sorted(case_scores.items())},
            }
        )
    leaderboard.sort(key=lambda row: (-row["overall_score"], -row["quality_score"], row["median_duration_seconds"]))

    recorded_thinking = manifest.get("thinking_control")
    if not isinstance(recorded_thinking, dict):
        configuration = manifest.get("configuration", {})
        if not isinstance(configuration, dict):
            configuration = {}
        recorded_thinking = {
            "version": 0,
            "status": "unverified",
            "requested": configuration.get("thinking", manifest.get("thinking")),
            "reasoning_effort": None,
            "source": "legacy_unverified",
            "disqualified_models": [],
        }
    return {
        "schema_version": 4,
        "formula": {
            "overall": "0.80*quality + 0.10*completion + 0.05*speed + 0.05*token_efficiency",
            "completion_threshold": 60,
            "notes": "Speed and token efficiency are relative to the fastest/leanest successful rankable run for each case and repetition. Models with integrity violations are disqualified.",
        },
        "integrity": integrity,
        "run": {
            "profile": manifest.get("profile"),
            "sandbox": manifest.get("sandbox", {"backend": "audit-only", "enforced": False}),
            "environment": manifest.get("environment", {}),
            "thinking_control": recorded_thinking,
        },
        "leaderboard": leaderboard,
        "results": results,
    }


def render_markdown(report: dict[str, Any], run_dir: Path) -> str:
    leaderboard = report.get("leaderboard", [])
    integrity = report.get("integrity", {})
    run_metadata = report.get("run", {})
    sandbox = run_metadata.get("sandbox", {}) if isinstance(run_metadata, dict) else {}
    environment = run_metadata.get("environment", {}) if isinstance(run_metadata, dict) else {}
    hardware = environment.get("hardware", {}) if isinstance(environment, dict) else {}
    thinking_control = run_metadata.get("thinking_control", {}) if isinstance(run_metadata, dict) else {}
    if not isinstance(sandbox, dict):
        sandbox = {}
    if not isinstance(hardware, dict):
        hardware = {}
    if not isinstance(thinking_control, dict):
        thinking_control = {}
    backend = sandbox.get("backend", "audit-only")
    enforced = bool(sandbox.get("enforced", False))
    capabilities = ", ".join(
        name
        for name, key in (
            ("filesystem", "filesystem_isolation"),
            ("processi", "process_isolation"),
            ("rete", "network_isolation"),
        )
        if sandbox.get(key)
    ) or "nessuna capacità OS"
    memory = hardware.get("memory_total_bytes")
    memory_text = f"{float(memory) / (1024 ** 3):.1f} GiB" if isinstance(memory, (int, float)) else "n/d"
    lines = [
        "# LocalAgent Benchmark Report",
        "",
        f"Run: `{run_dir.name}`",
        "",
        "## Ambiente e isolamento",
        "",
        f"Sandbox: **{backend}** ({'enforced' if enforced else 'audit-only'}); capacità applicate: {capabilities}.",
        f"Provider: `{environment.get('provider_kind') or 'ollama'}`; runtime: `{environment.get('provider_version') or 'non verificato'}` ({'dichiarato in configurazione' if environment.get('provider_kind') not in (None, 'ollama') else 'API'}).",
        f"Hardware: `{hardware.get('machine') or 'n/d'}`, CPU logiche: {hardware.get('logical_cpu_count') or 'n/d'}, memoria: {memory_text}.",
        "",
        "## Controllo thinking",
        "",
        (
            f"Stato: **{thinking_control.get('status', 'unverified')}**; "
            f"richiesto: `{thinking_control.get('requested') or 'n/d'}`; "
            f"inviato al provider: `{thinking_control.get('reasoning_effort') or 'non verificato'}`; "
            f"versione controllo: {thinking_control.get('version', 0)}."
        ),
        "",
        "## Integrità del run",
        "",
    ]
    if sandbox.get("deprecated_backend"):
        thinking_heading = lines.index("## Controllo thinking")
        lines[thinking_heading:thinking_heading] = [
            "Nota: il backend macOS usa `sandbox-exec`, interfaccia deprecata da Apple; disponibilità e probe sono registrati a ogni run.",
            "",
        ]
    integrity_status = integrity.get("status", "not_recorded")
    if integrity_status == "passed":
        lines.append("**Stato: valida.** Snapshot, baseline e confini registrati non mostrano violazioni.")
    elif integrity_status == "not_recorded":
        lines.append("**Stato: non registrata.** Il run usa uno schema precedente ai controlli d'integrità.")
    else:
        lines.append(f"**Stato: {integrity_status}.** Il run richiede revisione prima di usare la classifica.")
    disqualified = integrity.get("disqualified_models", [])
    if disqualified:
        lines.append("Modelli esclusi dalla classifica: " + ", ".join(f"`{model}`" for model in disqualified) + ".")
    mismatch_cases = sorted(
        set(integrity.get("input_mismatches", [])) | set(integrity.get("baseline_mismatches", []))
    )
    if mismatch_cases:
        lines.append("Casi con baseline non uniforme: " + ", ".join(f"`{case}`" for case in mismatch_cases) + ".")
    violations = integrity.get("violations", [])
    if violations:
        lines.extend(
            [
                "",
                "### Violazioni rilevate",
                "",
                "| Modello | Caso | Rip. | Tipo | Motivo | Target | Accesso | Evidenza | Chiamata |",
                "|---|---|---:|---|---|---|---|---|---|",
            ]
        )
        for violation in violations:
            details = violation.get("details", []) if isinstance(violation, dict) else []
            if not isinstance(details, list):
                details = [details]
            if not details:
                details = [{}]
            for detail in details:
                if isinstance(detail, dict):
                    reason = detail.get("reason", violation.get("kind", "unknown"))
                    target = detail.get("target", "")
                    access = detail.get("access", "")
                    evidence = detail.get("evidence", "")
                    call_id = detail.get("tool_call_id", "")
                else:
                    reason = violation.get("kind", "unknown")
                    target = detail
                    access = ""
                    evidence = ""
                    call_id = ""
                cells = [
                    violation.get("model", "unknown"),
                    violation.get("case_id", "unknown"),
                    violation.get("repetition", 1),
                    violation.get("kind", "unknown"),
                    reason,
                    target,
                    access,
                    evidence,
                    call_id,
                ]
                rendered = [str(cell).replace("|", "\\|").replace("\n", " ") for cell in cells]
                lines.append("| " + " | ".join(rendered) + " |")
    lines.extend(
        [
            "",
            "## Classifica",
            "",
            "| # | Modello | Totale | Qualità | Completamento | Velocità | Token eff. | Tempo mediano | Token output | σ score |",
            "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for index, row in enumerate(leaderboard, 1):
        lines.append(
            "| {rank} | `{model}` | {overall:.1f} | {quality:.1f} | {completion:.0f}% | {speed:.1f} | "
            "{tokens_eff:.1f} | {duration} | {tokens:.0f} | {stddev:.1f} |".format(
                rank=index,
                model=row["model"],
                overall=row["overall_score"],
                quality=row["quality_score"],
                completion=row["completion_rate"],
                speed=row["speed_score"],
                tokens_eff=row["token_efficiency_score"],
                duration=_fmt_seconds(row["median_duration_seconds"]),
                tokens=row["median_output_tokens"],
                stddev=row["score_stddev"],
            )
        )
    if not leaderboard:
        lines.append("| – | Nessun risultato valido | – | – | – | – | – | – | – | – |")

    case_ids = sorted({str(item.get("case_id")) for item in report.get("results", [])})
    if case_ids:
        lines.extend(
            [
                "",
                "## Qualità per caso",
                "",
                "| Modello | " + " | ".join(f"`{case_id}`" for case_id in case_ids) + " |",
                "|---|" + "---:|" * len(case_ids),
            ]
        )
        for row in leaderboard:
            cells = [f"{row.get('case_scores', {}).get(case_id, 0):.1f}" for case_id in case_ids]
            lines.append(f"| `{row['model']}` | " + " | ".join(cells) + " |")

    lines.extend(
        [
            "",
            "Il punteggio totale pesa qualità 80%, completamento 10%, velocità relativa 5% ed efficienza token relativa 5%. "
            "Una task è completata quando `pi` termina correttamente e il grader assegna almeno 60/100.",
            "",
            "## Dettaglio per task",
            "",
            "| Modello | Caso | Rip. | Stato | Integrità | Punti | Tempo | CPU | Energia | Tool/errori | Output token |",
            "|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for result in sorted(report.get("results", []), key=lambda item: (str(item.get("model")), str(item.get("case_id")), int(item.get("repetition", 1)))):
        metrics = result.get("metrics", {})
        model = str(result.get("model", "?"))
        recorded_integrity = result.get("integrity", {})
        if recorded_integrity.get("valid_for_ranking") is False:
            integrity_cell = "violata"
        elif model in set(disqualified):
            integrity_cell = "escluso"
        elif "valid_for_ranking" in recorded_integrity:
            integrity_cell = "ok"
        else:
            integrity_cell = "n/d"
        system_metrics = result.get("system_metrics")
        if not isinstance(system_metrics, dict):
            system_metrics = {}
        process_metrics = system_metrics.get("process", {})
        energy_metrics = system_metrics.get("energy", {})
        if isinstance(process_metrics, dict) and process_metrics.get("available"):
            cpu = float(process_metrics.get("user_seconds", 0)) + float(process_metrics.get("system_seconds", 0))
            cpu_cell = f"{cpu:.2f}s"
        else:
            cpu_cell = "n/d"
        if isinstance(energy_metrics, dict) and energy_metrics.get("available"):
            energy_cell = f"{float(energy_metrics.get('energy_joules', 0)):.2f}J"
        else:
            energy_cell = "n/d"
        lines.append(
            "| `{model}` | `{case}` | {repetition} | {status} | {integrity} | {score:.1f} | {duration} | {cpu} | {energy} | {tools}/{errors} | {tokens} |".format(
                model=model,
                case=result.get("case_id", "?"),
                repetition=result.get("repetition", 1),
                status=result.get("status", "?"),
                integrity=integrity_cell,
                score=float(result.get("grade", {}).get("score", 0)),
                duration=_fmt_seconds(float(result.get("duration_seconds", 0))),
                cpu=cpu_cell,
                energy=energy_cell,
                tools=metrics.get("tool_calls", 0),
                errors=metrics.get("tool_errors", 0),
                tokens=metrics.get("usage", {}).get("output", 0),
            )
        )

    rubric_results = [
        result
        for result in report.get("results", [])
        if isinstance(result.get("manual_rubric"), dict)
        and result["manual_rubric"].get("path") == "manual-rubric.md"
    ]
    if rubric_results:
        lines.extend(
            [
                "",
                "## Rubriche manuali",
                "",
                "Le rubriche seguenti sono facoltative e non modificano score automatico o classifica:",
                "",
            ]
        )
        for result in rubric_results:
            rubric = result["manual_rubric"]
            result_path = Path(str(result.get("_path", "")))
            rubric_path = result_path.parent / str(rubric["path"])
            max_score = rubric.get("max_score")
            max_score_text = (
                f"{float(max_score):g}"
                if isinstance(max_score, (int, float)) and not isinstance(max_score, bool)
                else "n/d"
            )
            lines.append(
                f"- `{result.get('model', '?')}` · `{result.get('case_id', '?')}` · "
                f"rip. {result.get('repetition', 1)}: "
                f"[{rubric_path.name}]({rubric_path.as_posix()}) "
                f"(massimo manuale {max_score_text})."
            )

    lines.extend(["", "## Lettura dei risultati", ""])
    if leaderboard:
        best = leaderboard[0]
        if not any(row["successful_tasks"] for row in leaderboard):
            lines.append(
                "Nessun modello ha completato una task sopra soglia senza errori o timeout. "
                "I punteggi parziali restano utili per diagnosticare il lavoro prodotto, ma questo run non identifica un vincitore operativo."
            )
        else:
            lines.append(
                f"Il miglior punteggio composito di questo run è **{best['model']}** ({best['overall_score']:.1f}/100). "
                "Controlla comunque i punteggi dei singoli casi e le patch: il modello migliore in assoluto può non essere quello più adatto alle task che svolgi più spesso."
            )
        if disqualified:
            lines.append(
                "I modelli con violazioni d'integrità sono esclusi dall'aggregazione anche quando i grader hanno prodotto un punteggio."
            )
    else:
        if report.get("results") and disqualified:
            lines.append(
                "Il run contiene risultati, ma nessun modello è classificabile a causa dei controlli d'integrità."
            )
        else:
            lines.append("Il run non contiene ancora risultati. Esegui il benchmark prima di interpretare il report.")
    lines.extend(
        [
            "",
            "I tempi includono ragionamento, chiamate agli strumenti e test: rappresentano la produttività end-to-end, non il throughput puro del provider. "
            "Confronta i tempi solo sullo stesso computer, con lo stesso profilo e senza altri carichi pesanti.",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(run_dir: Path) -> dict[str, Any]:
    report = build_report(run_dir)
    (run_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (run_dir / "REPORT.md").write_text(render_markdown(report, run_dir), encoding="utf-8")
    return report
