"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .case_sdk import (
    CaseValidationError,
    create_case_template,
    validate_case_selection,
)
from .config import ConfigError, load_config
from .comparison import ComparisonError, write_comparison
from .dashboard_data import DashboardDataError, write_dashboard_data
from .ollama import OllamaError
from .report import write_report
from .runner import BenchmarkError, doctor, run_benchmark
from .sandbox import SANDBOX_MODES
from .thinking import THINKING_LEVELS


ROOT = Path(__file__).resolve().parents[2]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="benchmark.py",
        description="Benchmark personale offline per Pi e provider locali",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "benchmark.json",
        help="Percorso della configurazione (default: benchmark.json)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="Verifica Pi, Git, provider, modelli e casi")
    subparsers.add_parser("list", help="Elenca profili, casi e modelli rilevati")

    run = subparsers.add_parser("run", help="Esegue il benchmark")
    run.add_argument("--profile", default="standard", help="Profilo da eseguire")
    run.add_argument("--models", nargs="+", help="Modelli locali (default dalla configurazione)")
    run.add_argument("--cases", nargs="+", help="Casi specifici, ignorando il profilo")
    run.add_argument("--repetitions", type=int, help="Ripetizioni per modello/caso")
    run.add_argument("--timeout", type=int, help="Timeout di ogni task in secondi")
    run.add_argument(
        "--thinking",
        choices=THINKING_LEVELS,
        help="Modalità thinking effettiva (default da benchmark.json)",
    )
    run.add_argument("--seed", type=int, help="Seed intero per riprodurre l'ordine randomizzato delle task")
    run.add_argument(
        "--sandbox",
        choices=SANDBOX_MODES,
        help="Isolamento: audit, auto con fallback esplicito, oppure required senza fallback",
    )
    warmup = run.add_mutually_exclusive_group()
    warmup.add_argument("--warmup", dest="warmup", action="store_true", help="Forza warmup")
    warmup.add_argument("--no-warmup", dest="warmup", action="store_false", help="Disabilita warmup")
    run.set_defaults(warmup=None)
    run.add_argument("--output", type=Path, help="Directory output esplicita")

    report = subparsers.add_parser("report", help="Rigenera il report di un run")
    report.add_argument("run_dir", type=Path)
    compare = subparsers.add_parser("compare", help="Confronta statisticamente più run compatibili")
    compare.add_argument("run_dirs", type=Path, nargs="+")
    compare.add_argument("--output", type=Path, help="Directory del confronto")

    dashboard = subparsers.add_parser(
        "dashboard-data",
        help="Esporta run in un dataset JSON ridotto per la dashboard offline",
    )
    dashboard.add_argument("run_dirs", type=Path, nargs="+")
    dashboard.add_argument("--output", type=Path, help="File JSON di output")
    dashboard.add_argument(
        "--force",
        action="store_true",
        help="Sostituisce atomicamente un file di output esistente",
    )

    case = subparsers.add_parser("case", help="Crea e valida casi estensibili")
    case_commands = case.add_subparsers(dest="case_command", required=True)
    validate = case_commands.add_parser("validate", help="Valida manifesti, grader e calibrazione baseline")
    validate.add_argument("case_ids", nargs="*", help="ID da validare (default: tutti)")
    create = case_commands.add_parser("create", help="Crea un nuovo caso dal template")
    create.add_argument("case_id", help="ID portabile del caso")
    create.add_argument("--title-it", required=True, help="Titolo italiano")
    create.add_argument("--title-en", required=True, help="Titolo inglese")
    create.add_argument("--category", default="custom", help="Categoria (default: custom)")
    create.add_argument("--weight", type=float, default=1.0, help="Peso positivo (default: 1.0)")
    create.add_argument(
        "--manual-rubric",
        action="store_true",
        help="Aggiunge una rubrica umana opzionale, separata dal punteggio automatico",
    )
    return parser


def _print_doctor(payload: dict) -> None:
    for check in payload["checks"]:
        mark = "OK" if check["ok"] else "ERRORE"
        print(f"[{mark:6}] {check['name']}: {check['detail']}")
    if payload["models"]:
        print("\nModelli locali:")
        for model in payload["models"]:
            size = model.get("size")
            size_text = f"{size / (1024 ** 3):.1f} GiB" if size else "dimensione sconosciuta"
            thinking = model.get("thinking_capable")
            thinking_text = "sì" if thinking is True else "no" if thinking is False else "sconosciuto"
            print(
                f"  - {model['name']} ({size_text}; thinking: {thinking_text}; "
                f"richiesto: {model.get('thinking_requested', 'n/d')}; "
                f"compatibilità: {model.get('thinking_compatibility', 'n/d')})"
            )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = load_config(args.config)
        if args.command == "doctor":
            payload = doctor(config)
            _print_doctor(payload)
            return 0 if payload["ok"] else 1
        if args.command == "list":
            payload = doctor(config)
            print("Profili:")
            for name, ids in config.profiles.items():
                print(f"  - {name}: {', '.join(ids)}")
            print("\nCasi:")
            for case in config.cases.values():
                print(f"  - {case.id}: {case.title} [{case.category}, peso {case.weight:g}]")
            print("\nModelli locali:")
            for model in payload["models"]:
                print(f"  - {model['name']}")
            return 0 if payload["ok"] else 1
        if args.command == "run":
            run_dir = run_benchmark(
                config,
                profile=args.profile,
                requested_models=args.models,
                requested_cases=args.cases,
                repetitions=args.repetitions,
                timeout_seconds=args.timeout,
                thinking_level=args.thinking,
                use_warmup=args.warmup,
                output_dir=args.output,
                order_seed=args.seed,
                sandbox_mode=args.sandbox,
            )
            print(f"\nBenchmark completato: {run_dir}")
            print(f"Report: {run_dir / 'REPORT.md'}")
            report_payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
            failed = [item for item in report_payload.get("results", []) if item.get("status") != "ok"]
            integrity = report_payload.get("integrity", {})
            integrity_failed = integrity.get("status") not in {None, "passed", "not_recorded"}
            if failed or integrity_failed:
                if failed:
                    print(f"Attenzione: {len(failed)} task terminate con errore o timeout.", file=sys.stderr)
                if integrity_failed:
                    print("Attenzione: il run contiene violazioni d'integrità; consulta il report.", file=sys.stderr)
                return 1
            return 0
        if args.command == "report":
            report = write_report(args.run_dir.resolve())
            print(json.dumps(report["leaderboard"], indent=2, ensure_ascii=False))
            return 0
        if args.command == "compare":
            output = args.output or config.root / "results" / f"comparison-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            comparison = write_comparison(args.run_dirs, output)
            print(f"Confronto completato: {output.resolve()}")
            print(f"Modelli aggregati: {len(comparison['models'])}")
            return 0
        if args.command == "dashboard-data":
            output = args.output or config.root / "results" / f"dashboard-data-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
            dataset = write_dashboard_data(
                args.run_dirs,
                output,
                workspace_root=config.root,
                overwrite=args.force,
            )
            print(f"Dataset dashboard creato: {output.resolve()}")
            print(f"Run esportati: {len(dataset['runs'])}; profili: {', '.join(dataset['profile_order'])}")
            return 0
        if args.command == "case":
            if args.case_command == "create":
                created = create_case_template(
                    config.cases_directory,
                    args.case_id,
                    title_it=args.title_it,
                    title_en=args.title_en,
                    category=args.category,
                    weight=args.weight,
                    include_manual_rubric=args.manual_rubric,
                )
                print(f"Caso creato e validato: {created.directory}")
                print(f"Esecuzione diretta: python3 benchmark.py run --cases {created.id}")
                print("Prima di un run, personalizza prompt, fixture e grader, poi committa gli input.")
                return 0
            selected_ids = args.case_ids or list(config.cases)
            unknown = sorted(set(selected_ids) - set(config.cases))
            if unknown:
                raise CaseValidationError(f"Casi sconosciuti: {', '.join(unknown)}")
            reports = validate_case_selection(config.cases[case_id] for case_id in dict.fromkeys(selected_ids))
            for report in reports:
                rubric = "sì" if report["manual_rubric"] else "no"
                print(
                    f"[OK] {report['id']}: baseline {report['baseline_score']:g}/100, "
                    f"peso {report['weight']:g}, rubrica manuale {rubric}"
                )
            print(f"Validazione completata: {len(reports)} casi validi")
            return 0
    except (
        CaseValidationError,
        ConfigError,
        BenchmarkError,
        ComparisonError,
        DashboardDataError,
        OllamaError,
        OSError,
    ) as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 2
    return 2
