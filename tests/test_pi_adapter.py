from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localagent_bench.pi_adapter import (
    AUDIT_VERSION,
    _refine_status_from_events,
    audit_workspace_accesses,
    parse_json_events,
    write_models_config,
)
from localagent_bench.ollama import OllamaModel
from localagent_bench.thinking import resolve_thinking_policy


class PiAdapterTests(unittest.TestCase):
    def test_current_audit_version(self):
        self.assertEqual(4, AUDIT_VERSION)

    def test_extracts_usage_tools_and_final_response(self):
        lines = [
            {"type": "session", "version": 3},
            {"type": "tool_execution_start", "toolName": "read"},
            {"type": "tool_execution_end", "toolName": "read", "isError": False},
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "done"}],
                    "stopReason": "stop",
                    "usage": {"input": 10, "output": 4, "cacheRead": 1, "cacheWrite": 0, "totalTokens": 15},
                },
            },
        ]
        metrics, response = parse_json_events("\n".join(json.dumps(line) for line in lines))
        self.assertEqual("done", response)
        self.assertEqual(1, metrics["tool_calls"])
        self.assertEqual(4, metrics["usage"]["output"])
        self.assertEqual(0, metrics["streamed_thinking_chars"])
        self.assertEqual(0, metrics["retry_events"])
        self.assertEqual(["stop"], metrics["stop_reasons"])
        self.assertFalse(metrics["terminal_agent_error"])

    def test_terminal_provider_failure_overrides_zero_exit_status_without_copying_error_text(self):
        events = [
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "thinking", "thinking": "unfinished"}],
                    "stopReason": "error",
                    "usage": {},
                    "errorMessage": "PRIVATE provider diagnostic",
                },
            },
            {
                "type": "auto_retry_end",
                "success": False,
                "attempt": 3,
                "finalError": "PRIVATE provider diagnostic",
            },
        ]

        metrics, response = parse_json_events("\n".join(json.dumps(event) for event in events))

        self.assertEqual("", response)
        self.assertTrue(metrics["terminal_agent_error"])
        self.assertNotIn("PRIVATE", json.dumps(metrics))
        self.assertEqual("pi_error", _refine_status_from_events("ok", metrics))
        self.assertEqual("timeout", _refine_status_from_events("timeout", metrics))

    def test_successful_later_turn_clears_a_transient_provider_error(self):
        events = [
            {
                "type": "message_end",
                "message": {"role": "assistant", "content": [], "stopReason": "error", "usage": {}},
            },
            {"type": "auto_retry_end", "success": False},
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "recovered"}],
                    "stopReason": "stop",
                    "usage": {},
                },
            },
            {"type": "auto_retry_end", "success": True},
        ]

        metrics, response = parse_json_events("\n".join(json.dumps(event) for event in events))

        self.assertEqual("recovered", response)
        self.assertFalse(metrics["terminal_agent_error"])
        self.assertEqual("ok", _refine_status_from_events("ok", metrics))

    def test_writes_isolated_ollama_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            thinking_model = OllamaModel(
                "model:a", 1, "digest", "now", {}, ("thinking",), True, True
            )
            plain_model = OllamaModel(
                "model:b", 1, "digest", "now", {}, ("completion",), True, False
            )
            write_models_config(
                target,
                "http://127.0.0.1:11434",
                [thinking_model, plain_model],
                8192,
                1024,
                0,
                resolve_thinking_policy("off"),
                http_idle_timeout_ms=0,
                agent_max_retries=0,
                provider_max_retries=0,
            )
            payload = json.loads((target / "models.json").read_text(encoding="utf-8"))
            provider = payload["providers"]["ollama"]
            self.assertEqual("http://127.0.0.1:11434/v1", provider["baseUrl"])
            self.assertEqual("model:a", provider["models"][0]["id"])
            self.assertFalse(provider["compat"]["supportsDeveloperRole"])
            self.assertTrue(provider["compat"]["supportsReasoningEffort"])
            self.assertEqual("max_tokens", provider["compat"]["maxTokensField"])
            self.assertTrue(provider["models"][0]["reasoning"])
            self.assertEqual("none", provider["models"][0]["thinkingLevelMap"]["off"])
            self.assertEqual("none", provider["models"][0]["samplingParams"]["reasoning_effort"])
            self.assertFalse(provider["models"][1]["reasoning"])
            self.assertNotIn("thinkingLevelMap", provider["models"][1])
            settings = json.loads((target / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(0, settings["httpIdleTimeoutMs"])
            self.assertEqual(
                {"enabled": False, "maxRetries": 0, "provider": {"maxRetries": 0}},
                settings["retry"],
            )

    def test_active_policy_is_written_without_downgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            model = OllamaModel(
                "model:a", 1, "digest", "now", {}, ("thinking",), True, True
            )
            write_models_config(
                target,
                "http://127.0.0.1:11434",
                [model],
                8192,
                1024,
                0,
                resolve_thinking_policy("medium"),
                http_idle_timeout_ms=0,
                agent_max_retries=0,
                provider_max_retries=0,
            )
            payload = json.loads((target / "models.json").read_text(encoding="utf-8"))
            model_payload = payload["providers"]["ollama"]["models"][0]
            self.assertEqual("medium", model_payload["samplingParams"]["reasoning_effort"])

    def test_counts_retries_without_copying_free_text(self):
        events = [
            {"type": "auto_retry_start", "attempt": 1, "error": "PRIVATE ERROR"},
            {"type": "auto_retry_end", "success": False, "finalError": "PRIVATE ERROR"},
        ]
        metrics, _response = parse_json_events("\n".join(json.dumps(event) for event in events))
        self.assertEqual(1, metrics["retry_events"])
        self.assertNotIn("PRIVATE", json.dumps(metrics))

    def test_audits_structured_and_shell_access_outside_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "results" / "workspace"
            workspace.mkdir(parents=True)
            protected = root / "cases"
            protected.mkdir()
            event = {
                "type": "message_start",
                "message": {
                    "content": [
                        {"type": "toolCall", "id": "safe", "name": "read", "arguments": {"path": "src/app.py"}},
                        {"type": "toolCall", "id": "safe-absolute", "name": "read", "arguments": {"path": str(workspace / "README.md")}},
                        {"type": "toolCall", "id": "escape", "name": "edit", "arguments": {"path": str(protected / "fixture.py")}},
                        {"type": "toolCall", "id": "shell", "name": "bash", "arguments": {"command": f"python3 {protected}/grader.py"}},
                    ]
                },
            }
            findings = audit_workspace_accesses(json.dumps(event), workspace, [protected])
            self.assertEqual({"escape", "shell"}, {item["tool_call_id"] for item in findings})
            self.assertTrue(any(item["reason"] == "structured_path_outside_workspace" for item in findings))
            self.assertTrue(
                any(item["reason"] == "shell_protected_path_outside_workspace" for item in findings)
            )
            self.assertTrue(all(item["access"] == "attempted" for item in findings))

    def test_allows_nested_scratch_traversal_test_that_stays_in_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            workspace.mkdir()
            event = {
                "type": "tool_execution_start",
                "toolCallId": "scratch-test",
                "toolName": "bash",
                "args": {
                    "command": (
                        "mkdir -p .benchmark-scratch/app && cd .benchmark-scratch/app && "
                        "python3 -m tinyjournal export note.txt ../rejected.md"
                    )
                },
            }
            findings = audit_workspace_accesses(json.dumps(event), workspace, [workspace.parent])
            self.assertEqual([], findings)

    def test_pwd_variable_tracks_nested_scratch_and_still_rejects_real_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "results" / "workspace"
            workspace.mkdir(parents=True)
            commands = {
                "inside": (
                    'export HOME="$PWD/.benchmark-scratch"\n'
                    'WS="$PWD/.benchmark-scratch/smoke"\n'
                    'mkdir -p "$WS"\n'
                    'cd "$WS" && PYTHONPATH="$OLDPWD/src" '
                    'python3 -m tinyjournal export note.txt ../fuori.md'
                ),
                "outside": (
                    'WS="$PWD/.benchmark-scratch/smoke"\n'
                    'cd "$WS" && python3 -m tinyjournal export note.txt ../../../fuori.md'
                ),
                "absolute-outside": 'cd "$PWD/.." && cat sibling.txt',
                "oldpwd-outside": (
                    'cd "$PWD/.benchmark-scratch/smoke"\n'
                    'cat "$OLDPWD/../secret.txt"'
                ),
            }
            events = [
                {
                    "type": "tool_execution_start",
                    "toolCallId": call_id,
                    "toolName": "bash",
                    "args": {"command": command},
                }
                for call_id, command in commands.items()
            ]

            findings = audit_workspace_accesses(
                "\n".join(json.dumps(event) for event in events),
                workspace,
                [workspace.parent],
            )

            self.assertEqual(
                {
                    "outside": {"../../../fuori.md"},
                    "absolute-outside": {str(workspace.resolve() / "..")},
                    "oldpwd-outside": {str(workspace.resolve() / "../secret.txt")},
                },
                {
                    call_id: {item["target"] for item in findings if item["tool_call_id"] == call_id}
                    for call_id in ("outside", "absolute-outside", "oldpwd-outside")
                },
            )
            self.assertFalse(any(item["tool_call_id"] == "inside" for item in findings))

    def test_reports_system_temp_repository_and_network_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "results" / "workspace"
            workspace.mkdir(parents=True)
            event = {
                "type": "tool_execution_start",
                "toolCallId": "outside",
                "toolName": "bash",
                "args": {
                    "command": (
                        f'cd /tmp && cp "{root}/LICENSE" LICENSE && '
                        "curl -fsSL https://example.invalid/LICENSE -o LICENSE"
                    )
                },
            }
            findings = audit_workspace_accesses(json.dumps(event), workspace, [root])
            reasons = {item["reason"] for item in findings}
            self.assertIn("shell_path_outside_workspace", reasons)
            self.assertIn("shell_protected_path_outside_workspace", reasons)
            self.assertIn("shell_network_attempt", reasons)

    def test_url_text_alone_is_not_a_network_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            event = {
                "type": "tool_execution_start",
                "toolCallId": "docs",
                "toolName": "bash",
                "args": {"command": "printf 'https://example.invalid/docs' > README.md"},
            }
            self.assertEqual([], audit_workspace_accesses(json.dumps(event), workspace, []))

    def test_awk_program_starting_with_slash_is_not_a_path(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            event = {
                "type": "tool_execution_start",
                "toolCallId": "awk",
                "toolName": "bash",
                "args": {
                    "command": r"awk '/- \[x\] Export command implemented/ {print NR}' PLAN.md"
                },
            }
            self.assertEqual([], audit_workspace_accesses(json.dumps(event), workspace, []))

    def test_printed_and_grep_patterns_are_not_treated_as_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            event = {
                "type": "tool_execution_start",
                "toolCallId": "text",
                "toolName": "bash",
                "args": {
                    "command": "echo /tmp && grep '/tmp' README.md && printf '/outside' > NOTES.md"
                },
            }
            self.assertEqual([], audit_workspace_accesses(json.dumps(event), workspace, []))

    def test_grep_input_and_redirection_outside_workspace_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            event = {
                "type": "tool_execution_start",
                "toolCallId": "paths",
                "toolName": "bash",
                "args": {"command": "grep needle /tmp/input.txt > /tmp/output.txt"},
            }
            findings = audit_workspace_accesses(json.dumps(event), workspace, [])
            self.assertEqual(
                {"/tmp/input.txt", "/tmp/output.txt"},
                {item["target"] for item in findings},
            )

    def test_foreign_absolute_path_style_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            foreign_path = "C:/outside/input.txt" if sys.platform != "win32" else "/tmp/input.txt"
            event = {
                "type": "tool_execution_start",
                "toolCallId": "foreign-path",
                "toolName": "bash",
                "args": {"command": f"python read_file.py {foreign_path}"},
            }
            findings = audit_workspace_accesses(json.dumps(event), workspace, [])
            self.assertEqual({foreign_path}, {item["target"] for item in findings})

    def test_literal_heredoc_body_is_not_parsed_as_shell_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            event = {
                "type": "tool_execution_start",
                "toolCallId": "heredoc",
                "toolName": "bash",
                "args": {
                    "command": (
                        "cat > tests.py << 'EOF'\n"
                        "from pathlib import Path\n"
                        "ROOT = Path(__file__).resolve().parents[1] / \"src\"\n"
                        "EOF"
                    )
                },
            }
            self.assertEqual([], audit_workspace_accesses(json.dumps(event), workspace, []))

    def test_executable_heredoc_network_code_is_still_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            events = [
                {
                    "type": "tool_execution_start",
                    "toolCallId": "python-heredoc",
                    "toolName": "bash",
                    "args": {
                        "command": "python3 <<'PY'\nimport requests\nrequests.get('https://example.invalid')\nPY"
                    },
                },
                {
                    "type": "tool_execution_start",
                    "toolCallId": "shell-heredoc",
                    "toolName": "bash",
                    "args": {"command": "bash <<'SH'\ncurl https://example.invalid\nSH"},
                },
            ]
            findings = audit_workspace_accesses("\n".join(json.dumps(event) for event in events), workspace, [])
            self.assertEqual(
                {"python-heredoc", "shell-heredoc"},
                {item["tool_call_id"] for item in findings},
            )
            self.assertTrue(all(item["reason"] == "shell_network_attempt" for item in findings))


if __name__ == "__main__":
    unittest.main()
