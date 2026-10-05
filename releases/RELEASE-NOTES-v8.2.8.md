# Navigator v8.2.8 Release Notes

**Release Date**: 2026-10-05
**Type**: Patch — stop-gate over-fire on read-only subagent turns (TASK-92)

## Fixed

- **Launching a research agent no longer counts as mutating the codebase.** The Stop gate
  treated every `Task`/`Agent` call as a task action, so a turn that only ran read-only Bash
  and launched `navigator-research` (Read, Grep, Glob, Bash, LSP) was forced to continue with
  1 of 6 completion indicators met. Both runtimes now record each agent call's
  `subagent_type`; when every agent in the turn is a known read-only type (Explore, Plan,
  claude-code-guide, navigator-research, task-planner, with or without the `navigator:`
  prefix) the agent tools leave the action set and the Bash evidence decides. Unknown or
  missing types stay mutating, so the gate can still over-fire but never under-fire.

Fourth stop-gate over-fire fixed on 2026-10-05 (TASK-90 covered `cd` and absolute-path heads).

Tests: Python +3 (`BreakerTest`), kit +1 and four new parity transcripts (`agent_ro`,
`agent_explore`, `agent_general`, `agent_ro_edit`); 154 kit tests.
Task doc: `.agent/tasks/TASK-92-readonly-agents-not-task-actions.md`.
