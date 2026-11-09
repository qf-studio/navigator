# TASK-64: v7.0.0 Release Gate — Validation, RC Soak, Rollback

**Status**: ✅ Closed — 2026-09-01 (v7.0.0 shipped via modified gate; see Gate Outcome)
**Created**: 2026-07-10
**Parent plan**: v7.0.0 hooks-runtime concept (approved 2026-07-10)
**Execution**: interactive — NOT dispatched to Pilot (user decision 2026-07-10)
**Effort**: M
**Depends on**: TASK-57, TASK-58, TASK-59, TASK-60, TASK-61, TASK-62, TASK-63

## Context

**Problem**: v7.0.0 is a big-bang release that replaces nine independent hooks with one dispatcher
runtime. The existing release gate does not cover the new failure classes: `release_validator.py`
has a working `--verify-hooks` flag (`verify_hooks()`, line 326) but release.yml's validate job
only runs `--verify-hook-paths` — the live check is NOT wired into CI (verified gap). Nothing
checks that manifest commands route through `nav_dispatch.py`, that registered op modules exist and
import (the v5.1.0 missing-skill incident, generalized to ops), or that harness-conformance
results exist for the CC version we ship against. Rollback is untested prose.

**Goal**: Ship v7.0.0 through a hard gate: extended CI validation, a ≥3-day RC soak on this repo
plus one Pilot STAGING worker, a verified marketplace downgrade path, and recorded Pilot sign-off.
Two hard gates restated from the plan: **no tag without ship-week CC conformance results, and no
tag without Pilot sign-off**. Sign-off concerns compatibility with the external Pilot product only;
the v7 tasks themselves are not dispatched to Pilot.

## Known Pitfalls & Patterns

- **mem-036** (pitfall, 0.95): manifest hooks with an env-var guard silently no-op'd for two
  releases when the variable was unset. → Phase 1: `--verify-hooks` must execute each manifest
  command with `CLAUDE_PLUGIN_ROOT` set AND unset; both paths must reach the dispatcher (fallback
  resolution), never a silent exit 0 with no output.
- **mem-037** (pitfall, 1.0): Stop hook stamping state on conversational turns deadlocked the
  enforcer; fixed by tristate. → Phase 1: the Stop-event representative stdin includes a
  conversational (non-mutating) turn fixture; assert the dispatcher does NOT emit `continue:true`
  on it — catches the "unconditional continue:true" class at release time.
- **mem-035** (pitfall, 1.0): live behavior contradicted docs on PreToolUse injection; harness
  claims are version-fragile. → Phase 2/5: `--verify-conformance` is a hard gate requiring a
  results file for the ship-week CC version, re-run before tagging if CC updated during soak.
- **v5.1.0 incident** (precedent): skill referenced in manifest but never committed shipped broken.
  → Phase 1: `--verify-dispatcher` generalizes the existence/committed/imports check to ops.
- **TASK-45** (precedent): subprocess-against-tmp-project contract-test pattern. → Phase 1 reuses
  it for dispatcher invocations (representative stdin via subprocess, assert on stdout/exit code).

## Acceptance Criteria

- [ ] release.yml validate job runs `--verify-hooks`; a dispatcher that exits non-zero or emits
      invalid output on any registered event fails CI
- [ ] `--verify-hooks` invokes the dispatcher once per registered event with representative stdin;
      asserts exit 0 AND valid event-shaped JSON (or documented empty output) per event
- [ ] Stop-event fixture with a conversational turn produces no `continue:true` in output
- [ ] `--verify-hooks` exercises each manifest command with `CLAUDE_PLUGIN_ROOT` set and unset;
      unset path resolves via fallback — a silent no-op on either path is a failure
- [ ] New `--verify-dispatcher`: every manifest hook command routes through `nav_dispatch.py`;
      every registry-declared op module exists on disk, is git-committed, and imports cleanly
- [ ] New `--verify-conformance`: fails unless `tests/harness-conformance/results/cc-<ver>.json`
      exists for the installed (ship-week) CC version (TASK-58 artifact)
- [ ] Version-bearing file audit recorded below: if v7 adds a 6th file (dispatcher `__version__`),
      bump-version.sh AND validator version checks are updated in the same commit
- [ ] `v7.0.0-rc1` tagged (bump script already accepts pre-release suffixes — verified) and soaked
      ≥3 days on the navigator repo + one Pilot STAGING worker
- [ ] Pilot coordination checklist complete and sign-off recorded in this doc (Phase 4)
- [ ] Marketplace downgrade to `navigator@6.18.1` executed and verified during RC week
- [ ] Written rollback procedure exists in `releases/RELEASE-NOTES-v7.0.0.md` (SHIP REQUIREMENT)
- [ ] `v7.0.0` tagged only after both hard gates pass

## Implementation

### Phase 1 — Validator additions

**Goal**: All three verification modes implemented and wired into CI.
**Tasks**:
- Add `--verify-hooks` to release.yml validate job (currently only `--verify-hook-paths` at
  line 39 and `--verify-tag` in the tag job).
- Extend `verify_hooks()`: per registered event, run the manifest command as a subprocess against
  a tmp project (TASK-45 pattern) with a representative stdin payload; assert exit 0 + parseable,
  event-shaped JSON. Fixture set includes the mem-037 conversational Stop turn. Run each command
  with env set and unset (mem-036).
- Implement `--verify-dispatcher` (manifest→dispatcher routing; registry op modules exist,
  committed, import cleanly) and `--verify-conformance` (ship-week results file present).
**Files**: `skills/nav-release/functions/release_validator.py`, `.github/workflows/release.yml`,
`skills/nav-release/functions/test_release_validator.py`.

### Phase 2 — Version-bearing file audit

**Goal**: Bump tooling and validator agree on the canonical version-location list.
**Tasks**: Audit whether v7 introduces a 6th version-bearing file (e.g. dispatcher `__version__`).
If yes: add to bump-version.sh (currently five locations) and to `check_version_consistency()` /
`check_version_match()` in the same commit. If no: record "still five" here.
**Files**: `scripts/bump-version.sh`, `skills/nav-release/functions/release_validator.py`.

### Phase 3 — RC tag + soak

**Goal**: `v7.0.0-rc1` running for ≥3 days on real workloads.
**Tasks**: `./scripts/bump-version.sh 7.0.0-rc1`, tag, publish via release.yml (CI-published,
verified workflow). Soak on this repo (daily use) and one Pilot STAGING worker. Log defects here;
any gate-relevant fix restarts the 3-day clock.
**Files**: version-bearing files, `releases/RELEASE-NOTES-v7.0.0.md` (draft).

### Phase 4 — Pilot coordination checklist + sign-off

**Goal**: Compatibility with the external Pilot product confirmed on RC output.
**Tasks** (each checked against the RC, not main):
- [ ] v2 signal parse on RC output via vendored-regex round-trip test
      (`` r'```pilot-signal\n(.+?)\n```' ``) including the CRLF adversarial case
- [ ] Headless end-to-end run through every new gate with zero interactive blocks
- [ ] Stop-continue × Pilot-loop interaction confirmed (unconditionally OFF under PILOT_EXECUTOR)
- [ ] Worker configs migrated
- [ ] Sign-off record filled in: `Signed off by: ____ / date: ____ / RC build: ____ / CC ver: ____`
**Files**: this doc (sign-off record), `tests/` pilot-signal round-trip test.

### Phase 5 — Rollback verification + final gate + tag

**Goal**: Proven escape hatch, then ship.
**Tasks**: During RC week, downgrade a live install to `navigator@6.18.1` via marketplace and
verify hooks/config still function (additive-only migration makes this safe by design — confirm
empirically). Write the rollback procedure into `releases/RELEASE-NOTES-v7.0.0.md`. Re-run
`--verify-conformance` against the ship-week CC version. With both hard gates green, bump to
`7.0.0` and tag.
**Files**: `releases/RELEASE-NOTES-v7.0.0.md`, version-bearing files.

## Out of Scope

- Dispatcher, ops, or lib code changes (TASK-59..62) — this task gates, it does not build
- Conformance suite implementation and probe scripts (TASK-58; this task only consumes results)
- config_migrator / CLAUDE.md demotion (TASK-63)
- Dispatching any v7 work to Pilot as tasks (user decision — sign-off is compatibility only)
- Post-ship v7.1 candidates (MessageDisplay etc., excluded in the plan)

## Technical Decisions

| Decision | Options Considered | Chosen | Reasoning |
|---|---|---|---|
| Live hook check in CI | manual pre-release run; CI job | promote `--verify-hooks` into release.yml validate job | flag exists but was never wired — verified gap; manual steps get skipped |
| Missing-artifact scope | skills only; skills + ops | `--verify-dispatcher` covers ops too | v5.1.0 incident class generalizes: registry entries can reference uncommitted modules |
| Conformance gating | advisory warning; hard gate | hard gate: no tag without ship-week CC results | mem-035 proved harness claims version-fragile; CC ships weekly during soak |
| Release path | direct v7.0.0 tag; RC + soak | v7.0.0-rc1, ≥3 days, this repo + Pilot staging | big-bang runtime replacement; soak is the only end-to-end evidence |
| Rollback strategy | git revert; marketplace downgrade | verified downgrade to @6.18.1 + written procedure as ship requirement | additive-only config migration keeps v6 blocks intact; procedure must be user-executable |

Deferred decisions:
- Whether v7 adds a 6th version-bearing file (dispatcher `__version__`) — settled by Phase 2 audit.
- Exact representative-stdin corpus per event — drawn from TASK-60 contract-test fixtures once
  those land; not designed here.

## Verify

```bash
python3 skills/nav-release/functions/release_validator.py --verify-hooks
python3 skills/nav-release/functions/release_validator.py --verify-dispatcher
python3 skills/nav-release/functions/release_validator.py --verify-conformance
grep -n "verify-hooks" .github/workflows/release.yml        # wired into validate job
./scripts/bump-version.sh 7.0.0-rc1 && git diff --stat      # all version-bearing files touched
make test && make conformance-check                          # incl. pilot-signal round-trip
claude plugin install navigator@6.18.1                       # rollback path, during RC week
```

## Done

- release.yml fails on a dispatcher that crashes, emits malformed JSON, or continue:true's a
  conversational Stop fixture — demonstrated by a deliberate red run before merge
- `v7.0.0-rc1` soaked ≥3 days on two real workloads with defect log in this doc
- Pilot sign-off record filled in; all five checklist items checked against RC output
- `releases/RELEASE-NOTES-v7.0.0.md` contains a tested rollback procedure to @6.18.1
- `v7.0.0` tag exists; marketplace serves it; both hard gates documented as passed

## Gate Outcome (2026-09-01)

The gate ran in a modified form, decided interactively by the user on 2026-09-01
("Conformance first, then ship"):

- **Conformance hard gate: PASSED as specified.** Full S1–S6 suite re-driven
  against ship-week CC **2.1.241** (results: `tests/harness-conformance/results/`
  `cc-2.1.241.json`). All channel verdicts identical to cc-2.1.205 — no harness
  change affects the runtime. One probe-harness defect found and fixed during the
  drive: the S6 SessionStart logger string-prefix-gated on `$PWD`, which arrives
  realpath'd (`/private/tmp/...`) under subprocess-driven sessions — a
  method-lesson-2 violation in the probe itself; glob widened in
  `harness/nav-spike/.claude-plugin/plugin.json`. Side observation recorded in
  the results file: on 2.1.241 headless, S4 exit-2 blocks no longer leak hook
  chrome to stderr (decision:block remains the shipped winner).
- **RC soak + Pilot sign-off hard gate: WAIVED by user decision 2026-09-01**, on
  the evidence of ~7 weeks of continuous dogfood (2026-07-10 → 2026-09-01) on
  two real workloads — this repo (daily interactive use) and a live Pilot-repo
  worker — far exceeding the 3-day RC intent. Dogfood defects were fixed as
  TASK-65..71; no `v7.0.0-rc1` was tagged and the Phase 4 formal sign-off record
  was not executed. Sign-off record: waived per above.
- **Phase 1 validator additions (`--verify-dispatcher`, `--verify-conformance`,
  release.yml `--verify-hooks` wiring): NOT implemented** — carried forward as a
  post-ship follow-up. Partial coverage shipped instead: `--verify-hook-paths`
  (all 13 manifest commands route through `nav_dispatch.py`, ran green) and
  `make conformance-check` (ran green for 2.1.241).
  **Follow-up opened 2026-10-08: TASK-99** (`tasks/archive/TASK-99-release-validator-dispatcher-conformance.md`).
- **Phase 2 audit**: still five version-bearing files; no dispatcher
  `__version__` added.
- **Rollback**: written procedure shipped in `releases/RELEASE-NOTES-v7.0.0.md`
  (additive-only migration); the live downgrade-to-@6.18.1 drill was not
  executed pre-tag.
- Pre-tag checks, all green: `--check-all` (post-bump), `--verify-hooks` 26/26
  set+unset across 13 events, `--verify-hook-paths`, `make test` 7/7,
  `make conformance-check`.

## Refs

- Plan: v7.0.0 hooks-runtime concept (approved 2026-07-10) — test strategy, migration & rollback,
  work breakdown sections
- `skills/nav-release/functions/release_validator.py`, `.github/workflows/release.yml`,
  `scripts/bump-version.sh`, `releases/RELEASE-NOTES-v7.0.0.md`
- TASK-57 (spike results), TASK-58 (conformance suite), TASK-60 (contract-test fixtures)
- mem-035, mem-036, mem-037; v5.1.0 incident; TASK-45 contract-test pattern

**Last Updated**: 2026-07-10
