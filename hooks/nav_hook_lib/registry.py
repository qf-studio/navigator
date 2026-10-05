#!/usr/bin/env python3
"""nav_hook_lib.registry — declarative EVENT -> ordered OpSpec lists (TASK-60 Phase 2).

The single dispatcher (hooks/nav_dispatch.py -> nav_hook_lib.runtime.dispatch)
consults EVENT_OPS to decide which op modules run for a given hook event, in
which phase order, behind which config toggle. This module is pure data: it
imports no op modules (runtime imports them lazily, only when their event
fires and their matcher hits) and performs no I/O.

Registry semantics consumed by runtime.dispatch:

  - Phases execute in PHASE_ORDER (gates -> responders -> injectors ->
    recorders). A blocking result from a 'gates' op short-circuits every
    phase to its right. Ops in phase 'gates' are exempt from the soft
    deadline — they always run.
  - Within one event, list order IS merge order (additional_context strings
    are concatenated in registry order, then budget.clamp'd).
  - OpSpec.config_key names a toggle block in .agent/.nav-config.json: the
    EXISTING v6 blocks for TASK-61 ports (fixtures/nav-config-v6.18.1.json)
    or a v7 block seeded in config.DEFAULTS for TASK-62 rows; runtime gates
    each op on config.get(cfg, config_key + '.enabled', True).
  - OpSpec.matcher is a regex tested against payload tool_name for
    PreToolUse/PostToolUse; None means the op always runs for its event.
  - A missing op module (the normal state until TASK-61 lands the ports) is
    skipped with a meta.op_errors note — never a crash.

Pilot-executor policy is NOT expressed here: runtime evaluates
config.is_pilot_executor() once at dispatch entry and passes it to ops as
ctx.pilot_executor (the registry stays posture-agnostic).

Pure Python stdlib only (guard test in test_config.py).
"""
from __future__ import annotations

from dataclasses import dataclass

# Pipeline phase order. runtime.dispatch executes phases left to right; the
# strings below are the only valid OpSpec.phase values.
PHASE_ORDER = ("gates", "responders", "injectors", "recorders")

# The seven v6 manifest event surfaces plus the TASK-62 additions. Every
# TASK-62 event below passed the validate-or-drop gate (`claude plugin
# validate`, CC 2.1.205 accepted all six candidates; a control probe with a
# bogus event name was rejected, proving the gate is real) and maps to a
# committed op module (v5.1.0 lesson: never a registration with no op
# behind it).
EVENTS = (
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "PreCompact",
    "PostCompact",
    # TASK-62 event surfaces (validate-or-drop survivors, CC 2.1.205):
    "SubagentStart",
    "PostToolUseFailure",
    "TaskCreated",
    "TaskCompleted",
    "ConfigChange",
    "Setup",
)

# Coarse tool matcher shared by the PostToolUse recorders (kept coarse for
# spawn suppression; fine filtering happens inside the ops).
MUTATING_TOOLS = "Edit|Write|MultiEdit|NotebookEdit"


@dataclass(frozen=True)
class OpSpec:
    """One dispatchable operation — exactly these five fields (TASK-60 contract).

    name:       op module hooks/ops/<name>.py exposing run(ctx) -> dict|None
    phase:      one of PHASE_ORDER
    matcher:    regex against payload tool_name (Pre/PostToolUse); None = always
    config_key: v6 toggle block name; <config_key>.enabled gates the op
    budget_ms:  advisory per-op soft time budget. NOT enforced by the TASK-60
                runtime (which applies the event-level soft deadline); recorded
                for TASK-61 tuning and future per-op telemetry.
    """

    name: str
    phase: str
    matcher: str | None
    config_key: str
    budget_ms: int


# ---------------------------------------------------------------------------
# EVENT -> ordered ops: the eight TASK-61 rows plus every TASK-62 row, each
# landed together with its committed op module and citing its channel
# verdict memory (mem-050..055) in an adjacent comment.
# ---------------------------------------------------------------------------
EVENT_OPS: dict[str, list[OpSpec]] = {
    "SessionStart": [
        OpSpec("session_start", "injectors", None, "session_start_hook", 8000),
    ],
    "UserPromptSubmit": [
        OpSpec("prompt_gate", "gates", None, "workflow_enforcer_hook", 1500),
        # prompt_tier1 (TASK-62 Phase 1) — mem-053 (S4 PASS, CC 2.1.205):
        #   UserPromptSubmit block-as-answer WORKS with zero model invocation
        #   (num_turns=0, duration_api_ms=0); WINNER is decision:block JSON —
        #   exit-2 leaks raw hook command chrome into the visible answer.
        #   Caution: the harness appends 'Original prompt: <trigger>' to the
        #   block message, so context-scanning ops must tolerate that echo
        #   (the answer is sentinel-wrapped in <nav-t1-response> so strip_all
        #   removes it AND the echo line). Fallback if the channel regresses:
        #   demote Tier-1 to an advisory injection ("answer verbatim from
        #   this data"). tier1.enabled seeds OFF (config.DEFAULTS).
        OpSpec("prompt_tier1", "responders", None, "tier1", 800),
        # prompt_modes (TASK-82 ADHD, TASK-93 STE) — same decision:block
        #   channel as Tier-1 (mem-053) for the exact toggle phrases
        #   "<mode> mode on|off|status" of every row in reply_modes.MODES,
        #   plus the active rule blocks as additional_context on every prompt
        #   while a person's switch is on. One row: the op answers OR
        #   injects, never both. reply_modes.enabled seeds True (availability
        #   only); every personal switch seeds off, so nothing is injected by
        #   default.
        OpSpec("prompt_modes", "responders", None, "reply_modes", 200),
        OpSpec("prompt_brief", "injectors", None, "brief_hook", 2000),
    ],
    "PreToolUse": [
        # read_guard stays deny-only regardless of mem-054 (S5, CC 2.1.205):
        # plain stdout is DEAD (reconfirms mem-035 for stdout) while
        # hookSpecificOutput.additionalContext DELIVERS (supersedes mem-035
        # for that sub-channel) — the advisory redesign is a v7.x follow-up,
        # not TASK-61.
        OpSpec("read_guard", "gates", "Read", "read_guard_hook", 1000),
    ],
    "PostToolUse": [
        # jit_memory (TASK-62 Phase 3) — mem-050 (S1 PASS, CC 2.1.205):
        #   PostToolUse hookSpecificOutput.additionalContext DELIVERS to the
        #   model (supersedes mem-035 for this sub-channel); content must be
        #   DECLARATIVE — imperative instructions are flagged by the model as
        #   prompt injection and refused (2/2 runs). Fallback if the channel
        #   regresses: queue in state, surface at the next UserPromptSubmit.
        #   jit_memory.enabled seeds OFF (config.DEFAULTS). Listed first per
        #   phase order (injectors before recorders).
        OpSpec("jit_memory", "injectors", MUTATING_TOOLS, "jit_memory", 1500),
        OpSpec("graph_sync", "recorders", MUTATING_TOOLS, "task_graph_sync_hook", 2000),
        OpSpec("profile_sync", "recorders", MUTATING_TOOLS, "profile_sync_hook", 2000),
    ],
    "Stop": [
        # stop_completion (TASK-62 Phase 2) — mem-051 (S2, CC 2.1.205):
        #   Stop 'continue: true' is a NO-OP for forced continuation;
        #   'decision: block' + reason IS the working mechanism (exactly one
        #   continuation; stop_hook_active harness belt + single-shot fuse
        #   both verified). Ships on decision:block with continue:true OFF
        #   permanently; default OFF, and always OFF under the Pilot
        #   executor (two loop supervisors must not fight). Listed before
        #   stop_state per phase order (gates run first); when it blocks,
        #   the stop_state recorder is short-circuited so the turn is NOT
        #   stamped/reset — a forced continuation is the same turn, and the
        #   consumed completion.stop_fuse survives until the next clean
        #   turn end re-arms it via stop_state's reset barrel.
        OpSpec("stop_completion", "gates", None, "stop_completion", 2000),
        OpSpec("stop_state", "recorders", None, "workflow_state_hook", 2000),
    ],
    "PreCompact": [
        OpSpec("compact_marker", "recorders", None, "compact_hook", 25000),
    ],
    "PostCompact": [
        OpSpec("compact_marker", "recorders", None, "compact_hook", 4000),
    ],
    # ---- TASK-62 event surfaces beyond the seven v6 ones. All six event
    # registrations passed the validate-or-drop gate (CC 2.1.205) and land
    # in the manifest together with these rows. ----
    "SubagentStart": [
        # subagent_context (TASK-62 Phase 4) — mem-052 (S3 PASS, CC 2.1.205):
        #   hookSpecificOutput.additionalContext WORKS with both-way
        #   main/subagent isolation; viable at the 2k-char budget
        #   (budget.BUDGETS). Plan decision: had S3 failed, the feature would
        #   be DROPPED (no degraded mode). subagent_context.enabled seeds OFF
        #   (config.DEFAULTS).
        OpSpec("subagent_context", "injectors", None, "subagent_context", 3500),
    ],
    "PostToolUseFailure": [
        # failure_diagnosis (TASK-62 Phase 3) — inherits mem-050's S1 PASS
        #   for the additionalContext envelope shape (routing matrix recorded
        #   in mem-050; declarative content only). The EVENT itself was
        #   unproven by the spike: its registration survived the
        #   validate-or-drop gate (CC 2.1.205 accepted it). Fallback if the
        #   channel regresses: state-queue + next-event surfacing, same as
        #   jit_memory. failure_diagnosis.enabled seeds OFF (config.DEFAULTS).
        OpSpec("failure_diagnosis", "injectors", None, "failure_diagnosis", 3500),
    ],
    "TaskCreated": [
        # graph_sync lifecycle branch (TASK-62 Phase 5) — recorder side
        #   effect only, no spike dependency; event kept by validate-or-drop.
        OpSpec("graph_sync", "recorders", None, "task_graph_sync_hook", 2000),
    ],
    "TaskCompleted": [
        OpSpec("graph_sync", "recorders", None, "task_graph_sync_hook", 2000),
    ],
    "ConfigChange": [
        # config_guard (TASK-62 Phase 5) — systemMessage channel; no spike
        #   dependency in the routing matrix (no mem-05x verdict required);
        #   event kept by validate-or-drop.
        OpSpec("config_guard", "injectors", None, "config_guard", 1000),
    ],
    "Setup": [
        # setup (TASK-62 Phase 5) — systemMessage onboarding hint / runtime
        #   status; event kept by validate-or-drop. mem-055 (S6, CC 2.1.205)
        #   backs the plumbing: ${CLAUDE_PLUGIN_ROOT} binds correctly in
        #   plugin-manifest hook commands (headless -p included), so the
        #   manifest guard resolves the dispatcher on Setup fires. Note: the
        #   runtime early-outs on a missing .agent/, so only the initialized
        #   -project status line ships through dispatch (op docstring).
        OpSpec("setup", "injectors", None, "setup_hook", 1500),
    ],
}
