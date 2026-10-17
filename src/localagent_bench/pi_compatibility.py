"""Probe the configured Pi binary against a synthetic OpenAI-compatible server."""

from __future__ import annotations

import json
import tempfile
import threading
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .ollama import OllamaModel
from .pi_adapter import run_pi, write_models_config
from .sandbox import SandboxError, SandboxSelection, select_sandbox
from .thinking import resolve_thinking_policy


CONTRACT_VERSION = 1
REFERENCE_PI_VERSION = "0.85.1"
PROBE_MODEL = "pi-contract-probe"
PROBE_MAX_TOKENS = 321
MAX_REQUEST_BYTES = 65536


@dataclass(frozen=True)
class PiCompatibility:
    status: str
    contract_version: int
    checks: tuple[str, ...]
    failed_check: str | None = None

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def to_manifest(self) -> dict[str, Any]:
        return asdict(self)


class _CaptureServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int]):
        super().__init__(address, _Handler)
        self.requests: list[dict[str, Any]] = []
        self.response_status = 200
        self.invalid_request = False


class _Handler(BaseHTTPRequestHandler):
    server: _CaptureServer

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self.server.invalid_request = True
        self.send_error(405)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        raw_length = self.headers.get("Content-Length", "")
        try:
            length = int(raw_length)
        except ValueError:
            length = -1
        if self.path != "/v1/chat/completions" or not 0 < length <= MAX_REQUEST_BYTES:
            self.server.invalid_request = True
            self.send_error(400)
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        if not isinstance(payload, dict):
            self.server.invalid_request = True
            self.send_error(400)
            return
        self.server.requests.append(payload)
        if self.server.response_status != 200:
            body = json.dumps({"error": {"message": "synthetic failure", "type": "server_error"}}).encode()
            self.send_response(self.server.response_status)
            self.send_header("Content-Type", "application/json")
        else:
            chunks = [
                {"id": "chatcmpl-probe", "object": "chat.completion.chunk", "created": 1,
                 "model": PROBE_MODEL, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]},
                {"id": "chatcmpl-probe", "object": "chat.completion.chunk", "created": 1,
                 "model": PROBE_MODEL, "choices": [{"index": 0, "delta": {"content": "done"}, "finish_reason": None}]},
                {"id": "chatcmpl-probe", "object": "chat.completion.chunk", "created": 1,
                 "model": PROBE_MODEL, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
            ]
            body = ("".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


def _event_contract(stdout: str) -> bool:
    try:
        events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    except json.JSONDecodeError:
        return False
    return bool(events) and all(isinstance(item, dict) and isinstance(item.get("type"), str) for item in events)


def check_pi_compatibility(
    pi_command: tuple[str, ...], timeout_seconds: int, sandbox: SandboxSelection | None = None,
    cancel_event: threading.Event | None = None,
) -> PiCompatibility:
    """Fail closed; only fixed diagnostics leave this function, never Pi output."""
    checks: list[str] = []
    if timeout_seconds < 10:
        return PiCompatibility("failed", CONTRACT_VERSION, (), "probe_timeout_configuration")
    try:
        server = _CaptureServer(("127.0.0.1", 0))
    except OSError:
        return PiCompatibility("failed", CONTRACT_VERSION, (), "loopback_unavailable")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="pi-contract-") as temporary:
            root = Path(temporary)
            url = f"http://127.0.0.1:{server.server_port}"
            model = OllamaModel(PROBE_MODEL, 1, "synthetic", "now", {}, ("completion", "thinking"), True, True)
            for thinking, expected, response_status in (("off", "none", 200), ("medium", "medium", 200), ("off", "none", 500)):
                if cancel_event is not None and cancel_event.is_set():
                    return PiCompatibility("failed", CONTRACT_VERSION, tuple(checks), "cancelled")
                server.requests.clear()
                server.invalid_request = False
                server.response_status = response_status
                workspace = root / f"workspace-{thinking}-{response_status}"
                workspace.mkdir()
                agent_dir = root / f"agent-{thinking}-{response_status}"
                write_models_config(
                    agent_dir, url, [model], 8192, PROBE_MAX_TOKENS, 0,
                    resolve_thinking_policy(thinking), http_idle_timeout_ms=0,
                    agent_max_retries=0, provider_max_retries=0,
                )
                try:
                    result = run_pi(
                        pi_command, PROBE_MODEL, thinking, "Reply with exactly: done",
                        workspace, agent_dir, timeout_seconds, sandbox or select_sandbox("audit"), url,
                        tools="", cancel_event=cancel_event,
                    )
                except (OSError, ValueError, SandboxError):
                    return PiCompatibility("failed", CONTRACT_VERSION, tuple(checks), "pi_launch")
                label = f"{thinking}_{response_status}"
                if result.status == "cancelled":
                    return PiCompatibility("failed", CONTRACT_VERSION, tuple(checks), "cancelled")
                if result.status == "timeout":
                    return PiCompatibility("failed", CONTRACT_VERSION, tuple(checks), f"{label}_timeout")
                if server.invalid_request or len(server.requests) != 1:
                    return PiCompatibility("failed", CONTRACT_VERSION, tuple(checks), f"{label}_request_count")
                payload = server.requests[0]
                if payload.get("reasoning_effort") != expected:
                    return PiCompatibility("failed", CONTRACT_VERSION, tuple(checks), f"{label}_reasoning_effort")
                if payload.get("max_tokens") != PROBE_MAX_TOKENS or "max_completion_tokens" in payload:
                    return PiCompatibility("failed", CONTRACT_VERSION, tuple(checks), f"{label}_max_tokens")
                if not _event_contract(result.stdout) or result.metrics.get("json_parse_errors"):
                    return PiCompatibility("failed", CONTRACT_VERSION, tuple(checks), f"{label}_events")
                if result.metrics.get("retry_events") != 0:
                    return PiCompatibility("failed", CONTRACT_VERSION, tuple(checks), f"{label}_retry")
                if response_status == 200:
                    if result.status != "ok" or result.final_response.strip() != "done" or result.metrics.get("assistant_turns", 0) < 1:
                        return PiCompatibility("failed", CONTRACT_VERSION, tuple(checks), f"{label}_response")
                elif result.status != "pi_error":
                    return PiCompatibility("failed", CONTRACT_VERSION, tuple(checks), f"{label}_terminal_error")
                checks.append(label)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    return PiCompatibility("passed", CONTRACT_VERSION, tuple(checks))
