# TASK-42: Audit Remediation Roadmap

**Status**: ✅ Complete — wp1–wp11 shipped; wp12 security re-sweep done 2026-07-09 (no exploitable findings; see wp12 section)
**Created**: 2026-06-02
**Priority**: High
**Source**: 10-dimension audit `wf_0dc1b9ce-7d8` (86 verified findings) → remediation plan `wf_187896bb-5af`
**Shipped already**: critical hook-manifest regression fixed in **v6.15.6**; all remediation work-packages wp1–wp11 (TASK-43…51 + wp10/TASK-25) shipped to `main`. wp12 security re-sweep completed 2026-07-09 (see wp12 section at end) — roadmap closed.

---

## Summary

Remediation runs in four dependency-respecting waves anchored on a CI gate that makes every subsequent fix verifiable. The keystone is wp1 (CI test + pre-publish validation gate): until it exists, the 233 unit tests never run automatically, the Makefile test target is a sham, and the exact v6.15.5 dead-hook/version-drift regression can recur — so every other fix would ship unverified. We front-load wp1 plus the no-dependency quick wins (wp8 skill-template trimming, wp2 version-tooling correctness) that derisk later doc and release work. Test coverage (wp4) lands immediately after the gate so it both runs in CI and protects the higher-risk hook/graph/detection fixes (wp5, wp6, wp7) that depend on it. The two heavy, independent script tracks (wp10 multi-Claude, wp11 misc Python) run in parallel where capacity allows since they touch neither the gate nor each other. Docs/config reconciliation (wp9) lands last because its SOP rewrite must reflect wp2's bump-script and release-path decisions.

## Keystone

Build wp1 (CI test job + pre-publish validation gate) first. Today release.yml is the only publish path, it runs zero tests, and it has no version-consistency / tag-vs-manifest / hook-path check — exactly the gap that let the v6.15.5 dead-hook + version-drift regression ship before the v6.15.6 hotfix. The Makefile `test` target is verified a no-op (it only exec's status_generator.py), so the 233 passing unit tests never execute automatically. Until wp1 wires per-directory unittest discovery (the 6 genuine dirs summing to 233, excluding the two mis-named non-test files) and adds release_validator --verify-hook-paths + tag==manifest assertions to a `validate` job that the `release` job needs:, every downstream fix (wp4-wp11) ships unverified and the regression class stays open. Land the test job non-blocking on push/PR first, then gate releases on the validate job once it is confirmed green against the clean v6.15.6 tree.

## Work-Package Index

| WP | Task | Phase | Effort | Risk | Deps | Rec |
| --- | --- | --- | --- | --- | --- | --- |
| `wp1-ci-gate` — CI test + pre-publish validation gate | TASK-43 | — | M | med | — | `fix+test` |
| `wp2-version-tooling` — Version & release tooling correctness | TASK-44 | — | L | med | — | `fix+test` |
| `wp8-skill-templates` — Skill template/reference integrity | TASK-50 | — | M | low | — | `fix-now` |
| `wp4-hook-tests` — Test coverage for hooks & destructive/blocking paths | TASK-45 | — | L | med | TASK-43 | `fix+test` |
| `wp5-hook-safety` — Hook correctness & safety fixes (non-path) | TASK-46 | — | M | med | TASK-45 | `fix+test` |
| `wp6-kg-integrity` — Knowledge-graph data integrity + dormant maintenance wiring | TASK-47 | — | L | med | TASK-45 | `split` |
| `wp7-detection` — Detection precision: token-boundary matching + consolidate complexity impls | TASK-48 | — | M | med | TASK-45 | `fix+test` |
| `wp3-plugin-paths` — Plugin-relative path resolution (skills + hooks work outside the source repo) | TASK-49 | — | L | med | — | `fix+test` |
| `wp10-multiclaude` — Multi-Claude reliability → **DEPRECATED** (2026-06-04): superseded by native Workflows; scripts tombstoned, not repaired | TASK-25 | — | L | med | — | ~~`fix+test`~~ → `deprecate` |
| `wp11-python-misc` — Misc Python correctness fixes | TASK-51 | — | M | low | — | `fix+test` |
| `wp9-docs-config` — Docs & config drift cleanup | TASK-52 | — | M | low | TASK-44 | `fix+test` |

## Phases

### Phase 1: Phase 1 — Establish the gate + batch zero-dependency quick wins

**Work-packages**: TASK-43, TASK-50, TASK-44

Stand up the CI test runner and pre-publish validation gate (keystone) so all later work is verifiable, and concurrently land the independent low-risk wins. wp8 is doc-only skill-template trimming (no hooks, no manifest, no graph) and wp2 fixes the inverted/dead version logic and adds the bump script — both have no dependsOn and wp2 is a prerequisite for wp9's SOP rewrite. Running them now removes the false generator/template references and the inverted version_lt before any release flows through the new gate. Note ownership: wp8 owns only the nav-stats v3.5.0 string while wp3 (Phase 3) owns the nav-stats cwd-path fix in the same file — coordinate to avoid a collision.

**Exit criterion**: test.yml runs the 233 unit tests on push/PR and the release.yml validate job (--check-all, --verify-hook-paths, --verify-tag, tag==manifest) passes green against v6.15.6 with `release` set to needs: validate; `make test` runs the same 233 tests; every functions/templates/examples path in backend-endpoint/frontend-component SKILL.md resolves to a real file; version_lt reports 6.15.4<6.15.5 true and scripts/bump-version.sh updates all five version locations with release_validator --check-version exiting 0.

### Phase 2: Phase 2 — Test coverage for the surfaces about to be edited

**Work-packages**: TASK-45

wp4 depends on wp1 (its new hook/scorer/graph tests need the CI per-dir runner to execute automatically and to be protected from regression). It must land before the riskier behavioral fixes in Phase 3 because it characterizes the two exit-2 blocking hooks, the compact round-trip, the untested scorers, and adds corruption guards to the graph/profile loaders — establishing the safety net those fixes lean on. It also performs the discovery hygiene (renaming the two mis-named non-test files) that keeps whole-repo discovery clean for everything after.

**Exit criterion**: `python -m unittest discover -s hooks -p test_*.py` passes with the 4 new hook test files; graph_manager.load_graph and profile_manager.load_profile return empty structures (not raise) on corrupt JSON with tests asserting it; the two former mis-named test files no longer match the discovery glob and all SKILL.md/import references are updated; whole-repo discovery collects without ImportError.

### Phase 3: Phase 3 — Behavioral fixes guarded by Phase 2 tests

**Work-packages**: TASK-46, TASK-47, TASK-48

wp5 (hook correctness/safety), wp6 (knowledge-graph integrity + maintenance wiring), and wp7 (detection precision) all declare dependsOn wp4 so their changes land against existing coverage. These touch the highest-consequence runtime surfaces: the published plugin.json manifest (wp5 token_monitor retirement), the SessionStart blocking-budget hook (wp5 auto-update decouple), git-tracked graph data (wp6 dedup/dangling repair), and the exit-2 enforcer's input (wp7 detection boundaries). Running them after wp4 means the blocking-hook and graph behavior is regression-checked. wp6 is recommended split (data-repair track A vs decay-wiring track B) and can be staged within the phase. Path-overlap note: wp5 explicitly defers the nav_session_start CLAUDE_PROJECT_ROOT→DIR one-liner to wp3 (Phase 4) to avoid a double edit on _project_root.

**Exit criterion**: plugin.json contains no token_monitor reference and still parses with nav_task_graph_sync+nav_profile_sync intact; graph_maintenance --action health reports 0 duplicate edges, 0 dangling edges, 0 out-of-range confidences (852→682 edges, 6 dangling removed, mem-026=0.9); detect_workflow('document everything we discussed') returns loop_mode=False while 'run until done' still triggers; all Phase 2 hook tests still pass.

### Phase 4: Phase 4 — Independent script tracks + path resolution (parallelizable)

**Work-packages**: TASK-49, TASK-25, TASK-51

wp3 (plugin-relative path resolution), wp10 (multi-Claude reliability), and wp11 (misc Python) carry no dependsOn edges and touch disjoint surfaces, so they run in parallel for throughput. wp3 is placed here so it can absorb the deferred nav_session_start CLAUDE_PROJECT_ROOT→DIR change from wp5 and the nav-stats cwd-path fix that wp8 left to it, after the hook tests (wp4) exist to confirm the workflow_enforcer block/no-block invariant survives the stdin refactor — its acceptance criteria explicitly require wp4's tests to still pass. wp10 and wp11 are self-contained (scripts/ and skill helpers respectively) and need only their own stub/unit tests.

**Exit criterion**: No bare `python3 skills/` or `bash scripts/` invocations remain in any SKILL.md and helpers resolve from a non-repo cwd with CLAUDE_PLUGIN_DIR unset; nav_session_start uses CLAUDE_PROJECT_DIR; multi-Claude wait_for_file honors its timeout arg, retry re-invokes stubbed claude, APPROVED gate is anchored, git add . is scoped, and shellcheck passes; all six misc Python fixes have passing test_*.py and existing hook tests from wp4 still pass.

### Phase 5: Phase 5 — Docs & config reconciliation

**Work-packages**: TASK-52

wp9 declares dependsOn wp2 because its version-management SOP rewrite, the config_migrator VERSION_CONFIGS extension, and the bump-checklist reconciliation must reflect wp2's bump-version.sh, the releases/ canonical path, and the corrected version-tooling reality. It lands last so it can also reflect the shipped state of every prior phase (eight hooks after wp5's token_monitor retirement, the real skill set, the corrected manifests) and stop the docs drifting against decisions still in flight.

**Exit criterion**: README hardcodes no skill count; CLAUDE.md sample shows 6.15.6 and ~7k tokens with /nav:update-doc removed; config_migrator seeds all v5.x/v6.x feature + lifecycle-hook blocks idempotently (regression test passes); version-management.md lists only real locations and its embedded audit script exits 0 at v6.15.6; neither manifest contains aleks@example.com; both manifests and .nav-config.json still json.load cleanly.

## Critical Path

`TASK-43 → TASK-45 → TASK-47`

## Quick Wins (batch immediately)

- wp8-skill-templates
- wp2-version-tooling (HIGH version_lt one-line inversion fix + test)
- wp11-python-misc (task_id_generator regex one-liner, release_validator _strip_dot_slash helper, profile_manager add_goal name guard)
- wp5-hook-safety (token_monitor retirement + plugin.json/README ~30min, highest-value single edit; workflow_enforcer ImportError stderr one-liner)
- wp7-detection (delete dead complexity_scorer.py; code_analyzer [a-z]+skip-set 'm' fix)

## Sequencing Notes & File-Overlap Conflicts

Dependency edges respected exactly as declared: wp4→wp1; wp5/wp6/wp7→wp4; wp9→wp2; wp1/wp2/wp3/wp8/wp10/wp11 have no deps. Longest chain is wp1→wp4→{wp5|wp6|wp7} at depth 3 (criticalPath picks wp6 as the deepest/heaviest tail since it is L-effort, split-recommended, and mutates git-tracked data). FILE-OVERLAP CONFLICTS to coordinate: (1) hooks/nav_session_start.py — wp5 (auto-update decouple, _section_auto_update) and wp3 (CLAUDE_PROJECT_ROOT→DIR at line 60) both edit it; wp5 explicitly cedes the line-60 one-liner to wp3, so do the wp5 edits first (Phase 3) then wp3's single-token fix (Phase 4) to avoid a merge collision on _project_root. wp6's OPTIONAL decay-wiring also targets this hook — keep it strictly read-only and do it within wp6 only after wp5's _section_auto_update rewrite settles. (2) skills/nav-stats/SKILL.md — wp8 owns ONLY the 'v3.5.0+' string (line 48), wp3 owns the cwd-relative scripts/session-stats.sh path (lines 46/53/72); these are different lines, batch into one editing pass if wp3 and wp8 run close together. (3) skills/frontend-component/SKILL.md — wp4 renames test_generator.py→file_generator.py (updates refs) and wp8/wp3 also edit this file's template/path references; sequence wp4's rename before wp3/wp8 touch the same file or grep-update jointly. (4) release_validator.py — wp1 adds --verify-hook-paths + tag-vs-version, wp2 implements the --check-version dispatch branch, wp11 adds _strip_dot_slash; all three edit the same file across phases — land wp1's additions first (Phase 1), wp2's --check-version same phase (they are interdependent: wp1's gate CALLS wp2's --check-version), and wp11's lstrip helper can ride either. wp2 and wp1 are effectively co-required in Phase 1 since wp1's tag==manifest assertion depends on wp2 wiring --check-version. DEFER candidates: wp6 track B (decay/staleness wiring) may be deferred to a follow-up if mutation-on-session-start risk is judged too high this pass — the spec's fallback is to mark decay/staleness experimental in config+SKILL.md rather than wire it; wp10's full single-impl complexity-scorer merge is explicitly out of scope (wp7 deletes the dead complexity_scorer.py but defers merging workflow_detector.calculate_complexity into complexity_detector to a separate risk-managed WP because it would change enforcer block thresholds). wp10 and wp11 can start any time (no deps) but are slotted into Phase 4 to keep the critical path uncluttered; pull them earlier if parallel capacity exists.

## Open Gap

- **Security re-sweep (wp12) not completed** — the audit's security dimension and its plan agent both failed to return structured output. Injection / auto-update supply-chain / read-guard-bypass review is still owed before this roadmap is considered complete.

## Refs

- Per-WP tasks: TASK-43 (ci-gate), TASK-44 (version-tooling), TASK-45 (hook-tests), TASK-46 (hook-safety), TASK-47 (kg-integrity), TASK-48 (detection), TASK-49 (plugin-paths), TASK-50 (skill-templates), TASK-51 (python-misc), TASK-52 (docs-config)
- wp10 (multi-Claude) → **TASK-25** (existing)
- Audit backlog memory: `project_audit_backlog_2026_06`

---

## wp12 Security Re-sweep — completed 2026-07-09

Inline review (subagent runs were blocked by model cyber-safeguards; reviewed directly).
Scope per Open Gap: injection, auto-update supply chain, read-guard bypass.
Files reviewed: `hooks/nav_session_start.py`, `hooks/nav_brief.py`, `hooks/nav_read_guard.py`,
`skills/nav-start/functions/auto_updater.py`, `scripts/check-version.sh`, plus a repo-wide
scan for `shell=True` / `eval` / `exec` / `os.system` (zero hits outside a docstring).

### Dimension 1: Context-injection surfaces — PASS (trust-boundary notes)

- **No command injection.** Every subprocess call uses argv lists; nav_brief concepts are
  regex-restricted (`[a-z][a-z\-_]{3,}`) and passed as a single argv element; config-derived
  paths never touch a shell string.
- **Anti-recursion mitigations present and deliberate**: nav_brief strips echoed
  `<nav-workflow-block>` sentinels before scoring; nav_read_guard's block message
  deliberately omits the triggering file_path (commented rationale in source).
- **I-1 (low, accepted)**: SessionStart injects `.agent/` file content (README, marker,
  profile, memories) into model context. A hostile repo could plant instruction text there —
  but that is the same trust domain as CLAUDE.md itself; Claude Code's model treats project
  files as trusted. No remote or cross-project content is ever injected. No action.
- **I-2 (low)**: PreCompact markers embed `git status` output; hostile *filenames* in the
  working tree flow into injected context. Same local trust domain. No action.

### Dimension 2: Auto-update supply chain — PASS with one documented inherent risk

- **U-1 (medium, inherent)**: No cryptographic verification of releases (no signing/checksum).
  Trust anchor = GitHub repo over HTTPS + Claude Code's plugin pipeline. A GitHub account/repo
  compromise means code execution on auto-updating users at next session start (hooks run
  automatically). This is the standard marketplace trust model; mitigations that exist today:
  `auto_update.enabled: false` and manual review before `nav-upgrade`. Release signing is
  possible future work, not a defect.
- **U-2 (good)**: tag↔plugin.json validation (5fe5ddd, mirrored in auto_updater) blocks
  malformed/phantom releases; post-update the installed version is re-verified against the
  target and mismatches are added to `ignored_releases`.
- **U-3 (accepted)**: validation fetch fails OPEN on network error — documented, and it is an
  integrity check, not an authenticity check, so fail-open does not weaken the (absent)
  authenticity guarantee.
- **U-4 (good)**: SessionStart path is read-only (`--check-drift`); the mutating update runs
  only via the skill flow with fixed identifiers (`navigator@navigator-marketplace`) — no
  user- or network-controlled data reaches a command line. Remote version strings are parsed
  with strict `\d+\.\d+\.\d+` regexes.
- **U-5 (low, availability)**: reinstall fallback is uninstall→add→install; a failure after
  uninstall leaves the plugin absent until next session. Not a security issue.

### Dimension 3: Read-guard bypass — PASS (by design; keep framing honest)

- **R-1 (by design)**: nav_read_guard is a token-budget guard, not a security boundary.
  Known bypasses — Bash `cat`, Grep/Glob, agents, config threshold raise, counter-file
  delete — are all acceptable because its purpose is anti-pattern prevention; its own block
  message advertises the escape hatches. Docs and source already frame it exactly this way;
  keep it that way (never cite it as an access control).
- **R-2 (minor)**: symlinks inside `.agent/` pointing outside escape counting
  (`Path.resolve()` semantics). Irrelevant to security, negligible to token accounting.

### Verdict

**No exploitable findings.** One inherent-risk documentation item (U-1) — now recorded here.
The security dimension that failed to return structured output in the original audit
(`wf_0dc1b9ce-7d8`) is hereby re-run and closed. TASK-42 remediation roadmap is complete.
