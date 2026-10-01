# Navigator v7.9.0 Release Notes — "Say the Word"

**Release Date**: 2026-10-01
**Type**: Minor — ADHD mode (TASK-82) and the removal of the deprecated multi-Claude orchestration

## Summary

Two things. A per-person switch that reshapes replies for an ADHD reader and flips on or
off mid-session by saying so, with zero model turn. And the end of the multi-Claude shell
orchestration that was deprecated in v6.15: native Claude Code Workflows, the Agent tool
and Pilot own that job now, so the skills, scripts, templates and config block are gone.

## What's New

### ADHD mode (TASK-82)

Say `adhd mode on`, `adhd mode off` or `adhd mode` at any prompt. The new `prompt_adhd` op
answers the phrase itself through the same `decision: block` channel as Tier-1 (no model
turn) and writes a personal switch to `~/.config/navigator/adhd-mode.json`
(`NAVIGATOR_CONFIG_HOME` overrides the directory). The switch follows you across repos and
takes effect on the next prompt, no restart.

While on, every prompt carries a short declarative rule block as injected context: one next
action first, time-critical items first with the deadline in bold, bullets over prose, lists
capped at five, numbered steps with "step k of n", flat tone for errors, no preamble, one
sub-two-minute closing action. Error output, test results, explanations you asked for and
warnings before destructive actions are never shortened. While off, the rules exist nowhere
in the context. Subagents and the Pilot executor never see the block.

- Config block `adhd_mode`: `enabled` (seeds `true`, only makes the machinery available)
  and `on` (`true`/`false` pins it for a repo in `.nav-config.json` or the `.local`
  override; `null` defers to the person). Resolution: repo pin > personal switch > off.
- `nav-features`: new `adhd_mode` row. `enable adhd_mode` writes the personal file, not
  the repo; `--local` pins `adhd_mode.on` in `.nav-config.local.json`.
- Session start prints `ADHD mode: on (personal switch ...)` when a switch is set.
- Lib: `nav_hook_lib.adhd` (phrases, resolution, rule block) and `nav_hook_lib.personal`
  (per-person JSON files under the config home).
- Design and reference review: `.agent/tasks/TASK-82-adhd-mode.md`. The rule set builds
  on the user's own rules plus `ayghri/i-have-adhd`.

### Research agents on Sonnet (documented)

`navigator-research`, `task-planner` and the deep-research fetcher already declare
`model: sonnet` in their frontmatter; on Claude Code 2.1.284 that resolves to Sonnet 5.5.
CLAUDE.md now says so. No behaviour change.

## Breaking Changes

**Multi-Claude orchestration removed** (deprecated since v6.15.0, TASK-25). Deleted:
`nav-multi` and `nav-install-multi-claude` skills, `scripts/navigator-multi-claude*.sh`
and their helpers (`sub-claude-monitor.sh`, `resume-workflow.sh`,
`multi-claude-dashboard.sh`, `install-multi-claude.sh`, `simple-poc.sh`, `POC-LEARNINGS.md`),
`templates/multi-claude/`, both multi-Claude SOPs, memory mem-020, and the `multi_agent`
config block (DEFAULTS, migrator, tier-1 feature list, `nav-features` table). A stale
`multi_agent` block in an existing `.nav-config.json` is ignored. Use the Workflow and Agent
tools, or Pilot, for parallel and multi-phase work.

## Tests

- 34 new tests: `test_personal.py`, `test_adhd.py`, `test_prompt_adhd.py` (incl. the full
  dispatcher subprocess path: toggle on, block injected, toggle off), session-start notice,
  `nav-features` personal-switch CLI.
- Registry, config-defaults, migrator and golden-fixture suites updated for the new block
  and the removed one. `make test` green.

## Getting Started

```bash
claude plugin update navigator@navigator-marketplace   # then restart Claude Code
```

Then, in any Navigator project: `adhd mode on`.
