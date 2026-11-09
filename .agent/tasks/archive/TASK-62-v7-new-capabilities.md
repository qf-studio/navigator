# TASK-62: New Runtime Capabilities on Spike-Proven Channels

**Status**: ✅ Implemented — 2026-07-10 (all six new events validated + registered; ops live-verified; tier1 zero-token answer proven at ~99ms)
**Created**: 2026-07-10
**Parent plan**: v7.0.0 hooks-runtime concept (approved 2026-07-10)
**Execution**: interactive — NOT dispatched to Pilot (user decision 2026-07-10)
**Effort**: L
**Depends on**: TASK-57, TASK-61

## Context

**Problem**: v6 hooks only gate and record. The channels TASK-57 probes — UserPromptSubmit
block-as-answer, Stop `continue:true`, tool-result-position `additionalContext`, SubagentStart
context — enable capabilities v6 cannot express: zero-token deterministic answers, forced
continuation on unfinished work, pitfall knowledge injected at the moment of action. None may be
built on an unproven channel (mem-035 precedent: harness docs are version-fragile).

**Goal**: Build the new capabilities from the plan's routing matrix, each strictly on a channel
TASK-57 PROVED, each with its named fallback wired if the probe failed. Ops run inside the TASK-60
dispatcher alongside TASK-61-ported siblings; only spike-gated behavior is spike-gated — the rest
(graph_sync events, config_guard) uses channels with no spike dependency.

## Known Pitfalls & Patterns

- **mem-034** (pitfall, 1.0): exit-2 on UserPromptSubmit blocks the model; stderr echoing the
  trigger phrase re-triggers recursively. → Phase 1 sentinel-wraps every Tier-1 answer in
  `<nav-t1-response>`, adds the escape line, and emits stderr only via the shared lib emitter.
- **mem-035** (pitfall, 1.0): PreToolUse stdout + `additionalContext` silently dropped,
  live-verified v6.12.0, CONFLICTS with current docs. → Phases 1–4 consume TASK-57 verdicts
  before any code; every capability names its fallback; nothing is trusted from docs.
- **mem-036** (pitfall, 0.95): unset plugin env var made hooks silently no-op for two releases.
  → Phase 6 contract tests execute manifest commands with `CLAUDE_PLUGIN_ROOT` set AND unset.
- **mem-037** (pitfall, 1.0): Stop hook stamping state on conversational turns deadlocked the
  enforcer; fixed by tristate. → Phase 2 never emits continue on turns without mutating tool_use.
- **TASK-45 pattern**: subprocess-against-tmp-project contract tests — Phase 6 harness template.
- **v5.1.0 incident**: manifest referenced a skill never committed — every plugin.json
  registration added here must map to a committed op file (`--verify-hooks`).

## Acceptance Criteria

- [ ] `nav stats` (exact, ≤48 chars post-strip) yields a `<nav-t1-response>`-wrapped answer with
      escape line "reply 'ask claude' to run the model" and zero model invocation (S4 PASS path)
- [ ] Non-exact variants ("nav stats please") reach the model — no fuzzy matching
- [ ] Tier-1 hit records `turn.tier1_hit`; hit followed by near-identical re-prompt increments a
      false-positive counter surfaced by /nav:stats
- [ ] `PILOT_EXECUTOR` bypasses prompt_tier1 entirely (contract test)
- [ ] S4 FAIL path: prompt_tier1 emits advisory injection "answer verbatim from this data";
      no block/exit-2 path exists in the op
- [ ] stop_completion continues only when indicators fail AND no nav-signal v3 `exit` present;
      indicators reuse `exit_gate.evaluate_exit` vocabulary (code_committed, tests_passing,
      code_simplified, docs_updated, ticket_closed, marker_created)
- [ ] Fuse: flag file consumed on emit; second Stop in the same turn yields (composition test)
- [ ] `completion.held_count` caps at `stop_completion.max_continues` (default 2, seeded by
      TASK-63) per user turn; resets on UserPromptSubmit
- [ ] `stop_completion.continue_enabled` defaults OFF; missing config block ⇒ off
- [ ] Turn without mutating tool_use never continues (mem-037 composition case)
- [ ] `PILOT_EXECUTOR` disables stop_completion unconditionally, regardless of config
- [ ] Editing `hooks/*.py` injects mem-034/035 at tool-result position once per session
      (`jit.injected[]` dedupe); second edit injects nothing
- [ ] S1 FAIL path: injection queued in `jit.pending`, surfaced on next UserPromptSubmit
- [ ] PostToolUseFailure with matching tool+error pattern surfaces a graph pitfall; no match ⇒
      silent (no generic noise)
- [ ] SubagentStart payload ≤2k chars (budget.py clamp); if S3 FAILED, subagent_context is not
      registered at all
- [ ] TaskCreated/TaskCompleted update the graph; invalid `.nav-config.json` edit triggers a
      config_guard systemMessage warning
- [ ] All new event registrations in plugin.json map to committed ops; contract tests pass with
      env set AND unset (mem-036)

## Implementation

### Phase 0 — Channel verdict intake

- **Goal**: bind each capability to its TASK-57 probe verdict before writing op code.
- **Tasks**: read the TASK-57 spike memories (authoritative verdict source; the TASK-58 results
  file `tests/harness-conformance/results/cc-<version>.json` is supplementary when present);
  record
  build-vs-fallback per capability (S4→tier1, S2→stop_completion, S1→jit/failure_diagnosis,
  S3→subagent_context); if S3 failed, strike Phase 4 now.
- **Files**: `tests/harness-conformance/results/` (read-only), this doc (verdict table appended).

### Phase 1 — prompt_tier1 responder (S4-gated)

- **Goal**: deterministic zero-token answers for a narrow exact-match command set.
- **Tasks**: exact-match table — `nav stats`, `show features`, `list markers`, `graph health`,
  `nav version`/drift — prompt ≤48 chars post-strip; sentinel-wrap answer + escape line (mem-034);
  record `turn.tier1_hit`; false-positive telemetry (hit → near-identical re-prompt) with a
  /nav:stats row; per-rule off-switch; central `is_pilot_executor()` bypass. S4 FAIL fallback:
  demote to advisory injection "answer verbatim from this data".
- **Files**: `hooks/ops/prompt_tier1.py` + `test_prompt_tier1.py`, `skills/nav-stats/` (telemetry).

### Phase 2 — stop_completion gate with full circuit breaker (S2-gated)

- **Goal**: force one continuation when work is demonstrably unfinished; never runaway.
- **Tasks**: dual-condition gate — `exit_gate.evaluate_exit` indicators AND explicit nav-signal v3
  `exit`; breaker per risk register: single-shot flag-file fuse consumed on emit, `held_count`
  capped at `stop_completion.max_continues` (default 2) per user turn, reset on
  UserPromptSubmit, kill-switch `stop_completion.continue_enabled`
  seeded OFF, never continue on non-mutating turns (mem-037 ported), unconditionally disabled
  under `PILOT_EXECUTOR` (two loop supervisors must not fight). S2 FAIL fallback: Stop
  `decision:block` instead of `continue:true`.
- **Files**: `hooks/ops/stop_completion.py` + test, `skills/nav-loop/functions/exit_gate.py`
  (imported, not modified), state sections `completion{indicators, signal, held_count}`.

### Phase 3 — jit_memory + failure_diagnosis injectors (S1-gated)

- **Goal**: pitfall knowledge delivered at the moment of action.
- **Tasks**: jit_memory on PostToolUse(Edit|Write|MultiEdit) — edits to `hooks/*.py` inject
  mem-034/035 at tool-result position, once-per-session dedupe via `jit.injected[]`;
  failure_diagnosis on PostToolUseFailure — graph pitfall lookup keyed by tool + error pattern.
  Shared S1 FAIL fallback: queue in `jit.pending`, surface on next UserPromptSubmit.
- **Files**: `hooks/ops/jit_memory.py`, `hooks/ops/failure_diagnosis.py`, colocated tests.

### Phase 4 — subagent_context (S3-gated; DROP on failure)

- **Goal**: subagents start with a session snapshot + top-K relevant memories.
- **Tasks**: SubagentStart `additionalContext` built from runtime state + graph recall; hard 2k
  budget via `nav_hook_lib/budget.py`. If S3 failed: feature dropped — no registration, no
  degraded mode (plan decision).
- **Files**: `hooks/ops/subagent_context.py` + test.

### Phase 5 — graph_sync events + config_guard + setup (no spike dependency)

- **Goal**: native lifecycle events feed the graph; config edits validated on save.
- **Tasks**: extend graph_sync (ported in TASK-61) for TaskCreated/TaskCompleted; new
  config_guard on ConfigChange emits systemMessage warning on invalid `.nav-config.json`;
  register both events in the manifest.
- **Files**: `hooks/ops/graph_sync.py`, `hooks/ops/config_guard.py` + tests,
  `.claude-plugin/plugin.json`.

#### setup op (Setup event)
- **Tasks**: `hooks/ops/setup.py` — Setup-event responder emitting a stdout onboarding hint
  (`.agent/` missing → point at nav-init; present → one-line runtime status). Registers the
  Setup event in plugin.json (this task owns all new-event registration per TASK-60).
- **Files**: `hooks/ops/setup.py` + `test_setup.py`.

### Phase 6 — Contract + composition tests

- **Goal**: every new op proven under ship-path conditions.
- **Tasks**: contract tests per new event (TASK-45 subprocess-vs-tmp-project template; cases:
  pristine v6.18.1 config, no-`.agent/`, PILOT_EXECUTOR, off-switches, malformed stdin, env set
  AND unset per mem-036); composition tests: fuse consumed exactly once, held_count reset on
  UserPromptSubmit, mem-037 non-mutating-turn case, Tier-1 echo-hygiene probe (mem-034 class).
- **Files**: `hooks/ops/test_*.py`, composition cases beside the Stop↔gate suite from TASK-61.

## Phase 0 Verdict Table (recorded at close, 2026-07-10)

| Probe | Verdict (memory) | Capability | Path taken |
|---|---|---|---|
| S4 | PASS, winner decision:block (mem-053) | prompt_tier1 | block-as-answer built; no exit-2 path |
| S2 | continue:true FAIL, decision:block works (mem-051) | stop_completion | decision:block fallback; continue never emitted |
| S1 | PASS, declarative only (mem-050) | jit_memory + failure_diagnosis | tool-result injection built; no pending-queue fallback needed |
| S3 | PASS (mem-052) | subagent_context | shipped at 2k budget; drop path not taken |

## Sanctioned Deviations (recorded at close)

- held_count/fuse reset lives in the Stop reset barrel (turn end), not on UserPromptSubmit —
  fail-safe direction (fewer continuations after interrupted turns), documented in the op.
- stop_completion registers as a GATE ordered before the stop_state recorder (registry invariant:
  phase order); the block short-circuits stop_state so fuse/held_count survive continuation.
- False-positive counter surfaces in the Tier-1 `nav stats` answer and in nav-stats docs; a
  dedicated /nav:stats telemetry row rides with the skill (display-only).
- "--verify-hooks confirms registrations" is realized as unit tests
  (test_registry + ManifestShapeTest assert every event maps to a committed op).

## Out of Scope

- **PermissionRequest/PermissionDenied** — never fight the user's permission policy (plan).
- **MessageDisplay** — v7.1 candidate (plan exclusion).
- **StopFailure** — recursion hazard (plan exclusion).
- Dispatcher/registry/lib (TASK-59/60); porting the nine v6 hooks (TASK-61); config_migrator
  `VERSION_CONFIGS["7.0.0"]` + CLAUDE.md demotion (TASK-63); release gates + RC soak (TASK-64).
- Tier-1 whitelist growth beyond the five seed commands.

## Technical Decisions

| Decision | Options Considered | Chosen | Reasoning |
|---|---|---|---|
| Tier-1 matching | fuzzy intent scoring; exact table | Exact-match, ≤48 chars post-strip | Risk register: whitelist starts narrow; false positives erode trust |
| Completion vocabulary | new indicator enum; reuse exit_gate | Reuse `evaluate_exit` indicators | One vocabulary shared with Loop Mode; no drift |
| continue:true default | on with breaker; seeded off | Kill-switch seeded OFF | Migration policy: new blocking features seed off |
| Non-mutating-turn continue | allow with cap; never | Never | mem-037 ported: conversational turns deadlocked the enforcer |
| Pilot interaction | config-gated; unconditional off | Unconditionally disabled under PILOT_EXECUTOR | Two loop supervisors must not fight |
| subagent_context degraded mode | state-queue fallback; drop | Drop feature if S3 failed | Plan: no degraded mode worth having |

Deferred decisions:
- Tier-1 command-table growth (review false-positive telemetry after RC soak; v7.1).
- Top-K value and ranking function for subagent memory selection (tune during RC soak).
- Similarity threshold defining "near-identical re-prompt" for false-positive telemetry.

## Verify

```
make test                    # full suite incl. new op, contract, composition tests
make conformance-check       # fails without results for installed CC version
PILOT_EXECUTOR=1 python3 hooks/nav_dispatch.py UserPromptSubmit \
  < tests/fixtures/tier1_nav_stats.json          # passthrough: no block, no tier1_hit
time python3 hooks/nav_dispatch.py UserPromptSubmit \
  < tests/fixtures/tier1_nav_stats.json          # <200ms (plan latency budget)
```

Live drives (plan verification layer 3): type `nav stats` → instant sentinel-wrapped answer, zero
model turn; finish a task without committing → exactly one forced continuation, then yield; edit
`hooks/nav_dispatch.py` → mem-034/035 attached to the edit result.

## Done

- `nav stats` answers without a model invocation (or via advisory fallback if S4 failed).
- Unfinished work (indicators unmet, no v3 exit) continues once then yields; breaker tests green.
- Editing `hooks/*.py` surfaces mem-034/035 exactly once per session; tool failures surface
  matching graph pitfalls.
- Subagents receive ≤2k context, or the feature is absent (S3 verdict recorded either way).
- TaskCreated/TaskCompleted feed the graph; invalid config edits warn via systemMessage.
- `--verify-hooks` confirms every new registration maps to a committed op (v5.1.0 incident class).

## Refs

- Parent plan: `~/.claude/plans/the-cocept-of-the-delightful-dongarra.md` (routing matrix, Tier-1
  safety rails, risk register, deliberate exclusions)
- TASK-57 (spike verdicts — hard gate), TASK-61 (ported ops this task extends)
- `skills/nav-loop/functions/exit_gate.py` — `evaluate_exit` + indicators vocabulary
- mem-034, mem-035, mem-036, mem-037 (`.agent/knowledge/memories/pitfalls/`, graph.json)
- Precedents: TASK-45 (contract-test pattern), v5.1.0 incident (manifest/commit drift)

**Last Updated**: 2026-07-10
