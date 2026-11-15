---
name: nav-route
description: Print a route report in plain words from the active task document and live GitHub state - the goal, the roadmap in phases with ticket numbers, side tracks, the queue now, and what waits for the user. Auto-invoke when user says "route report", "show the route", "where are we on the plan", "status report", "what is left", "what waits for me", or when route mode asks for a report (session start and end, after a dispatch, a merge, a review verdict, or a deviation from the plan).
allowed-tools: Bash, Read
version: 1.0.0
---

# Navigator Route

Print a status report that the user can follow without the task document. The report names
work by what it does and by its ticket number. It never shows an internal step code.

## When to Invoke

- The user asks for a status: "route report", "show the route", "where are we", "what is left".
- Route mode is on (`route mode on`) and one of its events occurs: session start, session
  end, a dispatch, a merge, a review verdict, a deviation from the plan.

Do NOT invoke for the list of all roadmap documents. That is `nav-roadmaps`.

## The Source: the `## Route` Section

The script reads one section of the task document. `nav-task` writes it for a new task.

```markdown
## Route

### Phase 1: The gate reads the status line
- [x] 1. Read the status from one shared function. (#48)
- [ ] 2. Show done documents as one count line. (PR #49, needs 1)
- [ ] 3. Install the plugin on the build machine. (operator, needs 2)

### Side tracks
- [ ] Repair the test target on macOS. (#52)

### Waits for you
- [ ] Decide the release number.
```

- A step is one checkbox line: an order number and a plain line that says what the step does.
- The trailing parenthesis is optional. It holds the ticket (`#12`, `PR #12`,
  `owner/repo#12`), the word `operator` for a step that a person does, and `needs` with the
  step numbers that must be done first.
- A step with no ticket and no `operator` shows as "Not filed".
- The section holds no state words. The state comes from GitHub when `gh` answers. A checked
  box is always done. With no `gh`, the checkboxes give the state.
- `### Side tracks` holds work outside the main route. `### Waits for you` holds the open
  decisions for the user.
- The goal comes from `**Goal**:` in `## Context`.

The `/nav` pane reads its legs from the same section (`hooks/mod/ui/route.ts`).

## Execution Steps

### Step 1: Run the Script

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"

python3 "$PLUGIN_DIR/skills/nav-route/functions/route_render.py" [--task .agent/tasks/TASK-XX-slug.md]
```

With no `--task`, the script takes the last open task document that has a route section.

Choose the form:

| Moment | Command |
|---|---|
| Session start, a plan change, or the user asks | the full form (no flag) |
| Each other event, when a marker holds an earlier state | `--short --since <marker file>` |
| The full form with changes marked | `--since <marker file>` |
| A marker is written (`nav-marker`) | `--state` (JSON for the `## Route State` block) |

`--since` takes a context marker that holds a `## Route State` block, or a JSON file from
`--state`. Other flags: `--no-gh` (checkboxes only), `--queue-label NAME` (an issue label
that means "in the queue"; default `pilot`, `in-progress`, `queued`; an assignee also counts),
`--today YYYY-MM-DD`.

### Step 2: Present

1. Paste the output as printed. Do not retype the lines and do not add step codes.
2. If the work left the plan since the last report, add one sentence below the report: what
   left the plan, and why.
3. Add nothing else.

### Step 3: On an Error

The script exits with code 2 and one line on stderr. It never guesses.

| Error | Action |
|---|---|
| `step N has no plain line` | Write what step N does in plain words in the task document. |
| `step N starts with an internal code 'U2'` | Replace the code with plain words. |
| `the task document has no '## Route' section` | Add the section (see `examples/route-section.md`). |
| `no '**Goal**:' text` | Write two or three plain sentences after `**Goal**:` in `## Context`. |
| `needs step N, which the route does not have` | Correct the `needs` number. |

Edit the task document, then run the script again. Ask the user when the plain words for a
step are not clear from the document.

## Output Format

See `examples/route-report.md` for the full form and the short form.

## Rules

- The states are: `Done` (with the date from GitHub), `Merged`, `In the queue now`, `Next`,
  `Later`, `Blocked: needs step N`, `Closed, not merged`, `Closed, not planned`.
- `Next` is the first open step whose needed steps are done. A step with no `needs` does not
  wait for the steps before it.
- An open pull request, an assigned issue, and an issue with a queue label are in the queue.
- "What waits for you" lists the operator step that is next, each open pull request, and the
  open lines of `### Waits for you`.
- The script reads the task document and calls `gh api` for each ticket. It writes no files.
- A route covers one task document. Other work is one side-track line with its ticket.
