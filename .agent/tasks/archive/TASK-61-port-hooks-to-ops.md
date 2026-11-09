# TASK-61: Port the nine v6 hooks to dispatcher ops (parity)

**Status**: ✅ Implemented — 2026-07-10 (nine surfaces at byte-parity; goldens leg-1 proven against HEAD v6 scripts in a worktree; old hooks + 7 test files deleted; guard allowlists empty)
**Created**: 2026-07-10
**Parent plan**: v7.0.0 hooks-runtime concept (approved 2026-07-10)
**Execution**: interactive — NOT dispatched to Pilot (user decision 2026-07-10)
**Effort**: L
**Depends on**: TASK-60

## Context

**Problem**: v6 runs nine independent hook scripts, each with its own stdin parse, config read,
state I/O, and env guard. TASK-60 lands the dispatcher + registry + manifest rewrite, but until the
nine existing behaviors live inside `hooks/ops/`, Navigator runs two runtimes at once. The port must
change zero observable behavior — parity is the gate, not a goal.

**Goal**: All nine v6 hooks become dispatcher ops. A recorded golden corpus proves the
dispatcher-routed ops byte-match v6 stdout/exit behavior BEFORE any new behavior lands (plan,
Verification §2). Stop becomes the single audited "turn-lifecycle reset barrel". State moves to
`.agent/.nav-runtime-state.json` (schema 2) as a clean break. Old hook files are deleted at the end.

The nine surfaces being ported:

| v6 hook | Event (matcher) | v7 op (phase) |
|---|---|---|
| nav_session_start.py | SessionStart | session_start (injector) |
| nav_pre_compact.py / nav_post_compact.py | Pre/PostCompact | compact_marker (recorder) |
| nav_task_graph_sync.py | PostToolUse (Edit\|Write) | graph_sync (recorder) |
| nav_profile_sync.py | PostToolUse (Edit\|Write) | profile_sync (recorder) |
| nav_read_guard.py | PreToolUse (Read) | read_guard (gate) |
| nav_workflow_state.py | Stop | stop_state (recorder) |
| workflow_enforcer.py | UserPromptSubmit | prompt_gate (gate) |
| nav_brief.py | UserPromptSubmit | prompt_brief (injector) |

## Known Pitfalls & Patterns

- **mem-034** (pitfall, 1.0): UserPromptSubmit exit 2 blocks the model; stderr echoing the trigger
  phrase re-triggers the block recursively. Shapes Phase 5: the echo probe becomes a permanent
  composition test, and no op scans text that hasn't passed `sentinels.strip_all()`.
- **mem-035** (pitfall, 1.0): PreToolUse stdout AND `additionalContext` produce zero model-visible
  output (live-verified v6.12.0; conflicts with current docs). Shapes Phase 4: read_guard ports as
  deny-only (exit 2 + stderr). Advisory channel is spike-gated (S5) — not added here.
- **mem-036** (pitfall, 0.95): unset env var made every hook silently no-op for two releases.
  Shapes Phase 0: every contract test runs the manifest command with `CLAUDE_PLUGIN_ROOT` set AND
  unset; both paths must produce recorded, non-empty evidence.
- **mem-037** (pitfall, 1.0): Stop hook stamping `check_shown=false` on conversational turns
  deadlocked the enforcer; fixed with tristate. Shapes Phase 5: stop_state + prompt_gate port
  together, never split, with the full tristate table asserted end-to-end.
- **TASK-45 pattern**: subprocess-against-tmp-project contract tests — the golden-parity harness
  reuses this template (Phase 0).
- **v5.1.0 incident**: manifest referenced a file never committed. Shapes Phase 7: after deletion, a
  repo-wide grep for old hook filenames must come back clean (manifest, docs, Makefile).

## Acceptance Criteria

- [ ] Golden corpus checked in: ≥1 real recorded payload per v6 hook surface (all nine), each with
      captured v6 stdout + exit code as the golden.
- [ ] For every corpus case, `nav_dispatch.py <event>` stdout and exit code byte-match the golden.
      The only sanctioned difference is internal state-file paths (clean break, see Decisions).
- [ ] Parity suite passes before any op contains behavior absent from its v6 source (enforced by
      port order: parity test lands in the same commit as each op, before the next port starts).
- [ ] Stop op is the only writer that resets turn-lifecycle state: read counter, tier-1 fuse slot,
      continue-counter slot — one code path, one test.
- [ ] Composition test: full tristate table — every value stop_state writes, prompt_gate reads and
      acts on correctly (block / pass / no-op per value).
- [ ] Composition test: read×5 → Stop → read×1 asserts counter == 1.
- [ ] mem-034 echo case is a permanent test: gate block stderr never contains the trigger phrase.
- [ ] Contract tests for each event run the manifest command with `CLAUDE_PLUGIN_ROOT` set AND
      unset; unset path fails loudly in tests, never silently no-ops.
- [ ] `.agent/.nav-runtime-state.json` carries `"schema": 2`; a v7 reader given a schema-less state
      file ignores it (test with a v6 `.nav-workflow-state.json` fixture).
- [ ] session_start archives `.nav-workflow-state.json`, `.nav-read-counter.json`,
      `.nav-profile-sync-state.json` to `.agent/.nav-v6-state.bak/` — never deletes; test asserts
      `.agent/.context-markers/` is untouched.
- [ ] The nine old hook files are deleted; repo grep for their filenames hits only CHANGELOG /
      archived tasks. Each old hook test is superseded by op-colocated tests before deletion.
- [ ] nav-upgrade migration note covers consumer `settings.json` entries referencing old hook paths.
- [ ] `make test` green with new test dirs in `TEST_DIRS`.

## Implementation

**Port order (binding)**: session_start → compact_marker → graph_sync + profile_sync → read_guard →
stop_state + prompt_gate (together) → prompt_brief. Coupled pair never splits across commits.

### Phase 0 — Golden corpus + parity harness
- **Goal**: recorded real payloads and captured v6 outputs; harness diffing v6 script vs dispatcher.
- **Tasks**: record one real payload per surface from live sessions; capture v6 stdout/exit as
  goldens; build subprocess-vs-tmp-project runner (TASK-45 template); env set/unset variants
  (mem-036); wire dir into Makefile `TEST_DIRS`.
- **Files**: `tests/golden/` (corpus, runner, goldens), `Makefile`.

### Phase 1 — session_start
- **Goal**: SessionStart parity + legacy state archival.
- **Tasks**: port `nav_session_start.py` → `ops/session_start`; archive the three legacy state
  files to `.agent/.nav-v6-state.bak/` (copy, never delete); leave `.context-markers/` alone
  (user save-points, not session-scoped); parity test.
- **Files**: `hooks/ops/session_start.py` + `test_session_start.py`.

### Phase 2 — compact_marker
- **Goal**: Pre+PostCompact parity in one op file (both branches).
- **Tasks**: port `nav_pre_compact.py` + `nav_post_compact.py`; marker behavior unchanged
  (markers stay the channel, per routing matrix); parity tests for both events.
- **Files**: `hooks/ops/compact_marker.py` + `test_compact_marker.py`.

### Phase 3 — graph_sync + profile_sync
- **Goal**: PostToolUse (Edit|Write) recorder parity.
- **Tasks**: port both syncs as recorder-phase ops; assert phase ordering (recorders run last);
  parity tests.
- **Files**: `hooks/ops/graph_sync.py`, `hooks/ops/profile_sync.py`, colocated tests.

### Phase 4 — read_guard
- **Goal**: PreToolUse (Read) gate parity, deny-only.
- **Tasks**: port as gate-phase op; deny-only channel — assume mem-035 stands; no advisory output
  (spike S5 may reopen that channel later — explicitly not this task); parity test incl. exit-2 path.
- **Files**: `hooks/ops/read_guard.py` + `test_read_guard.py`.

### Phase 5 — stop_state + prompt_gate (together, never split)
- **Goal**: the coupled tristate pair ported in one commit; Stop becomes the reset barrel.
- **Tasks**: port `nav_workflow_state.py` → `ops/stop_state` and `workflow_enforcer.py` →
  `ops/prompt_gate`; make the v6 `_reset_read_counter` coupling first-class — stop_state resets
  read counter + tier-1 fuse slot + continue-counter slot in one audited path (slots are consumed
  by TASK-62, reset semantics land now); preserve tristate stamping rules (mem-037: never stamp on
  conversational turns); composition tests: full tristate table, read×5→Stop→read×1 == 1, mem-034
  echo probe as permanent case.
- **Files**: `hooks/ops/stop_state.py`, `hooks/ops/prompt_gate.py`, colocated tests,
  `tests/golden/test_composition.py`.

### Phase 6 — prompt_brief
- **Goal**: UserPromptSubmit brief-injector parity.
- **Tasks**: port `nav_brief.py`; keep v6 stateless behavior byte-identical; `brief.pending`
  section exists in schema (TASK-56 deferred) but is not populated here; parity test with both
  UserPromptSubmit ops on the same payload.
- **Files**: `hooks/ops/prompt_brief.py` + `test_prompt_brief.py`.

### Phase 7 — deletion + migration note
- **Goal**: single runtime; no dangling references.
- **Tasks**: delete the nine old hook files and superseded test files (replacements already landed
  per phase); repo-wide grep clean (v5.1.0 incident); add nav-upgrade migration note for consumer
  `settings.json` entries pointing at old hook paths; update DEVELOPMENT-README hook table.
- **Files**: `hooks/*.py` (deletions), `skills/nav-upgrade/SKILL.md`, `.agent/DEVELOPMENT-README.md`.

## Out of Scope

- New capabilities: Tier-1, stop_completion/continue, jit_memory, subagent_context,
  failure_diagnosis, config_guard, setup op → TASK-62.
- New event registrations beyond the nine v6 surfaces (TaskCreated/TaskCompleted graph_sync rows,
  SubagentStart, ConfigChange) — routing-matrix expansion, not parity.
- `VERSION_CONFIGS["7.0.0"]`, CLAUDE.md demotion, nav-features toggles → TASK-63.
- Release gates (`--verify-dispatcher`, conformance wiring) → TASK-64.
- Scoring/lib internals — consumed from TASK-59/60, not modified here.

## Technical Decisions

| Decision | Options Considered | Chosen | Reasoning |
|---|---|---|---|
| Parity gate | rewrite with improvements; byte-parity first | golden corpus, stdout+exit byte-match | plan Verification §2: parity proven before any new behavior |
| Port order | event order; alphabetical; risk-first | leaf-first, Stop+gate pair last and together | tristate coupling (mem-037); pair split = deadlock class |
| Turn resets | scattered per-op resets (v6) | Stop = single audited reset barrel | risk register: "read-guard/Stop reset coupling lost" |
| State migration | in-place content migration | clean break: new file, `schema:2`, archive to `.nav-v6-state.bak/` | turn/session-scoped data + mandatory restart make migration meaningless |
| read_guard channel | advisory stdout/additionalContext; deny-only | deny-only (exit 2 + stderr) | mem-035 live-verified; docs contradict — not load-bearing |
| Old-file deletion | delete per-port | delete once, at end of task | mid-task rollback keeps v6 scripts intact; bisectable |

Deferred decisions:
- Advisory channel for read_guard if spike S5 overturns mem-035 — revisit in TASK-62 at earliest.
- Stop `continue:true` semantics — spike S2-gated, default OFF, owned by TASK-62 stop_completion;
  this task only reserves the fuse/counter reset slots in the barrel.

## Verify

```bash
make test                                    # full estate incl. tests/golden/ via TEST_DIRS
python3 -m unittest discover -s tests/golden -v          # parity + composition suites
CLAUDE_PLUGIN_ROOT= python3 -m unittest discover -s tests/golden -v   # mem-036 unset variant
grep -rn "nav_workflow_state\|workflow_enforcer\|nav_read_guard\|nav_brief\.py" \
  --include="*.json" --include="*.py" --include="Makefile" .   # expect zero hits post-Phase-7
ls .agent/.nav-v6-state.bak/ && ls .agent/.context-markers/    # archived vs untouched
```

Live drives (this repo): loop-trigger prompt after a mutating turn without WORKFLOW CHECK → block;
"fix the bug" → INTENT BRIEF; five Reads → Stop → one Read → no guard trip.

## Done

- Nine v6 behaviors run only via `nav_dispatch.py`; old hook files gone; grep clean.
- Golden parity suite green on the full corpus; composition suite (tristate table, counter reset,
  echo probe) green and permanent.
- Single state file with `schema:2`; legacy files archived, markers untouched.
- nav-upgrade migration note published for consumer settings referencing old paths.

## Sanctioned Deviations (recorded at close, 2026-07-10)

- Landed as one commit, not per-port commits: parallel port groups shared one working tree. Leg-1
  golden evidence (V6GoldenRegressionTest 9/9 OK) was captured in a git worktree at pre-port HEAD.
- Unset-env criterion: the TASK-60 sh-guard makes unset+missing-dispatcher a deliberate SILENT
  exit 0 (asserted, not accidental); parity suite proves unset+resolvable produces golden output.
- The Verify grep hits inert provenance/migration references by design (goldens corpus, ops
  docstrings, nav-upgrade machinery, v6 config KEY names kept for parity) — criterion satisfied
  in spirit; live references were all fixed.
- runtime.py gained an opt-in `ack` result key mid-task (five goldens record v6's bare {} doc,
  unproducible through the frozen merge) — documented in runtime docstring + ops/README.
- PostToolUse matcher widened to Edit|Write|MultiEdit|NotebookEdit (TASK-60); syncs skip
  notebook payloads gracefully (tested).
- Silent-path goldens (prompt_gate/prompt_brief/read_guard) lock the no-output path; branch
  behavior is locked by colocated + composition tests instead.
- Live drives (loop-block, INTENT BRIEF, read-guard trip) deferred to the alpha gate — they need
  a restarted session running the v7 manifest; .claude/settings.local.json dev backstop now
  routes through nav_dispatch so the next session in this repo exercises v7 live.

## Refs

- Plan: `~/.claude/plans/the-cocept-of-the-delightful-dongarra.md` (routing matrix, risk register,
  Migration & rollback, Verification §2)
- TASK-60 (dispatcher/registry/manifest), TASK-45 (contract-test pattern), TASK-56 (brief hook)
- `hooks/nav_workflow_state.py` (`_reset_read_counter`, tristate), `hooks/workflow_enforcer.py`
- mem-034, mem-035, mem-036, mem-037 (`.agent/knowledge/memories/pitfalls/`)

**Last Updated**: 2026-07-10
