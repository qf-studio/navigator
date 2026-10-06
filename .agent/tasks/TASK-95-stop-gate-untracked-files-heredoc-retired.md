# TASK-95: Stop gate — `code_committed` ignores untracked files; heredoc bucket retired

**Status**: 📐 Plan — 2026-10-06 (research done, awaiting confirmation)

## Origin

Planned as "heredoc-aware Bash classifier", the bucket TASK-94 named next (178 of 385
mutating calls carried a heredoc). The research pass replayed three days of this repo's
transcripts (685 Bash calls, 429 mutating) and bucketed every mutating call by the first
segment that trips the classifier, with heredoc bodies stripped first:

| Blame head | Calls | Real write? |
|---|---|---|
| `python3 - <<'EOF'` | 134 | yes in 24 of 25 sampled bodies (`write_text`, `sed -i`, `git`) |
| `sed -i` | 30 | yes |
| `git add` / `git push` | 41 | yes |
| `cat > file <<'EOF'` | 28 | yes (the `>` is caught on the command line) |
| `python3 -c` / `python3 script.py` / `python3 -m` | 49 | mostly no (counting scripts, graph queries) |
| `make mod-test` / `mod-gen-check` / `mod-typecheck` | 21 | no |
| `claude plugin list/update`, `gh run`, `awk`, `tail \| python3 -m json.tool` | 29 | no |
| only a heredoc body / redirect, no mutating head | 14 | mixed |

Masking heredoc bodies flips **0** of the 199 heredoc calls to read-only: every heredoc
either feeds an interpreter (`python3 -`, mutating by the unknown-head rule, and in
practice a real write) or follows a `>` redirect. TASK-94's count was of heredocs among
mutating calls, not of over-fires. The bucket is retired.

The reject log (13 `stop_completion` entries) shows the actual defect instead: every entry
has `met: 1` and `code_committed` unmet, including turns that ended in `git commit && git
push`. `_git_clean` runs `git status --porcelain` and treats any output as dirty; this repo
keeps `.agent/marketing/` untracked on purpose, so the tree is never "clean" and
`code_committed` can never be met here. `MIN_HEURISTICS` is 2 and `ticket_closed` is always
met without a PM tool, so a working `code_committed` alone would have satisfied the gate on
each committed turn.

## Change

**A. `code_committed` ignores untracked files** (both runtimes). `git status --porcelain
--untracked-files=no`: a tree whose only noise is untracked paths counts as committed. An
untracked file the turn itself created still shows up through the `file_paths` /
mutating-Bash evidence, and a modified tracked file still dirties the tree. Parity fixture:
`git_untracked_only` → clean; `git_modified` → dirty.

**B. Bash-driven `.md` edits count as `docs_updated`.** `file_paths` only sees Edit/Write
inputs. A mutating Bash command whose text names a `*.md` path (`sed -i … X.md`,
`python3 - <<'EOF'` with `Path("X.md")`) sets `docs_updated`. Indicators only relax the gate,
so a false positive here cannot cause an under-fire on a real write (the mutating verdict is
untouched); it only stops a forced continuation on a turn that did update docs.

**C. Test targets.** `TEST_CMD_RE` gains `make (test-all|mod-test)` so a kit run counts as
`tests_passing`. (`make mod-gen-check` is a consistency check, not a test; left out.)

**D. Retire the heredoc plan.** Record the measurement in this doc and a knowledge-graph
learning: "heredocs among mutating calls ≠ over-fires; bucket by blame head with bodies
stripped before naming a next target."

**E. Keep the replay script.** Move `/tmp/measure.py` into `scripts/stop_gate_replay.py`
with the blame-head bucketing above, so the next bucket claim comes with the same table.

## Won't do

- Interpreter heads (`python3 -c`, scripts, `make`, `awk`, `gh run`, `claude plugin`):
  49 + 50 calls, all read-only in practice, all unknown heads. Allowlisting `awk`, `gh run
  (watch|view|list)` and `claude plugin list` is cheap and over-fire-only; `python3 …` and
  `make` are not classifiable by head. Separate decision; not in this task.
- Heredoc body masking. Zero measured benefit.

## Verify

- Python: `_git_clean` tests for untracked-only vs modified; `_derive_indicators` tests for a
  Bash `.md` edit and for `make mod-test`.
- Kit: parity fixtures regenerated (`scripts/mod_fixtures/stopops.py`), `make mod-gen-check
  mod-test mod-typecheck`.
- Replay: `python3 scripts/stop_gate_replay.py --days 3` prints the blame-head table; the
  13 logged rejects re-evaluated with A+B: expected ≥ 10 would not fire (the committed
  turns), the research-only ones already fixed by TASK-92/8.2.8.
- Live: a turn that edits a `.md` via `sed -i` and commits ends without a forced
  continuation while `.agent/marketing/` stays untracked.

## Refs

- `hooks/ops/stop_completion.py` `_git_clean` (:492), `_derive_indicators` (:528),
  `TEST_CMD_RE` (:85), `MIN_HEURISTICS` (:74)
- `hooks/mod/ops/stop_completion.ts` `gitStatus` (:25), indicators (:106-115)
- `scripts/mod_fixtures/stopops.py`, `hooks/mod/tests/stopops.test.ts`
- `.agent/tasks/archive/TASK-94-bash-classifier-quote-aware.md` (the bucket claim)
- `.agent/.nav-rejects.jsonl` (13 entries, all `met: 1`)
