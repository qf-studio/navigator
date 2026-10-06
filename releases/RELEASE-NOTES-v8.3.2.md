# Navigator v8.3.2 Release Notes

**Release Date**: 2026-10-06
**Type**: Patch — stop gate `code_committed` and untracked files; heredoc bucket retired (TASK-95)

## Fixed

- **A committed turn no longer reads as uncommitted because of untracked files.** The
  `code_committed` indicator ran `git status --porcelain` and treated any output as a dirty
  tree. A repo that keeps a scratch directory untracked on purpose could therefore never meet
  it: all 13 stop-gate rejects in this repo's log had `code_committed` unmet, including turns
  that ended in `git commit && git push`. Both runtimes now skip `??` lines unless the turn's
  own file evidence names that path, so a file the turn created and left untracked still
  counts as uncommitted work, and a modified tracked file still dirties the tree.
- **Docs edits made through Bash count.** A mutating Bash command that names a `*.md` path
  (`sed -i … README.md`, a `python3 -` heredoc that writes one) sets `docs_updated`; Edit and
  Write paths counted already. Indicators only relax the gate; the mutating verdict is
  unchanged.
- **`make mod-test` is a test run** for `tests_passing`, next to `make test`, `pytest` and
  `unittest`.

## Retired

TASK-94 named heredoc bodies as the next over-fire bucket (178 of 385 mutating calls). A
replay of three days of Bash calls, bucketed by the first segment that trips the classifier
with heredoc bodies stripped, shows masking those bodies flips 0 of 203 heredoc calls: each
one feeds `python3 -` (an unknown head, and in practice a real write) or follows a `>`
redirect. The bucket is dropped. `scripts/stop_gate_replay.py` keeps the method so the next
bucket claim comes with the same table.

Tests: Python +8 (`GitCleanTest`, derived indicators), kit +1 git mode and +4 transcripts
with every parity case regenerated; 157 kit tests.
Task doc: `.agent/tasks/TASK-95-stop-gate-untracked-files-heredoc-retired.md`.
