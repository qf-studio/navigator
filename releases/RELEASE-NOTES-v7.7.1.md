# Navigator v7.7.1 Release Notes — "Count What the Judge Does"

**Release Date**: 2026-09-23
**Type**: Patch — telemetry and eval tooling for the typed judge; no gating changes

## Summary

v7.7.0 put a typed judge behind the keyword scorers and measured it on 60 invented
prompts. This patch makes the judge measurable in use (TASK-80, workstreams A and B).

## Override telemetry

Runtime state gains a `judge` section (30-day TTL, cumulative like `tier1`): calls,
failures, last and max latency, and per axis — loop, complexity, task-shaped, ambiguity —
whether the judge **overrode** the keyword decision, **agreed** with it, or stayed
**undecided** inside the band. For the score axes "agreed" compares the decision side of
the threshold, not the raw number. Counters only; no prompt text ever enters state.

`nav stats` shows two lines:

```
judge: 86 calls / 1 failed · 499 ms last, 1271 ms max
judge axes: 4 overridden / 240 agreed / 15 undecided
```

The nav-stats skill report carries the same as a row.

## Real-session eval tooling

`scripts/judge_label.py` builds a labeled set from prompts you actually typed:

- `extract` walks local transcripts, keeps genuine user prompts (no tool results, hook
  feedback, slash-command echoes, or subagent transcripts), redacts key-shaped tokens,
  caps and deduplicates, samples across projects.
- `label` is one keystroke per prompt (`n` not a task, `d` small task, `t` substantial,
  `a` substantial and needs a brief, `l` loop). `sheet` / `import` do the same through a
  markdown file. `status` counts.
- The output is gitignored. It holds real prompts from private projects and must never be
  committed; only aggregate numbers belong in the repo. `scripts/judge_eval.py` skips
  unlabeled rows, so a partial set already produces numbers.

## First live read

Four days, 92 judged prompts across two projects: loop 91 agreed / 0 overridden,
complexity 81 agreed / 10 undecided, task 81 agreed / 4 overridden / 6 undecided. The
keyword heuristics are right almost every time on ordinary prompts; the judge's value is
in the tails, and no tail case occurred in the window. It stays opt-in and off by default.

## Also in this release

- TASK-79 marked released; docs site synced to 7.7.0 on 2026-09-19.
- Repository note: GitHub reports the repo moved to `qf-studio/navigator`; the old path
  redirects.
