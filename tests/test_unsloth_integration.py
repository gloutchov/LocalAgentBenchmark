"""Synthetic Unsloth integration without a real credential store or LLM."""
from __future__ import annotations

import copy
import io
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from contextlib import redirect_stdout
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from urllib.error import HTTPError
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localagent_bench.cli import _parser, main as cli_main
from localagent_bench.comparison import ComparisonError, build_comparison
from localagent_bench.config import ConfigError, load_config
from localagent_bench.dashboard_data import _sanitize_exclusions
from localagent_bench.guided import GuidedError, GuidedOrchestrator
from localagent_bench.guided_process import ProcessResult
from localagent_bench.pi_adapter import PiRun
from localagent_bench.pi_compatibility import CONTRACT_VERSION, PiCompatibility
from localagent_bench.provider_session import provider_session
from localagent_bench.providers import ProviderError, _request
from localagent_bench.runner import BenchmarkError, doctor, run_benchmark


PASSED = PiCompatibility("passed", CONTRACT_VERSION, ("off_200", "medium_200", "off_500"))
FAILED = PiCompatibility("failed", CONTRACT_VERSION, (), "off_200_reasoning_effort")
MODEL = "synthetic/coder"


class _UnslothHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def _reply(self, value, status=200):
        raw = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _authorized(self):
        return self.headers.get("Authorization") == "Bearer " + self.server.secret

    def do_GET(self):
        self.server.calls.append(("GET", self.path))
        if not self._authorized():
            self._reply({"detail": "invalid credential"}, 401)
        elif self.path == "/v1/models":
            self._reply({"data": [{"id": MODEL, "owned_by": "unsloth-studio", "loaded": True,
                                    "quant": "Q4_K_M", "context_length": 32768}]})
        elif self.path == "/api/auth/api-keys":
            if self.server.inference_only:
                self._reply({"detail": self.server.scope_detail}, 403)
            else:
                self._reply({"api_keys": [{"name": "metadata-must-not-persist"}]})
        else:
            self._reply({}, 404)

    def do_POST(self):
        if not self._authorized():
            self._reply({}, 401)
            return
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.calls.append(("POST", self.path))
        self.server.payloads.append(payload)
        if self.path != "/v1/chat/completions":
            self._reply({}, 404)
            return
        if self.server.error:
            self._reply({"error": {"message": self.server.secret}}, 500)
            return
        prompt = payload["messages"][0]["content"]
        question = next((row for row in self.server.suite["questions"] if row["prompt"] in prompt), None)
        answer = json.dumps({"status": question["category"], "value": question["expected"]}) if question else "7"
        if not payload.get("stream"):
            message = {"role": "assistant", "content": answer}
            if payload.get("reasoning_effort") != "none":
                message["reasoning_content"] = "synthetic preflight reasoning"
            if payload.get("tools"):
                message["tool_calls"] = [{"id": "synthetic-call", "type": "function", "function": {
                    "name": "benchmark_probe", "arguments": '{"value":7}',
                }}]
            self._reply({"choices": [{"message": message}], "usage": {"completion_tokens": 12}})
            return
        chunks = [
            {"choices": [{"delta": {"content": answer[:5]}}]},
            {"choices": [{"delta": {"content": answer[5:]}}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}],
             "usage": {"prompt_tokens": 10, "completion_tokens": 12}},
        ]
        raw = b"".join(("data: " + json.dumps(row) + "\n\n").encode() for row in chunks) + b"data: [DONE]\n\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class UnslothConfigIntegrationTests(unittest.TestCase):
    def test_authentication_diagnostics_only_accept_static_gateway_codes(self):
        marker = "synthetic-private-" + uuid.uuid4().hex
        for status, code, expected in [
            (401, "provider_gateway_credential_rejected", "chiave API rifiutata"),
            (403, "provider_gateway_inference_scope_required", "sola inferenza"),
            (401, "provider_gateway_inference_scope_required", "HTTP 401"),
            (403, marker, "HTTP 403"),
        ]:
            with self.subTest(status=status, code=code):
                body = io.BytesIO(json.dumps({"error": {"code": code, "message": marker}}).encode())
                error = HTTPError("http://127.0.0.1/policy", status, marker, {}, body)
                with patch("localagent_bench.providers._OPENER.open", side_effect=error):
                    with self.assertRaisesRegex(ProviderError, expected) as caught:
                        _request("http://127.0.0.1:1234", "/benchmark/unsloth-policy")
                self.assertNotIn(marker, str(caught.exception))
                self.assertTrue(body.closed)

    def test_reference_transport_backend_and_secret_validation_precede_case_loading(self):
        raw = json.loads((ROOT / "benchmark.json").read_text(encoding="utf-8"))
        raw["provider"].update(kind="unsloth", credential_ref="integration-reference")
        mutations = [
            (lambda item: item["provider"].pop("credential_ref"), "credential_ref"),
            (lambda item: item["provider"].update(credential_ref="sk-unsloth-not-a-reference"), "credential_ref"),
            (lambda item: item["provider"].update(credential_ref="../unsafe"), "credential_ref"),
            (lambda item: item["provider"].update(api_key="synthetic-literal"), "Credenziali"),
            (lambda item: item["provider"].update(token="synthetic-literal"), "Credenziali"),
            (lambda item: item["provider"].update(transport={"timeout_seconds": True}), "transport|Transport"),
            (lambda item: item["provider"].update(transport={"max_connections": 0}), "transport|Transport"),
            (lambda item: item["provider"].update(transport={"unbounded": 1}), "transport|Transport"),
            (lambda item: item["provider"].update(backend_version={"invalid": True}), "backend_version"),
            (lambda item: item["provider"].update(backend_version=""), "backend_version"),
            (lambda item: item["provider"].update(url="http://127.0.0.1:0"), "porta|port"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "benchmark.json"
            for mutate, expected in mutations:
                changed = copy.deepcopy(raw)
                mutate(changed)
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.subTest(expected=expected), self.assertRaisesRegex(ConfigError, expected):
                    load_config(path)

    def test_cli_ephemeral_prompt_is_an_explicit_global_option(self):
        args = _parser().parse_args(["--credential-prompt", "run", "--thinking", "off"])
        self.assertTrue(args.credential_prompt)
        self.assertEqual("off", args.thinking)

    def test_unverified_client_tool_calling_is_a_provider_exclusion(self):
        manifest = {"thinking_control": {"requested": "off", "disqualified_models": [MODEL],
                    "preflights": {MODEL: {"status": "tool_calling_not_verified"}}}}
        exclusions = _sanitize_exclusions(manifest, {}, [MODEL])
        self.assertEqual([{"model": MODEL, "reason": "provider_incompatible", "case_id": None}], exclusions)
        manifest["thinking_control"]["preflights"][MODEL]["status"] = "context_window_mismatch"
        exclusions = _sanitize_exclusions(manifest, {}, [MODEL])
        self.assertEqual([{"model": MODEL, "reason": "provider_context_mismatch", "case_id": None}], exclusions)


class UnslothRuntimeIntegrationTests(unittest.TestCase):
    def setUp(self):
        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", 0), _UnslothHandler)
        except OSError:
            self.skipTest("loopback non disponibile")
        self.secret = "synthetic-" + uuid.uuid4().hex
        self.server.secret = self.secret
        self.server.scope_detail = "This API key is inference only: private scope detail must not persist."
        self.server.inference_only = True
        self.server.error = False
        self.server.calls = []
        self.server.payloads = []
        self.server.suite = json.loads((ROOT / "preliminary/suite.json").read_text(encoding="utf-8"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop_server)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.directory = tempfile.TemporaryDirectory(prefix="unsloth-integration-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        shutil.copytree(ROOT / "cases", self.root / "cases", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "preliminary", self.root / "preliminary")
        (self.root / "AGENTS.md").write_text("Synthetic test instructions. Work in this workspace only.\n", encoding="utf-8")
        (self.root / ".gitignore").write_text("results/\n__pycache__/\n*.pyc\n", encoding="utf-8")
        self.config_path = self.root / "benchmark.json"
        raw = json.loads((ROOT / "benchmark.json").read_text(encoding="utf-8"))
        raw["provider"].update(kind="unsloth", url=self.url, credential_ref="integration-reference",
                               runtime_version="synthetic-studio", backend_version="synthetic-llama")
        raw["preliminary"].update(repetitions=2, timeout_seconds=10)
        self.config_path.write_text(json.dumps(raw), encoding="utf-8")
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.name", "Synthetic Benchmark Test")
        self._git("config", "user.email", "synthetic@benchmark.invalid")
        self._git("add", ".")
        self._git("commit", "-q", "-m", "synthetic integration fixture")
        self.config = load_config(self.config_path)
        self.resolve = patch("localagent_bench.provider_session.resolve_credential", return_value=self.secret).start()
        self.addCleanup(patch.stopall)
        patch("localagent_bench.runner._command_version", return_value="synthetic-pi").start()
        patch("localagent_bench.runner.check_pi_compatibility", return_value=PASSED).start()
        patch("localagent_bench.runner.shutil.which", return_value="synthetic-command").start()

    def _git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True, timeout=30)

    def _stop_server(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def _run(self, name="task", **overrides):
        arguments = dict(profile="smoke", requested_models=[MODEL], requested_cases=["targeted_patch"],
                         repetitions=1, timeout_seconds=30, thinking_level="off", use_warmup=False,
                         output_dir=self.root / "results" / name, order_seed=7)
        arguments.update(overrides)
        with redirect_stdout(io.StringIO()):
            return run_benchmark(self.config, **arguments)

    def _assert_no_secret(self, directory):
        for path in directory.rglob("*"):
            if path.is_file() and ".git" not in path.parts:
                raw = path.read_bytes()
                for forbidden in (self.secret, "integration-reference", self.server.scope_detail,
                                  "metadata-must-not-persist"):
                    self.assertNotIn(forbidden.encode(), raw, str(path.relative_to(directory)))

    def test_task_uses_gateway_in_pi_config_but_records_stable_origin_and_honest_lifecycle(self):
        pi = PiRun("ok", 0, .01, "", "", {"usage": {"output": 1}, "tool_calls": 0, "tool_errors": 0}, "done", ["pi"])
        with patch("localagent_bench.runner.run_pi", return_value=pi) as run_pi:
            run_dir = self._run()
        manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(self.url, manifest["configuration"]["provider_url"])
        self.assertEqual(self.url, manifest["configuration"]["ollama_url"])
        self.assertEqual("synthetic-llama", manifest["environment"]["provider_backend_version"])
        self.assertEqual("preloaded_manual", manifest["provider_controls"]["lifecycle"])
        self.assertFalse(manifest["provider_controls"]["cold_start_verified"])
        self.assertEqual("preloaded", manifest["load_events"][0]["status"])
        pi_url = run_pi.call_args.args[8]
        self.assertNotEqual(self.url, pi_url)
        provider_file = next(run_dir.glob("models/*/cases/*/.pi-agent/models.json"))
        pi_settings = json.loads(provider_file.read_text(encoding="utf-8"))["providers"]["unsloth"]
        self.assertEqual(pi_url + "/v1", pi_settings["baseUrl"])
        self.assertEqual("unsloth", pi_settings["apiKey"])
        self.assertNotIn(self.secret, repr(run_pi.call_args))
        self._assert_no_secret(run_dir)
        self._assert_closed(pi_url)

    def _assert_closed(self, url):
        parsed = urlsplit(url)
        try:
            connection = socket.create_connection((parsed.hostname, parsed.port), timeout=.2)
        except OSError:
            return
        with connection:
            self.fail("Provider gateway remained open after session exit")

    def test_preliminary_streams_through_same_session_and_records_unload_unavailable(self):
        run_dir = self._run(name="preliminary", profile="preliminary", requested_cases=None,
                            repetitions=2, timeout_seconds=10)
        manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        observations = manifest["preliminary"]["observations"]
        self.assertEqual(20, len(observations))
        self.assertTrue(all(row["status"] == "ok" for row in observations))
        unloads = [row for row in manifest["preliminary"]["lifecycle"] if row["event"].startswith("unload")]
        self.assertEqual(["not_supported", "not_supported"], [row["status"] for row in unloads])
        self.assertEqual([], manifest["cases"])
        self.assertTrue(any(payload.get("stream") is True for payload in self.server.payloads))
        self.assertTrue(all(payload.get("enable_tools") is False for payload in self.server.payloads))
        self.assertTrue(all(payload.get("nudge_tool_calls") is False for payload in self.server.payloads))
        self._assert_no_secret(run_dir)

    def test_doctor_list_and_guided_discovery_share_policy_without_secret_in_ui(self):
        payload = doctor(self.config)
        self.assertTrue(payload["ok"])
        self.assertEqual([MODEL], [row["name"] for row in payload["models"]])
        self.assertNotIn(self.secret, json.dumps(payload))
        session = GuidedOrchestrator(self.config, config_path=self.config_path)
        guided = session.discover()
        self.assertEqual(MODEL, guided["models"][0]["name"])
        self.assertNotIn("integration-reference", json.dumps(session.settings_summary()))
        self.assertNotIn(self.secret, json.dumps(guided))
        with redirect_stdout(io.StringIO()) as output:
            status = cli_main(["--config", str(self.config_path), "list"])
        self.assertEqual(0, status)
        self.assertIn(MODEL, output.getvalue())
        self.assertNotIn(self.secret, output.getvalue())
        self.server.inference_only = False
        self.assertFalse(doctor(self.config)["ok"])
        with self.assertRaises(GuidedError):
            session.discover()

    def test_incompatible_pi_never_reads_credential_store_or_contacts_provider(self):
        self.resolve.reset_mock()
        with patch("localagent_bench.runner.check_pi_compatibility", return_value=FAILED):
            with self.assertRaisesRegex(BenchmarkError, "off_200_reasoning_effort"):
                self._run()
            self.assertFalse(doctor(self.config)["ok"])
        self.resolve.assert_not_called()
        self.assertEqual([], self.server.calls)

    def test_dirty_inputs_block_doctor_before_reading_credential(self):
        (self.root / "AGENTS.md").write_text("uncommitted synthetic instructions\n", encoding="utf-8")
        self.resolve.reset_mock()
        payload = doctor(self.config)
        self.assertFalse(payload["ok"])
        self.assertTrue(any(check["name"] == "inputs" and not check["ok"] for check in payload["checks"]))
        self.resolve.assert_not_called()
        self.assertEqual([], self.server.calls)

    def test_session_does_not_admit_non_gguf_mapping_fallbacks(self):
        config = replace(self.config, model_files={
            "gguf": self.root / "synthetic.GGUF", "other": self.root / "synthetic.safetensors",
        })
        with patch("localagent_bench.provider_session.ProviderGateway") as gateway:
            gateway.return_value.__enter__.return_value.url = "http://127.0.0.1:9999"
            with provider_session(config):
                pass
        self.assertEqual(("gguf",), gateway.call_args.kwargs["gguf_model_ids"])

    def test_guided_preliminary_cancellation_records_unload_unavailable(self):
        process = Mock()
        process.run.return_value = ProcessResult(-15, True, ())
        session = GuidedOrchestrator(self.config, config_path=self.config_path, process_runner=process)
        discovery = session.discover()
        self.resolve.reset_mock()
        with self.assertRaises(GuidedError) as caught:
            session.run([MODEL], discovery, preliminary=True)
        self.assertEqual("cancelled", caught.exception.code)
        manifest = json.loads(session.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("cancelled", manifest["status"])
        self.assertEqual("preliminary", manifest["phases"][0]["profile"])
        self.assertEqual([{"model": MODEL, "status": "not_supported"}], manifest["phases"][0]["cleanup"])
        self.resolve.assert_not_called()
        self._assert_no_secret(session.manifest_path.parent)

    def test_gateway_closes_when_run_raises_or_session_is_cancelled(self):
        urls = []
        def fail(config, **_kwargs):
            urls.append(config.ollama_url)
            raise RuntimeError("synthetic failure")
        with patch("localagent_bench.runner._run_provider_session", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
                self._run()
        self._assert_closed(urls[0])
        with self.assertRaises(KeyboardInterrupt):
            with provider_session(self.config) as active:
                cancelled_url = active.ollama_url
                raise KeyboardInterrupt()
        self._assert_closed(cancelled_url)

    def test_comparison_requires_backend_version_as_well_as_runtime_and_hash(self):
        # Keep this test independent from model task scores by constructing only
        # the small supported run/report contract used by comparison.
        from test_comparison import ComparisonTests
        helper = ComparisonTests()
        runs = [helper._write_run(self.root, name, overall=75, verified_thinking=True) for name in ("first", "second")]
        for run in runs:
            path = run / "run.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["configuration"].update(provider_kind="unsloth", provider_url=self.url)
            manifest["environment"].update(provider_kind="unsloth", provider_version="synthetic-studio",
                                          provider_backend_version="synthetic-llama")
            for metadata in manifest["model_metadata"].values():
                metadata.setdefault("details", {})["context_length"] = 32768
            path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertEqual("unsloth", build_comparison(runs)["compatibility"]["provider_kind"])
        context_path = runs[1] / "run.json"
        context_manifest = json.loads(context_path.read_text(encoding="utf-8"))
        metadata = next(iter(context_manifest["model_metadata"].values()))
        for context in (65536, None, True):
            metadata["details"]["context_length"] = context
            context_path.write_text(json.dumps(context_manifest), encoding="utf-8")
            with self.subTest(resident_context=context), self.assertRaises(ComparisonError):
                build_comparison(runs)
        metadata["details"]["context_length"] = 32768
        context_path.write_text(json.dumps(context_manifest), encoding="utf-8")
        for field in ("provider_backend_version", "provider_version"):
            path = runs[1] / "run.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            original = manifest["environment"].pop(field)
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.subTest(field=field), self.assertRaises(ComparisonError):
                build_comparison(runs)
            manifest["environment"][field] = original
            path.write_text(json.dumps(manifest), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
