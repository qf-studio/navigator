# TASK-52: Docs & config drift cleanup

**Status**: ✅ Implemented — 2026-06-04
**Created**: 2026-06-02
**Work-package**: `wp9-docs-config`
**Phase**: 5 — Docs & config reconciliation
**Priority**: Low
**Effort**: M — Mostly trivial one-line string edits (README counts, CLAUDE.md version/token/command, manifest emails, DEVELOPMENT-README TASK-40 — each <5 min). Two items carry the bulk: the version-management SOP rewrite (SSOT map + ~90-line embedded bash audit script, must be re-grounded against the real manifests) and the config_migrator VERSION_CONFIGS extension (~11 new blocks copied verbatim from live .nav-config.json, plus a migration test to confirm idempotent additive behavior). Total well under a half-day; no exploration needed since all facts are now verified.
**Risk**: low — No blocking hook or runtime control flow touched. config_migrator change is additive (get_missing_configs only inserts keys absent from a user's config; version guard at line 166 prevents downgrades) — worst case a brand-new default block lands in an existing user's config, which is the intended behavior. session_start_hook addition to .nav-config.json is read defensively via .get with safe defaults, so it cannot break the SessionStart hook. The email change touches both published manifests (plugin.json + marketplace.json ship to every install) but is a metadata-only string with no functional effect. README/CLAUDE.md/SOP edits are docs-only.
**Depends on**: TASK-44 (wp2-version-tooling)
**Recommendation**: `fix+test`
**Source**: audit `wf_0dc1b9ce-7d8` → plan `wf_187896bb-5af`; roadmap in TASK-42

---

## Summary

Reconcile every stale version/skill-count/config reference and dead command across CLAUDE.md, README.md, DEVELOPMENT-README.md, the version-management SOP, the plugin manifests, and config_migrator so the docs match the v6.15.6 shipping reality and stop drifting each release.

## Findings Addressed

- README contradicts itself on skill count (27 line 98 vs 19 line 170); actual registered count is 29
- CLAUDE.md config sample pins version 5.5.0 (line 923) and omits all v6.x feature blocks (lines 921-938)
- config_migrator.py VERSION_CONFIGS stops at 5.6.0 (lines 57-80) so no v5.x/v6.x block (tom_features, loop_mode, knowledge_graph, multi_agent, the *_hook toggles) is ever seeded on upgrade
- session_start_hook block is absent from .agent/.nav-config.json; nav_session_start.py:255 reads it via .get with safe defaults (no runtime bug) but the documented opt-out is undiscoverable
- version-management SOP references a marketplace plugins[0].version field and README status/roadmap/footer lines (SOP lines 31-64, 108-120, 132-220) that do not exist in the current manifests/README
- Placeholder email aleks@example.com shipped in both .claude-plugin/plugin.json author.email (line 7) and .claude-plugin/marketplace.json owner.email (line 6)
- CLAUDE.md advertises legacy slash command /nav:update-doc (line 852) which has no backing skill
- CLAUDE.md overstates its own token cost as ~15k (line 879); actual file is 28,120 chars (~7k tokens)
- DEVELOPMENT-README lists TASK-40 as an active in-flight thread (line 150) but it is archived at .agent/tasks/archive/TASK-40-phase-3-hook-migration-v6.12.md
- DEVELOPMENT-README says 6-file bump checklist (lines 166, 233) while the linked version-management SOP says 9 locations; reconcile to one authoritative list

**Already resolved in v6.15.6** (excluded from this work):
- ~~v6.15.6 removed the deleted nav_commit_reminder.py PostToolUse(Bash) block from .claude-plugin/plugin.json (both the 'high' and duplicate 'critical' findings for plugin.json:139-148 are resolved; current line 139 onward is the nav_task_graph_sync group)~~
- ~~v6.15.6 synced DEVELOPMENT-README.md version references at lines 81, 182, 289 to v6.15.6 (the v6.15.3 'frozen' finding and the medium 'states v6.15.3' finding are resolved); the v6.15.4/v6.15.5 summaries also live in marketplace.json breaking_changes~~
- ~~v6.15.6 deleted the nav_commit_reminder.py row from the DEVELOPMENT-README hook table and corrected 'ten hooks' to 'nine' (DEVELOPMENT-README.md:198 finding resolved; token_monitor.py is still present and correctly marked '(legacy)')~~
- ~~README.md version badge at line 8 is already v6.15.6 (the SOP's phantom README status/roadmap/footer version lines never existed, so there is nothing else to bump in README for version)~~
- ~~CLAUDE.md footer is already synced to Navigator Version 6.15.6~~

## Implementation

All changes are doc/config string edits plus one small Python dict extension; no shipped runtime control flow changes. (1) README.md: change line 98 '✅ 27 skills' and line 170 '**19 skills**' to a single non-numeric phrasing ('full skill suite' / 'skills that auto-invoke') so the count cannot drift, since the manifest skills array (verified 29 entries, 1:1 with skills/*/ dirs) is the source of truth. (2) CLAUDE.md: bump the config sample version literal 5.5.0 to 6.15.6 at line 923 and add a one-line note that the sample is a minimal subset (the live .nav-config.json carries tom_features/loop_mode/knowledge_graph/multi_agent/*_hook blocks); fix the '~15k' token figure at line 879 to '~7k' (verified 28,120 chars); remove '/nav:update-doc' from line 852 (no nav-update-doc skill dir exists; grep hits are only plugin-slash-command example files) and map the intent to nav-task/nav-sop. (3) config_migrator.py: extend VERSION_CONFIGS (lines 57-80) with keys for 5.0.0 (tom_features), 5.1.0 (loop_mode), 6.0.0 (knowledge_graph), 6.1.0 (multi_agent), and the lifecycle-hook toggle blocks (compact_hook, task_graph_sync_hook, workflow_state_hook, profile_sync_hook, workflow_enforcer_hook, read_guard_hook, session_start_hook) keyed at their introduction versions, copying the exact default shapes from the live .agent/.nav-config.json so existing users get discoverable opt-out keys on upgrade — the existing get_missing_configs loop (lines 107-114) already only adds keys absent from config, so this is purely additive and idempotent. (4) .agent/.nav-config.json: add a session_start_hook block ({enabled:true, include_sections:[...], char_budget:...}) mirroring nav_session_start.py:256-263 defaults so the documented opt-out is present. (5) version-management.md: rewrite the Single Source of Truth + Version Reference Map (lines 29-64) and the embedded audit script (lines 132-220) to drop the dead plugins[0].version row (marketplace.json has only metadata.version + plugins[].name/source — verified) and the phantom README status/roadmap/footer lines, replacing with the real locations (marketplace.json metadata.version, plugin.json version, README badge line ~8, CLAUDE.md footer + config sample, .nav-config.json version, DEVELOPMENT-README footer); update SOP Created/Last-Updated dates. (6) Both manifests: replace aleks@example.com with the real maintainer contact (confirm address with maintainer before edit). (7) DEVELOPMENT-README.md: drop TASK-40 from the active list at line 150 (it is archived) and refresh the 'as of 2026-05-18' date; reconcile the '6-file bump checklist' (lines 166, 233) and the SOP to one authoritative file set — the DEVELOPMENT-README 6-file list is closer to reality, so update the SOP to match it.

### Files

| File | Change |
| --- | --- |
| `README.md` | Lines 98 + 170: replace '27 skills' and '19 skills' with a single non-numeric phrasing (manifest is SSOT for count) |
| `CLAUDE.md` | Line 923 sample version 5.5.0 -> 6.15.6 + minimal-subset note; line 879 '~15k' -> '~7k'; line 852 remove /nav:update-doc |
| `skills/nav-sync-claude/functions/config_migrator.py` | Extend VERSION_CONFIGS (57-80) with v5.0/5.1/6.0/6.1 feature blocks + all lifecycle-hook toggle blocks incl. session_start_hook, copying live config defaults |
| `.agent/.nav-config.json` | Add session_start_hook block mirroring nav_session_start.py defaults (enabled/include_sections/char_budget) |
| `.agent/sops/development/version-management.md` | Rewrite SSOT + Version Reference Map (29-64) and audit script (132-220): drop phantom plugins[0].version and README status/roadmap/footer lines; list the real 6 locations; refresh dates |
| `.claude-plugin/plugin.json` | Line 7 author.email: replace placeholder aleks@example.com with real maintainer contact |
| `.claude-plugin/marketplace.json` | Line 6 owner.email: replace placeholder aleks@example.com with real maintainer contact |
| `.agent/DEVELOPMENT-README.md` | Line 150: remove archived TASK-40 from active list + refresh 'as of' date; reconcile 6-file checklist wording (166, 233) with the rewritten SOP |

## Acceptance Criteria

- [x] grep -nE '27 skills|19 skills' README.md returns nothing; README no longer hardcodes a skill count
- [x] CLAUDE.md config sample shows "version": "6.15.6" and is labelled a minimal subset; the ~15k token figure is corrected to ~7k; /nav:update-doc no longer appears in CLAUDE.md
- [x] config_migrator VERSION_CONFIGS contains tom_features, loop_mode, knowledge_graph, multi_agent, and all *_hook toggle blocks (incl. session_start_hook) keyed by introduction version; a unit/regression test migrates a synthetic v5.3.0 config and asserts all v5.x/v6.x blocks are seeded and a second run is a no-op (idempotent)
- [x] .agent/.nav-config.json contains a session_start_hook block; python3 hooks/nav_session_start.py still emits its payload unchanged with the block present (smoke test)
- [x] version-management.md Version Reference Map lists only locations that exist (no plugins[0].version, no README status/roadmap/footer lines); the embedded audit script run against the repo at v6.15.6 exits 0 with zero ERRORS
- [x] neither .claude-plugin/plugin.json nor .claude-plugin/marketplace.json contains aleks@example.com (grep -r 'aleks@example.com' .claude-plugin returns nothing)
- [x] DEVELOPMENT-README.md active task list does not include TASK-40; the bump-checklist count is consistent between DEVELOPMENT-README and version-management.md
- [x] json.load succeeds on both manifests and .nav-config.json after edits (no JSON syntax breakage)

## Technical Decisions

- **Recommendation**: `fix+test`. No blocking hook or runtime control flow touched. config_migrator change is additive (get_missing_configs only inserts keys absent from a user's config; version guard at line 166 prevents downgrades) — worst case a brand-new default block lands in an existing user's config, which is the intended behavior. session_start_hook addition to .nav-config.json is read defensively via .get with safe defaults, so it cannot break the SessionStart hook. The email change touches both published manifests (plugin.json + marketplace.json ship to every install) but is a metadata-only string with no functional effect. README/CLAUDE.md/SOP edits are docs-only.

## Out of Scope

- Findings outside this work-package's listed scope (see TASK-42 roadmap for the full map).

## Refs

- TASK-42 — Audit Remediation Roadmap (umbrella)
- TASK-44 — dependency (`wp2-version-tooling`)

## Verify

```bash
# See Acceptance Criteria; run the relevant tests/validators before marking done.
```

## Done

- [x] All acceptance criteria checked
- [x] Tests pass in CI (once TASK-43 gate exists)
- [x] Committed + roadmap (TASK-42) status updated
