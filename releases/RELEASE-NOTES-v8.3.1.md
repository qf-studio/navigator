# Navigator v8.3.1 Release Notes

**Release Date**: 2026-10-05
**Type**: Patch — Bash read-only classifier is quote-aware (TASK-94)

## Fixed

- **A pipe inside quotes no longer makes a turn "mutating".** The Stop gate's Bash
  classifier cut commands at every `|`, `;` and `>` without reading quotes, so a grep
  pattern with `\|`, a `--jq '.a | .b'` filter or a `printf "%s | %s"` format produced a
  bogus segment whose head was unknown, and the whole turn counted as a write. Both runtimes
  now mask the contents of quoted spans before the redirect and segment scans. Command
  heads, flags and redirect targets are never inside quotes, so nothing that was read-only
  can turn mutating, and `echo "x" > "$F"` still counts as a write.

Measured on three days of this repo's transcripts: 134 of 522 "mutating" verdicts become
read-only, none of them a real write. Heredoc bodies are unchanged and remain the largest
remaining over-fire bucket.

Tests: Python +14 parser cases, kit +1 with a mask unit test, two parity transcripts
(157 kit tests). Task doc: `.agent/tasks/TASK-94-bash-classifier-quote-aware.md`.
