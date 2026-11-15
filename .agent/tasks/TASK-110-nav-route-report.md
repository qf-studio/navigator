# TASK-110: nav-route — a route report in plain words, plus a personal route mode

**Status**: 🚧 In Progress
**Created**: 2026-11-15
**Assignee**: Manual

---

## Context

**Problem**:
In long sessions the status reports used internal step codes from the task documents. The
user could not follow them. Navigator has no report shape, and a task document holds the
route in three places with no plain text per step and no ticket on the step.

**Goal**:
Each status report shows the goal, the route in phases with real ticket numbers and live
state, the side tracks, the queue, and the decisions that wait for the user. The report
comes from one `## Route` section that the task template, the render script and the `/nav`
pane all read.

---

## Known Pitfalls & Patterns

- **DECISION** (90%, mem-091): a reply mode is one row of `MODES` in both runtimes;
  `MAX_TOTAL_BLOCK_CHARS` is asserted. Phase 3 adds a row and raises the cap on purpose.
- **PITFALL** (90%, mem-093): the `/nav` next card counts every `- [ ]` of the active task
  doc. Phase 2 makes `parseSteps` read `## Route` first, so acceptance boxes are not steps.
- **PITFALL** (research 2026-11-15): Status readers look at 2000 bytes, 400 bytes and 15
  lines. The goal stays inside `## Context`; nothing new goes above the Status line.
- **PITFALL** (research 2026-11-15): `graph_builder.py` matches "Completed" anywhere. The
  route section holds no state words; state is derived.

---

## Acceptance Criteria

- [x] For a task document with a route section, the output has the five sections and no
      internal step code.
- [x] A step with no plain line gives an error that names the step.
- [x] With `gh` unavailable, the report still renders from the checkboxes.
- [x] The short form shows only changed rows and the count of unchanged rows.
- [x] `route mode on` / `off` work like STE mode; Python and TypeScript give the same block.
- [x] The `/nav` pane takes its steps from `## Route` when the document has one.

---

## Route

### Phase 1: The route format and the report script
- [x] 1. Define the route section: phases, one line per step, ticket and needs at the end.
- [x] 2. Print the report from a task document and from GitHub state. (needs 1)
- [x] 3. Print the short form and the route state for a marker. (needs 2)

### Phase 2: One format for the template and the pane
- [x] 4. Add the route section to the three task templates. (needs 1)
- [x] 5. Make the pane read its steps from the route section. (needs 1)

### Phase 3: The route mode and the marker
- [x] 6. Add the route reply mode to both runtimes. (needs 2)
- [x] 7. Record the route state in a context marker. (needs 3)

### Phase 4: Documents and the pull request
- [x] 8. Describe the skill and the mode in the project documents. (needs 6)
- [ ] 9. Open the pull request for review. (#50, needs 8)

### Waits for you
- [ ] Review the pull request and decide on the release number.
- [ ] Decide what the `/nav` pane shows in place of the memories card.

---

## Out of Scope

- Enforcement in the stop hook.
- A route with no task document (a GitHub tracking issue as the source).
- A route across more than one main task document.
- The `/nav` pane redesign (roadmap and ticket card). It follows as its own task.
- A release bump.

---

## Technical Decisions

| Decision | Options Considered | Chosen | Reasoning |
|----------|-------------------|--------|-----------|
| Route shape in the document | 5-column table; phase list of checkbox lines | Phase list | Real documents have phases, dependencies and parallel steps; checkbox lines already parse in the pane |
| Ticket position | Separate Refs map; on the step line | On the step line, in a trailing parenthesis | One place per fact; the Refs map held 5 of 9 legs in a real document |
| State | A column in the document; derived | Derived from `gh`, checkbox as fallback | A hand-kept state goes stale and can flip the graph status |
| Report shape | Table; phase groups of lines | Phase groups | The owner rejected the simple table |
| Mode block | Full shape in the block; short block that names the skill | Short block | The block rides every prompt; the script holds the shape |
| Block cap | Keep 1600; raise | Raise to 2200 | ADHD + STE already use 1519 |
| Route state store | A state file; a block in the marker | Marker block | The script writes no files |

---

## Verify

```bash
make test
make mod-gen-check
make mod-test
python3 skills/nav-route/functions/route_render.py --task .agent/tasks/TASK-110-nav-route-report.md
```

---

## Done

- [ ] `skills/nav-route/functions/route_render.py` prints the full form, the short form and
      the route state.
- [ ] `make test` and `make mod-test` pass.
- [ ] The pull request for #50 is open.

---

## Refs

- Issue: https://github.com/qf-studio/navigator/issues/50
- Research: the issue comment of 2026-11-15, plus two `navigator-research` passes in the
  session of 2026-11-15 (task document readers; `/nav` pane data sources).

---

**Last Updated**: 2026-11-15
