from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from test_guided import ROOT, write_phase
from localagent_bench.cli import main
from localagent_bench.config import load_config
from localagent_bench.guided import GuidedCancelled, GuidedError, GuidedOrchestrator
from localagent_bench.guided_process import ProcessResult
from localagent_bench.integrity import InputIntegrityError, fingerprint_tree
from localagent_bench.multi_provider import ModelSelection, MultiProviderSession
from localagent_bench.runner import EXECUTION_POLICY
from localagent_bench.session_dashboard import load_session_dashboard
from localagent_bench.session_inputs import CONTEXT_NAME, freeze_session_inputs, session_context


class SessionProcess:
    def __init__(self, *, missing=None, timeout=None, mutate=False, cancel=False):
        self.missing = missing
        self.timeout = timeout
        self.mutate = mutate
        self.cancel = cancel
        self.calls = []

    def run(self, command, *, cwd, cancel_event, on_line):
        def argument(name):
            return command[command.index(name) + 1]

        provider, profile = argument("--provider"), argument("--profile")
        output = Path(argument("--output"))
        models = command[command.index("--models") + 1:command.index("--seed")]
        digest = argument("--session-input-hash")
        self.calls.append((provider, profile, digest))
        config = load_config(cwd / "benchmark.json")
        cases = [config.cases[case] for case in config.profiles[profile]]
        context, _, _ = session_context(config, output, digest, cases, (), EXECUTION_POLICY)
        if self.cancel:
            return ProcessResult(-15, True, ())
        if self.mutate:
            (context / "AGENTS.snapshot.md").write_text("changed", encoding="utf-8")
        if provider == self.missing:
            return ProcessResult(2, False, ("private upstream error",))
        failed = provider == self.timeout
        written = write_phase(output.parent, profile, models, models if not failed else [], failed=failed)
        written.rename(output)
        run_path = output / "run.json"
        run = json.loads(run_path.read_text())
        run.update(schema_version=4, configuration={"provider_kind": provider}, order_seed=int(argument("--seed")),
                   session={"id": output.parent.name, "input_sha256": digest})
        run_path.write_text(json.dumps(run), encoding="utf-8")
        report_path = output / "report.json"
        report = json.loads(report_path.read_text())
        report["schema_version"] = 4
        if failed:
            report["results"][0]["status"] = "timeout"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return ProcessResult(1 if failed else 0, False, ())


class MultiProviderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in ("AGENTS.md", ".gitignore"):
            shutil.copy2(ROOT / name, self.root / name)
        shutil.copytree(ROOT / "cases", self.root / "cases", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "preliminary", self.root / "preliminary")
        raw = json.loads((ROOT / "benchmark.json").read_text())
        raw["additional_providers"] = [
            {"kind": "lmstudio", "url": "http://127.0.0.1:1234"},
            {"kind": "colibri", "url": "http://127.0.0.1:8000"},
        ]
        raw["guided"]["model_wait_timeout_seconds"] = 1
        raw["guided"]["preliminary"] = False
        self.path = self.root / "benchmark.json"
        self.path.write_text(json.dumps(raw), encoding="utf-8")
        for args in (["init", "-q"], ["add", "."],
                     ["-c", "user.name=Synthetic Test", "-c", "user.email=test@example.invalid",
                      "commit", "-qm", "synthetic inputs"]):
            subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)
        self.config = load_config(self.path)

    def orchestrator(self, process, *, doctor=None):
        def discover(config):
            if config.provider_kind == "colibri" and doctor:
                return doctor(config)
            return {"ok": True, "models": [{"name": "same"}]}
        return MultiProviderSession(GuidedOrchestrator(
            self.config, self.path, process_runner=process, doctor_function=discover,
        ))

    def test_same_id_two_providers_share_snapshot_and_seed_and_keep_timeouts(self):
        process = SessionProcess(timeout="lmstudio")
        session = self.orchestrator(process)
        manifest = session.run([ModelSelection("ollama", "same"), ModelSelection("lmstudio", "same")],
                               sandbox="audit", profile="smoke", seed=23, open_dashboard=False)
        data = json.loads(manifest.read_text())
        self.assertEqual("partial", data["status"])
        self.assertEqual([23, 23], [row["seed"] for row in data["phases"]])
        self.assertEqual(1, len({digest for _, _, digest in process.calls}))
        dataset, public = load_session_dashboard(manifest, root=self.root, results=self.root / "results")
        self.assertEqual({"ollama", "lmstudio"}, {run["provider"] for run in dataset["runs"]})
        self.assertEqual([], dataset["funnel"])
        self.assertEqual(["ollama", "lmstudio"], [row["provider"] for row in public["phases"]])
        self.assertEqual("timeout", public["phases"][-1]["reason"])
        self.assertNotIn(str(self.root), json.dumps(public))

    def test_completed_session_starts_one_dashboard_for_the_manifest(self):
        session = self.orchestrator(SessionProcess())
        with patch.object(session.guided, "dashboard_starter") as start:
            path = session.run([ModelSelection("ollama", "same"), ModelSelection("lmstudio", "same")],
                               sandbox="audit", profile="smoke")
        start.assert_called_once()
        self.assertEqual(["--session", str(path)], start.call_args.args[0][-2:])
        self.assertEqual("opened", json.loads(path.read_text())["dashboard"]["status"])

    def test_unavailable_model_does_not_block_other_models_of_same_provider(self):
        session = self.orchestrator(SessionProcess())
        manifest = session.run(
            [ModelSelection("ollama", "same"), ModelSelection("ollama", "missing"),
             ModelSelection("lmstudio", "same")],
            sandbox="audit", profile="smoke", open_dashboard=False,
        )
        payload = json.loads(manifest.read_text())
        self.assertEqual("partial", payload["status"])
        self.assertEqual([{"model": "missing", "reason": "model_unavailable"}],
                         payload["phases"][0]["exclusions"])
        self.assertEqual(2, len(payload["dashboard"]["run_directories"]))

    def test_unavailable_provider_and_cancelled_process(self):
        selections = [ModelSelection("lmstudio", "same"), ModelSelection("ollama", "same")]
        manifest = self.orchestrator(SessionProcess(missing="lmstudio")).run(
            selections, sandbox="audit", profile="smoke", open_dashboard=False,
        )
        raw = manifest.read_text()
        self.assertNotIn("private upstream error", raw)
        self.assertEqual(["excluded", "completed"], [row["status"] for row in json.loads(raw)["phases"]])
        session = self.orchestrator(SessionProcess(cancel=True))
        with self.assertRaises(GuidedCancelled):
            session.run(selections, sandbox="audit", profile="smoke", open_dashboard=False)
        self.assertEqual("cancelled", json.loads(session.manifest_path.read_text())["status"])

    def test_manual_load_rechecks_id_and_context_before_running(self):
        process = SessionProcess()
        resident = iter([("old", 32768), ("same", 8192), ("same", 65536)])

        def doctor(config):
            model, context = next(resident)
            return {"ok": True, "models": [{"name": model, "details": {"context_length": context}}]}

        session = self.orchestrator(process, doctor=doctor)
        events = []

        def confirm(event):
            events.append(event["type"])
            if event["type"] == "model_wait":
                session.resume()

        path = session.run([ModelSelection("colibri", "same"), ModelSelection("ollama", "same")],
                           sandbox="audit", profile="smoke", open_dashboard=False, callback=confirm)
        self.assertEqual(2, events.count("model_wait"))
        self.assertEqual(["colibri", "ollama"], [kind for kind, _, _ in process.calls])
        self.assertIsNotNone(json.loads(path.read_text())["phases"][0]["manual_wait_seconds"])

    def test_wait_timeout_and_cancellation(self):
        def doctor(config):
            return {"ok": True, "models": [{"name": "old", "details": {"context_length": 65536}}]}

        selections = [ModelSelection("colibri", "same"), ModelSelection("ollama", "same")]
        session = self.orchestrator(SessionProcess(), doctor=doctor)
        path = session.run(selections, sandbox="audit", profile="smoke", open_dashboard=False,
                           callback=lambda event: None)
        self.assertEqual("model_wait_timeout", json.loads(path.read_text())["phases"][0]["reason"])
        session = self.orchestrator(SessionProcess(), doctor=doctor)
        with self.assertRaises(GuidedCancelled):
            session.run(selections, sandbox="audit", profile="smoke", open_dashboard=False,
                        callback=lambda event: session.cancel() if event["type"] == "model_wait" else None)

    def test_mutation_aborts_matrix_and_rejects_forged_snapshot(self):
        selections = [ModelSelection("ollama", "same"), ModelSelection("lmstudio", "same")]
        process = SessionProcess(mutate=True)
        session = self.orchestrator(process)
        with self.assertRaisesRegex(GuidedError, "Snapshot"):
            session.run(selections, sandbox="audit", profile="smoke", open_dashboard=False)
        self.assertEqual(1, len(process.calls))
        data = json.loads(session.manifest_path.read_text())
        self.assertEqual({"status": "invalidated", "run_directories": []}, data["dashboard"])
        folder = session.manifest_path.parent
        cases = [self.config.cases[case] for case in self.config.profiles["smoke"]]
        with self.assertRaises(InputIntegrityError):
            session_context(self.config, folder / "forged", fingerprint_tree(folder / CONTEXT_NAME),
                            cases, (), EXECUTION_POLICY)

    def test_shared_context_preliminary_policy_and_suite(self):
        from localagent_bench.preliminary import PRELIMINARY_POLICY
        folder = self.root / "results" / "guided-multi-20261128-123000-ab1234"
        folder.mkdir(parents=True)
        digest = freeze_session_inputs(self.config, folder, ("preliminary", "smoke"), EXECUTION_POLICY)
        context, cases, manifest = session_context(self.config, folder / "preliminary", digest, [],
                                                  (self.config.preliminary.suite,),
                                                  EXECUTION_POLICY + PRELIMINARY_POLICY)
        self.assertEqual([], cases)
        self.assertNotEqual(manifest["execution_policy_sha256"], manifest["preliminary_policy_sha256"])
        self.assertTrue((context / "extra-0.json").is_file())

    def test_cli_dispatches_paired_selection(self):
        real = self.orchestrator(SessionProcess())
        with patch("localagent_bench.cli.MultiProviderSession", return_value=real), redirect_stdout(StringIO()):
            status = main(["--config", str(self.path), "session", "--model", "ollama=same", "--model",
                           "lmstudio=same", "--profile", "smoke", "--sandbox", "audit", "--no-open"])
        self.assertEqual(0, status)
        self.assertTrue(real.manifest_path.is_file())


if __name__ == "__main__":
    unittest.main()
