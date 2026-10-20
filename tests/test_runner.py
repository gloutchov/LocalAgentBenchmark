from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localagent_bench.config import CaseSpec, load_config
from localagent_bench.integrity import (
    InputIntegrityError,
    fingerprint_tree,
    require_clean_inputs,
    snapshot_cases,
    verify_snapshot,
)
from localagent_bench.ollama import OllamaModel, ThinkingPreflight
from localagent_bench.pi_adapter import AUDIT_VERSION, SCRATCH_DIRECTORY, PiRun
from localagent_bench.pi_compatibility import CONTRACT_VERSION, PiCompatibility
from localagent_bench.runner import (
    BenchmarkError,
    EXECUTION_POLICY,
    _build_task_order,
    _capture_git,
    _git,
    _prepare_workspace,
    run_benchmark,
)


def _ollama_test_config():
    return replace(
        load_config(ROOT / "benchmark.json"),
        provider_kind="ollama",
        ollama_url="http://127.0.0.1:11434",
        provider_version=None,
        model_files={},
    )


def _mock_provider(factory, model, preflight, *, kind="ollama", runtime_version="test"):
    provider = factory.return_value
    provider.kind = kind
    provider.explicit_load = kind != "ollama"
    provider.infer_capability_from_preflight = kind != "ollama"
    provider.version_source = "api" if kind == "ollama" else "configuration"
    provider.list_models.return_value = [model]
    provider.fingerprint_model.side_effect = lambda item: item
    provider.inspect_model.return_value = model
    provider.preflight_thinking.return_value = preflight
    provider.version.return_value = runtime_version
    provider.warmup.return_value = {}
    return provider


class RunnerGitTests(unittest.TestCase):
    def setUp(self):
        patcher = patch(
            "localagent_bench.runner.check_pi_compatibility",
            return_value=PiCompatibility("passed", CONTRACT_VERSION, ("off_200", "medium_200", "off_500")),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_diff_includes_committed_and_untracked_changes(self):
        config = load_config(ROOT / "benchmark.json")
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            workspace = Path(directory) / "workspace"
            baseline = _prepare_workspace(config, config.cases["targeted_patch"], workspace)
            self.assertTrue((workspace / SCRATCH_DIRECTORY).is_dir())
            self.assertNotIn(SCRATCH_DIRECTORY, _git(workspace, "status", "--short").stdout)
            readme = workspace / "README.md"
            readme.write_text(readme.read_text(encoding="utf-8") + "\ncommitted marker\n", encoding="utf-8")
            _git(workspace, "add", "README.md")
            _git(workspace, "commit", "-q", "-m", "candidate commit")
            (workspace / "NEW.md").write_text("untracked marker\n", encoding="utf-8")
            _, diff, _ = _capture_git(workspace, baseline)
            self.assertIn("committed marker", diff)
            self.assertIn("untracked marker", diff)

    def test_snapshot_is_stable_and_detects_changes(self):
        config = load_config(ROOT / "benchmark.json")
        case = config.cases["milestone_closure"]
        with tempfile.TemporaryDirectory() as directory:
            context = Path(directory) / "context"
            snapshots, manifest = snapshot_cases(
                [case],
                context,
                ROOT / "AGENTS.md",
                ROOT / ".gitignore",
                EXECUTION_POLICY,
            )
            self.assertEqual(
                manifest["cases"]["milestone_closure"]["fixture_sha256"],
                fingerprint_tree(snapshots[0].fixture_path),
            )
            self.assertFalse(any(path.name == "__pycache__" for path in snapshots[0].fixture_path.rglob("*")))
            self.assertTrue((context / "EXECUTION_POLICY.snapshot.md").is_file())
            self.assertTrue(manifest["cases"]["milestone_closure"]["effective_input_sha256"])
            self.assertTrue(snapshots[0].manifest_path.is_file())
            self.assertTrue(snapshots[0].manual_rubric_path.is_file())
            self.assertTrue(manifest["cases"]["milestone_closure"]["manifest_sha256"])
            self.assertTrue(manifest["cases"]["milestone_closure"]["manual_rubric_sha256"])
            self.assertEqual([], verify_snapshot(context, manifest))
            baseline_trees = []
            for name in ("first", "second"):
                workspace = Path(directory) / name
                baseline = _prepare_workspace(
                    config,
                    snapshots[0],
                    workspace,
                    context / "AGENTS.snapshot.md",
                    context / ".gitignore.snapshot",
                )
                baseline_trees.append(_git(workspace, "rev-parse", f"{baseline}^{{tree}}").stdout.strip())
            self.assertEqual(baseline_trees[0], baseline_trees[1])
            prompt = snapshots[0].prompt_path
            prompt.write_text(prompt.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
            self.assertIn("cases/milestone_closure/prompt.md", verify_snapshot(context, manifest))

    def test_milestone_fixture_provides_required_license(self):
        config = load_config(ROOT / "benchmark.json")
        case = config.cases["milestone_closure"]
        self.assertTrue((case.fixture_path / "LICENSE").is_file())
        self.assertIn("Apache License", (case.fixture_path / "LICENSE").read_text(encoding="utf-8"))

    def test_task_order_is_seeded_and_complete(self):
        config = load_config(ROOT / "benchmark.json")
        cases = [config.cases["targeted_patch"], config.cases["secure_workspace"]]
        first = _build_task_order(["a", "b"], cases, 2, 42)
        second = _build_task_order(["a", "b"], cases, 2, 42)
        self.assertEqual(first, second)
        self.assertEqual(8, len(first))
        self.assertEqual(
            {("a", "targeted_patch", 1), ("a", "targeted_patch", 2),
             ("a", "secure_workspace", 1), ("a", "secure_workspace", 2),
             ("b", "targeted_patch", 1), ("b", "targeted_patch", 2),
             ("b", "secure_workspace", 1), ("b", "secure_workspace", 2)},
            {(item["model"], item["case_id"], item["repetition"]) for item in first},
        )

    def test_run_rejects_incompatible_pi_before_contacting_ollama(self):
        config = load_config(ROOT / "benchmark.json")
        with (
            patch("localagent_bench.runner.require_clean_inputs"),
            patch("localagent_bench.runner._command_version", return_value="0.99.0"),
            patch("localagent_bench.runner.check_pi_compatibility", return_value=PiCompatibility("failed", CONTRACT_VERSION, (), "off_200_reasoning_effort")),
            patch("localagent_bench.runner.create_provider") as provider_factory,
        ):
            with self.assertRaisesRegex(BenchmarkError, "off_200_reasoning_effort"):
                run_benchmark(
                    config,
                    profile="smoke",
                    requested_models=None,
                    requested_cases=None,
                    repetitions=1,
                    timeout_seconds=30,
                    thinking_level="off",
                    use_warmup=False,
                    output_dir=None,
                )
        provider_factory.assert_not_called()

    def test_local_provider_loads_model_even_without_warmup(self):
        model = OllamaModel("local/coder", 1, "gguf-digest", None, {})
        config = replace(load_config(ROOT / "benchmark.json"), provider_kind="lmstudio",
                         ollama_url="http://127.0.0.1:1234", provider_version="0.4.0")
        pi_result = PiRun("ok", 0, 0.1, "", "", {"usage": {"output": 1}, "tool_calls": 0,
                                                    "tool_errors": 0}, "done", ["pi"])
        with tempfile.TemporaryDirectory() as directory:
            with (patch("localagent_bench.runner.require_clean_inputs"),
                  patch("localagent_bench.runner._command_version", return_value="0.84.3"),
                  patch("localagent_bench.runner.create_provider") as provider_factory,
                  patch("localagent_bench.runner.run_pi", return_value=pi_result) as pi_mock):
                provider = _mock_provider(
                    provider_factory, model,
                    ThinkingPreflight("passed", "off", "none", None, False, 0, None, 1),
                    kind="lmstudio", runtime_version="0.4.0",
                )
                run_dir = run_benchmark(
                    config, profile="smoke", requested_models=[model.name],
                    requested_cases=["milestone_closure"], repetitions=1,
                    timeout_seconds=30, thinking_level="off", use_warmup=False,
                    output_dir=Path(directory) / "run", order_seed=1,
                )
            provider.load.assert_called_once_with(model.name, timeout=30)
            self.assertEqual("lmstudio", pi_mock.call_args.kwargs["provider_kind"])
            settings = next(run_dir.glob("models/*/cases/*/.pi-agent/models.json"))
            self.assertIn("lmstudio", json.loads(settings.read_text(encoding="utf-8"))["providers"])
            manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertEqual("loaded", manifest["load_events"][0]["status"])

    @patch("localagent_bench.runner._command_version", return_value="0.85.1")
    @patch("localagent_bench.runner.require_clean_inputs")
    @patch("localagent_bench.runner.run_pi")
    @patch("localagent_bench.runner.create_provider")
    def test_run_uses_frozen_inputs_and_records_integrity(
        self,
        provider_factory,
        run_pi_mock,
        _require_clean_inputs_mock,
        _command_version_mock,
    ):
        model = OllamaModel("model:a", 1, "digest", "now", {})
        run_pi_mock.return_value = PiRun(
            status="ok",
            exit_code=0,
            duration_seconds=1.0,
            stdout="",
            stderr="",
            metrics={"usage": {"output": 1}, "tool_calls": 0, "tool_errors": 0},
            final_response="done",
            command=["pi"],
            sandbox={"backend": "audit-only", "enforced": False},
            system_metrics={
                "process": {"available": True, "user_seconds": 0.2, "system_seconds": 0.1},
                "energy": {"available": False},
            },
        )
        config = _ollama_test_config()
        with tempfile.TemporaryDirectory() as directory:
            preflight = ThinkingPreflight("passed", "off", "none", None, False, 0, 0, 1)
            _mock_provider(provider_factory, model, preflight)
            run_dir = run_benchmark(
                config,
                profile="smoke",
                requested_models=["model:a"],
                requested_cases=["milestone_closure"],
                repetitions=1,
                timeout_seconds=30,
                thinking_level=None,
                use_warmup=False,
                output_dir=Path(directory) / "run",
                order_seed=7,
            )
            result_path = next(run_dir.glob("models/*/cases/*/result.json"))
            result = json.loads(result_path.read_text(encoding="utf-8"))
            report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
            self.assertTrue(result["integrity"]["valid_for_ranking"])
            self.assertEqual(AUDIT_VERSION, result["integrity"]["audit_version"])
            self.assertTrue(result["baseline_tree"])
            self.assertEqual("passed", report["integrity"]["status"])
            manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(7, manifest["order_seed"])
            self.assertEqual("0.13.3", manifest["benchmark_version"])
            self.assertEqual("passed", manifest["pi_compatibility"]["status"])
            self.assertEqual(32768, manifest["configuration"]["context_window"])
            self.assertEqual(30, manifest["configuration"]["timeout_seconds"])
            self.assertEqual(AUDIT_VERSION, manifest["execution_policy"]["audit_version"])
            self.assertEqual("audit-only", manifest["sandbox"]["backend"])
            self.assertFalse(manifest["sandbox"]["enforced"])
            self.assertEqual(4, result["schema_version"])
            self.assertEqual(4, manifest["schema_version"])
            self.assertEqual("none", manifest["thinking_control"]["reasoning_effort"])
            self.assertEqual("passed", manifest["thinking_control"]["status"])
            self.assertEqual("passed", result["thinking_control"]["preflight"])
            self.assertEqual(1, result["case_manifest_schema_version"])
            self.assertEqual("Milestone closure, versioning, and Git discipline", result["case_title_en"])
            self.assertFalse(result["manual_rubric"]["included_in_automatic_score"])
            self.assertTrue((result_path.parent / "manual-rubric.md").is_file())
            self.assertTrue(result["system_metrics"]["process"]["available"])
            self.assertIn("hardware", manifest["environment"])
            self.assertIn("Non accedere alla rete", run_pi_mock.call_args.args[3])
            self.assertTrue((result_path.parent / "workspace" / SCRATCH_DIRECTORY).is_dir())
            self.assertTrue((result_path.parent / ".pi-agent" / "models.json").is_file())
            markdown = (run_dir / "REPORT.md").read_text(encoding="utf-8")
            self.assertIn("Sandbox: **audit-only** (audit-only)", markdown)
            self.assertIn("0.30s", markdown)
            self.assertIn("## Rubriche manuali", markdown)
            self.assertIn("manual-rubric.md", markdown)

    def test_preflight_rejects_dirty_case_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_root = root / "cases" / "example"
            fixture = case_root / "fixture"
            fixture.mkdir(parents=True)
            (root / "AGENTS.md").write_text("rules\n", encoding="utf-8")
            (root / ".gitignore").write_text("results/\n", encoding="utf-8")
            (case_root / "prompt.md").write_text("prompt\n", encoding="utf-8")
            (case_root / "grader.py").write_text("print('{}')\n", encoding="utf-8")
            (fixture / "README.md").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=root, check=True)
            case = CaseSpec(
                id="example",
                title="Example",
                category="test",
                weight=1,
                directory=case_root,
                prompt_path=case_root / "prompt.md",
                fixture_path=fixture,
                grader_path=case_root / "grader.py",
            )
            require_clean_inputs(root, [case])
            (case_root / "prompt.md").write_text("changed\n", encoding="utf-8")
            with self.assertRaises(InputIntegrityError):
                require_clean_inputs(root, [case])

    @patch("localagent_bench.runner._command_version", return_value="0.85.1")
    @patch("localagent_bench.runner.require_clean_inputs")
    @patch("localagent_bench.runner.run_pi")
    @patch("localagent_bench.runner.create_provider")
    def test_showcase_profile_runs_from_the_frozen_synthetic_dataset(
        self,
        provider_factory,
        run_pi_mock,
        _require_clean_inputs_mock,
        _command_version_mock,
    ):
        model = OllamaModel("showcase:test", 1, "digest", "now", {})
        run_pi_mock.return_value = PiRun(
            status="ok",
            exit_code=0,
            duration_seconds=0.5,
            stdout="",
            stderr="",
            metrics={"usage": {"output": 1}, "tool_calls": 0, "tool_errors": 0},
            final_response="synthetic test run",
            command=["pi"],
            sandbox={"backend": "audit-only", "enforced": False},
            system_metrics={"process": {"available": False}, "energy": {"available": False}},
        )
        config = _ollama_test_config()
        with tempfile.TemporaryDirectory() as directory:
            preflight = ThinkingPreflight("passed", "off", "none", None, False, 0, 0, 1)
            _mock_provider(provider_factory, model, preflight)
            run_dir = run_benchmark(
                config,
                profile="showcase",
                requested_models=[model.name],
                requested_cases=None,
                repetitions=1,
                timeout_seconds=30,
                thinking_level=None,
                use_warmup=False,
                output_dir=Path(directory) / "showcase-run",
                order_seed=20260903,
            )
            result_path = next(run_dir.glob("models/*/cases/*/result.json"))
            result = json.loads(result_path.read_text(encoding="utf-8"))
            manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            workspace = result_path.parent / "workspace"
            self.assertEqual("showcase", manifest["profile"])
            self.assertEqual("results_dashboard", result["case_id"])
            self.assertEqual(20, result["manual_rubric"]["max_score"])
            self.assertLess(result["grade"]["score"], 60)
            self.assertTrue((workspace / "dashboard-data.json").is_file())
            self.assertEqual(2, json.loads((workspace / "dashboard-data.json").read_text())["schema_version"])

    @patch("localagent_bench.runner._command_version", return_value="0.85.1")
    @patch("localagent_bench.runner.require_clean_inputs")
    @patch("localagent_bench.runner.run_pi")
    @patch("localagent_bench.runner.create_provider")
    def test_failed_thinking_preflight_excludes_model_before_showcase_task(
        self,
        provider_factory,
        run_pi_mock,
        _require_clean_inputs_mock,
        _command_version_mock,
    ):
        model = OllamaModel(
            "showcase:test", 1, "digest", "now", {}, ("thinking",), True, True
        )
        failed = ThinkingPreflight(
            "unexpected_thinking", "off", "none", True, True, 12, 4, 2
        )
        config = _ollama_test_config()
        with tempfile.TemporaryDirectory() as directory:
            _mock_provider(provider_factory, model, failed)
            run_dir = run_benchmark(
                config,
                profile="showcase",
                requested_models=[model.name],
                requested_cases=None,
                repetitions=1,
                timeout_seconds=30,
                thinking_level="off",
                use_warmup=False,
                output_dir=Path(directory) / "showcase-run",
                order_seed=7,
            )
            run_pi_mock.assert_not_called()
            manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
            self.assertEqual("failed", manifest["thinking_control"]["status"])
            self.assertEqual([model.name], manifest["thinking_control"]["disqualified_models"])
            self.assertEqual([model.name], report["integrity"]["disqualified_models"])
            self.assertEqual([], report["leaderboard"])

    @patch("localagent_bench.runner._command_version", return_value="0.85.1")
    @patch("localagent_bench.runner.require_clean_inputs")
    @patch("localagent_bench.runner.run_pi")
    @patch("localagent_bench.runner.create_provider")
    def test_off_task_with_thinking_or_retry_disqualifies_entire_model(
        self,
        provider_factory,
        run_pi_mock,
        _require_clean_inputs_mock,
        _command_version_mock,
    ):
        model = OllamaModel(
            "model:a", 1, "digest", "now", {}, ("thinking",), True, True
        )
        run_pi_mock.return_value = PiRun(
            status="ok",
            exit_code=0,
            duration_seconds=0.5,
            stdout="",
            stderr="",
            metrics={
                "usage": {"output": 1, "reasoning": 3},
                "tool_calls": 0,
                "tool_errors": 0,
                "streamed_thinking_chars": 7,
                "retry_events": 1,
            },
            final_response="done",
            command=["pi"],
            sandbox={"backend": "audit-only", "enforced": False},
            system_metrics={"process": {"available": False}, "energy": {"available": False}},
        )
        passed = ThinkingPreflight("passed", "off", "none", True, False, 0, 0, 1)
        config = _ollama_test_config()
        with tempfile.TemporaryDirectory() as directory:
            provider = _mock_provider(provider_factory, model, passed)
            run_dir = run_benchmark(
                config,
                profile="smoke",
                requested_models=[model.name],
                requested_cases=None,
                repetitions=1,
                timeout_seconds=30,
                thinking_level="off",
                use_warmup=True,
                output_dir=Path(directory) / "run",
                order_seed=7,
            )
            result_path = next(run_dir.glob("models/*/cases/*/result.json"))
            result = json.loads(result_path.read_text(encoding="utf-8"))
            report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
            reasons = {
                item["reason"] for item in result["integrity"]["thinking_control_violations"]
            }
            self.assertEqual({"unexpected_thinking", "unexpected_retry"}, reasons)
            self.assertFalse(result["integrity"]["valid_for_ranking"])
            self.assertEqual([model.name], report["integrity"]["disqualified_models"])
            self.assertEqual([], report["leaderboard"])
            policy = provider.warmup.call_args.args[1]
            self.assertEqual("off", policy.requested)
            self.assertEqual("none", policy.reasoning_effort)


if __name__ == "__main__":
    unittest.main()
