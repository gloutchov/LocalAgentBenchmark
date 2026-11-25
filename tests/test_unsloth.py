from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localagent_bench.ollama import OllamaModel
from localagent_bench.providers import LocalProvider, ProviderError
from localagent_bench.thinking import resolve_thinking_policy
from localagent_bench.unsloth import UnslothProvider


POLICY = {"inference_only": True}


def _row(name="local/coder", **extra):
    return {"id": name, "owned_by": "unsloth-studio", "loaded": True, "quant": "Q4_K_M", **extra}


def _answer(*, thinking=False, tool=False):
    message = {"role": "assistant", "content": "7"}
    if thinking:
        message["reasoning_content"] = "synthetic private reasoning"
    if tool:
        message["content"] = None
        message["tool_calls"] = [{"id": "call-probe", "type": "function", "function": {
            "name": "benchmark_probe", "arguments": '{"value":7}',
        }}]
    return {"choices": [{"message": message}]}


class UnslothAdapterTests(unittest.TestCase):
    def setUp(self):
        self.provider = LocalProvider("unsloth", "http://127.0.0.1:8000", runtime_version="verified-test")

    def test_factory_preserves_dedicated_adapter_contract(self):
        self.assertIsInstance(self.provider, UnslothProvider)
        self.assertTrue(self.provider.explicit_load)
        self.assertEqual("preloaded_manual", self.provider.lifecycle_mode)
        self.assertEqual("verified-test", self.provider.version())

    @patch("localagent_bench.providers._request")
    def test_discovery_filters_media_unloaded_nonlocal_and_ambiguous_models(self, request):
        request.side_effect = [POLICY, {"data": [
            _row(), _row("media", task="text-to-speech"), _row("unloaded", loaded=False),
            _row("foreign", owned_by="foreign"), _row("ambiguous", quant=None),
            _row("/private/model", quant="Q4"), _row("bad\nname"), _row("folder/../model"),
            _row("bool-loaded", loaded=1), _row("other", task="embedding"),
        ]}]
        models = self.provider.list_models()
        self.assertEqual(["local/coder"], [model.name for model in models])
        self.assertEqual("Q4_K_M", models[0].details["quantization_level"])
        self.assertEqual("api_quant", models[0].details["format_source"])
        self.assertIsNone(models[0].thinking_capable)
        self.assertEqual(["/benchmark/unsloth-policy", "/v1/models"],
                         [call.args[1] for call in request.call_args_list])

    @patch("localagent_bench.providers._request")
    def test_explicit_gguf_mapping_allows_absent_quant_without_claiming_api_proof(self, request):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "coder.gguf"
            path.write_bytes(b"synthetic-gguf")
            provider = LocalProvider("unsloth", self.provider.url, {"local/coder": path})
            request.side_effect = [POLICY, {"data": [_row(quant=None)]}]
            model = provider.list_models(with_digest=True)[0]
            self.assertEqual("configured_gguf_file", model.details["format_source"])
            self.assertEqual(hashlib.sha256(b"synthetic-gguf").hexdigest(), model.digest)
            self.assertNotIn(str(path), repr(model))

    @patch("localagent_bench.providers._request")
    def test_policy_must_be_verified_before_reading_models(self, request):
        for policy in ({}, {"inference_only": False}, {"inference_only": 1}, {"inference_only": "true"}):
            request.reset_mock()
            request.return_value = policy
            with self.assertRaisesRegex(ProviderError, "policy.*non verificata"):
                self.provider.list_models()
            self.assertEqual(1, request.call_count)

    @patch("localagent_bench.providers._request")
    def test_malformed_or_duplicate_model_lists_are_refused(self, request):
        for payload in ({"data": None}, {"data": [_row(), _row()]}):
            request.side_effect = [POLICY, payload]
            with self.assertRaises(ProviderError):
                self.provider.list_models()

    @patch("localagent_bench.providers._request")
    def test_load_verifies_residency_and_never_calls_model_management(self, request):
        request.side_effect = [POLICY, {"data": [_row()]}]
        self.assertEqual({"status": "resident_verified", "mode": "preloaded_manual"},
                         self.provider.load("local/coder", timeout=5))
        self.assertEqual("not_supported", self.provider.unload("local/coder")["status"])
        self.assertEqual(["/benchmark/unsloth-policy", "/v1/models"],
                         [call.args[1] for call in request.call_args_list])

    @patch("localagent_bench.providers._request")
    def test_missing_resident_model_is_a_manual_action_not_an_auto_load(self, request):
        request.side_effect = [POLICY, {"data": [_row(loaded=False)]}]
        with self.assertRaisesRegex(ProviderError, "caricarlo manualmente"):
            self.provider.load("local/coder", timeout=5)
        self.assertFalse(any(call.args[1].endswith("/load") for call in request.call_args_list))

    @patch("localagent_bench.providers._request")
    def test_inspect_retains_existing_digest_provenance(self, request):
        request.side_effect = [POLICY, {"data": [_row()]}]
        model = OllamaModel("local/coder", None, "digest", None, {"digest_source": "configured_gguf_file"})
        inspected = self.provider.inspect_model(model)
        self.assertEqual("digest", inspected.digest)
        self.assertEqual("configured_gguf_file", inspected.details["digest_source"])

    @patch("localagent_bench.providers._request")
    def test_thinking_and_inert_client_tool_probes_share_the_requested_policy(self, request):
        for level in ("off", "medium"):
            request.reset_mock()
            request.side_effect = [POLICY, {"data": [_row()]}, _answer(thinking=level == "medium"), _answer(tool=True)]
            result = self.provider.preflight_thinking(
                OllamaModel("local/coder", None, None, None, {}), resolve_thinking_policy(level), timeout=5,
            )
            self.assertTrue(result.passed)
            generations = [call.args[2] for call in request.call_args_list if call.args[1] == "/v1/chat/completions"]
            self.assertEqual(["none" if level == "off" else "medium"] * 2,
                             [payload["reasoning_effort"] for payload in generations])
            self.assertEqual("benchmark_probe", generations[-1]["tool_choice"]["function"]["name"])
            self.assertNotIn("synthetic private reasoning", repr(result))

    @patch("localagent_bench.providers._request")
    def test_model_without_verified_tool_calling_is_excluded(self, request):
        request.side_effect = [POLICY, {"data": [_row()]}, _answer(), _answer()]
        result = self.provider.preflight_thinking(
            OllamaModel("local/coder", None, None, None, {}), resolve_thinking_policy("off"), timeout=5,
        )
        self.assertEqual("tool_calling_not_verified", result.status)

    @patch("localagent_bench.providers._request")
    def test_malformed_tool_arguments_are_never_repaired_or_executed(self, request):
        for arguments in ('{"value":7.0}', "{'value':7}", '{"value":7,"extra":true}', '__import__("os")'):
            response = _answer(tool=True)
            response["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = arguments
            request.side_effect = [POLICY, {"data": [_row()]}, _answer(), response]
            result = self.provider.preflight_thinking(
                OllamaModel("local/coder", None, None, None, {}), resolve_thinking_policy("off"), timeout=5,
            )
            self.assertEqual("tool_calling_not_verified", result.status)

    @patch("localagent_bench.providers._request")
    def test_off_detects_reasoning_in_the_tool_probe_too(self, request):
        for response in (
            _answer(thinking=True, tool=True),
            {"choices": [{"message": {"content": "<think>unfinished"}}]},
            {**_answer(tool=True), "usage": {"reasoning_tokens": 3}},
        ):
            request.side_effect = [POLICY, {"data": [_row()]}, _answer(), response]
            result = self.provider.preflight_thinking(
                OllamaModel("local/coder", None, None, None, {}), resolve_thinking_policy("off"), timeout=5,
            )
            self.assertEqual("unexpected_thinking", result.status)
            self.assertTrue(result.thinking_observed)

    @patch("localagent_bench.providers._request")
    def test_warmup_verifies_residency_and_uses_same_effort(self, request):
        request.side_effect = [POLICY, {"data": [_row()]}, _answer()]
        result = self.provider.warmup("local/coder", resolve_thinking_policy("off"), timeout=5, context_window=8192)
        self.assertEqual("preloaded_manual", result["lifecycle_mode"])
        self.assertEqual("none", request.call_args.args[2]["reasoning_effort"])


class _GatewayHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def _reply(self, payload, status=200):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self.server.paths.append(self.path)
        if self.path == "/benchmark/unsloth-policy":
            self._reply(POLICY if self.server.policy else {}, 200 if self.server.policy else 503)
        elif self.path == "/v1/models":
            self._reply({"data": [_row()]})
        else:
            self._reply({}, 404)

    def do_POST(self):
        self.server.paths.append(self.path)
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/v1/chat/completions":
            self._reply(_answer(thinking=payload["reasoning_effort"] != "none", tool=bool(payload.get("tools"))))
        else:
            self._reply({}, 404)


class UnslothHttpTests(unittest.TestCase):
    def setUp(self):
        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", 0), _GatewayHandler)
        except OSError:
            self.skipTest("loopback non disponibile")
        self.server.paths = []
        self.server.policy = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._close)
        self.provider = LocalProvider("unsloth", f"http://127.0.0.1:{self.server.server_port}")

    def _close(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def test_http_roundtrip_and_manual_lifecycle(self):
        model = self.provider.list_models()[0]
        self.assertTrue(self.provider.preflight_thinking(model, resolve_thinking_policy("off"), timeout=5).passed)
        self.assertTrue(self.provider.preflight_thinking(model, resolve_thinking_policy("medium"), timeout=5).passed)
        self.provider.warmup(model.name, resolve_thinking_policy("off"), timeout=5, context_window=8192)
        self.assertEqual("not_supported", self.provider.unload(model.name)["status"])
        self.assertFalse(any(path.endswith("/load") or path.endswith("/unload") for path in self.server.paths))

    def test_http_policy_failure_blocks_discovery_before_models(self):
        self.server.policy = False
        with self.assertRaises(ProviderError):
            self.provider.list_models()
        self.assertEqual(["/benchmark/unsloth-policy"], self.server.paths)


if __name__ == "__main__":
    unittest.main()
