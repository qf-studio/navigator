# TASK-70: Invisible exit signals + read-only Bash false-fire

**Status**: ✅ Implemented — 2026-07-11

## Context

Two dogfood findings from live v7 use (2026-07-10/11):

1. **Protocol noise**: the `nav-signal:v3:{...}` exit line the stop_completion gate
   requires was fully visible in assistant replies — end users should never see
   machine-readable protocol. Live experiment (2026-07-11): HTML comments ARE hidden by
   the GFM renderer in **assistant output** (user confirmed "didn't see them"). This is
   a different channel from hook block reasons, which render as plain text and showed
   comments literally (the failed Tier-1 sentinel bet, 57e8bd4) — per-channel verdicts,
   consistent with mem-035 discipline.

2. **False-fire on inspection turns**: `stop_completion` fired "this turn mutated the
   codebase" twice on turns that only ran `grep`/`ls`/`git status`. Root cause:
   `stop_state.TASK_ACTION_TOOLS` counts `Bash` wholesale, so any Bash tool_use made the
   turn "mutating" (the mem-037 guard was too coarse).

## Implementation

`hooks/nav_hook_lib/signals.py`:
- `_V3_LINE` accepts an optional HTML-comment wrapper:
  `<!-- nav-signal:v3:{...} -->` (spacing/indent/CRLF tolerated; truncated wrapper
  still parses; prose sharing the line still disqualifies). Bare lines unchanged.

`hooks/ops/stop_completion.py`:
- `READONLY_BASH_CMDS` + `READONLY_GIT_SUBCMDS` allowlists and `_bash_readonly()`:
  a command is read-only iff every `&&`/`||`/`;`/`|`/newline segment starts with an
  allowlisted head (git resolved by subcommand). Unknown → mutating (over-fire beats
  missed writes).
- `_turn_mutating()`: vocabulary stays anchored to `stop_state.TASK_ACTION_TOOLS`;
  a Bash-ONLY action turn is mutating only if some command is not read-only.
- `_reason()` now instructs the model to emit the exit signal comment-wrapped, so
  forced-continuation recoveries are also invisible.

Behavioral convention (model side): emit the exit signal ONLY when the gate challenges
a turn or a loop genuinely exits — never defensively on every turn — and emit it
comment-wrapped: `<!-- nav-signal:v3:{"type":"exit","reason":"..."} -->`.

## Acceptance Criteria

- [x] Comment-wrapped v3 lines parse (spacing, indent, CRLF, truncated-wrapper,
      prose-on-line negative case) — `test_signals.py`.
- [x] Comment-wrapped exit signal satisfies the Stop gate — `test_stop_completion.py`.
- [x] Read-only Bash turns (grep/ls/find/git status/git log, incl. pipes and `&&`)
      never force a continuation — PERMANENT regression tests.
- [x] Mutating Bash (`rm`, `git commit`, unknown commands like `python3 x.py`) and
      file-tool turns still gate exactly as before.
- [x] `make test` green (7/7 suites).

## Verify

```
python3 -m unittest discover -s hooks/nav_hook_lib -p 'test_signals.py'
python3 -m unittest discover -s hooks/ops -p 'test_stop_completion.py'
make test
```

## Refs

- `hooks/nav_hook_lib/signals.py`, `hooks/nav_hook_lib/test_signals.py`
- `hooks/ops/stop_completion.py`, `hooks/ops/test_stop_completion.py`
- TASK-65 (evidence populator), mem-037 (non-mutating turn guard),
  57e8bd4 (hook-channel comments render literally — the contrasting verdict)
