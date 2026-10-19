from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localagent_bench.config import load_config
from localagent_bench.guided import (
    GuidedCancelled,
    GuidedError,
    GuidedOrchestrator,
    evaluate_phase,
    find_latest_manifest,
    select_promoted,
    validate_model_name,
)
from localagent_bench.dashboard_data import DashboardDataError
from localagent_bench.guided_process import ManagedProcessRunner, ProcessResult
from localagent_bench.sandbox import SandboxError


def write_phase(
    root: Path,
    profile: str,
    models: list[str],
    ranked: list[str],
    *,
    disqualified: list[str] | None = None,
    incomplete: list[str] | None = None,
    failed: bool = False,
    failed_models: list[str] | None = None,
    finished: bool = True,
    thinking_status: str = "passed",
    thinking_disqualified: list[str] | None = None,
) -> Path:
    run = root / profile
    run.mkdir(parents=True)
    disqualified = disqualified or []
    incomplete = incomplete or []
    task_failures = set(failed_models or [])
    if failed and models:
        task_failures.add(models[0])
    results = []
    for model in models:
        if model in incomplete:
            continue
        results.append(
            {
                "model": model,
                "case_id": "case",
                "repetition": 1,
                "status": "error" if model in task_failures else "ok",
            }
        )
    manifest = {
        "profile": profile,
        "models": models,
        "finished_at": "2026-09-26T10:00:00+00:00" if finished else None,
        "task_order": [
            {"model": model, "case_id": "case", "repetition": 1} for model in models
        ],
        "integrity": {"status": "passed", "aborted": False},
        "thinking_control": {
            "status": thinking_status,
            "disqualified_models": thinking_disqualified or [],
        },
    }
    leaderboard = [
        {
            "model": model,
            "overall_score": 90 - index,
            "quality_score": 91 - index,
            "completion_rate": 100,
            "median_duration_seconds": 10 + index,
        }
        for index, model in enumerate(ranked)
    ]
    report = {
        "run": {"profile": profile, "thinking_control": {"status": thinking_status}},
        "integrity": {
            "status": "violations_detected" if disqualified else "passed",
            "disqualified_models": disqualified,
            "incomplete_models": incomplete,
        },
        "leaderboard": leaderboard,
        "results": results,
    }
    (run / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
    (run / "report.json").write_text(json.dumps(report), encoding="utf-8")
    return run


class FakeRunner:
    def __init__(
        self,
        rankings: dict[str, list[str]],
        *,
        cancel_profile: str | None = None,
        failures: dict[str, list[str]] | None = None,
    ) -> None:
        self.rankings = rankings
        self.cancel_profile = cancel_profile
        self.failures = failures or {}
        self.commands: list[list[str]] = []
        self.cancelled = False

    def run(self, args, *, cwd, cancel_event, on_line=None):
        command = list(args)
        self.commands.append(command)
        profile = command[command.index("--profile") + 1]
        output = Path(command[command.index("--output") + 1])
        model_start = command.index("--models") + 1
        model_end = command.index("--seed")
        models = command[model_start:model_end]
        if self.cancel_profile == profile:
            return ProcessResult(returncode=-15, cancelled=True, output_tail=())
        failed_models = self.failures.get(profile, [])
        write_phase(
            output.parent,
            profile,
            models,
            self.rankings[profile],
            failed_models=failed_models,
        )
        if on_line:
            on_line(f"[1/1] {models[0]} · case · ripetizione 1")
        return ProcessResult(
            returncode=1 if failed_models else 0,
            cancelled=False,
            output_tail=(),
        )

    def cancel(self):
        self.cancelled = True


class GuidedTests(unittest.TestCase):
    def test_selection_preserves_official_order_and_handles_short_or_empty_lists(self):
        rows = (
            {"model": "tie-second", "overall_score": 90},
            {"model": "tie-first", "overall_score": 90},
            {"model": "third", "overall_score": 80},
        )
        self.assertEqual(("tie-second", "tie-first"), select_promoted(rows, 2))
        self.assertEqual(("tie-second", "tie-first", "third"), select_promoted(rows, 4))
        self.assertEqual((), select_promoted((), 4))

    def test_phase_validation_records_integrity_and_thinking_exclusions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = write_phase(
                root,
                "smoke",
                ["ranked", "integrity", "thinking"],
                ["ranked"],
                disqualified=["integrity", "thinking"],
                incomplete=["thinking"],
                thinking_status="partial",
                thinking_disqualified=["thinking"],
            )
            outcome = evaluate_phase(
                run,
                root=root,
                expected_profile="smoke",
                expected_models=["ranked", "integrity", "thinking"],
                promotion_limit=4,
                process_returncode=1,
            )
            self.assertEqual(("ranked",), outcome.promoted)
            self.assertEqual(
                {"integrity": "integrity", "thinking": "thinking_control"},
                {item["model"]: item["reason"] for item in outcome.exclusions},
            )

    def test_phase_validation_rejects_partial_failed_and_unverified_runs(self):
        scenarios = (
            ({"finished": False}, "partial_run"),
            ({"thinking_status": "unverified"}, "thinking_unverified"),
            ({"incomplete": ["beta"], "disqualified": ["beta"]}, "partial_run"),
        )
        for index, (options, code) in enumerate(scenarios):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                run = write_phase(
                    root,
                    "smoke",
                    ["alpha", "beta"],
                    ["alpha"],
                    **options,
                )
                with self.assertRaises(GuidedError) as raised:
                    evaluate_phase(
                        run,
                        root=root,
                        expected_profile="smoke",
                        expected_models=["alpha", "beta"],
                        promotion_limit=4,
                        process_returncode=0,
                    )
                self.assertEqual(code, raised.exception.code)

    def test_failed_model_is_excluded_without_stopping_valid_promotions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = write_phase(
                root,
                "smoke",
                ["failed", "winner", "valid"],
                ["winner", "failed", "valid"],
                failed=True,
            )
            outcome = evaluate_phase(
                run,
                root=root,
                expected_profile="smoke",
                expected_models=["failed", "winner", "valid"],
                promotion_limit=4,
                process_returncode=1,
            )
            self.assertEqual(("winner", "valid"), outcome.promoted)
            self.assertEqual(
                [{"model": "failed", "reason": "task_failed"}],
                list(outcome.exclusions),
            )

    def test_hostile_model_names_are_rejected_before_argument_construction(self):
        for name in ("--output", "model name", "model;touch-owned", "../model", "bad\nname"):
            with self.subTest(name=name), self.assertRaises(GuidedError):
                validate_model_name(name)
        self.assertEqual("namespace/model:tag", validate_model_name("namespace/model:tag"))
        self.assertEqual("publisher/model@q4_k_m", validate_model_name("publisher/model@q4_k_m"))

    def test_discovery_distinguishes_ollama_pi_dirty_inputs_and_no_models(self):
        base = load_config(ROOT / "benchmark.json")
        failures = (
            ("ollama", "ollama_unavailable"),
            ("pi", "pi_unavailable"),
            ("inputs", "dirty_inputs"),
            ("sandbox", "sandbox_unavailable"),
        )
        for check, expected_code in failures:
            with self.subTest(check=check):
                payload = {
                    "ok": False,
                    "models": [{"name": "model:latest"}],
                    "checks": [{"name": check, "ok": False, "detail": f"{check} failed"}],
                }
                orchestrator = GuidedOrchestrator(
                    base,
                    ROOT / "benchmark.json",
                    doctor_function=lambda _config, value=payload: value,
                )
                with self.assertRaises(GuidedError) as raised:
                    orchestrator.discover()
                self.assertEqual(expected_code, raised.exception.code)

        no_models = GuidedOrchestrator(
            base,
            ROOT / "benchmark.json",
            doctor_function=lambda _config: {"ok": True, "models": [], "checks": []},
        )
        with self.assertRaises(GuidedError) as raised:
            no_models.discover()
        self.assertEqual("no_models", raised.exception.code)

    def test_guided_discovery_rejects_remote_ollama(self):
        base = load_config(ROOT / "benchmark.json")
        remote = replace(base, ollama_url="https://example.invalid")
        orchestrator = GuidedOrchestrator(remote, ROOT / "benchmark.json")
        with self.assertRaises(GuidedError) as raised:
            orchestrator.discover()
        self.assertEqual("remote_ollama", raised.exception.code)

    def test_output_and_phase_paths_must_be_new_and_confined(self):
        base = load_config(ROOT / "benchmark.json")
        orchestrator = GuidedOrchestrator(base, ROOT / "benchmark.json")
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            output = Path(directory) / "existing"
            output.mkdir()
            with self.assertRaises(GuidedError) as raised:
                orchestrator._benchmark_command("smoke", ["model:latest"], 1, output)
            self.assertEqual("output_exists", raised.exception.code)
        with tempfile.TemporaryDirectory() as root_dir, tempfile.TemporaryDirectory() as outside:
            outside_run = write_phase(Path(outside), "smoke", ["model"], ["model"])
            with self.assertRaises(GuidedError) as raised:
                evaluate_phase(
                    outside_run,
                    root=Path(root_dir),
                    expected_profile="smoke",
                    expected_models=["model"],
                    promotion_limit=4,
                    process_returncode=0,
                )
            self.assertEqual("unsafe_output", raised.exception.code)

    def test_integration_runs_exact_funnel_and_opens_dashboard_with_three_runs(self):
        base = load_config(ROOT / "benchmark.json")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(
                base,
                root=root,
                dashboard=replace(
                    base.dashboard,
                    results_directory=root / "results",
                    assets_directory=root / "dashboard",
                    snapshot_source=root / "snapshot.json",
                ),
                guided=replace(base.guided, preferences_file=root / ".local" / "prefs.json"),
            )
            models = [f"model-{index}" for index in range(1, 7)]
            rankings = {
                "smoke": ["model-3", "model-1", "model-5", "model-2", "model-4", "model-6"],
                "standard": ["model-5", "model-3", "model-1", "model-2"],
                "full": ["model-3", "model-5"],
            }
            runner = FakeRunner(rankings)
            dashboard_runs: list[Path] = []
            dashboard_commands: list[list[str]] = []

            def build_dashboard(runs):
                dashboard_runs.extend(runs)
                return {"runs": [1, 2, 3]}

            def start_dashboard(args, *, cwd):
                dashboard_commands.append(list(args))
                return object()

            orchestrator = GuidedOrchestrator(
                config,
                root / "benchmark.json",
                process_runner=runner,
                dashboard_builder=build_dashboard,
                dashboard_starter=start_dashboard,
            )
            discovery = {"ok": True, "models": [{"name": model} for model in models]}
            manifest_path = orchestrator.run(models, discovery, thinking="medium", sandbox="audit")
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(["smoke", "standard", "full"], [item["profile"] for item in payload["phases"]])
            self.assertEqual(rankings["smoke"][:4], payload["transitions"][0]["selected"])
            self.assertEqual(rankings["standard"][:2], payload["transitions"][1]["selected"])
            self.assertEqual(3, len({item["run_directory"] for item in payload["phases"]}))
            self.assertEqual(3, len(dashboard_runs))
            self.assertNotIn("showcase", json.dumps(payload))
            self.assertNotIn("results_dashboard", json.dumps(payload))
            self.assertEqual("completed", payload["status"])
            self.assertEqual("medium", payload["settings"]["thinking"])
            self.assertEqual("audit", payload["settings"]["sandbox"])
            self.assertEqual(1, len(dashboard_commands))
            for command in runner.commands:
                self.assertIsInstance(command, list)
                self.assertNotIn("shell=True", command)
                self.assertEqual("medium", command[command.index("--thinking") + 1])
                self.assertEqual("audit", command[command.index("--sandbox") + 1])

    def test_guided_rejects_invalid_modes_before_creating_session(self):
        config = load_config(ROOT / "benchmark.json")
        orchestrator = GuidedOrchestrator(config, ROOT / "benchmark.json")
        discovery = {"ok": True, "models": [{"name": "safe-model"}]}
        with self.assertRaises(GuidedError) as raised:
            orchestrator.run(["safe-model"], discovery, thinking="unknown", sandbox="audit")
        self.assertEqual("invalid_setting", raised.exception.code)
        with self.assertRaises(GuidedError) as raised:
            orchestrator.run(["safe-model"], discovery, thinking="off", sandbox="unsupported")
        self.assertEqual("invalid_setting", raised.exception.code)
        self.assertIsNone(orchestrator.manifest_path)

    def test_required_sandbox_failure_does_not_create_session(self):
        config = load_config(ROOT / "benchmark.json")
        orchestrator = GuidedOrchestrator(config, ROOT / "benchmark.json")
        discovery = {"ok": True, "models": [{"name": "safe-model"}]}
        with patch("localagent_bench.guided.select_sandbox", side_effect=SandboxError("backend unavailable")):
            with self.assertRaises(GuidedError) as raised:
                orchestrator.run(["safe-model"], discovery, thinking="medium", sandbox="required")
        self.assertEqual("sandbox_unavailable", raised.exception.code)
        self.assertIsNone(orchestrator.manifest_path)

    def test_integration_continues_after_per_model_task_failures(self):
        base = load_config(ROOT / "benchmark.json")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(
                base,
                root=root,
                dashboard=replace(
                    base.dashboard,
                    results_directory=root / "results",
                    assets_directory=root / "dashboard",
                    snapshot_source=root / "snapshot.json",
                ),
                guided=replace(base.guided, preferences_file=root / ".local" / "prefs.json"),
            )
            models = ["winner", "smoke-error", "standard-error", "valid"]
            runner = FakeRunner(
                {
                    "smoke": ["winner", "smoke-error", "standard-error", "valid"],
                    "standard": ["standard-error", "winner", "valid"],
                    "full": ["valid", "winner"],
                },
                failures={
                    "smoke": ["smoke-error"],
                    "standard": ["standard-error"],
                },
            )
            opened: list[list[Path]] = []
            orchestrator = GuidedOrchestrator(
                config,
                root / "benchmark.json",
                process_runner=runner,
                dashboard_builder=lambda runs: opened.append(runs) or {},
                dashboard_starter=lambda _args, *, cwd: object(),
            )

            manifest_path = orchestrator.run(
                models,
                {"ok": True, "models": [{"name": model} for model in models]},
            )
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))

            command_models = []
            for command in runner.commands:
                start = command.index("--models") + 1
                end = command.index("--seed")
                command_models.append(command[start:end])
            self.assertEqual(
                [
                    models,
                    ["winner", "standard-error", "valid"],
                    ["winner", "valid"],
                ],
                command_models,
            )
            self.assertEqual("completed", payload["status"])
            self.assertEqual(
                [{"model": "smoke-error", "reason": "task_failed"}],
                payload["phases"][0]["exclusions"],
            )
            self.assertEqual(
                [{"model": "standard-error", "reason": "task_failed"}],
                payload["phases"][1]["exclusions"],
            )
            self.assertEqual(1, len(opened))
            self.assertEqual(3, len(opened[0]))

    def test_cancellation_stops_before_promotion_and_preserves_manifest(self):
        base = load_config(ROOT / "benchmark.json")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(
                base,
                root=root,
                dashboard=replace(base.dashboard, results_directory=root / "results"),
                guided=replace(base.guided, preferences_file=root / ".local" / "prefs.json"),
            )
            runner = FakeRunner({"smoke": []}, cancel_profile="smoke")
            orchestrator = GuidedOrchestrator(
                config,
                root / "benchmark.json",
                process_runner=runner,
            )
            with self.assertRaises(GuidedCancelled):
                orchestrator.run(["model-1"], {"ok": True, "models": [{"name": "model-1"}]})
            self.assertIsNotNone(orchestrator.manifest_path)
            payload = json.loads(orchestrator.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual("cancelled", payload["status"])
            self.assertEqual([], payload["transitions"])

    def test_empty_leaderboard_stops_before_standard(self):
        base = load_config(ROOT / "benchmark.json")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(
                base,
                root=root,
                dashboard=replace(base.dashboard, results_directory=root / "results"),
                guided=replace(base.guided, preferences_file=root / ".local" / "prefs.json"),
            )
            runner = FakeRunner({"smoke": []})
            orchestrator = GuidedOrchestrator(
                config,
                root / "benchmark.json",
                process_runner=runner,
            )
            with self.assertRaises(GuidedError) as raised:
                orchestrator.run(["model-1"], {"ok": True, "models": [{"name": "model-1"}]})
            self.assertEqual("no_candidates", raised.exception.code)
            self.assertEqual(1, len(runner.commands))
            payload = json.loads(orchestrator.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual("failed", payload["status"])
            self.assertEqual([], payload["transitions"][0]["selected"])
            self.assertEqual(
                [payload["phases"][0]["run_directory"]],
                payload["dashboard"]["run_directories"],
            )

    def test_process_runner_uses_structured_arguments(self):
        runner = ManagedProcessRunner()
        with tempfile.TemporaryDirectory() as directory:
            result = runner.run(
                [sys.executable, "-c", "print('structured ok')"],
                cwd=Path(directory),
                cancel_event=threading.Event(),
            )
        self.assertEqual(0, result.returncode)
        self.assertEqual(("structured ok",), result.output_tail)

    def test_process_runner_cancels_the_child_process_group(self):
        runner = ManagedProcessRunner()
        cancel = threading.Event()
        timer = threading.Timer(0.2, cancel.set)
        started = time.monotonic()
        timer.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                result = runner.run(
                    [sys.executable, "-c", "import time; time.sleep(30)"],
                    cwd=Path(directory),
                    cancel_event=cancel,
                )
        finally:
            timer.cancel()
        self.assertTrue(result.cancelled)
        self.assertLess(time.monotonic() - started, 10)

    def test_reopen_dashboard_uses_one_to_three_confined_runs(self):
        base = load_config(ROOT / "benchmark.json")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = root / "results"
            session = results / "guided-session"
            session.mkdir(parents=True)
            runs = [session / profile for profile in ("smoke", "standard", "full")]
            for run in runs:
                run.mkdir()
            config = replace(
                base,
                root=root,
                dashboard=replace(base.dashboard, results_directory=results),
                guided=replace(base.guided, preferences_file=root / ".local" / "prefs.json"),
            )
            built: list[list[Path]] = []
            started: list[list[str]] = []
            orchestrator = GuidedOrchestrator(
                config,
                root / "benchmark.json",
                dashboard_builder=lambda selected: built.append(selected) or {},
                dashboard_starter=lambda args, *, cwd: started.append(list(args)),
            )
            manifest = session / "guided-run.json"
            manifest.write_text(
                json.dumps(
                    {
                        "dashboard": {
                            "status": "opened",
                            "run_directories": [
                                str(run.relative_to(root)) for run in runs
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(manifest, find_latest_manifest(config))
            orchestrator.reopen_dashboard(manifest)
            self.assertEqual([[run.resolve() for run in runs]], built)
            self.assertEqual(1, len(started))

            manifest.write_text(
                json.dumps(
                    {
                        "dashboard": {"status": "pending", "run_directories": []},
                        "phases": [
                            {
                                "profile": "smoke",
                                "status": "failed",
                                "run_directory": str(runs[0].relative_to(root)),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            built.clear()
            started.clear()
            self.assertEqual(manifest, find_latest_manifest(config))
            orchestrator.reopen_dashboard(manifest)
            self.assertEqual([[runs[0].resolve()]], built)
            self.assertEqual(1, len(started))

            manifest.write_text(
                json.dumps(
                    {
                        "dashboard": {
                            "run_directories": [
                                "results/guided-session/smoke",
                                "../outside",
                                "results/guided-session/full",
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(GuidedError) as raised:
                orchestrator.reopen_dashboard(manifest)
            self.assertEqual("dashboard_failed", raised.exception.code)

    def test_reopen_dashboard_wraps_dataset_errors_for_the_gui(self):
        base = load_config(ROOT / "benchmark.json")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = root / "results"
            session = results / "guided-session"
            session.mkdir(parents=True)
            run_paths = []
            for profile in ("smoke", "standard", "full"):
                run = session / profile
                run.mkdir()
                run_paths.append(str(run.relative_to(root)))
            manifest = session / "guided-run.json"
            manifest.write_text(
                json.dumps({"dashboard": {"run_directories": run_paths}}),
                encoding="utf-8",
            )
            config = replace(
                base,
                root=root,
                dashboard=replace(base.dashboard, results_directory=results),
                guided=replace(base.guided, preferences_file=root / ".local" / "prefs.json"),
            )

            def fail_dataset(_runs):
                raise DashboardDataError("dataset non valido")

            orchestrator = GuidedOrchestrator(
                config,
                root / "benchmark.json",
                dashboard_builder=fail_dataset,
            )
            with self.assertRaises(GuidedError) as raised:
                orchestrator.reopen_dashboard(manifest)
            self.assertEqual("dashboard_failed", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
