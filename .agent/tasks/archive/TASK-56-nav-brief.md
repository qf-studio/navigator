# TASK-56: nav-brief — Intent-Brief Enforcement for Ambiguous Prompts

**Status**: ✅ Implemented — 2026-07-09 (shipped in v6.18.0)
**Created**: 2026-07-09
**Effort**: M (~3.25 days planned)

## Problem

The expensive failure mode is no longer context overflow — it's rework: ambiguous
task prompts ("add rate limiting to the API") get implemented on guessed scope,
then corrected over 2-4 exchanges. Corrections burn tokens on undo/redo, pollute
context with dead ends, and force mid-feature compacts.

## Solution

Front-load the negotiation. A new `UserPromptSubmit` hook scores each prompt for
**ambiguity** (a third axis, distinct from complexity), and — when a task-shaped
prompt scores at/above threshold — injects a compact instruction telling the
model to render a one-screen INTENT BRIEF (Goal/Scope/Approach/Limits/Verify/
Won't-do) pre-filled from knowledge-graph memories, ask max 2 open questions,
and wait for confirmation before touching files.

## Architecture

```
prompt → hooks/nav_brief.py (UserPromptSubmit, sibling of workflow_enforcer)
           ├─ skills/nav-brief/functions/ambiguity_scorer.py (pure, stdlib)
           ├─ shells out: skills/nav-graph/functions/memory_recall.py
           │    (--concepts from prompt tokens, 3s timeout, silent-skip)
           └─ exit 0 + stdout block (NEVER exit 2 — mem-034: exit 2 blocks
              the model entirely, defeating the feature)
model  → skills/nav-brief/SKILL.md (render brief, passthrough rules, drift)
```

Fixed design constraints (from research):
- New **sibling entry** in `plugin.json` UserPromptSubmit array; `workflow_enforcer.py` untouched.
- Scorer is a **third standalone module** (TASK-48 precedent: scorers stay separate).
- Config block `brief_hook: {enabled, ambiguity_threshold: 0.5, memory_budget_chars: 1200}`.
- Stateless in v1: "prompt answers a pending brief" handled model-side (SKILL.md).

## Scoring Design

Zero-out gates (→ 0.0, not task-shaped): questions (ends `?` / interrogative
first word), short confirmations (≤6 words, yes/ok/go-ahead family).
Base 0.5 on task-shaped verb; +0.2 vague-scope signal ("the API", "the codebase",
bare plurals); credits: file path −0.4, number −0.2, limiter word −0.2,
acceptance-criteria phrase −0.3. Clamp [0,1]. Word-boundary regex only.

## Work Packages

- [x] WP1: `skills/nav-brief/functions/test_ambiguity_scorer.py` + `ambiguity_scorer.py` (TDD)
- [x] WP2: `hooks/test_nav_brief.py` + `hooks/nav_brief.py` (TDD)
- [x] WP3: Register in `.claude-plugin/plugin.json` (hook + skill) + `.agent/.nav-config.json` `brief_hook` block
- [x] WP4: `skills/nav-brief/SKILL.md`
- [x] WP5: Composition case in `hooks/test_hooks_smoke.py` (both UserPromptSubmit hooks on same payload)
- [x] WP6: Docs — CLAUDE.md section, DEVELOPMENT-README hook table (9 hooks), CHANGELOG entry

## Expected Effect (hypotheses to validate)

| Metric | Now | Target |
|---|---|---|
| Corrections per substantial task | 2-4 | ≤1 |
| Tokens on rework | 15-30% | <5% |
| Time to first correct diff | — | +1 exchange (accepted cost) |

Compounding bet: brief edits feed the knowledge graph → later briefs pre-fill
→ open questions trend to 0.

## Non-Goals (v1)

- Statefulness across turns (pending-brief tracking)
- `strict_block` hard gating
- Stop-hook measurement counter (deferred — mem-037 composition risk, no consumer yet)
- Corrections-per-task OTel metrics
- Prompt rewriting

## Verification

- `python3 -m unittest` green for both new test files + zero regressions in
  `test_workflow_enforcer.py` / `test_hooks_smoke.py`
- Manual: ambiguous prompt renders brief; question/confirmation/file-scoped
  prompts stay silent
