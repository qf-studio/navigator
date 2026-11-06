#!/usr/bin/env python3
"""Tests for ops/task_doc_guard.py — GH-40.

Covers the gate (Write/Edit/Bash into a NEW ``.agent/tasks/TASK-<n>*.md``
without ``/nav-task`` this session → exit 2 + sentinel stderr naming the
file), the Skill recorder branch, the exemptions (existing doc, other
directories, archive, other names), ``strict_block: false`` (advisory, exit 0),
the Pilot executor passthrough, and the end-to-end session scope of the
``skills`` state section through runtime.dispatch.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))          # this dir
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # hooks/ (nav_hook_lib)

import task_doc_guard
from nav_hook_lib import config, runtime, sentinels, state

SESSION_ID = "sess-task-doc-guard-tests"
NOW = 1_700_000_000.0

BLOCK_OPEN = sentinels.TAGS["nav-task-doc-guard-block"]["open"]
BLOCK_CLOSE = sentinels.TAGS["nav-task-doc-guard-block"]["close"]

NEW_DOC = "TASK-99-x.md"


class TaskDocGuardTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve() / "project"
        self.tasks = self.root / ".agent" / "tasks"
        self.tasks.mkdir(parents=True)
        self._saved_env = {
            key: os.environ.pop(key, None)
            for key in ("CLAUDE_PROJECT_DIR", "PILOT_EXECUTOR", "NAVIGATOR_MOD_OWNS")
        }
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        for key, value in self._saved_env.items():
            if value is not None:
                os.environ[key] = value

    # -- helpers ----------------------------------------------------------

    def write_config(self, cfg):
        (self.root / ".agent" / ".nav-config.json").write_text(
            json.dumps(cfg), encoding="utf-8")

    def payload(self, tool_name, session_id=SESSION_ID, **tool_input):
        return {
            "cwd": str(self.root),
            "session_id": session_id,
            "tool_name": tool_name,
            "tool_input": tool_input,
        }

    def write_payload(self, rel=f".agent/tasks/{NEW_DOC}", tool_name="Write"):
        return self.payload(tool_name, file_path=str(self.root / rel))

    def bash_payload(self, command):
        return self.payload("Bash", command=command)

    def skill_payload(self, skill="navigator:nav-task", session_id=SESSION_ID):
        return self.payload("Skill", session_id=session_id, skill=skill)

    def ctx(self, payload, state=None, pilot=False):
        return types.SimpleNamespace(
            event="PreToolUse",
            payload=payload,
            config=config.load(self.root),
            state=state if state is not None else {},
            pilot_executor=pilot,
            now=NOW,
        )

    def run_op(self, payload, **kwargs):
        return task_doc_guard.run(self.ctx(payload, **kwargs))

    def assertBlocked(self, result, name=NEW_DOC):
        self.assertIsNotNone(result)
        self.assertEqual(result["exit_code"], 2)
        stderr = result["stderr"]
        self.assertTrue(stderr.startswith(BLOCK_OPEN), stderr)
        self.assertTrue(stderr.rstrip().endswith(BLOCK_CLOSE), stderr)
        self.assertIn(name, stderr)
        self.assertIn("run /nav-task", stderr.replace("Run /nav-task", "run /nav-task"))
        # deny-only channel (mem-035/mem-054): no advisory stdout keys
        for key in ("additional_context", "permission_decision", "decision"):
            self.assertNotIn(key, result)

    def assertSilent(self, result):
        self.assertIn(result, (None, {}))


class GateTest(TaskDocGuardTestBase):
    def test_write_new_task_doc_without_skill_blocks(self):
        self.assertBlocked(self.run_op(self.write_payload()))

    def test_edit_of_missing_file_blocks_like_write(self):
        self.assertBlocked(self.run_op(self.write_payload(tool_name="Edit")))

    def test_write_after_nav_task_skill_passes(self):
        st = {}
        self.assertSilent(self.run_op(self.skill_payload(), state=st))
        self.assertTrue(st["skills"]["nav_task_ran"])
        self.assertSilent(self.run_op(self.write_payload(), state=st))

    def test_bare_skill_name_also_counts(self):
        st = {}
        self.run_op(self.skill_payload(skill="nav-task"), state=st)
        self.assertTrue(st["skills"]["nav_task_ran"])

    def test_other_skill_does_not_count(self):
        st = {}
        self.run_op(self.skill_payload(skill="navigator:nav-start"), state=st)
        self.assertNotIn("skills", st)
        self.assertBlocked(self.run_op(self.write_payload(), state=st))

    def test_edit_of_existing_doc_passes(self):
        (self.tasks / NEW_DOC).write_text("# existing\n", encoding="utf-8")
        self.assertSilent(self.run_op(self.write_payload(tool_name="Edit")))
        self.assertSilent(self.run_op(self.write_payload(tool_name="Write")))

    def test_path_outside_tasks_dir_passes(self):
        for rel in (f"docs/{NEW_DOC}", f".agent/sops/{NEW_DOC}", f"{NEW_DOC}",
                    f".agent/tasks/archive/{NEW_DOC}"):
            with self.subTest(rel=rel):
                self.assertSilent(self.run_op(self.write_payload(rel)))

    def test_non_task_names_pass(self):
        for name in ("gh-40.md", "TASK-notes.md", "TASK-99-x.txt", "README.md"):
            with self.subTest(name=name):
                self.assertSilent(self.run_op(self.write_payload(f".agent/tasks/{name}")))

    def test_task_prefix_comes_from_config(self):
        self.write_config({"task_prefix": "GH"})
        self.assertBlocked(self.run_op(self.write_payload(".agent/tasks/GH-7-y.md")),
                           name="GH-7-y.md")
        self.assertSilent(self.run_op(self.write_payload()))  # TASK-99 no longer a task doc

    def test_relative_path_resolves_against_project_root(self):
        payload = self.payload("Write", file_path=f".agent/tasks/{NEW_DOC}")
        self.assertBlocked(self.run_op(payload))

    def test_dotdot_traversal_cannot_hide_the_target(self):
        payload = self.payload("Write", file_path=f"src/../.agent/tasks/{NEW_DOC}")
        self.assertBlocked(self.run_op(payload))

    def test_malformed_payloads_are_silent(self):
        for payload in ({"tool_name": "Write"},
                        {"tool_name": "Write", "tool_input": {"file_path": 7}},
                        {"tool_name": "Bash", "tool_input": {"command": None}},
                        {"tool_name": "Read", "tool_input": {}},
                        {"tool_name": "Skill", "tool_input": {"skill": None}}):
            with self.subTest(payload=payload):
                self.assertSilent(self.run_op(dict(payload, cwd=str(self.root))))

    def test_block_records_a_reject_without_the_tool_input(self):
        result = self.run_op(self.write_payload())
        self.assertEqual(result["reject"]["evidence"], {"tool": "Write", "file": NEW_DOC})


class BashTest(TaskDocGuardTestBase):
    PATH = f".agent/tasks/{NEW_DOC}"

    def test_heredoc_redirect_blocks(self):
        command = f"cat > {self.PATH} <<'EOF'\n# TASK-99\n\nbody\nEOF"
        self.assertBlocked(self.run_op(self.bash_payload(command)))

    def test_plain_and_append_redirects_block(self):
        for command in (f"echo hi > {self.PATH}", f"echo hi >> {self.PATH}",
                        f'echo hi >"{self.PATH}"', f"printf x 2>/dev/null >{self.PATH}"):
            with self.subTest(command=command):
                self.assertBlocked(self.run_op(self.bash_payload(command)))

    def test_tee_cp_mv_block(self):
        for command in (f"echo hi | tee {self.PATH}", f"echo hi | tee -a {self.PATH}",
                        f"cp /tmp/draft.md {self.PATH}", f"mv -f /tmp/draft.md {self.PATH}",
                        f"cd x && sudo cp /tmp/draft.md {self.PATH}"):
            with self.subTest(command=command):
                self.assertBlocked(self.run_op(self.bash_payload(command)))

    def test_absolute_target_blocks(self):
        command = f"cat > {self.root / self.PATH} <<EOF\nx\nEOF"
        self.assertBlocked(self.run_op(self.bash_payload(command)))

    def test_passes_after_nav_task(self):
        st = {"skills": {"nav_task_ran": True}}
        command = f"cat > {self.PATH} <<'EOF'\nx\nEOF"
        self.assertSilent(self.run_op(self.bash_payload(command), state=st))

    def test_existing_doc_and_other_targets_pass(self):
        (self.tasks / NEW_DOC).write_text("# existing\n", encoding="utf-8")
        for command in (f"echo hi >> {self.PATH}",
                        "echo hi > /tmp/out.txt",
                        f"cat {self.PATH}",
                        f"cp {self.PATH} /tmp/backup.md",
                        f"mv {self.PATH} .agent/tasks/archive/{NEW_DOC}",
                        "ls .agent/tasks | grep TASK-99",
                        "echo $X > $TASKS/TASK-99-x.md"):
            with self.subTest(command=command):
                self.assertSilent(self.run_op(self.bash_payload(command)))

    def test_text_inside_a_heredoc_body_is_data(self):
        command = f"cat > notes.md <<'EOF'\necho hi > {self.PATH}\nEOF"
        self.assertSilent(self.run_op(self.bash_payload(command)))

    def test_stderr_redirect_to_ampersand_fd_is_not_a_target(self):
        self.assertSilent(self.run_op(self.bash_payload("make test 2>&1 | tail")))


class StrictBlockTest(TaskDocGuardTestBase):
    def test_strict_block_false_is_an_advisory_exit_zero(self):
        self.write_config({"task_doc_guard_hook": {"strict_block": False}})
        result = self.run_op(self.write_payload())
        self.assertNotIn("exit_code", result)
        self.assertNotIn("reject", result)
        self.assertIn(NEW_DOC, result["stderr"])
        self.assertIn("/nav-task", result["stderr"])
        self.assertNotIn(BLOCK_OPEN, result["stderr"])

    def test_default_is_strict(self):
        self.assertEqual(config.get(config.load(self.root), "task_doc_guard_hook.strict_block"),
                         True)
        self.assertEqual(config.get(config.load(self.root), "task_doc_guard_hook.enabled"),
                         True)


class PilotExecutorTest(TaskDocGuardTestBase):
    def test_pilot_executor_is_silent_for_every_tool(self):
        st = {}
        for payload in (self.write_payload(), self.write_payload(tool_name="Edit"),
                        self.bash_payload(f"cat > .agent/tasks/{NEW_DOC} <<EOF\nx\nEOF"),
                        self.skill_payload()):
            with self.subTest(tool=payload["tool_name"]):
                self.assertIsNone(self.run_op(payload, state=st, pilot=True))
        self.assertEqual(st, {})  # not even the recorder branch runs


class DispatchSessionScopeTest(TaskDocGuardTestBase):
    """End-to-end through runtime.dispatch with real state persistence."""

    def dispatch(self, payload, now=NOW):
        return runtime.dispatch("PreToolUse", payload, now=now)

    def test_skill_then_write_in_the_same_session_passes(self):
        self.assertEqual(self.dispatch(self.skill_payload()).exit_code, 0)
        st = state.load(self.root / ".agent", session_id=SESSION_ID, now=NOW)
        self.assertTrue(st["skills"]["nav_task_ran"])
        self.assertEqual(self.dispatch(self.write_payload()).exit_code, 0)

    def test_write_without_skill_exits_two_with_the_block_text(self):
        res = self.dispatch(self.write_payload())
        self.assertEqual(res.exit_code, 2)
        self.assertIn(BLOCK_OPEN, res.stderr)
        self.assertIn(NEW_DOC, res.stderr)

    def test_nav_task_from_another_session_does_not_unlock_this_one(self):
        self.dispatch(self.skill_payload(session_id="sess-other"))
        agent = self.root / ".agent"
        self.assertIn("skills", state.load(agent, session_id="sess-other", now=NOW))
        # state loaded for another session id drops the section ...
        self.assertNotIn("skills", state.load(agent, session_id=SESSION_ID, now=NOW))
        # ... so the gate fires again in the new session
        res = self.dispatch(self.write_payload(), now=NOW + 1)
        self.assertEqual(res.exit_code, 2)

    def test_skills_is_a_session_scoped_state_section(self):
        self.assertIn("skills", state.SESSION_SCOPED_SECTIONS)
        self.assertIn("skills", state.KNOWN_SECTIONS)


if __name__ == "__main__":
    unittest.main()
