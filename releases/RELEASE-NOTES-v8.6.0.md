# Navigator v8.6.0 Release Notes

**Release Date**: 2026-11-15
**Type**: Minor — the `/nav` pane shows roadmaps, the active route with tickets and live
state, and what waits for you (TASK-111)

## Added

- **Roadmap documents.** A roadmap is its own named document: `.agent/roadmaps/<name>.md` with
  a title, a `**Goal**:` paragraph and the `## Route` section of v8.5.0. A roadmap is the
  larger unit; its steps point to task documents and tickets. A task document keeps the
  small route of one step.
- **A step can point to a task document.** `(TASK-12)` in the trailing parenthesis of a step
  line, alone or with a ticket (`(TASK-12, #50)`). The state comes from the Status line of
  that task document: in progress shows as `In work`, done shows as `Done`. GitHub state and
  a checked box still win.
- **The route card in `/nav`.** The pane draws the active route from
  `route_render.py --format json`: the name and the goal, each phase with its done count, the
  open phase with ticket and state per step, and the next step as the press that submits it.
  A second card shows the queue and the items that wait for you, when they exist.
- **The roadmaps list behind `t`.** Every roadmap and every open task document that has a
  route section, with its done count. A press selects the active route for the pane, the
  band and "route report" (the `route` section of `.agent/.nav-runtime-state.json`).
- **Script flags.** `--doc PATH` (`--task` is the same flag), `--list`, `--format json`,
  `--with-list`, `--gh-timeout SECONDS`. With no `--doc` the script takes the selected route,
  else the first open roadmap, else the last open task document with a route.

## Changed

- **The side panel layout (below 72 columns).** One card holds the context gauge, the session
  and the judge verdict as one row each. The route card shows the open phase only, with one
  cut line and one tag per open step: the ticket on the step the press does, one state word
  (`queue`, `work`, `next`, `blocked`) on the others. The queue row and the source line wait
  behind `d`.
- **The band** adds `2 in queue · 1 waits` from the route report and keeps these counts when
  the line is short: the leg text gives way first, then the legs-left count. With a report
  the band names the step that the press does.
- **When the pane asks GitHub.** On `/nav` when the last answer is older than one minute, on
  `r`, and after a turn that ran `gh`, a push, a merge or a pull. Never at session start and
  never under `PILOT_EXECUTOR`. Each call waits 3 seconds at most. The pane has no timers.
- **nav-roadmaps** lists every file in a `roadmaps/` folder, whatever its name.
- A task document with no `## Route` section keeps the "next" leg card of earlier versions.

## Removed

- **The memories card and its pin button.** The prompt hooks inject the same memories
  (`prompt_brief`, `jit_memory`); a pin lived for one prompt.
- **The tasks list behind `d`** (the roadmaps list replaces it) and the graph node count on
  the session card. The context trend moved behind `d`.

## Upgrade notes

- `claude plugin update navigator@navigator-marketplace`, then restart Claude Code.
- No config change. To use a roadmap, add `.agent/roadmaps/<name>.md`; see
  `skills/nav-route/examples/route-section.md`.
- The judge row and the context percent appear after the first prompt and the first
  completed turn of a session, as before.

## Verification

- `make test` (49 tests in `skills/nav-route/functions`), `make mod-gen-check`,
  `make mod-test` (184 tests, 15 new for the pane), `make mod-typecheck`.
- The script tests pass on Python 3.9.6.
- The owner checked the pane on the terminal in a real session; two layout rounds followed.
