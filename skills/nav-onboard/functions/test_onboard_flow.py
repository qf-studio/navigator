#!/usr/bin/env python3
"""nav-onboard runs as SKILL.md documents it, and its exercises never touch the repo (GH-35).

Covers: the recommender → tracker → validator path on a fresh nav-init-shaped project using
the documented one-line CLI forms; curriculum ``task_file`` names resolve to files in
``learning-tasks/``; the philosophy entry points at the plugin's copy; the practice sandbox
with ``task_id_source: github`` never calls ``gh`` (a fake ``gh`` on PATH fails the test if
it runs) and leaves ``git status`` unchanged.
"""

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

FUNCTIONS = Path(__file__).resolve().parent
sys.path.insert(0, str(FUNCTIONS))
from onboarding_paths import ENV_OVERRIDE, onboarding_dir  # noqa: E402
from practice import PRACTICE_SKILLS, practice_root, run_practice  # noqa: E402
from skill_recommender import LEARNING_TASKS_DIR, recommend_skills, task_file_for  # noqa: E402
from task_validator import validate_task  # noqa: E402

PY = sys.executable
RECOMMENDER = FUNCTIONS / "skill_recommender.py"
ANALYZER = FUNCTIONS / "project_analyzer.py"
TRACKER = FUNCTIONS / "progress_tracker.py"
VALIDATOR = FUNCTIONS / "task_validator.py"
PRACTICE = FUNCTIONS / "practice.py"
EXERCISES = ("nav-marker", "nav-task", "nav-sop", "nav-compact")


def _run(args, cwd, env=None, stdin=None):
    return subprocess.run([PY, *args], cwd=cwd, env=env, input=stdin,
                          capture_output=True, text=True)


def _tree_digest(root: Path) -> dict:
    """Relative path → content hash for every file under root (excluding .git)."""
    digest = {}
    for path in root.rglob("*"):
        if ".git" in path.parts or not path.is_file():
            continue
        digest[str(path.relative_to(root))] = hashlib.sha1(path.read_bytes()).hexdigest()
    return digest


class _FreshProject(unittest.TestCase):
    """A nav-init-shaped repo in a temp dir, onboarding state in a throwaway home."""

    def setUp(self):
        self.project = Path(tempfile.mkdtemp()).resolve()
        self.home = tempfile.mkdtemp()
        self._env = mock.patch.dict(os.environ, {ENV_OVERRIDE: self.home})
        self._env.start()
        agent = self.project / ".agent"
        (agent / "tasks").mkdir(parents=True)
        (agent / "sops" / "debugging").mkdir(parents=True)
        (agent / "DEVELOPMENT-README.md").write_text("# Navigator\n")
        (agent / "tasks" / "TASK-04-old.md").write_text("# TASK-04: old\n")
        self.write_config({"version": "8.4.3", "task_prefix": "TASK",
                           "task_id_source": "local", "project_management": "none"})
        (self.project / "package.json").write_text(json.dumps({
            "name": "demo-app", "dependencies": {"react": "18", "express": "4"},
            "devDependencies": {"jest": "29"}}))
        self.env = dict(os.environ)

    def write_config(self, config: dict):
        (self.project / ".agent" / ".nav-config.json").write_text(json.dumps(config))

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.project, ignore_errors=True)
        shutil.rmtree(self.home, ignore_errors=True)


class CurriculumFilesExist(unittest.TestCase):
    def _analysis(self, project_type, **extra):
        base = {"project_type": project_type, "project_name": "x", "database": None,
                "has_storybook": False, "has_figma_mcp": False}
        base.update(extra)
        return base

    def test_every_curriculum_task_file_exists_on_disk(self):
        for project_type in ("frontend", "backend", "fullstack", "unknown"):
            rec = recommend_skills(self._analysis(project_type, database="PostgreSQL"))
            for flow, entries in rec["curriculum"].items():
                for entry in entries:
                    if entry.get("skill") is None:
                        continue
                    with self.subTest(project_type=project_type, flow=flow, skill=entry["skill"]):
                        self.assertIsNotNone(entry["task_file"])
                        self.assertTrue((LEARNING_TASKS_DIR / entry["task_file"]).is_file(),
                                        entry["task_file"])

    def test_essential_files_follow_the_numbering_on_disk(self):
        self.assertEqual(task_file_for("nav-marker"), "02-nav-marker.md")
        self.assertEqual(task_file_for("nav-task"), "03-nav-task.md")
        self.assertEqual(task_file_for("nav-sop"), "04-nav-sop.md")
        self.assertEqual(task_file_for("nav-compact"), "05-nav-compact.md")
        self.assertEqual(task_file_for("frontend-component", "development"), "06-dev-skill.md")
        self.assertIsNone(task_file_for("no-such-skill"))

    def test_quick_start_teaches_start_marker_task_in_that_order(self):
        rec = recommend_skills(self._analysis("backend"))
        skills = [e["skill"] for e in rec["curriculum"]["quick_start"]]
        self.assertEqual(skills[:3], ["nav-start", "nav-marker", "nav-task"])
        self.assertEqual(skills[3], "backend-endpoint")

    def test_philosophy_reading_is_the_plugin_copy(self):
        rec = recommend_skills(self._analysis("frontend"))
        philosophy = rec["curriculum"]["full_education"][0]
        self.assertEqual(philosophy["section"], "Philosophy")
        self.assertTrue(Path(philosophy["file"]).is_absolute())
        self.assertTrue(Path(philosophy["file"]).is_file(), philosophy["file"])
        self.assertIn("philosophy", philosophy["file"])


class RecommenderCli(_FreshProject):
    def test_runs_with_no_input_as_documented(self):
        proc = _run([RECOMMENDER], cwd=self.project, env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rec = json.loads(proc.stdout)
        self.assertEqual(rec["project_type"], "fullstack")
        self.assertIn("nav-start", rec["essential_skills"])

    def test_accepts_the_analyzer_on_stdin(self):
        analysis = _run([ANALYZER], cwd=self.project, env=self.env).stdout
        proc = _run([RECOMMENDER, "--analysis", "-"], cwd=self.project, env=self.env,
                    stdin=analysis)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["project_type"], "fullstack")

    def test_reports_a_project_tutorial_when_the_repo_ships_one(self):
        self.assertIsNone(json.loads(_run([RECOMMENDER], cwd=self.project,
                                          env=self.env).stdout)["project_tutorial"])
        (self.project / ".agent" / "ONBOARDING.md").write_text("# Team tutorial\n")
        rec = json.loads(_run([RECOMMENDER], cwd=self.project, env=self.env).stdout)
        self.assertTrue(rec["project_tutorial"].endswith(".agent/ONBOARDING.md"))


class TrackerCli(_FreshProject):
    def test_init_with_only_the_flow_as_documented(self):
        proc = _run([TRACKER, "init", "quick_start"], cwd=self.project, env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads((onboarding_dir(self.project) / ".progress-data.json").read_text())
        self.assertEqual(data["project_type"], "fullstack")
        self.assertEqual(data["project_name"], "demo-app")
        self.assertEqual(data["essential_skills"], ["nav-start", "nav-marker", "nav-task"])
        self.assertEqual(len(data["development_skills"]), 1)

    def test_init_accepts_a_bare_skill_list(self):
        proc = _run([TRACKER, "init", "full_education", "python", "--project-name", "p",
                     "--skills", '["nav-start", "nav-compact"]'],
                    cwd=self.project, env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads((onboarding_dir(self.project) / ".progress-data.json").read_text())
        self.assertEqual(data["essential_skills"], ["nav-start", "nav-compact"])
        self.assertEqual(data["project_type"], "python")

    def test_update_and_next_use_the_documented_forms(self):
        _run([TRACKER, "init", "quick_start"], cwd=self.project, env=self.env)
        proc = _run([TRACKER, "update", "nav-start", "completed", "shown"],
                    cwd=self.project, env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["next_task"], "nav-marker")
        nxt = _run([TRACKER, "next"], cwd=self.project, env=self.env)
        self.assertEqual(nxt.stdout.strip(), "nav-marker")
        bad = _run([TRACKER, "update", "nope", "completed"], cwd=self.project, env=self.env)
        self.assertEqual(bad.returncode, 1)

    def test_project_dir_flag_works_from_elsewhere(self):
        proc = _run([TRACKER, "--project-dir", str(self.project), "init", "quick_start"],
                    cwd=tempfile.gettempdir(), env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((onboarding_dir(self.project) / "PROGRESS.md").exists())


class QuickStartEndToEnd(_FreshProject):
    """Recommender → tracker → practice → validator, repo byte-identical afterwards."""

    def test_quick_start_runs_end_to_end_and_leaves_the_repo_untouched(self):
        before = _tree_digest(self.project)
        rec = json.loads(_run([RECOMMENDER], cwd=self.project, env=self.env).stdout)
        self.assertEqual(_run([TRACKER, "init", "quick_start"], cwd=self.project,
                              env=self.env).returncode, 0)
        for entry in rec["curriculum"]["quick_start"]:
            skill = entry["skill"]
            self.assertTrue((LEARNING_TASKS_DIR / entry["task_file"]).is_file())
            if skill in PRACTICE_SKILLS:
                run = _run([PRACTICE, "run", skill], cwd=self.project, env=self.env)
                self.assertEqual(run.returncode, 0, run.stderr)
                result = json.loads(run.stdout)
                self.assertTrue(result["repo_untouched"])
                for created in result["created"]:
                    self.assertTrue(created.startswith(str(practice_root(self.project))))
                check = _run([VALIDATOR, skill, "--practice"], cwd=self.project, env=self.env)
                self.assertEqual(check.returncode, 0, check.stdout)
                self.assertEqual(json.loads(check.stdout)["mode"], "practice")
            upd = _run([TRACKER, "update", skill, "completed"], cwd=self.project, env=self.env)
            self.assertEqual(upd.returncode, 0, upd.stderr)
        self.assertEqual(_run([TRACKER, "next"], cwd=self.project, env=self.env).stdout.strip(),
                         "complete")
        self.assertEqual(_tree_digest(self.project), before)
        self.assertEqual(_run([PRACTICE, "clean"], cwd=self.project, env=self.env).returncode, 0)
        self.assertFalse(practice_root(self.project).exists())

    def test_validator_fails_before_the_exercise_and_passes_after(self):
        for skill in EXERCISES:
            with self.subTest(skill=skill):
                self.assertFalse(validate_task(str(self.project), skill, practice=True)["valid"])
                run_practice(str(self.project), skill)
                self.assertTrue(validate_task(str(self.project), skill, practice=True)["valid"])

    def test_practice_task_id_is_the_next_local_id(self):
        result = run_practice(str(self.project), "nav-task")
        self.assertIn("TASK-05-learning-feature.md", result["created"][0])
        self.assertIsNone(result["would_create_issue"])
        real_doc = self.project / ".agent" / "tasks" / "TASK-05-learning-feature.md"
        self.assertFalse(real_doc.exists())


class GithubSourceNeverCallsGh(_FreshProject):
    def setUp(self):
        super().setUp()
        self.write_config({"task_prefix": "TASK", "task_id_source": "github"})
        self.bin = Path(tempfile.mkdtemp())
        self.sentinel = self.bin / "gh-was-called"
        fake_gh = self.bin / "gh"
        fake_gh.write_text(f"#!/bin/sh\necho called > '{self.sentinel}'\n"
                           "echo https://github.com/x/y/issues/999\n")
        fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IEXEC)
        self.env["PATH"] = f"{self.bin}{os.pathsep}{self.env.get('PATH', '')}"
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"],
                       cwd=self.project, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm",
                        "init"], cwd=self.project, check=True)

    def tearDown(self):
        shutil.rmtree(self.bin, ignore_errors=True)
        super().tearDown()

    def _git_status(self):
        return subprocess.run(["git", "status", "--porcelain"], cwd=self.project,
                              capture_output=True, text=True).stdout

    def test_fake_gh_is_the_one_on_path(self):
        proc = subprocess.run(["gh", "issue", "create"], env=self.env, capture_output=True,
                              text=True)
        self.assertIn("issues/999", proc.stdout)
        self.sentinel.unlink()

    def test_nav_task_exercise_shows_the_issue_and_does_not_create_it(self):
        self.assertEqual(self._git_status(), "")
        run = _run([PRACTICE, "run", "nav-task"], cwd=self.project, env=self.env)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertFalse(self.sentinel.exists(), "practice mode ran gh")
        self.assertEqual(result["would_create_issue"]["title"], "Learning feature")
        self.assertIn("GH-NEW-learning-feature.md", result["created"][0])
        check = _run([VALIDATOR, "nav-task", "--practice"], cwd=self.project, env=self.env)
        self.assertEqual(check.returncode, 0, check.stdout)
        self.assertEqual(self._git_status(), "")

    def test_all_exercises_leave_git_status_clean(self):
        for skill in EXERCISES:
            run = _run([PRACTICE, "run", skill], cwd=self.project, env=self.env)
            self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse(self.sentinel.exists())
        self.assertEqual(self._git_status(), "")
        self.assertFalse((self.project / ".agent" / ".context-markers").exists())

    def test_practice_module_cannot_spawn_processes(self):
        source = PRACTICE.read_text()
        self.assertNotIn("subprocess", source)
        self.assertNotIn("os.system", source)


if __name__ == "__main__":
    unittest.main()
