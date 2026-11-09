# TASK-48: Detection precision: token-boundary matching + consolidate complexity impls

**Status**: ✅ Implemented — 2026-06-03
**Created**: 2026-06-02
**Work-package**: `wp7-detection`
**Phase**: 3 — Behavioral fixes (guarded)
**Priority**: Medium
**Effort**: M — ~half-day. The three edits are small and mechanical (regex swap, char-class fix, file delete). Bulk of the time is writing the new workflow_detector test suite from scratch (currently untested, and it gates a blocking hook) plus re-running test_complexity_detector.py (33 tests) and the enforcer smoke path to confirm the contract and exit-code behavior are unchanged. Not S because workflow_detector feeds a user-facing blocking hook and deserves real test coverage before/after.
**Risk**: med — workflow_detector.detect_workflow is imported by the exit(2) blocking enforcer hook (hooks/workflow_enforcer.py:50) registered in the published plugin.json manifest. Removing 'everything' REDUCES false blocks (the safe direction), but tightening complexity word boundaries could lower some borderline scores below the 0.5 task_mode threshold — verify representative prompts still classify correctly. Must preserve the exact dict keys detect_workflow returns or the hook's fallback stub diverges. Deleting complexity_scorer.py is low-risk (no importers). No knowledge-graph mutation involved. Manifest itself is not edited.
**Depends on**: TASK-45 (wp4-hook-tests)
**Recommendation**: `fix+test`
**Source**: audit `wf_0dc1b9ce-7d8` → plan `wf_187896bb-5af`; roadmap in TASK-42

---

## Summary

Eliminate substring/loop-trigger false positives that route innocuous prompts into LOOP/TASK mode (and the exit(2) enforcer block), and consolidate three divergent complexity scorers onto the single tested implementation.

## Findings Addressed

- complexity_scorer.py substring matching inflates complexity (skills/nav-start/functions/complexity_scorer.py:114-117)
- workflow_detector.py bare 'everything' loop trigger + substring matching fires on innocuous mentions and feeds the exit(2) blocking enforcer (skills/nav-start/functions/workflow_detector.py:32-49,109-111)
- analyze_unclear_names regex [a-hln-z] wrongly excludes 'm' in addition to i/j/k (skills/nav-simplify/scripts/code_analyzer.py:191-192)
- three divergent complexity implementations with no shared logic (complexity_scorer.calculate_score, workflow_detector.calculate_complexity, complexity_detector.detect_complexity)

**Already resolved in v6.15.6** (excluded from this work):
- ~~v6.15.6 removed the dead nav_commit_reminder.py PostToolUse(Bash) hook from plugin.json and synced DEVELOPMENT-README to nine hooks — unrelated to detection precision; none of this WP's four findings were touched by it~~

## Implementation

Verified ground truth before scoping: (1) complexity_scorer.py has ZERO importers anywhere (grep `from complexity_scorer`/`import complexity_scorer` = empty; only its own docstring at lines 9-11 references it) and no test file — it is dead code. (2) The only live path through a BLOCKING hook is hooks/workflow_enforcer.py line 50 `from workflow_detector import detect_workflow`, registered as UserPromptSubmit in .claude-plugin/plugin.json line 110. (3) complexity_detector.py (nav-workflow) already uses `re.search(r'\b...\b')` word boundaries throughout and has 33 passing tests in test_complexity_detector.py exercising detect_signals/calculate_complexity/detect_complexity. (4) Reproduced the false positive live: `detect_workflow("Please document everything we discussed")` returns loop_mode=True, trigger='everything', mode=LOOP — which feeds workflow_enforcer's exit(2) branch. (5) Confirmed `[a-hln-z]` excludes i,j,k AND m (a-h, l, n-z skips m) via direct regex test.

Work, smallest-blast-radius first:
- code_analyzer.py:192 — replace single_letter_pattern char class with capture-any-single-letter `\b(const|let|var)\s+([a-z])\s*=` and add an explicit skip set `{"i","j","k"}` in the analyze_unclear_names loop (lines 194-203) so 'm' (and any non-loop single letter) is flagged again. Mirrors the audit rec. test_roi_scoring.py only uses synthetic `{"type":"unclear_naming"}` dicts (lines 30,32,138), so no existing test breaks; add a focused unit test.
- workflow_detector.py — (a) LOOP_TRIGGERS (lines 32-49): drop bare "everything" and "all of it"; keep multi-word phrases ("complete everything", "do all", "run until done", etc.). (b) detect_loop_trigger (lines 109-111): match each phrase on token boundaries — compile `re.compile(r'\b' + re.escape(phrase) + r'\b')` (handles internal apostrophes/spaces fine) instead of `phrase in message_lower`. (c) calculate_complexity (lines 128-149): replace `indicator in message_lower` substring checks with `re.search(r'\b'+re.escape(indicator)+r'\b', message_lower)` so "add" no longer matches "address", "modify" no longer matches "modifying" mid-word, etc. Preserve the exact return contract `(score, matched)` and the dict shape detect_workflow returns (loop_mode, loop_trigger, task_mode, complexity, recommended_mode) — the enforcer hook and its fallback depend on it.
- Consolidation: delete complexity_scorer.py (dead, no importers, no tests) rather than fix it — removes one of the three divergent impls outright. Do NOT attempt to merge workflow_detector.calculate_complexity into complexity_detector.detect_complexity in this WP: they have incompatible scoring contracts (additive-from-0 with per-indicator weights vs base-0.5 ± signed adjustments) and the enforcer's loop-trigger detection has no analog in complexity_detector. Consolidating leaves two impls (the tested complexity_detector for nav-workflow's skill-deferral path, and the boundary-hardened workflow_detector for the enforcer hook); document in the task doc why a full single-impl merge is deferred (would change enforcer block thresholds — needs its own risk-managed WP).
- Add a test file skills/nav-start/functions/test_workflow_detector.py (currently NONE) asserting: bare "everything"/"all of it" no longer trigger LOOP; legitimate phrases still trigger; substring non-matches ("address" ≠ "add", "modifying" ≠ "modify") score lower; detect_workflow contract keys preserved.

### Files

| File | Change |
| --- | --- |
| `skills/nav-start/functions/workflow_detector.py` | Remove bare 'everything'/'all of it' from LOOP_TRIGGERS; switch detect_loop_trigger and calculate_complexity to compiled \b...\b word-boundary regex; preserve return contract |
| `skills/nav-start/functions/complexity_scorer.py` | Delete — dead code (zero importers, no tests); removes one of three divergent complexity impls |
| `skills/nav-simplify/scripts/code_analyzer.py` | Fix analyze_unclear_names regex to [a-z] and skip {i,j,k} programmatically so 'm' is flagged again (line 192 + loop 194-203) |
| `skills/nav-start/functions/test_workflow_detector.py` | New test file: assert no false-positive loop triggers, word-boundary complexity matching, and preserved detect_workflow output keys |
| `skills/nav-simplify/scripts/test_roi_scoring.py` | Add a unit test for analyze_unclear_names asserting 'm' flagged and i/j/k skipped (verify path; existing synthetic-dict tests unaffected) |

## Acceptance Criteria

- [x] detect_workflow('Please document everything we discussed') returns loop_mode=False, recommended_mode != 'LOOP'
- [x] detect_workflow('run until done: fix the bug') still returns loop_mode=True with trigger 'run until done'
- [x] calculate_complexity('fix the address field') does not match 'add' (no 'low:add' in matched); calculate_complexity('add a feature') does match 'add'
- [x] complexity_scorer.py is deleted and `grep -rn complexity_scorer` returns no live references (its wp4 test test_complexity_scorer.py deleted alongside — see note)
- [x] analyze_unclear_names flags 'const m = 1' and does NOT flag const i/j/k; existing test_roi_scoring.py tests still pass (now 24, +4 added)
- [x] new skills/nav-start/functions/test_workflow_detector.py passes and covers loop-trigger boundaries + complexity word boundaries + detect_workflow contract keys (43 tests; 30 pre-existing from wp4 + 13 added here)
- [x] skills/nav-workflow/functions/test_complexity_detector.py still passes unchanged (101 tests — doc's "33" was stale)
- [x] workflow_enforcer.py end-to-end smoke: innocuous 'everything' prompt exits 0 (no block)

## Implementation Notes (deviations from plan)

The plan was written 2026-06-02, before wp4/TASK-45 (hook tests) landed 2026-06-03.
Two of its ground-truth assumptions were stale by the time this WP ran:

1. **complexity_scorer.py "has no test file"** — false. wp4 added
   `test_complexity_scorer.py` (8 tests) covering exactly the module this WP
   deletes. Deleting the module orphaned the test, so **both** were removed via
   `git rm`. Still satisfies "no live references" (the test was the only
   remaining reference) and the consolidation goal (one fewer divergent impl).
2. **test_workflow_detector.py "currently NONE"** — false. wp4 already created
   it (30 tests). The TASK-48 cases were **appended** as three new classes
   rather than overwriting. All 30 pre-existing tests still pass under the
   word-boundary change (only impact: `test_all_known_triggers_match` iterates
   the now-shorter LOOP_TRIGGERS list).

`make test` green across the full suite after changes.

## Technical Decisions

- **Recommendation**: `fix+test`. workflow_detector.detect_workflow is imported by the exit(2) blocking enforcer hook (hooks/workflow_enforcer.py:50) registered in the published plugin.json manifest. Removing 'everything' REDUCES false blocks (the safe direction), but tightening complexity word boundaries could lower some borderline scores below the 0.5 task_mode threshold — verify representative prompts still classify correctly. Must preserve the exact dict keys detect_workflow returns or the hook's fallback stub diverges. Deleting complexity_scorer.py is low-risk (no importers). No knowledge-graph mutation involved. Manifest itself is not edited.

## Out of Scope

- Merging `workflow_detector.calculate_complexity` into the tested `complexity_detector` (changes enforcer block thresholds — separate risk-managed WP).

## Refs

- TASK-42 — Audit Remediation Roadmap (umbrella)
- TASK-45 — dependency (`wp4-hook-tests`)

## Verify

```bash
# See Acceptance Criteria; run the relevant tests/validators before marking done.
```

## Done

- [x] All acceptance criteria checked
- [x] Tests pass locally (`make test` green); CI gate (TASK-43) will run on branch push
- [x] Committed + roadmap (TASK-42) status updated
