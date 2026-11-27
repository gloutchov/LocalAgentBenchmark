from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localagent_bench.colibri_protocol import ColibriSettings
from localagent_bench.config import load_config
from localagent_bench.model_bundle import ModelBundle, ModelBundleError, valid_bundle_manifest
from localagent_bench.preliminary_stream import measure
from localagent_bench.provider_adapter import create_provider
from localagent_bench.provider_session import provider_session
from localagent_bench.providers import ProviderError, _request
from localagent_bench.thinking import resolve_thinking_policy


class BundleTests(unittest.TestCase):
    def test_fingerprint_uses_declared_names_and_rejects_mutations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "weights").write_bytes(b"weights")
            (root / "tokenizer.json").write_bytes(b"{}")
            raw = {"root": str(root), "files": ["weights", "tokenizer.json"]}
            bundle = ModelBundle.parse(raw)
            manifest, identity = bundle.fingerprint()
            raw["files"].reverse()
            reversed_manifest, _ = ModelBundle.parse(raw).fingerprint()
            self.assertEqual(manifest, reversed_manifest)
            self.assertTrue(valid_bundle_manifest(manifest, manifest["fingerprint_sha256"]))
            self.assertNotIn(str(root), json.dumps(manifest))
            manifest["files"][0]["sha256"] = "0" * 64
            self.assertFalse(valid_bundle_manifest(manifest, manifest["fingerprint_sha256"]))
            (root / "weights").write_bytes(b"updated")
            with self.assertRaises(ModelBundleError):
                bundle.verify(identity)

    def test_refuses_unlisted_paths_duplicates_missing_files_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for paths in (["../outside"], ["/outside"], ["C:/outside"], ["a", "A"], ["a//b"]):
                with self.subTest(paths=paths), self.assertRaises(ModelBundleError):
                    ModelBundle.parse({"root": str(root), "files": paths})
            missing = ModelBundle.parse({"root": str(root), "files": ["missing"]})
            with self.assertRaises(ModelBundleError):
                missing.fingerprint()
            (root / "real").write_bytes(b"data")
            try:
                (root / "link").symlink_to(root / "real")
            except (OSError, NotImplementedError):
                return
            with self.assertRaises(ModelBundleError):
                ModelBundle.parse({"root": str(root), "files": ["link"]}).fingerprint()


class _ColibriEndpoint(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def _respond(self, payload, status=200, content_type="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        header = self.headers.get("Authorization")
        self.server.headers_seen.append(header)
        if self.server.bearer is not None and header != "Bearer " + self.server.bearer:
            self._respond({"error": "private provider failure"}, 401)
            return False
        return True

    def do_GET(self):
        if self._authorized():
            self.server.paths.append(self.path)
            self._respond({"data": [self.server.model]})

    def do_POST(self):
        if not self._authorized():
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.posts.append(body)
        self.server.paths.append(self.path)
        if body.get("stream"):
            frames = [
                {"choices": [{"delta": {"content": "OK"}, "finish_reason": "stop"}],
                 "usage": {"completion_tokens": 1}},
                {"colibri": {"stats": {"internal_path": "/private/runtime"}}},
            ]
            if body.get("tools"):
                calls = {"index": 0, "id": "probe", "type": "function",
                         "function": {"name": "benchmark_probe", "arguments": '{"value":7}'}}
                frames = [{"choices": [{"delta": {"tool_calls": [calls]}, "finish_reason": "tool_calls"}]}]
                if not self.server.tool_calling:
                    frames = [{"choices": [{"delta": {}, "finish_reason": "stop"}]}]
            raw = "".join("data: " + json.dumps(frame) + "\n\n" for frame in frames)
            self._respond((raw + "data: [DONE]\n\n").encode(), content_type="text/event-stream")
        else:
            message = {"content": "OK"}
            if self.server.reasoning:
                message["reasoning_content"] = "synthetic"
            if body.get("tools") and self.server.tool_calling:
                message["tool_calls"] = [{"type": "function", "id": "probe",
                                          "function": {"name": "benchmark_probe", "arguments": '{"value":7}'}}]
            end = "tool_calls" if message.get("tool_calls") else "stop"
            self._respond({"choices": [{"message": message, "finish_reason": end}]})


class ColibriTests(unittest.TestCase):
    def setUp(self):
        try:
            upstream = ThreadingHTTPServer(("127.0.0.1", 0), _ColibriEndpoint)
        except OSError:
            self.skipTest("loopback non disponibile")
        upstream.bearer = None
        upstream.headers_seen = []
        upstream.paths = []
        upstream.posts = []
        upstream.model = {"object": "model", "id": "resident", "capabilities": ["chat"],
                          "context_length": 32768, "max_model_len": 32768}
        upstream.reasoning = False
        upstream.tool_calling = True
        self.upstream = upstream
        self.thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop)
        base = load_config(ROOT / "benchmark.json")
        self.config = replace(base, provider_kind="colibri", colibri=ColibriSettings.parse({}),
                              ollama_url=f"http://127.0.0.1:{upstream.server_port}")
        self.off = resolve_thinking_policy("off")

    def _stop(self):
        self.upstream.shutdown()
        self.upstream.server_close()
        self.thread.join()

    def test_resident_off_tool_call_and_preliminary_sse(self):
        with provider_session(self.config) as active:
            provider = create_provider(active)
            model = provider.list_models()[0]
            self.assertEqual("resident", model.name)
            self.assertTrue(provider.preflight_thinking(model, self.off, timeout=5).passed)
            self.assertEqual("not_supported", provider.unload(model.name)["status"])
            row = measure(active.ollama_url, model.name, "synthetic", self.off,
                          self.config.preliminary, temperature=0, seed=4)
            self.assertEqual("OK", row["answer"])
        self.assertEqual(3, len(self.upstream.posts))
        self.assertTrue(all(row["reasoning_effort"] == "none" and row["context_compaction"] == "off"
                            and row["store"] is False for row in self.upstream.posts))
        self.assertTrue(all(header is None for header in self.upstream.headers_seen))
        self.assertEqual({"/v1/models", "/v1/chat/completions"}, set(self.upstream.paths))
        self.assertNotIn("internal_path", json.dumps(row))

    def test_optional_credential_and_auth_errors_stay_host_only(self):
        self.upstream.bearer = "test-provider-secret"
        with provider_session(self.config) as active:
            with self.assertRaisesRegex(ProviderError, "HTTP 401"):
                create_provider(active).list_models()
        config = replace(self.config, provider_auth_ref="synthetic")
        with patch("localagent_bench.provider_session.resolve_credential", return_value=self.upstream.bearer):
            with provider_session(config) as active:
                self.assertEqual("resident", create_provider(active).list_models()[0].name)
                self.assertNotIn(self.upstream.bearer, repr(active))
        self.assertIn("Bearer " + self.upstream.bearer, self.upstream.headers_seen)

    def test_unverified_thinking_tool_calling_context_and_residency_block(self):
        with provider_session(self.config) as active:
            provider = create_provider(active)
            model = provider.list_models()[0]
            active_policy = resolve_thinking_policy("medium")
            self.assertEqual("thinking_level_unverified", provider.preflight_thinking(model, active_policy, timeout=5).status)
            self.assertEqual([], self.upstream.posts)
            self.upstream.reasoning = True
            self.assertEqual("unexpected_thinking", provider.preflight_thinking(model, self.off, timeout=5).status)
            self.upstream.reasoning = False
            self.upstream.tool_calling = False
            self.assertEqual("tool_calling_not_verified", provider.preflight_thinking(model, self.off, timeout=5).status)
            self.upstream.model["max_model_len"] = 8192
            self.assertEqual("context_window_mismatch", provider.preflight_thinking(model, self.off, timeout=5).status)
            self.upstream.model["id"] = "other"
            with self.assertRaisesRegex(ProviderError, "HTTP 409"):
                _request(active.ollama_url, "/v1/chat/completions",
                         {"model": model.name, "messages": [{"role": "user", "content": "probe"}],
                          "reasoning_effort": "none"}, timeout=2)
