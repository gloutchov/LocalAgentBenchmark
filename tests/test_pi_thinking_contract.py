from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localagent_bench.ollama import OllamaModel
from localagent_bench.pi_adapter import run_pi, write_models_config
from localagent_bench.pi_compatibility import check_pi_compatibility
from localagent_bench.sandbox import select_sandbox
from localagent_bench.thinking import resolve_thinking_policy


def _pi_version() -> str | None:
    executable = shutil.which("pi")
    if not executable:
        return None
    try:
        completed = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


class _CaptureServer(ThreadingHTTPServer):
    requests: list[dict[str, Any]]
    response_status: int


class _OpenAIHandler(BaseHTTPRequestHandler):
    server: _CaptureServer

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
        self.server.requests.append(payload)
        if self.server.response_status != 200:
            body = json.dumps(
                {"error": {"message": "synthetic terminal failure", "type": "server_error"}}
            ).encode("utf-8")
            self.send_response(self.server.response_status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        chunks = [
            {
                "id": "chatcmpl-test",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": payload.get("model", "contract-model"),
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            },
            {
                "id": "chatcmpl-test",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": payload.get("model", "contract-model"),
                "choices": [{"index": 0, "delta": {"content": "done"}, "finish_reason": None}],
            },
            {
                "id": "chatcmpl-test",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": payload.get("model", "contract-model"),
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        ]
        body = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


@unittest.skipUnless(
    _pi_version() is not None,
    "richiede Pi installato",
)
class PiThinkingContractTests(unittest.TestCase):
    def test_runtime_compatibility(self):
        result = check_pi_compatibility((shutil.which("pi") or "pi",), 30)
        self.assertTrue(result.passed, result)

    def setUp(self):
        try:
            self.server = _CaptureServer(("127.0.0.1", 0), _OpenAIHandler)
        except OSError as exc:
            self.skipTest(f"bind loopback non disponibile: {exc}")
        self.server.requests = []
        self.server.response_status = 200
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.ollama_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        if hasattr(self, "server"):
            self.server.shutdown()
            self.server.server_close()
        if hasattr(self, "thread"):
            self.thread.join(timeout=5)

    def _run(self, thinking: str, *, response_status: int = 200):
        self.server.requests.clear()
        self.server.response_status = response_status
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        workspace = root / "workspace"
        workspace.mkdir()
        agent_dir = root / "agent"
        model = OllamaModel(
            "contract-model",
            1,
            "digest",
            "now",
            {},
            ("completion", "thinking"),
            True,
            True,
        )
        write_models_config(
            agent_dir,
            self.ollama_url,
            [model],
            8192,
            321,
            0,
            resolve_thinking_policy(thinking),
            http_idle_timeout_ms=0,
            agent_max_retries=0,
            provider_max_retries=0,
        )
        result = run_pi(
            (shutil.which("pi") or "pi",),
            model.name,
            thinking,
            "Reply with exactly: done",
            workspace,
            agent_dir,
            20,
            select_sandbox("audit"),
            self.ollama_url,
        )
        return result, list(self.server.requests)

    def test_real_pi_forwards_explicit_off_and_active_effort_with_max_tokens(self):
        off_result, off_requests = self._run("off")
        self.assertEqual("ok", off_result.status, off_result.stderr)
        self.assertEqual(1, len(off_requests))
        self.assertEqual("none", off_requests[0].get("reasoning_effort"))
        self.assertEqual(321, off_requests[0].get("max_tokens"))
        self.assertNotIn("max_completion_tokens", off_requests[0])

        medium_result, medium_requests = self._run("medium")
        self.assertEqual("ok", medium_result.status, medium_result.stderr)
        self.assertEqual(1, len(medium_requests))
        self.assertEqual("medium", medium_requests[0].get("reasoning_effort"))
        self.assertEqual(321, medium_requests[0].get("max_tokens"))

    def test_real_pi_does_not_retry_terminal_provider_failure(self):
        result, requests = self._run("off", response_status=500)
        self.assertEqual("pi_error", result.status)
        self.assertEqual(1, len(requests))
        self.assertEqual(0, result.metrics["retry_events"])


if __name__ == "__main__":
    unittest.main()
