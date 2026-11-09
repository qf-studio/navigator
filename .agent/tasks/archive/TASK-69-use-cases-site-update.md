# TASK-69: Use-case content — landing page + docs site update

**Status**: ✅ Implemented — 2026-07-10 (site commit 8deb8db); live since the site moved to
AWS at navigator.quantflow.studio on 2026-10-08 (repo `qf-studio/navigator-docs`)

## Context

Navigator's feature set has grown (v6.18.1 released; v7 runtime in local alpha) but the
site (`~/Projects/startups/navigator-site`, deployed at navigator.quantflow.studio) has no
use-case-oriented content: the landing page (`content/index.mdx`) sells the core loop
(context engineering, sessions that last) and the docs are organized by feature/skill,
not by "what problem does this solve for me."

A 7-case map was drafted in-session (2026-07-10), organized by developer moment, framed
benefit-first per positioning rules (outcomes not features; superset not alternative):

1. **Long feature work that used to die mid-session** — session_start, lazy docs,
   read_guard, compact markers.
2. **Unattended / semi-attended execution** — Loop Mode, evidence-gated stop_completion
   (v7), Task Mode phases, PILOT_EXECUTOR headless mode.
3. **Starting work with the right shape** — prompt gating, intent briefs,
   agents-vs-skills routing.
4. **Team memory that survives people and sessions** — knowledge graph, memory types,
   SOPs, task docs, 48-hour onboarding.
5. **Zero-cost operational queries** — Tier-1 instant answers (v7), grot cards.
6. **Code quality without ceremony** — simplification pass, ToM checkpoints,
   nav-diagnose.
7. **Pipeline hand-off** — nav-pilot dispatch, PM integrations.

Differentiation lives in 1, 2, 4 (evidence-gated completion, compact-survival markers,
queryable decisions). Case 5 is the best live demo (deterministic, zero-token).

## Scope

- **Repo**: `navigator-site` only. No plugin-repo README/CLAUDE.md changes.
- **New docs page**: `content/use-cases.mdx` carrying all 7 cases, each linking to the
  relevant concept/skill pages; wired into `content/_meta.js` (after Getting Started).
- **Landing update**: one compact section on `content/index.mdx` (3–4 headline cases:
  long sessions, unattended runs, team memory, zero-token queries) linking to
  `/use-cases`. Keep the existing hero and section order otherwise intact.

## Decision points (defaults chosen; override before implementation)

1. **v7 content policy** — RESOLVED by user 2026-07-10: the site is not publicly
   launched yet (at the time: no custom domain, no announcement), so there is no released-claims surface
   to protect. v7 capabilities (Tier-1 instant answers, evidence-gated completion,
   dispatcher runtime) are written as first-class, no version badges. The site launches
   with/after v7.
2. **Placement** — DEFAULT: dedicated `/use-cases` page + compact landing section.
   Alternative: landing-only section (rejected: 7 cases don't fit the landing rhythm).

## Acceptance Criteria

- [x] `content/use-cases.mdx` exists: all 7 cases, benefit-first headers (the developer's
      problem, not the feature name), each case names its features and links at least one
      existing docs page.
- [x] `content/_meta.js` includes the new page; sidebar renders it.
- [x] `content/index.mdx` gains a use-cases section (3–4 cases max, one line each +
      link to `/use-cases`); no other landing sections reworded.
- [x] Tone/formatting matches existing site MDX conventions (check neighboring pages for
      callout/component usage before writing).
- [x] `bun run build` (or the repo's build script) exits clean; both pages visually
      checked in dev server.
- [x] Deploy: shipped with the AWS move (push `main` + `prod-*` tag in `qf-studio/navigator-docs`).

## Verify

```
cd ~/Projects/startups/navigator-site
bun run build
bun run dev   # visual check: / and /use-cases
```

## Won't do

- TASK-15 marketing-doc refresh (separate, stale, needs its own pass).
- DNS / domain work.
- Repositioning rewrite of existing landing copy.
- Plugin-repo docs (README, CLAUDE.md, .agent/system) — v7 docs there are already
  truth-synced (9796332).

## Refs

- Site repo: `~/Projects/startups/navigator-site` (Nextra; landing = `content/index.mdx`,
  nav = `content/_meta.js`, all pages MDX via `app/[[...mdxPath]]`)
- Positioning rules: benefit-focused ("Finish What You Start"), superset framing
- Use-case map source: session 2026-07-10 (post-v7-alpha dogfood session)
- TASK-55 (site build), TASK-64 (v7 release gate — gates landing v7 claims)
