# TASK-66 — read_guard per-turn counter double-increments

**Status**: ✅ Implemented — 2026-07-10

## Context

Live observation: reading N non-allowlisted `.agent/` files in one turn drove the
read-guard per-turn counter to **2N** (turn_count 2, 4, 6, 8, 10, 12 for reads 1–6),
so the strict block fired on the **3rd** read (count 6 ≥ escalate_threshold 5) instead of
the 5th.

Root cause (evidence-based, not the reported framing): a single
`read_guard.run(ctx)` / dispatch increments `reads.turn_count` by **exactly 1** — the op
has one increment site (`_increment_counter`) and the existing unit + end-to-end
simulations confirm +1 per dispatch. The 2N only appears when **one Read tool-use fires
the `PreToolUse` surface twice** (dual hook wiring across the v6→v7 migration, or a harness
double-fire). The counter was keyed on the *dispatch*, not on the *unique Read tool-use*,
so a duplicated dispatch of the same Read advanced it a second time. Reproduced exactly:
two `runtime.dispatch("PreToolUse", …)` calls per read yield 2, 4, 6, 8, 10, 12 and a block
at read 3.

Fix: make the per-turn increment **idempotent per `tool_use_id`**. Real `PreToolUse`
payloads carry a stable `tool_use_id` (verified: `tests/golden/goldens/read_guard.json`,
captured verbatim from a live session, contains `"tool_use_id": "toolu_01NHm6y…"`). Each
qualifying Read is counted exactly once; a repeated dispatch of an already-counted id is a
no-op that re-evaluates the same threshold. Payloads with no id fall back to the v6
per-dispatch behavior (older harnesses that fire once), preserving prior behavior and the
goldens.

## Acceptance Criteria

- [x] Each qualifying (non-allowlisted, `.agent/`) Read increments `reads.turn_count` by
      exactly 1, even when its `PreToolUse` dispatch repeats within the turn.
- [x] The strict block fires when the count **reaches** `escalate_threshold` (the 5th
      qualifying read), not before.
- [x] Allowlist exemptions (`DEVELOPMENT-README.md`, `.nav-config.json`,
      `.user-profile.json`, `knowledge/graph.json`) still never increment.
- [x] 300s in-op staleness reset, deny-only exit-2 + sentinel stderr, and the
      Stop-reset-barrel coupling (`stop_state` overwrites `reads` → `{"turn_count": 0}`)
      are preserved.
- [x] Golden byte-parity (`tests/golden/test_parity.py::test_read_guard`) stays green.
- [x] Regression tests: K double-fired reads count K (not 2K); block first fires on the
      escalate-th unique read; duplicate dispatch is idempotent; allowlisted never counts.

## Implementation

`hooks/ops/read_guard.py`:
- Added `_tool_use_id(payload)` — returns the payload's `tool_use_id` (or camelCase
  `toolUseId`) as the dedup key, else `None`.
- `_increment_counter(ctx, stale_after_s, tool_use_id)` now tracks a bounded per-turn set
  `reads.seen_tool_uses` (cap `MAX_SEEN_TOOL_USES = 64`; duplicates arrive adjacently). A
  repeated `tool_use_id` returns the recorded count without re-incrementing; a new id (or
  `None`) increments by 1. The stale-window reset and the `reads` section shape are
  otherwise unchanged, so the `stop_state` reset barrel and 300s window keep working.
- `run()` passes `_tool_use_id(payload)` into the counter.

## Verify

```
cd hooks/ops && python3 -m unittest test_read_guard      # 28 tests OK
python3 -m unittest tests.golden.test_parity             # read_guard parity OK
make test                                                # full suite green
```

The end-to-end `DispatcherDoubleFireTest` double-fires each Read through
`runtime.dispatch` with real state persistence and asserts `turn_count == i` (never `2*i`)
and the first block at read 5.

## Done

Counter now represents unique Read tool-uses per turn and is immune to duplicate
`PreToolUse` dispatch; the block fires on the 5th qualifying read as designed.

## Refs

- `hooks/ops/read_guard.py`, `hooks/ops/test_read_guard.py`
- `hooks/nav_hook_lib/runtime.py` (single dispatch per event), `hooks/ops/stop_state.py`
  (reset barrel `reads.turn_count → 0`)
- `tests/golden/goldens/read_guard.json` (live payload proving `tool_use_id` presence)
