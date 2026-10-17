from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localagent_bench.report import write_report
from localagent_bench.pi_adapter import AUDIT_VERSION


class ReportTests(unittest.TestCase):
    def test_report_ranks_quality_first_and_accepts_pre_manifest_results(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            for model, score, duration, tokens in (("accurate", 90, 20, 200), ("fast", 60, 5, 50)):
                case_dir = run_dir / "models" / model / "cases" / "case-r1"
                case_dir.mkdir(parents=True)
                result = {
                    "schema_version": 3,
                    "model": model,
                    "case_id": "case",
                    "case_weight": 1,
                    "repetition": 1,
                    "status": "ok",
                    "duration_seconds": duration,
                    "metrics": {"usage": {"output": tokens}, "tool_calls": 1, "tool_errors": 0},
                    "grade": {"score": score},
                }
                (case_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
            report = write_report(run_dir)
            self.assertEqual("accurate", report["leaderboard"][0]["model"])
            self.assertEqual(90, report["leaderboard"][0]["case_scores"]["case"])
            self.assertEqual(4, report["schema_version"])
            self.assertEqual("unverified", report["run"]["thinking_control"]["status"])
            self.assertNotIn("case_manifest_schema_version", report["results"][0])
            self.assertEqual(AUDIT_VERSION, report["integrity"]["audit_version"])
            self.assertIsNone(report["leaderboard"][0]["median_energy_joules"])
            self.assertTrue((run_dir / "REPORT.md").exists())

    def test_integrity_violation_disqualifies_entire_model(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            tasks = [
                {"model": model, "case_id": case, "repetition": 1}
                for model in ("clean", "escaped")
                for case in ("one", "two")
            ]
            (run_dir / "run.json").write_text(
                json.dumps(
                    {
                        "task_order": tasks,
                        "integrity": {"status": "violations_detected", "violations": []},
                    }
                ),
                encoding="utf-8",
            )
            for model in ("clean", "escaped"):
                for case in ("one", "two"):
                    case_dir = run_dir / "models" / model / "cases" / f"{case}-r1"
                    case_dir.mkdir(parents=True)
                    valid = not (model == "escaped" and case == "one")
                    result = {
                        "model": model,
                        "case_id": case,
                        "case_weight": 1,
                        "repetition": 1,
                        "status": "ok",
                        "duration_seconds": 10,
                        "metrics": {"usage": {"output": 10}},
                        "grade": {"score": 90},
                        "baseline_tree": f"tree-{case}",
                        "input_fingerprint": f"input-{case}",
                        "integrity": {"valid_for_ranking": valid},
                    }
                    (case_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
            report = write_report(run_dir)
            self.assertEqual(["clean"], [row["model"] for row in report["leaderboard"]])
            self.assertEqual(["escaped"], report["integrity"]["disqualified_models"])
            self.assertIn("Modelli esclusi dalla classifica: `escaped`", (run_dir / "REPORT.md").read_text(encoding="utf-8"))

    def test_minority_baseline_is_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            models = ("first", "second", "contaminated")
            (run_dir / "run.json").write_text(
                json.dumps(
                    {
                        "task_order": [
                            {"model": model, "case_id": "case", "repetition": 1} for model in models
                        ],
                        "integrity": {"status": "passed", "violations": []},
                    }
                ),
                encoding="utf-8",
            )
            for model in models:
                case_dir = run_dir / "models" / model / "cases" / "case-r1"
                case_dir.mkdir(parents=True)
                result = {
                    "model": model,
                    "case_id": "case",
                    "case_weight": 1,
                    "repetition": 1,
                    "status": "ok",
                    "duration_seconds": 10,
                    "metrics": {"usage": {"output": 10}},
                    "grade": {"score": 90},
                    "baseline_tree": "different" if model == "contaminated" else "expected",
                    "integrity": {"valid_for_ranking": True},
                }
                (case_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
            report = write_report(run_dir)
            self.assertEqual(["contaminated"], report["integrity"]["disqualified_models"])
            self.assertEqual(["case"], report["integrity"]["baseline_mismatches"])
            self.assertEqual({"first", "second"}, {row["model"] for row in report["leaderboard"]})

    def test_report_reaudits_paths_and_network_with_current_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "results" / "run"
            case_dir = run_dir / "models" / "escaped" / "cases" / "case-r1"
            workspace = case_dir / "workspace"
            workspace.mkdir(parents=True)
            (run_dir / "run.json").write_text(
                json.dumps(
                    {
                        "task_order": [{"model": "escaped", "case_id": "case", "repetition": 1}],
                        "integrity": {"status": "passed", "violations": []},
                    }
                ),
                encoding="utf-8",
            )
            result = {
                "model": "escaped",
                "case_id": "case",
                "case_weight": 1,
                "repetition": 1,
                "status": "ok",
                "duration_seconds": 10,
                "metrics": {"usage": {"output": 10}},
                "grade": {"score": 90},
                "integrity": {
                    "valid_for_ranking": True,
                    "source_mutations": [],
                    "snapshot_mutations": [],
                    "external_accesses": [],
                },
            }
            (case_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
            event = {
                "type": "tool_execution_start",
                "toolCallId": "outside",
                "toolName": "bash",
                "args": {"command": "cd /tmp && curl https://example.invalid/input"},
            }
            (case_dir / "pi-events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")

            report = write_report(run_dir)

            self.assertEqual([], report["leaderboard"])
            self.assertEqual(["escaped"], report["integrity"]["disqualified_models"])
            details = report["integrity"]["violations"][0]["details"]
            self.assertEqual(
                {"shell_path_outside_workspace", "shell_network_attempt"},
                {item["reason"] for item in details},
            )
            markdown = (run_dir / "REPORT.md").read_text(encoding="utf-8")
            self.assertIn("### Violazioni rilevate", markdown)
            self.assertIn("shell_network_attempt", markdown)

    def test_reaudit_replaces_a_stale_manifest_false_positive(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "results" / "run"
            case_dir = run_dir / "models" / "clean" / "cases" / "case-r1"
            workspace = case_dir / "workspace"
            workspace.mkdir(parents=True)
            stale_violation = {
                "model": "clean",
                "case_id": "case",
                "repetition": 1,
                "kind": "external_workspace_access",
                "details": [{"reason": "shell_parent_traversal", "target": ".."}],
            }
            (run_dir / "run.json").write_text(
                json.dumps(
                    {
                        "task_order": [{"model": "clean", "case_id": "case", "repetition": 1}],
                        "integrity": {"status": "violations_detected", "violations": [stale_violation]},
                    }
                ),
                encoding="utf-8",
            )
            result = {
                "model": "clean",
                "case_id": "case",
                "case_weight": 1,
                "repetition": 1,
                "status": "ok",
                "duration_seconds": 10,
                "metrics": {"usage": {"output": 10}},
                "grade": {"score": 90},
                "integrity": {
                    "audit_version": 3,
                    "valid_for_ranking": False,
                    "source_mutations": [],
                    "snapshot_mutations": [],
                    "external_accesses": stale_violation["details"],
                },
            }
            (case_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
            safe_event = {
                "type": "tool_execution_start",
                "toolCallId": "scratch-test",
                "toolName": "bash",
                "args": {
                    "command": (
                        'WS="$PWD/.benchmark-scratch/smoke"\n'
                        'cd "$WS" && python3 -m tinyjournal export note.txt ../fuori.md'
                    )
                },
            }
            (case_dir / "pi-events.jsonl").write_text(json.dumps(safe_event) + "\n", encoding="utf-8")

            report = write_report(run_dir)

            self.assertEqual("passed", report["integrity"]["status"])
            self.assertEqual([], report["integrity"]["violations"])
            self.assertEqual(["clean"], [row["model"] for row in report["leaderboard"]])
            self.assertEqual(3, json.loads((case_dir / "result.json").read_text())["integrity"]["audit_version"])


if __name__ == "__main__":
    unittest.main()
