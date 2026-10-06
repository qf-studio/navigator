# TASK-92: Stop gate over-fires on turns that only launch a read-only agent

**Status**: ✅ Released — v8.2.8, 2026-10-05

## Origin

Reject log 2026-10-05 19:13: `stop_completion · mutating turn, 1/6 indicators met`, evidence
`mutating_tools: ["Agent", "Bash"]`. Replaying the turn: both Bash calls classify read-only;
the only other tool was `Agent` with `subagent_type: navigator:navigator-research`, whose
tool set is Read, Grep, Glob, Bash, LSP. Fourth stop-gate over-fire of the day (TASK-90
fixed the other three).

## Cause

`TASK_ACTION_TOOLS` lists `Task` and `Agent` unconditionally on both runtimes
(`hooks/ops/stop_state.py`, `hooks/mod/ops/stop_state.ts`). `_is_mutating` /
`isMutating` returns true as soon as any action tool other than Bash appears, so a
research-only subagent is treated like an Edit.

## Change

- [x] Evidence builders record each Agent/Task call's `subagent_type`.
- [x] A known read-only agent type (Explore, Plan, claude-code-guide, navigator-research,
      task-planner, with or without the `navigator:` prefix) does not count as a task
      action; unknown or omitted types stay mutating (over-fire only, TASK-71).
- [x] Parity fixtures: read-only agent turn → no block; general-purpose agent turn → block.
- [x] Release 8.2.8.

## Result

Replaying the 19:13 turn's evidence (`Agent` navigator-research + read-only Bash) through
`_turn_mutating` now returns not-mutating on both runtimes. Four new parity transcripts
(`agent_ro`, `agent_explore`, `agent_general`, `agent_ro_edit`); Python +3 tests, kit +1
(154 kit tests). Unknown or missing `subagent_type` still blocks.

## Verify

```
make test            # NAVIGATOR_MOD_OWNS unset
make mod-gen-check mod-test mod-typecheck
```

## Refs

- `hooks/ops/stop_completion.py` `_collect_tool_evidence`, `_is_mutating`
- `hooks/mod/lib/stop-transcript.ts`, `hooks/mod/ops/stop_completion.ts`
- `scripts/mod_fixtures/stopops.py`
