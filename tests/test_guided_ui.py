from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localagent_bench.guided_ui import (
    TEXT,
    THEME_PALETTES,
    _completed_task_progress,
    _sorted_model_indices,
    _summary,
    load_preferences,
    save_preferences,
)


class GuidedUiTests(unittest.TestCase):
    def test_progress_counts_completed_tasks_within_each_stage(self):
        self.assertEqual(0.0, _completed_task_progress(1, 1, 4))
        self.assertEqual(0.5, _completed_task_progress(1, 3, 4))
        self.assertEqual(1.0, _completed_task_progress(2, 1, 4))
        self.assertEqual(1.5, _completed_task_progress(2, 3, 4))
        self.assertEqual(2.5, _completed_task_progress(3, 2, 2))
        self.assertEqual(0.0, _completed_task_progress(0, 1, 2))
        self.assertEqual(0.0, _completed_task_progress(1, 1, 0))

    def test_theme_palette_keeps_controls_and_progress_legible(self):
        def luminance(color: str) -> float:
            channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
            linear = [
                channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
                for channel in channels
            ]
            return sum(channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

        def contrast(first: str, second: str) -> float:
            values = sorted((luminance(first), luminance(second)))
            return (values[1] + 0.05) / (values[0] + 0.05)

        for theme, palette in THEME_PALETTES.items():
            with self.subTest(theme=theme):
                self.assertGreaterEqual(contrast(palette["foreground"], palette["surface"]), 4.5)
                self.assertGreaterEqual(contrast(palette["selection_text"], palette["selection"]), 4.5)
                self.assertGreaterEqual(contrast(palette["disabled_foreground"], palette["disabled_background"]), 4.5)
                self.assertGreaterEqual(contrast(palette["accent"], palette["progress_track"]), 3)

    def test_translations_remain_synchronized(self):
        self.assertEqual(set(TEXT["it"]), set(TEXT["en"]))

    def test_model_sorting_is_numeric_stable_and_keeps_unknown_values_last(self):
        models = [
            {"name": "zeta", "size": 2, "thinking_capable": False},
            {"name": "Alpha", "size": 10, "thinking_capable": True},
            {"name": "middle", "size": None, "thinking_capable": None},
        ]

        def names(column, descending=False):
            return [
                models[index]["name"]
                for index in _sorted_model_indices(models, column, descending)
            ]

        self.assertEqual(["Alpha", "middle", "zeta"], names("name"))
        self.assertEqual(["zeta", "Alpha", "middle"], names("size"))
        self.assertEqual(["Alpha", "zeta", "middle"], names("size", True))
        self.assertEqual(["zeta", "Alpha", "middle"], names("thinking"))
        self.assertEqual(["Alpha", "zeta", "middle"], names("thinking", True))
        with self.assertRaises(ValueError):
            _sorted_model_indices(models, "unsupported", False)

    def test_preferences_round_trip_and_reject_unknown_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "preferences.json"
            root = Path(directory)
            save_preferences(path, {"language": "it", "theme": "dark"}, root=root)
            self.assertEqual(
                {"language": "it", "theme": "dark"}, load_preferences(path, root=root)
            )
            path.write_text('{"language":"xx","theme":"light","secret":"ignored"}', encoding="utf-8")
            self.assertEqual({"theme": "light"}, load_preferences(path, root=root))
            with self.assertRaisesRegex(ValueError, "non valide"):
                save_preferences(path, {"language": "xx", "theme": "light"}, root=root)
            with tempfile.TemporaryDirectory() as outside:
                with self.assertRaisesRegex(ValueError, "root del progetto"):
                    save_preferences(
                        Path(outside) / "preferences.json",
                        {"language": "it", "theme": "light"},
                        root=root,
                    )

    def test_source_launchers_exist_and_do_not_embed_absolute_checkout_paths(self):
        launchers = (
            ROOT / "launchers" / "LocalAgent-Benchmark.command",
            ROOT / "launchers" / "LocalAgent-Benchmark.cmd",
            ROOT / "launchers" / "LocalAgent-Benchmark.sh",
        )
        for launcher in launchers:
            with self.subTest(launcher=launcher.name):
                content = launcher.read_text(encoding="utf-8")
                self.assertIn("guided_benchmark.py", content)
                self.assertNotIn(str(ROOT), content)
        if sys.platform != "win32":
            self.assertTrue(launchers[0].stat().st_mode & 0o111)
            self.assertTrue(launchers[2].stat().st_mode & 0o111)

    def test_completion_summary_is_bilingual_and_lists_runs_and_exclusions(self):
        payload = {
            "phases": [
                {
                    "profile": "smoke",
                    "leaderboard": [{"model": "alpha", "overall_score": 91}],
                    "promoted": ["alpha"],
                    "exclusions": [{"model": "beta", "reason": "integrity"}],
                }
            ],
            "dashboard": {
                "run_directories": [
                    "results/guided/session/smoke",
                    "results/guided/session/standard",
                    "results/guided/session/full",
                ]
            },
        }
        summary = _summary(payload)
        self.assertIn("Italiano", summary)
        self.assertIn("English", summary)
        self.assertIn("promossi alpha", summary)
        self.assertIn("promoted alpha", summary)
        self.assertIn("beta [integrity]", summary)
        self.assertIn("results/guided/session/full", summary)


if __name__ == "__main__":
    unittest.main()
