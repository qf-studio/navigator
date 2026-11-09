# TASK-43: CI test + pre-publish validation gate

**Status**: ✅ Implemented (CI run pending branch push) — 2026-06-02
**Created**: 2026-06-02
**Work-package**: `wp1-ci-gate`
**Phase**: 1 — Gate + zero-dep quick wins
**Priority**: High
**Effort**: M — ~half-day. The test-discovery loop and YAML are mechanical (~half done already by knowing the 6 dirs and 233 count). The two validator additions are small, self-contained Python functions in an existing well-structured file (~40-60 lines + a couple of unit tests for the new functions). Main time sink is iterating on YAML in CI (tag-trigger job is awkward to test locally; can dry-run the validator commands locally but the workflow wiring needs a throwaway tag push or `act` to fully verify).
**Risk**: med — No hook code or graph data is touched, so runtime user impact is nil. The real risk is the gate itself: an over-strict or buggy assertion could block ALL future releases (release.yml is the only publish path, fires on `v*` tag push). Mitigations: keep the test job on push/PR (non-blocking to release) initially, add the validate job as `needs:` only after the validator commands are confirmed green against the current clean v6.15.6 tree (verified locally: --check-all passed=True, --verify-hooks 18/18, all 5 versions=6.15.6). The new --verify-hook-paths must parse the `${CLAUDE_PLUGIN_DIR:-...}/hooks/<name>.py` command form (verified shape in plugin.json) — a sloppy regex could false-positive and wedge releases.
**Depends on**: none
**Recommendation**: `fix+test`
**Source**: audit `wf_0dc1b9ce-7d8` → plan `wf_187896bb-5af`; roadmap in TASK-42

---

## Summary

Add a GitHub Actions test job (runs all 233 existing unit tests) plus a pre-publish validation gate that blocks the release if any plugin.json hook command path is missing from hooks/, any of the 5 version files disagree, or the pushed tag version does not equal the manifest version — the exact regression that shipped in v6.15.5 and was hotfixed in v6.15.6.

## Findings Addressed

- release.yml publishes with zero pre-publish validation: no version-consistency check, no tag-vs-plugin.json match, no release_validator/test run (.github/workflows/release.yml:11-108)
- CI (release.yml) runs NO tests — the 233 passing unit tests never execute automatically (.github/workflows/release.yml:1-125)

**Already resolved in v6.15.6** (excluded from this work):
- ~~The CRITICAL finding (deleted nav_commit_reminder.py still registered in plugin.json PostToolUse:Bash) was removed and version refs synced in v6.15.6 (plugin.json now registers 9 hooks, all resolving to existing files; DEVELOPMENT-README corrected). This WP adds the automated gate so the class of regression cannot recur, but the specific dead-hook block is already gone — verified: release_validator --verify-hooks reports 18/18 and all 5 version files read 6.15.6.~~

## Implementation

Two pieces, both grounded in verified code.

(1) TEST JOB. The Makefile `test` target (Makefile:16-22) is a sham — it only `exec`s status_generator.py and never touches the 13 test_*.py files; `unittest discover -s skills` from repo root finds 0 tests because every test file does `sys.path.insert(0, str(Path(__file__).parent))` and imports its sibling module by bare name (e.g. test_exit_gate.py:11 `from exit_gate import ...`). They must be discovered per-directory. Verified: running `python3 -m unittest discover -p "test_*.py"` from each of the 6 genuine unittest dirs sums to EXACTLY 233 tests, all OK: nav-upgrade/functions (7), nav-sync-claude/functions (7), nav-simplify/scripts (20), nav-workflow/functions (101 = 3 files), nav-init/functions (11), nav-loop/functions (87 = 4 files). Two files named test_*.py are NOT unittest and must be excluded: skills/frontend-component/functions/test_generator.py (an argparse CLI generator) and skills/product-design/functions/test_mcp_connection.py (a live Figma MCP probe needing a venv). Implementation: add .github/workflows/test.yml (on push + pull_request) that loops over the 6 dirs (or globs functions/scripts dirs minus the venv and the two non-test files) and runs `python3 -m unittest discover -p "test_*.py"` in each via a subshell, failing on first non-OK. Provide a `make test` rewrite mirroring the same loop so local and CI agree.

(2) PRE-PUBLISH GATE. Add a `validate` job to release.yml that runs BEFORE the existing `release` job (make `release` need: `validate`). It runs the existing skills/nav-release/functions/release_validator.py plus two NEW assertions that currently do not exist:
  (a) HOOK-PATH RESOLUTION (the keystone). verify_hooks() (release_validator.py:316-394) smoke-tests hook commands at runtime but does NOT statically assert the file exists, and crucially mis-classifies the v6.15.6 signature: a missing-file PostToolUse/Bash hook exits 2 with stderr, but is_silent_failure (line 365-370) is only True for events in HOOK_EMITS_PAYLOAD={SessionStart,PreCompact,PostCompact}; PostToolUse is silent-by-design, so it lands in `passed` (verified by reproducing the classifier — returns PASS). Add a new function (and `--verify-hook-paths` flag) that, for every hook command in plugin.json, extracts the `hooks/<name>.py` basename from the command string and asserts (root / "hooks" / name).exists(), failing with the offending command. This is literally the follow-up the v6.15.6 marketplace.json breaking_changes note prescribes.
  (b) TAG-VS-MANIFEST. release_validator already has check_version_consistency() (line 128-178) reading all 5 files (plugin.json, marketplace.json metadata.version, CLAUDE.md, README.md badge, .nav-config.json) and --verify-tag (line 431-448) checks only SKILL.md presence in the tag — neither compares the pushed tag to the manifest. Note --check-version is declared as an arg (line 400) but has NO dispatch branch in main(); wire it (or add `--assert-tag-version`) to compare the GITHUB_REF-stripped version against every value from check_version_consistency() and fail on any mismatch. The gate shell strips `refs/tags/v` exactly as release.yml:25 already does.

The validate job: checkout (fetch-depth: 0, needed for --verify-tag git ls-tree), then run `release_validator.py --check-all`, `--verify-hook-paths`, `--verify-tag "$TAG"`, and the tag==version assertion; any non-zero exit fails the workflow before any `gh release create` runs.

### Files

| File | Change |
| --- | --- |
| `.github/workflows/test.yml` | NEW: on push/PR, loop the 6 genuine unittest dirs and run `python3 -m unittest discover -p test_*.py` in each, excluding the two non-unittest test_*.py files and the product-design venv |
| `.github/workflows/release.yml` | Add a `validate` job (checkout fetch-depth 0) running release_validator --check-all/--verify-hook-paths/--verify-tag plus tag==manifest version assertion; make existing `release` job `needs: validate` |
| `skills/nav-release/functions/release_validator.py` | Add verify_hook_paths() + `--verify-hook-paths` flag (static hooks/<name>.py existence per plugin.json command); wire the declared-but-undispatched --check-version (or add --assert-tag-version) to compare a tag version against all check_version_consistency() values |
| `Makefile` | Rewrite the sham `test` target (currently only exec's one module) to run the same per-dir unittest discovery loop as test.yml so local == CI |

## Acceptance Criteria

- [ ] test.yml runs on push and PR and executes exactly the 233 genuine unit tests (6 dirs), excluding skills/frontend-component/functions/test_generator.py and skills/product-design/functions/test_mcp_connection.py; the job fails if any test fails
- [ ] `make test` runs the same 233 tests locally and exits non-zero on failure (no longer a no-op exec of status_generator.py)
- [ ] release_validator.py --verify-hook-paths exits 0 on current main and exits non-zero with the offending command when a plugin.json hook command references a hooks/<name>.py that does not exist (regression-test: re-add a nav_commit_reminder.py PostToolUse:Bash block to a temp manifest -> non-zero)
- [ ] release_validator.py tag-vs-version mode exits 0 when the tag (e.g. v6.15.6) matches all 5 version files and non-zero when any of plugin.json/marketplace.json/CLAUDE.md/README.md/.nav-config.json disagrees with the tag
- [ ] release.yml `release` job has `needs: validate`; the validate job runs --check-all, --verify-hook-paths, --verify-tag, and the tag==version assertion, and no `gh release create` step can run if any fails
- [ ] New validator functions have unit tests under skills/nav-release/functions/test_release_validator.py discoverable by the same per-dir runner (raising the suite past 233)

## Technical Decisions

- **Recommendation**: `fix+test`. No hook code or graph data is touched, so runtime user impact is nil. The real risk is the gate itself: an over-strict or buggy assertion could block ALL future releases (release.yml is the only publish path, fires on `v*` tag push). Mitigations: keep the test job on push/PR (non-blocking to release) initially, add the validate job as `needs:` only after the validator commands are confirmed green against the current clean v6.15.6 tree (verified locally: --check-all passed=True, --verify-hooks 18/18, all 5 versions=6.15.6). The new --verify-hook-paths must parse the `${CLAUDE_PLUGIN_DIR:-...}/hooks/<name>.py` command form (verified shape in plugin.json) — a sloppy regex could false-positive and wedge releases.

## Out of Scope

- Findings outside this work-package's listed scope (see TASK-42 roadmap for the full map).

## Refs

- TASK-42 — Audit Remediation Roadmap (umbrella)

## Verify

```bash
# See Acceptance Criteria; run the relevant tests/validators before marking done.
```

## Done

- [ ] All acceptance criteria checked
- [ ] Tests pass in CI (once TASK-43 gate exists)
- [ ] Committed + roadmap (TASK-42) status updated
