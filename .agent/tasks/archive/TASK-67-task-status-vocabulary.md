# TASK-67: Task-status vocabulary (unknown → mapped)

**Status**: ✅ Implemented — 2026-07-10

## Context

`skills/nav-graph/functions/task_to_graph.py::extract_status` fed the graph on every
TaskCreated / TaskCompleted / Edit / Write task-doc sync. Its vocabulary only recognized
**emoji-prefixed** status forms (`✅ Completed`, `🚧 In Progress`, `📋 Backlog`,
`🔬 Research`). Any task doc whose `**Status**` line is plain text — e.g.
`**Status**: Implemented` or `**Status**: In Progress` — was recorded as `unknown`.

Navigator's own task docs (this repo) use the plain-text form `**Status**: ✅ Implemented`
and `**Status**: Implemented`, so most in-repo tasks were syncing as `unknown`, which also
suppressed decision-memory extraction (that path is gated on `status == 'completed'`).

## Acceptance Criteria

- [x] Plain-text status words are recognized case-insensitively, with or without a leading
      emoji or punctuation: Implemented, Complete/Completed, In Progress, Planned,
      Deprecated, Design, Research, Dispatched, Blocked.
- [x] Existing canonical values are preserved (`completed`, `in-progress`, `backlog`,
      `research`); genuinely new states get their own canonicals (`design`, `deprecated`,
      `blocked`, `dispatched`). `Implemented` maps to `completed`; `Planned` → `backlog`.
- [x] Recognition is scoped to the `**Status**` line so prose mentions of "design" or
      "research" elsewhere in the doc do not misclassify the task.
- [x] A genuinely unrecognized status line still maps to `unknown`.
- [x] Emoji-only status forms (no word) still resolve via the emoji table (back-compat).
- [x] Colocated unittest discovery is green (`make test`).

## Implementation

`skills/nav-graph/functions/task_to_graph.py`:

- Added module-level `STATUS_EMOJI` (emoji → canonical) and `STATUS_WORDS` (ordered
  `(phrase, canonical)` list, most-specific phrase first so `in progress` wins over any
  shorter substring).
- Rewrote `extract_status` to (1) isolate the `**Status**:` line via a tolerant regex that
  accepts `**Status**:` and `**Status:**`, (2) match whole-word phrases from `STATUS_WORDS`
  against that line, then (3) fall back to the emoji table, then (4) fall back to the legacy
  whole-content emoji/word scan for docs without a standard Status line. Unrecognized →
  `unknown`.

## Verify

```
python3 -m unittest discover -s skills/nav-graph/functions -p 'test_task_to_graph.py' -v
make test
```

New fixtures assert `✅ Implemented`, `Implemented`, `In Progress`, `🔬 Research & Planning`,
`Deprecated` each map to a non-`unknown` canonical; a garbage status line still → `unknown`.

## Done

- [x] `extract_status` widened; new tests added and green.
- [x] No changes outside the two owned code files + this doc.

## Refs

- `skills/nav-graph/functions/task_to_graph.py`
- `skills/nav-graph/functions/test_task_to_graph.py`
- Sibling emoji-only extractor: `skills/nav-graph/functions/graph_builder.py`
