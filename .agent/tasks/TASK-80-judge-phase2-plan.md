# TASK-80: Typed judge, phase 2 — evidence first, then one more surface

**Status**: 📐 Plan — 2026-09-19 (no code yet; confirm scope before implementation)

## Framing constraint

Jev is a specific model for a specific shape of problem: **a typed answer (yes/no
probability, pick-one, or position on a short rubric) over a small piece of state, with a
deterministic fallback when the answer is not decisive.** It is not a generator, not a
reasoner, and not a drop-in for every heuristic in the runtime.

Consequences for this plan:

- No provider abstraction, no "judge anything" API. `judge.py` stays TypeSafe-specific
  with its eight fixed questions; a new surface gets its own fixed question set.
- A surface qualifies only if all four hold: (1) the input is short text or a short list,
  (2) the output is one of a defined set, (3) a wrong answer is cheap because a heuristic
  or the user catches it, (4) the call fits inside the hook budget or runs outside a hook.
- Every new surface ships behind its own off-switch and its own labeled eval, in that
  order: eval first, wiring second. TASK-79 set that precedent.
- Explicitly out: tier1 exact match, the deep-research ship gate, read_guard, Stop gates,
  anything that needs the model to explain itself.

## Workstream A — evidence from real sessions (no model changes)

**Goal**: replace the 60 invented prompts with labels from real prompts, so the tier and
ambiguity numbers are calibrated rather than directional.

- Source: Claude Code transcripts on this machine (`~/.claude/projects/*/…jsonl`), user
  turns only, deduplicated, secret-redacted with `judge.redact_secrets`, head-capped.
  Target 300–500 prompts across at least three projects.
- Labeling: a small CLI (`scripts/judge_label.py`) that shows a prompt and asks for
  tier / task / ambiguous; labels stored next to the fixture. Labeled by the user, not by
  the model and not by me — the point is independence from the question author.
- Output: `fixtures/judge_eval_real.json` + a re-run of the threshold sweep. Thresholds
  move only if the real set says so; the invented set stays as the regression fixture.
- Also record how often each axis lands **in the band** (undecided). That number decides
  whether the band is too wide (judge rarely contributes) or too narrow (overrides on
  coin flips).

Size: 1 day incl. labeling time. Depends on nothing.

## Workstream B — override telemetry (no model changes)

**Goal**: know, per session, how often the judge actually changed a decision, so the
feature can be judged in use rather than on a fixture.

- `scoring._apply_judgment` already returns `overrides`. Record a small counter block in
  the runtime state on UserPromptSubmit: `judge.calls`, `judge.failed`, per-axis
  `overridden` / `undecided` / `agreed`, `latency_ms` last + max.
- Surface it in `nav stats` next to the existing token numbers ("judge: 41 calls, 9
  overrides, 3 undecided, p50 660 ms") and nowhere else.
- mem-034 applies: counters and model id only, never prompt text.

Size: half a day. Depends on nothing; makes A's band question answerable from live use.

## Workstream C — memory relevance rerank (the one new surface)

**Why this surface and not another**: `memory_recall.rank_memories` ranks by raw concept-
set overlap. Candidates are short (one-line summaries), the output is a per-candidate
yes/no ("is this memory useful for this prompt"), a wrong answer only reorders a list the
user sees, and the call already happens inside a 3 s subprocess budget the brief owns.
All four qualifying conditions hold. Reranking is also the shape Jev's own cookbooks
lead with.

- Retrieval stays as is (overlap, top 10 by the current sort). One request with one noul
  per candidate, state = the prompt plus the candidate line. Reorder by probability;
  drop candidates below `noul_low`; keep the original order on any failure.
- Surfaces: NAV-BRIEF memories and SessionStart "Relevant Memories" only. Subagent
  context and failure diagnosis stay on overlap — they run in tighter budgets.
- Config: `judge.rerank_memories` (default `false`), reusing the same key, model, fuse.
- Eval first: 30 prompts × the recalled candidates, labeled useful / not by the user;
  metric is precision at 3 versus overlap order. Wire only if it wins.
- Budget check before wiring: recall subprocess today ~≤3 s; adding ~0.7 s must fit or
  the rerank runs only when the judge already answered this prompt (shared call is not
  possible — different state — but the timing is known).

Size: 1.5 days incl. eval. Depends on A only for confidence in the band values.

## Not planned, and why

- **Complexity for the Stop completion gate** — a gate with a 5 s budget and a
  forced-continuation consequence; a wrong answer is not cheap. Fails condition 3.
- **Skill routing (`detect_skill_match`)** — plausible shape, but the current matcher's
  failure mode is ties on dict order, which is a deterministic bug to fix first.
- **Critic severity in deep research** — the critic already runs as an Opus subagent
  with the full report; a typed second opinion adds a dependency without a fallback
  story. Fails condition 4 and the "not a reasoner" constraint.
- **A provider layer** — one provider, one endpoint, one model family. Abstracting now
  would be speculation.

## Order and exit

B → A → C. B is cheap and turns the dogfood in this repo into data; A makes the numbers
honest; C is the only new surface and only ships if its own eval wins.

Exit for the whole task: real-session numbers in the task doc, `nav stats` showing judge
counters, and a rerank decision (shipped or explicitly rejected with the eval attached).
