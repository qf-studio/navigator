#!/usr/bin/env python3
"""nav_hook_lib.adhd — ADHD mode: a per-person output-shaping switch (TASK-82).

One rule block, injected on every prompt while the mode is on, and gone from
the context the moment it is off. The switch is the person's, not the repo's:

  resolution:  repo config ``adhd_mode.on`` (true/false pins it; null defers)
               > personal file ~/.config/navigator/adhd-mode.json {"on": bool}
               > off

``adhd_mode.enabled`` (seeded True) only says the machinery is available —
toggle phrases answer and the block can be injected. Nothing is injected for
anyone until they say "adhd mode on". Stdlib + siblings only.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from . import config, personal

STATE_NAME = "adhd-mode"
CONFIG_KEY = "adhd_mode"
MAX_PHRASE_CHARS = 32

# Exact toggle phrases (after _normalize). Deliberately no fuzzy matching:
# a prompt that merely mentions ADHD must never flip the switch.
ON_PHRASES = frozenset({
    "adhd mode on", "adhd mode: on", "adhd on", "enable adhd mode",
    "start adhd mode", "turn on adhd mode", "adhd mode enable",
})
OFF_PHRASES = frozenset({
    "adhd mode off", "adhd mode: off", "adhd off", "disable adhd mode",
    "stop adhd mode", "turn off adhd mode", "adhd mode disable",
})
STATUS_PHRASES = frozenset({"adhd mode", "adhd mode?", "adhd mode status", "adhd status"})

# The rule block. Declarative framing (facts about the reader, the shape that
# works) rather than imperatives — tool-adjacent injections that read as
# commands get flagged as prompt injection (mem-050); prompt-adjacent ones
# are safer, but the same style keeps the block robust. Built from the user's
# global rules (first four bullets) plus the i-have-adhd rules that add
# something (numbered steps, state restated, list cap, flat errors, no
# preamble, sub-two-minute closer) and its override cases.
RULE_BLOCK = """\
ADHD MODE: on (personal setting; "adhd mode off" ends it)
The reader has ADHD. The reply shape that works for them:
- First line: the ONE next action. Time-critical items first, the deadline in bold.
- Bullets over prose. Lists hold at most 5 items; longer ones split into now / later.
- Multi-step work: numbered, one bounded action per step, "step k of n" restated each turn.
- Several things pending: the single most important one is named, not a flat list.
- Errors: cause and fix in a flat tone. Wins stated plainly.
- No preamble, no recap, no pleasantries. The reply ends with one action under two minutes.
Kept in full regardless: error output, test results, anything the user asked to have
explained, and every warning before a destructive action.
Applies to replies only, not to files, reports or commit messages."""

_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    text = _WS.sub(" ", (text or "").strip().lower())
    return text.rstrip(" .!").strip()


def classify(prompt: str):
    """'on' | 'off' | 'status' for an exact toggle phrase, else None."""
    if not prompt or len(prompt) > MAX_PHRASE_CHARS:
        return None
    phrase = _normalize(prompt)
    if phrase in ON_PHRASES:
        return "on"
    if phrase in OFF_PHRASES:
        return "off"
    if phrase in STATUS_PHRASES:
        return "status"
    return None


def personal_on():
    """The personal switch as a bool, or None when never set / unreadable."""
    value = personal.read(STATE_NAME).get("on")
    return value if isinstance(value, bool) else None


def set_personal(on: bool, now: float | None = None) -> bool:
    """Persist the personal switch. ``now`` is an epoch float (ctx.now)."""
    stamp = datetime.fromtimestamp(now, timezone.utc) if now is not None \
        else datetime.now(timezone.utc)
    return personal.write(STATE_NAME, {
        "on": bool(on),
        "updated": stamp.replace(microsecond=0).isoformat(),
    })


def resolve(cfg) -> tuple:
    """(on: bool, source: 'repo' | 'personal' | 'default') for a layered config."""
    pinned = config.get(cfg, f"{CONFIG_KEY}.on")
    if isinstance(pinned, bool):
        return pinned, "repo"
    value = personal_on()
    if isinstance(value, bool):
        return value, "personal"
    return False, "default"


def status_line(cfg) -> str:
    """One human line for session start / status answers; '' when off by default."""
    on, source = resolve(cfg)
    if source == "repo":
        where = "pinned by repo config adhd_mode.on"
    elif source == "personal":
        where = f"personal switch, {personal.path(STATE_NAME)}"
    else:
        return ""
    return f"ADHD mode: {'on' if on else 'off'} ({where})."
