# TASK-94: Bash read-only classifier ignores quotes

**Status**: ✅ Released — v8.3.1, 2026-10-05

## Origin

Stop-gate reject 2026-10-05 ~19:50: a turn whose Bash was `for f in …; do printf "%s | %s\n" …`
counted as mutating. Replaying the turn: the `|` inside the quoted format string split the
command into a segment whose head was `%s\n"`, unknown, therefore mutating.

## Research (navigator-research, 2026-10-05)

- Neither classifier parses quotes at any step (`hooks/ops/stop_completion.py:296-364`,
  `hooks/mod/lib/stop-bash.ts`). Order today: peel `$(…)`/backtick substitutions → scan
  redirects on the raw text → split segments on `|| && ; | \n` → whitespace-split tokens →
  head rules. The code comment at `stop_completion.py:132` already admits "quoted '>' may
  over-fire".
- Three days of transcripts in this repo: 620 Bash calls, 522 classified mutating. Masking
  the contents of single- and double-quoted spans before the redirect and segment scans
  flips 137 of the 522 to read-only. None of the 137 is a real write (checked against a
  known-mutator regex, heredocs, redirect targets). Most are `\|` alternations in grep
  patterns, `--jq '… | …'` and quoted echo labels.
- 178 of the remaining 385 are heredocs (`python3 - <<'EOF'`, `cat > f <<EOF`); their heads
  are mutating anyway. Heredoc body awareness is out of scope here.
- `{ a; b; }` groups, `( a | b )` subshells and `$'…'` quoting are also unhandled; `{`, `(`
  become heads. Out of scope; noted below.
- Prior rule (TASK-71, 85, 90, 92): unknown stays mutating, over-fire only, never under-fire.

## Design

**One masking step, same place on both runtimes.** After substitutions are peeled and before
the redirect scan and the segment split, replace the contents of every quoted span with a
placeholder of the same length, keeping the quote characters:

- `'…'` single quotes: no escapes inside.
- `"…"` double quotes: `\"` and `\\` are consumed, not terminators.
- `$'…'` ANSI-C quotes: treated as single-quoted.
- An unterminated quote masks to the end of the string (bash would not run that line).
- Substitutions are peeled first, as today, so `"$(ls | wc)"` is still recursed.

Heads and flags are never inside quotes, so the git/gh/curl/sed rules and the allowlist see
the same tokens as before. The redirect rule sees `> "xxxx"` as a non-`/dev/null` target and
keeps it mutating. `sh -c "rm x"`, `bash -c`, `eval`, `xargs` keep their unknown heads.

**Why this is over-fire-safe.** Masking can only hide text that was inside quotes. A quoted
mutating word is an argument, not a command head, unless the head is an interpreter, and
every interpreter head (`sh`, `bash`, `eval`, `python3`, `xargs`, …) is unknown and stays
mutating. A quoted redirect target keeps the redirect mutating. Nothing that was read-only
can become mutating.

**Parity.** `_mask_quotes` in `stop_completion.py`, `maskQuotes` in `stop-bash.ts`, byte-same
behavior asserted by new fixture transcripts.

## Change

- [x] `_mask_quotes` / `maskQuotes` + call site; update the L132 comment.
- [x] Python tests: READONLY gains `grep "a\|b" f | head`, `grep ">" f`,
      `gh pr view 1 --jq '.a | .b'`, `printf "%s | %s\n" a b`, `echo $'a|b'`,
      `echo "unterminated | x`; MUTATING gains `echo "x" > out.txt`, `sh -c "ls"`,
      `echo "a" > "$F"`, `bash -c "rm x"`.
- [x] Kit test (same cases) and fixtures `bash_quoted_ro`, `bash_quoted_mut` in
      `scripts/mod_fixtures/stopops.py`; regenerate; `make mod-gen-check mod-test`.
- [x] Re-run the three-day replay (`/tmp/measure.py` from the research run, or the same
      logic in `scripts/`): expect ~137 flips, 0 true writes. Record the numbers here.
- [x] Release 8.3.1 (patch), site stop-completion page one sentence.

## Result (2026-10-05)

Three-day replay of this repo's transcripts, same script as the research run:

| Measure | Before | After |
|---|---|---|
| Bash calls | 620 | 624 |
| Classified mutating | 522 | 388 |

134 verdicts flipped to read-only, none a real write (the research pass checked every
flip against known mutators, heredocs and redirect targets). Tests: Python +14 parser
cases, kit +1 (mask unit + the same cases), two parity transcripts (`bash_quoted_ro`,
`bash_quoted_mut`); 775 Python, 157 kit, all green.

## Won't do (this task)

Heredoc body awareness (178 calls, separate task); `{ }` groups and `( )` subshells; a
real shell parser. The over-fire-only rule stands.

## Verify

```
NAVIGATOR_MOD_OWNS= make test
make mod-gen-check mod-test mod-typecheck
```

## Refs

- `hooks/ops/stop_completion.py` `_bash_readonly`, `hooks/mod/lib/stop-bash.ts` `bashReadonly`
- `hooks/ops/test_stop_completion.py` `ReadonlyBashParserTest`, `hooks/mod/tests/stopops.test.ts`
- `scripts/mod_fixtures/stopops.py` `bash_*` transcripts
- TASK-71, TASK-85, TASK-90, TASK-92 (over-fire-only lineage)
