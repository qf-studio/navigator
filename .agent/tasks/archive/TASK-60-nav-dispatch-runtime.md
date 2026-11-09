# TASK-60: nav_dispatch — Single Dispatcher Entrypoint + Op Registry

**Status**: ✅ Implemented — 2026-07-10 (37→39-line fail-open shim, registry + phase pipeline, manifest rewrite w/ sh-guard fallback; p95 ~41ms; 7 adversarial findings fixed incl. BaseException escape, continue-merge inversion, PILOT_EXECUTOR merge belt)
**Created**: 2026-07-10
**Parent plan**: v7.0.0 hooks-runtime concept (approved 2026-07-10)
**Execution**: interactive — NOT dispatched to Pilot (user decision 2026-07-10)
**Effort**: M
**Depends on**: TASK-59

## Context

**Problem**: v6 registers nine independent hook scripts in plugin.json. Each pays its own
interpreter/config/state startup cost, ordering on shared events is implicit array order,
PILOT_EXECUTOR is re-implemented per hook (which is how one got missed), and a crash in any
script has no shared containment or surfacing path. Two hooks on one event emit two output
documents that the harness resolves arbitrarily.

**Goal**: One dispatcher per event. plugin.json registers
`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/nav_dispatch.py" <event>` once per event; `registry.py`
maps EVENT → ordered OpSpec list executed through the phase pipeline
gates → responders → injectors → recorders, merged into a single JSON output document.
Fail-open everywhere: Navigator must never block the harness. Ships the contract-test harness
skeleton that TASK-61/62 op ports plug into.

Hard gate (plan): no dispatcher code before TASK-57 spike memories exist. TASK-59's
`nav_hook_lib` (hio/config/state/sentinels) is the substrate — this task consumes it, never
reimplements it.

## Known Pitfalls & Patterns

- mem-034 (100%): UserPromptSubmit exit-2 blocks the model; unwrapped stderr echoes recycle as
  trigger phrases. → Phase 3: the `[nav-dispatch-error]` crash sentinel is emitted only via
  `nav_hook_lib.sentinels` — ops never write raw stderr (lint test greps op files).
- mem-035 (100%): PreToolUse/PostToolUse stdout + additionalContext silently dropped
  (live-verified v6.12.0; CONFLICTS with current docs). → Phase 2: registry rows for these
  events carry the spike-gated channel note; nothing here assumes those channels work.
- mem-036 (95%): manifest env var unset → hooks silently no-op'd for two releases. → Phase 5:
  every event's literal manifest command runs as a subprocess under three env variants
  (set / unset / empty).
- mem-037 (100%): Stop hook stamping state on conversational turns deadlocked the enforcer.
  → Phase 3: state read once / written once atomically per dispatch; the soft deadline may drop
  injectors and recorders but never gates, so gate inputs are never half-written.
- TASK-45 precedent: subprocess-vs-tmp-project contract tests (`test_workflow_enforcer.py`) are
  the harness template. → Phase 5.
- v5.1.0 incident: manifest referenced a skill never committed. → Phase 4: manifest rewrite and
  dispatcher land in the same commit; contract tests execute the literal manifest commands.

## Acceptance Criteria

- [ ] `hooks/nav_dispatch.py` is <40 lines; whole body inside try/except → exit 0 (fail-open;
      no code path in the shim exits non-zero)
- [ ] `registry.py` maps each event to an ordered OpSpec list with exactly the fields
      `name, phase, matcher, config_key, budget_ms`
- [ ] Pipeline runs gates → responders → injectors → recorders; a gate block short-circuits
      all rightward phases (contract test with synthetic ops proves it)
- [ ] Merge rules hold: additionalContext concatenated under per-event char budget, dropping
      lowest-priority op output first; highest-priority decision wins; `continue` is OR'd;
      exactly one JSON output document and one exit code per event
- [ ] Per-op isolation: injected op crash → `meta.op_errors` entry + sentinel stderr line, and
      sibling ops still execute (crash-injection contract test)
- [ ] Internal soft deadline = manifest timeout − 500ms, checked before each op; gates always
      run even after the deadline expires
- [ ] Op modules import lazily; UserPromptSubmit dispatch ≤200ms p95 against the timing fixture
      (CI assertion)
- [ ] State file read once and written once (tmp+rename) per dispatch — verified by test
- [ ] plugin.json: one command per event via `${CLAUDE_PLUGIN_ROOT}`; coarse matchers kept
      (`Read`; `Edit|Write|MultiEdit|NotebookEdit`); timeouts SessionStart 10s, PreCompact 30s,
      all other events 5s
- [ ] Contract harness covers the mandatory list: pristine v6.18.1 config fixture exits 0;
      no-`.agent` project degrades silently (exit 0, no output); PILOT_EXECUTOR bypasses all
      blocking behaviors; each per-behavior off-switch honored; malformed stdin fails open;
      crash-injection; mem-036 three-env-variant manifest command tests
- [ ] Dispatcher writes `.agent/.nav-dispatch-health.json` on error; the next SessionStart
      dispatch surfaces the last recorded error

## Implementation

### Phase 1 — Shim
**Goal**: crash-proof entrypoint.
**Tasks**: `nav_dispatch.py` <40 lines — parse `argv[1]` event, read stdin once, delegate to
`nav_hook_lib.runtime.dispatch(event, payload)`, print the merged doc, exit 0. Whole body
try/except → exit 0. Unknown or missing event → exit 0, no output.
**Files**: `hooks/nav_dispatch.py`

### Phase 2 — Registry
**Goal**: declarative EVENT → ops mapping.
**Tasks**: `OpSpec(name, phase, matcher, config_key, budget_ms)`; per-event ordered lists seeded
from the plan's routing matrix (op modules land in TASK-61/62 — registry skips missing modules
with a `meta.op_errors` note). Phase-order constant: gates, responders, injectors, recorders.
Spike-gated rows (PostToolUse injectors, Stop continue, SubagentStart) annotated with their
plan fallbacks.
**Files**: `hooks/nav_hook_lib/registry.py`, `hooks/nav_hook_lib/runtime.py`

### Phase 3 — Merge, isolation, deadline
**Goal**: deterministic composition under failure.
**Tasks**: per-op try/except; merge rules (budgeted concat, priority decision, OR'd continue);
soft deadline = manifest timeout − 500ms checked before each op, gates exempt; PILOT_EXECUTOR
evaluated once at dispatch entry and passed to ops; state read once / atomic write once;
sentinel-only stderr; write `.agent/.nav-dispatch-health.json` on any op or dispatch error.
**Files**: `hooks/nav_hook_lib/runtime.py`, `hooks/nav_hook_lib/budget.py`

### Phase 4 — Manifest rewrite
**Goal**: plugin.json routes every event through the dispatcher.
**Tasks**: replace nine per-script entries with one dispatcher command per **v6 event surface**
(SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, Stop, Pre/PostCompact); new
routing-matrix events (SubagentStart, PostToolUseFailure, TaskCreated/TaskCompleted,
ConfigChange) are registered in TASK-62 per spike verdicts — never here with no op behind them
(`"${CLAUDE_PLUGIN_ROOT}/hooks/nav_dispatch.py" <event>`); matchers `Read` and
`Edit|Write|MultiEdit|NotebookEdit`; timeouts 10/30/5. Lands in the same commit as the
dispatcher (v5.1.0 lesson); ships only inside big-bang v7.0.0, never standalone.
**Files**: `.claude-plugin/plugin.json`

### Phase 5 — Contract-test harness skeleton
**Goal**: per-event subprocess tests that future ops plug into.
**Tasks**: harness from the `test_workflow_enforcer.py` template — build tmp project, run the
literal manifest command as a subprocess, assert on stdout/exit code. Implement the mandatory
case list (see Acceptance Criteria) plus the timing fixture for the 200ms assertion.
**Files**: `hooks/test_nav_dispatch.py`, `hooks/ops/` test skeleton

## Out of Scope

- Porting the nine v6 hooks to ops + golden parity tests (TASK-61)
- New capabilities: Tier-1, stop_completion, jit_memory, subagent_context (TASK-62)
- config_migrator 7.0.0, CLAUDE.md demotion, nav-features toggles (TASK-63)
- `--verify-dispatcher` release gate and CI wiring (TASK-64)
- Any reliance on spike-gated channels (PostToolUse additionalContext, Stop continue:true,
  SubagentStart injection) — routing rows exist, behavior lands only per TASK-57 results

## Technical Decisions

| Decision | Options Considered | Chosen | Reasoning |
|---|---|---|---|
| Topology | v6 nine scripts; single dispatcher | Dispatcher per event | Amortized cost, one doc |
| Failure posture | fail-block; fail-open | Fail-open, always exit 0 | Never brick the harness |
| Op ordering | implicit array order; phases | gates→resp→inj→rec | Deliberate gate cut |
| Matchers | fine in manifest; coarse+op filter | Coarse manifest matchers | Spawn suppression |
| PILOT_EXECUTOR | per-op checks (v6) | Evaluated once at dispatch | Per-hook checks get missed |
| Deadline | hard kill; soft per-op check | Soft, gates exempt | Gates never starved |

Deferred decisions:
- Exact per-event char budgets for additionalContext concat (tuned during TASK-61 port)
- Per-op priority values (assigned as ops land in TASK-61/62)
- Whether the PreToolUse advisory channel reopens (TASK-57 probe S5 decides)

## Verify

```bash
wc -l hooks/nav_dispatch.py                                            # < 40
echo '{}' | python3 hooks/nav_dispatch.py UserPromptSubmit; echo $?    # 0
printf 'garbage' | python3 hooks/nav_dispatch.py Stop; echo $?         # 0 — malformed stdin
python3 hooks/nav_dispatch.py; echo $?                                 # 0 — missing event arg
make test                                                              # contract harness green
grep -o 'hooks/[a-z_]*\.py' .claude-plugin/plugin.json | sort -u       # only nav_dispatch.py
time (echo '{"prompt":"x"}' | python3 hooks/nav_dispatch.py UserPromptSubmit)  # ≤ 0.2s
```

## Done

- Every plugin.json hook entry routes through `nav_dispatch.py <event>`; no per-script entries;
      only the six v6 event surfaces are registered (new events belong to TASK-62)
- Dispatcher exits 0 on: pristine v6.18.1 config, no-.agent project, malformed stdin, op crash
- Crash-injection test shows siblings ran and `meta.op_errors` populated
- `.agent/.nav-dispatch-health.json` written on error and surfaced at the next SessionStart
- Timing fixture holds UserPromptSubmit dispatch ≤200ms p95 in CI

## Refs

- Plan: `~/.claude/plans/the-cocept-of-the-delightful-dongarra.md` (§Architecture decision 1
  and 5, §Module layout, §Routing matrix, §Risk register, §Test strategy)
- TASK-57 (spike gate), TASK-59 (nav_hook_lib substrate), TASK-61 (op ports consume harness)
- `hooks/test_workflow_enforcer.py` — contract-test template
- `.agent/knowledge/memories/pitfalls/`: mem-034, mem-035, mem-036, mem-037

**Last Updated**: 2026-07-10
