# Navigator v8.1.2 Release Notes

**Release Date**: 2026-10-05
**Type**: Patch — the `/nav` pane follows every kind of doc edit (TASK-89); the session-start drift check is hook-safe and the auto-update docs are honest (TASK-81)

## Fixed

- **The pane follows Bash edits, git moves and agent runs.** The task list, marker, memories
  and the next card reloaded only after a turn in which Edit or Write touched `.agent/`. A doc
  changed through a Bash heredoc or `sed -i`, a task archived with `git mv`, a commit, or a
  subagent's edits left the pane stale until `r`. All of them now set the reload; and each edit
  of the active task doc re-reads its checklist at once, so the next card advances while the
  turn is still running. The full reload still waits for the turn to end.
- **The hook drift check never runs the Claude CLI.** `auto_updater.py --check-drift`, run by
  both session-start ops, resolved the plugin version with `claude plugin list` — a 10 s
  subprocess inside a 4 s hook budget, and the source of the wrong "behind plugin (v7.0.0)" line
  in September. It now reads the plugin's own manifest, then the cache tree. 0.08 s live.
- **Auto-update docs say what happens.** The nav-features, nav-upgrade and nav-sync-claude
  skills, the feature table, and eight docs-site pages no longer claim Navigator updates itself
  on session start. It shows the notice; `claude plugin update navigator@navigator-marketplace`
  or nav-start Step 1.5 applies it. `auto_update.enabled: false` means no check and no notice.

Tests: 139 kit tests (+9 across update and register suites); Python drift tests with the CLI
patched to fail plus a static guard; the golden fixture drops the version-dependent drift
section (`tests/golden/README.md`, deviations).
Design: `.agent/tasks/archive/TASK-89-pane-follows-bash-and-agent-edits.md`,
`.agent/tasks/archive/TASK-81-auto-update-truth.md`.
