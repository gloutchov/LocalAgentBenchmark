from __future__ import annotations

import json
import sys
import threading
import unittest
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localagent_bench.providers import LocalProvider, ProviderError
from localagent_bench.config import load_config
from localagent_bench.provider_adapter import create_provider
from localagent_bench.thinking import resolve_thinking_policy


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def _reply(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.server.calls.append(("GET", self.path, None))
        if self.server.redirect:
            self.send_response(302)
            self.send_header("Location", "https://example.invalid/remote")
            self.end_headers()
        elif self.path == "/api/v1/models":
            self._reply({"models": [{"key": "local/coder", "type": "llm", "size_bytes": 8,
                                      "loaded_instances": [{"id": "local/coder@1"}],
                                      "capabilities": {"reasoning": {"allowed_options": ["off", "medium"]}}}]})
        elif self.path == "/models":
            if self.server.unload_polls_left:
                self.server.unload_polls_left -= 1
                if not self.server.unload_polls_left:
                    self.server.model_status = "unloaded"
            elif self.server.fail_loading and self.server.model_status == "loading":
                self.server.model_status = "unloaded"
            elif self.server.model_status == "loading" and not self.server.stuck_loading:
                self.server.model_polls += 1
                if self.server.model_polls >= 2:
                    self.server.model_status = "loaded"
            status = {"value": self.server.model_status}
            if self.server.fail_loading:
                status["failed"] = True
            self._reply({"data": [{"id": "local/coder", "status": status}]})
        else:
            self._reply({"error": "unsupported"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        self.server.calls.append(("POST", self.path, payload))
        if self.path == "/api/v1/models/load":
            self._reply({"status": "loaded", "instance_id": "local/coder@1"})
        elif self.path == "/api/v1/models/unload":
            self._reply({"instance_id": payload["instance_id"]})
        elif self.path == "/models/load":
            if self.server.model_status == "loaded":
                self._reply({"error": {"code": 400, "message": "model is already loaded"}}, 400)
                return
            self.server.model_status = "loading"
            self.server.model_polls = 0
            self._reply({"success": True})
        elif self.path == "/models/unload":
            if not self.server.delayed_unload_polls:
                self.server.model_status = "unloaded"
            else:
                self.server.unload_polls_left = self.server.delayed_unload_polls
            self._reply({"success": True})
        elif self.path == "/v1/chat/completions":
            message = {"content": "OK"}
            if payload.get("reasoning_effort") == "medium":
                message["reasoning_content"] = "private work"
            self._reply({"choices": [{"message": message}]})
        else:
            self._reply({"error": "unsupported"}, 404)


class ProviderHttpTests(unittest.TestCase):
    def setUp(self):
        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        except OSError:
            self.skipTest("loopback non disponibile")
        self.server.calls = []
        self.server.redirect = False
        self.server.model_status = "unloaded"
        self.server.model_polls = 0
        self.server.stuck_loading = False
        self.server.fail_loading = False
        self.server.delayed_unload_polls = 0
        self.server.unload_polls_left = 0
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop_server)
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def _stop_server(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def test_lmstudio_http_roundtrip(self):
        base = load_config(ROOT / "benchmark.json")
        config = replace(
            base,
            provider_kind="lmstudio", ollama_url=self.url,
            defaults=replace(base.defaults, context_window=8192),
        )
        provider = create_provider(config)
        model = provider.list_models()[0]
        self.assertTrue(model.thinking_capable)
        self.assertTrue(provider.preflight_thinking(model, resolve_thinking_policy("off"), timeout=5).passed)
        self.assertTrue(provider.preflight_thinking(model, resolve_thinking_policy("medium"), timeout=5).passed)
        provider.load(model.name, timeout=5)
        provider.warmup(model.name, resolve_thinking_policy("off"), timeout=5, context_window=8192)
        provider.unload(model.name)
        calls = self.server.calls
        self.assertIn(("POST", "/api/v1/models/load", {"model": "local/coder", "context_length": 8192}), calls)
        self.assertIn(("POST", "/api/v1/models/unload", {"instance_id": "local/coder@1"}), calls)
        self.assertEqual(["none", "medium", "none"],
                         [payload["reasoning_effort"] for method, path, payload in calls
                          if method == "POST" and path == "/v1/chat/completions"])

    def test_llama_router_http_roundtrip(self):
        config = replace(
            load_config(ROOT / "benchmark.json"),
            provider_kind="llama_cpp", ollama_url=self.url,
        )
        provider = create_provider(config)
        model = provider.list_models()[0]
        self.assertIsNone(model.thinking_capable)
        self.assertTrue(provider.preflight_thinking(model, resolve_thinking_policy("off"), timeout=5).passed)
        provider.unload(model.name)
        self.assertIn(("POST", "/models/load", {"model": "local/coder"}), self.server.calls)
        self.assertIn(("POST", "/models/unload", {"model": "local/coder"}), self.server.calls)
        load_index = next(i for i, call in enumerate(self.server.calls) if call[:2] == ("POST", "/models/load"))
        chat_index = next(i for i, call in enumerate(self.server.calls) if call[:2] == ("POST", "/v1/chat/completions"))
        self.assertGreaterEqual(sum(call[:2] == ("GET", "/models") for call in self.server.calls[load_index + 1:chat_index]), 2)

    def test_llama_router_load_times_out_when_instance_stays_loading(self):
        self.server.stuck_loading = True
        provider = LocalProvider("llama_cpp", self.url)
        with self.assertRaisesRegex(ProviderError, "scaduto"):
            provider.load("local/coder", timeout=0.5)
        provider.unload("local/coder")

    def test_llama_router_load_reports_failed_child(self):
        self.server.fail_loading = True
        provider = LocalProvider("llama_cpp", self.url)
        with self.assertRaisesRegex(ProviderError, "terminato"):
            provider.load("local/coder", timeout=5)

    def test_llama_router_waits_for_unload_before_reloading(self):
        self.server.delayed_unload_polls = 3
        provider = LocalProvider("llama_cpp", self.url)
        provider.load("local/coder", timeout=5)
        provider.unload("local/coder", timeout=5)
        self.assertEqual("unloaded", self.server.model_status)
        self.assertEqual(0, self.server.unload_polls_left)
        provider.load("local/coder", timeout=5)
        unload_index = next(i for i, call in enumerate(self.server.calls) if call[:2] == ("POST", "/models/unload"))
        next_load_index = next(i for i, call in enumerate(self.server.calls[unload_index + 1:], unload_index + 1)
                               if call[:2] == ("POST", "/models/load"))
        self.assertEqual(3, sum(call[:2] == ("GET", "/models") for call in self.server.calls[unload_index + 1:next_load_index]))

    def test_llama_router_unload_times_out_if_model_stays_loaded(self):
        self.server.delayed_unload_polls = 1000
        provider = LocalProvider("llama_cpp", self.url)
        provider.load("local/coder", timeout=5)
        with self.assertRaisesRegex(ProviderError, "scaricamento.*scaduto"):
            provider.unload("local/coder", timeout=0.5)

    def test_redirect_is_rejected_before_external_request(self):
        self.server.redirect = True
        with self.assertRaisesRegex(ProviderError, "Redirect"):
            LocalProvider("llama_cpp", self.url).list_models()
        self.assertEqual([("GET", "/models", None)], self.server.calls)


if __name__ == "__main__":
    unittest.main()
