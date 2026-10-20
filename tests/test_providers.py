from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localagent_bench.llama_cpp import LlamaCppProvider
from localagent_bench.lmstudio import LMStudioProvider
from localagent_bench.ollama import OllamaModel, OllamaProvider
from localagent_bench.config import ConfigError, load_config
from localagent_bench.provider_adapter import create_provider
from localagent_bench.providers import LocalProvider, ProviderError
from localagent_bench.thinking import resolve_thinking_policy


class LocalProviderTests(unittest.TestCase):
    def test_factory_selects_dedicated_adapters_without_changing_config(self):
        config = load_config(ROOT / "benchmark.json")
        ollama = create_provider(replace(config, provider_kind="ollama"))
        lmstudio = create_provider(replace(config, provider_kind="lmstudio"))
        llama_cpp = create_provider(replace(config, provider_kind="llama_cpp"))
        self.assertIsInstance(ollama, OllamaProvider)
        self.assertIsInstance(lmstudio, LMStudioProvider)
        self.assertIsInstance(llama_cpp, LlamaCppProvider)
        self.assertFalse(ollama.explicit_load)
        self.assertTrue(lmstudio.explicit_load)
        self.assertTrue(llama_cpp.explicit_load)
        self.assertEqual(("api", "configuration", "configuration"),
                         (ollama.version_source, lmstudio.version_source, llama_cpp.version_source))

    def test_provider_url_rejects_malformed_port(self):
        raw = json.loads((ROOT / "benchmark.json").read_text(encoding="utf-8"))
        raw["provider"]["url"] = "http://127.0.0.1:invalid"
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "benchmark.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "porta valida"):
                load_config(path)

    @unittest.skipUnless(sys.platform == "win32", "Windows command shim")
    @patch("localagent_bench.config.shutil.which", return_value="C:/tools/pi.cmd")
    def test_windows_resolves_pi_command_shim(self, _which):
        config = load_config(ROOT / "benchmark.json")
        self.assertEqual("C:/tools/pi.cmd", config.pi_command[0])

    @patch("localagent_bench.providers._request")
    def test_lmstudio_discovery_filters_non_llms_and_hashes_explicit_gguf(self, request):
        request.return_value = {"models": [
            {"key": "coder", "type": "llm", "size_bytes": 3, "format": "gguf",
             "capabilities": {"reasoning": {"allowed_options": ["off", "medium"]}}},
            {"key": "embed", "type": "embedding"},
        ]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "coder.gguf"
            path.write_bytes(b"GGUF-test")
            provider = LocalProvider("lmstudio", "http://127.0.0.1:1234", {"coder": path}, "0.4.0")
            listed = provider.list_models(with_digest=True)
        self.assertEqual(["coder"], [item.name for item in listed])
        self.assertEqual(hashlib.sha256(b"GGUF-test").hexdigest(), listed[0].digest)
        self.assertTrue(listed[0].thinking_capable)
        self.assertEqual("0.4.0", provider.version())
        self.assertEqual("/api/v1/models", request.call_args.args[1])

    @patch("localagent_bench.providers._request")
    def test_llama_router_discovery_and_unload(self, request):
        request.side_effect = [
            {"data": [{"id": "coder.gguf", "status": {"value": "loaded"}}]},
            {"success": True},
            {"data": [{"id": "coder.gguf", "status": {"value": "unloaded"}}]},
        ]
        provider = LocalProvider("llama_cpp", "http://127.0.0.1:8080")
        self.assertEqual("coder.gguf", provider.list_models()[0].name)
        provider.unload("coder.gguf")
        self.assertEqual("/models/unload", request.call_args_list[1].args[1])
        self.assertEqual({"model": "coder.gguf"}, request.call_args_list[1].args[2])
        self.assertEqual("/models", request.call_args.args[1])

    @patch("localagent_bench.providers._request")
    def test_off_and_active_thinking_fail_closed(self, request):
        provider = LocalProvider("lmstudio", "http://127.0.0.1:1234")
        model = OllamaModel("coder", None, None, None, {})
        request.side_effect = [{"status": "loaded"}, {"choices": [{"message": {"reasoning_content": "private", "content": "7"}}]}]
        off = provider.preflight_thinking(model, resolve_thinking_policy("off"), timeout=30)
        self.assertEqual("unexpected_thinking", off.status)
        self.assertEqual("none", request.call_args.args[2]["reasoning_effort"])
        self.assertNotIn("private", repr(off))
        request.side_effect = [{"status": "loaded"}, {"choices": [{"message": {"content": "7"}}]}]
        active = provider.preflight_thinking(model, resolve_thinking_policy("medium"), timeout=30)
        self.assertEqual("thinking_not_observed", active.status)
        request.side_effect = [{"status": "loaded"}, {"choices": [{"message": {"content": "<think>hidden</think>7"}}]}]
        tagged = provider.preflight_thinking(model, resolve_thinking_policy("off"), timeout=30)
        self.assertEqual("unexpected_thinking", tagged.status)
        request.side_effect = ProviderError("unsupported")
        error = provider.preflight_thinking(model, resolve_thinking_policy("medium"), timeout=30)
        self.assertEqual("provider_error", error.status)

    @patch("localagent_bench.providers._request")
    def test_lmstudio_unloads_only_selected_model_instances(self, request):
        request.side_effect = [
            {"models": [
                {"key": "coder", "loaded_instances": [{"id": "coder@1"}]},
                {"key": "other", "loaded_instances": [{"id": "other@1"}]},
            ]},
            {"instance_id": "coder@1"},
        ]
        LocalProvider("lmstudio", "http://127.0.0.1:1234").unload("coder")
        self.assertEqual({"instance_id": "coder@1"}, request.call_args.args[2])


if __name__ == "__main__":
    unittest.main()
