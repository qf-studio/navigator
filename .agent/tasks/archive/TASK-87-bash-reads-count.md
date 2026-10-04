# TASK-87: Reads through Bash count in the /nav reads card

**Status**: ✅ Implemented — 2026-10-04 (unreleased; next patch)
**Origin**: dogfood 2026-10-04 — a session that read `.agent/` docs all day with `cat` / `sed -n`
showed `0  0 docs`; the card counted the `Read` tool only. The fan-out verdict had the same
blind spot.

## Change

- `ui/nav.ts` `bashReadFiles(command)`: for each pipeline segment whose head is `cat`, `sed`,
  `head`, `tail`, `grep`, `rg`, `wc` or `diff`, every argument that looks like a file (known
  extension, optional absolute path) is a read; `isDocPath` = `.agent/` paths.
- `register.tsx` Bash handler: when the command is read-only (`bashReadonly`) and did not error,
  each file counts through `countRead` — docs vs code — exactly like a `Read` call.
- `stop-bash.ts` / `stop_completion.py` (parity): `sed` is read-only unless an in-place flag
  (`-i…`, `--in-place[=…]`) is present. Fixtures regenerated.

## Not counted

`ls`, `find`, running a script (`python3 x.py`), `awk` (not on the allowlist), anything with a
redirect to a file (the command is then not read-only). The read guard (PreToolUse on `Read`)
still sees only the Read tool: it blocks, so it stays conservative.

Tests: `nav.test.ts` parser cases, `register.test.ts` (i2) end to end, classifier cases in both
suites. 131 kit tests.
