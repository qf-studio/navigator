# Navigator v8.2.6 Release Notes

**Release Date**: 2026-10-05
**Type**: Patch — stop-gate over-fire on Bash-only turns (TASK-90)

## Fixed

- **Stop gate on `cd` and `/bin/ls`.** Every forced continuation on 2026-10-05 (3 of 3 in the
  reject log) came from a turn that only listed, read and ran `git status`. Two read-only
  heads were unknown to the classifier on both runtimes: `cd`, which leads almost every
  multi-step command, and `/bin/ls`, the absolute path a machine with `ls` aliased to eza
  uses. `cd` is now read-only; a head starting with `/` is reduced to its basename before the
  allowlist lookup, so `/bin/ls` is `ls` while `/usr/bin/rm` stays mutating and `./ls` never
  resolves.

Replaying the last two days of transcripts (483 Bash calls): 44 flip to read-only, all of them
listings, greps and `git status`. The over-fire-only rule from TASK-71 is unchanged.

Tests: Python `READONLY` / `MUTATING` replays (+9), kit `stopops` TASK-90 case (150 kit tests).
Task doc: `.agent/tasks/TASK-90-stop-gate-cd-and-path-heads.md`.
