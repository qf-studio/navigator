# TASK-65 — stop_completion completion-indicator populator

**Status**: ✅ Implemented — 2026-07-10

## Context

The Stop-event forced-continuation gate (`hooks/ops/stop_completion.py`) blocks a
mutating-but-unfinished turn until enough completion indicators are met
(`met >= MIN_HEURISTICS`, and `MIN_HEURISTICS == 2`). It read those indicators from
`ctx.state['completion']['indicators']` — but **no op ever wrote that key**. The dict was
always empty, so every mutating turn scored `0/6` and the gate force-continued *every*
mutating turn once (a live bug the user hit). The fix derives indicators from observable
turn evidence and feeds them into `_evaluate_heuristics`, merged with any explicit state
indicators (a state `True` still wins, so other writers keep counting).

## Acceptance Criteria

- [x] `_turn_scan` also collects, for the ending turn: file paths from
  Edit/Write/MultiEdit/NotebookEdit `input.file_path`/`input.notebook_path`, and Bash
  commands paired with whether the following `tool_result` was `is_error`.
- [x] `_derive_indicators` maps the six vocabulary names from observable evidence:
  `code_committed` (git tree clean), `tests_passing` (test command, not errored),
  `docs_updated` (`*.md` touched), `marker_created` (`/.context-markers/` path),
  `ticket_closed` (PM == `none`), `code_simplified` (never — no reliable signal).
- [x] Derived indicators OR'd with explicit state indicators; state `True` wins.
- [x] Every existing breaker preserved byte-for-byte: single-shot `stop_fuse`,
  `held_count` cap, mem-037 non-mutating guard, `stop_hook_active`, nav-signal v3 exit
  short-circuit, unconditional `PILOT_EXECUTOR` disable, `continue_enabled`/`enabled`
  kill switches. The `met/6 + unmet list` message is unchanged (now shows real counts).
- [x] Tests prove each of the six rules independently; committed+tested turn yields
  (no continue); uncommitted mutating turn still continues; breaker/kill-switch/fuse
  cases still pass. `make test` green.

## Implementation

`hooks/ops/stop_completion.py`:
- `_turn_scan` now returns `(text, tools, evidence)` where `evidence` =
  `{"file_paths": [...], "bash": [(command, is_error), ...]}`. Bash commands are matched
  to their result's `is_error` by `tool_use_id`; an unmatched command defaults to
  not-errored. The turn-span walk (back to the last genuine user prompt) is unchanged;
  tool_result plumbing user entries are now inspected for `is_error` before being skipped.
- `_collect_tool_evidence(name, block, file_paths, bash_uses)` extracts a file path
  (`FILE_PATH_TOOLS`) or a `(id, command)` (Bash) from one tool_use block.
- `_git_clean(root)` runs `['git','status','--porcelain']` at `hio.project_root(payload)`
  with a 2s timeout; empty stdout AND rc 0 → True; any failure/timeout → False.
- `_derive_indicators(evidence, cfg, payload)` returns only the True indicators;
  `TEST_CMD_RE = r'\b(make test|pytest|(python3?\s+-m\s+)?unittest)\b'` gates
  `tests_passing`. `ticket_closed` is True only when `project_management == 'none'`;
  `code_simplified` is never derived (documented in the docstring).
- `run()` builds `filtered` by OR-ing `state_ind.get(name)` with `derived.get(name)` over
  the full vocabulary before calling `_evaluate_heuristics`.

## Verify

- `cd hooks/ops && python3 -m unittest test_stop_completion` → 46 tests, OK.
- `make test` → exit 0, all unit tests passed.

New/updated tests (`hooks/ops/test_stop_completion.py`): `DerivedIndicatorTest` covers each
of the six rules independently (plus failing/non-test command negatives, notebook_path,
PM on/off, state-wins and state+derived merge, and the non-mutating guard over evidence),
the committed+tested-yields and uncommitted-still-continues acceptance cases. Pre-existing
count-exact cases pin `project_management` via a new `pm_cfg()` helper (isolating the
`ticket_closed` derivation); the base `setUp` patches `_git_clean` → False for determinism
(the subprocess dispatch tests run their own git in a throwaway non-repo dir).

## Done

- `hooks/ops/stop_completion.py` — evidence scan + `_git_clean` + `_derive_indicators` +
  merge wiring.
- `hooks/ops/test_stop_completion.py` — `DerivedIndicatorTest` + helpers; three legacy
  count cases isolated via `pm_cfg()`.

## Refs

- Bug: `completion.indicators` never written → gate always `0/6` → force-continue.
- mem-034 (no transcript text in reason / stderr), mem-037 (non-mutating turns never
  continue), mem-051 (`decision:block` is the continuation channel).
- Vocabulary source: `skills/nav-loop/functions/exit_gate.py` (`evaluate_exit`).
