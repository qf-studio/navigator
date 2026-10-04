# Navigator v8.1.1 Release Notes

**Release Date**: 2026-10-04
**Type**: Patch — the `/nav` reads card sees reads made through Bash (TASK-87)

## Fixed

- **Reads through Bash now count.** The reads card and its fan-out verdict counted the `Read`
  tool only, so a session that read docs with `cat` / `sed -n` / `head` showed `0  0 docs`.
  A read-only Bash command (`cat`, `sed`, `head`, `tail`, `grep`, `rg`, `wc`, `diff`) now counts
  every file it names — `.agent/` paths as docs, the rest as code — exactly like a `Read` call.
  Not counted: `ls`, `find`, running a script, `awk`, anything that redirects to a file.
- **`sed` without an in-place flag is read-only** in both runtimes' Bash allowlist
  (`-i…` / `--in-place[=…]` still mark the turn as mutating), so a `sed -n` inspection turn no
  longer trips the completion gate.

Tests: 131 kit tests; classifier cases in both suites; fixtures regenerated.
Design: `.agent/tasks/archive/TASK-87-bash-reads-count.md`.
