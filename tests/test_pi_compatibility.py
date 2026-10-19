from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localagent_bench.pi_adapter import PiRun
from localagent_bench.pi_compatibility import check_pi_compatibility
from localagent_bench.pi_adapter import run_pi
from localagent_bench.sandbox import select_sandbox


class PiCompatibilityTests(unittest.TestCase):
    def test_cancellation_terminates_probe_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "slow.py"
            script.write_text("import time\ntime.sleep(10)\n", encoding="utf-8")
            workspace = root / "workspace"
            workspace.mkdir()
            agent = root / "agent"
            agent.mkdir()
            cancel = threading.Event()
            timer = threading.Timer(0.2, cancel.set)
            timer.start()
            try:
                start = time.monotonic()
                result = run_pi(
                    (sys.executable, str(script)), "synthetic", "off", "done",
                    workspace, agent, 10, select_sandbox("audit"),
                    "http://127.0.0.1:1", tools="", cancel_event=cancel,
                )
            finally:
                timer.cancel()
            self.assertEqual("cancelled", result.status)
            self.assertLess(time.monotonic() - start, 5)

    def _probe(self, *, bad_effort=False, retry=False, broken_events=False, wrong_error=False,
               provider_kind="ollama"):
        def fake_run(pi_command, model, thinking, prompt, workspace, agent_dir, timeout, sandbox, url, *, tools, cancel_event,
                     provider_kind=provider_kind):
            self.assertEqual(("pi",), pi_command)
            self.assertEqual("", tools)
            settings = json.loads((agent_dir / "models.json").read_text(encoding="utf-8"))
            self.assertEqual(f"{url}/v1", settings["providers"][provider_kind]["baseUrl"])
            effort = settings["providers"][provider_kind]["models"][0]["samplingParams"]["reasoning_effort"]
            payload = {
                "model": model,
                "reasoning_effort": "wrong" if bad_effort else effort,
                "max_tokens": 321,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
            }
            request = Request(
                f"{url}/v1/chat/completions", data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            try:
                with urlopen(request, timeout=5) as response:
                    response.read()
                failed = False
            except HTTPError as exc:
                self.assertEqual(500, exc.code)
                failed = True
            metrics = {
                "json_parse_errors": 0, "retry_events": 1 if retry else 0,
                "assistant_turns": 1,
            }
            return PiRun(
                "ok" if (wrong_error or not failed) else "pi_error", 0, 0.1,
                "not-json" if broken_events else '{"type":"message_end"}\n',
                "", metrics, "done", ["pi"],
            )

        with patch("localagent_bench.pi_compatibility.run_pi", side_effect=fake_run):
            return check_pi_compatibility(("pi",), 10, provider_kind=provider_kind)

    def test_compatible_binary_passes_synthetic_contract(self):
        result = self._probe()
        if result.failed_check == "loopback_unavailable":
            self.skipTest("loopback non disponibile")
        self.assertTrue(result.passed, result)
        self.assertEqual(("off_200", "medium_200", "off_500"), result.checks)

    def test_custom_local_provider_uses_same_pi_contract(self):
        for kind in ("lmstudio", "llama_cpp"):
            with self.subTest(provider=kind):
                result = self._probe(provider_kind=kind)
                if result.failed_check == "loopback_unavailable":
                    self.skipTest("loopback non disponibile")
                self.assertTrue(result.passed, result)

    def test_bad_payload_fails_closed(self):
        result = self._probe(bad_effort=True)
        if result.failed_check == "loopback_unavailable":
            self.skipTest("loopback non disponibile")
        self.assertEqual("off_200_reasoning_effort", result.failed_check)

    def test_retry_and_corrupt_events_fail_closed(self):
        for options, expected in (
            ({"retry": True}, "off_200_retry"),
            ({"broken_events": True}, "off_200_events"),
            ({"wrong_error": True}, "off_500_terminal_error"),
        ):
            with self.subTest(expected=expected):
                result = self._probe(**options)
                if result.failed_check == "loopback_unavailable":
                    self.skipTest("loopback non disponibile")
                self.assertEqual(expected, result.failed_check)


if __name__ == "__main__":
    unittest.main()
