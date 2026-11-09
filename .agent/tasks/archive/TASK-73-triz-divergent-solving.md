# TASK-73: TRIZ Phase 2 — nav-triz divergent solving

**Status**: ✅ Implemented — 2026-09-10

## Context

**Problem**: Phase 1 (TASK-72, v7.1.0) captures contradictions and lets the graph answer
"how did we resolve this before". It still leaves the model with one plan: the first idea
that fits. TRIZ's actual leverage is divergence — several candidates from *different*
resolution families, each with a named downside, before converging.

**Goal**: A skill that, when a contradiction is declared on a substantial task or the user
asks for alternatives, produces three competing candidates from different separation modes,
recommends one, and captures the resolution back into the graph.

**Decision**: user chose to skip the dogfood gate proposed in TASK-72 and build Phase 2
immediately (2026-09-10). Ceremony risk is handled the way mem-060/mem-074 resolved
"feature value vs regression risk": by condition — the skill fires only on explicit ask or
a declared contradiction on a substantial task, never on routine prompts.

## Implementation

- `skills/nav-triz/SKILL.md` — 7-step protocol (contradiction → IFR → reuse inventory →
  prior resolutions + principle prompts → three candidates with mandatory "worsens" cell →
  recommend one → capture decision), one-screen output template, fire/no-fire rules,
  hand-offs.
- `skills/nav-triz/functions/triz_suggest.py` — deterministic keyword ranking over ~21
  software-mapped principles; one candidate per separation mode first, padded with a
  generic trio; prior decisions via `graph_manager.query_contradictions`; always exit 0.
  Tests: `test_triz_suggest.py` (catalog integrity, ranking, diversity, padding,
  plural/singular keyword match, graph priors, CLI JSON).
- `skills/nav-triz/reference/PRINCIPLES.md` — four separation modes with repo examples,
  the mapped principles table, the non-transferring list, usage steps. Lazy-loaded.
- Wiring: `plugin.json` skills list, `Makefile` TEST_DIRS, nav-brief hand-off paragraph,
  navigator-research Phase 0.5 evidence step, nav-workflow RESEARCH bullet, CLAUDE.md
  Intent Briefs paragraph, DEVELOPMENT-README thread line.

## Non-goals

- A hook op or scorer change; the skill is model-invoked only.
- Auto-capturing the chosen candidate (step 7 is explicit on purpose).
- Contradiction Matrix (39×39) — the parameter vocabulary does not map to software.

## Acceptance Criteria

- [x] `triz_suggest.py` returns 3 candidates from distinct separation modes when ≥3 modes
      match; pads to the limit otherwise; generic trio with a visible label on no match
- [x] Prior resolutions come from the live graph (`--filter` per keyword), empty without a
      graph, exit 0 throughout
- [x] Skill listed in `plugin.json`; release validator passes; `make test` green
- [x] Brief, research agent, and workflow docs point to the skill only under the declared-
      contradiction condition

## Verify

```bash
make test
python3 skills/nav-release/functions/release_validator.py --check-all
python3 skills/nav-triz/functions/triz_suggest.py --contradiction "clean codebase vs rollback safety"
# expect: prior mem-063 + mem-073, candidates led by #11 beforehand cushioning
```

## CHANGELOG draft (next version)

- **nav-triz (TASK-73)**: divergent solving for declared contradictions — three candidates
  from different TRIZ separation modes with mandatory downsides, one recommendation, capture
  back to the graph; `triz_suggest.py` principle prompts + prior resolutions;
  `reference/PRINCIPLES.md` software-mapped principles.

## Refs

- TASK-72 (Phase 1), mem-060, mem-074, `skills/nav-triz/reference/PRINCIPLES.md`
