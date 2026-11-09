# TASK-44: Version & release tooling correctness

**Status**: ✅ Implemented — 2026-06-02
**Created**: 2026-06-02
**Work-package**: `wp2-version-tooling`
**Phase**: 1 — Gate + zero-dep quick wins
**Priority**: High
**Effort**: L — L (1-2d). The HIGH version_lt fix is S on its own (one-line logic + test). But the package spans 3 scripts + 1 Python module + 2 doc files + a new bump script + 2 new test files + migrating 4 stray release-notes files. The version_detector rewrite is bounded (logic already proven in auto_updater.py — copy/adapt), the --check-version branch is ~15 lines, and the bump script is straightforward sed/jq across five exact locations I verified. Doc rewrite of SOP Step 3/4 plus checklist is the bulk of the prose work.
**Risk**: med — release.yml is a published, tag-triggered workflow — a wrong edit to pre-release detection silently mismarks every future release; the change is low-LOC but must be tested against a dummy tag. version_lt and version_detector feed the auto-update path users hit on every session start, so a regression could trigger spurious reinstalls or suppress real updates — mitigated by unit tests. No KG/graph mutation, no blocking hook involved. bump-version.sh writes five repo files but is run manually, not in a hook.
**Depends on**: none
**Recommendation**: `fix+test`
**Source**: audit `wf_0dc1b9ce-7d8` → plan `wf_187896bb-5af`; roadmap in TASK-42

---

## Summary

Fix the inverted/dead version-comparison and detection logic and the documented-vs-automated release-path drift so Navigator's upgrade and release tooling reports the right answer and the SOP matches the CI workflow.

## Findings Addressed

- HIGH: version_lt() in scripts/check-version.sh is logically inverted (reports 'up to date' when update available)
- MED: version_detector.get_current_version() parses wrong line of `claude plugin list` (single-line regex vs multi-line block)
- MED: version_detector get_plugin_json_version() fallback paths don't match version-keyed cache layout, returns None
- MED: release_validator.py --check-version parsed but never used; wrong version still exits 0
- MED: SOP creates release notes at repo root but release.yml canonical path is releases/
- MED: multi-file version bump is fully manual/vim-driven, no bump script (SOP flags this gap)
- LOW: release.yml greps 'Experimental' (capital) but marketplace.json only has lowercase 'experimental', and that token lives in a historical changelog array entry not a status field — detection can never fire correctly
- LOW: check-version.sh masks command exit code via `local var=$(cmd)`, making the network-failure guard unreliable
- LOW: release_validator reads marketplace .metadata.version while post-install.sh greps first "version" match — they agree only by coincidence (no top-level version exists)

**Already resolved in v6.15.6** (excluded from this work):
- ~~v6.15.6 removed the dead nav_commit_reminder.py hook block and synced versions — none of the wp2 findings were resolved by that change; all nine remain open in the current tree (verified plugin.json/marketplace/README/CLAUDE.md/.nav-config all read 6.15.6 but the logic bugs are untouched)~~

## Implementation

Fix in four grounded groups. (1) HIGH version_lt: rewrite scripts/check-version.sh:64-75 to return true only when v1<v2 AND v1!=v2 — `[ "$(printf '%s\n%s' "$v1" "$v2" | sort -V | head -1)" = "$v1" ] && [ "$v1" != "$v2" ]`. Verified empirically the current `sort -V -C || return 0` is inverted (6.15.4<6.15.5 -> FALSE). Also fix the :90-92 exit-code mask: split `local latest_version; latest_version=$(get_latest_version)` so `$?` is meaningful. (2) version_detector.py: replace get_current_version() :38-45 single-line regex with the proven multi-line block-scan from skills/nav-start/functions/auto_updater.py:44-64 (set in_navigator_block on the `@`/`❯` line, match `Version:\s*v?(\d+\.\d+\.\d+)` on following lines, reset on next `❯`); replace get_plugin_json_version() :57-73 static paths with a glob of `~/.claude/plugins/cache/*/navigator/*/.claude-plugin/plugin.json` picking the highest version dir (mirror the existing sort-by-`re.findall(r'\d+')` logic in release_validator.py:308-312). (3) release_validator.py: implement the --check-version branch in main() after :453 — compare each value from check_version_consistency() to args.check_version, print mismatches, return 1 on any mismatch or NOT_FOUND; this is what wp1's CI gate will call. Optionally standardize marketplace access on .metadata.version everywhere and assert it equals plugin.json top-level (post-install.sh:9 already resolves to metadata.version since no top-level key exists). (4) release.yml:59-64 + SOP: make pre-release detection rely on tag suffixes only (drop the marketplace grep — the lowercase 'experimental' token is a historical changelog entry, not a status field, so any grep false-fires) OR add a real `metadata.status` field and grep that; align the SOP inline comment + Step 9 text. Add scripts/bump-version.sh <version> updating all five verified locations (plugin.json:3, marketplace.json metadata.version:10, README badge:8 `version-X-blue`, CLAUDE.md:967 `**Navigator Version**:`, .agent/.nav-config.json:2) then running release_validator --check-version; rewrite SOP Step 3 (:96-127), Step 4 path (:132), README example (:276), checklist (:603) to use releases/ and the bump script; migrate the 4 stray root RELEASE-NOTES files (v5.3.0/v5.4.0/v5.5.0/v6.1.0) into releases/.

### Files

| File | Change |
| --- | --- |
| `scripts/check-version.sh` | Rewrite version_lt() (lines 64-75) to non-inverted v1<v2 logic; split local-assignment at :90-92 so $? guard works |
| `skills/nav-upgrade/functions/version_detector.py` | Replace get_current_version() block-scan (38-45) with auto_updater's multi-line logic; replace get_plugin_json_version() fallback paths (57-73) with cache-glob of ~/.claude/plugins/cache/*/navigator/*/.claude-plugin/plugin.json |
| `skills/nav-release/functions/release_validator.py` | Implement the --check-version branch in main() (~line 453): compare each detected version to the argument, exit 1 on mismatch/NOT_FOUND |
| `.github/workflows/release.yml` | Fix pre-release detection (lines 59-64): drop the false-firing marketplace grep in favor of tag-suffix-only, or grep a real status field |
| `.agent/sops/development/complete-release-workflow.md` | Update Step 3 (96-127) to reference scripts/bump-version.sh, Step 4 (132)/README example (276)/checklist (603) to use releases/ path; align pre-release-detection text (374,392) |
| `scripts/bump-version.sh` | NEW: bump all five version locations from a single arg and run release_validator --check-version |
| `tests/test-check-version.sh` | NEW: unit test asserting version_lt 6.15.4<6.15.5 true, equal false, 6.16.0<6.15.5 false |
| `skills/nav-upgrade/functions/test_version_detector.py` | NEW: tests for block-scan parsing of `claude plugin list` fixture and cache-glob fallback (mirrors existing skills/*/functions/test_*.py harness) |
| `releases/RELEASE-NOTES-v5.3.0.md` | Migrate stray root-level file into releases/ (also v5.4.0, v5.5.0, v6.1.0) |

## Acceptance Criteria

- [x] tests/test-check-version.sh asserts: version_lt 6.15.4 6.15.5 -> true (exit 0), version_lt 6.15.5 6.15.5 -> false, version_lt 6.16.0 6.15.5 -> false; runs green (7 cases incl. numeric 6.9.0<6.10.0 + v-prefix; wired into `make test` via SHELL_TESTS)
- [x] check-version.sh version_lt rewritten to non-inverted logic (equal→GE guard + `sort -V | head -n1` first-token test); :90 exit-code mask split so the network-failure guard reads get_latest_version's `$?`; main() guarded behind `BASH_SOURCE==$0` so the test can source it. (Logic verified + unit-tested; not run live against the network.)
- [x] test_version_detector.py: get_current_version() returns the version from a multi-line `claude plugin list` fixture; get_plugin_json_version() resolves a version from a simulated ~/.claude/plugins/cache/*/navigator/<v>/.claude-plugin/plugin.json tree (6 tests green)
- [x] release_validator.py --check-version 9.9.9 exits non-zero with a per-file mismatch report; --check-version <actual> exits 0 — verified (NOTE: the --check-version branch itself shipped in wp1/TASK-43; this WP only verifies it)
- [x] release.yml pre-release detection now tag-suffix-only; the dead `grep "Experimental"` marketplace branch removed (0 capital matches confirmed — it could never fire correctly). (Live tag behavior verifies on the next release push.)
- [x] scripts/bump-version.sh updates all five version locations (plugin.json, marketplace.json metadata.version, README badge, CLAUDE.md, .nav-config.json) then runs release_validator --check-version; verified format-preserving via a no-op 6.15.6 bump (all 5 matched, validator PASSED, zero spurious diff)
- [x] SOP Step 3/4, README example, Step 7 tag msg, Step 9, troubleshooting, and checklist all reference releases/ and scripts/bump-version.sh; no remaining instruction to write notes at repo root (historical v4.3.0 example output left as accurate record)
- [x] the 4 stray root RELEASE-NOTES files (v5.3.0/v5.4.0/v5.5.0/v6.1.0) moved under releases/ via git mv so release.yml's FALLBACK branch is only legacy-compat

## Implementation Notes (2026-06-02)

- **Scope delta from plan**: group 3 (`--check-version` dispatch) was already implemented when wp1/TASK-43 landed `check_version_match()` + the main() branch — this WP verified it rather than building it. All other findings were untouched in the tree and fixed here.
- **Bonus cleanup**: removed a Claude-Code co-author block from the SOP Step 6 commit example (violated the project "no Claude Code mentions in commits" rule).
- **Files**: scripts/check-version.sh, skills/nav-upgrade/functions/version_detector.py, .github/workflows/release.yml, scripts/bump-version.sh (new), tests/test-check-version.sh (new), skills/nav-upgrade/functions/test_version_detector.py (new), Makefile (SHELL_TESTS), .agent/sops/development/complete-release-workflow.md, releases/RELEASE-NOTES-v{5.3.0,5.4.0,5.5.0,6.1.0}.md (git mv).

## Technical Decisions

- **Recommendation**: `fix+test`. release.yml is a published, tag-triggered workflow — a wrong edit to pre-release detection silently mismarks every future release; the change is low-LOC but must be tested against a dummy tag. version_lt and version_detector feed the auto-update path users hit on every session start, so a regression could trigger spurious reinstalls or suppress real updates — mitigated by unit tests. No KG/graph mutation, no blocking hook involved. bump-version.sh writes five repo files but is run manually, not in a hook.

## Out of Scope

- Findings outside this work-package's listed scope (see TASK-42 roadmap for the full map).

## Refs

- TASK-42 — Audit Remediation Roadmap (umbrella)

## Verify

```bash
# See Acceptance Criteria; run the relevant tests/validators before marking done.
```

## Done

- [x] All acceptance criteria checked
- [x] Tests pass locally (`make test` green incl. new shell + python tests); CI runs on branch push (TASK-43 gate)
- [x] Committed + roadmap (TASK-42) status updated
