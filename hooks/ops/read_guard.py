#!/usr/bin/env python3
"""read_guard op — `.agent/` bulk-read guard gate (TASK-61 Phase 4).

Parity port of hooks/nav_read_guard.py. PreToolUse(Read) gate: counts
non-allowlisted reads of `.agent/` files per turn and escalates when the
count crosses thresholds:

  - warn at ``warn_threshold`` (default 3): stderr advisory, exit 0;
  - escalate at ``escalate_threshold`` (default 5):
      * ``strict_block`` true (default) → exit 2 + sentinel-wrapped stderr
        block (the deny-only channel — mem-035/mem-054: no advisory
        stdout/additionalContext output; the spike-gated advisory redesign
        is explicitly NOT this task);
      * ``strict_block`` false → stderr advisory only, exit 0.

v6 fidelity:
  - Counter moves from v6's .nav-read-counter.json to the schema-2 runtime
    state (``ctx.state['reads'].turn_count`` — the one sanctioned parity
    delta). Session-change reset is now lib-owned (state.load drops the
    session-scoped ``reads`` section on session mismatch, replacing v6's
    session_id field check); the Stop op remains the primary reset.
  - Per-turn counting is IDEMPOTENT per Read tool-use (TASK-66). The counter
    represents *unique* qualifying Read tool-uses, not dispatch invocations:
    a single Read tool-use can fire the PreToolUse surface more than once
    (dual hook wiring across the v6->v7 migration, or a harness double-fire),
    and counting per dispatch made N reads reach 2N — the block escalated on
    the 3rd read instead of the 5th. Each qualifying Read is now keyed on its
    ``tool_use_id`` (present on real payloads — verified by the read_guard
    golden captured live) and counted EXACTLY once; a repeated dispatch of an
    already-counted id is a no-op that re-evaluates the same threshold.
    Payloads with no id fall back to per-dispatch counting (older harnesses
    that fire exactly once), preserving prior behavior and the goldens.
  - The 300s ``stale_after_seconds`` staleness window stays INSIDE this op
    (v6 semantics; the state section's 2h TTL is a coarser lib backstop,
    per the TASK-59 review note): a counter whose ``updated_at`` predates
    the window is treated as fresh-from-zero, guarding against a missed
    Stop reset (mem-036). Missing/invalid timestamps are NOT stale —
    stop_state's reset barrel writes ``{"turn_count": 0}`` without one.
  - Block stderr keeps the v6 sentinel wrap (nav-read-guard-block) and
    deliberately omits the triggering file_path — no payload-derived
    substrings that could become future recursive-trigger surfaces
    (mem-034); text routes through the result ``stderr`` key.
  - ``.agent/`` presence and ``read_guard_hook.enabled`` gates are
    runtime-owned (dispatch early-out + OpSpec.config_key).

No ctx.pilot_executor check on purpose: v6 had none (the guard blocked under
Pilot too); the v7 runtime belt strips the exit-2 under the Pilot executor,
which is the sanctioned safety improvement over v6.
"""
from __future__ import annotations

from pathlib import Path

from nav_hook_lib import config, hio, sentinels

# Files in `.agent/` that Navigator itself reads during legitimate session
# start or on-demand patterns; exempt from the counter (v6 defaults, also
# mirrored in config.DEFAULTS["read_guard_hook"]["allowlist"]).
DEFAULT_ALLOWLIST = frozenset({
    "DEVELOPMENT-README.md",
    ".nav-config.json",
    ".user-profile.json",
    "knowledge/graph.json",
    "research/",  # nav-deep-research workspaces: subagents read many source notes (TASK-74)
})

DEFAULT_WARN_THRESHOLD = 3
DEFAULT_ESCALATE_THRESHOLD = 5
DEFAULT_STALE_AFTER_SECONDS = 300

# Bound on the per-turn set of counted tool-use ids kept for dedup. Duplicate
# dispatches of one Read arrive adjacently, so a small window always catches
# them; the cap keeps the state section from growing over a long turn.
MAX_SEEN_TOOL_USES = 64


def _resolve_agent_relative(file_path: str, root: Path) -> str | None:
    """Path relative to .agent/ when the file is under it, else None (v6 logic)."""
    if not file_path:
        return None
    path = Path(file_path)
    if not path.is_absolute():
        path = root / file_path
    try:
        rel = path.resolve().relative_to((root / ".agent").resolve())
    except (ValueError, OSError):
        return None
    return rel.as_posix()


def _allowlist(cfg) -> frozenset:
    value = config.get(cfg, "read_guard_hook.allowlist")
    if isinstance(value, list):
        return frozenset(str(item) for item in value)
    return DEFAULT_ALLOWLIST


def _is_allowlisted(agent_rel: str, allow: frozenset) -> bool:
    """Exact match, or prefix match for entries ending in '/' (directory allowlist)."""
    if agent_rel in allow:
        return True
    return any(entry.endswith("/") and agent_rel.startswith(entry) for entry in allow)


def _is_stale(updated_at, stale_after_s: int, now: float) -> bool:
    """True when the counter's last update predates the staleness window.

    v6 semantics: guards against a missed Stop reset (mem-036) — a stale
    counter must not falsely block the next turn's legitimate reads.
    Missing or non-numeric timestamps are NOT stale (preserves prior count;
    same discipline as v6's unparseable-ISO handling), and a non-positive
    window disables staleness entirely.
    """
    if stale_after_s <= 0:
        return False
    if not isinstance(updated_at, (int, float)) or isinstance(updated_at, bool):
        return False
    return (now - float(updated_at)) > stale_after_s


def _tool_use_id(payload) -> str | None:
    """Stable identity of the Read tool-use, or None (TASK-66 dedup key).

    Real PreToolUse payloads carry ``tool_use_id`` (verified: the read_guard
    golden payload, captured verbatim from a live session, includes a
    ``toolu_...`` value). Keying the per-turn counter on it makes each unique
    Read count exactly once even when the SAME tool-use fires the PreToolUse
    dispatch more than once. camelCase is accepted defensively. Returns None
    when no id is present so the caller falls back to per-dispatch counting.
    """
    if not isinstance(payload, dict):
        return None
    for key in ("tool_use_id", "toolUseId"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _increment_counter(ctx, stale_after_s: int, tool_use_id: str | None) -> int:
    """Bump reads.turn_count for a NEW Read tool-use; reset first when stale.

    Idempotent per tool-use (TASK-66): a repeated dispatch of an already-
    counted ``tool_use_id`` this turn returns the recorded count WITHOUT
    re-incrementing, so a single Read never advances the counter twice (the
    double-increment root cause) and the threshold decision is identical
    across the duplicate. Reads with no id (tool_use_id is None) keep the v6
    per-dispatch behavior. The reset-barrel coupling is preserved: stop_state
    still overwrites the whole ``reads`` section on Stop, dropping the seen set
    with it, and a stale window resets to a fresh (empty) section here.
    """
    reads = ctx.state.get("reads")
    if not isinstance(reads, dict) or _is_stale(reads.get("updated_at"),
                                                stale_after_s, ctx.now):
        reads = {}
    seen = reads.get("seen_tool_uses")
    if not isinstance(seen, list):
        seen = []
    count = int(reads.get("turn_count", 0))
    if tool_use_id is not None and tool_use_id in seen:
        reads["turn_count"] = count  # duplicate dispatch: idempotent no-op
        ctx.state["reads"] = reads
        return count
    count += 1
    reads["turn_count"] = count
    reads["updated_at"] = float(ctx.now)
    if tool_use_id is not None:
        seen.append(tool_use_id)
        reads["seen_tool_uses"] = seen[-MAX_SEEN_TOOL_USES:]
    ctx.state["reads"] = reads
    return count


def _block_text(count: int, threshold: int) -> str:
    """The v6 hard-block notice, sentinel-wrapped (user-addressed, mem-034).

    Deliberately omits the triggering file_path — keeps the message free of
    arbitrary substrings that could become future recursive-trigger surfaces.
    """
    body = (
        f"Navigator nav-read-guard: blocked at {count} .agent/ reads "
        f"(escalate_threshold={threshold}).\n"
        "  Why: this turn has crossed the bulk-load threshold. Sequential "
        ".agent/ reads risk 50k+ token consumption and session crash.\n"
        "  How to proceed (your choice):\n"
        "    1. Use a Task or Explore agent for the remaining lookups — "
        "they read excerpts, not full files, and are designed for "
        "multi-file discovery.\n"
        "    2. Split the work: end this turn, start a new one (the "
        "counter resets on every Stop event).\n"
        "    3. Raise the threshold: set read_guard_hook.escalate_threshold "
        "to a higher number in .agent/.nav-config.json.\n"
        "    4. Disable strict enforcement: set read_guard_hook.strict_block"
        "=false in .agent/.nav-config.json."
    )
    return sentinels.wrap("nav-read-guard-block", body)


def run(ctx):
    payload = ctx.payload
    if payload.get("tool_name") != "Read":
        return None  # defensive: the registry matcher already restricts to Read

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or ""
    if not isinstance(file_path, str) or not file_path:
        return None

    root = hio.project_root(payload)
    agent_rel = _resolve_agent_relative(file_path, root)
    if agent_rel is None:
        return None  # outside .agent/ — ignore
    if _is_allowlisted(agent_rel, _allowlist(ctx.config)):
        return None  # allowlisted — counts toward zero

    cfg = ctx.config
    warn_at = int(config.get(cfg, "read_guard_hook.warn_threshold",
                             DEFAULT_WARN_THRESHOLD))
    escalate_at = int(config.get(cfg, "read_guard_hook.escalate_threshold",
                                 DEFAULT_ESCALATE_THRESHOLD))
    strict_block = config.get(cfg, "read_guard_hook.strict_block", True)
    stale_after = int(config.get(cfg, "read_guard_hook.stale_after_seconds",
                                 DEFAULT_STALE_AFTER_SECONDS))

    count = _increment_counter(ctx, stale_after, _tool_use_id(payload))

    if count >= escalate_at and strict_block:
        # Deny-only channel: exit 2 + sentinel stderr (mem-035/mem-054).
        return {
            "exit_code": 2,
            "stderr": _block_text(count, escalate_at),
            # TASK-88 reject log: the path goes to the log file, never to stderr.
            "reject": {
                "reason": f"{count} .agent/ reads this turn (escalate_threshold={escalate_at})",
                "evidence": {"path": agent_rel, "count": count, "threshold": escalate_at},
            },
        }
    if count >= escalate_at:
        return {"stderr": (
            f"[nav-read-guard] {count} .agent/ files read this turn. "
            "Bulk-load anti-pattern threshold crossed (risk: 50k+ tokens). "
            "Use a Task or Explore agent for multi-file discovery."
        )}
    if count >= warn_at:
        return {"stderr": (
            f"[nav-read-guard] {count} .agent/ files read this turn. "
            "Navigator lazy-loading pattern: load only what the task needs. "
            "For broader surveys, use a Task or Explore agent."
        )}
    return None
