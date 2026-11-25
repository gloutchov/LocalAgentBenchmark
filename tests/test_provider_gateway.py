from __future__ import annotations

import gc
import http.client
import io
import json
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
import warnings
from contextlib import redirect_stderr
from dataclasses import replace
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localagent_bench.provider_gateway import GatewayError, ProviderGateway, _Handler, _SecretFilter
from localagent_bench.config import load_config
from localagent_bench.provider_session import provider_session
from localagent_bench.ollama import OllamaModel
from localagent_bench.pi_adapter import run_pi, write_models_config
from localagent_bench.sandbox import select_sandbox
from localagent_bench.thinking import resolve_thinking_policy


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
        self.send_header("X-Untrusted-Echo", _key())
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
            if self.server.mode in {"upstream_error", "models_forbidden"}:
                self._json({"error": _key()}, 403 if self.server.mode == "models_forbidden" else 401)
                return
            self._json({"data": [{"id": "local-coder", "owned_by": "unsloth-studio",
                                  "loaded": self.server.loaded, "quant": self.server.quant,
                                  "task": None, "context_length": self.server.context_length, "note": _key()}]})
        elif self.path == "/api/auth/api-keys":
            if self.server.scope == "inference":
                self._json({"detail": "This API key is inference only: " + _key()}, 403)
            elif self.server.scope == "full":
                self._json({"keys": [{"value": _key()}]})
            elif self.server.scope == "unauthorized":
                self._json({"detail": _key()}, 401)
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
        elif self.server.mode == "tool_roundtrip":
            self.server.roundtrip_posts += 1
            if self.server.roundtrip_posts == 1:
                delta = {"role": "assistant", "tool_calls": [{"index": 0, "id": "synthetic_read",
                         "type": "function", "function": {"name": "read",
                         "arguments": json.dumps({"path": "synthetic.txt"})}}]}
                if payload.get("reasoning_effort") != "none":
                    delta["reasoning_content"] = "synthetic-replay-marker"
                finish = "tool_calls"
            else:
                delta, finish = {"role": "assistant", "content": "OK"}, "stop"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            events = [{"id": "synthetic-chat", "object": "chat.completion.chunk", "model": "local-coder",
                       "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                      {"id": "synthetic-chat", "object": "chat.completion.chunk", "model": "local-coder",
                       "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]}]
            try:
                for event in events:
                    self.wfile.write(b"data: " + json.dumps(event).encode() + b"\n\n")
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
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
        self.server.context_length = 32768
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
            for scope, expected in (("full", 403), ("invalid", 503), ("unauthorized", 503)):
                self.server.scope = scope
                status, raw = self._call(gateway, "/benchmark/unsloth-policy")
                self.assertEqual(expected, status)
                self.assertNotIn(_key().encode(), raw)
            count = len(self.server.calls)
            self.assertEqual(404, self._call(gateway, "/api/auth/api-keys")[0])
            self.assertEqual(count, len(self.server.calls))

    def test_policy_authentication_diagnostics_are_allowlisted_without_remote_headers(self):
        with ProviderGateway(self.url, _key()) as gateway:
            for mode, status, code in (
                ("upstream_error", 401, "provider_gateway_credential_rejected"),
                ("models_forbidden", 403, "provider_gateway_credential_rejected"),
                ("normal", 403, "provider_gateway_inference_scope_required"),
            ):
                self.server.mode = mode
                self.server.scope = "full"
                connection = http.client.HTTPConnection("127.0.0.1", int(gateway.url.rsplit(":", 1)[1]), timeout=3)
                try:
                    connection.request("GET", "/benchmark/unsloth-policy")
                    response = connection.getresponse()
                    self.assertEqual(status, response.status)
                    self.assertIsNone(response.getheader("X-Untrusted-Echo"))
                    raw = response.read()
                    self.assertEqual({"error": {"code": code}}, json.loads(raw))
                    self.assertNotIn(_key().encode(), raw)
                finally:
                    connection.close()

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
            status, raw = self._call(gateway, "/v1/chat/completions", payload)
            self.assertEqual(403, status)
            self.assertEqual({"error": {"code": "provider_gateway_inference_scope_required"}}, json.loads(raw))
            self.assertEqual(count, sum(call[0] == "POST" for call in self.server.calls))

    def test_sdk_store_false_is_allowed_without_enabling_persistence(self):
        with ProviderGateway(self.url, _key()) as gateway:
            status, _raw = self._call(gateway, "/v1/chat/completions", self._payload(store=False))
            self.assertEqual(200, status)
            self.assertIs(self.server.calls[-1][3]["store"], False)
            count = sum(call[0] == "POST" for call in self.server.calls)
            for value in (True, None, 0, "false", {}):
                with self.subTest(value_type=type(value).__name__):
                    status, _raw = self._call(gateway, "/v1/chat/completions", self._payload(store=value))
                    self.assertEqual(503, status)
            self.assertEqual(count, sum(call[0] == "POST" for call in self.server.calls))

    @unittest.skipUnless(shutil.which("pi"), "requires installed Pi for the real gateway contract")
    def test_real_pi_sdk_payload_passes_gateway_to_synthetic_stream(self):
        self.server.mode = "sse"
        with tempfile.TemporaryDirectory(prefix="lab-pi-gateway-") as name:
            root = Path(name)
            workspace = root / "workspace"
            workspace.mkdir()
            agent_dir = root / "agent"
            policy = resolve_thinking_policy("off")
            model = OllamaModel("local-coder", None, None, None, {}, ("completion",), False, None)
            with ProviderGateway(self.url, _key()) as gateway:
                write_models_config(agent_dir, gateway.url, [model], 32768, 256, 0, policy,
                                    http_idle_timeout_ms=0, agent_max_retries=0,
                                    provider_max_retries=0, provider_kind="unsloth")
                result = run_pi((shutil.which("pi"),), "local-coder", "off", "Reply with exactly OK.",
                                workspace, agent_dir, 30, select_sandbox("audit"), gateway.url,
                                provider_kind="unsloth")
            self.assertEqual("ok", result.status)
            self.assertNotIn(_key(), result.stdout)
            posted = [call[3] for call in self.server.calls if call[0] == "POST"]
            self.assertEqual(1, len(posted))
            self.assertEqual("none", posted[0]["reasoning_effort"])
            self.assertIs(posted[0]["store"], False)
            self.assertIs(posted[0]["enable_tools"], False)

    @unittest.skipUnless(shutil.which("pi"), "requires installed Pi for the real gateway contract")
    def test_real_pi_tool_roundtrip_is_symmetric_for_off_and_medium(self):
        self.server.mode = "tool_roundtrip"
        original = _Handler._generation_body
        rejected_shapes = []

        def observe_rejection(handler, payload):
            try:
                return original(handler, payload)
            except GatewayError:
                if isinstance(payload, dict):
                    rejected_shapes.append({"top_level_names": sorted(payload),
                        "message_shapes": [{"field_names": sorted(message),
                            "field_types": {key: type(value).__name__ for key, value in message.items()}}
                            for message in payload.get("messages", []) if isinstance(message, dict)]})
                raise

        for mode in ("off", "medium"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(prefix="lab-pi-replay-") as name:
                self.server.roundtrip_posts = 0
                self.server.calls.clear()
                rejected_shapes.clear()
                root = Path(name)
                workspace = root / "workspace"
                workspace.mkdir()
                (workspace / "synthetic.txt").write_text("synthetic workspace content\n", encoding="utf-8")
                agent_dir = root / "agent"
                policy = resolve_thinking_policy(mode)
                model = OllamaModel("local-coder", None, None, None, {},
                                    ("completion", "thinking"), True, True)
                with patch.object(_Handler, "_generation_body", observe_rejection), ProviderGateway(self.url, _key()) as gateway:
                    write_models_config(agent_dir, gateway.url, [model], 32768, 256, 0, policy,
                                        http_idle_timeout_ms=0, agent_max_retries=0,
                                        provider_max_retries=0, provider_kind="unsloth")
                    result = run_pi((shutil.which("pi"),), "local-coder", mode,
                                    "Read synthetic.txt and then reply OK.", workspace, agent_dir,
                                    30, select_sandbox("audit"), gateway.url, tools="read", provider_kind="unsloth")
                # Failure diagnostics contain field names/types only, never prompts,
                # replay values, provider bodies, or credential/header values.
                self.assertEqual("ok", result.status, json.dumps(rejected_shapes, sort_keys=True))
                posted = [call[3] for call in self.server.calls if call[0] == "POST"]
                self.assertEqual(2, len(posted))
                for request in posted:
                    self.assertEqual(policy.reasoning_effort, request["reasoning_effort"])
                    self.assertIs(request["store"], False)
                    self.assertIs(request["enable_tools"], False)
                replay = next(message for message in posted[1]["messages"] if message["role"] == "assistant")
                self.assertEqual(mode == "medium", "reasoning_content" in replay)
                self.assertEqual(1, sum(message["role"] == "tool" for message in posted[1]["messages"]))
                self.assertEqual("synthetic workspace content\n", (workspace / "synthetic.txt").read_text())

    def test_assistant_reasoning_replay_accepts_only_bounded_standard_fields(self):
        valid = [{"reasoning_content": "synthetic replay"}, {"reasoning": "synthetic replay"},
                 {"reasoning_text": "synthetic replay"}, {"reasoning_details": [
                     {"type": "reasoning.text", "text": "synthetic replay", "signature": "synthetic-signature", "index": 0},
                     {"type": "reasoning.summary", "summary": "synthetic summary", "id": None, "format": "synthetic"},
                     {"type": "reasoning.encrypted", "data": "synthetic-opaque-data"}]}]
        with ProviderGateway(self.url, _key()) as gateway:
            for replay in valid:
                payload = self._payload(messages=[{"role": "assistant", "content": None, **replay},
                                                   {"role": "user", "content": "Continue synthetic test."}])
                self.assertEqual(200, self._call(gateway, "/v1/chat/completions", payload)[0])
                for field in replay:
                    self.assertEqual(replay[field], self.server.calls[-1][3]["messages"][0][field])
            count = sum(call[0] == "POST" for call in self.server.calls)
            invalid = [
                {"reasoning_content": None}, {"reasoning": {}}, {"reasoning_text": []},
                {"reasoning_details": {}}, {"reasoning_details": ["synthetic"]},
                {"reasoning_details": [{"type": "remote.execution", "text": "synthetic"}]},
                {"reasoning_details": [{"type": "reasoning.text", "text": "synthetic", "provider_base_url": "https://example.invalid"}]},
                {"reasoning_details": [{"type": "reasoning.text", "text": "synthetic", "index": True}]},
                {"reasoning_details": [{"type": "reasoning.text", "text": "synthetic", "index": -1}]},
                {"reasoning_details": [{"type": "reasoning.text", "text": "synthetic", "signature": {}}]},
                {"reasoning_details": [{"type": "reasoning.summary", "summary": "synthetic", "format": "x" * 129}]},
                {"reasoning_details": [{"type": "reasoning.encrypted", "data": []}]},
                {"reasoning_details": [{"type": "reasoning.text", "text": "synthetic"}] * 129},
            ]
            for replay in invalid:
                payload = self._payload(messages=[{"role": "assistant", "content": None, **replay}])
                self.assertEqual(503, self._call(gateway, "/v1/chat/completions", payload)[0])
            for role in ("user", "system", "developer", "tool"):
                payload = self._payload(messages=[{"role": role, "content": "synthetic", "reasoning_content": "synthetic"}])
                self.assertEqual(503, self._call(gateway, "/v1/chat/completions", payload)[0])
            self.assertEqual(count, sum(call[0] == "POST" for call in self.server.calls))
        with ProviderGateway(self.url, _key(), max_request_bytes=1024) as gateway:
            payload = self._payload(messages=[{"role": "assistant", "content": None, "reasoning_content": "x" * 1025}])
            self.assertEqual(413, self._call(gateway, "/v1/chat/completions", payload)[0])

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

    def test_context_window_is_rechecked_before_each_generation_without_extra_requests(self):
        self.server.context_length = 65536
        with ProviderGateway(self.url, _key(), expected_context_window=32768) as gateway:
            self.assertEqual(200, self._call(gateway, "/v1/chat/completions", self._payload())[0])
            calls_before = len(self.server.calls)
            self.server.context_length = 8192
            status, raw = self._call(gateway, "/v1/chat/completions", self._payload())
            self.assertEqual(409, status)
            self.assertEqual({"error": {"code": "provider_gateway_context_window_mismatch"}}, json.loads(raw))
            self.assertEqual(1, sum(call[0] == "POST" for call in self.server.calls))
            self.assertEqual([("GET", "/v1/models"), ("GET", "/api/auth/api-keys")],
                             [(call[0], call[1]) for call in self.server.calls[calls_before:]])

    def test_session_enforces_the_configured_context_window_in_its_gateway(self):
        base = load_config(ROOT / "benchmark.json")
        config = replace(base, provider_kind="unsloth", ollama_url=self.url,
                         provider_auth_ref="synthetic-reference",
                         defaults=replace(base.defaults, context_window=32768))
        self.server.context_length = 8192
        with patch("localagent_bench.provider_session.resolve_credential", return_value=_key()):
            with provider_session(config) as active:
                status, raw = self._call(SimpleNamespace(url=active.ollama_url),
                                         "/v1/chat/completions", self._payload())
        self.assertEqual(409, status)
        self.assertEqual({"error": {"code": "provider_gateway_context_window_mismatch"}}, json.loads(raw))
        self.assertFalse(any(call[0] == "POST" for call in self.server.calls))

    def test_unknown_context_is_not_invented_or_misclassified_as_too_small(self):
        with ProviderGateway(self.url, _key(), expected_context_window=32768) as gateway:
            for value in (None, 0, -1, True, "8192", 8192.5, {}):
                with self.subTest(value_type=type(value).__name__):
                    self.server.context_length = value
                    self.assertEqual(200, self._call(gateway, "/v1/chat/completions", self._payload())[0])
        self.server.context_length = 8192
        with ProviderGateway(self.url, _key()) as gateway:
            # Existing callers without an expected window retain their contract.
            self.assertEqual(200, self._call(gateway, "/v1/chat/completions", self._payload())[0])
        for value in (True, 0, -1, "32768", 32768.0):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(GatewayError):
                ProviderGateway(self.url, _key(), expected_context_window=value)

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
                    self.assertEqual(403, self._call(gateway, "/benchmark/unsloth-policy")[0])
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
