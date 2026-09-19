# Navigator v7.7.0 Release Notes — "Judge, Then Fall Back"

**Release Date**: 2026-09-19
**Type**: Minor — typed prompt judge behind the keyword scorers, opt-in

## Summary

Every prompt-time decision in the hook runtime was a keyword match: fourteen loop-trigger
phrases, weighted complexity keywords, an ambiguity base of 0.5 minus credits. Cheap,
deterministic, and wrong in ways a reader spots instantly. The example that prompted this
release: a subagent report whose section header read "F. Loop mode" put the session into
Loop Mode.

v7.7.0 adds a typed judge (TASK-79). With `judge.enabled`, one HTTP request per prompt to
TypeSafe's Jev — a model that returns probabilities for typed questions instead of text —
answers eight questions at once: is this a task, does it ask for autonomous iteration,
complexity on a four-level rubric, ambiguity on three, and whether scope, limits,
approach and verification are stated. Each axis overrides its keyword heuristic only when
the answer is decisive. Undecided axes, a timeout, a missing key or any error leave the
heuristic in charge, byte for byte.

## Measured

60 labeled prompts, including the observed false-fires (`hooks/nav_hook_lib/fixtures/`):

| Axis | Heuristic | Blended |
|---|---|---|
| Tier (DIRECT / TASK / LOOP) | 38/60 | 53/60 |
| Task-shaped (brief gate) | 43/60 | 54/60 |
| Ambiguous (brief needed) | 47/60 | 50/60 |

Median latency 662 ms, about 700 input tokens per prompt, roughly $0.00003 each. The
"Loop mode" header scores 0.14 on the loop question and is silenced. Thresholds ship from a
nine-cell sweep over the recorded responses, replayable with
`python3 scripts/judge_eval.py --replay hooks/nav_hook_lib/fixtures/judge_eval_recorded.json`.

## What ships

- `hooks/nav_hook_lib/judge.py` — stdlib `urllib` client. Redacts key-shaped tokens and
  head-caps the prompt before it becomes request state; never raises, never writes
  stderr; `for_ctx` caches one call per dispatch for both prompt ops.
- `scoring.detect_workflow`, `score_ambiguity`, `score` take `judgment=`; `None` is the
  exact pre-7.7 behavior, so the v6 parity snapshots did not move.
- `prompt_gate` and `prompt_brief` consume it. The WORKFLOW CHECK block carries one
  extra "Judged by" line only when a judgment was used.
- Config block `judge` in `config.DEFAULTS`, seeded `enabled: false`; row in
  `show features`. Key from `TYPESAFE_API_KEY` or `~/.config/typesafe/api_key`.
- 22 client tests, 10 blend tests, 8 op tests.

## What it deliberately does not touch

Tier-1 exact match (fuzzy matching was rejected in mem-053), the deep-research ship gate
(documented as "not an LLM judge"), read_guard and the Stop gates (hard blockers inside a
5-second budget). Memory relevance reranking is the natural next surface and is deferred
to its own task.

## Enable

1. Key from https://console.typesafe.ai/keys → `export TYPESAFE_API_KEY=...` in the
   environment Claude Code runs in, or write it to `~/.config/typesafe/api_key` (mode
   600). The key never goes in `.agent/.nav-config.json`; that file is committed.
2. Say `enable judge` (or set `judge.enabled: true`). The toggle prints the key hint.
3. `python3 hooks/nav_hook_lib/judge.py --check` from the plugin root: enable flag, key
   source, live round trip. Session start then shows `Typed judge: on (…)`, or a warning
   with the same hint when no key resolves.

Full setup, config keys and troubleshooting: `.agent/sops/integrations/typesafe-judge-setup.md`.
The prompt text leaves the machine when enabled; that is why it ships off.
