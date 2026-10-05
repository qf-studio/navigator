#!/usr/bin/env python3
"""Tests for ops/read_guard.py — TASK-61 Phase 4 parity port of nav_read_guard.py.

Covers the v6 threshold ladder (silent < warn < escalate advisory < strict
block with exit 2 + sentinel stderr), allowlist and out-of-tree exemptions,
config overrides, the deny-only channel (no stdout keys, no
permission_decision — mem-035/mem-054), the in-op 300s staleness window over
the schema-2 `reads` state section (missing/invalid timestamps are NOT
stale — the Stop reset barrel writes `{"turn_count": 0}` without one), and
mem-034 hygiene (block stderr never carries the triggering file path).
Golden byte-parity itself is asserted by tests/golden/test_parity.py.
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

import read_guard
from nav_hook_lib import config, runtime, sentinels, state

SESSION_ID = "sess-read-guard-tests"
NOW = 1_700_000_000.0

BLOCK_OPEN = sentinels.TAGS["nav-read-guard-block"]["open"]
BLOCK_CLOSE = sentinels.TAGS["nav-read-guard-block"]["close"]


class ReadGuardTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve() / "project"
        (self.root / ".agent" / "tasks").mkdir(parents=True)
        self._saved_env = {
            key: os.environ.pop(key, None) for key in ("CLAUDE_PROJECT_DIR",)
        }
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        for key, value in self._saved_env.items():
            if value is not None:
                os.environ[key] = value

    # -- helpers ----------------------------------------------------------

    def write_config(self, hook_cfg):
        path = self.root / ".agent" / ".nav-config.json"
        path.write_text(json.dumps({"read_guard_hook": hook_cfg}), encoding="utf-8")

    def payload(self, file_path, tool_name="Read", tool_use_id=None):
        doc = {
            "cwd": str(self.root),
            "session_id": SESSION_ID,
            "tool_name": tool_name,
            "tool_input": {"file_path": file_path},
        }
        if tool_use_id is not None:
            doc["tool_use_id"] = tool_use_id
        return doc

    def ctx(self, payload, state=None, now=NOW):
        return types.SimpleNamespace(
            event="PreToolUse",
            payload=payload,
            config=config.load(self.root),
            state=state if state is not None else {},
            pilot_executor=False,
            now=now,
        )

    def agent_file(self, rel="tasks/TASK-01-sample.md"):
        return str(self.root / ".agent" / rel)

    def run_read(self, state, rel="tasks/TASK-01-sample.md", now=NOW):
        ctx = self.ctx(self.payload(self.agent_file(rel)), state=state, now=now)
        return read_guard.run(ctx), ctx


class CountingTest(ReadGuardTestBase):
    def test_first_counted_read_is_silent_and_recorded(self):
        result, ctx = self.run_read(state={})
        self.assertIsNone(result)
        self.assertEqual(ctx.state["reads"]["turn_count"], 1)
        self.assertEqual(ctx.state["reads"]["updated_at"], NOW)

    def test_counter_continues_across_invocations(self):
        result, ctx = self.run_read(
            state={"reads": {"turn_count": 1, "updated_at": NOW - 10}})
        self.assertIsNone(result)
        self.assertEqual(ctx.state["reads"]["turn_count"], 2)

    def test_allowlisted_file_is_not_counted(self):
        result, ctx = self.run_read(state={}, rel="DEVELOPMENT-README.md")
        self.assertIsNone(result)
        self.assertNotIn("reads", ctx.state)

    def test_nested_allowlist_entry_matches_full_relative_path(self):
        result, ctx = self.run_read(state={}, rel="knowledge/graph.json")
        self.assertIsNone(result)
        self.assertNotIn("reads", ctx.state)

    def test_directory_allowlist_entry_matches_by_prefix(self):
        # research/ is a default entry (TASK-74): deep-research subagents read many
        # source notes in one turn and must not trip the ladder.
        result, ctx = self.run_read(state={}, rel="research/ion-traps/sources/005.md")
        self.assertIsNone(result)
        self.assertNotIn("reads", ctx.state)

    def test_directory_entry_does_not_match_sibling_prefix_without_slash(self):
        result, ctx = self.run_read(state={}, rel="research-notes.md")
        self.assertEqual(ctx.state["reads"]["turn_count"], 1)

    def test_file_outside_agent_dir_is_ignored(self):
        ctx = self.ctx(self.payload(str(self.root / "notes.md")), state={})
        self.assertIsNone(read_guard.run(ctx))
        self.assertNotIn("reads", ctx.state)

    def test_relative_agent_path_is_counted(self):
        ctx = self.ctx(self.payload(".agent/tasks/TASK-01-sample.md"), state={})
        self.assertIsNone(read_guard.run(ctx))
        self.assertEqual(ctx.state["reads"]["turn_count"], 1)

    def test_non_read_tool_is_ignored(self):
        ctx = self.ctx(self.payload(self.agent_file(), tool_name="Grep"), state={})
        self.assertIsNone(read_guard.run(ctx))
        self.assertNotIn("reads", ctx.state)

    def test_missing_file_path_is_ignored(self):
        payload = self.payload("")
        ctx = self.ctx(payload, state={})
        self.assertIsNone(read_guard.run(ctx))
        self.assertNotIn("reads", ctx.state)


class ThresholdLadderTest(ReadGuardTestBase):
    def test_warn_threshold_emits_advisory_without_exit_code(self):
        result, ctx = self.run_read(
            state={"reads": {"turn_count": 2, "updated_at": NOW - 5}})
        self.assertNotIn("exit_code", result)
        self.assertIn("[nav-read-guard] 3 .agent/ files read this turn.",
                      result["stderr"])
        self.assertIn("lazy-loading", result["stderr"])
        self.assertEqual(ctx.state["reads"]["turn_count"], 3)

    def test_escalate_with_strict_block_exits_2_with_sentinel(self):
        result, ctx = self.run_read(
            state={"reads": {"turn_count": 4, "updated_at": NOW - 5}})
        self.assertEqual(result["exit_code"], 2)
        self.assertIn(BLOCK_OPEN, result["stderr"])
        self.assertIn(BLOCK_CLOSE, result["stderr"])
        self.assertIn("blocked at 5 .agent/ reads (escalate_threshold=5)",
                      result["stderr"])
        self.assertEqual(ctx.state["reads"]["turn_count"], 5)
        # TASK-88: the refusal summary the runtime logs (path only here, never stderr).
        self.assertEqual(result["reject"]["reason"],
                         "5 .agent/ reads this turn (escalate_threshold=5)")
        self.assertEqual(result["reject"]["evidence"]["count"], 5)
        self.assertEqual(result["reject"]["evidence"]["threshold"], 5)
        self.assertTrue(result["reject"]["evidence"]["path"].endswith(".md"))

    def test_block_stderr_never_carries_the_file_path(self):
        # mem-034: no payload-derived substrings in the block notice (v6 rule).
        result, _ = self.run_read(
            state={"reads": {"turn_count": 4, "updated_at": NOW - 5}})
        self.assertNotIn(self.agent_file(), result["stderr"])
        self.assertNotIn("TASK-01-sample.md", result["stderr"])

    def test_escalate_without_strict_block_is_advisory_only(self):
        self.write_config({"strict_block": False})
        result, _ = self.run_read(
            state={"reads": {"turn_count": 4, "updated_at": NOW - 5}})
        self.assertNotIn("exit_code", result)
        self.assertIn("Bulk-load anti-pattern threshold crossed", result["stderr"])

    def test_deny_only_channel_has_no_stdout_keys(self):
        # mem-035/mem-054: no advisory stdout / additionalContext / permission
        # output from this gate — exit 2 + stderr is the whole channel.
        result, _ = self.run_read(
            state={"reads": {"turn_count": 4, "updated_at": NOW - 5}})
        # `reject` is runtime bookkeeping (TASK-88), stripped before the merge.
        self.assertEqual(set(result) - {"reject"}, {"exit_code", "stderr"})

    def test_config_overrides_thresholds(self):
        self.write_config({"warn_threshold": 1, "escalate_threshold": 2})
        result, _ = self.run_read(
            state={"reads": {"turn_count": 1, "updated_at": NOW - 5}})
        self.assertEqual(result["exit_code"], 2)
        self.assertIn("blocked at 2 .agent/ reads (escalate_threshold=2)",
                      result["stderr"])

    def test_config_allowlist_replaces_defaults(self):
        self.write_config({"allowlist": ["custom.md"]})
        result, ctx = self.run_read(state={}, rel="custom.md")
        self.assertIsNone(result)
        self.assertNotIn("reads", ctx.state)
        # Default entries are no longer exempt once overridden (v6 semantics).
        result, ctx = self.run_read(state={}, rel="DEVELOPMENT-README.md")
        self.assertEqual(ctx.state["reads"]["turn_count"], 1)


class StalenessTest(ReadGuardTestBase):
    """The 300s window lives INSIDE the op (v6 semantics); the `reads` section
    TTL (2h, nav_hook_lib.state) is only the coarser lib backstop."""

    def test_stale_counter_resets_before_increment(self):
        result, ctx = self.run_read(
            state={"reads": {"turn_count": 4, "updated_at": NOW - 301}})
        self.assertIsNone(result)  # fresh-from-zero: count is 1, no block
        self.assertEqual(ctx.state["reads"]["turn_count"], 1)
        self.assertEqual(ctx.state["reads"]["updated_at"], NOW)

    def test_counter_inside_window_is_kept(self):
        result, ctx = self.run_read(
            state={"reads": {"turn_count": 4, "updated_at": NOW - 299}})
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(ctx.state["reads"]["turn_count"], 5)

    def test_missing_timestamp_is_not_stale(self):
        # The Stop reset barrel writes {"turn_count": 0} with no updated_at;
        # v6 treated missing/unparseable timestamps as NOT stale.
        result, ctx = self.run_read(state={"reads": {"turn_count": 4}})
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(ctx.state["reads"]["turn_count"], 5)

    def test_invalid_timestamp_is_not_stale(self):
        result, ctx = self.run_read(
            state={"reads": {"turn_count": 4, "updated_at": "yesterday"}})
        self.assertEqual(result["exit_code"], 2)

    def test_non_positive_window_disables_staleness(self):
        self.write_config({"stale_after_seconds": 0})
        result, ctx = self.run_read(
            state={"reads": {"turn_count": 4, "updated_at": NOW - 999_999}})
        self.assertEqual(result["exit_code"], 2)

    def test_custom_window_from_config(self):
        self.write_config({"stale_after_seconds": 60})
        result, ctx = self.run_read(
            state={"reads": {"turn_count": 4, "updated_at": NOW - 61}})
        self.assertIsNone(result)
        self.assertEqual(ctx.state["reads"]["turn_count"], 1)


class DoubleDispatchDedupTest(ReadGuardTestBase):
    """TASK-66 regression: a single Read tool-use must advance the per-turn
    counter EXACTLY once, even when its PreToolUse surface dispatches twice
    (dual hook wiring / harness double-fire). Before the fix, N reads reached
    2N and the block escalated on the 3rd read instead of the 5th."""

    def _run_id(self, state, tool_use_id, rel="tasks/TASK-01-sample.md", now=NOW):
        ctx = self.ctx(self.payload(self.agent_file(rel), tool_use_id=tool_use_id),
                       state=state, now=now)
        return read_guard.run(ctx), ctx

    def test_duplicate_dispatch_of_same_tool_use_is_idempotent(self):
        st = {}
        r1, ctx = self._run_id(st, "toolu-A")
        self.assertIsNone(r1)
        self.assertEqual(ctx.state["reads"]["turn_count"], 1)
        # SAME tool_use_id dispatched again this turn — must not re-increment.
        r2, ctx = self._run_id(st, "toolu-A")
        self.assertIsNone(r2)
        self.assertEqual(ctx.state["reads"]["turn_count"], 1)

    def test_k_reads_each_double_fired_count_k_not_2k(self):
        st = {}
        k = 4
        ctx = None
        for i in range(1, k + 1):
            tid, rel = f"toolu-{i}", f"tasks/TASK-{i:02d}.md"
            self._run_id(st, tid, rel=rel)          # first wiring
            _, ctx = self._run_id(st, tid, rel=rel)  # duplicate wiring
        self.assertEqual(ctx.state["reads"]["turn_count"], k)

    def test_distinct_tool_uses_each_increment_once(self):
        st = {}
        self._run_id(st, "toolu-A", rel="tasks/TASK-01-sample.md")
        _, ctx = self._run_id(st, "toolu-B", rel="tasks/TASK-02-other.md")
        self.assertEqual(ctx.state["reads"]["turn_count"], 2)

    def test_block_first_fires_on_escalate_th_unique_read(self):
        st = {}
        outcomes = []  # (first_dispatch_result, duplicate_result) per unique read
        for i in range(1, 7):
            tid, rel = f"toolu-{i}", f"tasks/TASK-{i:02d}.md"
            first, _ = self._run_id(st, tid, rel=rel)
            dup, _ = self._run_id(st, tid, rel=rel)
            outcomes.append((first, dup))
        # No block on unique reads 1..4, nor on their duplicate dispatches.
        for first, dup in outcomes[:4]:
            self.assertNotEqual((first or {}).get("exit_code"), 2)
            self.assertNotEqual((dup or {}).get("exit_code"), 2)
        # The block appears first exactly on the 5th unique read (escalate=5),
        # and the duplicate dispatch of that read re-blocks identically.
        self.assertEqual(outcomes[4][0]["exit_code"], 2)
        self.assertEqual(outcomes[4][1]["exit_code"], 2)

    def test_allowlisted_read_never_increments_even_with_id(self):
        st = {}
        _, ctx = self._run_id(st, "toolu-A", rel="DEVELOPMENT-README.md")
        self.assertNotIn("reads", ctx.state)

    def test_missing_id_keeps_v6_per_dispatch_counting(self):
        # No tool_use_id (older harness firing exactly once): each dispatch
        # still increments, so nothing regresses for single-fire environments.
        st = {}
        ctx = self.ctx(self.payload(self.agent_file()), state=st)
        read_guard.run(ctx)
        ctx = self.ctx(self.payload(self.agent_file()), state=st)
        read_guard.run(ctx)
        self.assertEqual(ctx.state["reads"]["turn_count"], 2)


class DispatcherDoubleFireTest(ReadGuardTestBase):
    """End-to-end through runtime.dispatch with real state persistence: the
    same Read tool-use dispatched twice per read (separate processes reload
    the seen set from disk) counts once, so turn_count tracks unique reads and
    the block fires on the 5th, not the 3rd."""

    def _dispatch(self, rel, tool_use_id, now):
        payload = self.payload(self.agent_file(rel), tool_use_id=tool_use_id)
        return runtime.dispatch("PreToolUse", payload, now=now)

    def test_double_fired_reads_count_once_and_block_on_fifth(self):
        agent = self.root / ".agent"
        blocked_at = None
        for i in range(1, 7):
            tid, rel = f"toolu-{i}", f"tasks/TASK-{i:02d}.md"
            self._dispatch(rel, tid, now=NOW + i)          # wiring 1
            res = self._dispatch(rel, tid, now=NOW + i)     # wiring 2 (duplicate)
            st = state.load(agent, session_id=SESSION_ID, now=NOW + i)
            self.assertEqual(st["reads"]["turn_count"], i)  # i, never 2*i
            if res.exit_code == 2 and blocked_at is None:
                blocked_at = i
        self.assertEqual(blocked_at, 5)


if __name__ == "__main__":
    unittest.main()
