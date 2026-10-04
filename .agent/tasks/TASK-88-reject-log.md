# TASK-88: Reject log — every refusal the runtime makes, one line, greppable

**Status**: 📋 Planned — 2026-10-04 (research done; not started)
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
