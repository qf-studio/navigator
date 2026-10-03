# Navigator v8.0.1 Release Notes

**Release Date**: 2026-10-03
**Type**: Patch — the completion gate stops over-firing on read-only turns (TASK-85)

## Fixed

- **`stop_completion` forced continuations on read-only turns when two sessions shared a repo.**
  The previous Stop's working-tree digest lived in the session-scoped `completion` section; any
  event from another session in the same repo reset it, so the tree-evidence rule could not
  fire and the Bash allowlist alone judged the turn. The digest now lives per session in
  `tree.digests` (bounded to the 8 most recent sessions), outside the scoped section, in both
  runtimes. `completion.tree_digest` is still written.
- **Read-only allowlist**: `lsof`, `pgrep`, `nproc`, `sw_vers`; `curl` is read-only unless it
  names an output (`-o`, `-O`, `-sSo…`, `--output…`, `--remote-name…`).
- **Mod only**: a Bash-only turn whose every call Claude Code held `isReadOnly` is never
  mutating, whatever the allowlist says. Python keeps the allowlist; parity fixtures replay with
  no such flag.

Tests: Python op suite 65 (4 new), mod kit 124 (classifier, flag, end-to-end gate pair),
fixtures regenerated. Verified live on 2026-10-03 against the turn shape that over-fired.

Full design: `.agent/tasks/TASK-85-stop-gate-shared-state.md`.
