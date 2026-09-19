#!/usr/bin/env python3
"""prompt_gate op — UserPromptSubmit workflow-enforcement gate.

Parity port of hooks/workflow_enforcer.py (TASK-61 Phase 5, coupled with
ops/stop_state.py — mem-037: the pair never splits). v6 rules preserved:

  - Soft warn (context injection) when a loop trigger or a Task-Mode-grade
    complexity score is detected: the WORKFLOW CHECK reminder block, exactly
    the v6 stdout bytes (the runtime routes UserPromptSubmit context-only
    output over the same plain-stdout channel v6 printed to).
  - Hard block (exit 2 + sentinel-wrapped stderr) ONLY when ALL of:
      1. a Loop Mode trigger is in the current prompt,
      2. the prior turn stamped check_shown == False (the tristate written
         by ops/stop_state.py — True/None never block, mem-037),
      3. workflow_enforcer_hook.strict_block is true (default true).
  - PILOT passthrough: ctx.pilot_executor short-circuits everything (the v6
    per-hook check, kept even though the runtime merge belt also guards).

mem-034 discipline, both halves:
  - the prompt is sentinels.strip_all()'d BEFORE trigger matching, so an
    echoed block notice (or its 'Original prompt:' harness echo) can never
    recursively re-trigger the block;
  - the block stderr is sentinel-wrapped AND redact_phrases()'d against
    LOOP_TRIGGERS, so no trigger phrase can leave through stderr.

TASK-79: when ``judge.enabled`` (ships OFF) a typed judgment overlays the
loop-trigger and complexity heuristics per axis when decisive; the WORKFLOW
CHECK block then carries one extra "Judged by" line. Disabled or failed judge
== the exact v6 bytes.

State source is the schema-2 runtime state (turn.signals.check_shown)
instead of v6's .nav-workflow-state.json — the one sanctioned parity delta.
The block message names the v7 file/keys accordingly.
"""
from __future__ import annotations

import os

from nav_hook_lib import config, judge, scoring, sentinels

BLOCK_TAG = "nav-workflow-block"

# The v6 block notice, minus the sentinel wrap (sentinels.wrap adds it) and
# with the state-file remedy updated to the schema-2 runtime state file
# (the sanctioned internal-state-path delta). Addressed to the USER: a
# UserPromptSubmit exit-2 blocks the prompt before the model runs.
BLOCK_MESSAGE = (
    "Navigator workflow_enforcer: blocked.\n"
    "  Why: the prior assistant turn skipped its required workflow "
    "check block, but your prompt requests autonomous iteration.\n"
    "  State: .agent/.nav-runtime-state.json turn.signals.check_shown=false\n"
    "  How to proceed (your choice):\n"
    "    1. Send any different prompt that does not request "
    "autonomous iteration. The next assistant response will "
    "restore state; then retry your original prompt.\n"
    "    2. Edit .agent/.nav-runtime-state.json and set "
    "turn.signals.check_shown=true.\n"
    "    3. Disable strict enforcement: set "
    "workflow_enforcer_hook.strict_block=false in "
    ".agent/.nav-config.json."
)


def _user_message(payload: dict) -> str:
    """Prompt from payload (legacy env fallback), strip_all()'d (mem-034)."""
    prompt = payload.get("prompt") or payload.get("user_message") or ""
    if not prompt:
        prompt = os.environ.get("CLAUDE_USER_MESSAGE", "")
    return sentinels.strip_all(prompt)


def _prior_check_shown(state: dict):
    """turn.signals.check_shown tristate from the runtime state (schema 2)."""
    turn = state.get("turn")
    if not isinstance(turn, dict):
        return None
    signals = turn.get("signals")
    if not isinstance(signals, dict):
        return None
    return signals.get("check_shown")


def _warn_lines(result: dict, task_mode_enabled: bool) -> list:
    """The v6 soft-warn stdout, line by line (byte parity with v6 print())."""
    warnings = []
    if result["loop_mode"]:
        trigger = result.get("loop_trigger", "unknown")
        warnings.append(f"⚠️  LOOP MODE TRIGGER DETECTED: '{trigger}'")
        warnings.append("   Show NAVIGATOR_STATUS blocks and use EXIT_SIGNAL.")
    if result["task_mode"] and task_mode_enabled:
        score = result.get("complexity", 0)
        warnings.append(f"⚠️  TASK MODE RECOMMENDED: complexity={score}")
        warnings.append("   Show phase tracking (RESEARCH → IMPL → VERIFY → COMPLETE).")
    if not warnings:
        return []
    judge_info = result.get("judge")
    if judge_info:
        warnings.append(
            f"ℹ️  Judged by {judge_info.get('model') or 'judge'} "
            f"({judge_info.get('latency_ms', 0)} ms)")
    return warnings + [
        "",
        "Remember to show WORKFLOW CHECK block!",
        "┌─────────────────────────────────────┐",
        "│ WORKFLOW CHECK                      │",
        "├─────────────────────────────────────┤",
        f"│ Loop trigger: {'YES' if result['loop_mode'] else 'NO':17} │",
        f"│ Complexity: {result.get('complexity', 0):<19} │",
        f"│ Mode: {result['recommended_mode']:<24} │",
        "└─────────────────────────────────────┘",
    ]


def run(ctx):
    # v6 per-hook PILOT escape hatch, preserved on top of the runtime belt.
    if ctx.pilot_executor:
        return None

    message = _user_message(ctx.payload)
    if not message:
        return None

    strict_block = bool(
        config.get(ctx.config, "workflow_enforcer_hook.strict_block", True))
    task_mode_enabled = bool(config.get(ctx.config, "task_mode.enabled", True))

    # TASK-79: typed judge overlay (judge.enabled ships OFF -> None -> pure
    # heuristics). Cached on ctx so prompt_brief reuses the same answer.
    judgment = judge.for_ctx(ctx, message)
    result = scoring.detect_workflow(message, judgment=judgment)

    # Decide block first; the soft warn is suppressed when blocking so the
    # only emitted text is the sentinel-wrapped stderr (mem-034).
    will_block = False
    if strict_block and result["loop_mode"]:
        will_block = _prior_check_shown(ctx.state) is False

    if will_block:
        stderr = sentinels.wrap(BLOCK_TAG, BLOCK_MESSAGE)
        # Redaction belt: no LOOP_TRIGGERS phrase may leave via stderr —
        # Claude Code echoes blocked stderr into the next prompt (mem-034).
        stderr = sentinels.redact_phrases(stderr, scoring.LOOP_TRIGGERS)
        return {"exit_code": 2, "stderr": stderr}

    lines = _warn_lines(result, task_mode_enabled)
    if not lines:
        return None
    return {"additional_context": "\n".join(lines)}
