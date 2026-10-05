#!/usr/bin/env python3
"""prompt_modes op — reply-mode toggles + rule injection on UserPromptSubmit.

One responder-phase op (registry row after prompt_tier1) serves every row of
``nav_hook_lib.reply_modes.MODES`` (ADHD TASK-82, STE TASK-93):

  - Toggle: an exact phrase ("adhd mode on" / "ste mode off" / "adhd mode")
    flips or reports that mode's PERSONAL switch and answers with
    ``decision: block`` at zero model invocation (mem-053 channel, same as
    Tier-1; plain text, never a sentinel wrapper). Independent of
    ``tier1.enabled``.
  - Injection: while any mode resolves on, every other prompt carries the
    active rule blocks (table order, blank line between) as
    additional_context, ahead of the brief (registry order is merge order).
    Off means nothing is injected — the rules exist nowhere in the context.

Phrases, resolution and blocks live in ``nav_hook_lib.reply_modes``; the op
stays thin. Silent under the Pilot executor (no human reader). A repo pin
``<mode>.on`` wins over the personal switch, and a toggle phrase says so
instead of silently writing. When the v8 Navigator mod owns this op,
runtime._dispatch skips it before it runs (TASK-84).
"""
from __future__ import annotations

import json
import os

from nav_hook_lib import config, reply_modes, sentinels, signals


def _user_message(payload: dict) -> str:
    prompt = payload.get("prompt") or payload.get("user_message") or ""
    if not prompt:
        prompt = os.environ.get("CLAUDE_USER_MESSAGE", "")
    return sentinels.strip_all(prompt)


def _block(reason: str) -> dict:
    doc = json.loads(signals.prompt_block(reason))
    return {"decision": doc["decision"], "reason": doc["reason"]}


def _toggle_reason(mode, kind: str, ctx) -> str:
    label, word, path = mode.label, mode.key, reply_modes.personal_path(mode)
    if not reply_modes.mode_enabled(mode, ctx.config):
        return (f"{label} mode: disabled in this repo ({mode.config_key}.enabled is false "
                "in .agent/.nav-config.json or the .local override). Nothing changed.")
    pinned = config.get(ctx.config, f"{mode.config_key}.on")
    if kind == "status":
        line = reply_modes.status_line(mode, ctx.config) \
            or f"{label} mode: off (never switched on)."
        return line + f' Say "{word} mode on" or "{word} mode off".'
    wanted = kind == "on"
    if not reply_modes.set_personal(mode, wanted, ctx.now):
        return f"{label} mode: could not write the personal switch ({path}). Nothing changed."
    state = "on" if wanted else "off"
    if isinstance(pinned, bool):
        return (f"{label} mode: personal switch set to {state}, but this repo pins it "
                f"{'on' if pinned else 'off'} via {mode.config_key}.on in "
                ".agent/.nav-config.json (or the .local override). "
                "Remove the pin for the switch to apply here.")
    tail = ("Applies from your next prompt, in every repo. "
            f'Say "{word} mode off" to stop.' if wanted else
            "The rule block is no longer injected anywhere.")
    return f"{label} mode: {state} (personal, {path}). {tail}"


def run(ctx):
    if ctx.pilot_executor:
        return None  # no human reader
    message = _user_message(ctx.payload).strip()
    if not message:
        return None  # malformed/empty payload: nothing to answer or shape
    hit = reply_modes.classify(message)
    if hit:
        mode, kind = hit
        return _block(_toggle_reason(mode, kind, ctx))
    block = reply_modes.injection(ctx.config)
    return {"additional_context": block} if block else None
