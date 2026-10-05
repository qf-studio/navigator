#!/usr/bin/env python3
"""nav_hook_lib.reply_modes — per-person reply modes (TASK-82 ADHD, TASK-93 STE).

A reply mode is a rule block that rides every prompt while the mode is on and
exists nowhere in the context while it is off. Every mode is one row in
``MODES``; adding a mode is adding a row here and the mirrored row in
``hooks/mod/lib/reply_modes.ts``. Table order is injection order: reply-shape
rules (ADHD) come before sentence rules (STE), so the later block applies
inside the earlier one.

The switch is the person's, not the repo's:

  resolution:  repo config ``<config_key>.on`` (true/false pins it; null defers)
               > personal file ~/.config/navigator/<state_name>.json {"on": bool}
               > off

``reply_modes.enabled`` gates the op. ``<config_key>.enabled`` (seeded True)
only says that one mode's toggle phrases answer and its block may be injected.
Nothing is injected for anyone until they say "<word> mode on".
Stdlib + siblings only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from . import config, personal

OP_CONFIG_KEY = "reply_modes"
MAX_PHRASE_CHARS = 32
# Soft ceiling on the sum of every rule block (all modes on at once); asserted
# by tests so a new row cannot quietly double the per-prompt cost.
MAX_TOTAL_BLOCK_CHARS = 1600


@dataclass(frozen=True)
class Mode:
    key: str            # short word in toggle phrases: "adhd mode on"
    label: str          # human label in answers: "ADHD mode: on"
    config_key: str     # repo block: <config_key>.enabled / <config_key>.on
    state_name: str     # personal file: ~/.config/navigator/<state_name>.json
    rule_block: str
    extra_on: tuple = ()
    extra_off: tuple = ()

    # Exact toggle phrases (after _normalize). Deliberately no fuzzy matching:
    # a prompt that merely mentions a mode must never flip its switch.
    @property
    def on_phrases(self) -> frozenset:
        w = self.key
        return frozenset({
            f"{w} mode on", f"{w} mode: on", f"{w} on", f"enable {w} mode",
            f"start {w} mode", f"turn on {w} mode", f"{w} mode enable", *self.extra_on,
        })

    @property
    def off_phrases(self) -> frozenset:
        w = self.key
        return frozenset({
            f"{w} mode off", f"{w} mode: off", f"{w} off", f"disable {w} mode",
            f"stop {w} mode", f"turn off {w} mode", f"{w} mode disable", *self.extra_off,
        })

    @property
    def status_phrases(self) -> frozenset:
        w = self.key
        return frozenset({f"{w} mode", f"{w} mode?", f"{w} mode status", f"{w} status"})


# Rule blocks use declarative framing (facts about the reader, the shape that
# works) rather than imperatives — tool-adjacent injections that read as
# commands get flagged as prompt injection (mem-050); prompt-adjacent ones
# are safer, but the same style keeps the blocks robust.

# ADHD (TASK-82): the user's global rules (first four bullets) plus the
# i-have-adhd rules that add something (numbered steps, state restated, list
# cap, flat errors, no preamble, sub-two-minute closer) and its override cases.
ADHD_RULE_BLOCK = """\
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

# STE (TASK-93): a Part 1 subset of ASD-STE100 Issue 9 (Simplified Technical
# English). Sentence-level rules only; the ~900-word dictionary does not fit a
# developer conversation and is deliberately left out.
STE_RULE_BLOCK = """\
STE MODE: on (personal setting; "ste mode off" ends it)
The reader wants ASD-STE100 Simplified Technical English. The sentence style that works:
- One idea per sentence. Instructions have 20 words or fewer, descriptions 25 or fewer.
- Instructions use the imperative. Descriptions use the active voice and the present tense.
- One instruction per sentence. A paragraph has one topic and six sentences or fewer.
- No gerunds, no noun clusters over three words, no synonyms for one meaning.
- Full sentences with articles, not labels. Technical names stay as written in the code.
Error output, test results and quoted text stay verbatim. Applies to replies only, inside
any reply-shape rules above."""

MODES: tuple = (
    Mode("adhd", "ADHD", "adhd_mode", "adhd-mode", ADHD_RULE_BLOCK),
    Mode("ste", "STE", "ste_mode", "ste-mode", STE_RULE_BLOCK,
         extra_on=("use ste",), extra_off=("stop ste",)),
)

_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    text = _WS.sub(" ", (text or "").strip().lower())
    return text.rstrip(" .!").strip()


def by_key(key: str):
    return next((m for m in MODES if m.key == key), None)


def by_config_key(config_key: str):
    return next((m for m in MODES if m.config_key == config_key), None)


def classify(prompt: str):
    """(mode, 'on' | 'off' | 'status') for an exact toggle phrase, else None."""
    if not prompt or len(prompt) > MAX_PHRASE_CHARS:
        return None
    phrase = _normalize(prompt)
    for mode in MODES:
        if phrase in mode.on_phrases:
            return mode, "on"
        if phrase in mode.off_phrases:
            return mode, "off"
        if phrase in mode.status_phrases:
            return mode, "status"
    return None


def personal_on(mode: Mode):
    """The personal switch as a bool, or None when never set / unreadable."""
    value = personal.read(mode.state_name).get("on")
    return value if isinstance(value, bool) else None


def set_personal(mode: Mode, on: bool, now: float | None = None) -> bool:
    """Persist the personal switch. ``now`` is an epoch float (ctx.now)."""
    stamp = datetime.fromtimestamp(now, timezone.utc) if now is not None \
        else datetime.now(timezone.utc)
    return personal.write(mode.state_name, {
        "on": bool(on),
        "updated": stamp.replace(microsecond=0).isoformat(),
    })


def personal_path(mode: Mode):
    return personal.path(mode.state_name)


def mode_enabled(mode: Mode, cfg) -> bool:
    """``<config_key>.enabled`` — the mode's machinery is available (default True)."""
    return bool(config.get(cfg, f"{mode.config_key}.enabled", True))


def resolve(mode: Mode, cfg) -> tuple:
    """(on: bool, source: 'repo' | 'personal' | 'default') for a layered config."""
    pinned = config.get(cfg, f"{mode.config_key}.on")
    if isinstance(pinned, bool):
        return pinned, "repo"
    value = personal_on(mode)
    if isinstance(value, bool):
        return value, "personal"
    return False, "default"


def status_line(mode: Mode, cfg) -> str:
    """One human line for session start / status answers; '' when off by default."""
    on, source = resolve(mode, cfg)
    if source == "repo":
        where = f"pinned by repo config {mode.config_key}.on"
    elif source == "personal":
        where = f"personal switch, {personal_path(mode)}"
    else:
        return ""
    return f"{mode.label} mode: {'on' if on else 'off'} ({where})."


def status_lines(cfg) -> list:
    """One line per mode that someone switched explicitly; [] when all default."""
    lines = [status_line(mode, cfg) for mode in MODES if mode_enabled(mode, cfg)]
    return [line for line in lines if line]


def active_blocks(cfg) -> list:
    """Rule blocks of every enabled mode that resolves on, in table order."""
    return [mode.rule_block for mode in MODES
            if mode_enabled(mode, cfg) and resolve(mode, cfg)[0]]


def injection(cfg):
    """The additional_context text for a prompt, or None when no mode is on."""
    blocks = active_blocks(cfg)
    return "\n\n".join(blocks) if blocks else None
