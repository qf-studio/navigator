# TASK-50: Skill template/reference integrity

**Status**: ✅ Implemented — 2026-06-03
**Created**: 2026-06-02
**Work-package**: `wp8-skill-templates`
**Phase**: 1 — Gate + zero-dep quick wins
**Priority**: High
**Effort**: M — Mostly markdown surgery in two ~640-line SKILL.md files plus a one-line nav-stats edit and six empty-dir removals. No code logic changes. Bulk of the time is careful section deletion/renumbering and re-reading the edited SKILL.md to confirm no dangling cross-references remain. The version-convention decision adds a small docs touch. Comfortably under a half-day; not S because there are two large files with interdependent step/function/template/example lists that must stay self-consistent.
**Risk**: low — No blocking hook, no published JSON manifest, no knowledge-graph mutation. Changes are doc-only (SKILL.md text, frontmatter version strings) plus deletion of confirmed-empty directories. Worst case is over-trimming a step that the model could otherwise have run; mitigated by keeping the inline-fallback phrasing. The only published surface is skill frontmatter (loaded by Claude Code at session start) — version bumps are cosmetic and safe. Removing empty dirs cannot break the test skills since their SKILL.md never references those paths.
**Depends on**: none
**Recommendation**: `fix-now`
**Source**: audit `wf_0dc1b9ce-7d8` → plan `wf_187896bb-5af`; roadmap in TASK-42

---

## Summary

Make backend-endpoint and frontend-component SKILL.md reference only files that actually ship, fix the express-route placeholder list, normalize stale skill versions, and remove the false "v3.5.0+" string and empty test-skill scaffolding so the model never invokes nonexistent generators/templates.

## Findings Addressed

- backend-endpoint references missing functions/templates/examples (error_handler_generator.py, test_generator.py, error-handler/fastify/graphql-resolver/validation-zod templates, graphql-resolver.ts example)
- frontend-component references missing component-with-hooks-template.tsx, component-container-template.tsx, and UserProfile.tsx example
- express-route-template.ts documented placeholders do not match actual template placeholders
- stale/inconsistent skill frontmatter versions (backend-endpoint/frontend-component at 1.0.0 despite Next.js + graph additions; mixed 1.0.0/2.0.0/1.1.0 across skills)
- nav-stats hard-codes 'requires Navigator v3.5.0+' string in a v6.15.6 plugin (own the string only; the false-trigger path fix belongs to wp3)
- backend-test and frontend-test ship empty examples/functions/templates directories

**Already resolved in v6.15.6** (excluded from this work):
- ~~None of these findings were resolved by v6.15.6 — commit e5aff9f only removed the deleted nav_commit_reminder.py block from plugin.json/DEVELOPMENT-README and synced versions; it did not touch any skills/* file in this work-package (verified via git log on skills/backend-endpoint, frontend-component, backend-test, frontend-test, nav-stats/SKILL.md).~~

## Implementation

Documentation-trimming over file-creation, matching the maintainers' prior approach in commit 1d63f86 ("repair generators" by editing existing files, not expanding the matrix).

backend-endpoint/SKILL.md: (1) Delete Step 4 "Generate Error Handling Middleware" (lines 215-224) and Step 5 "Generate Test File" (lines 233-244) OR rewrite them to "the model writes this inline" — both `functions/error_handler_generator.py` and `functions/test_generator.py` are confirmed absent on disk. Renumber Steps 6-8 accordingly (or keep numbering, just drop the bash invocations of missing scripts). (2) Remove function entries #4 (error_handler_generator.py, lines 441-452) and #5 (test_generator.py, lines 456-476) from the Predefined Functions section; only route_validator.py, endpoint_generator.py, validation_generator.py ship. (3) In the Templates section, delete the `fastify-route-template.ts` (520-522), `graphql-resolver-template.ts` (524-526), and `validation-zod-template.ts` (528-530) blocks — none exist; note Zod is generated inline by validation_generator.py (which builds the schema via ZOD_TYPE_MAP, no template). Keep express + the two nextjs template blocks (those files exist). The endpoint-test-template.spec.ts file DOES exist so its block (532-539) can stay, but since no generator drives it, reframe it as "reference test shape." (4) In Examples (lines 547-549) remove the `graphql-resolver.ts` bullet — only users-get.ts and users-post.ts exist. (5) Fix express-route-template placeholder list (486-491): the actual template uses ${ROUTE_PATH}, ${HTTP_METHOD}, ${RESOURCE_NAME}, ${RESOURCE_NAME_LOWER}, ${HTTP_METHOD_LOWER}, ${MIDDLEWARE_BLOCK}; replace the listed ${VALIDATION_MIDDLEWARE}/${AUTH_MIDDLEWARE} (the express template does not use them — it uses ${MIDDLEWARE_BLOCK} which endpoint_generator.py builds from auth+validation flags) with the three missing ones. (Note: ${VALIDATION_MIDDLEWARE}/${AUTH_MIDDLEWARE} DO exist in endpoint_generator.py's substitution dict, lines 68-69, but are not present in the express template — so the doc should list what the template actually contains.)

frontend-component/SKILL.md: (1) In Step 3 (lines 164-172) remove the "Component with hooks" and "Container component" template references — `component-with-hooks-template.tsx` and `component-container-template.tsx` are absent; only component-simple-template.tsx + the four nextjs-* templates exist. Either drop with-hooks/container from the Step 1 type menu (lines 61-63) too, or keep them as "uses simple template + model fills hooks." (2) Remove the Templates blocks for component-with-hooks-template.tsx (488-494) and component-container-template.tsx (496-503). (3) Examples (line 530): remove the `UserProfile.tsx - Container component` bullet — only Button.tsx and SearchBar.tsx exist on disk.

Version normalization: bump backend-endpoint and frontend-component frontmatter `version:` from 1.0.0 (they have Next.js + knowledge-graph additions, so should be >= 2.0.0 to match backend-test/frontend-test/database-migration which are already 2.0.0). Decide a single convention — recommend per-skill semver bumped on material SKILL.md change; document it once in DEVELOPMENT-README or a CONTRIBUTING note. Do not attempt to retro-version all 29 skills; just correct the two that are demonstrably understated.

nav-stats/SKILL.md:48 — change the string "This feature requires Navigator v3.5.0+" to a version-neutral message (e.g. "Session stats script missing — reinstall Navigator"). The actual false-trigger is the cwd-relative `scripts/session-stats.sh` check (line 46); scripts/session-stats.sh exists, so the branch only fires on a path-resolution miss. That path fix is wp3's nav-stats cwd-path item — own only the string here.

backend-test / frontend-test: `git rm` the empty examples/, functions/, templates/ directories (confirmed empty; SKILL.md v2.0.0 never references files in them and explicitly relies on inline templates + the model). Alternatively add a .gitkeep with a one-line README explaining they are intentionally model-driven, but removal is cleaner and matches the SKILL.md "When NOT to Use" framing.

### Files

| File | Change |
| --- | --- |
| `/Users/aleks.petrov/Projects/startups/navigator/skills/backend-endpoint/SKILL.md` | Remove Steps 4-5 + function entries #4-#5 (missing error_handler_generator.py/test_generator.py); drop fastify/graphql-resolver/validation-zod template blocks and graphql-resolver.ts example; fix express-route placeholder list to ${RESOURCE_NAME_LOWER}/${HTTP_METHOD_LOWER}/${MIDDLEWARE_BLOCK}; bump version to 2.0.0 |
| `/Users/aleks.petrov/Projects/startups/navigator/skills/frontend-component/SKILL.md` | Remove with-hooks/container template references (Step 3 + Templates section) and UserProfile.tsx example; reconcile Step 1 type menu; bump version to 2.0.0 |
| `/Users/aleks.petrov/Projects/startups/navigator/skills/nav-stats/SKILL.md` | Line 48: replace stale 'requires Navigator v3.5.0+' string with version-neutral message |
| `/Users/aleks.petrov/Projects/startups/navigator/skills/backend-test/examples` | Remove empty directory (git rm) — unused, SKILL.md is model-driven |
| `/Users/aleks.petrov/Projects/startups/navigator/skills/backend-test/functions` | Remove empty directory (git rm) |
| `/Users/aleks.petrov/Projects/startups/navigator/skills/backend-test/templates` | Remove empty directory (git rm) |
| `/Users/aleks.petrov/Projects/startups/navigator/skills/frontend-test/examples` | Remove empty directory (git rm) |
| `/Users/aleks.petrov/Projects/startups/navigator/skills/frontend-test/functions` | Remove empty directory (git rm) |
| `/Users/aleks.petrov/Projects/startups/navigator/skills/frontend-test/templates` | Remove empty directory (git rm) |
| `/Users/aleks.petrov/Projects/startups/navigator/skills/frontend-component/functions/__pycache__/test_generator.cpython-314.pyc` | Remove stray committed pyc (cleanup, optional) and add functions/__pycache__ to .gitignore if not already ignored |

## Acceptance Criteria

- [x] Every functions/templates/examples path referenced in backend-endpoint/SKILL.md and frontend-component/SKILL.md resolves to a file that exists on disk (verified via a grep+stat script — 21 refs, all resolve).
- [x] express-route-template.ts placeholder list in SKILL.md lists exactly the placeholders present in templates/express-route-template.ts (${ROUTE_PATH}, ${HTTP_METHOD}, ${HTTP_METHOD_LOWER}, ${RESOURCE_NAME}, ${RESOURCE_NAME_LOWER}, ${MIDDLEWARE_BLOCK}); ${VALIDATION_MIDDLEWARE}/${AUTH_MIDDLEWARE} removed (set-equal check passed).
- [x] backend-endpoint and frontend-component frontmatter `version:` bumped 1.0.0 → 2.0.0; versioning convention stated in new root `CONTRIBUTING.md` (per-skill semver, independent of plugin version).
- [x] grep for 'v3.5.0' returns nothing in skills/nav-stats/SKILL.md (string replaced with version-neutral "reinstall/update Navigator" message; owns only the string — the cwd-path check at line 46 stays for wp3).
- [x] skills/backend-test and skills/frontend-test contain only SKILL.md; empty dirs removed. (NOTE: they were untracked filesystem scaffold — git only tracked SKILL.md — so they never shipped; `rmdir` is local cleanup, no git delta.)
- [x] No stray .pyc tracked — already clean: `__pycache__/` is gitignored (.gitignore:64) and `git ls-files` shows zero tracked pyc. No action needed.
- [x] Sanity: trimmed SKILL.md never directs the agent to an absent `python3 functions/<file>.py` (error_handler_generator/test_generator invocations in backend-endpoint replaced with inline-write guidance).

## Implementation Notes (2026-06-03)

- **Two findings were already clean**: the stray `.pyc` (already gitignored + untracked) and the "shipped empty dirs" (untracked scaffold, never in git). Verified rather than fixed; `rmdir` done locally for tidiness.
- **Approach**: doc-trimming + inline-fallback phrasing (per the low-risk recommendation), not file-creation. Steps 4–5 of backend-endpoint and the with-hooks/container paths of frontend-component now instruct inline authoring instead of invoking absent generators/templates.
- **Files**: skills/backend-endpoint/SKILL.md, skills/frontend-component/SKILL.md, skills/nav-stats/SKILL.md, CONTRIBUTING.md (new). Frontmatter is the only published surface touched.

## Technical Decisions

- **Recommendation**: `fix-now`. No blocking hook, no published JSON manifest, no knowledge-graph mutation. Changes are doc-only (SKILL.md text, frontmatter version strings) plus deletion of confirmed-empty directories. Worst case is over-trimming a step that the model could otherwise have run; mitigated by keeping the inline-fallback phrasing. The only published surface is skill frontmatter (loaded by Claude Code at session start) — version bumps are cosmetic and safe. Removing empty dirs cannot break the test skills since their SKILL.md never references those paths.

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
- [x] Tests pass (`make test` green — no code changed; doc-only WP)
- [x] Committed + roadmap (TASK-42) status updated
