# TASK-71: stop_completion false-fires on ops/status turns

**Status**: ✅ Implemented — 2026-07-16

## Context

Dogfood finding from live v7 use in the pilot repo (2026-07-16): the gate
forced continuations on two consecutive turns that did no codebase work —
one marker-load/queue-check turn, one **purely read-only** daemon/PR status
check. Two independent root causes:

1. **TASK-70's allowlist can't parse real inspection commands.** `gh pr view`,
   `ps aux`, `command -v`, `[ -n "$X" ]`, `for` loops, and `LOG=$(ls ...)`
   assignment heads all tokenize to unrecognized heads → "mutating".
   `git fetch`/`ls-tree` were missing from the git subcommand set.
2. **Indicators can't reach 2/6 on ops turns in a busy repo.** `code_committed`
   derives from whole-tree `git status --porcelain` cleanliness — a shared
   root with a pending sync commit pins it False indefinitely; with
   `code_simplified` never derivable and `ticket_closed` pinned by PM config,
   the score sits at 1/6 and EVERY vocabulary-mutating turn without a trailing
   exit signal eats a forced continuation, one per turn, forever.

## Implementation

`hooks/ops/stop_completion.py`:

- **Shell-aware `_bash_readonly()`**: `$(...)`/backtick substitutions validated
  recursively then removed; leading `VAR=` assignments and control-flow words
  (`if`/`then`/`do`/`while`/`!`/`time`...) stripped; `for`/`done`/`fi` are
  standalone; `command -v` is a lookup. **Redirect hardening**: output
  redirects to anything but `/dev/null`/`&N` are mutating — closes the
  `echo x > file` hole TASK-70's allowlisted heads left open.
- **Allowlists**: + `ps`, text-pipeline staples (`sort`/`cut`/`tr`/`jq`/...),
  `test`/`[`/`[[`; git + `fetch`, `ls-tree`, `ls-remote`, `cat-file`,
  `show-ref`, `rev-list`; NEW `READONLY_GH_SUBCMDS` resolved by subcommand
  pair (`pr view` reads, `pr merge` stays mutating), mirroring the git
  pattern. Unknown heads/pairs stay mutating — over-fire only.
- **Tree-digest evidence layer**: `_tree_digest()` (sha256 of porcelain
  output) captured at every armed Stop — before the fuse/cap short-circuits —
  into `completion.tree_digest` (survives the stop_state barrel). In
  `_turn_mutating()`, an unchanged digest across consecutive Stops overrules a
  vocabulary-mutating classification for **Bash-only** turns: daemon
  restarts, sqlite reads, and sibling-repo work no longer read as "mutated
  the codebase". File tools and Task/Agent turns never take this path;
  missing digests (non-repo, timeout, first turn) fall back to vocabulary.
  `stop_hook_active` stops skip capture — a forced continuation's writes land
  in the next comparison (over-fire only, documented).

## Non-goals

- `code_committed` still derives from whole-tree cleanliness — with the
  digest layer suppressing ops turns at classification, the dirty-root pin
  no longer matters there; revisit only if genuine code turns misjudge.
- No new config knobs; reason string unchanged (mem-034).

## Acceptance Criteria

- [x] The 2026-07-16 false-fire command shapes classify read-only —
      PERMANENT replays in `ReadonlyBashParserTest`.
- [x] `gh` writes, redirects to paths, substitutions running unknown
      commands, and `VAR=1 make build` stay mutating.
- [x] Unchanged digest suppresses a vocabulary-mutating Bash turn; changed /
      missing digest falls back; file tools ignore the digest; capture
      survives the consumed-fuse path — `DigestEvidenceTest`.
- [x] End-to-end via `nav_dispatch.py` in a real git repo: third Stop on an
      untouched tree is silent where pre-TASK-71 blocked every turn.
- [x] `make test` green (61 stop_completion tests, all suites pass).

## Verify

```
python3 -m unittest discover -s hooks/ops -p 'test_stop_completion.py'
make test
```
