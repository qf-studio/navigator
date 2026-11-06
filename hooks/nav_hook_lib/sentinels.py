#!/usr/bin/env python3
"""
Navigator hook-runtime sentinels — tag registry, strip primitive, stderr emitter.

This module is the ONLY place under hooks/ allowed to write to stderr, and the
only owner of sentinel-tag knowledge. Two mem-034 rules become structure here:

  1. No op scans unstripped text: callers run ``strip_all()`` over any prompt /
     transcript text before phrase matching, so echoed block notices cannot
     recursively re-trigger a blocker.
  2. Stderr never leaks trigger phrases: ``emit_stderr()`` is the sole stderr
     writer and redacts every phrase in its ``redact`` list before writing.

Residual risk (mem-053): on UserPromptSubmit block messages Claude Code
appends ``Original prompt: <trigger>`` OUTSIDE any sentinel wrap, so tag
stripping alone cannot keep the trigger phrase out of scanned text.
``strip_all()`` therefore also removes ``Original prompt:`` lines — but ONLY
when at least one sentinel was actually removed from the text, so ordinary
user text is never touched. The rule for every gate: match on strip_all()'d
text AND redact triggers on emit (both halves are required; neither alone
closes the recursion loop).

Pure stdlib. See .agent/knowledge/memories/pitfalls/mem-034.md and mem-053.
"""

import re
import sys

REDACTION_PLACEHOLDER = "[redacted]"

# ---------------------------------------------------------------------------
# Tag registry — enumerated from the v6 sources (sweep 2026-07-10, TASK-59).
#
# kind "block":  paired tags wrapping a whole block notice; Claude Code echoes
#                blocked stderr into the next prompt's context, so strip_all()
#                excises the entire open..close span (content included).
# kind "marker": standalone idempotence marker line (no close tag, no wrapped
#                span); strip_all() removes only the marker string itself and
#                leaves surrounding content intact.
#
# status "current": emitted by a live v6 hook today.
# status "legacy":  no longer emitted, but may persist in old transcripts and
#                   markers — strip_all() must keep removing these forever.
#                   The v6 sweep (hooks/*.py, skills/*/functions/*.py, plus
#                   git-history pickaxe over retired hooks) found no retired
#                   tags, so the legacy shelf ships empty; new entries land
#                   here when a tag is renamed or retired, never deleted.
# ---------------------------------------------------------------------------
TAGS = {
    "nav-workflow-block": {
        "open": "<nav-workflow-block>",
        "close": "</nav-workflow-block>",
        "kind": "block",
        "status": "current",
        "source": "hooks/ops/prompt_gate.py",
    },
    "nav-read-guard-block": {
        "open": "<nav-read-guard-block>",
        "close": "</nav-read-guard-block>",
        "kind": "block",
        "status": "current",
        "source": "hooks/ops/read_guard.py",
    },
    "nav-task-doc-guard-block": {
        "open": "<nav-task-doc-guard-block>",
        "close": "</nav-task-doc-guard-block>",
        "kind": "block",
        "status": "current",
        "source": "hooks/ops/task_doc_guard.py",
    },
    "nav-session-start-injected:v1": {
        "open": "<!-- nav-session-start-injected:v1 -->",
        "close": None,
        "kind": "marker",
        "status": "current",
        "source": "hooks/ops/session_start.py",
    },
    # NOTE: Tier-1 answers (ops/prompt_tier1.py) are deliberately NOT wrapped —
    # a block reason renders as plain text, so any marker shows literally, and
    # Tier-1 is self-safe via its exact-match + 48-char rail (S4/mem-053). No
    # nav-t1-response tag exists.
}

# Precompiled span patterns for block tags (open..close, DOTALL).
_BLOCK_PATTERNS = [
    re.compile(re.escape(spec["open"]) + r".*?" + re.escape(spec["close"]), re.DOTALL)
    for spec in TAGS.values()
    if spec["kind"] == "block"
]

# Claude Code's harness echo on UserPromptSubmit block messages (mem-053):
# appended OUTSIDE any sentinel wrap, so it must be stripped separately —
# but only after a sentinel proved the text carries hook output (see
# strip_all).
_ORIGINAL_PROMPT_LINE = re.compile(r"^\s*Original prompt:.*$", re.MULTILINE)


def wrap(tag, text):
    """Wrap ``text`` in the named sentinel tag; returns the composed string.

    block tags:  open + newline + text + newline + close (the v6 stderr shape).
    marker tags: marker line prepended to text (the v6 nav_session_start shape,
                 where the sentinel is the first line of the injected payload).

    Raises KeyError for a tag not in the registry — unknown tags are a bug,
    never a soft fallback.
    """
    spec = TAGS[tag]
    if spec["kind"] == "block":
        return spec["open"] + "\n" + text + "\n" + spec["close"]
    return spec["open"] + "\n" + text


def strip_all(text):
    """Remove every registered sentinel (current AND legacy) from ``text``.

    - block tags: the whole open..close span is excised, wrapped content
      included; orphaned open/close tags (e.g. a truncated echo) are also
      removed defensively.
    - marker tags: only the marker string is removed; surrounding content
      survives.
    - harness echo (mem-053): when at least one sentinel WAS removed, any
      ``Original prompt: ...`` line is removed too — Claude Code appends that
      echo to UserPromptSubmit block messages outside the sentinel wrap, so
      the trigger phrase would otherwise survive stripping and re-trigger the
      gate. Targeted on purpose: text without sentinels is returned with its
      ``Original prompt:`` lines (ordinary user words) intact.

    Idempotent. This is the strip-first primitive every op must run before
    scanning prompt/transcript text for trigger phrases (mem-034).
    """
    if not text:
        return text
    original = text
    for pattern in _BLOCK_PATTERNS:
        text = pattern.sub("", text)
    for spec in TAGS.values():
        text = text.replace(spec["open"], "")
        if spec["close"]:
            text = text.replace(spec["close"], "")
    if text != original:
        text = _ORIGINAL_PROMPT_LINE.sub("", text)
    return text


def redact_phrases(text, phrases):
    """Replace each phrase (case-insensitive) with the redaction placeholder."""
    if not phrases:
        return text
    for phrase in phrases:
        if not phrase:
            continue
        text = re.sub(re.escape(phrase), REDACTION_PLACEHOLDER, text, flags=re.IGNORECASE)
    return text


def emit_stderr(text, redact=None):
    """Write ``text`` to stderr — THE only stderr writer under hooks/ (v7).

    ``redact`` is an iterable of phrases (e.g. LOOP_TRIGGERS) that must never
    reach stderr verbatim: Claude Code echoes blocked stderr into the next
    prompt's context, and an echoed trigger phrase re-triggers the block
    recursively (mem-034). Each phrase is replaced case-insensitively with
    ``[redacted]`` before writing. Output always ends with a single newline.
    """
    text = redact_phrases(text, redact)
    if not text.endswith("\n"):
        text += "\n"
    sys.stderr.write(text)
