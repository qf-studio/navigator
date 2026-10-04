#!/usr/bin/env python3
"""Tests for ops/stop_completion.py — the forced-continuation gate (TASK-62).

Layers (TASK-45 pattern):
  - Op-level contract: dual condition (indicators unmet AND no nav-signal v3
    exit), the layered breaker (stop_fuse single-shot, held_count cap,
    stop_hook_active, non-mutating turns per mem-037), both kill switches
    seeded OFF, unconditional Pilot disable, mem-034 strip-before-scan.
  - Vendored-constants sync against skills/nav-loop/functions/exit_gate.py.
  - Subprocess composition via hooks/nav_dispatch.py: fuse consumed exactly
    once (second Stop silent + barrel re-arms), non-mutating turn never
    continues, Pilot/stop_hook_active silent, CLAUDE_PLUGIN_ROOT set AND
    unset (mem-036).
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))          # this dir
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # hooks/

import stop_completion  # noqa: E402
from nav_hook_lib import config as nav_config  # noqa: E402
from nav_hook_lib import sentinels, signals  # noqa: E402

HOOKS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = HOOKS_DIR.parent
DISPATCH = str(HOOKS_DIR / "nav_dispatch.py")
EXIT_GATE_PATH = REPO_ROOT / "skills" / "nav-loop" / "functions" / "exit_gate.py"

ENV_VARS = ("PILOT_EXECUTOR", "CLAUDE_USER_MESSAGE", "CLAUDE_PROJECT_DIR",
            "CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DIR")

EXIT_LINE = signals.emit("exit", success=True, reason="all done")


def enabled_cfg(project_management=None, **overrides):
    cfg = copy.deepcopy(nav_config.DEFAULTS)
    cfg["stop_completion"]["enabled"] = True
    cfg["stop_completion"]["continue_enabled"] = True
    if project_management is not None:
        cfg["project_management"] = project_management
    for key, value in overrides.items():
        cfg["stop_completion"][key] = value
    return cfg


def pm_cfg(**overrides):
    """Enabled config WITH a PM tool configured, so the derived ticket_closed
    indicator (TASK-65) stays False — isolating the other five indicators to
    exact counts in tests that pre-date the observable-evidence populator."""
    return enabled_cfg(project_management="github", **overrides)


def turn_with_tools(steps, closing="working, more to do", user_prompt="do it"):
    """A turn whose tool_use blocks carry real ``input`` + ``id`` and whose
    tool_results carry ``is_error`` — exercising the TASK-65 evidence scan.

    ``steps`` items: {"name", "input"?, "id"?, "is_error"?}. Layout mirrors the
    real harness: user prompt -> [tool_use, tool_result]* -> closing text.
    """
    entries = [{"message": {"role": "user", "content": user_prompt}}]
    for i, step in enumerate(steps):
        tid = step.get("id", f"toolu_{i}")
        use = {"type": "tool_use", "name": step["name"], "id": tid}
        if "input" in step:
            use["input"] = step["input"]
        entries.append({"message": {"role": "assistant", "content": [
            {"type": "text", "text": f"step {i}"}, use]}})
        result = {"type": "tool_result", "tool_use_id": tid, "content": "ok"}
        if step.get("is_error"):
            result["is_error"] = True
        entries.append({"message": {"role": "user", "content": [result]}})
    entries.append({"message": {"role": "assistant",
                                "content": [{"type": "text", "text": closing}]}})
    return entries


def unmet_names(reason: str) -> set:
    """The set of indicator names listed as unmet in a block reason string."""
    segment = reason.split("unmet: ")[1].split(")")[0]
    return {name.strip() for name in segment.split(",")}


def transcript_entries(closing_text, tools=("Edit",), user_prompt="implement it"):
    """A realistic turn: user prompt, tool_use assistant step(s), tool_result
    plumbing, then a text-only closing assistant message (the common shape —
    the tool_use never sits in the FINAL assistant message)."""
    entries = [{"message": {"role": "user", "content": user_prompt}}]
    for tool in tools:
        entries.append({"message": {"role": "assistant", "content": [
            {"type": "text", "text": f"using {tool}"},
            {"type": "tool_use", "name": tool},
        ]}})
        entries.append({"message": {"role": "user", "content": [
            {"type": "tool_result", "content": "ok"},
        ]}})
    entries.append({"message": {"role": "assistant", "content": [
        {"type": "text", "text": closing_text},
    ]}})
    return entries


def write_transcript(base: Path, entries) -> Path:
    path = base / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n",
                    encoding="utf-8")
    return path


class StopCompletionTestBase(unittest.TestCase):
    def setUp(self):
        self._saved = {key: os.environ.pop(key, None) for key in ENV_VARS}
        self.addCleanup(self._restore)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(os.path.realpath(self._tmp.name))
        # Deterministic default: no real git call leaks into op-level tests
        # (this checkout may be clean or dirty). Tests that assert the
        # code_committed rule override this per-case. Subprocess dispatch tests
        # are unaffected — they run their own git in a throwaway non-repo dir.
        git = mock.patch.object(stop_completion, "_git_clean", return_value=False)
        git.start()
        self.addCleanup(git.stop)
        # Same discipline for the TASK-71 tree digest: None = no evidence, so
        # every pre-existing test keeps pure vocabulary classification.
        # DigestEvidenceTest overrides per-case.
        digest = mock.patch.object(stop_completion, "_tree_digest",
                                   return_value=None)
        digest.start()
        self.addCleanup(digest.stop)

    def _restore(self):
        for key, value in self._saved.items():
            if value is not None:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)

    def make_ctx(self, entries=None, cfg=None, state=None, pilot=False,
                 stop_hook_active=False, payload_extra=None):
        payload = {"stop_hook_active": stop_hook_active}
        if entries is not None:
            payload["transcript_path"] = str(write_transcript(self.tmp, entries))
        if payload_extra:
            payload.update(payload_extra)
        return types.SimpleNamespace(
            event="Stop",
            payload=payload,
            config=cfg if cfg is not None else enabled_cfg(),
            state=state if state is not None else {},
            pilot_executor=pilot,
            now=100.0,
            session_id="s",
        )


class DualConditionTest(StopCompletionTestBase):
    def test_unfinished_mutating_turn_blocks(self):
        # pm_cfg + patched-dirty git + no md/marker/test evidence => a fully
        # unfinished turn stays 0/6 (all six indicators genuinely unmet).
        ctx = self.make_ctx(transcript_entries("edited the file; more to do"),
                            cfg=pm_cfg())
        result = stop_completion.run(ctx)
        self.assertEqual(result["decision"], "block")
        self.assertNotIn("continue_", result)   # mem-051: continue is a no-op
        self.assertNotIn("exit_code", result)
        reason = result["reason"]
        self.assertIn("0/6", reason)
        for name in stop_completion.INDICATOR_VOCABULARY:
            self.assertIn(name, reason)
        self.assertIn('"exit"', reason)  # tells the model how to yield
        completion = ctx.state["completion"]
        self.assertIs(completion["stop_fuse"], True)
        self.assertEqual(completion["held_count"], 1)
        self.assertIs(completion["signal"]["exit_seen"], False)

    def test_exit_signal_yields(self):
        ctx = self.make_ctx(transcript_entries("done\n" + EXIT_LINE))
        self.assertIsNone(stop_completion.run(ctx))

    def test_pilot_signal_v2_exit_yields(self):
        closing = "done\n```pilot-signal\n{\"type\": \"exit\", \"success\": true}\n```"
        ctx = self.make_ctx(transcript_entries(closing))
        self.assertIsNone(stop_completion.run(ctx))

    def test_html_comment_wrapped_exit_signal_yields(self):
        # TASK-70: the user-invisible emission convention — comment-wrapped
        # exit signals must satisfy the gate exactly like bare ones.
        ctx = self.make_ctx(transcript_entries("done\n<!-- " + EXIT_LINE + " -->"))
        self.assertIsNone(stop_completion.run(ctx))

    def test_inline_last_assistant_message_wins_for_signal_scan(self):
        ctx = self.make_ctx(transcript_entries("no signal in transcript"),
                            payload_extra={"last_assistant_message":
                                           "finishing\n" + EXIT_LINE})
        self.assertIsNone(stop_completion.run(ctx))

    def test_indicators_met_yields(self):
        state = {"completion": {"indicators": {
            "code_committed": True, "tests_passing": True}}}
        ctx = self.make_ctx(transcript_entries("committed"), state=state)
        self.assertIsNone(stop_completion.run(ctx))

    def test_one_indicator_is_not_enough(self):
        state = {"completion": {"indicators": {"code_committed": True}}}
        ctx = self.make_ctx(transcript_entries("committed"), state=state,
                            cfg=pm_cfg())
        result = stop_completion.run(ctx)
        self.assertEqual(result["decision"], "block")
        self.assertIn("1/6", result["reason"])
        self.assertNotIn("code_committed", result["reason"].split("unmet: ")[1])

    def test_non_vocabulary_indicators_are_ignored(self):
        state = {"completion": {"indicators": {"vibes": True, "swagger": True}}}
        ctx = self.make_ctx(transcript_entries("done?"), state=state,
                            cfg=pm_cfg())
        result = stop_completion.run(ctx)
        self.assertEqual(result["decision"], "block")
        self.assertIn("0/6", result["reason"])

    def test_exit_signal_inside_echoed_sentinel_block_is_ignored(self):
        # mem-034: signals are scanned on strip_all()'d text — an exit line
        # riding inside an echoed block notice must not count as completion.
        closing = sentinels.wrap("nav-workflow-block", EXIT_LINE) + "\nstill going"
        ctx = self.make_ctx(transcript_entries(closing))
        result = stop_completion.run(ctx)
        self.assertEqual(result["decision"], "block")

    def test_reason_never_echoes_transcript_text(self):
        marker = "SECRET-TRANSCRIPT-7f3a"
        ctx = self.make_ctx(transcript_entries(f"work on {marker} continues"))
        result = stop_completion.run(ctx)
        self.assertEqual(result["decision"], "block")
        self.assertNotIn(marker, result["reason"])


class BreakerTest(StopCompletionTestBase):
    def test_consumed_fuse_short_circuits(self):
        state = {"completion": {"stop_fuse": True}}
        ctx = self.make_ctx(transcript_entries("unfinished"), state=state)
        self.assertIsNone(stop_completion.run(ctx))
        self.assertEqual(ctx.state["completion"], {"stop_fuse": True})

    def test_held_count_cap_default_two(self):
        state = {"completion": {"held_count": 2}}
        ctx = self.make_ctx(transcript_entries("unfinished"), state=state)
        self.assertIsNone(stop_completion.run(ctx))

    def test_held_count_below_cap_blocks_and_increments(self):
        state = {"completion": {"held_count": 1}}
        cfg = enabled_cfg(max_continues=3)
        ctx = self.make_ctx(transcript_entries("unfinished"), cfg=cfg, state=state)
        result = stop_completion.run(ctx)
        self.assertEqual(result["decision"], "block")
        self.assertEqual(ctx.state["completion"]["held_count"], 2)

    def test_stop_hook_active_short_circuits(self):
        ctx = self.make_ctx(transcript_entries("unfinished"),
                            stop_hook_active=True)
        self.assertIsNone(stop_completion.run(ctx))

    def test_non_mutating_turn_never_continues(self):
        # mem-037: conversational/research turns must never be forced on.
        entries = [
            {"message": {"role": "user", "content": "what does this do?"}},
            {"message": {"role": "assistant", "content": [
                {"type": "text", "text": "it parses the config"},
            ]}},
        ]
        ctx = self.make_ctx(entries)
        self.assertIsNone(stop_completion.run(ctx))

    def test_readonly_tool_turn_never_continues(self):
        entries = transcript_entries("looked around", tools=("Read",))
        # Read is not in TASK_ACTION_TOOLS — not a mutating turn.
        ctx = self.make_ctx(entries)
        self.assertIsNone(stop_completion.run(ctx))

    def test_readonly_bash_turn_never_continues(self):
        # TASK-70: pure-inspection Bash turns (grep/ls/git status) false-fired
        # the gate as "mutated the codebase". PERMANENT — observed live twice
        # on 2026-07-10/11.
        entries = turn_with_tools([
            {"name": "Bash", "input": {"command": "grep -rn foo hooks/ | head"}},
            {"name": "Bash", "input": {"command": "ls -la && git status --porcelain"}},
            {"name": "Bash", "input": {"command": "git log --oneline -5; find . -name '*.py'"}},
        ])
        ctx = self.make_ctx(entries)
        self.assertIsNone(stop_completion.run(ctx))

    def test_mutating_bash_turn_still_continues(self):
        entries = turn_with_tools([
            {"name": "Bash", "input": {"command": "ls && rm -rf build/"}},
        ])
        result = stop_completion.run(self.make_ctx(entries, cfg=pm_cfg()))
        self.assertEqual(result["decision"], "block")

    def test_unknown_bash_command_counts_as_mutating(self):
        # Safe direction: unrecognized commands are treated as writes.
        entries = turn_with_tools([
            {"name": "Bash", "input": {"command": "python3 scripts/migrate.py"}},
        ])
        result = stop_completion.run(self.make_ctx(entries, cfg=pm_cfg()))
        self.assertEqual(result["decision"], "block")

    def test_mutating_git_subcommand_counts_as_mutating(self):
        entries = turn_with_tools([
            {"name": "Bash", "input": {"command": "git add -A && git commit -m x"}},
        ])
        result = stop_completion.run(self.make_ctx(entries, cfg=pm_cfg()))
        self.assertEqual(result["decision"], "block")

    def test_file_tool_beside_readonly_bash_is_mutating(self):
        entries = turn_with_tools([
            {"name": "Bash", "input": {"command": "git status"}},
            {"name": "Edit", "input": {"file_path": "/tmp/x.py"}},
        ])
        result = stop_completion.run(self.make_ctx(entries, cfg=pm_cfg()))
        self.assertEqual(result["decision"], "block")

    def test_inline_only_payload_never_continues(self):
        # The inline field carries no tool information: safe direction.
        ctx = self.make_ctx(payload_extra={
            "last_assistant_message": "edited things, more to do"})
        self.assertIsNone(stop_completion.run(ctx))

    def test_prior_turn_tools_do_not_leak_across_user_prompt_boundary(self):
        entries = transcript_entries("edited", tools=("Edit",))
        entries += [
            {"message": {"role": "user", "content": "thanks, one question"}},
            {"message": {"role": "assistant", "content": [
                {"type": "text", "text": "answering the question only"},
            ]}},
        ]
        ctx = self.make_ctx(entries)
        self.assertIsNone(stop_completion.run(ctx))


class ReadonlyBashParserTest(unittest.TestCase):
    """TASK-71: _bash_readonly shell-syntax awareness + gh/git allowlists.

    The read-only cases replay the exact command shapes that false-fired the
    gate live on 2026-07-16 (queue/daemon status checks in the pilot repo).
    PERMANENT regression tests.
    """

    READONLY = (
        # live false-fire replays (2026-07-16)
        "gh pr view 4373 --json state,reviewDecision",
        "gh issue list --label pilot --state open --limit 20",
        "gh run view --job 87651532134 --log 2>/dev/null | tail -40",
        "ps aux | grep -E '[b]in/pilot' | grep -v grep; echo \"---exit:$?\"",
        "ps -p 86555 -o pid,etime,command 2>/dev/null | tail -1",
        'LOG=$(ls -t ~/.pilot/logs/*.log 2>/dev/null | head -1); '
        '[ -n "$LOG" ] && grep -E "version" "$LOG" | head -5',
        "command -v pilot",
        "git fetch origin main 2>&1 | tail -2",
        "git ls-tree --name-only origin/main .agent/ | tail -8",
        # syntax shapes
        "for d in a b; do ls \"$d\"; done",
        "while read line; do echo \"$line\"; done",
        "if grep -q foo bar.txt; then echo yes; fi",
        "FOO=1 BAR=2 ls",
        "X=`git rev-parse HEAD`",
        "echo hi >/dev/null 2>&1",
        "echo hi >&2",
        "test -f x && cat x",
        # live false-fire replays (2026-10-03, TASK-85)
        "lsof -nP -iTCP:9464 -sTCP:LISTEN 2>/dev/null | tail -n +2",
        "curl -sfg --noproxy '*' --max-time 1 http://localhost:9092/api/v1/query",
        "curl -sL https://navigator-site.vercel.app/ | grep -o 'v8.0.0' | head -1",
        "pgrep -f 'claude --plugin-dir' | head -1",
        "sed -n '1,40p' hooks/mod/register.tsx | head -20",
        "sed -e 's/a/b/' notes.md",
    )
    MUTATING = (
        "curl -sSo /tmp/f https://x",       # -o inside a flag cluster
        "curl -O https://x/f",
        "curl --output out.json https://x",
        "curl -sS --remote-name https://x/f",
        "sed -i '' 's/a/b/' notes.md",         # in-place edit
        "sed --in-place=.bak 's/a/b/' notes.md",
        "gh pr merge 4373",
        "gh api repos/o/r/issues -X POST",
        "gh pr view 1 && gh issue close 2",
        "git fetch origin && git checkout main",
        "command pilot --version",          # executes pilot, not a lookup
        "VAR=1 make build",                 # assignment strip exposes make
        "echo hi > /tmp/f",                 # redirect to a real path
        "grep x f >> out.txt",
        "LOG=$(make build)",                # substitution runs the command
        "for f in a b; do rm \"$f\"; done",
        "sqlite3 db.sqlite 'select 1'",     # unknown head stays mutating
    )

    def test_readonly_commands(self):
        for cmd in self.READONLY:
            with self.subTest(cmd=cmd):
                self.assertTrue(stop_completion._bash_readonly(cmd))

    def test_mutating_commands(self):
        for cmd in self.MUTATING:
            with self.subTest(cmd=cmd):
                self.assertFalse(stop_completion._bash_readonly(cmd))


class DigestEvidenceTest(StopCompletionTestBase):
    """TASK-71: unchanged working-tree digest overrules vocabulary."""

    def entries(self, command="python3 scripts/ops_probe.py"):
        return turn_with_tools([{"name": "Bash", "input": {"command": command}}])

    def test_unchanged_digest_suppresses_vocab_mutating_turn(self):
        state = {"completion": {"tree_digest": "D"}}
        ctx = self.make_ctx(self.entries(), cfg=pm_cfg(), state=state)
        with mock.patch.object(stop_completion, "_tree_digest",
                               return_value="D"):
            self.assertIsNone(stop_completion.run(ctx))
        completion = ctx.state["completion"]
        self.assertEqual(completion.get("tree_digest"), "D")
        self.assertNotIn("stop_fuse", completion)  # no fuse burn

    def test_changed_digest_blocks_and_records(self):
        state = {"completion": {"tree_digest": "D1"}}
        ctx = self.make_ctx(self.entries(), cfg=pm_cfg(), state=state)
        with mock.patch.object(stop_completion, "_tree_digest",
                               return_value="D2"):
            result = stop_completion.run(ctx)
        self.assertEqual(result["decision"], "block")
        self.assertEqual(ctx.state["completion"]["tree_digest"], "D2")

    def test_no_prior_digest_falls_back_to_vocabulary(self):
        ctx = self.make_ctx(self.entries(), cfg=pm_cfg())
        with mock.patch.object(stop_completion, "_tree_digest",
                               return_value="D"):
            result = stop_completion.run(ctx)
        self.assertEqual(result["decision"], "block")
        self.assertEqual(ctx.state["completion"]["tree_digest"], "D")

    def test_file_tool_turn_ignores_unchanged_digest(self):
        state = {"completion": {"tree_digest": "D"}}
        entries = turn_with_tools(
            [{"name": "Edit", "input": {"file_path": "a.py"}}])
        ctx = self.make_ctx(entries, cfg=pm_cfg(), state=state)
        with mock.patch.object(stop_completion, "_tree_digest",
                               return_value="D"):
            result = stop_completion.run(ctx)
        self.assertEqual(result["decision"], "block")

    def test_digest_captured_even_on_consumed_fuse(self):
        # The fuse short-circuit must not starve the next turn's comparison.
        state = {"completion": {"stop_fuse": True, "tree_digest": "OLD"}}
        ctx = self.make_ctx(self.entries(), state=state)
        with mock.patch.object(stop_completion, "_tree_digest",
                               return_value="NEW"):
            self.assertIsNone(stop_completion.run(ctx))
        self.assertEqual(ctx.state["completion"]["tree_digest"], "NEW")
        self.assertIs(ctx.state["completion"]["stop_fuse"], True)

    # TASK-85: the digest is kept per session outside the session-scoped
    # `completion`, so another session's events in the same repo cannot
    # erase it and a read-only turn here still reads as non-mutating.
    def test_other_session_cannot_erase_this_sessions_digest(self):
        state = {"tree": {"digests": {"s": "D"}}}  # completion reset by a flip
        ctx = self.make_ctx(self.entries(), cfg=pm_cfg(), state=state)
        with mock.patch.object(stop_completion, "_tree_digest",
                               return_value="D"):
            self.assertIsNone(stop_completion.run(ctx))
        self.assertNotIn("stop_fuse", ctx.state.get("completion", {}))

    def test_session_entry_wins_over_completion_digest(self):
        state = {"completion": {"tree_digest": "X"},
                 "tree": {"digests": {"s": "D"}}}
        ctx = self.make_ctx(self.entries(), cfg=pm_cfg(), state=state)
        with mock.patch.object(stop_completion, "_tree_digest",
                               return_value="D"):
            self.assertIsNone(stop_completion.run(ctx))

    def test_digest_recorded_per_session_and_bounded(self):
        others = {f"old{i}": f"H{i}" for i in range(8)}
        state = {"tree": {"digests": dict(others)}}
        ctx = self.make_ctx(self.entries(), cfg=pm_cfg(), state=state)
        with mock.patch.object(stop_completion, "_tree_digest",
                               return_value="D1"):
            result = stop_completion.run(ctx)
        self.assertEqual(result["decision"], "block")  # first sight: vocabulary
        digests = ctx.state["tree"]["digests"]
        self.assertEqual(digests["s"], "D1")
        self.assertEqual(ctx.state["completion"]["tree_digest"], "D1")
        self.assertEqual(len(digests), stop_completion.TREE_DIGESTS_MAX)
        self.assertNotIn("old0", digests)  # the oldest entry made room

    def test_no_session_id_falls_back_to_completion_only(self):
        ctx = self.make_ctx(self.entries(), cfg=pm_cfg(),
                            state={"completion": {"tree_digest": "D"}})
        ctx.session_id = None
        with mock.patch.object(stop_completion, "_tree_digest",
                               return_value="D"):
            self.assertIsNone(stop_completion.run(ctx))
        self.assertNotIn("tree", ctx.state)

    def test_digest_failure_keeps_prior_value(self):
        state = {"completion": {"tree_digest": "D"}}
        ctx = self.make_ctx(self.entries(), cfg=pm_cfg(), state=state)
        # base setUp patches _tree_digest -> None (no evidence this Stop)
        result = stop_completion.run(ctx)
        self.assertEqual(result["decision"], "block")  # fallback: vocabulary
        self.assertEqual(ctx.state["completion"]["tree_digest"], "D")


class DerivedIndicatorTest(StopCompletionTestBase):
    """TASK-65: completion indicators populated from OBSERVABLE turn evidence.

    Each rule is proven independently. Where a single indicator is met the gate
    still blocks (met=1 < MIN_HEURISTICS=2), so the rule is verified by reading
    the unmet list out of the reason string.
    """

    def _block(self, entries, cfg=None):
        result = stop_completion.run(self.make_ctx(entries, cfg=cfg or pm_cfg()))
        self.assertIsNotNone(result, "expected a block")
        self.assertEqual(result["decision"], "block")
        return result["reason"]

    def test_code_committed_when_git_clean(self):
        entries = turn_with_tools([{"name": "Edit", "input": {"file_path": "a.py"}}])
        with mock.patch.object(stop_completion, "_git_clean", return_value=True):
            reason = self._block(entries)
        self.assertIn("1/6", reason)
        self.assertNotIn("code_committed", unmet_names(reason))

    def test_dirty_tree_leaves_code_committed_unmet(self):
        entries = turn_with_tools([{"name": "Edit", "input": {"file_path": "a.py"}}])
        # base setUp patches _git_clean -> False (dirty tree)
        reason = self._block(entries)
        self.assertIn("0/6", reason)
        self.assertIn("code_committed", unmet_names(reason))

    def test_tests_passing_when_test_command_not_errored(self):
        entries = turn_with_tools(
            [{"name": "Bash", "input": {"command": "make test"}, "is_error": False}])
        reason = self._block(entries)
        self.assertNotIn("tests_passing", unmet_names(reason))

    def test_unittest_module_command_counts_as_tests_passing(self):
        entries = turn_with_tools(
            [{"name": "Bash",
              "input": {"command": "python3 -m unittest test_stop_completion"}}])
        reason = self._block(entries)
        self.assertNotIn("tests_passing", unmet_names(reason))

    def test_failing_test_command_does_not_count(self):
        entries = turn_with_tools(
            [{"name": "Bash", "input": {"command": "pytest"}, "is_error": True}])
        reason = self._block(entries)
        self.assertIn("0/6", reason)
        self.assertIn("tests_passing", unmet_names(reason))

    def test_non_test_command_does_not_count(self):
        # `make build` is mutating (unknown head) but is not a test command.
        entries = turn_with_tools(
            [{"name": "Bash", "input": {"command": "make build"}, "is_error": False}])
        reason = self._block(entries)
        self.assertIn("tests_passing", unmet_names(reason))

    def test_docs_updated_when_md_touched(self):
        entries = turn_with_tools(
            [{"name": "Edit", "input": {"file_path": "docs/README.md"}}])
        reason = self._block(entries)
        self.assertNotIn("docs_updated", unmet_names(reason))

    def test_marker_created_when_context_marker_written(self):
        # A .json marker path isolates marker_created from docs_updated (.md).
        entries = turn_with_tools([{"name": "Write", "input": {
            "file_path": "/repo/.agent/.context-markers/save.json"}}])
        reason = self._block(entries)
        self.assertNotIn("marker_created", unmet_names(reason))
        self.assertIn("docs_updated", unmet_names(reason))

    def test_notebook_path_is_collected_as_file_path(self):
        entries = turn_with_tools([{"name": "NotebookEdit", "input": {
            "notebook_path": "analysis.md"}}])
        reason = self._block(entries)
        self.assertNotIn("docs_updated", unmet_names(reason))

    def test_ticket_closed_when_no_pm_configured(self):
        entries = turn_with_tools([{"name": "Edit", "input": {"file_path": "a.py"}}])
        reason = self._block(entries, cfg=enabled_cfg())  # project_management none
        self.assertNotIn("ticket_closed", unmet_names(reason))

    def test_ticket_open_when_pm_configured(self):
        entries = turn_with_tools([{"name": "Edit", "input": {"file_path": "a.py"}}])
        reason = self._block(entries, cfg=pm_cfg())
        self.assertIn("ticket_closed", unmet_names(reason))

    def test_code_simplified_never_derived(self):
        # Even a rich turn (md doc touched) never derives code_simplified.
        entries = turn_with_tools(
            [{"name": "Edit", "input": {"file_path": "notes.md"}}])
        reason = self._block(entries)
        self.assertIn("code_simplified", unmet_names(reason))

    def test_committed_and_tested_turn_yields_no_continue(self):
        # code_committed (git clean) + tests_passing (make test ok) = 2 => yield.
        entries = turn_with_tools(
            [{"name": "Bash", "input": {"command": "make test"}, "is_error": False}])
        ctx = self.make_ctx(entries, cfg=pm_cfg())
        with mock.patch.object(stop_completion, "_git_clean", return_value=True):
            self.assertIsNone(stop_completion.run(ctx))
        self.assertEqual(ctx.state, {})  # no fuse burned, no counter

    def test_uncommitted_mutating_turn_still_continues(self):
        # Dirty tree, no other evidence, PM configured => 0/6 => forced continue.
        entries = turn_with_tools([{"name": "Edit", "input": {"file_path": "a.py"}}])
        ctx = self.make_ctx(entries, cfg=pm_cfg())
        result = stop_completion.run(ctx)
        self.assertEqual(result["decision"], "block")
        self.assertEqual(ctx.state["completion"]["held_count"], 1)

    def test_state_true_indicator_wins_over_empty_derivation(self):
        # Explicit state indicators still count even when nothing is derived.
        state = {"completion": {"indicators": {
            "code_committed": True, "code_simplified": True}}}
        entries = turn_with_tools([{"name": "Edit", "input": {"file_path": "a.py"}}])
        ctx = self.make_ctx(entries, cfg=pm_cfg(), state=state)
        self.assertIsNone(stop_completion.run(ctx))

    def test_state_and_derived_indicators_merge(self):
        # One from state (code_simplified) + one derived (docs_updated) = 2.
        state = {"completion": {"indicators": {"code_simplified": True}}}
        entries = turn_with_tools([{"name": "Edit", "input": {"file_path": "x.md"}}])
        ctx = self.make_ctx(entries, cfg=pm_cfg(), state=state)
        self.assertIsNone(stop_completion.run(ctx))

    def test_non_mutating_turn_ignores_evidence(self):
        # A read-only turn never continues even if it touched a .md path.
        entries = turn_with_tools([{"name": "Read", "input": {"file_path": "a.md"}}])
        self.assertIsNone(stop_completion.run(self.make_ctx(entries, cfg=pm_cfg())))


class KillSwitchTest(StopCompletionTestBase):
    def test_missing_config_block_is_off(self):
        ctx = self.make_ctx(transcript_entries("unfinished"),
                            cfg=copy.deepcopy(nav_config.DEFAULTS))
        self.assertIsNone(stop_completion.run(ctx))

    def test_enabled_without_continue_enabled_is_off(self):
        cfg = enabled_cfg(continue_enabled=False)
        ctx = self.make_ctx(transcript_entries("unfinished"), cfg=cfg)
        self.assertIsNone(stop_completion.run(ctx))

    def test_continue_enabled_without_enabled_is_off(self):
        cfg = enabled_cfg(enabled=False)
        ctx = self.make_ctx(transcript_entries("unfinished"), cfg=cfg)
        self.assertIsNone(stop_completion.run(ctx))

    def test_pilot_executor_disables_unconditionally(self):
        ctx = self.make_ctx(transcript_entries("unfinished"), pilot=True)
        self.assertIsNone(stop_completion.run(ctx))
        self.assertEqual(ctx.state, {})  # no fuse burn, no counter


class ExitGateSyncTest(StopCompletionTestBase):
    """The vendored constants must track the skill source (no drift)."""

    def _load_skill(self):
        self.assertTrue(EXIT_GATE_PATH.is_file(), EXIT_GATE_PATH)
        spec = importlib.util.spec_from_file_location("exit_gate_src",
                                                      EXIT_GATE_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_vendored_constants_match_exit_gate(self):
        gate = self._load_skill()
        self.assertEqual(stop_completion.MIN_HEURISTICS,
                         gate.MIN_HEURISTICS_DEFAULT)
        self.assertEqual(len(stop_completion.INDICATOR_VOCABULARY),
                         gate.TOTAL_INDICATORS)
        source = EXIT_GATE_PATH.read_text(encoding="utf-8")
        for name in stop_completion.INDICATOR_VOCABULARY:
            self.assertIn(name, source,
                          f"indicator {name} not documented in exit_gate.py")

    def test_loader_finds_exit_gate_in_this_checkout(self):
        gate = stop_completion._load_exit_gate()
        self.assertIsNotNone(gate)
        self.assertTrue(callable(gate.evaluate_exit))


class DispatchCompositionTest(StopCompletionTestBase):
    """Subprocess composition via nav_dispatch.py (TASK-45 template)."""

    STOP_ON = json.dumps(
        {"stop_completion": {"enabled": True, "continue_enabled": True}})

    def make_project(self, config_body=None):
        project = self.tmp / "project"
        agent = project / ".agent"
        agent.mkdir(parents=True, exist_ok=True)
        (agent / ".nav-config.json").write_text(
            config_body if config_body is not None else self.STOP_ON)
        return project

    def dispatch(self, project, payload, env_extra=None):
        env = os.environ.copy()
        for var in ENV_VARS:
            env.pop(var, None)
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            [sys.executable, DISPATCH, "Stop"],
            input=json.dumps(payload), capture_output=True, text=True,
            cwd=project, env=env, timeout=60,
        )

    def payload(self, project, tpath, stop_hook_active=False):
        return {"cwd": str(project), "session_id": "s1",
                "transcript_path": str(tpath),
                "stop_hook_active": stop_hook_active}

    def read_state(self, project):
        path = project / ".agent" / ".nav-runtime-state.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def doc(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def test_fuse_consumed_once_second_stop_silent(self):
        project = self.make_project()
        tpath = write_transcript(self.tmp,
                                 transcript_entries("edited; more to do"))
        payload = self.payload(project, tpath)

        first = self.doc(self.dispatch(project, payload))
        self.assertEqual(first.get("decision"), "block", first)
        state = self.read_state(project)
        self.assertIs(state["completion"]["stop_fuse"], True)
        self.assertEqual(state["completion"]["held_count"], 1)
        # The gate short-circuited the stop_state recorder: same turn, no stamp.
        self.assertNotIn("turn", state)

        second = self.doc(self.dispatch(project, payload))
        self.assertNotIn("decision", second)  # silent: fuse consumed
        state = self.read_state(project)
        # stop_state ran this time: barrel re-armed the breaker for the next
        # turn and stamped the (now ended) turn.
        self.assertIs(state["completion"]["stop_fuse"], False)
        self.assertEqual(state["completion"]["held_count"], 0)
        self.assertIn("turn", state)

    def test_non_mutating_turn_never_continues_composition(self):
        project = self.make_project()
        entries = [
            {"message": {"role": "user", "content": "quick question"}},
            {"message": {"role": "assistant", "content": [
                {"type": "text", "text": "here is the answer"},
            ]}},
        ]
        tpath = write_transcript(self.tmp, entries)
        doc = self.doc(self.dispatch(project, self.payload(project, tpath)))
        self.assertNotIn("decision", doc)

    def test_stop_hook_active_is_silent(self):
        project = self.make_project()
        tpath = write_transcript(self.tmp,
                                 transcript_entries("edited; more to do"))
        doc = self.doc(self.dispatch(
            project, self.payload(project, tpath, stop_hook_active=True)))
        self.assertNotIn("decision", doc)

    def test_pilot_executor_never_blocks(self):
        project = self.make_project()
        tpath = write_transcript(self.tmp,
                                 transcript_entries("edited; more to do"))
        result = self.dispatch(project, self.payload(project, tpath),
                               env_extra={"PILOT_EXECUTOR": "1"})
        doc = self.doc(result)
        self.assertNotIn("decision", doc)
        completion = self.read_state(project).get("completion") or {}
        self.assertNotEqual(completion.get("held_count"), 1)

    def test_seeded_off_pristine_config_is_silent(self):
        project = self.make_project(config_body="{}")
        tpath = write_transcript(self.tmp,
                                 transcript_entries("edited; more to do"))
        doc = self.doc(self.dispatch(project, self.payload(project, tpath)))
        self.assertNotIn("decision", doc)

    def test_unchanged_tree_digest_silences_third_stop(self):
        # TASK-71 end-to-end: stop 1 blocks (no prior digest) and records the
        # working-tree digest; stop 2 is silent (fuse) and the barrel
        # re-arms; stop 3 — same unknown-command turn, tree untouched — is
        # silent on EVIDENCE, where pre-TASK-71 it blocked every turn.
        project = self.make_project()
        subprocess.run(["git", "init", "-q"], cwd=project, check=True)
        entries = turn_with_tools(
            [{"name": "Bash", "input": {"command": "sqlite3 db 'select 1'"}}])
        tpath = write_transcript(self.tmp, entries)
        payload = self.payload(project, tpath)

        first = self.doc(self.dispatch(project, payload))
        self.assertEqual(first.get("decision"), "block", first)
        second = self.doc(self.dispatch(project, payload))
        self.assertNotIn("decision", second)  # fuse consumed; barrel re-arms
        third = self.doc(self.dispatch(project, payload))
        self.assertNotIn("decision", third)   # digest evidence: tree unchanged
        state = self.read_state(project)
        self.assertEqual(state["completion"]["held_count"], 0)

    def test_block_behavior_identical_env_set_and_unset(self):
        # mem-036: CLAUDE_PLUGIN_ROOT set AND unset must both block.
        for env_extra in (None, {"CLAUDE_PLUGIN_ROOT": str(REPO_ROOT)}):
            with self.subTest(env=env_extra):
                project = self.make_project()
                tpath = write_transcript(
                    self.tmp, transcript_entries("edited; more to do"))
                doc = self.doc(self.dispatch(
                    project, self.payload(project, tpath), env_extra=env_extra))
                self.assertEqual(doc.get("decision"), "block", doc)
                # reset for the next subTest iteration
                (project / ".agent" / ".nav-runtime-state.json").unlink()


if __name__ == "__main__":
    unittest.main()
