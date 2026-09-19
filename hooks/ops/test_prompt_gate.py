#!/usr/bin/env python3
"""Tests for ops/prompt_gate.py — the workflow-enforcement gate (v6 parity).

Two layers:
  - Differential vs the v6 script (hooks/workflow_enforcer.py run as a
    subprocess): the soft-warn stdout must be byte-identical (op context +
    the dispatcher shim's trailing newline == v6 stdout). Auto-skips once
    Phase 7 deletes the v6 source.
  - Op-level contract: block fires ONLY on (loop trigger) AND
    (check_shown is False) AND (strict_block); tristate True/None never
    block (mem-037); PILOT passthrough; mem-034 strip-before-match and
    no-trigger-in-stderr redaction.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))          # this dir
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # hooks/

import prompt_gate  # noqa: E402
from nav_hook_lib import config as nav_config  # noqa: E402
from nav_hook_lib import scoring, sentinels  # noqa: E402

HOOKS_DIR = Path(__file__).resolve().parent.parent
V6_SCRIPT = HOOKS_DIR / "workflow_enforcer.py"

LOOP_PROMPT = "run until done: polish the release notes"


def make_ctx(prompt=None, cfg=None, check_shown="absent", pilot=False):
    state = {}
    if check_shown != "absent":
        state["turn"] = {"signals": {"check_shown": check_shown}}
    payload = {} if prompt is None else {"prompt": prompt}
    return types.SimpleNamespace(
        event="UserPromptSubmit",
        payload=payload,
        config=cfg or copy.deepcopy(nav_config.DEFAULTS),
        state=state,
        pilot_executor=pilot,
        now=0.0,
    )


class GateTestBase(unittest.TestCase):
    def setUp(self):
        self._saved = {
            key: os.environ.pop(key, None)
            for key in ("PILOT_EXECUTOR", "CLAUDE_USER_MESSAGE",
                        "CLAUDE_PROJECT_DIR")
        }
        self.addCleanup(self._restore)

    def _restore(self):
        for key, value in self._saved.items():
            if value is not None:
                os.environ[key] = value


class V6WarnDifferentialTest(GateTestBase):
    """Soft-warn stdout byte parity against the live v6 script."""

    def _v6_stdout(self, prompt: str) -> str:
        if not V6_SCRIPT.is_file():
            self.skipTest("workflow_enforcer.py deleted (Phase 7)")
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(V6_SCRIPT)],
                input=json.dumps({"prompt": prompt, "cwd": tmp}),
                cwd=tmp, env=dict(os.environ), capture_output=True, text=True,
                timeout=30,
            )
        self.assertEqual(proc.returncode, 0)
        return proc.stdout

    def _assert_warn_parity(self, prompt: str):
        result = prompt_gate.run(make_ctx(prompt))
        self.assertIsNotNone(result)
        # The dispatcher shim print()s the merged plain-stdout doc, adding
        # exactly one newline — that composed byte stream is what must match.
        self.assertEqual(result["additional_context"] + "\n",
                         self._v6_stdout(prompt))

    def test_loop_trigger_warn_bytes_match_v6(self):
        self._assert_warn_parity(LOOP_PROMPT)

    def test_task_mode_warn_bytes_match_v6(self):
        self._assert_warn_parity(
            "refactor the auth module across the codebase")

    def test_combined_loop_and_task_warn_bytes_match_v6(self):
        self._assert_warn_parity(
            "keep going: implement the new feature and migrate the schema")

    def test_silent_prompt_matches_v6_silence(self):
        prompt = "thanks, looks good"
        self.assertEqual(self._v6_stdout(prompt), "")
        self.assertIsNone(prompt_gate.run(make_ctx(prompt)))


class BlockRulesTest(GateTestBase):
    def test_blocks_on_loop_trigger_after_false_stamp(self):
        result = prompt_gate.run(make_ctx(LOOP_PROMPT, check_shown=False))
        self.assertEqual(result["exit_code"], 2)
        self.assertTrue(result["stderr"].startswith("<nav-workflow-block>"))
        self.assertTrue(result["stderr"].endswith("</nav-workflow-block>"))
        self.assertNotIn("additional_context", result)  # warn suppressed

    def test_block_stderr_contains_no_trigger_phrase(self):
        # mem-034 permanent probe (also asserted end-to-end in
        # tests/golden/test_composition.py).
        result = prompt_gate.run(make_ctx(LOOP_PROMPT, check_shown=False))
        lowered = result["stderr"].lower()
        for phrase in scoring.LOOP_TRIGGERS:
            self.assertNotIn(phrase, lowered)

    def test_true_stamp_warns_instead_of_blocking(self):
        result = prompt_gate.run(make_ctx(LOOP_PROMPT, check_shown=True))
        self.assertNotIn("exit_code", result)
        self.assertIn("LOOP MODE TRIGGER DETECTED", result["additional_context"])

    def test_none_stamp_never_blocks(self):
        # mem-037: conversational turns stamp None — blocking on it was the
        # AskUserQuestion deadlock.
        result = prompt_gate.run(make_ctx(LOOP_PROMPT, check_shown=None))
        self.assertNotIn("exit_code", result)

    def test_missing_state_never_blocks(self):
        result = prompt_gate.run(make_ctx(LOOP_PROMPT))
        self.assertNotIn("exit_code", result)

    def test_strict_block_false_warns_instead(self):
        cfg = copy.deepcopy(nav_config.DEFAULTS)
        cfg["workflow_enforcer_hook"]["strict_block"] = False
        result = prompt_gate.run(make_ctx(LOOP_PROMPT, cfg=cfg,
                                          check_shown=False))
        self.assertNotIn("exit_code", result)
        self.assertIn("LOOP MODE TRIGGER DETECTED", result["additional_context"])

    def test_no_loop_trigger_never_blocks_even_on_false(self):
        result = prompt_gate.run(
            make_ctx("please tidy the docs", check_shown=False))
        self.assertIsNone(result)


class HygieneTest(GateTestBase):
    def test_pilot_executor_passthrough(self):
        self.assertIsNone(
            prompt_gate.run(make_ctx(LOOP_PROMPT, check_shown=False,
                                     pilot=True)))

    def test_empty_prompt_is_silent(self):
        self.assertIsNone(prompt_gate.run(make_ctx()))

    def test_echoed_block_message_does_not_retrigger(self):
        # mem-034: re-fed block stderr + the harness 'Original prompt:' echo
        # must strip to nothing that matches LOOP_TRIGGERS.
        echoed = (
            sentinels.wrap("nav-workflow-block", prompt_gate.BLOCK_MESSAGE)
            + "\nOriginal prompt: " + LOOP_PROMPT
        )
        result = prompt_gate.run(make_ctx(echoed, check_shown=False))
        self.assertIsNone(result)

    def test_task_mode_disabled_suppresses_task_warn(self):
        cfg = copy.deepcopy(nav_config.DEFAULTS)
        cfg["task_mode"]["enabled"] = False
        result = prompt_gate.run(
            make_ctx("refactor the auth module across the codebase", cfg=cfg))
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# TASK-79 — judge overlay on the gate
# ---------------------------------------------------------------------------

from nav_hook_lib import judge as nav_judge  # noqa: E402


def _judgment(**kw):
    base = dict(is_task=0.9, wants_loop=0.05, complexity=0.2, complexity_confidence=0.95,
                ambiguity=0.3, ambiguity_confidence=0.9, dimensions={},
                model="jev-test", latency_ms=7,
                thresholds={"min_confidence": 0.6, "noul_low": 0.3, "noul_high": 0.7})
    base.update(kw)
    return nav_judge.Judgment(**base)


class TestGateJudge(GateTestBase):
    def test_disabled_by_default_no_call_and_v6_bytes(self):
        ctx = make_ctx(LOOP_PROMPT)
        calls = []
        real = nav_judge.call
        nav_judge.call = lambda *a, **k: calls.append(a) or None
        try:
            out = prompt_gate.run(ctx)
        finally:
            nav_judge.call = real
        self.assertEqual(calls, [])
        self.assertIn("LOOP MODE TRIGGER DETECTED: 'run until done'", out["additional_context"])
        self.assertNotIn("Judged by", out["additional_context"])

    def test_judged_no_silences_false_fire(self):
        ctx = make_ctx("## F. Loop mode\n| F1 | phase_detector.py |", check_shown=False)
        ctx._judgment = _judgment(wants_loop=0.1)  # pre-cached judgment
        self.assertIsNone(prompt_gate.run(ctx))    # no warn, and no strict block either

    def test_judged_yes_blocks_like_a_phrase(self):
        ctx = make_ctx("get every one of them finished, no check-ins", check_shown=False)
        ctx._judgment = _judgment(wants_loop=0.95)
        out = prompt_gate.run(ctx)
        self.assertEqual(out["exit_code"], 2)
        self.assertIn(prompt_gate.BLOCK_TAG, out["stderr"])

    def test_judged_warn_carries_model_line(self):
        ctx = make_ctx("clean up the hooks")
        ctx._judgment = _judgment(complexity=0.67, latency_ms=412)
        out = prompt_gate.run(ctx)
        text = out["additional_context"]
        self.assertIn("TASK MODE RECOMMENDED: complexity=0.67", text)
        self.assertIn("Judged by jev-test (412 ms)", text)
        self.assertIn("│ Mode: TASK", text)


class TestGateJudgeTelemetry(GateTestBase):
    def test_axes_recorded_into_state(self):
        ctx = make_ctx("clean up the hooks")
        ctx._judgment = _judgment(wants_loop=0.05, complexity=0.67)
        prompt_gate.run(ctx)
        self.assertEqual(ctx.state["judge"]["axes"]["loop"], {"agreed": 1})
        self.assertEqual(ctx.state["judge"]["axes"]["complexity"], {"overridden": 1})

    def test_nothing_recorded_without_judgment(self):
        ctx = make_ctx("clean up the hooks")
        prompt_gate.run(ctx)
        self.assertNotIn("judge", ctx.state)
