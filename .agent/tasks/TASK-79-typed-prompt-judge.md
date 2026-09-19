# TASK-79: Typed prompt judge — Jev behind the keyword scorers

**Status**: ✅ Implemented — 2026-09-19 (ships in v7.7.0, dogfooding ON in this repo)

## Context

**Problem**: every prompt-time decision in the hook runtime is a keyword or regex
match. Loop Mode fires on the phrase "loop mode" wherever it appears — including a
subagent report whose section header read "F. Loop mode" (observed 2026-09-19, this
session). Complexity is a weighted keyword sum; ambiguity is a base of 0.5 minus credits
for file paths and numbers. The matchers are cheap and deterministic, and wrong in ways a
reader spots instantly.

**Option evaluated**: TypeSafe's Jev (docs.typesafe.ai), a "System One" model that answers
typed questions with calibrated probabilities instead of text. One HTTP request carries
several questions answered in parallel. Measured on this repo's prompts: ~0.7 s per call,
~520 input tokens, $0.042 per million input tokens, output free. On the false-fire text
above it returned `wants_loop = 0.14` where the keyword matcher said YES.

**Contradiction resolved**: better classification improves gating precision and worsens
determinism and privacy (prompt text leaves the machine; answers can drift across model
versions). Separation in condition: the judge is an opt-in overlay that ships OFF, answers
only when confident, and every axis falls back to the existing heuristic on low
confidence, timeout, missing key, or any error. The heuristic remains the floor; nothing
is deleted.

## Scope

Phase 1 (this task): the three prompt-time classifiers behind one request.

| Axis | Heuristic today | Judge question | Consumed by |
|---|---|---|---|
| Loop trigger | 14-phrase list, word-boundary | `wants_loop` noul | prompt_gate tier + block precondition |
| Complexity | keyword tiers + regex families | `complexity` score, 4 levels | prompt_gate Task Mode, ScoreCard |
| Task-shaped | 26 verbs / question / confirmation | `is_task` noul | prompt_brief gate |
| Ambiguity | base 0.5 − credits | `ambiguity` score, 3 levels | prompt_brief threshold |
| Undefined dims | presence regexes | 4 nouls (scope/limits/approach/verification) | NAV-BRIEF rows |

Phase 2 (deferred, separate task): memory relevance rerank in `memory_recall.py` —
keep set-overlap retrieval, ask one noul per candidate, reorder.

Not in scope, on purpose: tier1 exact match (mem-053: fuzzy matching rejected), the
deep-research ship gate (documented as "not an LLM judge"), read_guard and the Stop
gates (hard blockers inside a 5 s budget).

## Design

- `hooks/nav_hook_lib/judge.py` — stdlib `urllib` client. `judge_prompt(prompt, cfg)`
  returns a `Judgment` or `None`; never raises, never writes stderr (mem-034). Prompt is
  `strip_all`'d by the op, then secret-redacted (`redact_secrets`) and head-capped
  (`max_state_chars`) before it becomes the request `state`. `for_ctx(ctx, message)`
  caches the result on the dispatch context so prompt_gate and prompt_brief share one
  call.
- Thresholds travel on the `Judgment`: nouls are decisive only outside the
  `[noul_low, noul_high]` band; score axes only when `confidence >= min_confidence`.
  Inside the band / below confidence, the heuristic answers for that axis.
- `scoring.detect_workflow(message, judgment=None)`, `score_ambiguity(prompt,
  judgment=None)`, `score(prompt, config, judgment=None)` — blend points. With
  `judgment=None` every function is byte-identical to before (v6 parity tests unchanged).
- Config block `judge` in `config.DEFAULTS`, seeded `enabled: false`; row in
  `prompt_tier1.FEATURE_BLOCKS` so `show features` lists it. Key from
  `TYPESAFE_API_KEY`, else the file named by `judge.api_key_file`
  (default `~/.config/typesafe/api_key`, mode 600).
- Budget: UserPromptSubmit manifest timeout is 5 s. Judge fuse defaults to 1500 ms;
  prompt_gate is a gate (deadline-exempt) so the fuse is the only protection.
- Eval: `scripts/judge_eval.py` over `hooks/nav_hook_lib/fixtures/judge_eval.json`
  (labeled prompts incl. the observed false-fires) prints heuristic vs judge accuracy
  per axis and latency. Thresholds are set from that run, not from cookbook defaults.

## Verification

- Unit: parse/decide/redact/fail-open/cache, blend with a fake judgment, ops parity with
  judge disabled (existing v6 snapshot tests must not change).
- Live: eval script run recorded below.
- Full suite: `python3 -m unittest discover -s hooks -p "test_*.py"`.

## Eval run

2026-09-19, `jev-1.13.0`, 60 labeled prompts, responses recorded in
`hooks/nav_hook_lib/fixtures/judge_eval_recorded.json` (replay with
`python3 scripts/judge_eval.py --replay <file>`).

| Axis | Heuristic | Judge alone | Blended (shipped policy) |
|---|---|---|---|
| Tier (DIRECT/TASK/LOOP) | 38/60 | 50/60 | 53/60 |
| Task-shaped | 43/60 | 57/60 | 54/60 |
| Ambiguous (brief needed) | 47/60 | 51/60 | 50/60 |

Latency median 662 ms, max 722 ms; 41,784 input tokens for the set (~700 per prompt
with all eight questions; ~$0.00003 per prompt).

Threshold sweep (noul band × confidence floor, 9 cells): 0.4/0.6 with floor 0.4 won or
tied on every axis; 0.3/0.7 with floor 0.6 (the cookbook-style defaults) cost one to two
prompts per axis. Shipped defaults follow the sweep.

Two calibration findings folded into the design:
- A linear map of the three-level ambiguity rubric puts "partly" at exactly the 0.5
  brief threshold, so "bump the version to 7.7.0" would brief. Levels are now weighted
  0 / 0.35 / 1.0 over the returned probabilities; only real "vague" mass crosses.
- Blended task-shapedness trails judge-alone because prompts inside the noul band keep
  the heuristic, which is the weaker source there. Accepted: the band is the safety
  margin against overriding on a coin flip.

Where the remaining misses sit: labels the author would argue with on re-read ("deep
research on X" as a task; "build a CLI" as TASK rather than a small task), not cases
where the judge contradicts an obvious reading. The observed false-fire (a section header
containing "Loop mode") scores `wants_loop = 0.14` and is silenced.
