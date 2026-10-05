# Navigator v8.2.1 Release Notes

**Release Date**: 2026-10-05
**Type**: Patch — the reject line fits the reads card (TASK-88 follow-up)

## Fixed

- **The reads card names the op.** v8.2.0 ended the card with
  `rejects today 1 · last 12:04 read_guard`; at the card's 26% width the first live screenshot
  showed `rejects today 1 · …` — the op name, the one part worth reading, was the part cut off.
  The line is now `1 reject · 12:04 read_guard` (`no rejects` when the log is empty), 27
  characters, so the op fits. `l` still opens the last eight full lines.

Tests: the pane-model test asserts the new form and the plural. Docs: CLAUDE.md, the archived
TASK-88 doc and the docs-site pages (nav-pane, reject-log) say the new line.
