#!/usr/bin/env python3
"""prompt_tier1 op — UserPromptSubmit Tier-1 deterministic responder (TASK-62 Phase 1).

Channel: mem-053 (S4 PASS, CC 2.1.205) — UserPromptSubmit block-as-answer via
``decision: block`` JSON answers at ZERO model invocation (num_turns=0). The
emitter is signals.prompt_block; exit-2 is deliberately impossible here (it
leaks hook command chrome into the visible answer — the losing spike shape).

Safety rails (plan risk register + mem-034):

  - EXACT-match table only, five seed commands, matched on the
    sentinels.strip_all()'d prompt, <=48 chars post-strip. No fuzzy matching:
    "nav stats please" reaches the model untouched.
  - Answers render as plain-text grot cards with the escape line in the footer
    border — NO sentinel wrapper (the harness draws a block reason as plain
    text, so an HTML-comment marker would show literally). Self-safe without
    one: decision:block is shown to the user, never auto-fed to the next prompt
    (S4/mem-053), and the exact-match + 48-char rail rejects any re-fed card.
  - Telemetry only, never behavior: a hit records ``turn.tier1_hit`` (+ the
    ``completion.tier1_fuse`` answered-this-turn marker the stop_state barrel
    re-arms); a near-identical re-prompt right after a hit increments
    ``tier1.false_positives`` (surfaced by /nav:stats) and still passes
    through to the model. "Near-identical" is an explicit similarity rule
    (TASK-68, _is_near_identical): the normalized prompt contains the hit
    command with at most SIMILARITY_MAX_EXTRA_TOKENS padding words, OR its
    token-set Jaccard against the command is >= SIMILARITY_MIN_JACCARD. A
    verbatim re-type (prompt == command) and a loosely-related prompt that
    only shares a word both clear neither rule and are not counted.
  - Per-rule off-switch ``tier1.rules.<id>: false``; whole feature seeds OFF
    (config.DEFAULTS tier1.enabled=false; the registry config gate skips the
    op, and run() re-checks for standalone callers).
  - ctx.pilot_executor bypasses ENTIRELY (no answer, no telemetry): a Pilot
    dispatch loop must never have its prompt swallowed by a responder.

Answers are computed deterministically from local project artifacts (runtime
state, layered config, .agent/.context-markers listing, knowledge graph
stats, plugin manifest) — never from the model.
"""
from __future__ import annotations

import json
import os

from nav_hook_lib import config, hio, judge, memory, sentinels, signals

ESCAPE_LINE = "reply 'ask claude' to run the model"
MAX_PROMPT_CHARS = 48  # post-strip guard: longer prompts are never matched
MARKERS_DIR = ".context-markers"
MAX_MARKERS_SHOWN = 10

# Near-identical re-prompt telemetry (TASK-68). A genuine rephrase of a just-
# answered Tier-1 command counts as a suspected false positive; a loosely-
# related prompt does not. TELEMETRY ONLY — never changes routing.
SIMILARITY_MAX_EXTRA_TOKENS = 3  # containment rule: command + <=3 padding words
SIMILARITY_MIN_JACCARD = 0.6     # token-set overlap rule (reordered rephrase)

# ---------------------------------------------------------------------------
# grot-style card renderer (Pilot TUI design system: rounded frame, titled top
# border, aligned rows, footer note). Monochrome — ANSI colour is not portable
# into a hook block reason, so the frame alone carries the identity. Every glyph
# used (box-drawing, ·, …) is a single terminal column, so len() == visual width.
# ---------------------------------------------------------------------------

CARD_WIDTH = 60  # total columns including the two border glyphs


def _fit(text: str, width: int) -> str:
    text = str(text)
    return text if len(text) <= width else text[: max(0, width - 1)] + "…"


def _border(left: str, right: str, note: str) -> str:
    label = f" {note} " if note else ""
    fill = CARD_WIDTH - 3 - len(label)
    if fill < 1:                      # note too long for the frame — clip it
        label = " " + _fit(note, CARD_WIDTH - 6) + " "
        fill = CARD_WIDTH - 3 - len(label)
    return f"{left}─{label}{'─' * fill}{right}"


def _row(text: str) -> str:
    inner = CARD_WIDTH - 2
    body = "  " + _fit(text, inner - 2)
    return "│" + body + " " * (inner - len(body)) + "│"


def _card(title: str, rows: list, footer: str) -> str:
    # One blank interior row top and bottom (grot card lines 1 & 8) so the
    # titled borders have breathing room from the content.
    lines = [_border("╭", "╮", title), _row("")]
    lines += [_row(r) for r in rows]
    lines += [_row(""), _border("╰", "╯", footer)]
    return "\n".join(lines)

# The five seed commands (Tier-1 whitelist growth is out of TASK-62 scope).
# Exact match against the lowercased, strip_all()'d, whitespace-trimmed
# prompt; rule ids double as the tier1.rules.<id> toggle keys.
COMMANDS = {
    "nav stats": "nav_stats",
    "show features": "show_features",
    "list markers": "list_markers",
    "graph health": "graph_health",
    "nav version": "nav_version",
}
RULE_COMMANDS = {rule: command for command, rule in COMMANDS.items()}

# Feature blocks listed by "show features" — every block carries .enabled in
# config.DEFAULTS, so the answer is total and deterministic.
FEATURE_BLOCKS = (
    "task_mode",
    "loop_mode",
    "simplification",
    "auto_update",
    "knowledge_graph",
    "multi_agent",
    "session_start_hook",
    "workflow_enforcer_hook",
    "brief_hook",
    "read_guard_hook",
    "task_graph_sync_hook",
    "profile_sync_hook",
    "workflow_state_hook",
    "compact_hook",
    "dispatcher",
    "tier1",
    "stop_completion",
    "jit_memory",
    "subagent_context",
    "failure_diagnosis",
    "config_guard",
    "setup_hook",
    "judge",
)


def _user_message(payload: dict) -> str:
    """Prompt from payload (legacy env fallback), strip_all()'d (mem-034)."""
    prompt = payload.get("prompt") or payload.get("user_message") or ""
    if not prompt:
        prompt = os.environ.get("CLAUDE_USER_MESSAGE", "")
    return sentinels.strip_all(prompt)


def _normalize(text: str) -> str:
    """Lowercase + collapse whitespace (used ONLY for near-identical telemetry)."""
    return " ".join(text.lower().split())


def _agent_dir(ctx):
    return hio.project_root(ctx.payload) / ".agent"


def _graph(ctx) -> dict:
    return hio.safe_json(_agent_dir(ctx) / "knowledge" / "graph.json") or {}


def _marker_names(ctx) -> list:
    try:
        markers = _agent_dir(ctx) / MARKERS_DIR
        if not markers.is_dir():
            return []
        return sorted(p.name for p in markers.iterdir() if p.is_file())
    except Exception:
        return []


def _plugin_version() -> str:
    plugin_dir = memory._plugin_dir()  # the lib's plugin-root resolver
    if plugin_dir is None:
        return "unknown"
    manifest = hio.safe_json(plugin_dir / ".claude-plugin" / "plugin.json") or {}
    version = manifest.get("version")
    return version if isinstance(version, str) and version else "unknown"


# ---------------------------------------------------------------------------
# Deterministic answer builders (one per rule id)
# ---------------------------------------------------------------------------

def _answer_nav_stats(ctx) -> str:
    stats = _graph(ctx).get("stats") or {}
    reads = ctx.state.get("reads") or {}
    tier1 = ctx.state.get("tier1") or {}
    meta = ctx.state.get("meta") or {}
    op_errors = meta.get("op_errors") if isinstance(meta.get("op_errors"), list) else []
    return _card("nav stats · zero model tokens", [
        "graph: {} nodes / {} edges / {} memories".format(
            stats.get("total_nodes", 0), stats.get("total_edges", 0),
            stats.get("memory_count", 0)),
        f"context markers: {len(_marker_names(ctx))}",
        f"reads this turn: {reads.get('turn_count', 0)}",
        "tier1: {} hits / {} suspected false positives".format(
            tier1.get("hits", 0), tier1.get("false_positives", 0)),
        f"recent op errors: {len(op_errors)}",
    ] + judge.summary_lines(ctx.state), ESCAPE_LINE)


def _answer_show_features(ctx) -> str:
    rows = []
    for block in FEATURE_BLOCKS:
        enabled = config.get(ctx.config, f"{block}.enabled", None)
        if enabled is None:
            status = "unset"
        else:
            status = "on" if enabled else "off"
        rows.append(f"{block}: {status}")
    return _card("show features · <block>.enabled", rows, ESCAPE_LINE)


def _answer_list_markers(ctx) -> str:
    names = _marker_names(ctx)
    if not names:
        return _card("list markers", [
            "No context markers in .agent/.context-markers/"], ESCAPE_LINE)
    rows = list(names[-MAX_MARKERS_SHOWN:])
    if len(names) > MAX_MARKERS_SHOWN:
        rows.insert(0, f"... showing the last {MAX_MARKERS_SHOWN}")
    return _card(f"list markers · {len(names)} total, newest last", rows,
                 ESCAPE_LINE)


def _answer_graph_health(ctx) -> str:
    graph = _graph(ctx)
    if not graph:
        return _card("graph health", [
            "No knowledge graph (.agent/knowledge/graph.json missing)",
            "say 'Initialize knowledge graph' to build one"], ESCAPE_LINE)
    stats = graph.get("stats") or {}
    concepts = graph.get("concept_index")
    return _card("graph health", [
        f"schema version: {graph.get('version', '?')}",
        f"last updated: {graph.get('last_updated', '?')}",
        "nodes: {} | edges: {} | memories: {}".format(
            stats.get("total_nodes", 0), stats.get("total_edges", 0),
            stats.get("memory_count", 0)),
        f"indexed concepts: {len(concepts) if isinstance(concepts, dict) else 0}",
    ], ESCAPE_LINE)


def _answer_nav_version(ctx) -> str:
    plugin_version = _plugin_version()
    config_version = ctx.config.get("version")
    config_line = config_version if isinstance(config_version, str) else "unset"
    if plugin_version == "unknown" or not isinstance(config_version, str):
        drift = "undetermined"
    elif plugin_version == config_version:
        drift = "none"
    else:
        drift = f"config {config_version} != plugin {plugin_version}"
    return _card("nav version", [
        f"Navigator plugin: {plugin_version}",
        f"project config version: {config_line}",
        f"version drift: {drift}",
    ], ESCAPE_LINE)


ANSWERS = {
    "nav_stats": _answer_nav_stats,
    "show_features": _answer_show_features,
    "list_markers": _answer_list_markers,
    "graph_health": _answer_graph_health,
    "nav_version": _answer_nav_version,
}


# ---------------------------------------------------------------------------
# Telemetry (state-only; never changes routing)
# ---------------------------------------------------------------------------

def _tier1_section(ctx) -> dict:
    section = ctx.state.get("tier1")
    if not isinstance(section, dict):
        section = {}
        ctx.state["tier1"] = section
    return section


def _record_hit(ctx, rule: str) -> None:
    turn = ctx.state.get("turn")
    if not isinstance(turn, dict):
        turn = {}
        ctx.state["turn"] = turn
    turn["tier1_hit"] = rule
    completion = ctx.state.get("completion")
    if not isinstance(completion, dict):
        completion = {}
        ctx.state["completion"] = completion
    # Answered-this-turn marker; the stop_state reset barrel re-arms it at
    # the next completed model turn (a Tier-1 hit itself fires no Stop).
    completion["tier1_fuse"] = True
    section = _tier1_section(ctx)
    section["hits"] = int(section.get("hits", 0) or 0) + 1


def _is_near_identical(normalized_prompt: str, command: str) -> bool:
    """True when the re-prompt is a genuine rephrase of the hit ``command``.

    Two named, telemetry-only rules (never routing):
      - containment + small padding: the prompt contains the command verbatim
        and adds at most SIMILARITY_MAX_EXTRA_TOKENS words ("nav stats please");
      - token-set overlap: Jaccard(prompt tokens, command tokens) >=
        SIMILARITY_MIN_JACCARD (a reordered / reworded near-duplicate).

    A verbatim re-type (prompt == command, a whitespace-only miss of the exact
    matcher) and a prompt sharing only a single word both clear neither rule.
    """
    if normalized_prompt == command:
        return False
    prompt_tokens = normalized_prompt.split()
    command_tokens = command.split()
    if not prompt_tokens or not command_tokens:
        return False
    if command in normalized_prompt:
        extra = len(prompt_tokens) - len(command_tokens)
        if 0 <= extra <= SIMILARITY_MAX_EXTRA_TOKENS:
            return True
    prompt_set, command_set = set(prompt_tokens), set(command_tokens)
    union = prompt_set | command_set
    if not union:
        return False
    return (len(prompt_set & command_set) / len(union)) >= SIMILARITY_MIN_JACCARD


def _count_false_positive(ctx, normalized_prompt: str) -> None:
    """Hit followed by a near-identical re-prompt => telemetry only.

    The user answered a Tier-1 block by rephrasing the same command — a
    signal the deterministic answer was NOT what they wanted. Counted for
    /nav:stats; the prompt still passes through to the model unchanged.
    """
    turn = ctx.state.get("turn")
    if not isinstance(turn, dict):
        return
    command = RULE_COMMANDS.get(turn.get("tier1_hit"))
    if not command:
        return
    if _is_near_identical(normalized_prompt, command):
        section = _tier1_section(ctx)
        section["false_positives"] = int(section.get("false_positives", 0) or 0) + 1
        turn.pop("tier1_hit", None)  # one-shot window per hit


def run(ctx):
    # Pilot bypass: ENTIRELY — no answer, no telemetry (plan decision).
    if ctx.pilot_executor:
        return None
    # Belt for standalone callers; the registry config gate already skips
    # the op when tier1.enabled is false (which is the seeded default).
    if not config.get(ctx.config, "tier1.enabled", False):
        return None

    candidate = _user_message(ctx.payload).strip()
    if not candidate or len(candidate) > MAX_PROMPT_CHARS:
        return None

    rule = COMMANDS.get(candidate.lower())
    if rule and config.get(ctx.config, f"tier1.rules.{rule}", True) is not False:
        # Record BEFORE building: the nav-stats answer must reflect the hit
        # it is itself producing (tier1.hits includes this one).
        _record_hit(ctx, rule)
        # The builder returns a complete grot card. No sentinel wrapper: the
        # harness renders a block reason as PLAIN TEXT (HTML comments show
        # literally), and Tier-1 is self-safe without one — decision:block is
        # shown to the user, never auto-fed to the next prompt (S4/mem-053),
        # and the exact-match + 48-char guard rejects any re-fed card.
        reason = ANSWERS[rule](ctx)
        # Channel shape comes from the spike-proven emitter (mem-053) —
        # decision:block JSON, NEVER exit-2. The runtime merges the parsed
        # keys into the single output document.
        doc = json.loads(signals.prompt_block(reason))
        return {"decision": doc["decision"], "reason": doc["reason"]}

    # Not an exact command: pass through (no fuzzy match, mem-053 rail),
    # but count a near-identical re-prompt right after a hit as a suspected
    # false positive (telemetry surfaced by /nav:stats).
    _count_false_positive(ctx, _normalize(candidate))
    return None
