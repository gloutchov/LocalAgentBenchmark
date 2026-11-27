"""Host-only authenticated loopback gateway with fixed routes and bounded I/O."""
from __future__ import annotations

import http.client
import json
import math
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from .colibri_protocol import resident_chat_model, resident_context
from .provider_auth import validate_secret


class GatewayError(RuntimeError):
    """Gateway setup failed; messages never include upstream content or keys."""


class _PolicyRejection(GatewayError):
    """Allowlisted diagnostic only; never constructed from an upstream body."""
    _REASONS = {
        "credential_401": (401, "provider_gateway_credential_rejected"),
        "credential_403": (403, "provider_gateway_credential_rejected"),
        "inference_scope": (403, "provider_gateway_inference_scope_required"),
        "context_window": (409, "provider_gateway_context_window_mismatch"),
        "model_not_resident": (409, "provider_gateway_model_not_resident"),
    }

    def __init__(self, reason: str):
        self.status, self.code = self._REASONS[reason]
        super().__init__(self.code)


def _target(url: str) -> tuple[str, int]:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except (TypeError, ValueError):
        raise GatewayError("provider_gateway_endpoint_invalid") from None
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
            or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment
            or port is None or not 1 <= port <= 65535):
        raise GatewayError("provider_gateway_endpoint_invalid")
    # Do not let a hosts-file alias change the permitted network destination.
    return ("127.0.0.1" if parsed.hostname == "localhost" else parsed.hostname), port


class _SecretFilter:
    """Emit immediately except for a suffix that may start a split credential."""
    def __init__(self, secret: str):
        self.pattern = secret.encode("ascii")
        self.pending = b""
        self.prefix = [0] * len(self.pattern)
        size = 0
        for index in range(1, len(self.pattern)):
            while size and self.pattern[index] != self.pattern[size]:
                size = self.prefix[size - 1]
            if self.pattern[index] == self.pattern[size]:
                size += 1
            self.prefix[index] = size

    def feed(self, block: bytes, *, final: bool = False) -> bytes:
        # '*' is outside the permitted bearer alphabet, so replacement cannot
        # recreate the credential or join two fragments into another occurrence.
        clean = (self.pending + block).replace(self.pattern, b"*")
        self.pending = b""
        matched = 0
        for value in clean[-max(0, len(self.pattern) - 1):]:
            while matched and value != self.pattern[matched]:
                matched = self.prefix[matched - 1]
            if value == self.pattern[matched]:
                matched += 1
            if matched == len(self.pattern):
                matched = self.prefix[matched - 1]
        if final:
            # A truncated response must not release almost all of a key. Keep
            # short ordinary suffixes intact (e.g. prose ending in the key's
            # first letter), but redact meaningful credential prefixes.
            minimum = min(8, max(1, len(self.pattern) - 1))
            return clean[:-matched] + b"*" if matched >= minimum else clean
        if matched:
            self.pending = clean[-matched:]
            return clean[:-matched]
        return clean


class _HeaderReader:
    """Enforce the configured aggregate limit before headers enter the parser."""
    def __init__(self, stream: Any, limit: int):
        self.stream, self.limit = stream, limit
        self.total = 0
        self.finished = False

    def readline(self, size: int = -1) -> bytes:
        if self.finished:
            return self.stream.readline(size)
        remaining = self.limit - self.total + 1
        value = self.stream.readline(min(size, remaining) if size >= 0 else remaining)
        self.total += len(value)
        if self.total > self.limit:
            raise http.client.LineTooLong("provider headers")
        if value in {b"\r\n", b"\n"}:
            self.finished = True
        return value

    def __getattr__(self, name: str) -> Any:
        return getattr(self.stream, name)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = False

    def process_request(self, request: socket.socket, client_address: Any) -> None:
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        with self.active_lock:
            self.active.add(request)
        try:
            super().process_request(request, client_address)
        except BaseException:
            with self.active_lock:
                self.active.discard(request)
            self.slots.release()
            raise

    def process_request_thread(self, request: socket.socket, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            with self.active_lock:
                self.active.discard(request)
            self.slots.release()

    def handle_error(self, _request: Any, _address: Any) -> None:
        # Exceptions can originate in an upstream response. Never print them.
        pass


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        super().setup()
        self.rfile = _HeaderReader(self.rfile, self.server.gateway.max_header_bytes)
        self.connection.settimeout(self.server.gateway.timeout_seconds)
        self.deadline = time.monotonic() + self.server.gateway.timeout_seconds
        self.upstream: http.client.HTTPConnection | None = None
        self.response_started = False
        self.response: http.client.HTTPResponse | None = None
        self.secret = self.server.gateway._secret
        with self.server.active_lock:
            self.server.handlers.add(self)
        self.timer = threading.Timer(self.server.gateway.timeout_seconds, self._expire)
        self.timer.daemon = True
        self.timer.start()

    def _expire(self) -> None:
        raw_socket = getattr(getattr(getattr(self.response, "fp", None), "raw", None), "_sock", None)
        for connection in (self.connection, getattr(self.upstream, "sock", None), raw_socket):
            if connection is not None:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def finish(self) -> None:
        self.timer.cancel()
        with self.server.active_lock:
            self.server.handlers.discard(self)
        self.secret = ""
        if self.response is not None:
            self.response.close()
        if self.upstream is not None:
            self.upstream.close()
        try:
            super().finish()
        except OSError:
            pass

    def log_message(self, *_args: Any) -> None:
        pass

    def send_error(self, code: int, *_args: Any, **_kwargs: Any) -> None:
        self._reply(code, {"error": {"code": "provider_gateway_request_rejected"}})

    def _reply(self, status: int, payload: dict[str, Any]) -> None:
        if self.response_started:
            self.close_connection = True
            return
        raw = json.dumps(payload, separators=(",", ":")).encode()
        self.response_started = True
        self.send_response_only(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.close_connection = True
        self.wfile.write(raw)

    def _remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("provider_gateway_timeout")
        return remaining

    def _open(self, method: str, path: str, body: bytes | None = None) -> http.client.HTTPResponse:
        gateway = self.server.gateway
        if self.response is not None:
            self.response.close()
            self.response = None
        if self.upstream is not None:
            self.upstream.close()
        self.upstream = http.client.HTTPConnection(*gateway.target, timeout=min(10.0, self._remaining()))
        self.upstream.connect()
        self.upstream.sock.settimeout(self._remaining())
        headers = {"Accept-Encoding": "identity", "Connection": "close"}
        if self.secret is not None:
            headers["Authorization"] = "Bearer " + self.secret
        if body is not None:
            headers["Content-Type"] = "application/json"
        # No client header, redirect, proxy, or alternate destination is reused.
        self.upstream.request(method, path, body=body, headers=headers)
        response = self.upstream.getresponse()
        self.response = response
        header_size = sum(len(k) + len(v) + 4 for k, v in response.getheaders())
        if header_size > gateway.max_header_bytes or response.getheader("Content-Encoding", "identity") != "identity":
            raise GatewayError("provider_gateway_upstream_headers")
        if len(response.headers.get_all("Content-Length", [])) > 1:
            raise GatewayError("provider_gateway_upstream_headers")
        length = response.getheader("Content-Length")
        if length is not None and (not length.isdecimal() or int(length) > gateway.max_response_bytes):
            raise GatewayError("provider_gateway_response_limit")
        return response

    def _small_json(self, response: http.client.HTTPResponse) -> dict[str, Any]:
        limit = min(1048576, self.server.gateway.max_response_bytes)
        try:
            raw = response.read(limit + 1)
            if len(raw) > limit:
                raise GatewayError("provider_gateway_response_limit")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise GatewayError("provider_gateway_upstream_protocol")
            return value
        finally:
            response.close()

    def _verify_policy(self) -> list[dict[str, Any]]:
        # The scope check is a read-only call to an existing authenticated route.
        # Full-access key metadata and free-form denials never reach the caller.
        response = self._open("GET", "/v1/models")
        if response.status in {401, 403}:
            raise _PolicyRejection("credential_401" if response.status == 401 else "credential_403")
        if response.status != 200:
            raise GatewayError("provider_gateway_policy_unverified")
        models = self._small_json(response).get("data")
        if not isinstance(models, list):
            raise GatewayError("provider_gateway_policy_unverified")
        self.upstream.close()
        response = self._open("GET", "/api/auth/api-keys")
        if response.status == 200:
            raise _PolicyRejection("inference_scope")
        if response.status != 403:
            raise GatewayError("provider_gateway_policy_unverified")
        detail = self._small_json(response).get("detail")
        if not isinstance(detail, str) or not detail.startswith("This API key is inference only:"):
            raise GatewayError("provider_gateway_policy_unverified")
        self.upstream.close()
        return models

    def _policy(self) -> None:
        self._verify_policy()
        self._reply(200, {"inference_only": True})

    def _reasoning_history(self, message: dict[str, Any]) -> None:
        text_fields = {"reasoning", "reasoning_content", "reasoning_text"}
        fields = text_fields | {"reasoning_details"}
        present = fields & set(message)
        if not present:
            return
        if message.get("role") != "assistant":
            raise GatewayError("provider_gateway_request_protocol")
        # The complete encoded request already has a byte limit. Apply that
        # bound to replay text too, and keep structured replay metadata shallow.
        limit = self.server.gateway.max_request_bytes
        for field in text_fields & present:
            if not isinstance(message[field], str) or len(message[field].encode("utf-8")) > limit:
                raise GatewayError("provider_gateway_request_protocol")
        if "reasoning_details" not in present:
            return
        details = message["reasoning_details"]
        if not isinstance(details, list) or len(details) > 128:
            raise GatewayError("provider_gateway_request_protocol")
        payload_fields = {"reasoning.text": "text", "reasoning.summary": "summary", "reasoning.encrypted": "data"}
        for detail in details:
            if not isinstance(detail, dict) or not isinstance(detail.get("type"), str):
                raise GatewayError("provider_gateway_request_protocol")
            content_field = payload_fields.get(detail["type"])
            allowed = {"type", "id", "format", "index", content_field}
            if detail["type"] == "reasoning.text":
                allowed.add("signature")
            if content_field is None or set(detail) - allowed or not isinstance(detail.get(content_field), str):
                raise GatewayError("provider_gateway_request_protocol")
            if len(detail[content_field].encode("utf-8")) > limit:
                raise GatewayError("provider_gateway_request_protocol")
            for field in ("id", "signature"):
                value = detail.get(field)
                if value is not None and (not isinstance(value, str) or len(value.encode("utf-8")) > limit):
                    raise GatewayError("provider_gateway_request_protocol")
            if "format" in detail and (not isinstance(detail["format"], str) or len(detail["format"]) > 128):
                raise GatewayError("provider_gateway_request_protocol")
            if "index" in detail and (type(detail["index"]) is not int or not 0 <= detail["index"] <= 2147483647):
                raise GatewayError("provider_gateway_request_protocol")

    def _colibri_body(self, payload: dict[str, Any], model: str) -> bytes:
        gateway = self.server.gateway
        if payload.get("reasoning_effort") != "none":
            raise GatewayError("provider_gateway_request_protocol")
        response = self._open("GET", "/v1/models")
        if response.status in {401, 403}:
            raise _PolicyRejection("credential_401" if response.status == 401 else "credential_403")
        if response.status != 200:
            raise GatewayError("provider_gateway_upstream_protocol")
        resident = resident_chat_model(self._small_json(response).get("data"))
        if resident is None or resident["id"] != model:
            raise _PolicyRejection("model_not_resident")
        context = resident_context(resident)
        if context is None or (gateway.expected_context_window is not None
                               and context < gateway.expected_context_window):
            raise _PolicyRejection("context_window")
        return json.dumps({**payload, "store": False, "context_compaction": "off"},
                          allow_nan=False, separators=(",", ":")).encode()

    def _generation_body(self, payload: Any) -> bytes:
        allowed = {"model", "messages", "tools", "tool_choice", "stream", "stream_options",
                   "max_tokens", "max_completion_tokens", "temperature", "reasoning_effort",
                   "top_p", "seed", "parallel_tool_calls", "stop", "frequency_penalty",
                   "presence_penalty", "store"}
        if not isinstance(payload, dict) or set(payload) - allowed:
            raise GatewayError("provider_gateway_request_protocol")
        # Pi's OpenAI SDK explicitly disables response storage. Permit only
        # that boolean; no caller can enable server-side persistence here.
        if payload.get("store", False) is not False:
            raise GatewayError("provider_gateway_request_protocol")
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise GatewayError("provider_gateway_request_protocol")
        for message in messages:
            if (not isinstance(message, dict) or set(message) - {"role", "content", "name", "tool_call_id", "tool_calls",
                                                                "reasoning", "reasoning_content", "reasoning_text", "reasoning_details"}
                    or message.get("role") not in {"system", "developer", "user", "assistant", "tool"}):
                raise GatewayError("provider_gateway_request_protocol")
            self._reasoning_history(message)
            content = message.get("content")
            if isinstance(content, list):
                if any(not isinstance(part, dict) or set(part) != {"type", "text"}
                       or part.get("type") != "text" or not isinstance(part.get("text"), str) for part in content):
                    raise GatewayError("provider_gateway_request_protocol")
            elif content is not None and not isinstance(content, str):
                raise GatewayError("provider_gateway_request_protocol")
        tools = payload.get("tools", [])
        if not isinstance(tools, list) or any(not isinstance(tool, dict) or set(tool) != {"type", "function"}
                or tool.get("type") != "function" or not isinstance(tool.get("function"), dict) for tool in tools):
            raise GatewayError("provider_gateway_request_protocol")
        model = payload.get("model")
        if not isinstance(model, str) or not 1 <= len(model) <= 256:
            raise GatewayError("provider_gateway_request_protocol")
        if self.server.gateway.kind == "colibri":
            return self._colibri_body(payload, model)
        models = self._verify_policy()
        admitted = [item for item in models if isinstance(item, dict) and item.get("id") == model
                    and item.get("owned_by") == "unsloth-studio" and item.get("loaded") is True
                    and (item.get("task") is None or item.get("task") == "text-generation")
                    and ((isinstance(item.get("quant"), str) and bool(item["quant"].strip()))
                         or model in self.server.gateway.gguf_model_ids)]
        if not admitted:
            raise GatewayError("provider_gateway_model_not_resident_gguf")
        expected_context = self.server.gateway.expected_context_window
        for item in admitted:
            context = item.get("context_length")
            if expected_context is not None and type(context) is int and 0 < context < expected_context:
                raise _PolicyRejection("context_window")
        payload = dict(payload)
        payload.update(store=False, enable_tools=False, enabled_tools=[], mcp_enabled=False,
                       auto_heal_tool_calls=False, nudge_tool_calls=False)
        return json.dumps(payload, allow_nan=False, separators=(",", ":")).encode()

    def _forward(self) -> None:
        gateway = self.server.gateway
        self.close_connection = True
        if self.headers.get("Origin") or self.headers.get("Transfer-Encoding"):
            self._reply(400, {"error": {"code": "provider_gateway_request_rejected"}})
            return
        if (gateway.kind == "unsloth" and self.command == "GET"
                and self.path == "/benchmark/unsloth-policy"):
            if self.headers.get("Content-Length") not in {None, "0"}:
                self._reply(400, {"error": {"code": "provider_gateway_request_rejected"}})
                return
            self._policy()
            return
        if (self.command, self.path) not in {("GET", "/v1/models"), ("POST", "/v1/chat/completions")}:
            self._reply(404, {"error": {"code": "provider_gateway_route_rejected"}})
            return
        body = None
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) > 1:
            self._reply(400, {"error": {"code": "provider_gateway_request_rejected"}})
            return
        if self.command == "POST":
            if len(lengths) != 1 or not lengths[0].isdecimal():
                self._reply(411, {"error": {"code": "provider_gateway_length_required"}})
                return
            length = int(lengths[0])
            if length > gateway.max_request_bytes:
                self._reply(413, {"error": {"code": "provider_gateway_request_limit"}})
                return
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise GatewayError("provider_gateway_request_incomplete")
            payload = json.loads(raw)
            body = self._generation_body(payload)
            if len(body) > gateway.max_request_bytes:
                self._reply(413, {"error": {"code": "provider_gateway_request_limit"}})
                return
        elif lengths and lengths != ["0"]:
            self._reply(400, {"error": {"code": "provider_gateway_request_rejected"}})
            return
        response = self._open(self.command, self.path, body)
        if response.status != 200:
            status = response.status if response.status in {400, 401, 403, 404, 408, 413, 429, 500, 502, 503, 504} else 502
            self._reply(status, {"error": {"code": "provider_gateway_upstream_failed"}})
            return
        raw_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
        if raw_type not in {"application/json", "text/event-stream"}:
            raise GatewayError("provider_gateway_upstream_protocol")
        self.response_started = True
        self.send_response_only(200)
        self.send_header("Content-Type", raw_type)
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        redactor = _SecretFilter(self.secret) if self.secret is not None else None
        total = 0
        while True:
            self._remaining()
            block = response.read1(8192)
            if not block:
                break
            total += len(block)
            if total > gateway.max_response_bytes:
                raise GatewayError("provider_gateway_response_limit")
            clean = redactor.feed(block) if redactor is not None else block
            if clean:
                self.wfile.write(clean)
                self.wfile.flush()
        tail = redactor.feed(b"", final=True) if redactor is not None else b""
        if tail:
            self.wfile.write(tail)
            self.wfile.flush()

    def _run(self) -> None:
        try:
            self._forward()
        except _PolicyRejection as exc:
            # Refused management responses may contain key metadata. Discard
            # them before emitting an allowlisted local status/code pair.
            if self.response is not None:
                self.response.close()
            if self.upstream is not None:
                self.upstream.close()
            try:
                self._reply(exc.status, {"error": {"code": exc.code}})
            except OSError:
                pass
        except (OSError, ValueError, TypeError, OverflowError, http.client.HTTPException, GatewayError):
            try:
                self._reply(503, {"error": {"code": "provider_gateway_unavailable"}})
            except OSError:
                pass

    do_GET = _run
    do_POST = _run


class ProviderGateway:
    """Session-scoped host gateway. ``url`` is the only value passed to Pi.

    Context exit interrupts open sockets. Python cannot promise zeroing immutable
    strings; the credential is retained in host memory only for this session.
    """
    def __init__(self, url: str, secret: str | None, *, kind: str = "unsloth",
                 timeout_seconds: float = 1200,
                 max_request_bytes: int = 8388608, max_response_bytes: int = 33554432,
                 max_header_bytes: int = 16384, max_connections: int = 16,
                 gguf_model_ids: tuple[str, ...] = (), expected_context_window: int | None = None):
        self.target = _target(url)
        if kind not in {"unsloth", "colibri"}:
            raise GatewayError("provider_gateway_kind_invalid")
        self.kind = kind
        self._secret = None if kind == "colibri" and secret is None else validate_secret(secret)
        if (type(timeout_seconds) not in {float, int} or not math.isfinite(timeout_seconds)
                or not 0 < timeout_seconds <= 7200):
            raise GatewayError("provider_gateway_timeout_invalid")
        for value, lower, upper in ((max_request_bytes, 256, 67108864),
                                     (max_response_bytes, 256, 134217728),
                                     (max_header_bytes, 256, 65536),
                                     (max_connections, 1, 64)):
            if type(value) is not int or not lower <= value <= upper:
                raise GatewayError("provider_gateway_limit_invalid")
        self.timeout_seconds = float(timeout_seconds)
        self.max_request_bytes = max_request_bytes
        self.max_response_bytes = max_response_bytes
        self.max_header_bytes = max_header_bytes
        self.max_connections = max_connections
        if not isinstance(gguf_model_ids, tuple) or any(not isinstance(name, str) or not name or len(name) > 256 for name in gguf_model_ids):
            raise GatewayError("provider_gateway_model_ids_invalid")
        self.gguf_model_ids = frozenset(gguf_model_ids)
        if expected_context_window is not None and (type(expected_context_window) is not int or expected_context_window <= 0):
            raise GatewayError("provider_gateway_context_window_invalid")
        self.expected_context_window = expected_context_window
        self._server: _Server | None = None
        self._thread: threading.Thread | None = None
        self.url: str | None = None

    def __enter__(self) -> ProviderGateway:
        if self._server is not None or self._secret == "":
            raise GatewayError("provider_gateway_session_invalid")
        server = _Server(("127.0.0.1", 0), _Handler)
        server.gateway = self
        server.slots = threading.BoundedSemaphore(self.max_connections)
        server.active_lock = threading.Lock()
        server.active = set()
        server.handlers = set()
        self._server = server
        self.url = f"http://127.0.0.1:{server.server_port}"
        self._thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
        self._thread.start()
        return self

    def close(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            server.shutdown()
            with server.active_lock:
                active = list(server.active)
                handlers = list(server.handlers)
            for handler in handlers:
                handler._expire()
            for connection in active:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            server.server_close()
            if self._thread is not None:
                self._thread.join(timeout=1)
        self._secret = ""

    def __exit__(self, *_args: Any) -> None:
        self.close()
