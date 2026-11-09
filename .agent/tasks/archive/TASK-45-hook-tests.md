# TASK-45: Test coverage for hooks & destructive/blocking paths

**Status**: ✅ Implemented — 2026-06-03
**Created**: 2026-06-02
**Work-package**: `wp4-hook-tests`
**Phase**: 2 — Test coverage
**Priority**: High
**Effort**: L — ~1-2 days. 11 new test files. The two blocking-hook suites and the compact round-trip carry real complexity: workflow_enforcer needs a tmp-project fixture with a crafted .nav-workflow-state.json and exercises the select.select stdin path; nav_read_guard needs multi-invocation counter-state setup; the compact round-trip threads stdin JSON across pre→post→session_start with a synthetic JSONL transcript. The scorer/graph/profile direct-import tests are quick (mirror the existing test_complexity_detector.py pattern, ~S each). The two corruption-guard edits are trivial (~3 lines each). Renames are mechanical but require grepping SKILL.md for references. No new dependencies — all stdlib unittest.
**Risk**: med — The two corruption-guard edits touch live load paths for the knowledge graph and ToM profile, but they only ADD a fallback on an already-failing parse (current behavior is an uncaught exception), so they cannot regress a healthy file. The renamed files (test_generator.py, test_mcp_connection.py) are referenced by frontend-component and product-design SKILL.md and possibly by sibling imports — must grep and update all references or the skills break at runtime; this is the main risk surface. Tests themselves are additive (no production behavior change). The blocking hooks (nav_read_guard exit 2, workflow_enforcer exit 2) are exercised only via subprocess against tmp projects, never the real .agent/ — no risk to the running session. No published-manifest change.
**Depends on**: TASK-43 (wp1-ci-gate)
**Recommendation**: `fix+test`
**Source**: audit `wf_0dc1b9ce-7d8` → plan `wf_187896bb-5af`; roadmap in TASK-42

---

## Summary

Add a stdlib-unittest suite covering all 9 hooks (especially the two exit-2 blockers and the PreCompact/PostCompact marker round-trip), the untested workflow_detector/complexity_scorer scorers, and corruption-guarded graph/profile loaders, and stop the two mis-named non-test files from poisoning test discovery.

## Findings Addressed

- All 9 hooks (2,026 lines) have ZERO tests including two exit-2 blockers (nav_read_guard, workflow_enforcer)
- workflow_detector.calculate_complexity / detect_loop_trigger / detect_workflow untested while near-duplicate complexity_detector is heavily tested
- graph_manager.load_graph uses bare json.load with no corruption guard and has no tests
- profile_manager.load_profile uses bare json.load with no corruption guard and has no tests
- auto_updater.py destructive uninstall/reinstall path + version comparison + plugin-list parsing untested
- complexity_scorer.py (separate from tested complexity_detector) untested
- Two files named like tests are not tests (frontend-component/functions/test_generator.py, product-design/functions/test_mcp_connection.py) — poison test discovery
- nav_pre_compact / nav_post_compact marker round-trip has no test despite being the compact-survival mechanism

## Implementation

All tests use stdlib `unittest` (pytest is NOT installed; Python 3.14 in env, existing suites like skills/nav-workflow/functions/test_complexity_detector.py run via `python -m unittest`). Two test styles, both already proven in-repo: (1) direct import of the module-under-test via `sys.path.insert(0, str(Path(__file__).parent))`, (2) subprocess + piped stdin JSON for hooks.

HOOKS (new files hooks/test_*.py):
- test_workflow_enforcer.py: invoke hooks/workflow_enforcer.py via subprocess with `input=json.dumps({"prompt": ...})`, `cwd=<tmp project>`. Assert (a) plain prompt → exit 0, prints WORKFLOW CHECK block; (b) loop-trigger prompt with NO state file → exit 0 (soft warn, Phase-1 safety per lines 13/152-174); (c) loop-trigger prompt + `.agent/.nav-workflow-state.json` with `last_turn.check_shown=false` + default strict_block → exit 2 and stderr contains `<nav-workflow-block>` sentinel (lines 146-203); (d) same but `strict_block=false` in .nav-config.json → exit 0; (e) `PILOT_EXECUTOR=1` env → exit 0 immediately (line 126); (f) strip_block_messages: a prompt already containing the sentinel block does not re-trigger (mem-034 regression, line 57-69).
- test_nav_read_guard.py: subprocess with stdin `{"tool_name":"Read","tool_input":{"file_path":...},"cwd":...,"session_id":...}`. Assert (a) non-Read tool → exit 0; (b) path outside .agent/ → exit 0; (c) allowlisted file (DEVELOPMENT-README.md) never counts; (d) drive counter to warn_threshold then escalate_threshold via repeated invocations sharing one session_id+counter file → exit 2 at escalate with `<nav-read-guard-block>` (lines 241-243); (e) `strict_block=false` → exit 0 even past threshold (line 244); (f) session_id change resets counter (lines 133-136); (g) no `.agent/` dir → silent exit 0 (line 202).
- test_compact_roundtrip.py (covers nav_pre_compact + nav_post_compact + surfacing): build a tmp project with `.agent/`, write a synthetic JSONL transcript file. Run nav_pre_compact.py with stdin `{"cwd":..,"transcript_path":..,"session_id":..,"trigger":"manual"}`; assert a `before-compact-manual-*.md` marker AND `.context-markers/.active` are written (lines 300-309). Then run nav_post_compact.py with stdin `{"cwd":..,"compact_summary":"SUMMARY-SENTINEL"}`; assert the `## Compact Summary (Claude Code)` section is appended to the same marker (lines 97-103). Then call nav_session_start.py `_section_active_marker` (import or subprocess) and assert it surfaces the marker name (nav_session_start.py:71-88). Also assert PostCompact with missing `.active` is a no-op exit 0 (lines 80-83).
- test_hooks_smoke.py: parametrized smoke over the remaining hooks (nav_session_start, nav_profile_sync, nav_task_graph_sync, nav_workflow_state, token_monitor): feed minimal valid stdin JSON + a tmp `.agent/` cwd and assert exit 0 and valid/empty stdout (these are non-blocking; goal is import+no-crash + empty-JSON contract). Also feed each hook empty stdin and malformed JSON and assert it still exits 0 (every hook has a `json.JSONDecodeError` guard).

SCORERS (direct-import tests, mirror test_complexity_detector.py):
- skills/nav-start/functions/test_workflow_detector.py: detect_loop_trigger phrase matching (lines 100-113) incl. case-insensitivity and no-match; calculate_complexity thresholds (high 0.3 / medium 0.2 / low 0.1 / multi-file 0.2, cap 1.0, lines 116-155); detect_workflow dict shape the enforcer reads — keys loop_mode/loop_trigger/task_mode/complexity/recommended_mode (lines 158-187, consumed by workflow_enforcer.py:139-156).
- skills/nav-start/functions/test_complexity_scorer.py: calculate_score category boundaries trivial/simple/moderate/substantial/complex (lines 170-179), factor breakdown keys, task_mode>=0.5 (lines 181-187).

CORRUPTION GUARDS (code change + tests):
- skills/nav-graph/functions/graph_manager.py:16-22 — wrap `json.load` in try/except `json.JSONDecodeError` returning `create_empty_graph()`.
- skills/nav-profile/functions/profile_manager.py:15-21 — wrap `json.load` in try/except returning `{}` (matches existing missing-file contract).
- test_graph_manager.py: load on missing/corrupt/valid file; add_node/remove_node concept_index consistency (lines 81-124); add_edge dedup (lines 138-145); save_graph→load_graph round-trip via tempfile.
- test_profile_manager.py: load missing/corrupt; update_preference, add_correction max-20 cap (lines 88-90), add_goal upsert (lines 104-113).

AUTO_UPDATER (mocked, no real plugin ops):
- skills/nav-start/functions/test_auto_updater.py: unit-test pure functions with no mocking — compare_versions newer/older/equal/uneven-length (lines 89-110); get_current_version parsing by monkeypatching `subprocess.run` to return representative `claude plugin list` stdout (lines 44-64). For reinstall_plugin (lines 177-225), monkeypatch subprocess.run to assert a failed uninstall returns `success:false` WITHOUT calling install (verifies no inconsistent state) and that a failed reinstall is reported. Do NOT execute real `claude plugin` commands.

DISCOVERY HYGIENE (the two mis-named files):
- Rename skills/frontend-component/functions/test_generator.py → file_generator.py (0 test functions; argparse generator) and update its references in skills/frontend-component/SKILL.md.
- Rename skills/product-design/functions/test_mcp_connection.py → check_mcp_connection.py (module-level `from figma_mcp_client import` crashes collection) and update product-design/SKILL.md references.
- Add a discovery convention note (tests are `python -m unittest discover -s <dir> -p 'test_*.py'`); the rename removes the two false positives.

NOTE on running in CI: these are stdlib-unittest files runnable today with `python -m unittest`, but a CI job that auto-discovers and runs them is wp1-ci-gate's deliverable — hence dependsOn wp1.

### Files

| File | Change |
| --- | --- |
| `/Users/aleks.petrov/Projects/startups/navigator/hooks/test_workflow_enforcer.py` | NEW: subprocess tests for exit 0 vs exit 2 gate, sentinel stderr, PILOT_EXECUTOR bypass, strip_block_messages regression |
| `/Users/aleks.petrov/Projects/startups/navigator/hooks/test_nav_read_guard.py` | NEW: subprocess tests for counter increment, warn/escalate thresholds, exit 2 block, strict_block=false, session reset, allowlist |
| `/Users/aleks.petrov/Projects/startups/navigator/hooks/test_compact_roundtrip.py` | NEW: PreCompact writes marker+.active, PostCompact appends summary, nav_session_start surfaces it, missing-.active no-op |
| `/Users/aleks.petrov/Projects/startups/navigator/hooks/test_hooks_smoke.py` | NEW: import+no-crash + empty/malformed-stdin exit-0 smoke for nav_session_start, nav_profile_sync, nav_task_graph_sync, nav_workflow_state, token_monitor |
| `/Users/aleks.petrov/Projects/startups/navigator/skills/nav-start/functions/test_workflow_detector.py` | NEW: detect_loop_trigger, calculate_complexity thresholds, detect_workflow dict-shape contract |
| `/Users/aleks.petrov/Projects/startups/navigator/skills/nav-start/functions/test_complexity_scorer.py` | NEW: calculate_score category boundaries and factor breakdown |
| `/Users/aleks.petrov/Projects/startups/navigator/skills/nav-start/functions/test_auto_updater.py` | NEW: compare_versions, get_current_version parsing, reinstall failed-uninstall-no-install safety (subprocess mocked) |
| `/Users/aleks.petrov/Projects/startups/navigator/skills/nav-graph/functions/graph_manager.py` | EDIT load_graph (lines 16-22): guard json.load with try/except JSONDecodeError → create_empty_graph() |
| `/Users/aleks.petrov/Projects/startups/navigator/skills/nav-graph/functions/test_graph_manager.py` | NEW: load missing/corrupt/valid, add/remove_node concept-index, edge dedup, save/load round-trip |
| `/Users/aleks.petrov/Projects/startups/navigator/skills/nav-profile/functions/profile_manager.py` | EDIT load_profile (lines 15-21): guard json.load with try/except JSONDecodeError → {} |
| `/Users/aleks.petrov/Projects/startups/navigator/skills/nav-profile/functions/test_profile_manager.py` | NEW: load missing/corrupt, update_preference, add_correction 20-cap, add_goal upsert |
| `/Users/aleks.petrov/Projects/startups/navigator/skills/frontend-component/functions/test_generator.py` | RENAME → file_generator.py (not a test; poisons discovery); update SKILL.md refs |
| `/Users/aleks.petrov/Projects/startups/navigator/skills/product-design/functions/test_mcp_connection.py` | RENAME → check_mcp_connection.py (not a test; module-level figma import crashes collection); update SKILL.md refs |
| `/Users/aleks.petrov/Projects/startups/navigator/skills/frontend-component/SKILL.md` | EDIT: update references from test_generator.py to file_generator.py |
| `/Users/aleks.petrov/Projects/startups/navigator/skills/product-design/SKILL.md` | EDIT: update references from test_mcp_connection.py to check_mcp_connection.py |

## Acceptance Criteria

- [x] `python -m unittest discover -s hooks -p 'test_*.py'` passes — 38 tests across the 4 new hook test files (green via `make test`, which now includes `hooks`).
- [x] test_workflow_enforcer asserts exit 2 + `<nav-workflow-block>` sentinel only when loop trigger AND `last_turn.check_shown=false` AND strict_block=true; exit 0 in all other branches incl. PILOT_EXECUTOR set, missing state file, and a prompt already wrapped in the sentinel (mem-034 regression). State file confirmed `.agent/.nav-workflow-state.json`; block gated on `check_shown is False` (identity).
- [x] test_nav_read_guard drives the `.agent/.nav-read-counter.json` per-turn counter and asserts exit 2 + `<nav-read-guard-block>`, plus exit 0 when strict_block=false and on session_id change, allowlist exemption, and no-`.agent/` silent exit 0. (Deviation: the hook blocks AT `count >= escalate_threshold` (5th read), not strictly past it — asserted the real behavior.)
- [x] test_compact_roundtrip: PreCompact writes `before-compact-manual-*.md` + `.active`, PostCompact appends `## Compact Summary (Claude Code)` containing the injected sentinel, nav_session_start `_section_active_marker` surfaces the marker name (`## Active Marker:`), and PostCompact with no `.active` is a no-op exit 0.
- [x] graph_manager.load_graph → create_empty_graph() and profile_manager.load_profile → {} on a corrupt JSON file (try/except json.JSONDecodeError added), with tests asserting no raise.
- [x] test_workflow_detector + test_complexity_scorer cover loop-trigger matching (case-insensitive), complexity thresholds/cap, and all five complexity_scorer categories. (Confirmed real weights: workflow_detector high/med/low = 0.3/0.2/0.1 +0.2 multi-file cap 1.0; complexity_scorer factors action≤0.4/scope≤0.3/files≤0.2/planning≤0.2; task_mode flips at ≥0.5.)
- [x] test_auto_updater covers compare_versions (current-relative: -1/0/+1, uneven lengths), get_current_version parsing of multi-line `claude plugin list` (mocked subprocess), and reinstall_plugin returning success:false on failed uninstall WITHOUT invoking install (real flow is uninstall→add→install; verified call_count==1, no install argv). Zero real plugin operations.
- [x] frontend-component/functions/test_generator.py → `file_generator.py` and product-design/functions/test_mcp_connection.py → `check_mcp_connection.py` (git mv); all refs updated (frontend SKILL.md ×4; product-design INSTALL.md/setup.sh/README.md — the actual ref sites, not SKILL.md).
- [x] Whole-repo `python -m unittest discover -s . -p 'test_*.py'` no longer hits an ImportError/SystemExit from the two former mis-named files (figma import / argparse generator).

## Implementation Notes (2026-06-03)

- **9 new test files, 108 new tests**, all stdlib `unittest`. Hook tests are subprocess-against-tmp-project (never the real `.agent/`); scorer/graph/profile/updater are direct-import. Written by 4 parallel agents, each verifying against real source and running green; full `make test` green afterward.
- **Makefile**: added `hooks`, `skills/nav-start/functions`, `skills/nav-graph/functions`, `skills/nav-profile/functions` to `TEST_DIRS` so the new suites run in CI; refreshed the now-obsolete exclusion comment (the rename removed the discovery poison).
- **Deviations from the audit spec** (asserted real behavior): read-guard blocks AT threshold not past; `compare_versions` is current-relative; `reinstall_plugin` is a 3-step flow; `add_goal` upserts by name preserving `context`; `add_correction` keeps the last 20. The "11 test files" effort estimate was an overcount — the Files table specifies 9 new test files + 2 guard edits.
- product-design refs lived in INSTALL.md/setup.sh/README.md (not SKILL.md as the audit assumed) — all updated.

## Technical Decisions

- **Recommendation**: `fix+test`. The two corruption-guard edits touch live load paths for the knowledge graph and ToM profile, but they only ADD a fallback on an already-failing parse (current behavior is an uncaught exception), so they cannot regress a healthy file. The renamed files (test_generator.py, test_mcp_connection.py) are referenced by frontend-component and product-design SKILL.md and possibly by sibling imports — must grep and update all references or the skills break at runtime; this is the main risk surface. Tests themselves are additive (no production behavior change). The blocking hooks (nav_read_guard exit 2, workflow_enforcer exit 2) are exercised only via subprocess against tmp projects, never the real .agent/ — no risk to the running session. No published-manifest change.

## Out of Scope

- Findings outside this work-package's listed scope (see TASK-42 roadmap for the full map).

## Refs

- TASK-42 — Audit Remediation Roadmap (umbrella)
- TASK-43 — dependency (`wp1-ci-gate`)

## Verify

```bash
# See Acceptance Criteria; run the relevant tests/validators before marking done.
```

## Done

- [x] All acceptance criteria checked
- [x] Tests pass (`make test` green — 9 new files, 108 tests; whole-repo discovery clean); CI runs on branch push
- [x] Committed + roadmap (TASK-42) status updated
