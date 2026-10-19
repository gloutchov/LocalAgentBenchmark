from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localagent_bench.comparison import ComparisonError, write_comparison


class ComparisonTests(unittest.TestCase):
    def test_local_provider_requires_runtime_version_and_gguf_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self._write_run(root, "local-a", overall=70, verified_thinking=True)
            second = self._write_run(root, "local-b", overall=72, verified_thinking=True)
            for run in (first, second):
                path = run / "run.json"
                manifest = json.loads(path.read_text(encoding="utf-8"))
                manifest["configuration"].update({"provider_kind": "lmstudio", "provider_url": "http://127.0.0.1:1234"})
                manifest["environment"].update({"provider_kind": "lmstudio", "provider_version": "0.4.0"})
                path.write_text(json.dumps(manifest), encoding="utf-8")
            comparison = write_comparison([first, second], root / "compatible")
            self.assertEqual("lmstudio", comparison["compatibility"]["provider_kind"])
            path = second / "run.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["model_metadata"]["model:a"]["digest"] = None
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ComparisonError, "Hash GGUF"):
                write_comparison([first, second], root / "missing-hash")

    def _write_run(
        self,
        root: Path,
        name: str,
        *,
        overall: float,
        fingerprint: str = "same-input",
        sandbox_backend: str = "audit-only",
        digest: str = "digest-a",
        max_tokens: int = 8192,
        thinking: str = "off",
        verified_thinking: bool = False,
        agent_retries: int = 0,
        http_idle_timeout_ms: int = 0,
    ) -> Path:
        run_dir = root / name
        run_dir.mkdir()
        manifest = {
            "schema_version": 4 if verified_thinking else 3,
            "profile": "full",
            "cases": ["case"],
            "inputs": {"cases": {"case": {"effective_input_sha256": fingerprint}}},
            "sandbox": {"backend": sandbox_backend, "enforced": sandbox_backend != "audit-only"},
            "configuration": {
                "timeout_seconds": 30,
                "repetitions": 1,
                "thinking": thinking,
                "warmup": False,
                "context_window": 32768,
                "max_tokens": max_tokens,
                "temperature": 0,
            },
            "model_metadata": {
                "model:a": {
                    "digest": digest,
                    **(
                        {"capabilities": ["completion", "thinking"], "thinking_capable": True}
                        if verified_thinking
                        else {}
                    ),
                }
            },
            "environment": {
                "platform": "test-os",
                "pi": "0.85.1" if verified_thinking else None,
                "ollama": "0.12.0" if verified_thinking else None,
                "hardware": {"machine": "test-cpu", "logical_cpu_count": 8},
            },
        }
        if verified_thinking:
            effort = "none" if thinking == "off" else thinking
            manifest["configuration"].update(
                {
                    "reasoning_effort": effort,
                    "agent_max_retries": agent_retries,
                    "provider_max_retries": 0,
                    "http_idle_timeout_ms": http_idle_timeout_ms,
                }
            )
            manifest["thinking_control"] = {
                "version": 1,
                "status": "passed",
                "requested": thinking,
                "reasoning_effort": effort,
                "source": "explicit_sampling_parameter",
                "retry_policy": {
                    "agent_max_retries": agent_retries,
                    "provider_max_retries": 0,
                },
                "http_idle_timeout_ms": http_idle_timeout_ms,
            }
        report = {
            "schema_version": 4 if verified_thinking else 3,
            "integrity": {"audit_version": 3, "disqualified_models": []},
            "leaderboard": [
                {
                    "model": "model:a",
                    "overall_score": overall,
                    "quality_score": overall,
                    "completion_rate": 100,
                    "speed_score": 100,
                    "token_efficiency_score": 100,
                    "median_duration_seconds": 10,
                    "median_output_tokens": 100,
                    "median_cpu_seconds": 2,
                    "median_energy_joules": None,
                }
            ],
            "results": [],
        }
        (run_dir / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
        (run_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
        return run_dir

    def test_aggregates_compatible_runs_with_dispersion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self._write_run(root, "first", overall=80)
            second = self._write_run(root, "second", overall=90)
            output = root / "comparison"
            comparison = write_comparison([first, second], output)
            overall = comparison["models"][0]["metrics"]["overall_score"]
            self.assertEqual(2, overall["count"])
            self.assertEqual(85, overall["mean"])
            self.assertGreater(overall["stddev"], 0)
            self.assertGreaterEqual(overall["ci95_low"], 0)
            self.assertLessEqual(overall["ci95_high"], 100)
            completion = comparison["models"][0]["metrics"]["completion_rate"]
            self.assertEqual(100, completion["ci95_low"])
            self.assertEqual(100, completion["ci95_high"])
            self.assertTrue((output / "COMPARISON.md").is_file())
            self.assertEqual("digest-a", comparison["models"][0]["model_digest"])

    def test_rejects_duplicate_runs_and_changed_model_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self._write_run(root, "first", overall=80)
            with self.assertRaisesRegex(ComparisonError, "una sola volta"):
                write_comparison([first, first], root / "duplicate")
            changed = self._write_run(root, "changed", overall=80, digest="digest-b")
            with self.assertRaisesRegex(ComparisonError, "Digest Ollama divergente"):
                write_comparison([first, changed], root / "changed-digest")

    def test_rejects_different_inputs_or_sandbox_backends(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self._write_run(root, "first", overall=80)
            changed = self._write_run(root, "changed", overall=80, fingerprint="changed")
            with self.assertRaisesRegex(ComparisonError, "inputs"):
                write_comparison([first, changed], root / "bad-input")

            backend = self._write_run(root, "backend", overall=80, sandbox_backend="macos-seatbelt")
            with self.assertRaisesRegex(ComparisonError, "sandbox_backend"):
                write_comparison([first, backend], root / "bad-backend")

            configuration = self._write_run(root, "configuration", overall=80, max_tokens=4096)
            with self.assertRaisesRegex(ComparisonError, "max_tokens"):
                write_comparison([first, configuration], root / "bad-configuration")

    def test_thinking_control_is_part_of_the_compatibility_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            off = self._write_run(root, "off", overall=80, verified_thinking=True)
            off_same = self._write_run(root, "off-same", overall=82, verified_thinking=True)
            comparison = write_comparison([off, off_same], root / "compatible")
            self.assertEqual(1, comparison["compatibility"]["thinking_control_version"])
            self.assertEqual("none", comparison["compatibility"]["reasoning_effort"])

            medium = self._write_run(
                root,
                "medium",
                overall=80,
                thinking="medium",
                verified_thinking=True,
            )
            with self.assertRaisesRegex(ComparisonError, "reasoning_effort|thinking"):
                write_comparison([off, medium], root / "mixed-modes")

            retries = self._write_run(
                root,
                "retries",
                overall=80,
                verified_thinking=True,
                agent_retries=1,
            )
            with self.assertRaisesRegex(ComparisonError, "agent_max_retries"):
                write_comparison([off, retries], root / "mixed-retries")

            idle = self._write_run(
                root,
                "idle",
                overall=80,
                verified_thinking=True,
                http_idle_timeout_ms=300000,
            )
            with self.assertRaisesRegex(ComparisonError, "http_idle_timeout_ms"):
                write_comparison([off, idle], root / "mixed-idle")

            legacy = self._write_run(root, "legacy", overall=80)
            with self.assertRaisesRegex(
                ComparisonError, "thinking_control_version|run_schema_version"
            ):
                write_comparison([off, legacy], root / "mixed-legacy")

    def test_pi_contract_version_is_part_of_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self._write_run(root, "first", overall=80, verified_thinking=True)
            second = self._write_run(root, "second", overall=82, verified_thinking=True)
            manifest_path = second / "run.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["pi_compatibility"] = {"status": "passed", "contract_version": 1}
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ComparisonError, "pi_contract"):
                write_comparison([first, second], root / "mixed-contracts")


if __name__ == "__main__":
    unittest.main()
