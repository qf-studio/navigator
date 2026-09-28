#!/usr/bin/env python3
"""Tests for progress_tracker.py corrupt/partial-data resilience.

Covers the wp11/TASK-51 fix: reading a corrupt or partial
.progress-data.json must return an {"error": ...} dict (or None for
get_next_task) instead of raising JSONDecodeError/KeyError.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
from onboarding_paths import ENV_OVERRIDE, onboarding_dir, repo_id
from progress_tracker import init_progress, update_progress, get_progress, get_next_task
from workflow_generator import generate_workflow


class _IsolatedHome(unittest.TestCase):
    """Route per-person onboarding state into a throwaway home (GH-31)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.home = tempfile.mkdtemp()
        self._env = mock.patch.dict(os.environ, {ENV_OVERRIDE: self.home})
        self._env.start()
        self.onboarding = onboarding_dir(self.tmp)
        self.onboarding.mkdir(parents=True)
        self.data_file = self.onboarding / ".progress-data.json"

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.home, ignore_errors=True)


class TestOnboardingPaths(_IsolatedHome):
    def test_state_lives_outside_the_repo(self):
        self.assertTrue(str(self.onboarding).startswith(self.home))
        self.assertFalse(str(self.onboarding).startswith(self.tmp))

    def test_two_repos_get_separate_dirs(self):
        other = tempfile.mkdtemp()
        try:
            self.assertNotEqual(onboarding_dir(self.tmp), onboarding_dir(other))
        finally:
            shutil.rmtree(other, ignore_errors=True)

    def test_repo_id_is_stable_and_keyed_by_realpath(self):
        self.assertEqual(repo_id(self.tmp), repo_id(self.tmp + "/"))
        self.assertIn(Path(self.tmp).name[:40], repo_id(self.tmp))

    def test_default_home_is_under_config_when_unset(self):
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/tmp/xdg-test"}, clear=False):
            os.environ.pop(ENV_OVERRIDE, None)
            self.assertEqual(str(onboarding_dir(self.tmp)),
                             f"/tmp/xdg-test/navigator/onboarding/{repo_id(self.tmp)}")

    def test_init_and_workflow_write_nothing_under_project(self):
        init_progress(self.tmp, "quick_start", "python", "demo",
                      {"essential_skills": ["nav-start"], "recommended_skills": []})
        generate_workflow(self.tmp, {"project_name": "demo", "project_type": "python"},
                          {"essential_skills": [], "recommended_skills": [],
                           "optional_skills": [], "workflow_order": []})
        self.assertFalse((Path(self.tmp) / ".agent").exists())
        self.assertTrue((self.onboarding / "PROGRESS.md").exists())
        self.assertTrue((self.onboarding / "MY-WORKFLOW.md").exists())

    def test_update_regenerates_markdown_with_next_task(self):
        init_progress(self.tmp, "quick_start", "python", "demo",
                      {"essential_skills": [], "recommended_skills": []})
        out = update_progress(self.tmp, "nav-start", "completed")
        self.assertEqual(out["next_task"], "nav-marker")
        self.assertIn("**Next Task**: nav-marker", (self.onboarding / "PROGRESS.md").read_text())


class TestProgressTrackerResilience(_IsolatedHome):

    def _write(self, text: str):
        self.data_file.write_text(text)

    # --- corrupt (invalid JSON) ---------------------------------------

    def test_corrupt_get_progress_returns_error(self):
        self._write("{ this is not valid json")
        result = get_progress(self.tmp)
        self.assertIn("error", result)

    def test_corrupt_update_progress_returns_error(self):
        self._write("}{ broken")
        result = update_progress(self.tmp, "nav-start", "completed")
        self.assertIn("error", result)

    def test_corrupt_get_next_task_returns_none(self):
        self._write("not json at all")
        self.assertIsNone(get_next_task(self.tmp))

    # --- partial (valid JSON, missing required keys) ------------------

    def test_partial_data_does_not_crash(self):
        self._write(json.dumps({"flow_type": "quick_start"}))
        # All three must tolerate the missing 'progress'/'total' keys.
        prog = get_progress(self.tmp)
        self.assertIsInstance(prog, dict)
        self.assertEqual(prog.get("percentage"), 0)

        self.assertIsNone(get_next_task(self.tmp))

        upd = update_progress(self.tmp, "nav-start", "completed")
        self.assertIn("error", upd)  # unknown skill, not a KeyError crash


if __name__ == "__main__":
    unittest.main()
