# TASK-63: Config migration + CLAUDE.md demotion

**Status**: ✅ Implemented — 2026-07-10 (8 v7 blocks seeded additively; template 47 lines; root CLAUDE.md 988→331 with hook annotations; liveness guard live-verified)
**Created**: 2026-07-10
**Parent plan**: v7.0.0 hooks-runtime concept (approved 2026-07-10)
**Execution**: interactive — NOT dispatched to Pilot (user decision 2026-07-10)
**Effort**: M
**Depends on**: TASK-60 (dispatch-health contract); runs in parallel with TASK-61/62 per plan —
successor-block and Tier-1 key names are finalized against TASK-61 op names / TASK-62 whitelist
before Phase 1 lands

## Context

**Problem**: v7 moves enforcement from CLAUDE.md prose into the hook runtime. Two artifacts must
follow: (1) consumer configs need the v7 blocks seeded safely — new blocking features off, existing
enforcement posture (`strict_block`) carried over, and rollback to v6.18.1 must find the config
intact; (2) CLAUDE.md (root + consumer template) still *mandates* behaviors the runtime now
enforces — duplicate mandates drift, and prose stripped before hooks are proven live leaves a
project with neither prose nor enforcement.

**Goal**: `VERSION_CONFIGS["7.0.0"]` in the config migrator (additive-only, safe seeds, inheritance
of v6 choices) + demote `templates/CLAUDE.md` ~206 → ~60 lines + annotate root CLAUDE.md so every
surviving operative sentence names its enforcing hook + sequencing guard in nav-sync-claude so
regeneration only happens after hook liveness is confirmed. `nav-features` surfaces all new toggles.

## Known Pitfalls & Patterns

- **mem-036** (pitfall, 0.95): env var unset → manifest hooks silently no-op for two releases.
  This is exactly the failure the sequencing guard exists for: Phase 5 gates CLAUDE.md
  regeneration on *observed* liveness (dispatch-health file freshness), never on manifest or
  config inspection, which both look fine while hooks are dead.
- **mem-037** (pitfall, 1.0): Stop hook stamping state on conversational turns deadlocked the
  enforcer; its v7 successor risk is stop-continue runaway. Shapes Phase 1 seeds:
  `stop_completion.continue_enabled: false`, `max_continues: 2` — off until proven, capped when on.
- **v6.18.1 precedent**: decision extractor regressed on wide table-separator rows. Phases 3–4
  rewrite CLAUDE.md tables — keep separators at exactly `|---|` per cell.
- **TASK-45 pattern**: contract tests run the real artifact against tmp fixtures. Phase 2
  exercises the migrator CLI against tmp config files (pristine v6.18.1 fixture), not only
  imported internals.

## Acceptance Criteria

- [ ] `VERSION_CONFIGS["7.0.0"]` exists with: `dispatcher` block, Tier-1 per-rule toggles,
      `stop_completion` (`continue_enabled: false`, `max_continues: 2`), and successor blocks for
      `workflow_enforcer_hook` / `read_guard_hook`.
- [ ] Migrating a pristine v6.18.1 config adds v7 blocks and leaves every pre-existing key
      byte-identical — no deletions, no renames (rollback to v6.18.1 finds config intact).
- [ ] Successor blocks inherit the user's existing `strict_block` values (fixture matrix:
      true→true, false→false, block absent→shipped default), not fresh defaults.
- [ ] Every net-new blocking/intercepting feature seeds OFF (stop-continue disabled; Tier-1 cut
      disabled until enabled per rule). Successors of existing gates keep the inherited posture.
- [ ] Running the migrator twice on the same config produces byte-identical output (idempotent).
- [ ] `templates/CLAUDE.md` ≤ ~60 lines containing only: Project Context, Code Standards, one
      "Navigator runtime" paragraph (config off-switches + `PILOT_EXECUTOR`), and the preserved
      customization region.
- [ ] Root CLAUDE.md: WORKFLOW CHECK mandate, session-start ritual, forbidden-actions-as-mandate,
      loop exit rules, and brief instructions removed as mandates; every surviving operative
      sentence carries "enforced by hook X — this text is documentation, not the mechanism".
- [ ] nav-sync-claude refuses CLAUDE.md regeneration when the dispatch-health file is absent or
      stale, and proceeds when fresh; refusal message names the guard and the file checked.
- [ ] "show features" (nav-features) lists every new v7 toggle with its current value.

## Implementation

### Phase 1 — VERSION_CONFIGS["7.0.0"] + inheritance seeding

**Goal**: v7 config blocks, additive-only, safe defaults, v6 posture carried.
**Tasks**:
- Add `"7.0.0"` entry: `dispatcher`, Tier-1 per-rule toggle block, `stop_completion`
  (`continue_enabled: false`, `max_continues: 2`), successors of `workflow_enforcer_hook` and
  `read_guard_hook` (final key names from TASK-61 op names / TASK-62).
- Extend the migrator to support derived seeds: today `VERSION_CONFIGS` values are static;
  successor blocks need their `strict_block` computed from the user's existing v6 block.
- Enforce additive-only: migrator never deletes or renames v6 blocks; v6 blocks stay as-is even
  once superseded (cleanup deferred to a 7.x minor).
**Files**: `skills/nav-sync-claude/functions/config_migrator.py`

### Phase 2 — Migrator tests

**Goal**: idempotency, additive-only, and inheritance proven against fixtures.
**Tasks**:
- Extend existing idempotency coverage (`test_seeding_is_idempotent_on_second_run`) to the 7.0.0
  blocks; add double-run byte-identity check via the CLI against a tmp fixture (TASK-45 pattern).
- Pristine v6.18.1 fixture: assert every v6 key survives migration unchanged.
- Inheritance matrix: `strict_block` true / false / absent → expected successor values.
- New-blocking-seeds-off assertions for `stop_completion` and Tier-1 rules.
**Files**: `skills/nav-sync-claude/functions/test_config_migrator.py`

### Phase 3 — templates/CLAUDE.md demotion (~206 → ~60 lines)

**Goal**: consumer template carries context, not enforcement.
**Tasks**:
- Keep: Project Context, Code Standards, preserved customization region.
- Add one "Navigator runtime" paragraph: lists config off-switches (per-block `enabled`,
  `strict_block`, Tier-1 per-rule, `stop_completion.continue_enabled`) and `PILOT_EXECUTOR`.
- Delete workflow/session/loop/brief mandates (now runtime). Keep any tables at `|---|` separators.
- Confirm `claude_updater.py` customization extraction still round-trips the new template shape.
**Files**: `templates/CLAUDE.md`, `skills/nav-sync-claude/functions/claude_updater.py` (if needed)

### Phase 4 — Root CLAUDE.md annotation pass

**Goal**: philosophy stays; mandates die into runtime; remainder is documentation.
**Tasks**:
- Remove as mandates: WORKFLOW CHECK block requirement, session-start ritual, forbidden-actions
  list-as-mandate (→ config policy), loop exit rules, brief instructions.
- Annotate each surviving operative sentence: "enforced by hook X — this text is documentation,
  not the mechanism" (op names per TASK-61/62).
- Keep philosophy, docs map, project context, code standards.
**Files**: `CLAUDE.md`

### Phase 5 — nav-sync-claude sequencing guard

**Goal**: never leave a project with neither prose nor enforcement.
**Tasks**:
- Before regenerating CLAUDE.md to the demoted template, check dispatch-health file freshness
  (written by the dispatcher, per TASK-60); absent/stale → abort regeneration, keep existing
  prose, report why and what to do (start a session so hooks stamp health, then re-sync).
- Test both branches: fresh file → regenerates; absent/stale → refuses (mem-036 class).
**Files**: `skills/nav-sync-claude/functions/claude_updater.py`, its tests

### Phase 6 — nav-features toggle surfacing

**Goal**: every new v7 toggle discoverable and flippable via "show features".
**Tasks**: register `dispatcher`, Tier-1 per-rule toggles, `stop_completion`, and successor-block
switches in the feature manager; verify listing + toggle round-trip.
**Files**: `skills/nav-features/functions/feature_manager.py`, `skills/nav-features/SKILL.md`

## Out of Scope

- Deleting/renaming deprecated v6 config blocks — deferred to a 7.x minor (additive-only rule).
- Dispatcher/ops implementation and behavior of the toggled features (TASK-60/61/62). Note:
  `stop_completion` and Tier-1 are spike-gated (S2/S4); this task ships their config and prose
  surface regardless of spike outcome — the blocks toggle whatever TASK-62 lands.
- State-file migration and `.agent/.nav-v6-state.bak/` archival (handled with the runtime cutover).
- Release validation, rollback procedure doc, RC soak (TASK-64).
- Landing/docs-site copy updates.

## Technical Decisions

| Decision | Options Considered | Chosen | Reasoning |
|---|---|---|---|
| Migration strategy | rewrite blocks in place; additive-only | Additive-only | Rollback to v6.18.1 must find its config intact |
| New blocking defaults | seed on for visibility; seed off | Seed OFF | Stop-continue runaway is mem-037's successor risk; prove before enable |
| `strict_block` seeding | fresh defaults; inherit v6 value | Inherit | Upgrade must not silently change enforcement posture |
| v6 block cleanup | remove at 7.0.0; defer | Defer to 7.x minor | Additive-only rule; deprecation needs its own notice cycle |
| Regeneration timing | always on sync; gate on liveness | Gate on dispatch-health freshness | Never leave a project with neither prose nor enforcement |

Resolved during implementation (2026-07-10, Phases 1–2 + 5–6):
- Successor block key names — RESOLVED: v7 ops kept the v6 config keys verbatim
  (`workflow_enforcer_hook`, `read_guard_hook`, etc. — see
  `hooks/nav_hook_lib/registry.py` `OpSpec.config_key`), so NO successor blocks and NO
  renames exist. `strict_block` inheritance is satisfied by the additive-only rule:
  existing blocks are never touched, so the user's posture carries over unchanged and
  no derived-seed machinery was needed. (Also recorded in the `config_migrator.py`
  `VERSION_CONFIGS` docstring.)
- Tier-1 rule-id list — RESOLVED: `nav_stats`, `show_features`, `list_markers`,
  `graph_health`, `nav_version` (TASK-62 whitelist), seeded per-rule `true` under
  `tier1.rules` with the `tier1.enabled` master switch `false`.
- Liveness freshness threshold — RESOLVED: 7 days. The health file is written by the
  dispatcher on ERROR only, so liveness proof is EITHER a fresh
  `.agent/.nav-runtime-state.json` (`meta.schema == 2`, `meta.updated` within 7 days)
  OR a fresh `.agent/.nav-dispatch-health.json` (`last_error.ts` within 7 days);
  absent both, nav-sync-claude refuses regeneration (exit 3) naming the guard, the
  files checked, and the remedy.

## Verify

```bash
make test                                            # full estate, incl. nav-sync-claude dir
python3 skills/nav-sync-claude/functions/config_migrator.py /tmp/fx/.nav-config.json
python3 skills/nav-sync-claude/functions/config_migrator.py /tmp/fx/.nav-config.json
# second run reports no changes; diff against first-run snapshot is empty
wc -l templates/CLAUDE.md                            # ≤ ~65
grep -c "WORKFLOW CHECK" templates/CLAUDE.md         # 0
grep -c "enforced by" CLAUDE.md                      # ≥ count of surviving operative sentences
```

Live: on this repo, run "sync CLAUDE.md" with dispatch-health file removed → refusal; start a
session (health stamped) → sync proceeds. Then "show features" lists v7 toggles.

## Done

- Upgraded consumer config contains all v7 blocks, all v6 blocks untouched, blocking features off,
  `strict_block` posture carried; second migrator run is a no-op.
- `templates/CLAUDE.md` at ~60 lines; root CLAUDE.md mandates replaced by hook annotations.
- nav-sync-claude demonstrably refuses regeneration without fresh dispatch-health.
- nav-features shows and flips every new toggle.

## Refs

- Plan: `~/.claude/plans/the-cocept-of-the-delightful-dongarra.md` (§Migration & rollback,
  §CLAUDE.md demotion, §Risk register "Old consumer configs")
- `skills/nav-sync-claude/functions/config_migrator.py`, `test_config_migrator.py`,
  `claude_updater.py`
- `templates/CLAUDE.md`, root `CLAUDE.md`
- `skills/nav-features/functions/feature_manager.py`
- TASK-61 (op ports), TASK-62 (Tier-1 / stop_completion), TASK-60 (dispatch-health writer)
- mem-036, mem-037; precedents: TASK-45, v6.18.1 separator regression

**Last Updated**: 2026-07-10
