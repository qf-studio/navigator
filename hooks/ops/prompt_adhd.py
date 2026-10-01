#!/usr/bin/env python3
"""prompt_adhd op — ADHD mode toggle + rule injection on UserPromptSubmit (TASK-82).

Two jobs in one responder-phase op (registry row after prompt_tier1):

  - Toggle: an exact phrase ("adhd mode on" / "adhd mode off" / "adhd mode")
    flips or reports the PERSONAL switch and answers with ``decision: block``
    at zero model invocation (mem-053 channel, same as Tier-1; plain text,
    never a sentinel wrapper). Independent of ``tier1.enabled``.
  - Injection: while the resolved state is on, every other prompt carries
    ``nav_hook_lib.adhd.RULE_BLOCK`` as additional_context, ahead of the
    brief (registry order is merge order). Off means nothing is injected —
    the rules exist nowhere in the context.

Resolution and phrases live in ``nav_hook_lib.adhd``; the op stays thin.
Silent under the Pilot executor (no human reader) and when the repo pins
``adhd_mode.on`` — a pin wins over the personal switch, and a toggle phrase
says so instead of silently writing.
"""
from __future__ import annotations

import json
import os

from nav_hook_lib import adhd, config, sentinels, signals


def _user_message(payload: dict) -> str:
    prompt = payload.get("prompt") or payload.get("user_message") or ""
    if not prompt:
        prompt = os.environ.get("CLAUDE_USER_MESSAGE", "")
    return sentinels.strip_all(prompt)


def _block(reason: str) -> dict:
    doc = json.loads(signals.prompt_block(reason))
    return {"decision": doc["decision"], "reason": doc["reason"]}


def _toggle_reason(kind: str, ctx) -> str:
    pinned = config.get(ctx.config, "adhd_mode.on")
    if kind == "status":
        line = adhd.status_line(ctx.config) or "ADHD mode: off (never switched on)."
        return line + ' Say "adhd mode on" or "adhd mode off".'
    wanted = kind == "on"
    if not adhd.set_personal(wanted, ctx.now):
        return ("ADHD mode: could not write the personal switch "
                f"({adhd.personal.path(adhd.STATE_NAME)}). Nothing changed.")
    state = "on" if wanted else "off"
    if isinstance(pinned, bool):
        return (f"ADHD mode: personal switch set to {state}, but this repo pins it "
                f"{'on' if pinned else 'off'} via adhd_mode.on in .agent/.nav-config.json "
                f"(or the .local override). Remove the pin for the switch to apply here.")
    tail = ("Applies from your next prompt, in every repo. "
            'Say "adhd mode off" to stop.' if wanted else
            "The rule block is no longer injected anywhere.")
    return f"ADHD mode: {state} (personal, {adhd.personal.path(adhd.STATE_NAME)}). {tail}"


def run(ctx):
    if ctx.pilot_executor:
        return None
    message = _user_message(ctx.payload).strip()
    kind = adhd.classify(message)
    if kind:
        return _block(_toggle_reason(kind, ctx))
    on, _source = adhd.resolve(ctx.config)
    if not on:
        return None
    return {"additional_context": adhd.RULE_BLOCK}
