# TASK-72: TRIZ Phase 1 — contradictions in briefs, decisions, and research

**Status**: ✅ Implemented — 2026-09-10

## Context

**Problem**: Navigator's research surfaces are descriptive. The research agent answers
"how does X work", the planner produces one plan, and Decision memories store "we chose X
because Y" without the tension X resolved. Nothing lets a session ask "how did we resolve
this *kind* of problem before".

**Goal**: Borrow the one TRIZ move that transfers cleanly to software — name the
contradiction (improving A worsens B) and record how it was separated — and wire it into the
places Navigator already runs before code changes: the intent brief, the knowledge graph,
and the research/planning agents.

Phase 1 captures the data and closes one loop. No new hook op, no new memory type, no
schema validator. Phase 2 (divergent research step producing 3 candidates from different
principle families, a software-mapped principles reference) is deferred until the graph
holds 10–15 tagged decisions.

## Implementation

- **Brief** (`hooks/ops/prompt_brief.py`, `skills/nav-brief/SKILL.md`): optional
  `Contradiction` row, "improving X worsens Y" or `none`. Gated by
  `brief_hook.contradiction_field` (default on). Declared contradiction → query prior
  resolutions before filling `Approach`.
- **Decision memories** (`skills/nav-graph/functions/`): three optional footer lines
  `**Contradiction**` / `**Separation**` / `**Principle**` written by `memory_writer`,
  parsed by `graph_maintenance._parse_memory_file`, threaded through `add_memory`, and
  synced disk → node by `reconcile` (new `field_updates`, applied with `--execute`; never
  clears, never re-syncs `summary`). `--fields-only` applies the sync without registering
  unindexed files — needed here because `resolved/` holds deliberately pruned memories
  (mem-058) that a plain `--execute` re-registers under fresh ids with garbage summaries.
  Untagged memories are byte-identical to before.
- **Query**: `graph_manager.py --action contradictions [--filter "<terms>"]`; recall
  renderers append ` ↔ A vs B` when present.
- **Research prompts**: `agents/navigator-research.md` Phase 0.5 (Ideal Final Result +
  reuse inventory, contradiction lookup in Phase 0), `agents/task-planner.md` step 1.5 +
  IFR line in the plan template, nav-workflow RESEARCH bullets.
- **Retrofit**: ~10 existing decisions tagged by hand, reconciled into graph.json.

## Non-goals

- Contradiction detection in the ambiguity scorer; drift detection on the row.
- `.agent/philosophy/TRIZ-*.md` principles doc (Phase 2).
- Tagging every memory; consolidating the duplicated memory-type list (separate cleanup).

## Acceptance Criteria

- [x] NAV-BRIEF injection carries the Contradiction row by default; off-switch restores the
      v6 six-field line byte-for-byte
- [x] `create_memory_file` without the fields produces byte-identical output
- [x] writer → parser → reconcile round-trip preserves all three fields
- [x] `reconcile` reports and (on `--execute`) applies field updates to already-indexed
      nodes; idempotent; untagged nodes untouched
- [x] `--action contradictions --filter` matches case-insensitively, exits 0 on no match
- [x] recall compact/markdown/json show the fields only when present
- [x] `graph_builder` rebuild preserves the fields
- [x] Retrofitted decisions answer `--filter rollback` with mem-063 and mem-073

## Verify

```bash
make test
python3 skills/nav-graph/functions/graph_manager.py --action contradictions --filter rollback
python3 skills/nav-graph/functions/graph_maintenance.py --action reconcile   # field_updates: 0 after retrofit
# retrofit apply path (never plain --execute in this repo, see Implementation):
python3 skills/nav-graph/functions/graph_maintenance.py --action reconcile --execute --fields-only
python3 skills/nav-graph/functions/graph_maintenance.py --action health
```

## Phase 2 gate (revisit ~2026-10-08)

Count decisions carrying `contradiction` and whether `--action contradictions` was used in
sessions. If neither moved, do not build Phase 2.

## CHANGELOG draft (add under the next version heading)

- **TRIZ contradictions (TASK-72)**: intent brief gains an optional `Contradiction` row;
  Decision memories can record the contradiction they resolved (`--contradiction`,
  `--separation`, `--principle`) and are queryable via `graph_manager.py --action
  contradictions`; reconcile syncs the fields disk → graph; research and planner agents ask
  for the Ideal Final Result and a reuse inventory before mapping code.

## Refs

- Plan: brainstorm 2026-09-10 (TRIZ for Navigator, Phase 1 of 2)
- Related: TASK-56 (nav-brief), TASK-47 (KG integrity / reconcile), mem-061..073
