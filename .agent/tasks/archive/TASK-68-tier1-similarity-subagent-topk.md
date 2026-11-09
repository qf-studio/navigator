# TASK-68 — tier1 similarity threshold + subagent_context top-K

**Status**: ✅ Implemented — 2026-07-10

## Context

Two tuning items were left deferred at the end of the TASK-62 runtime work, both
with placeholder logic and a "decide later" comment:

1. `prompt_tier1._count_false_positive` flagged a near-identical re-prompt after
   a Tier-1 hit with a bare substring test (`command in normalized_prompt and
   != command`). Substring containment over-counts (any prompt that merely
   embeds the command string) and under-describes intent (no notion of a
   reordered rephrase). The similarity threshold was an explicit deferred
   TASK-62 decision.

2. `subagent_context` selected session memories via
   `knowledge_graph.max_session_memories` with an ad-hoc `TOP_K_DEFAULT`
   fallback and no explicit cap on what `memory.recall` returned — the top-K
   contract was implicit.

Both are TELEMETRY / CONTEXT-injection only. Neither changes routing.

## Acceptance Criteria

- [x] (A) tier1 false-positive detection uses an explicit, named similarity
      rule with `SIMILARITY_*` module constants, not a bare substring test.
- [x] (A) `nav stats please` still counts as a false positive after a
      `nav_stats` hit; `refactor the parser` does not; a prompt sharing only
      one word with the command does not.
- [x] (A) The one-shot window (`turn.pop("tier1_hit")`) still clears on a
      counted false positive.
- [x] (A) Detection remains telemetry-only — `run()` still returns `None` on
      the passthrough path; routing is unchanged.
- [x] (B) `subagent_context` has a named `TOP_K` constant (default 5) and caps
      the injected memory set to at most TOP_K with deterministic ordering.
- [x] (B) Output stays `<= 2000` chars via `budget.clamp(text, 'SubagentStart')`.
- [x] `make test` stays green; `test_prompt_tier1` + `test_subagent_context`
      extended.

## Implementation

### (A) `hooks/ops/prompt_tier1.py`

- Added module constants:
  - `SIMILARITY_MAX_EXTRA_TOKENS = 3` — containment padding budget.
  - `SIMILARITY_MIN_JACCARD = 0.6` — token-set overlap floor.
- Added `_is_near_identical(normalized_prompt, command)` implementing two named,
  telemetry-only rules; a prompt counts as a genuine rephrase when EITHER holds:
  - **containment + small padding**: the prompt contains the command verbatim
    and adds at most `SIMILARITY_MAX_EXTRA_TOKENS` extra words ("nav stats
    please"); OR
  - **token-set overlap**: `Jaccard(prompt tokens, command tokens) >=
    SIMILARITY_MIN_JACCARD` (a reordered / reworded near-duplicate such as
    "features show" for "show features").
  A verbatim re-type where `normalized_prompt == command` (a whitespace-only
  miss of the exact matcher) and a prompt sharing only a single word clear both
  rules and are not counted.
- `_count_false_positive` now delegates to `_is_near_identical`; on a match it
  increments `tier1.false_positives` and pops `turn.tier1_hit` (one-shot window),
  exactly as before. The passthrough `return None` is untouched.

### (B) `hooks/ops/subagent_context.py`

- Renamed `TOP_K_DEFAULT` → `TOP_K` (default 5); it is the documented default,
  overridable by `knowledge_graph.max_session_memories`.
- Added `_top_k_memories(summary, k)`: `memory.recall` already returns a
  compact, confidence-ranked list (one memory per line, highest confidence
  first) and applies its own `--limit`. The helper re-caps to at most `k`
  non-blank lines, **preserving recall's ranking order verbatim** — a stable,
  deterministic slice. This makes the top-K bound explicit regardless of what
  recall returns.
- `run()` passes `top_k` as the recall limit and then applies
  `_top_k_memories(memories, top_k)` before assembling the snapshot;
  `budget.clamp(text, 'SubagentStart')` (2k) is unchanged.

**Chosen defaults (documented decision):** `TOP_K = 5`,
`SIMILARITY_MAX_EXTRA_TOKENS = 3`, `SIMILARITY_MIN_JACCARD = 0.6`. The Jaccard
floor of 0.6 counts reordered/near-duplicate rephrases while rejecting prompts
that share only a minority of tokens; three padding words covers natural
politeness/qualifier suffixes ("please", "for me", "right now") without
matching genuinely different requests.

## Verify

```
cd hooks/ops && python3 -m unittest test_prompt_tier1 test_subagent_context
# -> Ran 49 tests OK
make test
# -> All unit tests passed (full suite green)
```

New tests:
- `test_prompt_tier1.py`: single-shared-word non-count, reordered-rephrase
  Jaccard count, verbatim-whitespace-miss non-count, and a direct
  `_is_near_identical` / constants probe.
- `test_subagent_context.py`: `TopKTest` (TOP_K default, at-most-TOP_K cap with
  `<= 2000` chars, deterministic ordering across runs, helper unit); the budget
  test was re-shaped to trigger the 2k clamp with TOP_K oversized lines rather
  than a 200-line list (assertions unchanged).

## Done

- Named similarity rule replaces the substring seed; false-positive telemetry
  now tracks genuine rephrases and ignores loosely-related prompts.
- subagent_context top-K is a named, deterministic, budget-clamped contract.
- Full suite green.

## Refs

- `hooks/ops/prompt_tier1.py`, `hooks/ops/test_prompt_tier1.py`
- `hooks/ops/subagent_context.py`, `hooks/ops/test_subagent_context.py`
- mem-053 (Tier-1 block-as-answer channel), mem-052 (SubagentStart 2k budget)
- TASK-62 (runtime capabilities that deferred these two decisions)
