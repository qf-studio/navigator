# TASK-15: Marketing Strategy & Community Adoption Plan

**Status**: 📋 Backlog — postponed 2026-10-05; marketing runs through the owner's Threads and LinkedIn accounts for now, back to this plan later. Refreshed 2026-10-05 against the repo at v8.2.7 (research pass over README, CLAUDE.md, the docs site, `.agent/marketing/`, grafana, archived launch plans). The 2025-10-20 plan is preserved below under "Retired plan" and in git history (`git show f1c7171:.agent/tasks/TASK-15-marketing-community-adoption.md`).
2026-10-05 against the repo at v8.2.7 (research pass over README, CLAUDE.md, the docs site,
`.agent/marketing/`, grafana, archived launch plans). The 2025-10-20 plan is preserved below
under "Retired plan" and in git history (`git show f1c7171:.agent/tasks/TASK-15-marketing-community-adoption.md`).
**Priority**: Medium — ships between releases, never blocks one
**Owner**: Aleks (QuantFlow Studio)
**Created**: 2025-10-20 · **Refreshed**: 2026-10-05 · **Next review**: 2026-11-05

---

## Where things stand (2026-10-05)

| Fact | Value | Evidence |
|---|---|---|
| Plugin | v8.2.7, mod runtime inside Claude Code 2.1.287+, Python fallback | `CLAUDE.md` Navigator Runtime (v8) |
| Repo | `qf-studio/navigator` (old `alekspetrov/` path redirects); 351 stars, 18 forks, created 2025-10-10 | `gh repo view` 2026-10-05 |
| Install | `/plugin marketplace add qf-studio/navigator` then `/plugin install navigator` | `README.md` Quick start |
| Site | navigator.quantflow.studio (AWS since 2026-10-08), 69 pages, landing with hero → loop → runtime → pane → superset table → CTA | TASK-55 |
| README | Benefit-led rewrite done ("Finish What You Start", the loop, before/after table); no images | `README.md:1-55` |
| Skills / agents | 31 skills, 6 agents | `skills/`, `agents/` |
| Workshop | JSNation Next.js workshop delivered 2026-05-22 (TASK-39); GitNation plan in `pilot-pr/launch/plans/` | TASK-39 |
| Social | Threads only in practice. Posted: v8.0.0 (2026-10-03), v8.2.5 (2026-10-05). Drafted, never posted: deep research (v7.3/7.4), typed judge (v7.7), team-friendly (v7.8), v8.1.0 | `.agent/marketing/` (untracked, local) |
| Video | None recorded. 2025-11 production plan and marker describe a pre-v6 product; obsolete | `VIDEO-PRODUCTION-PLAN.md:474` |
| Launches | No Product Hunt, Show HN, Reddit or Discord launch ever executed; only archived TASK-18 plans | `.agent/tasks/archive/TASK-18-*` |
| CONTRIBUTING | 20 lines, per-skill semver only | `CONTRIBUTING.md` |

### Claims that need hygiene before they go in copy

- **92% reduction** is the 12k-vs-150k computation (`project-architecture.md:320`), not a
  measured figure; the site already says "92% (instrumented)". Keep "150k → 12k" as the claim.
  "94% of the context window available" (README) is the same arithmetic from the other side.
- **97.7% marker compression** survives only in `.agent/philosophy/PATTERNS.md:682`. Not in
  README or the site. Do not use it in posts until it is re-measured on v8.
- **Grafana "10 panels"**: the dashboard has 13. Fixed in `.agent/grafana/README.md` in this
  refresh.
- **"Self-improving"**: `nav-skill-creator` exists but is not a headline feature anywhere. Drop.
- **PM tools**: Linear, GitHub, Jira, GitLab (the old doc omitted GitLab).

---

## Live checklist (routes on the pane again once Status returns to In Progress)

- [ ] Post the v8.2.6–v8.2.8 cut on Threads: short labeled cut, 500-char cap, pane
      screenshot (stop-gate over-fires fixed; finished task no longer the destination).
- [ ] Decide the three unposted drafts (deep research, typed judge, team-friendly): one
      "September in Navigator" roundup post, or delete the drafts.
- [ ] Record a 2-minute screen capture of a real session: nav-start → `/nav` pane → a reject
      landing in the reads card → next card advancing. Replaces the 2025 video plan.
- [ ] Show HN for v8: "a Claude Code plugin that runs inside Claude Code and draws its own
      pane". Link the site, not the repo README. One post, no relaunch.
- [ ] Expand CONTRIBUTING.md: `make test` (with `NAVIGATOR_MOD_OWNS` unset), `make mod-test`,
      fixture regeneration, the Python-parity rule, commit format.
- [ ] Re-measure the marker compression on a v8 session or retire the 97.7% claim from
      PATTERNS.md.
- [ ] Monthly on the review date: record stars, forks, release count, posts made, in the
      table above. Baseline 2026-10-05: 351 stars, 18 forks, 7 releases that day.

---

## Positioning (current)

**One line** (README): *Finish What You Start. Sessions that last. AI that learns. Features that ship.*

**Hero** (site): *Context engineering for Claude Code. Load what you need, when you need it —
150k tokens down to 12k. Sessions that last 20+ exchanges instead of crashing at 7.*

**Rule**: frame Navigator as a **superset** (has everything a workflow plugin has, plus a
runtime that enforces it), never as an alternative. The site and README compare against a
generic "typical plugin", not named competitors. The 2025 named-competitor matrix is retired;
none of those products is referenced anywhere else in the repo.

**What v8 adds that the 2025 plan never mentioned** (each is a post or a demo on its own):
the in-process mod runtime with Python fallback, the `/nav` pane and status band, the reject
log, the typed prompt judge, ADHD mode, the knowledge graph, TRIZ divergent solving, deep
research, LSP-aware research, intent briefs, Tier-1 instant answers, Task Mode, Theory of
Mind, loop mode, simplification, team-friendly multi-person mode (v7.8.0), the Pilot theme.

### Audiences (unchanged, still right)

1. **Solo developers / indie hackers** — pain: sessions that crash, lost work, token cost.
   Message: sessions that finish features. Channels: Threads (active), X, r/ClaudeAI, HN.
2. **Engineering teams of 5–20** — pain: inconsistent docs, slow onboarding. Message: onboard
   in 48 hours; one repo, many people (v7.8.0). Channels: LinkedIn, Dev.to.
3. **AI-tool power users** — pain: tool fatigue. Message: the runtime shows its decisions
   (judge, reject log, pane). Channels: newsletters, YouTube, Discord communities.

### Messaging frame: Hook → Problem → Solution → Proof → CTA

- Hook: "Your session died at exchange 7 again."
- Problem: everything loaded upfront; the context window is docs you never read.
- Solution: load what you need when you need it; a runtime that enforces it.
- Proof: 150k → 12k per session; the pane shows the fill, the rejects and the next leg live.
- CTA: `/plugin marketplace add qf-studio/navigator` → `/plugin install navigator`.

### Channel practice

| Channel | Use | Cadence |
|---|---|---|
| Threads | release cuts with a pane screenshot (what the user actually does) | per release worth announcing |
| GitHub releases | CI-published notes from `releases/` | every tag |
| Docs site | synced on every plugin release | every tag |
| Show HN | once, for v8 | one-shot |
| Dev.to / LinkedIn | team-mode and context-engineering long-form | when a piece exists |
| Reddit, Product Hunt, Discord | not used so far; revisit after the Show HN | — |

### Metrics

Baseline 2026-10-05: 351 stars, 18 forks. Install counts are not observable from the
marketplace. Targets are set at the monthly review, not here; the 2025 table (1,000 stars in
3 months, Product Hunt Top 5) was never tracked and is retired.

---

## Retired plan (2025-10-20), kept for reference

Items are plain bullets on purpose: the pane routes only on the live checklist above.
Status per item as of 2026-10-05.

**Phase 1 — Foundation**
- Rewrite README.md with marketing copy — done (benefit-led README).
- Visual diagrams — partial: `docs/ARCHITECTURE-DIAGRAMS.md` is text; site has `nav-pane.png`.
- GIFs/videos — not done; superseded by the live-checklist screen capture.
- CONTRIBUTING.md — exists, minimal; on the live checklist.
- 2-minute demo, 30-second pitch video, before/after screenshots, Grafana screenshots —
  not done except `.agent/grafana/dashboard-screenshot.jpg`.
- GitHub README as landing page — superseded by the docs site (TASK-55).
- docs.navigator.dev — done as navigator.quantflow.studio (live 2026-10-08).
- Product Hunt draft, Claude Code Discord, r/ClaudeAI, tweet thread, personal network —
  not executed.

**Phase 2 — Amplification**
- Blog post, Dev.to article, YouTube tutorial, 7-day thread series — not done.
- Product Hunt launch, Show HN, Reddit AMA, Discord server — not done; Show HN is on the
  live checklist, the rest dropped.
- Influencer and newsletter outreach, plugin-creator engagement — not done.
- Three case studies with ROI — not done; the JSNation workshop (TASK-39) is the one
  real-world artifact.

**Phase 3 — Scale**
- Content calendar, skill-of-the-week, contributor program, office hours, community
  Discord, marketplace feature, cross-promotion, MCP tutorials, guest posts, community
  skill marketplace — not started; revisit after the Show HN result.

**Also retired**: the four-week content calendar, the social copy templates (install
command and repo owner were wrong; the pitch predates the runtime), the Product Hunt
description, the KPI and revenue tables, the accountability checklists, the 2025 resource
and budget notes, and the named-competitor matrix (AI Context Optimizer, Augment Code,
16x Prompt, Context Note, LangGraph, LlamaIndex, Microsoft Agent Framework).

---

## References

- `README.md`, `CLAUDE.md` (Navigator Runtime v8), `.agent/system/project-architecture.md`
- Docs site: `/Users/aleks.petrov/Projects/startups/navigator-site` (repo `qf-studio/navigator-docs`; deploy: push `main` + `prod-*` tag)
- Drafts: `.agent/marketing/*.md` (local, untracked by design)
- Workshop: `.agent/tasks/TASK-39-nextjs-workshop-prep.md`; site: `TASK-55-landing-docs-site.md`
- Archived launch thinking: `.agent/tasks/archive/TASK-18-*`
