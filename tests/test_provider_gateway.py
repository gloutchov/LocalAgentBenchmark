from __future__ import annotations

import gc
import http.client
import io
import json
import socket
import sys
import threading
import time
import unittest
import warnings
from contextlib import redirect_stderr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localagent_bench.provider_gateway import GatewayError, ProviderGateway, _SecretFilter


def _key():
    return "synthetic-" + "credential" + "-not-a-real-provider-key"


class _Upstream(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def _json(self, payload, status=200):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        self.wfile.write(raw)

    def do_GET(self):
        self.server.calls.append(("GET", self.path, dict(self.headers), None))
        if self.path == "/v1/models":
            if self.server.mode == "redirect":
                self.send_response(302)
                self.send_header("Location", "https://example.invalid/" + _key())
                self.send_header("Content-Length", "0")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                return
            if self.server.mode == "upstream_error":
                self._json({"error": _key()}, 401)
                return
            self._json({"data": [{"id": "local-coder", "owned_by": "unsloth-studio",
                                  "loaded": self.server.loaded, "quant": self.server.quant,
                                  "task": None, "note": _key()}]})
        elif self.path == "/api/auth/api-keys":
            if self.server.scope == "inference":
                self._json({"detail": "This API key is inference only: " + _key()}, 403)
            elif self.server.scope == "full":
                self._json({"keys": [{"value": _key()}]})
            else:
                self._json({"detail": "Invalid key: " + _key()}, 403)
        else:
            self._json({"error": _key()}, 404)

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.calls.append(("POST", self.path, dict(self.headers), payload))
        if self.server.mode == "upstream_error":
            self._json({"error": _key()}, 403)
        elif self.server.mode == "sse":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            fragments = [b'data: {"choices":[{"delta":{"content":"', _key()[:13].encode(),
                         _key()[13:].encode(), b'"},"finish_reason":"stop"}]}\n\n', b'data: [DONE]\n\n']
            try:
                for fragment in fragments:
                    self.wfile.write(fragment)
                    self.wfile.flush()
                    time.sleep(.01)
            except OSError:
                pass
        elif self.server.mode == "slow":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            try:
                while not self.server.stop_event.wait(.02):
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            except OSError:
                pass
        elif self.server.mode == "oversize":
            self._json({"choices": [{"message": {"content": "x" * 4096}}]})
        else:
            self._json({"choices": [{"message": {"content": "OK " + _key()}}]})


class ProviderGatewayTests(unittest.TestCase):
    def setUp(self):
        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Upstream)
        except OSError:
            self.skipTest("loopback non disponibile")
        self.server.daemon_threads = True
        self.server.calls = []
        self.server.scope = "inference"
        self.server.mode = "normal"
        self.server.loaded = True
        self.server.quant = "Q4_K_M"
        self.server.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop)
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def _stop(self):
        self.server.stop_event.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)

    def _call(self, gateway, path="/v1/models", payload=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", int(gateway.url.rsplit(":", 1)[1]), timeout=3)
        try:
            raw = json.dumps(payload).encode() if payload is not None else None
            connection.request("POST" if payload is not None else "GET", path, body=raw,
                               headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def _payload(self, **extra):
        return {"model": "local-coder", "messages": [{"role": "user", "content": "synthetic prompt"}],
                "reasoning_effort": "none", "max_tokens": 8, **extra}

    def test_only_host_holds_auth_and_success_body_is_redacted(self):
        with ProviderGateway(self.url, _key()) as gateway:
            self.assertTrue(gateway.url.startswith("http://127.0.0.1:"))
            status, raw = self._call(gateway, headers={"Authorization": "Bearer fake", "Cookie": "never-forward"})
            self.assertEqual(200, status)
            self.assertNotIn(_key().encode(), raw)
            headers = self.server.calls[-1][2]
            self.assertEqual("Bearer " + _key(), headers["Authorization"])
            self.assertNotIn("Cookie", headers)
            self.assertNotIn(_key(), repr(gateway))
        self.assertEqual("", gateway._secret)

    def test_inference_only_probe_normalizes_and_discards_management_content(self):
        with ProviderGateway(self.url, _key()) as gateway:
            self.assertEqual((200, b'{"inference_only":true}'), self._call(gateway, "/benchmark/unsloth-policy"))
            for scope in ("full", "invalid"):
                self.server.scope = scope
                status, raw = self._call(gateway, "/benchmark/unsloth-policy")
                self.assertEqual(503, status)
                self.assertNotIn(_key().encode(), raw)
            count = len(self.server.calls)
            self.assertEqual(404, self._call(gateway, "/api/auth/api-keys")[0])
            self.assertEqual(count, len(self.server.calls))

    def test_generation_keeps_thinking_and_tools_client_side(self):
        with ProviderGateway(self.url, _key()) as gateway:
            payload = self._payload(tools=[{"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}],
                                    tool_choice="auto", parallel_tool_calls=False)
            status, raw = self._call(gateway, "/v1/chat/completions", payload)
            self.assertEqual(200, status)
            self.assertNotIn(_key().encode(), raw)
            forwarded = self.server.calls[-1][3]
            self.assertEqual("none", forwarded["reasoning_effort"])
            self.assertEqual(payload["tools"], forwarded["tools"])
            for field in ("enable_tools", "mcp_enabled", "auto_heal_tool_calls", "nudge_tool_calls"):
                self.assertIs(forwarded[field], False)
            self.assertEqual([], forwarded["enabled_tools"])
            self.server.scope = "full"
            count = sum(call[0] == "POST" for call in self.server.calls)
            self.assertEqual(503, self._call(gateway, "/v1/chat/completions", payload)[0])
            self.assertEqual(count, sum(call[0] == "POST" for call in self.server.calls))

    def test_remote_selectors_images_sessions_and_unloaded_models_are_rejected(self):
        with ProviderGateway(self.url, _key()) as gateway:
            for extra in ({"provider_base_url": "https://example.invalid"}, {"session_id": "saved"},
                          {"mcp_enabled": True}, {"enable_tools": True},
                          {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "https://example.invalid"}}]}]}):
                with self.subTest(extra=extra):
                    self.assertEqual(503, self._call(gateway, "/v1/chat/completions", self._payload(**extra))[0])
            self.server.loaded = False
            self.assertEqual(503, self._call(gateway, "/v1/chat/completions", self._payload())[0])
            self.assertFalse(any(call[0] == "POST" for call in self.server.calls))

    def test_only_explicit_gguf_mapping_can_supply_missing_quant(self):
        self.server.quant = None
        with ProviderGateway(self.url, _key()) as gateway:
            self.assertEqual(503, self._call(gateway, "/v1/chat/completions", self._payload())[0])
        with ProviderGateway(self.url, _key(), gguf_model_ids=("local-coder",)) as gateway:
            self.assertEqual(200, self._call(gateway, "/v1/chat/completions", self._payload())[0])

    def test_routes_origin_redirect_and_errors_are_sanitized(self):
        captured = io.StringIO()
        with redirect_stderr(captured), ProviderGateway(self.url, _key()) as gateway:
            for path in ("https://example.invalid/", "/v1/models?target=remote", "/v1/models/", "/models/load", "/props"):
                self.assertEqual(404, self._call(gateway, path)[0])
            self.assertEqual(400, self._call(gateway, headers={"Origin": "https://example.invalid"})[0])
            self.assertEqual([], self.server.calls)
            for mode, expected in (("redirect", 502), ("upstream_error", 401)):
                self.server.mode = mode
                status, raw = self._call(gateway)
                self.assertEqual(expected, status)
                self.assertNotIn(_key().encode(), raw)
        self.assertEqual("", captured.getvalue())

    def test_sse_redacts_even_across_upstream_chunk_boundaries(self):
        self.server.mode = "sse"
        with ProviderGateway(self.url, _key()) as gateway:
            status, raw = self._call(gateway, "/v1/chat/completions", self._payload(stream=True))
            self.assertEqual(200, status)
            self.assertIn(b"[DONE]", raw)
            self.assertNotIn(_key().encode(), raw)
            self.assertIn(b'"content":"*"', raw)
        redactor = _SecretFilter(_key())
        output = b"".join(redactor.feed(bytes([byte])) for byte in (b"prefix" + _key().encode() + b"suffix"))
        output += redactor.feed(b"", final=True)
        self.assertEqual(b"prefix*suffix", output)

    def test_truncated_credential_prefix_is_redacted_without_corrupting_short_prose(self):
        secret = _key()
        redactor = _SecretFilter(secret)
        self.assertEqual(b"prefix ", redactor.feed(b"prefix " + secret[:-1].encode()))
        self.assertEqual(b"*", redactor.feed(b"", final=True))
        redactor = _SecretFilter(secret)
        short = b"ordinary word" + secret[:1].encode()
        output = redactor.feed(short) + redactor.feed(b"", final=True)
        self.assertEqual(short, output)

    def test_policy_rejection_closes_unread_upstream_responses(self):
        self.server.scope = "full"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ResourceWarning)
            with ProviderGateway(self.url, _key()) as gateway:
                for _ in range(5):
                    self.assertEqual(503, self._call(gateway, "/benchmark/unsloth-policy")[0])
            gc.collect()
        self.assertFalse([warning for warning in caught if issubclass(warning.category, ResourceWarning)])

    def test_payload_response_and_header_limits(self):
        with ProviderGateway(self.url, _key(), max_request_bytes=256, max_response_bytes=2048,
                             max_header_bytes=512) as gateway:
            status, _raw = self._call(gateway, "/v1/chat/completions", self._payload(extra="x" * 512))
            self.assertEqual(413, status)
            status, _raw = self._call(gateway, headers={"X-Oversized": "x" * 1024})
            self.assertEqual(431, status)
            self.server.mode = "oversize"
            status, raw = self._call(gateway, "/v1/chat/completions", self._payload())
            self.assertEqual(503, status)
            self.assertNotIn(_key().encode(), raw)

    def test_deadline_and_close_interrupt_slow_stream(self):
        self.server.mode = "slow"
        started = time.monotonic()
        with ProviderGateway(self.url, _key(), timeout_seconds=.2) as gateway:
            status, _raw = self._call(gateway, "/v1/chat/completions", self._payload(stream=True))
            self.assertEqual(200, status)
        self.assertLess(time.monotonic() - started, 1.5)
        gateway = ProviderGateway(self.url, _key(), timeout_seconds=30)
        gateway.__enter__()
        connection = http.client.HTTPConnection("127.0.0.1", int(gateway.url.rsplit(":", 1)[1]), timeout=2)
        payload = json.dumps(self._payload(stream=True)).encode()
        connection.request("POST", "/v1/chat/completions", body=payload)
        response = connection.getresponse()
        self.assertEqual(200, response.status)
        started = time.monotonic()
        gateway.close()
        self.assertLess(time.monotonic() - started, 1)
        response.read()
        connection.close()

    def test_target_and_limits_validation(self):
        for url in ("https://127.0.0.1:8000", "http://remote.invalid:8000", "http://user:pass@127.0.0.1:8000",
                    "http://127.0.0.1:8000/", "http://127.0.0.1:8000?q=x", "http://127.0.0.1:invalid", "http://127.0.0.1"):
            with self.subTest(url=url), self.assertRaises(GatewayError):
                ProviderGateway(url, _key())
        for kwargs in ({"timeout_seconds": float("nan")}, {"max_header_bytes": 0}, {"max_connections": True}):
            with self.assertRaises(GatewayError):
                ProviderGateway(self.url, _key(), **kwargs)


if __name__ == "__main__":
    unittest.main()
