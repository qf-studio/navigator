# TASK-91: In-progress task detection reads the Status line, not prose

**Status**: ✅ Released — v8.2.7, 2026-10-05

## Origin

The `/nav` pane named TASK-67 as the next destination and every compact marker listed it
under "In-progress tasks", three months after it shipped (7caab72, 2026-07-10). TASK-67
itself fixed exactly this class of bug for the knowledge graph (`task_to_graph.py` reads
the `**Status**` line); two other parsers were left behind and matched the words
"in progress" anywhere in the doc. TASK-67's doc quotes the phrase in its own prose.

## Cause

Three sites decided "in progress" by substring over the whole head of a task doc:

- `hooks/mod/register.tsx` `refreshPane`: a shell `grep -il "status.*\(🚧\|in progress\)"`
  over every task doc, which matches any line containing both words.
- `hooks/mod/ops/compact_marker.ts` `activeTaskHint` and its Python twin
  `hooks/ops/compact_marker.py` `_active_task_hint`: `"in progress" in head.lower()`
  over the first 400 bytes.

## Change

- One predicate on both sides, `isInProgress` (`hooks/mod/lib/tasks.ts`) and
  `is_in_progress` (`hooks/ops/compact_marker.py`): when the doc has a Status line
  (`**Status**:`, `**Status:**`, `> Status:`, same tolerant regex as `task_to_graph.py`),
  that line alone decides — 🚧 or the whole-word phrase "in progress" / "in-progress".
  Docs without a Status line keep the legacy whole-head scan.
- The pane lists task docs through `$.fs.list` + `$.fs.read` and the predicate instead of
  the shell grep; the `path|# heading` line format into `parseTasks` is unchanged.
- The marker hint on both runtimes calls the predicate; the lifeops fixtures gained a
  finished doc that quotes the phrase (must not appear) and the `**Status:**` and
  `> Status:` forms (must appear).

## Verify

```
make test            # with NAVIGATOR_MOD_OWNS unset in the shell
make mod-gen-check mod-test mod-typecheck
```

New tests: `InProgressPredicateTests` in `hooks/ops/test_compact_marker.py`,
"in-progress predicate (TASK-91)" in `hooks/mod/tests/nav.test.ts`; the pane tests seed
task docs with Status lines instead of stubbing the grep.

On this repo the rule now lists TASK-15 only; TASK-67 drops out.

## Refs

- `hooks/mod/lib/tasks.ts`, `hooks/mod/register.tsx`, `hooks/mod/ops/compact_marker.ts`
- `hooks/ops/compact_marker.py`, `scripts/mod_fixtures/lifeops.py`
- Sibling: `skills/nav-graph/functions/task_to_graph.py::extract_status` (TASK-67)
