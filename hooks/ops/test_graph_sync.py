#!/usr/bin/env python3
"""Tests for ops/graph_sync.py — TASK-61 Phase 3 parity port of nav_task_graph_sync.py.

Covers the v6 branch table (task-doc edit → subprocess upsert; non-task edit /
missing graph / deleted task → silent ack), the `{}` ack contract, the v6
Edit|Write surface filter under the widened registry matcher (MultiEdit and
NotebookEdit — notebook_path payloads — skip silently; v6 never saw them),
and subprocess failure diagnostics. Golden byte-parity itself is asserted by
tests/golden/test_parity.py.
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

import graph_sync
from nav_hook_lib import config

SESSION_ID = "sess-graph-sync-tests"
NOW = 1_700_000_000.0

# Stub syncer: records argv next to itself, exits with the templated code.
STUB_SYNCER = """\
import json, sys
from pathlib import Path
Path(__file__).with_name("calls.json").write_text(json.dumps(sys.argv[1:]))
sys.exit({rc})
"""


class GraphSyncTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name).resolve()

        self.root = base / "project"
        (self.root / ".agent" / "tasks").mkdir(parents=True)
        (self.root / ".agent" / "knowledge").mkdir(parents=True)
        self.graph_path = self.root / ".agent" / "knowledge" / "graph.json"
        self.graph_path.write_text("{}\n", encoding="utf-8")

        self.plugin_dir = base / "plugin"
        self.functions_dir = self.plugin_dir / "skills" / "nav-graph" / "functions"
        self.functions_dir.mkdir(parents=True)
        self.write_stub(rc=0)

        self._saved_env = {
            key: os.environ.pop(key, None)
            for key in ("CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DIR", "CLAUDE_PROJECT_DIR")
        }
        os.environ["CLAUDE_PLUGIN_ROOT"] = str(self.plugin_dir)
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
        for key, value in self._saved_env.items():
            if value is not None:
                os.environ[key] = value

    # -- helpers ----------------------------------------------------------

    def write_stub(self, rc):
        syncer = self.functions_dir / "task_to_graph.py"
        syncer.write_text(STUB_SYNCER.format(rc=rc), encoding="utf-8")

    def stub_calls(self):
        path = self.functions_dir / "calls.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def payload(self, tool_name="Edit", **tool_input):
        return {
            "cwd": str(self.root),
            "session_id": SESSION_ID,
            "tool_name": tool_name,
            "tool_input": tool_input,
        }

    def ctx(self, payload, state=None):
        return types.SimpleNamespace(
            event="PostToolUse",
            payload=payload,
            config=config.load(self.root),
            state=state if state is not None else {},
            pilot_executor=False,
            now=NOW,
        )

    def make_task_doc(self, name="TASK-99-sample.md"):
        path = self.root / ".agent" / "tasks" / name
        path.write_text("# TASK-99: sample\n", encoding="utf-8")
        return path


class TaskDocSyncTest(GraphSyncTestBase):
    def test_task_doc_edit_runs_syncer_and_acks(self):
        task = self.make_task_doc()
        result = graph_sync.run(self.ctx(self.payload(file_path=str(task))))
        self.assertEqual(result["ack"], True)
        self.assertIn("nav_task_graph_sync: upserted TASK-99-sample.md",
                      result["stderr"])
        calls = self.stub_calls()
        self.assertEqual(calls[:2], ["--action", "add"])
        self.assertEqual(calls[calls.index("--task-path") + 1], str(task))
        self.assertEqual(calls[calls.index("--graph-path") + 1], str(self.graph_path))

    def test_relative_task_path_resolves_against_root(self):
        self.make_task_doc("TASK-07-rel.md")
        payload = self.payload(file_path=".agent/tasks/TASK-07-rel.md")
        result = graph_sync.run(self.ctx(payload))
        self.assertEqual(result["ack"], True)
        self.assertIsNotNone(self.stub_calls())

    def test_gh_prefixed_task_doc_syncs_too(self):
        """GH-32: task_id_source github names docs GH-<n>-slug.md."""
        task = self.make_task_doc("GH-57-oauth.md")
        result = graph_sync.run(self.ctx(self.payload(file_path=str(task))))
        self.assertEqual(result["ack"], True)
        self.assertIsNotNone(self.stub_calls())

    def test_non_task_markdown_in_tasks_dir_acks_without_sync(self):
        task = self.make_task_doc("README.md")
        result = graph_sync.run(self.ctx(self.payload(file_path=str(task))))
        self.assertEqual(result, {"ack": True})
        self.assertIsNone(self.stub_calls())

    def test_write_tool_is_on_the_v6_surface(self):
        task = self.make_task_doc()
        result = graph_sync.run(self.ctx(self.payload(tool_name="Write",
                                                      file_path=str(task))))
        self.assertEqual(result["ack"], True)
        self.assertIsNotNone(self.stub_calls())


class SilentAckBranchesTest(GraphSyncTestBase):
    """v6 printed `{}` on every Edit|Write branch — even when nothing synced."""

    def assert_ack_without_sync(self, result):
        self.assertEqual(result, {"ack": True})
        self.assertIsNone(self.stub_calls())

    def test_non_task_file_acks_without_subprocess(self):
        notes = self.root / "notes.md"
        notes.write_text("# Notes\n", encoding="utf-8")
        result = graph_sync.run(self.ctx(self.payload(file_path=str(notes))))
        self.assert_ack_without_sync(result)

    def test_non_task_name_inside_tasks_dir_is_ignored(self):
        stray = self.root / ".agent" / "tasks" / "notes.md"
        stray.write_text("scratch\n", encoding="utf-8")
        result = graph_sync.run(self.ctx(self.payload(file_path=str(stray))))
        self.assert_ack_without_sync(result)

    def test_missing_graph_skips_sync(self):
        self.graph_path.unlink()
        task = self.make_task_doc()
        result = graph_sync.run(self.ctx(self.payload(file_path=str(task))))
        self.assert_ack_without_sync(result)

    def test_deleted_task_file_skips_sync(self):
        missing = self.root / ".agent" / "tasks" / "TASK-42-gone.md"
        result = graph_sync.run(self.ctx(self.payload(file_path=str(missing))))
        self.assert_ack_without_sync(result)

    def test_missing_file_path_key_acks_without_subprocess(self):
        result = graph_sync.run(self.ctx(self.payload()))
        self.assert_ack_without_sync(result)


class WidenedMatcherSkipTest(GraphSyncTestBase):
    """MultiEdit/NotebookEdit reach the op via the coarse registry matcher.

    v6's manifest fired on Edit|Write only, so the op emits NOTHING for the
    new tool names (no ack, no sync) — locked here per the TASK-61 brief.
    """

    def test_notebook_edit_payload_skips_silently(self):
        notebook = self.root / ".agent" / "tasks" / "TASK-99-sample.ipynb"
        payload = self.payload(tool_name="NotebookEdit")
        payload["tool_input"] = {"notebook_path": str(notebook), "new_source": "x"}
        self.assertIsNone(graph_sync.run(self.ctx(payload)))
        self.assertIsNone(self.stub_calls())

    def test_multiedit_payload_skips_silently(self):
        task = self.make_task_doc()
        payload = self.payload(tool_name="MultiEdit", file_path=str(task))
        self.assertIsNone(graph_sync.run(self.ctx(payload)))
        self.assertIsNone(self.stub_calls())


class LifecycleEventTest(GraphSyncTestBase):
    """TASK-62: TaskCreated/TaskCompleted feed the graph via the event branch."""

    def lifecycle_ctx(self, event, payload_extra):
        payload = {"cwd": str(self.root), "session_id": SESSION_ID}
        payload.update(payload_extra)
        ctx = self.ctx(payload)
        ctx.event = event
        return ctx

    def test_task_created_with_task_path_runs_syncer(self):
        task = self.make_task_doc()
        result = graph_sync.run(
            self.lifecycle_ctx("TaskCreated", {"task_path": str(task)}))
        self.assertIn("upserted TASK-99-sample.md", result["stderr"])
        calls = self.stub_calls()
        self.assertEqual(calls[:2], ["--action", "add"])
        self.assertEqual(calls[calls.index("--task-path") + 1], str(task))

    def test_task_completed_with_nested_task_dict_runs_syncer(self):
        task = self.make_task_doc("TASK-42-done.md")
        result = graph_sync.run(self.lifecycle_ctx(
            "TaskCompleted", {"task": {"file_path": str(task)}}))
        self.assertIn("upserted TASK-42-done.md", result["stderr"])

    def test_relative_lifecycle_path_resolves_against_root(self):
        self.make_task_doc("TASK-07-rel.md")
        result = graph_sync.run(self.lifecycle_ctx(
            "TaskCreated", {"path": ".agent/tasks/TASK-07-rel.md"}))
        self.assertIn("upserted TASK-07-rel.md", result["stderr"])

    def test_payload_without_task_doc_path_is_silent(self):
        result = graph_sync.run(self.lifecycle_ctx(
            "TaskCompleted", {"task": {"id": "42", "subject": "no path here"}}))
        self.assertIsNone(result)
        self.assertIsNone(self.stub_calls())

    def test_non_task_doc_path_is_silent(self):
        notes = self.root / "notes.md"
        notes.write_text("# Notes\n", encoding="utf-8")
        result = graph_sync.run(self.lifecycle_ctx(
            "TaskCreated", {"file_path": str(notes)}))
        self.assertIsNone(result)
        self.assertIsNone(self.stub_calls())

    def test_missing_graph_is_silent_on_lifecycle_events(self):
        self.graph_path.unlink()
        task = self.make_task_doc()
        result = graph_sync.run(
            self.lifecycle_ctx("TaskCreated", {"task_path": str(task)}))
        self.assertIsNone(result)
        self.assertIsNone(self.stub_calls())

    def test_lifecycle_branch_never_emits_the_v6_ack(self):
        # The `{}` ack byte-contract belongs to the PostToolUse surface only.
        task = self.make_task_doc()
        result = graph_sync.run(
            self.lifecycle_ctx("TaskCompleted", {"task_path": str(task)}))
        self.assertNotIn("ack", result)


class SyncFailureTest(GraphSyncTestBase):
    def test_failed_sync_reports_rc_and_still_acks(self):
        self.write_stub(rc=1)
        task = self.make_task_doc()
        result = graph_sync.run(self.ctx(self.payload(file_path=str(task))))
        self.assertEqual(result["ack"], True)
        self.assertIn("nav_task_graph_sync: sync failed (rc=1)", result["stderr"])

    def test_missing_syncer_reports_and_acks(self):
        (self.functions_dir / "task_to_graph.py").unlink()
        task = self.make_task_doc()
        result = graph_sync.run(self.ctx(self.payload(file_path=str(task))))
        self.assertEqual(result["ack"], True)
        self.assertIn("task_to_graph.py missing", result["stderr"])


if __name__ == "__main__":
    unittest.main()
