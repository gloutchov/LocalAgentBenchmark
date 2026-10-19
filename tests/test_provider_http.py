from __future__ import annotations

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localagent_bench.providers import LocalProvider, ProviderError
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
            self._reply({"data": [{"id": "local/coder", "status": {"value": "unloaded"}}]})
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
        elif self.path in {"/models/load", "/models/unload"}:
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
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop_server)
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def _stop_server(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def test_lmstudio_http_roundtrip(self):
        provider = LocalProvider("lmstudio", self.url, context_window=8192)
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
        provider = LocalProvider("llama_cpp", self.url)
        model = provider.list_models()[0]
        self.assertIsNone(model.thinking_capable)
        self.assertTrue(provider.preflight_thinking(model, resolve_thinking_policy("off"), timeout=5).passed)
        provider.unload(model.name)
        self.assertIn(("POST", "/models/load", {"model": "local/coder"}), self.server.calls)
        self.assertIn(("POST", "/models/unload", {"model": "local/coder"}), self.server.calls)

    def test_redirect_is_rejected_before_external_request(self):
        self.server.redirect = True
        with self.assertRaisesRegex(ProviderError, "Redirect"):
            LocalProvider("llama_cpp", self.url).list_models()
        self.assertEqual([("GET", "/models", None)], self.server.calls)


if __name__ == "__main__":
    unittest.main()
