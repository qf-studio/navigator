#!/usr/bin/env python3
"""Tests for feature_manager.py — personal override layering (GH-30).

The shared .agent/.nav-config.json is committed; .agent/.nav-config.local.json
merges over it and is never shared. ``--local`` writes there; ``show`` marks
rows the override decides with ``L``.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from feature_manager import (LOCAL_CONFIG_PATH, is_feature_enabled, is_locally_overridden,
                             merge_config, show_features)

SCRIPT = Path(__file__).parent / "feature_manager.py"


class MergeTest(unittest.TestCase):
    def test_local_scalar_wins_sibling_kept(self):
        merged = merge_config({"judge": {"enabled": True, "model": "jev-latest"}},
                              {"judge": {"enabled": False}})
        self.assertIs(merged["judge"]["enabled"], False)
        self.assertEqual(merged["judge"]["model"], "jev-latest")

    def test_merge_does_not_mutate_inputs(self):
        shared = {"judge": {"enabled": True}}
        merge_config(shared, {"judge": {"enabled": False}})
        self.assertIs(shared["judge"]["enabled"], True)

    def test_empty_local_is_identity(self):
        shared = {"version": "7.7.1", "loop_mode": {"enabled": False}}
        self.assertEqual(merge_config(shared, {}), shared)

    def test_is_locally_overridden_only_when_enabled_key_present(self):
        self.assertTrue(is_locally_overridden({"judge": {"enabled": False}}, "judge"))
        self.assertFalse(is_locally_overridden({"judge": {"model": "x"}}, "judge"))
        self.assertFalse(is_locally_overridden({}, "judge"))
        self.assertFalse(is_locally_overridden({"judge": True}, "judge"))


class ShowTest(unittest.TestCase):
    def test_marks_local_rows_and_adds_legend(self):
        shared = {"version": "7.7.1", "judge": {"enabled": True}}
        local = {"judge": {"enabled": False}}
        out = show_features(merge_config(shared, local), local=local)
        judge_row = next(line for line in out.splitlines() if "│ judge " in line)
        self.assertIn("[ ] L", judge_row)
        self.assertIn(f"L = personal override from {LOCAL_CONFIG_PATH}", out)

    def test_no_legend_without_override(self):
        out = show_features({"version": "7.7.1"}, local={})
        self.assertNotIn("personal override", out)
        self.assertNotIn(" L ", out)


class CLITest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".agent").mkdir()
        self.shared = self.root / ".agent" / ".nav-config.json"
        self.local = self.root / ".agent" / LOCAL_CONFIG_PATH.split("/")[-1]
        self.shared.write_text(json.dumps({"version": "7.7.1", "judge": {"enabled": True}}))

    def tearDown(self):
        self.tmp.cleanup()

    def run_fm(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True)

    def test_disable_local_writes_only_the_local_file(self):
        proc = self.run_fm("disable", "judge", "--local")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(self.local.read_text()), {"judge": {"enabled": False}})
        self.assertIs(json.loads(self.shared.read_text())["judge"]["enabled"], True)
        self.assertIn("personal override written", proc.stdout)

    def test_show_reflects_local_override(self):
        self.local.write_text(json.dumps({"judge": {"enabled": False}}))
        proc = self.run_fm("show")
        judge_row = next(line for line in proc.stdout.splitlines() if "│ judge " in line)
        self.assertIn("[ ] L", judge_row)

    def test_shared_toggle_warns_when_local_still_overrides(self):
        self.local.write_text(json.dumps({"judge": {"enabled": False}}))
        proc = self.run_fm("enable", "judge")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("still overrides this feature", proc.stdout)
        self.assertIs(json.loads(self.shared.read_text())["judge"]["enabled"], True)

    def test_absent_local_file_changes_nothing(self):
        proc = self.run_fm("show")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("personal override", proc.stdout)
        self.assertFalse(self.local.exists())

    def test_corrupt_local_file_is_ignored_with_warning(self):
        self.local.write_text("{nope")
        proc = self.run_fm("show")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("ignoring the personal override", proc.stderr)


if __name__ == "__main__":
    unittest.main()
