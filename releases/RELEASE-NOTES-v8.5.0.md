# Navigator v8.5.0 Release Notes

**Release Date**: 2026-11-15
**Type**: Minor — nav-route: a route report in plain words, and a personal route mode (GH-50)

## Added

- **nav-route.** "route report" prints a status report that a reader can follow without the
  task document. It has five parts: the goal, the roadmap in phases, side tracks, the queue
  now, and what waits for you. Each step shows what it does in plain words, its ticket
  number, and its state (`Done 2026-11-08`, `Merged`, `In the queue now`, `Next`, `Later`,
  `Blocked: needs step 2`). The state comes from GitHub through `gh api`; a checked box is
  always done; with no `gh` the checkboxes give the state. `--short --since <marker>` prints
  only the changed lines and `unchanged: N`. `--state` prints the route state as JSON. A step
  with no plain line, or a step that starts with an internal code such as `U2`, is an error
  that names the step. The script writes no files.
- **The `## Route` section of a task document.** The three task templates (the nav-task
  skill, `task_formatter.py`, `templates/task-template.md`) carry it. A route is a list of
  phases; a step is one checkbox line with an order number and a plain line. A trailing
  parenthesis holds the ticket (`#12`, `PR #12`, `owner/repo#12`), `operator` for a step a
  person does, and `needs 1, 2`. `### Side tracks` and `### Waits for you` hold the work
  outside the route and the open decisions. The section holds no state words.
- **Route mode.** `route mode on` / `route mode off` / `route mode` is a third personal reply
  mode, a row of `MODES` in both runtimes with the switch in
  `~/.config/navigator/route-mode.json` and the repo block `route_mode`. Its block names the
  five parts, keeps internal step codes out, asks that each change since the last report is
  marked, and says when a report is due: session start and end, a dispatch, a merge, a review
  verdict, a deviation from the plan. The lines the skill prints stay as printed, so the STE
  sentence rules do not apply to them.
- **Route state in a context marker.** nav-marker stores the `--state` JSON in a
  `## Route State` block. The next session passes the marker to `--since`.

## Changed

- **The `/nav` pane takes its legs from `## Route`.** `parseSteps` reads the route section
  first, then the checklist, then the plan table. Acceptance and Done checkboxes of a task
  document with a route are no longer legs; side tracks and the waits list are not legs.
  Documents with no route section behave as before.
- **The reply-mode block cap is 2200 characters** (was 1600). ADHD and STE use 1519; the
  route block has 633. A Python test now asserts that the TypeScript mirror holds every
  block verbatim.

## Upgrade notes

- `claude plugin update navigator@navigator-marketplace`, then restart Claude Code.
- "sync CLAUDE.md" seeds `route_mode: { "enabled": true, "on": null }` in
  `.agent/.nav-config.json`. Without the block the defaults apply and the mode works.
- Task documents written before 8.5.0 have no route section. nav-route names the missing
  part; add the section from `skills/nav-route/examples/route-section.md`.
- Route mode is a rule for the model, not a gate. The stop hook does not check for a report.

## Verification

- `make test` (40 new tests in `skills/nav-route/functions`), `make mod-gen-check`,
  `make mod-test` (169 tests).
- The route tests and the mode tests pass on Python 3.9.6.
