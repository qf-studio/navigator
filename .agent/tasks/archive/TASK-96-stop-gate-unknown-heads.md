# TASK-96: Stop gate — read-only shapes among the unknown heads

**Status**: ✅ Implemented — 2026-10-07 (A+B+C+D, both runtimes; released in v8.3.3)

## Origin

TASK-95 retired the heredoc bucket and left "unknown-head read-only calls" as the remaining
over-fire source. `scripts/stop_gate_replay.py --days 4` (745 Bash calls, 467 mutating) with
one candidate rule per blame head:

| Rule | Calls | Verdict |
|---|---|---|
| `2>/dev/null;` — redirect target captured as `/dev/null;` | 14 | **classifier bug** |
| `make <target>` where target contains `test\|check\|typecheck\|validate` | 26 | relax-direction, see open question |
| `claude plugin list\|validate\|test` | 8 | read-only, outside the tree |
| `claude plugin update` | 8 | writes the plugin cache, never the tree |
| `(cd …)` subshells, `{ …; }` groups | 8 | parser gap: the `(` / `{` is read as a head |
| `awk '…'` with no `>` anywhere in the segment | 7 | read-only |
| `name() { …; }` function definitions | 6 | parser gap: `q()` is read as a head |
| `gh run watch\|view\|list` | 5 | read-only |
| `python3 -m json.tool` | 3 | read-only |
| `sed` without `-i` | 0 this window | read-only by construction |
| `python3 - <<EOF`, `python3 -c`, `python3 script.py` | 198 | stay mutating (not classifiable by head) |

## Change

**A. Redirect targets end at `;`, `&`, `|` or whitespace** (bug). `_REDIRECT_RE` captures
`\S+`, so `2>/dev/null;` yields `/dev/null;` ≠ `/dev/null` and the call is a write. Strip
trailing `;&|` from the captured target before the `/dev/null` / `&` check. Both runtimes;
fixture `bash_devnull_semicolon`.

**B. Transparent structure heads.** A segment that starts with `(`, `{`, or `name() {` is
classified by what follows: strip the opener (and a trailing `)` / `}` / `; }`) and
re-classify. A subshell that runs `rm` stays mutating; `(cd x && git status)` reads as
read-only. Fixtures `bash_subshell_ro`, `bash_group_mut`, `bash_func_ro`.

**C. New read-only pairs and heads.**
- `READONLY_GH_SUBCMDS` += `run watch`, `run view`, `run list`.
- New `READONLY_CLAUDE_SUBCMDS` = `plugin list`, `plugin validate`, `plugin test`,
  `plugin update` (cache only). `plugin install|uninstall|enable|disable` stay mutating: they
  can rewrite a project `.claude/settings.json` (seen on `anthropya`, 2026-10-07).
- `python3 -m json.tool` → read-only (the only `python3` form that is).
- `sed` → read-only unless `-i` is present (the existing `-i` rule already runs first).
- `awk` → read-only unless the raw, unmasked segment contains `>` (an in-program
  `print > "file"` writes; the quote mask would hide it, so check before masking).

**D. `make` targets — open question.** Treating `make X` as read-only when `X` matches
`test|check|typecheck|validate` flips 26 calls here, but a `make check` in another repo may
format files. This is the first relax-direction rule for the mutating verdict since TASK-71
set "over-fire only". If accepted: pattern-gated, never `lint|format|build|install`, and the
tree digest still catches a real write on the next Stop.

## Result (2026-10-07)

All four changes shipped, D included (the go came without the `make` exclusion). Replay of
the same four-day window: mutating 474 of 760 calls before, 419 of 776 after (the window
grew by this session's own calls); none of the flipped calls writes the tree. Shapes now
read-only: `2>/dev/null;`, `(cd x && git status)`, `{ ls; }`, `q() { ls; }`, `gh run
watch`, `claude plugin list|validate|test|update`, `python3 -m json.tool`, `awk` without
`>`, `make` with only test/check/typecheck/validate targets. A test-only turn (`make test`)
is no longer a task action, so two derived-indicator tests pair the run with an Edit and
one new test pins the silence. `make` targets skip `VAR=x` and redirect words; the `$1 > 3`
comparison inside an awk program still reads as a write (over-fire only).

Tests: Python +22 read-only / +22 mutating parser cases, +1 op test; kit +2 direct tests and
+8 transcripts with every stop-op parity case regenerated (159 kit tests).

## Expected effect

A+B+C flip about 45 of 467 mutating calls in this window (10%); D adds 26 (16% total).
None of the flipped calls writes the tree; the replay script reports the table after the
change.

## Won't do

`python3 -c`, `python3 script.py`, `python3 - <<EOF` (198 calls): the program body decides,
and a body heuristic (no `open(..,'w')`, no `write_text`, …) is under-fire territory. Stays
the over-fire-only design.

## Verify

- Python `ReadonlyBashParserTest` +10 cases (A, B, C); kit fixtures regenerated; parity green.
- `python3 scripts/stop_gate_replay.py --days 4` before/after: mutating 467 → ~420 (→ ~395 with D).
- Live: a turn of `(cd hooks/ops && python3 -m unittest …) 2>/dev/null; gh run view …` ends
  without a forced continuation.

## Refs

- `hooks/ops/stop_completion.py` `_REDIRECT_RE` (:134), `_bash_readonly` (:343-412),
  `READONLY_GH_SUBCMDS` (:117); `hooks/mod/lib/stop-bash.ts` (`REDIRECT` :36, `bashReadonly` :75)
- `scripts/mod_fixtures/stopops.py`, `hooks/mod/tests/stopops.test.ts`
- `scripts/stop_gate_replay.py` (TASK-95)
