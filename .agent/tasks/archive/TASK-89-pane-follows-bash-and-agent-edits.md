# TASK-89: /nav pane follows Bash edits, git moves, agent runs and mid-turn progress

**Status**: ✅ Released — v8.1.2, 2026-10-05
**Origin**: dogfood 2026-10-05 — after a whole task closed through Bash heredocs, `git mv` to the
archive and a commit, the pane still showed the old task and leg until `r` was pressed.

## Cause

`refreshPane` ran at `turn.complete` only when `activity.docsTouched` was set, and only the
Edit / Write / NotebookEdit `tool.call` handler set it (file path under `.agent/`). Three ways
`.agent/` changes without that flag: a mutating Bash command (heredoc, `python3 -`, `sed -i`),
git moving or committing task docs (`git mv` into `archive/`), and a subagent's edits, which do
not pass through this module's `tool.call`. Within a turn nothing re-read the active task's
checklist, so the next card moved only after the turn.

## Change

- `bashTouchesDocs(command)` (`hooks/mod/ui/nav.ts`): a mutating Bash command that names
  `.agent` or is a file-moving git command (`mv`, `commit`, `checkout`, `switch`, `stash`,
  `pull`, `merge`, `rebase`, `reset`, `restore`, `cherry-pick`). Read-only Bash never reaches it.
- `docsTouched($)` in `register.tsx`: sets the flag and runs `refreshSteps` — one `fs.read` of
  the active task doc, re-parsed into steps, so the next card advances mid-turn. Called from
  the Edit/Write handler (as before) and from the Bash handler when the command touches docs.
- A subagent's `turn.complete` sets `docsTouched`: the parent turn reloads the pane.
- The full `refreshPane` (three subprocess spawns) still waits for the turn to end.

## Verify

`register.test.ts` (t7) Bash heredoc into `.agent/tasks/` reloads the marker at turn end, a `# ro`
read does not; (t8) `git mv` reloads, `npm run build` does not; (t9) an Edit on the active doc
moves `→ then` before any `turn.complete`; (t10) a subagent turn makes the parent turn reload.
Live: close a task through Bash and watch `/nav` without `r`.
