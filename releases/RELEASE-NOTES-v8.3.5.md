# Navigator v8.3.5 Release Notes

**Release Date**: 2026-10-08
**Type**: Patch — release-CI gates for the Python fallback runtime (TASK-99, carried from TASK-64 Phase 1)

## Added

- **`release_validator.py --verify-dispatcher`.** Every manifest hook command must route
  through `hooks/nav_dispatch.py`, and every op named by an `OpSpec` in
  `hooks/nav_hook_lib/registry.py` must have `hooks/ops/<name>.py` that exists, is tracked by
  git and imports cleanly. This is the v5.1.0 missing-skill incident generalized to ops:
  `--verify-mod` already checks the mod side; this checks the side that runs when the mod
  does not (older Claude Code, policy block, three crashes in a session).
- **`release_validator.py --verify-conformance [CC_VERSION]`.** A harness-conformance results
  file (`tests/harness-conformance/results/cc-<version>.json`) must exist and parse for the
  Claude Code version we ship against. Without an argument the version comes from
  `claude --version` (the `make conformance-check` form); release CI passes the pinned version
  so the runner never needs the binary.
- **Release CI runs both, plus the hook smoke test.** `release.yml` gains one `CC_MOD_VERSION`
  env (`2.1.287`) that pins the `validate-mod` install and the conformance gate, and three
  validate steps after `--verify-mod`: `--verify-dispatcher`, `--verify-conformance
  "$CC_MOD_VERSION"`, `--verify-hooks`.

## Changed

- **`--verify-hooks` is hermetic.** The set path binds `CLAUDE_PLUGIN_ROOT` to the repo under
  release instead of the newest cached install (the wrong target for a release gate). The
  unset path runs with `HOME` pointed at a tmp dir whose
  `.claude/plugins/marketplaces/navigator-marketplace` is a symlink to the repo, so the
  manifest fallback is what resolves, on a runner or a laptop without the real directory.
  `NAVIGATOR_MOD_OWNS` and `PILOT_EXECUTOR` are scrubbed from both runs: inside a Claude Code
  session the mod's ownership list made the Python dispatcher exit silently on every owned
  op, which reproduced the v6.14.0 silent-fail signature on three payload events
  (in-session baseline 20/26 → 26/26; plain shell 23/26 → 26/26).

Tests: `test_release_validator.py` +11 (`VerifyDispatcherTest` ×6 including the repo itself,
`VerifyConformanceTest` ×4, `HookEnvsTest`), 27 in the file; `make test` green.
Docs: nav-release SKILL.md Step 1.5 and functions list, release-workflow SOP, DEPLOYMENT.md.
Task doc: `.agent/tasks/archive/TASK-99-release-validator-dispatcher-conformance.md`.
