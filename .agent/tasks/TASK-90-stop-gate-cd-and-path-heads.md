# TASK-90: Stop gate over-fires on `cd` and absolute-path read-only heads

**Status**: ✅ Implemented — 2026-10-05 (unreleased)
**Origin**: reject log 2026-10-05 — every stop_completion block that day (3 of 3) carried
`mutating_tools: ["Bash"]` on a turn that only listed, read and ran `git status`. One of them
forced a continuation on a session-start summary. First item on the TASK-84 "8.1 candidates"
list (mem-077 over-fire).

## Cause

`_bash_readonly` (Python) and `bashReadonly` (`hooks/mod/lib/stop-bash.ts`) resolve each
segment's head token against an allowlist; anything unknown is mutating by design (TASK-71:
over-fire only, never under-fire). Two read-only heads were unknown:

- `cd` — leads almost every multi-step command (`cd dir && grep …`). Changes the shell's
  directory, never the tree.
- `/bin/ls` — the absolute path this machine uses because `ls` is eza (mem: `/bin/ls -t` for
  newest-file lookups). The head is compared verbatim, so `/bin/ls` ≠ `ls`.

Claude Code's own `isReadOnly` verdict (TASK-85 belt) did not rescue these turns: the Bash
results did not carry `isReadOnly: true`, so the heuristic decided alone.

Replaying the last two days of transcripts (483 Bash calls) through the classifier:
450 mutating before, 406 after; the 44 that flip are all listings, greps and `git status`.

## Change

- `cd` joins `READONLY_BASH_CMDS` on both sides.
- A head starting with `/` is reduced to its basename before the lookup; the basename must
  still be a known read-only head, so `/usr/bin/rm` stays mutating. Relative paths (`./ls`,
  `~/bin/pilot-board`) never resolve: a script named like a read-only tool is still a script.
- Tests: Python `READONLY` / `MUTATING` replays (`hooks/ops/test_stop_completion.py`) and the
  kit (`hooks/mod/tests/stopops.test.ts`, "TASK-90" case). No generated fixture covers this
  classifier, so nothing to regenerate.

## Verify

```
cd hooks/ops && env -u NAVIGATOR_MOD_OWNS python3 -m unittest test_stop_completion -q   # 65 OK
claude plugin test .                                                                   # 150 pass
```

Live: a Bash-only turn of `cd`, `/bin/ls`, `grep`, `git status` ends without a stop_completion
line in `.agent/.nav-rejects.jsonl`.

## Not done here

- Claude Code's `isReadOnly` on Bash results: whether it is ever set for Bash is an
  external fact; when it is, the TASK-85 belt already wins. Worth a probe in a later dogfood.
- Other unknown heads seen in the replay were all inside heredocs of genuinely mutating
  commands (`python3 - <<EOF`), so no further allowlist growth is justified by the data.
