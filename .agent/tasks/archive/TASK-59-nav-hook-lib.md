# TASK-59: nav_hook_lib — Shared Hook Runtime Library

**Status**: ✅ Implemented — 2026-07-10 (217 lib tests; corpus 49 prompts ≤1 tier; guards widened
to hooks/ with v6-file allowlist; PreToolUse dropped from additional_context — permission-bypass
finding; state gains flock lock() + fail-closed session scoping per adversarial review)
**Created**: 2026-07-10
**Parent plan**: v7.0.0 hooks-runtime concept (approved 2026-07-10)
**Execution**: interactive — NOT dispatched to Pilot (user decision 2026-07-10)
**Effort**: M
**Depends on**: TASK-57

## Context

**Problem**: v6 is nine independent hook scripts that each re-implement I/O, config reads,
PILOT_EXECUTOR checks, sentinel handling, and scoring. The duplication is how bugs ship: two
contradictory complexity models coexist (additive vs base-0.5±), PILOT_EXECUTOR is re-checked per
hook (one miss = interactive block under Pilot), and stderr hygiene depends on every author
remembering mem-034. The v7 dispatcher (TASK-60) cannot be built on this.

**Goal**: extract `hooks/nav_hook_lib/` — the pure-stdlib runtime library every v7 op imports.
Nine modules: `hio.py`, `config.py`, `state.py`, `sentinels.py`, `transcript.py`, `scoring.py`,
`signals.py`, `budget.py`, `memory.py`. Behavior-preserving for scoring (characterization corpus);
old scorer paths become re-export shims. Depends on TASK-57 only because the recorded channel
facts shape the emitter API in `sentinels.py`/`signals.py` — design against spike memories, never
against harness docs.

## Known Pitfalls & Patterns

- **mem-034** (pitfall, confidence 1.0): exit 2 on UserPromptSubmit blocks the model; stderr that
  echoes the trigger phrase re-triggers the block recursively. → Phase 3: `sentinels.py` owns the
  ONLY stderr emitter, and it redacts trigger phrases; a lint-style test greps ops/hooks for raw
  stderr writes. The structural rule "no op scans unstripped text" is this memory made
  architectural.
- **mem-035** (pitfall, confidence 1.0): PreToolUse stdout AND `additionalContext` produce zero
  model-visible output (live-verified v6.12.0) — current docs claim otherwise. → Phase 3 emitter
  API exposes per-channel helpers only for channels a TASK-57 memory proved; anything else is
  spike-gated and excluded from the API surface.
- **mem-037** (pitfall, confidence 1.0): Stop hook stamping state on conversational turns
  deadlocked the enforcer; fixed by tristating `check_shown` (True/False/None). → Phase 2:
  `state.py` schema v2 preserves the tristate exactly — no boolean coercion on read or write.
- **TASK-48** (precedent): ambiguity ≠ complexity; scorers stay separate. → Phase 4 unifies the
  two complexity variants into one additive model but keeps ambiguity a separate axis on
  `ScoreCard`; the ambiguity scorer is wrapped, not merged.

## Acceptance Criteria

- [ ] `hooks/nav_hook_lib/` imports with stdlib only — a test scans lib sources and fails on any
      non-stdlib import
- [ ] `config.load()` against a pristine v6.18.1 config fixture returns safe defaults for every
      missing v7 block; zero `KeyError` possible (layered-defaults test iterates all blocks)
- [ ] `is_pilot_executor()` in `config.py` is the single policy point — a grep-style test fails if
      `PILOT_EXECUTOR` is read anywhere else under `hooks/`
- [ ] `state.py` round-trips schema v2 (`session, turn, reads, completion, brief, jit, profile,
      compact, meta`): atomic tmp+rename write, per-section staleness TTLs expire independently,
      differing `session.id` yields section-absent, `turn.signals.check_shown` tristate survives
- [ ] `sentinels.strip_all()` removes every current AND legacy sentinel tag (fixture lists all);
      lint test greps op/hook sources for `sys.stderr` writes outside `sentinels.py` — must be zero
- [ ] stderr emitter redacts trigger phrases (mem-034 echo case is a permanent unit test)
- [ ] `scoring.score(prompt)` returns `ScoreCard{complexity, tier, intent, ambiguity, triggers}`;
      intent router's skill patterns live in a data table, matching uses word-boundary
      `contains_phrase`
- [ ] Characterization corpus of ~40 real prompts: every v6 classification preserved within one
      tier of the unified model's output
- [ ] Old scorer modules (`workflow_detector`, `complexity_detector`, `skill_detector`,
      `ambiguity_scorer`) reduced to ≤5-line re-export shims; their existing test files still pass
- [ ] `signals.py`: nav-signal v3 emit→parse round-trip; pilot-signal v2 input parses and
      normalizes to v3; emit output matches vendored Pilot regex (round-trip incl. CRLF case)
- [ ] `transcript.py` tail-reader byte-matches `nav_workflow_state.py` behavior on a recorded
      transcript fixture
- [ ] `make test` green; no regression in `hooks/test_workflow_enforcer.py` / `test_hooks_smoke.py`

## Implementation

### Phase 1 — Package scaffold, `hio.py`, `config.py`
**Goal**: foundations every other module imports.
**Tasks**: `safe_read` / `safe_json` / atomic tmp+rename write / `project_root` / stdin payload
parse extracted from the nine v6 hooks; layered config defaults (missing block = safe/off, per
plan's old-consumer-config risk row); single `is_pilot_executor()`.
**Files**: `hooks/nav_hook_lib/{__init__,hio,config}.py` + colocated `test_*.py`; pristine
v6.18.1 config fixture under `hooks/nav_hook_lib/fixtures/`.

### Phase 2 — `state.py` (RuntimeState v2)
**Goal**: single state file `.agent/.nav-runtime-state.json`, `schema: 2`.
**Tasks**: namespaced sections per plan decision 2; section-level TTLs; different `session.id` ⇒
section absent; `check_shown` tristate preserved (mem-037); `meta.writer` / `meta.op_errors`
fields present; readers ignore schema-less files (v6 leftovers).
**Files**: `hooks/nav_hook_lib/state.py` + `test_state.py`.

### Phase 3 — `sentinels.py`, `signals.py` (channel-facing; consumes TASK-57 memories)
**Goal**: the only text-emission and text-scanning primitives in v7.
**Tasks**: ALL sentinel constants incl. legacy tags; `strip_all()`; sole stderr emitter with
trigger-phrase redaction (mem-034); lint-style test grepping for raw stderr writes; nav-signal v3
grammar (types `exit`/`status`/`check`/`brief`/`defer`) emit+parse; pilot-signal v2 compat parser
normalizing to v3 (Pilot's external contract frozen); per-channel emit helpers derived from the
TASK-57 memories only (mem-035 discipline).
**Files**: `hooks/nav_hook_lib/{sentinels,signals}.py` + tests incl. vendored-Pilot-regex
round-trip.

### Phase 4 — `scoring.py` unification + characterization corpus + shims
**Goal**: one scorer, provably v6-equivalent within a tier.
**Tasks**: additive complexity model replacing the base-0.5± variant; intent router with skill
patterns as a data table; lift `_contains_phrase` from `workflow_detector.py`; wrap (not merge)
the ambiguity scorer (TASK-48); build the ~40-prompt corpus from real v6 prompts; convert old
scorer files to ≤5-line re-export shims (delete in v8).
**Files**: `hooks/nav_hook_lib/scoring.py`, `test_scoring.py` (corpus embedded or fixture);
shims in `skills/nav-start/functions/workflow_detector.py`,
`skills/nav-workflow/functions/{complexity_detector,skill_detector}.py`,
`skills/nav-brief/functions/ambiguity_scorer.py`.

### Phase 5 — `transcript.py`, `budget.py`, `memory.py`
**Goal**: remaining shared utilities.
**Tasks**: tail-reader extracted from `nav_workflow_state.py` (fixture parity test); `budget.py`
char-budget clamps for injection payloads (SessionStart 9.5k / SubagentStart 2k per routing
matrix); `memory.py` thin wrapper over `skills/nav-graph/functions/memory_recall.py` preserving
its timeout/silent-skip semantics.
**Files**: `hooks/nav_hook_lib/{transcript,budget,memory}.py` + tests.

## Out of Scope

- `runtime.py` / `registry.py`, the dispatcher shim, and manifest rewrite — TASK-60
- Porting the nine hooks to ops / golden parity tests — TASK-61 (v6 hooks keep running as-is)
- New capabilities (Tier-1, stop_completion, jit_memory, subagent_context) — TASK-62
- config_migrator `VERSION_CONFIGS["7.0.0"]` and CLAUDE.md demotion — TASK-63
- Deleting the re-export shims (scheduled for v8, per plan "shims for one major")
- Harness-conformance suite packaging — TASK-58

## Technical Decisions

| Decision | Options Considered | Chosen | Reasoning |
|---|---|---|---|
| Complexity model | keep both variants; base-0.5±; additive | additive | plan §4: kills the contradictory base-0.5± variant |
| Ambiguity handling | fold into complexity; separate axis | separate axis on ScoreCard | TASK-48 precedent: ambiguity ≠ complexity |
| Old scorer paths | delete now; shim | ≤5-line re-export shims | rollback safety for one major; delete in v8 |
| State layout | per-hook files; single namespaced file | single `.nav-runtime-state.json` v2, atomic tmp+rename | plan decision 2: one read/write per event |
| stderr emission | per-op writes; central emitter | only emitter in `sentinels.py`, redacting | mem-034; enforced by lint-style grep test |
| Text scanning | ad-hoc per op; strip-first rule | no op scans unstripped text (`strip_all()`) | plan decision 3: mem-034 made architectural |
| Pilot compat | dual emit; parse-and-normalize | parser accepts pilot-signal v2 → v3 | Pilot supervisor contract frozen |
| Dependencies | third-party allowed; stdlib | pure stdlib | hooks must run on any user Python |

Deferred decisions (not table rows — still open):
- PreToolUse advisory channel: mem-035 says dead; TASK-57 S5 may reopen it. Emitter API stays
  deny-only until a superseding memory exists.
- Final indicators vocabulary for the v3 `exit` type: seeded from
  `skills/nav-loop/functions/exit_gate.py`, finalized when `stop_completion` lands (TASK-62).
- Per-op fallback wiring when a spike probe failed (state-queue, next-event surfacing): owned by
  TASK-60/61, not by this library.

## Verify

```bash
make test                                    # full estate green, incl. new lib tests
python3 -m unittest discover -s hooks/nav_hook_lib -p 'test_*.py' -t .
grep -rn "sys.stderr" hooks/ --include="*.py" \
  | grep -v "nav_hook_lib/sentinels.py" | grep -v "test_"   # expect empty (lint test mirrors)
grep -rn "PILOT_EXECUTOR" hooks/ skills/ --include="*.py" \
  | grep -v "config.py" | grep -v "test_"                   # expect empty after Phase 1
python3 -m unittest discover -s skills/nav-workflow/functions   # shims exercised by tests
```

Plus: characterization corpus run prints per-prompt v6-vs-v7 tier diff (must all be ≤1 tier).

## Done

- `hooks/nav_hook_lib/` exists with the nine modules, colocated tests, pure stdlib
- v6 hooks still pass their existing suites unchanged (library extraction is additive this task)
- Scoring characterization corpus checked in and green; old scorer files are shims
- Sentinel/lint and PILOT_EXECUTOR single-point tests standing guard for TASK-60/61
- TASK-60 can start: dispatcher has a library to build on

## Refs

- Parent plan: `~/.claude/plans/the-cocept-of-the-delightful-dongarra.md` (module layout,
  decisions 2–5, test strategy, work breakdown row TASK-59)
- TASK-57 (spike memories — emitter API inputs), TASK-48 (separate scorers precedent)
- `hooks/nav_workflow_state.py` (transcript tail-reader source),
  `skills/nav-start/functions/workflow_detector.py` (`_contains_phrase` source)
- mem-034, mem-035, mem-037 — `.agent/knowledge/memories/pitfalls/`

**Last Updated**: 2026-07-10
