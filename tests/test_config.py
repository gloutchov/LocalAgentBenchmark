from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localagent_bench.config import ConfigError, load_config
from localagent_bench.cli import _parser


class ConfigTests(unittest.TestCase):
    def test_repository_config_discovers_case_manifests(self):
        config = load_config(ROOT / "benchmark.json")
        self.assertEqual("installed", config.models)
        self.assertEqual(6, len(config.cases))
        self.assertEqual(("targeted_patch",), config.profiles["smoke"])
        self.assertEqual(("thinking_challenge",), config.profiles["thinking"])
        self.assertIn("thinking_challenge", config.profiles["standard"])
        self.assertIn("thinking_challenge", config.profiles["full"])
        self.assertEqual("audit", config.defaults.sandbox)
        self.assertEqual((ROOT / "cases").resolve(), config.cases_directory)
        self.assertEqual(
            "Targeted patch with regressions and documentation",
            config.cases["targeted_patch"].title_en,
        )
        self.assertEqual(
            ROOT / "cases" / "targeted_patch" / "case.json",
            config.cases["targeted_patch"].manifest_path,
        )
        self.assertEqual(20, config.cases["milestone_closure"].manual_rubric_max_score)
        self.assertEqual(("results_dashboard",), config.profiles["showcase"])
        self.assertEqual(20, config.cases["results_dashboard"].manual_rubric_max_score)
        self.assertEqual((ROOT / "dashboard").resolve(), config.dashboard.assets_directory)
        self.assertEqual((ROOT / "results").resolve(), config.dashboard.results_directory)
        self.assertEqual("127.0.0.1", config.dashboard.host)
        self.assertEqual(0, config.dashboard.port)
        self.assertTrue(config.dashboard.open_browser)
        self.assertEqual("off", config.defaults.thinking)
        self.assertEqual(300, config.defaults.thinking_preflight_timeout_seconds)
        self.assertEqual(0, config.defaults.http_idle_timeout_ms)
        self.assertEqual(0, config.defaults.agent_max_retries)
        self.assertEqual(0, config.defaults.provider_max_retries)
        self.assertEqual(("smoke", "standard", "full"), config.guided.profiles)
        self.assertEqual((4, 2), config.guided.promotion_limits)
        self.assertEqual(
            (ROOT / ".localagent-benchmark" / "guided-preferences.json").resolve(),
            config.guided.preferences_file,
        )

    def test_cli_thinking_override_is_parsed_without_changing_default(self):
        args = _parser().parse_args(["run", "--thinking", "medium"])
        self.assertEqual("medium", args.thinking)
        self.assertEqual("off", load_config(ROOT / "benchmark.json").defaults.thinking)
        with self.assertRaises(SystemExit):
            _parser().parse_args(["run", "--thinking", "automatic"])

    def test_invalid_thinking_control_defaults_are_rejected(self):
        raw = json.loads((ROOT / "benchmark.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            raw["defaults"]["thinking"] = "automatic"
            path = root / "benchmark.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "thinking"):
                load_config(path)

            raw["defaults"]["thinking"] = "off"
            raw["defaults"]["thinking_preflight_timeout_seconds"] = 1
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "thinking_preflight_timeout_seconds"):
                load_config(path)

    def test_unknown_profile_case_is_rejected(self):
        raw = json.loads((ROOT / "benchmark.json").read_text(encoding="utf-8"))
        raw["cases"] = [
            {
                "id": "targeted_patch",
                "title": "Legacy case",
                "category": "test",
                "weight": 1,
            }
        ]
        raw["profiles"] = {"standard": ["targeted_patch", "missing"]}
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "benchmark.json"
            fixture = path.parent / "cases" / "targeted_patch" / "fixture"
            fixture.mkdir(parents=True)
            (fixture.parent / "prompt.md").write_text("prompt\n", encoding="utf-8")
            (fixture.parent / "grader.py").write_text("print('{}')\n", encoding="utf-8")
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "Casi sconosciuti"):
                load_config(path)

    def test_legacy_inline_case_configuration_remains_readable(self):
        raw = json.loads((ROOT / "benchmark.json").read_text(encoding="utf-8"))
        raw["cases"] = [
            {"id": "legacy", "title": "Caso legacy", "category": "compatibility", "weight": 2}
        ]
        raw["profiles"] = {"standard": ["legacy"]}
        raw.pop("guided", None)
        raw.pop("preliminary", None)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "cases" / "legacy" / "fixture"
            fixture.mkdir(parents=True)
            (fixture.parent / "prompt.md").write_text("prompt\n", encoding="utf-8")
            (fixture.parent / "grader.py").write_text("print('{}')\n", encoding="utf-8")
            path = root / "benchmark.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            config = load_config(path)
            self.assertEqual(2, config.cases["legacy"].weight)
            self.assertIsNone(config.cases["legacy"].manifest_path)

    def test_cases_directory_cannot_escape_repository(self):
        raw = json.loads((ROOT / "benchmark.json").read_text(encoding="utf-8"))
        raw["cases"] = {"directory": "../cases"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "benchmark.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "dentro il repository"):
                load_config(path)

    def test_dashboard_configuration_is_confined_and_loopback_only(self):
        raw = json.loads((ROOT / "benchmark.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "benchmark.json"
            fixture = path.parent / "cases" / "dashboard_config" / "fixture"
            fixture.mkdir(parents=True)
            (fixture.parent / "prompt.md").write_text("prompt\n", encoding="utf-8")
            (fixture.parent / "grader.py").write_text("print('{}')\n", encoding="utf-8")
            raw["cases"] = [
                {"id": "dashboard_config", "title": "Dashboard config", "category": "test", "weight": 1}
            ]
            raw["profiles"] = {"standard": ["dashboard_config"]}
            raw["dashboard"]["assets_directory"] = "../outside"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "path relativo"):
                load_config(path)

            raw["dashboard"]["assets_directory"] = "dashboard"
            raw["dashboard"]["host"] = "0.0.0.0"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "127.0.0.1"):
                load_config(path)

            raw["dashboard"]["host"] = "127.0.0.1"
            raw["dashboard"]["port"] = 70000
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "0 e 65535"):
                load_config(path)

    def test_guided_configuration_rejects_unsafe_profiles_limits_and_paths(self):
        raw = json.loads((ROOT / "benchmark.json").read_text(encoding="utf-8"))
        raw["cases"] = [
            {"id": "example", "title": "Example", "category": "test", "weight": 1}
        ]
        raw["profiles"] = {
            "smoke": ["example"],
            "standard": ["example"],
            "full": ["example"],
            "showcase": ["example"],
        }
        mutations = (
            ({"profiles": ["smoke", "showcase", "full"]}, "esattamente"),
            ({"promotion_limits": [2, 4]}, "decrescente"),
            ({"promotion_limits": [4, 0]}, "positivi"),
            ({"preferences_file": "../preferences.json"}, "path relativo"),
        )
        for update, message in mutations:
            with self.subTest(update=update), tempfile.TemporaryDirectory(dir=ROOT) as directory:
                payload = json.loads(json.dumps(raw))
                payload["guided"].update(update)
                path = Path(directory) / "benchmark.json"
                fixture = path.parent / "cases" / "example" / "fixture"
                fixture.mkdir(parents=True)
                (fixture.parent / "prompt.md").write_text("prompt\n", encoding="utf-8")
                (fixture.parent / "grader.py").write_text("print('{}')\n", encoding="utf-8")
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(ConfigError, message):
                    load_config(path)


if __name__ == "__main__":
    unittest.main()
