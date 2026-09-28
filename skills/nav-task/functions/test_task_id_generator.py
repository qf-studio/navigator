#!/usr/bin/env python3
"""Tests for task_id_generator.py — local counter and GitHub-issue IDs (GH-32)."""

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
from task_id_generator import (LOCAL, GITHUB, create_github_task_id, get_next_task_id, main,
                               parse_issue_number, read_task_id_source)

SCRIPT = Path(__file__).parent / "task_id_generator.py"


class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class LocalCounterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.agent = Path(self.tmp.name) / ".agent"
        (self.agent / "tasks").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_id(self):
        self.assertEqual(get_next_task_id(str(self.agent)), "TASK-01")

    def test_next_after_existing_and_gh_docs_do_not_interfere(self):
        for name in ("TASK-05-a.md", "TASK-12.md", "GH-99-other.md", "README.md"):
            (self.agent / "tasks" / name).write_text("#")
        self.assertEqual(get_next_task_id(str(self.agent)), "TASK-13")

    def test_source_defaults_to_local_without_config(self):
        self.assertEqual(read_task_id_source(str(self.agent)), LOCAL)

    def test_source_reads_config_and_rejects_unknown(self):
        cfg = self.agent / ".nav-config.json"
        cfg.write_text(json.dumps({"task_id_source": "github"}))
        self.assertEqual(read_task_id_source(str(self.agent)), GITHUB)
        cfg.write_text(json.dumps({"task_id_source": "jira"}))
        self.assertEqual(read_task_id_source(str(self.agent)), LOCAL)


class GitHubIdTest(unittest.TestCase):
    def test_parse_issue_number_from_url(self):
        self.assertEqual(parse_issue_number("Creating issue in o/r\n\nhttps://github.com/o/r/issues/57\n"), 57)
        self.assertIsNone(parse_issue_number("nothing here"))

    def test_creates_issue_and_returns_gh_id(self):
        calls = []

        def runner(cmd, **kw):
            calls.append(cmd)
            return _Proc(0, "https://github.com/o/r/issues/57\n")

        task_id, url = create_github_task_id("Add OAuth", "body", labels=["pilot"],
                                             runner=runner)
        self.assertEqual(task_id, "GH-57")
        self.assertEqual(url, "https://github.com/o/r/issues/57")
        cmd = calls[0]
        self.assertEqual(cmd[:3], ["gh", "issue", "create"])
        self.assertEqual(cmd[cmd.index("--title") + 1], "Add OAuth")
        self.assertEqual(cmd[cmd.index("--label") + 1], "pilot")

    def test_gh_failure_raises_no_silent_local_fallback(self):
        with self.assertRaises(RuntimeError):
            create_github_task_id("x", runner=lambda cmd, **kw: _Proc(1, "", "auth required"))

    def test_missing_title_rejected(self):
        with self.assertRaises(ValueError):
            create_github_task_id("   ", runner=lambda cmd, **kw: _Proc(0, ""))

    def test_missing_gh_binary_is_a_clear_error(self):
        def runner(cmd, **kw):
            raise FileNotFoundError("gh")
        with self.assertRaises(RuntimeError) as ctx:
            create_github_task_id("x", runner=runner)
        self.assertIn("gh CLI not found", str(ctx.exception))


class CLITest(unittest.TestCase):
    """End-to-end through the CLI with a fake ``gh`` on PATH."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.agent = root / ".agent"
        (self.agent / "tasks").mkdir(parents=True)
        (self.agent / "tasks" / "TASK-03-x.md").write_text("#")
        self.bin = root / "bin"
        self.bin.mkdir()
        fake = self.bin / "gh"
        fake.write_text("#!/bin/sh\necho \"$@\" > \"$FAKE_GH_LOG\"\n"
                        "echo https://github.com/o/r/issues/41\n")
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        self.log = root / "gh.log"
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ.get('PATH', '')}",
                        FAKE_GH_LOG=str(self.log))

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True,
                              text=True, env=self.env)

    def test_legacy_positional_local(self):
        proc = self.run_cli(str(self.agent), "TASK")
        self.assertEqual(proc.stdout.strip(), "TASK-04")

    def test_auto_uses_config_github(self):
        (self.agent / ".nav-config.json").write_text(json.dumps({"task_id_source": "github"}))
        proc = self.run_cli("--agent-dir", str(self.agent), "--title", "Add OAuth",
                            "--label", "pilot", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out, {"id": "GH-41", "source": "github",
                               "url": "https://github.com/o/r/issues/41"})
        self.assertIn("--title Add OAuth", self.log.read_text())
        self.assertIn("--label pilot", self.log.read_text())

    def test_auto_stays_local_when_config_says_local(self):
        (self.agent / ".nav-config.json").write_text(json.dumps({"task_id_source": "local"}))
        proc = self.run_cli("--agent-dir", str(self.agent), "--title", "ignored")
        self.assertEqual(proc.stdout.strip(), "TASK-04")
        self.assertFalse(self.log.exists())

    def test_github_without_title_fails_loudly(self):
        proc = self.run_cli("--agent-dir", str(self.agent), "--source", "github")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("--title", proc.stderr)


if __name__ == "__main__":
    unittest.main()
