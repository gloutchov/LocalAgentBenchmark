from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localagent_bench.provider_auth import CredentialError, resolve_credential, validate_reference, validate_secret


def _key() -> str:
    return "test-" + "credential" + "-for-local-gateway"


class ProviderCredentialTests(unittest.TestCase):
    def test_reference_and_header_validation(self):
        self.assertEqual("local-provider_1", validate_reference("local-provider_1"))
        for value in ("", "../outside", " spaces ", "x\n-a", 5, "x" * 129):
            with self.subTest(value=repr(value)), self.assertRaises(CredentialError):
                validate_reference(value)
        for value in ("", "line\r\nInjected: x", "spaces key", "colon:key", "x" * 4097):
            with self.subTest(value=repr(value)), self.assertRaises(CredentialError):
                validate_secret(value)

    @patch("localagent_bench.provider_auth.sys.platform", "darwin")
    @patch("localagent_bench.provider_auth.subprocess.run")
    def test_macos_lookup_keeps_value_out_of_argv_and_environment(self, execute):
        execute.return_value = Mock(returncode=0, stdout=(_key() + "\n").encode())
        self.assertEqual(_key(), resolve_credential("unsloth-local"))
        args, kwargs = execute.call_args
        self.assertEqual(["/usr/bin/security", "find-generic-password", "-s", "LocalAgentBenchmark",
                          "-a", "unsloth-local", "-w"], args[0])
        self.assertNotIn(_key(), repr(args))
        self.assertNotIn("env", kwargs)
        self.assertEqual(subprocess.DEVNULL, kwargs["stderr"])
        self.assertEqual(subprocess.DEVNULL, kwargs["stdin"])

    @patch("localagent_bench.provider_auth.sys.platform", "linux")
    @patch("localagent_bench.provider_auth.shutil.which", return_value="/usr/bin/secret-tool")
    @patch("localagent_bench.provider_auth.subprocess.run")
    def test_linux_uses_only_lookup_attributes(self, execute, _which):
        execute.return_value = Mock(returncode=0, stdout=(_key() + "\n").encode())
        self.assertEqual(_key(), resolve_credential("provider"))
        self.assertEqual(["/usr/bin/secret-tool", "lookup", "service", "LocalAgentBenchmark",
                          "account", "provider"], execute.call_args.args[0])

    @patch("localagent_bench.provider_auth.sys.platform", "win32")
    @patch("localagent_bench.provider_auth._windows_value")
    def test_windows_reads_generic_credential_without_process(self, lookup):
        lookup.return_value = _key()
        with patch("localagent_bench.provider_auth.subprocess.run") as execute:
            self.assertEqual(_key(), resolve_credential("provider"))
            lookup.assert_called_once_with("provider")
            execute.assert_not_called()

    @patch("localagent_bench.provider_auth.sys.platform", "linux")
    @patch("localagent_bench.provider_auth.shutil.which", return_value=None)
    def test_missing_store_fails_closed(self, _which):
        with self.assertRaisesRegex(CredentialError, "credential_store_unavailable"):
            resolve_credential("provider")

    @patch("localagent_bench.provider_auth.sys.platform", "darwin")
    @patch("localagent_bench.provider_auth.subprocess.run")
    def test_store_failures_never_expose_output(self, execute):
        for result in (Mock(returncode=1, stdout=_key().encode()),
                       Mock(returncode=0, stdout=(_key() + "\nInjected").encode()),
                       Mock(returncode=0, stdout=b"\xff")):
            execute.side_effect = None
            execute.return_value = result
            with self.assertRaises(CredentialError) as context:
                resolve_credential("provider")
            self.assertNotIn(_key(), str(context.exception))
        execute.side_effect = subprocess.TimeoutExpired([_key()], 10, output=_key())
        with self.assertRaises(CredentialError) as context:
            resolve_credential("provider")
        self.assertNotIn(_key(), str(context.exception))
        self.assertIsNone(context.exception.__cause__)

    def test_memory_prompt_is_explicit_and_never_reads_store(self):
        with patch("localagent_bench.provider_auth.subprocess.run") as execute:
            value = resolve_credential("provider", prompt=True, prompt_function=lambda _label: _key())
            self.assertEqual(_key(), value)
            execute.assert_not_called()
        with patch("localagent_bench.provider_auth.sys.stdin.isatty", return_value=False):
            with self.assertRaisesRegex(CredentialError, "requires_terminal"):
                resolve_credential("provider", prompt=True)
        with self.assertRaisesRegex(CredentialError, "cancelled"):
            resolve_credential("provider", prompt=True, prompt_function=Mock(side_effect=EOFError))


if __name__ == "__main__":
    unittest.main()
