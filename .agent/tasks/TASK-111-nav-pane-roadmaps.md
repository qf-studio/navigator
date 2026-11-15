# TASK-111: /nav pane — roadmaps, the active route with tickets, the queue

**Status**: 🚧 In Progress
**Created**: 2026-11-15
**Assignee**: Manual

---

## Context

**Problem**:
The `/nav` pane showed one leg, three memories that the prompt hooks inject already, and a
task list behind a key. It showed no ticket numbers and no live state. A roadmap was a task
ID, and a task ID says nothing about a roadmap.

**Goal**:
The pane shows named roadmaps, the active route in phases with tickets and live state, the
queue, and what waits for the owner. It stays readable in the narrow side panel.

---

## Known Pitfalls & Patterns

- **DECISION** (2026-11-15): one route format and one source of state. The pane runs
  `route_render.py --format json --with-list` and draws the result; it derives no state.
- **PITFALL** (mem-093): every `- [ ]` of the active doc used to count as a leg. `parseSteps`
  reads `## Route` first; it stays the fast path between two script runs.
- **PITFALL** (TASK-108): remote surfaces get no hotkey props and no glyph gauges.
- **PATTERN** (TASK-102, TASK-81): outbound calls are skipped under `PILOT_EXECUTOR`; the pane
  has no timers, so a refresh needs an event.

---

## Acceptance Criteria

- [x] A roadmap document in `.agent/roadmaps/` is a route; a step can point to a task document.
- [x] The route card shows phases with counts, and the open phase with ticket and state per step.
- [x] The queue and the items that wait for the owner show when they exist.
- [x] `t` lists the routes; a press selects one for the pane, the band and "route report".
- [x] Below 72 columns the pane folds: one line for context and session, open steps only.
- [x] GitHub is asked on `/nav`, on `r` and after a turn that ran `gh`; never at session
      start and never under `PILOT_EXECUTOR`.
- [x] The memories card, its pin button and the tasks list are gone.

---

## Route

### Phase 1: The script
- [x] 1. Read roadmap documents and steps that point to a task document.
- [x] 2. Print the report and the route list as JSON for the pane. (needs 1)

### Phase 2: The pane
- [x] 3. Draw the route card, the queue card and the roadmap list. (needs 2)
- [x] 4. Fold the pane for the narrow side panel. (needs 3)
- [x] 5. Refresh ticket state on the right events. (needs 3)

### Phase 3: Documents and the check
- [x] 6. Describe the new pane and the roadmap documents. (needs 3)
- [ ] 7. Check the pane in a real session on the terminal and on the desktop. (operator, needs 6)

### Waits for you
- [ ] Decide when the pane update is released.

---

## Out of Scope

- A press that opens a ticket in the browser.
- A route with no document (a GitHub tracking issue as the source).
- The Python fallback runtime: it has no pane.
- A release. It follows on the owner's word.

---

## Technical Decisions

| Decision | Options Considered | Chosen | Reasoning |
|----------|-------------------|--------|-----------|
| Source of ticket state in the pane | A TypeScript port of the state rules; the Python script | The script | One set of rules; the mod already runs Python helpers |
| A roadmap | A task document; its own document | `.agent/roadmaps/<name>.md` | A roadmap spans tasks and tickets; a task ID is not its name |
| Step to task link | A Refs map; an attribute on the step line | `(TASK-12)` on the line | Same place as the ticket; state from the task's Status line |
| Selection store | `$.store`; the shared state file | `.nav-runtime-state.json`, section `route` | "route report" must follow the pane's selection |
| GitHub latency | A timer; a race; a per-call timeout | `--gh-timeout 3`, asked only on events | No timers in the pane; a fresh report is reused for a minute |
| Narrow layout | The wide card wrapped; a folded card | Folded | The side panel has about 36 columns |
| Memories card | Behind `d`; removed | Removed | The prompt hooks inject the same memories |

---

## Verify

```bash
make test
make mod-gen-check
make mod-test
make mod-typecheck
python3 skills/nav-route/functions/route_render.py --list
python3 skills/nav-route/functions/route_render.py
```

---

## Done

- [x] `route_render.py` reads `.agent/roadmaps/*.md`, `TASK-NN` steps, and prints JSON.
- [x] `hooks/mod/ui/roadmap.ts` and the pane cards exist with tests.
- [x] `make test`, `make mod-test` and `make mod-typecheck` pass.
- [ ] The pane is checked in a real session on both surfaces.

---

## Refs

- Roadmap: `.agent/roadmaps/route-reports-and-pane.md` (step 3)
- Before: `.agent/tasks/TASK-110-nav-route-report.md` (v8.5.0, issue 50)

---

**Last Updated**: 2026-11-15
