# TASK-58: Harness-Conformance Suite — Spike Probes Become Regression Checks

**Status**: ✅ Implemented — 2026-07-10 (suite packaged + re-driven live on CC 2.1.205; results file checked in; make conformance-check wired)
**Created**: 2026-07-10
**Parent plan**: v7.0.0 hooks-runtime concept (approved 2026-07-10)
**Execution**: interactive — NOT dispatched to Pilot (user decision 2026-07-10)
**Effort**: S
**Depends on**: TASK-57

## Context

**Problem**: Harness drift is the #1 risk in the v7 register — CC ships weekly, and every channel
claim v7 builds on (PostToolUse `additionalContext`, Stop `continue:true`, UserPromptSubmit
block-as-answer, `${CLAUDE_PLUGIN_ROOT}` binding) is version-fragile. mem-034/035/036/037-class
discoveries currently live only as graph memories plus archaeology in old task docs; there is no
re-runnable artifact that says "on CC vX.Y.Z these channels behaved like THIS".

**Goal**: Package the six TASK-57 probes as a versioned, re-runnable suite under
`tests/harness-conformance/`, check in the first `results/cc-<version>.json`, and wire a
`make conformance-check` target that fails loudly when no results file exists for the currently
installed CC version. The suite is **semi-automated by design** (probes need a live CC session and
human rendering judgment) — CI-ADJACENT, not CI. The make target is the release-gate hook: the
plan's second hard gate requires ship-week CC conformance results before any v7 tag.

## Known Pitfalls & Patterns

- **mem-035** (confidence 100%, live-verified v6.12.0): PreToolUse stdout+`additionalContext`
  dropped — CONFLICTS with current docs. Docs are untrustworthy; only version-stamped empirical
  results count. Shapes Phase 2: every results file carries `cc_version` and per-probe evidence.
- **mem-036** (confidence 95%): env-var unset → hooks silently no-op'd for two releases. Probes
  must run through real marketplace manifest execution, never ad-hoc `settings.json` hooks.
  Shapes Phase 2: run.md setup mandates the scratch-marketplace install path; S6 stays a probe.
- **mem-034** (confidence 100%): UserPromptSubmit exit-2 stderr echoed back into the next prompt →
  recursion. Shapes Phase 1: sentinels are UUIDs generated per run (never static strings), and
  the S4 probe's echo-hygiene grep is a permanent pass criterion.
- **mem-037** (confidence 100%): Stop hook stamping state on conversational turns deadlocked the
  enforcer. Shapes Phase 1: the S2 probe body keeps the single-shot flag-file fuse from the
  spike; "fuse consumed, second run does not continue" is part of its recorded result.
- **TASK-45 precedent**: subprocess-against-tmp-project contract tests, stdlib unittest, no
  external deps. Shapes Phase 3: the results-schema test is a plain unittest in `make test`,
  needing no live CC — only the probe *runs* are manual.
- **v5.1.0 incident**: a skill referenced in the manifest was never committed. Same failure
  class this gate targets: an artifact assumed present but absent. Shapes Phase 3:
  `conformance-check` verifies the results file EXISTS and names the missing path when it fails.

## Acceptance Criteria

- [ ] `tests/harness-conformance/` contains six probe hook bodies, one per TASK-57 probe
      (S1–S6), each self-contained (stdlib only, no `nav_hook_lib` import — the lib is TASK-59
      and this task runs parallel to it)
- [ ] Probes generate a fresh UUID sentinel per run; `grep` finds no hardcoded sentinel values
- [ ] `run.md` is a complete human drive script: scratch-marketplace setup, exact prompts to
      send per probe, exact greps to run, pass/fail criteria copied from the TASK-57 table —
      executable end-to-end without opening the TASK-57 doc
- [ ] `run.md` states the standing rule: **new harness discovery → new probe + new memory,
      always paired** (a memory without a probe is archaeology; a probe without a memory is
      unexplained)
- [ ] `results/cc-<version>.json` checked in for the CC version installed at completion time,
      populated by re-driving the packaged suite (validates packaging, not just transcription)
- [ ] `make conformance-check` exits 0 when a results file matching `claude --version` exists;
      exits non-zero and prints the expected filename otherwise
- [ ] Schema-validation unittest covers all files under `results/` and runs in `make test`
- [ ] Where a probe outcome is spike-gated (S5 either-outcome; S2 fallback to `decision:block`),
      the results schema records the observed outcome — the suite asserts observation, not hope

## Implementation

### Phase 1 — Port probe bodies
**Goal**: Six standalone probe scripts, verbatim behavior from the validated TASK-57 bodies.
**Tasks**:
- Port spike hook bodies to `probe_posttooluse.py` (S1), `probe_stop.py` (S2, flag-file fuse
  retained per mem-037), `probe_subagent.py` (S3), `probe_userpromptsubmit.py` (S4,
  echo-hygiene check per mem-034), `probe_pretooluse.py` (S5, mem-035 re-test),
  `probe_env_binding.py` (S6, mem-036 re-check)
- UUID sentinel generation per run; sentinel written to a scratch file so run.md greps can
  reference the exact value
**Files**: `tests/harness-conformance/probe_*.py`

### Phase 2 — run.md drive script + results schema + first results file
**Goal**: A human can produce a valid results file for any CC version using only run.md.
**Tasks**:
- Write `run.md`: scratch marketplace-plugin install (real `${CLAUDE_PLUGIN_ROOT}` binding,
  mem-036), scratch project with no `.claude/settings.json` and no `.agent/`, per-probe prompt
  + grep + dual observable (behavioral quote-check AND transcript position), teardown
- Define results schema: `schema`, `cc_version`, `date`, `plugin_commit`, per-probe
  `{channel, pass, evidence, notes}`; document it in run.md
- Re-drive the suite on the installed CC version; check in `results/cc-<version>.json`
- Document the probe+memory pairing rule in run.md
**Files**: `tests/harness-conformance/run.md`, `tests/harness-conformance/results/cc-*.json`

### Phase 3 — Makefile wiring + schema test
**Goal**: Missing conformance results fail loudly; malformed results fail in `make test`.
**Tasks**:
- Add `conformance-check` target: parse `claude --version`, assert
  `tests/harness-conformance/results/cc-<version>.json` exists, print expected path on failure
- Add `test_results_schema.py` (stdlib unittest, TASK-45 pattern) validating every checked-in
  results file; add `tests/harness-conformance` to `TEST_DIRS`
**Files**: `Makefile`, `tests/harness-conformance/test_results_schema.py`

## Out of Scope

- `release_validator --verify-conformance` flag and `release.yml` wiring — TASK-64
- Dispatcher, `nav_hook_lib`, or any op code — TASK-59/60 (hard gate: no dispatcher code before
  spike memories exist)
- Probes beyond S1–S6 — added later under the pairing rule as discoveries happen
- Running live probes in CI — impossible by design (live CC session required)
- Automated CC-update detection triggering re-runs — not in the plan

## Technical Decisions

| Decision | Options Considered | Chosen | Reasoning |
|---|---|---|---|
| CI relationship | Full CI automation; CI-adjacent manual suite | CI-adjacent | Probes need a live CC session and human rendering judgment (S4); only the artifact check automates |
| Gate semantics | Run probes at release; verify results file exists | Verify file exists | Live runs can't happen in CI; loud failure forces a human re-run for the ship-week CC version |
| Results storage | Graph memories only; checked-in JSON per version | Checked-in `results/cc-<version>.json` | Memories (TASK-57) capture conclusions; version-pinned files capture greppable evidence per CC release |
| Probe source | Rewrite fresh; port TASK-57 bodies | Port spike bodies | Bodies are already live-validated; rewriting invites drift from proven pass criteria |

Deferred decisions:
- Promotion of the gate into `release_validator` / `release.yml` (`--verify-conformance`) — TASK-64
- Whether S5's outcome reopens a PreToolUse advisory channel — spike-gated; the suite records
  either outcome without designing on it

## Verify

```bash
make conformance-check                      # results file present for installed CC → exit 0
mv tests/harness-conformance/results/cc-*.json /tmp/ && make conformance-check; echo "exit=$?"
                                            # → non-zero, message names expected file; restore after
cd tests/harness-conformance && python3 -m unittest discover -p "test_*.py"   # schema test
make test                                   # suite dir picked up via TEST_DIRS
grep -rn "sentinel" tests/harness-conformance/probe_*.py | grep -v uuid       # no static sentinels
```

Plus one full manual pass: follow run.md end-to-end on the installed CC version and confirm the
produced results file matches the checked-in one (or supersedes it if CC updated mid-task).

## Done

- Six probe bodies live under `tests/harness-conformance/`, drivable via run.md alone
- First `results/cc-<version>.json` checked in, produced by the packaged suite
- `make conformance-check` green with results present, loud and red without
- Schema test runs in `make test`; pairing rule documented in run.md
- Harness drift detection changed from archaeology to `git diff results/`

## Refs

- Parent plan: v7.0.0 hooks-runtime concept — spike table (S1–S6), test strategy, risk register
- `.agent/tasks/TASK-57-*.md` — spike doc: probe bodies, pass criteria, scratch-marketplace method
- `.agent/tasks/TASK-45-hook-tests.md` — subprocess/tmp-project contract-test pattern
- `Makefile` — `TEST_DIRS`, target conventions
- Memories: mem-034, mem-035, mem-036, mem-037

**Last Updated**: 2026-07-10
