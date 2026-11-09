# Navigator v8.4.13 Release Notes

**Release Date**: 2026-11-09
**Type**: Patch — session discipline (GH-40, GH-41, GH-42), Open Tasks on the Status line
(GH-47), nav-roadmaps

## Added

- **task_doc_guard (GH-40).** A deny-only PreToolUse gate on Write, Edit and Bash blocks a
  new `<task_prefix>-<n>*.md` directly under `.agent/tasks/` (file write, redirect, heredoc,
  `tee`, `cp`, `mv`) until `/nav-task` ran this session. The signal is recorded from a Skill
  call that ends in nav-task and from the slash command typed at the prompt. Existing docs,
  other directories, the archive and the Pilot executor pass. `task_doc_guard_hook.strict_block:
  false` turns the gate into an advisory. Python-only op; the plugin PreToolUse matcher is now
  `Read|Write|Edit|Bash|Skill`.
- **nav-roadmaps.** "show roadmaps" renders every roadmap document under `.agent/` as one
  table (title, path, kind, last date, status line, stale flag) plus per-section ticket counts
  for ticket-table roadmaps. `--also <repo>/.agent` scans sibling repos. The scanner reads
  headers only and changes no files.

## Changed

- **The completion gate needs a marker after a task doc (GH-41).** With
  `stop_completion.continue_enabled`, a turn that wrote a task doc under `.agent/tasks/` or
  dispatched legs without `--dry-run` records session evidence. Until a real context marker
  (not the `.active` pointer) is written this session, an exit signal no longer ends the turn
  and the continuation names nav-marker. `max_continues` still caps it; the cap logs
  `stop_completion.marker_bypassed` to the reject log. Ported to the mod.
  `stop_completion.require_marker_after_task_doc: false` restores the old rule.
- **Session-start Open Tasks (GH-47, #48, #49).** Open docs come first, newest id first, 20 at
  most; done docs collapse into one count line with up to 15 ids and "archive with nav-task".
  Only the Status line decides, through the TASK-91 regex shared with compact_marker
  (`is_done` next to `is_in_progress`, mirrored in `hooks/mod/lib/tasks.ts`): a leading ✅ 📦
  ❌ 🗑 means done, any other symbol means open, and without a symbol the first clause is
  matched whole-word (Complete, Implemented, Released, Won't Do, Removed). The H1 and prose
  never count, so a Backlog line that mentions "archived launch plans" stays open and a doc
  whose title quotes "completed" is read from its Status line. Status values are cut at 160
  code points; the head window per doc is 2000 code points. Task ids match ASCII digits only
  and the mod orders by code point, so both runtimes emit the same bytes (fixture
  `tasks-overflow`).

## Fixed

- **Duplicate task IDs across sessions (GH-42).** `get_next_task_id` (local mode) takes max+1
  over the working tree, `tasks/archive/` and `origin/main` after a `git fetch`; a failing
  fetch or a missing remote falls back to the local two with a stderr note. Git calls never
  prompt or hang.
- **Python 3.9.** `make test` is green on 3.9, the Pilot box's and macOS system Python:
  `code_analyzer` future annotations, the stdlib-purity guard skipped below 3.10. CI runs
  3.9 (ubuntu-24.04) and 3.12.
- **`make test`** runs the suites in parallel (`TEST_JOBS`, default 4), writes everything to
  stderr, ends with a FAILED SUITES block, and scrubs `NAVIGATOR_MOD_OWNS`, `PILOT_EXECUTOR`,
  `CLAUDE_PROJECT_DIR` and `CLAUDE_USER_MESSAGE` before every suite. The hooks p95 timing
  budget scales with the measured host slowdown. On macOS the recipe no longer dies inside BSD
  `xargs -I{}` ("command line cannot be assembled, too long") while printing "All unit tests
  passed"; the directory now arrives as `$1`.
- **Mod type check** clean again after #48 (`BigInt` on a possibly-undefined regex group).

Verified: every Python test directory green on 3.9 and 3.12 (hooks 856, nav_hook_lib 390,
golden 27), `make mod-test` 168 pass, `make mod-typecheck` clean, `gen_mod_data.py --check`
clean; on this repo the Open Tasks block lists six open docs and counts 46 done docs in one
line.

## Upgrade

```bash
claude plugin update navigator@navigator-marketplace
```

Restart Claude Code after the update.
