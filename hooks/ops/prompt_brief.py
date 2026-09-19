#!/usr/bin/env python3
"""prompt_brief op — UserPromptSubmit intent-brief injector.

Parity port of hooks/nav_brief.py (TASK-61 Phase 6). Stateless and
non-blocking, byte-identical v6 behavior:

  - Scores the (strip_all'd, mem-034) prompt with scoring.score_ambiguity;
    below threshold / question / confirmation / not task-shaped -> silent.
  - At/above threshold on a task-shaped prompt, injects the NAV-BRIEF
    instruction block, pre-filled with knowledge-graph memories recalled via
    nav_hook_lib.memory (v6 semantics: 3s timeout, limit 5, compact format,
    silence on ANY recall failure), truncated to memory_budget_chars.
  - PILOT passthrough: a dispatch loop has no human to answer a brief's
    open questions (v6 parity with workflow_enforcer's escape hatch).

Runs in the injectors phase: a prompt_gate block short-circuits this op —
same observable composition as v6 (a blocked prompt surfaced no brief).
TASK-79: with ``judge.enabled`` (ships OFF) the typed judgment decides
task-shapedness, ambiguity and the undefined rows when decisive; otherwise
the heuristic answers, byte-for-byte as before.

``brief.pending`` exists in the schema-2 state but is NOT populated here
(TASK-56 deferral recorded in the task doc); the op stays stateless.
"""
from __future__ import annotations

import os
import re

from nav_hook_lib import config, hio, judge, memory, scoring, sentinels

RECALL_TIMEOUT = 3
RECALL_LIMIT = 5
DEFAULT_THRESHOLD = 0.5
DEFAULT_MEMORY_BUDGET = 1200
MAX_CONCEPTS = 8

# Concept-extraction stopwords (v6 nav_brief.py, verbatim).
CONCEPT_STOPWORDS = {
    "this", "that", "these", "those", "with", "from", "into", "onto",
    "over", "under", "about", "after", "before", "please", "then",
    "them", "they", "their", "have", "been", "will", "would", "should",
    "could", "make", "sure", "need", "want", "like", "some", "more",
    "when", "what", "where", "which", "until", "done", "everything",
}

_CONCEPT_RE = re.compile(r"[a-z][a-z\-_]{3,}")


def _user_message(payload: dict) -> str:
    """Prompt from payload (legacy env fallback), strip_all()'d (mem-034)."""
    prompt = payload.get("prompt") or payload.get("user_message") or ""
    if not prompt:
        prompt = os.environ.get("CLAUDE_USER_MESSAGE", "")
    return sentinels.strip_all(prompt)


def _extract_concepts(message: str) -> list:
    """Up to MAX_CONCEPTS lowercase word-ish tokens, stopwords dropped (v6)."""
    concepts = []
    for token in _CONCEPT_RE.findall(message.lower()):
        if token in CONCEPT_STOPWORDS or token in concepts:
            continue
        concepts.append(token)
        if len(concepts) >= MAX_CONCEPTS:
            break
    return concepts


def _recall_memories(ctx, message: str, budget_chars: int) -> str:
    """Ranked-memory summary via nav_hook_lib.memory; '' on any failure."""
    concepts = _extract_concepts(message)
    if not concepts:
        return ""
    agent_dir = hio.project_root(ctx.payload) / ".agent"
    text = memory.recall(concepts=concepts, agent_dir=agent_dir,
                         limit=RECALL_LIMIT, timeout_s=RECALL_TIMEOUT)
    return text[:budget_chars]


def _brief_lines(result: dict, threshold: float, memories: str,
                 contradiction_field: bool = True) -> list:
    """The v6 emit_brief_instruction stdout, line by line (byte parity when
    `contradiction_field` is False; TASK-72 adds the optional TRIZ row)."""
    lines = [
        f"🧭 NAV-BRIEF: ambiguous task-shaped prompt "
        f"(score={result['score']}, threshold={threshold})"
    ]
    if result["undefined_dimensions"]:
        lines.append(f"Undefined: {', '.join(result['undefined_dimensions'])}")
    fields = "  Goal | Scope | Approach | Limits | Verify | Won't do"
    if contradiction_field:
        fields += " | Contradiction"
    lines += ["", "Render a one-screen INTENT BRIEF before writing any code:", fields]
    if contradiction_field:
        lines.append(
            "Contradiction: \"improving X worsens Y\" or \"none\". If declared, "
            "query prior resolutions before Approach (skill: nav-brief).")
    lines += [
        "Pre-fill defaults from the memories below when present. "
        "Max 2 open questions.",
        "Wait for user confirmation before implementation. (skill: nav-brief)",
    ]
    if memories:
        lines += ["", "## Relevant Memories", memories]
    return lines


def run(ctx):
    # v6 per-hook PILOT escape hatch, preserved on top of the runtime belt.
    if ctx.pilot_executor:
        return None

    message = _user_message(ctx.payload)
    if not message:
        return None

    threshold = float(
        config.get(ctx.config, "brief_hook.ambiguity_threshold", DEFAULT_THRESHOLD))
    budget_chars = int(
        config.get(ctx.config, "brief_hook.memory_budget_chars",
                   DEFAULT_MEMORY_BUDGET))

    # TASK-79: same cached judgment prompt_gate used (None when disabled).
    judgment = judge.for_ctx(ctx, message)
    result = scoring.score_ambiguity(message, judgment=judgment)
    judge.record_axes(ctx.state, (result.get("judge") or {}).get("axes"))
    if not result["task_shaped"] or result["score"] < threshold:
        return None

    memories = _recall_memories(ctx, message, budget_chars)
    contradiction_field = bool(
        config.get(ctx.config, "brief_hook.contradiction_field", True))
    return {"additional_context": "\n".join(
        _brief_lines(result, threshold, memories, contradiction_field))}
