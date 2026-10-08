# TASK-99: Release validator — dispatcher, conformance and live-hook gates in CI

**Status**: 📋 Planned — 2026-10-08
**Origin**: TASK-64 Phase 1, carried forward at v7.0.0 ship (2026-09-01) and never built
**Effort**: S–M (one validator file, one workflow, one test file)
**Depends on**: nothing open; `verify_mod` (TASK-84) already covers the mod side

## Problem

Release CI (`.github/workflows/release.yml`, job `validate`) runs `--check-all`,
`--verify-hook-paths`, `--check-version`, `--verify-tag` and `--verify-mod`. Three gaps from
TASK-64 remain:

1. **No op-module gate for the Python fallback.** `verify_mod` checks that every mod-owned op
   has a Python twin in `registry.py`, but nothing checks that every `OpSpec` in
   `hooks/nav_hook_lib/registry.py` has `hooks/ops/<name>.py` on disk, committed, and
   importable. This is the v5.1.0 missing-skill incident generalized to ops (mem-070 class).
2. **No conformance gate in CI.** `make conformance-check` exists but only runs locally
   against `claude --version`. CI pins Claude Code 2.1.287 in `validate-mod` and nothing asserts
   `tests/harness-conformance/results/cc-2.1.287.json` exists for it.
3. **`--verify-hooks` is not wired into CI.** It runs the 13 manifest commands with
   `CLAUDE_PLUGIN_ROOT` set and unset (mem-036 silent no-op class, mem-037 conversational Stop
   turn). The unset path resolves through
   `$HOME/.claude/plugins/marketplaces/navigator-marketplace`, which does not exist on a runner,
   so wiring it as-is would fail for the wrong reason (same cause as the `[unset]` failures on
   the dev laptop, see memory).

## Acceptance Criteria

- [ ] `--verify-dispatcher`: every manifest hook command in `.claude-plugin/plugin.json` names
      `hooks/nav_dispatch.py`; every distinct `OpSpec("<name>", ...)` in `registry.py` has
      `hooks/ops/<name>.py` that exists, is tracked by git (`git ls-files --error-unmatch`),
      and imports (`python3 -c "import ops.<name>"` with `hooks/` on `sys.path`, subprocess,
      exit 0). Output: resolved / problems lists; exit 1 on any problem.
- [ ] `--verify-conformance [VERSION]`: asserts
      `tests/harness-conformance/results/cc-<VERSION>.json` exists and parses as JSON. With no
      argument the version comes from `claude --version` (same as `make conformance-check`).
      release.yml passes the pinned mod version explicitly so CI never needs the `claude` binary.
- [ ] `verify_hooks()` gains a hermetic unset path: a tmp `HOME` with
      `.claude/plugins/marketplaces/navigator-marketplace` symlinked to the repo root, so the
      fallback resolution is exercised instead of a missing directory. Local runs keep working.
- [ ] `release.yml` `validate` job runs `--verify-dispatcher`, `--verify-conformance 2.1.287`
      (the version read from one place next to the `validate-mod` pin) and `--verify-hooks`.
- [ ] `test_release_validator.py`: a deleted op file, an untracked op file, a broken import, a
      missing results file and a manifest command that bypasses the dispatcher each fail the
      right check; the green path passes on the repo itself.
- [ ] `--check-all` is unchanged (it stays the fast local gate); the three new flags are
      separate steps so a CI failure names the gate.
- [ ] TASK-64 "Gate Outcome" gets one line pointing here; this doc archives on release.

## Approach

Single file `skills/nav-release/functions/release_validator.py`, same shape as the existing
`verify_*` functions (return `(ok, problems)` or `(passed, failed)`, printed by `main`):

- `verify_dispatcher(root, plugin)`: reuse `_OPSPEC_RE` for the registry names; dedupe
  (`compact_marker`, `graph_sync` appear more than once); for each name check path → git →
  import, stop at the first failure per op and report it.
- `verify_conformance(root, version)`: path check + `json.loads`; message copied from the
  Makefile rule so both say the same thing.
- `verify_hooks`: factor the env build into `_hook_envs(plugin_dir, tmp_home)`; create the
  symlink under `tempfile.TemporaryDirectory()`; pass `HOME=tmp_home` only in the unset env.
- Workflow: three steps after `--verify-mod`, each with a one-line comment naming the
  regression class it guards.

## Won't do

- No live Claude Code run in CI; conformance stays a results-file presence check (probes are
  live-driven, `tests/harness-conformance/run.md`).
- No change to `make conformance-check`; it remains the local form.
- No `__version__` in the dispatcher (TASK-64 Phase 2 recorded "still five files"; unchanged).
- No RC soak or rollback drill; those gates were waived with v7.0.0 and are not reopened.

## Verify

```bash
python3 skills/nav-release/functions/release_validator.py --verify-dispatcher
python3 skills/nav-release/functions/release_validator.py --verify-conformance 2.1.287
python3 skills/nav-release/functions/release_validator.py --verify-hooks
python3 -m pytest skills/nav-release/functions/test_release_validator.py -q
make test   # NAVIGATOR_MOD_OWNS unset inside a Claude Code session
```

## Refs

- `.agent/tasks/TASK-64-v7-release-gate.md` — Phase 1 spec and Gate Outcome
- `skills/nav-release/functions/release_validator.py` — `verify_hooks` (l.326),
  `verify_hook_paths` (l.407), `verify_mod` (l.446)
- `hooks/nav_hook_lib/registry.py` — `OpSpec` table; `hooks/nav_hook_lib/runtime.py`
  `OPS_PACKAGE = "ops"` (l.113)
- `Makefile` `conformance-check`; `tests/harness-conformance/results/cc-2.1.{205,241,287}.json`
- mem-036 (manifest env guard silent no-op), mem-037 (Stop stamping on conversational turns),
  mem-070 (missing artifact class)
