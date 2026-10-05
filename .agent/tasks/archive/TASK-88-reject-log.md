# TASK-88: Reject log — every refusal the runtime makes, one line, greppable

**Status**: ✅ Implemented — 2026-10-05 (shipped in v8.2.0)
**Origin**: a comment on the v8 post: "the interception point is worth more as a gate … the
reject log ends up the useful artifact; that's where your real failure modes show up."

## Research (2026-10-04)

Navigator already gates deterministically at the interception points; what it lacks is the
record. Refusal points in the mod (same ops in Python):

| Op | Event | Refusal | Recorded today |
|---|---|---|---|
| `read_guard` | tool.call Read | deny at the 5th repeated Read (strict) | `reads.turn_count` only |
| `prompt_gate` | prompt.submit | exit 2 when a loop prompt follows a skipped check (strict) | `turn.signals.check_shown` |
| `stop_completion` | classic.Stop | `decision: block` forced continuation | `completion.held_count` |
| `prompt_tier1`, `prompt_adhd` | prompt.submit | answer without a model turn — not a refusal | `tier1.hits` |

Crashes have a record (`meta.op_errors` + `.agent/.nav-dispatch-health.json`); refusals have
tallies, no reasons, no time. The 2026-10-03 stop-gate over-fire (six blocks on read-only turns,
TASK-85) was diagnosed from the transcript; a reject log would have shown it in one `grep`.

Out of scope here, noted from the same comment: a write-scope guard (deny Edit/Write outside the
repo root, args that don't resolve). Different feature; valuable under Pilot. 8.3 candidate.

## Plan

1. **One append point per runtime.** `hooks/mod/runner.ts` `runOps` already knows a blocking
   result (`isBlocking`); `nav_hook_lib/runtime.py` has `gate_blocked` at the same spot. Append
   one JSON line to `.agent/.nav-rejects.jsonl`:
   `{ts, session, event, op, tool?, reason, evidence}` — reason secret-redacted through the
   sentinels emitter, evidence = the op's own summary (read_guard: path + count; stop_completion:
   indicators met/unmet + mutating tools; prompt_gate: trigger phrase, redacted).
2. **Bounded**: keep the last 500 lines (rewrite on append past 600). Gitignored by `nav-init`.
3. **Config**: `reject_log.enabled`, default **on** — it observes, never blocks, so it may ship on.
   Off under nothing; Pilot writes it too (it is the autonomous case that needs it most).
4. **Pane**: with `d`, one line under reads — `rejects today 3 · last 14:03 stop_completion:
   read-only turn` — and `R` opens the last eight lines.
5. **Parity**: the line format is generated-fixture tested like the ops (`scripts/gen_mod_data.py`
   gets a `rejects` corpus); Python and mod produce byte-identical lines for the same refusal.

## Verify

Kit + Python tests for each refusal point; replay the 2026-10-03 over-fire corpus (stopops
fixtures) and assert six lines with `evidence.mutating_tools: ["Bash"]`; live: trip the read
guard on purpose and `tail .agent/.nav-rejects.jsonl`.

## Size

Small: ~150 lines across runner.ts / runtime.py / one pane line / nav-init gitignore, plus tests.
Half a day with parity fixtures.

## Implementation (2026-10-05)

- **Shape**: a refusing op attaches `reject: {reason, evidence}` to its blocking result
  (`ops/read_guard.py`, `ops/prompt_gate.py`, `ops/stop_completion.py` and their TS mirrors).
  The runtime strips the key before the merge and appends the line: `runtime._log_reject`
  (Python) and `logReject` in `hooks/mod/runner.ts` (mod) — one append point each, as planned.
  Line builder + bounded append live in `nav_hook_lib/rejects.py` / `hooks/mod/lib/rejects.ts`.
- **Line**: `{ts, session, event, op, tool?, reason, evidence, suppressed?}`; compact separators
  so Python and the mod emit identical bytes (`scripts/mod_fixtures/rejects.py` →
  `tests/fixtures/rejects.gen.ts`, asserted in `rejects.test.ts`). `suppressed: true` marks a
  refusal computed under Pilot that the merge belt then stripped — the record survives even
  though the block does not.
- **Evidence**: read_guard `{path, count, threshold}`; stop_completion
  `{met, unmet, mutating_tools}` (tools ∩ `TASK_ACTION_TOOLS`, so a Bash-only over-fire reads
  `["Bash"]`); prompt_gate `{trigger}`.
- **Config**: `reject_log.enabled`, default on (observes, never blocks). Gitignored here and by
  `nav-init`.
- **Pane**: under reads (with `d`): `rejects today N · last HH:MM <op>`; `l` opens the last
  eight lines. Hotkeys must be a lowercase letter, so `l`, not the planned `R`.

### Deviations from the plan

- The matched loop trigger goes into `evidence.trigger` unredacted. The plan said "redacted",
  but the file never enters the model's context (the pane renders it; stderr stays redacted),
  and a redacted trigger would make the log useless for the misfire it exists to catch.
- Pane hotkey `l` instead of `R` (engine refuses uppercase).

### Verify

- `make test` (unset `NAVIGATOR_MOD_OWNS` in a session with the mod loaded), `make mod-test`
  (146), `make mod-gen-check`, `make mod-typecheck`, `make mod-validate`: all green.
- Live Python path: a Stop with an Edit in the transcript through `hooks/nav_dispatch.py`
  wrote one line with `mutating_tools: ["Edit"]` to `.agent/.nav-rejects.jsonl`.
- Pending: the mod path live needs the plugin reinstalled from this tree (the loaded 8.1.2 mod
  predates the change); the read-guard trip and the `l` panel are covered by the kit.
