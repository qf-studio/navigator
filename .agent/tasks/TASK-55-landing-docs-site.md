# TASK-55: Navigator Landing Page + Documentation Site

**Status**: ✅ Live at https://navigator.quantflow.studio since 2026-10-08 — hosted on AWS like pilot-docs (ECS service `navigator-docs` on the quantflow cluster behind the ALB + CloudFront, Route 53 alias from `quantflow-domain-config`). Source repo `qf-studio/navigator-docs`; a `prod-<version>-<ts>` tag from `main` builds the image to GHCR and the AWS workflow mirrors it to ECR and deploys `quantflow-svc-navigator-docs`. The Vercel deployment (navigator-site.vercel.app) is retired. Previous status: built + deployed on Vercel 2026-06-24; 2026-07-09 sync.
**Created**: 2026-06-24
**Supersedes**: TASK-05 (Landing Page Content) and TASK-13 (Web Documentation Site — stale: VitePress/v3.1.0)
**Source**: deep-research workflow `wf_0777e387-af9` (9 agents, asset audit + Pilot-stack study + web refs + completeness critic)
**Companion artifacts**: `../../../navigator-site/docs/landing-page-raws.md`, `../../../navigator-site/docs/docs-site-IA.md` (moved into the new repo)
**Site repo**: `/Users/aleks.petrov/Projects/startups/navigator-site`

---

## Objective

Ship a marketing landing page + complete documentation site for the Navigator plugin (v6.16.0, 28 active skills),
built on the **same stack as Pilot's site** (Next.js 15 + Nextra 4 + `nextra-theme-docs` + Pagefind), so the two
products share proven architecture without coupling release cycles.

---

## Stack decision (recommended)

**Build a NEW standalone Nextra 4 app inside the navigator repo at `/site`.** Do **not** extend Pilot's site.

Rationale:
1. **Brand separation** — Pilot's `content/navigator/` is *internal* feature docs ("Context Intelligence"), not
   standalone product docs. Mixing muddies both brands and couples cadences (Navigator ships ~2×/day).
2. **Docs-as-code** — Navigator's marketing/docs source already lives in this repo (`README.md`, `docs/`). Versioning
   the site with the plugin (version auto-read from `.claude-plugin/plugin.json`) matches the documentation-first
   principle the product preaches.
3. **Ownership** — Navigator is MIT OSS on GitHub; Pilot is a hosted product on GitLab. A standalone site avoids
   granting Pilot-repo access to OSS contributors.
4. **Max reuse, no coupling** — copy Pilot's proven patterns (Nextra config, `_meta.js`, `Callout`/`Tabs`, 3-stage
   Dockerfile, Pagefind postbuild, `app/[[...mdxPath]]/page.tsx`) into a fresh app.

Directory: `/site` (excluded from plugin packaging + `.claude-plugin` marketplace manifest).

---

## Phases & effort (~8–12 eng-days; thin MVP ~3–4 days)

### Phase 0 — Sign-off + scaffold (1–1.5d)
- Confirm standalone `/site`, target domain, and brand identity (logo/palette) — **blocking open questions below**.
- Init Nextra 4 app with Bun; copy Pilot scaffolding (`app/layout.tsx`, catch-all MDX renderer, `mdx-components.tsx`,
  `globals.css`). Pin **exact** versions from Pilot's lockfile (Nextra 4, node 24.10.0).
- Navbar: Navigator brand + version component (reads `.claude-plugin/plugin.json`) + GitHub + Install CTA.
- Root `content/_meta.js` + placeholder `content/index.mdx`; gitignore `site/.next`, `site/node_modules`, `site/.pagefind`.
- **Deliverable**: `/site` boots via `bun run dev`; routable empty content tree with working nav.

### Phase 1 — Landing home (1.5–2d)
- Author `content/index.mdx` (`copyPage:false`, full-width) from [`docs/landing-page-raws.md`](../../docs/landing-page-raws.md) — pure MDX, no custom React hero for v1.
- Hero / problem / how-it-works / features grid / proof / use-cases / install / superset comparison / final CTA.
- Apply the **metric-grounding fixes** (see below) — honest "instrumented / run `/nav:stats`" framing, corrected install command, 28-skill count.
- **Deliverable**: production-ready landing an engineer understands in <2 min.

### Phase 2 — Docs migration (3–4d, largest)
- Getting Started ← `QUICK-START.md` (+ **fix `jitd` install bug**), nav-onboard.
- Concepts ← `ARCHITECTURE.md` + `ARCHITECTURE-DIAGRAMS.md` (ASCII → code blocks).
- Skills (28 active) ← `skills/*/SKILL.md` frontmatter; grouped per IA; deprecated tombstone for the 2.
- Configuration + Reference ← `CONFIGURATION.md`, `PERFORMANCE.md`; **add** `reference/troubleshooting`,
  `community/changelog` (footer links them).
- **Net-new**: `integrations/pilot.mdx` from `skills/nav-pilot/SKILL.md`.
- Version-correctness pass (strip v3/v5 targets → v6.16.0). Optional: script to auto-gen skill stubs from SKILL.md frontmatter.
- **Deliverable**: ~25 doc pages + all 28 active skills documented.

### Phase 3 — Search + polish (1.5–2d)
- Wire Pagefind (reuse Pilot postbuild); add `data-pagefind-body`/`-ignore` on diagram pages; verify landing + docs indexed.
- Responsive/perf/a11y/SEO (per-page frontmatter, OG image, sitemap/robots); internal link audit.
- **Deliverable**: working search; mobile-responsive, accessible, SEO-complete; passing Lighthouse.

### Phase 4 — Deploy (0.5–2d)
- **Recommended (OSS default): Vercel** — `/site` as project root, per-PR previews, free tier, no Dockerfile needed. _(historical rationale; superseded 2026-10-08 by AWS, see Phase 4)_
- **Parity alternative**: port Pilot's 3-stage Dockerfile + GitHub Actions `site.yml` → GHCR → self-host on Traefik.
  (Pilot uses GitLab CI — **not** portable; translate to GitHub Actions.)
- Keep the Dockerfile committed regardless for portability. Add a CI build gate (`bun install && bun run build`) on PRs touching `/site`.
- **Deliverable**: automated deploy on merge; live site on chosen domain w/ HTTPS; CI gate.

---

## Metric-grounding fixes (P0 — applied in raws, need sign-off)

1. **"Verified, not estimated"** → the 94/100 / 35% / 92% numbers trace to a *hardcoded sample* in
   `nav-stats/SKILL.md`; `PERFORMANCE.md` calls them estimates. Reframed to **"instrumented with OpenTelemetry — run
   `/nav:stats` for yours"**; efficiency panel labeled "example output". **Decision: publish a real dataset (keep
   "verified") OR ship softened framing?**
2. **Marker compression** → use the single grounded figure (~97.7%, ~130k convo → 2–5k marker); drop invented 130k–200k range.
3. **Skill count** → "28 active skills (2 deprecated)" everywhere.
4. **Install command** → `/plugin marketplace add alekspetrov/navigator` + `/plugin install navigator`; regression-check that no page ships `jitd` or `claude plugin add`.
5. **Figma MCP** → removed from comparison unless `product-design` is promoted + given a landing card.

---

## Risks
- Stack version drift (pin Pilot's exact Nextra/Next/node versions).
- Content staleness (`jitd` install bug, v5.2.0 PITCH, VitePress TASK-13) — version-correctness pass is mandatory.
- ASCII diagrams are weak as a marketing hero — may need real SVG/illustration (no brand assets exist yet).
- Zero real social proof (no testimonials/logos) — v1 ships without; weakens conversion.
- Deploy infra mismatch (Pilot self-host needs Traefik/registry the OSS repo lacks → Vercel avoids this). _(historical; the quantflow ECS/CloudFront infra closed this gap in 2026-09)_
- Repo bloat — `/site` must be excluded from plugin packaging + marketplace manifest.
- Docs-sync drift — 28 SKILL.md files change fast; prefer auto-generated skill stubs.

---

## Decisions (locked 2026-06-24)
1. ✅ **Separate repo** `../navigator-site` (sibling of `navigator/` and `pilot/`) — NOT inside the plugin repo (keeps it clean). Supersedes the earlier "standalone `/site` inside repo" wording.
2. ✅ **Domain: `navigator.quantflow.studio`** (matches `pilot.quantflow.studio`).
3. ✅ ~~**Deploy: Vercel** (custom domain via DNS CNAME; Dockerfile kept committed for self-host parity).~~ **Superseded 2026-10-08: AWS ECS + CloudFront, same shape as pilot-docs** (the committed Dockerfile is now the production build).
4. ✅ **Proof framing: softened** — "instrumented with OpenTelemetry, run `/nav:stats`"; efficiency panel labeled "example output".

## Phase 0 — DONE (2026-06-24)
Scaffolded `../navigator-site`: Next.js 15 + Nextra 4 + Pagefind, mirroring Pilot's `pilot/docs`. Landing
(`content/index.mdx`) + section shells (getting-started, concepts ×6, skills, configuration, integrations + pilot,
reference, community). **Build green** (20 static pages, Pagefind 15); dev serves all routes 200, unknown → 404.
Companion docs moved into `navigator-site/docs/` (landing raws + IA). Git initialized; 2 commits.

⚠️ **GOTCHA (pin exactly):** Nextra 4.6.1 + **zod ≥4.4** → every page 500s with
`Invalid input: expected nonoptional, received undefined → at children` (zod 4.4 regressed how Nextra's
`LayoutPropsSchema` validates the stripped `children` field). Fix = `overrides: { "zod": "4.3.6" }` + pin
`next@15.5.12`, `react@19.2.4` to match Pilot's lockfile. Do NOT float these with carets.

## Phase 2 — Skill docs DONE (2026-06-24)
Authored 23 per-skill MDX pages via 8 parallel agents (each read the real `SKILL.md`, no invented features),
grouped `content/skills/_meta.js`, and a full `skills/index.mdx` catalog. Build green (**43 static pages**, Pagefind
38); all live in production. Config/ops skills (nav-features, nav-upgrade, nav-sync-claude, nav-release) live in
those sections, not /skills.

## Phase 2 — Config/Reference/Integrations DONE (2026-06-24, commit 4839dfe)
17 detail pages via 8 parallel agents (source = CLAUDE.md sections + the real `SKILL.md`s + live `.nav-config.json`):
- **configuration/** (7): tom-features, loop-mode, task-mode, knowledge-graph, simplification, auto-update, pm-and-chat
- **reference/** (6): nav-config-schema, slash-commands, plugin-ops, performance, troubleshooting, migration
- **integrations/** (4): pm-tools, team-chat, grafana, multi-claude (deprecation tombstone → native Workflows)
- `_meta.js` ordering for all three sections; section index pages refreshed (Phase-2 placeholders removed).
- Softened metrics framing applied throughout (OTel + `/nav:stats`; sample figures labeled "example output").
- Build green (**60 static pages**, Pagefind 55); all verified 200 on production.

Schema-page audit surfaced live `.nav-config.json` keys NOT in CLAUDE.md (documented from the live file): whole
`pilot`, `multi_agent`, and all `*_hook` toggle blocks; sub-keys `loop_mode.{show_status_block,periodic_interval}`,
`simplification.{model,skip_patterns,max_file_size,preserve_comments,rules}`, `auto_update.last_check`. Slash-commands
page note: repo is **skills-only** (no `commands/` dir) — only the 5 canonical legacy `/nav:*` commands documented.

## Phase 2 — Concept bodies DONE (2026-06-25)
Expanded the 6 concept stubs into full mental-model pages via 4 parallel agents (source = `.agent/philosophy/*` +
CLAUDE.md): context-engineering, theory-of-mind, task-mode, loop-mode, knowledge-graph, autonomous-completion.
Concepts carry the "why" (philosophy/rationale); config keys deferred to `/configuration/*` (no duplication). Build
green (60 pages, Pagefind 55); all 6 verified 200 on production. **Phase 2 (docs migration) is content-complete.**

## Phase 3 — OG image + SEO DONE (2026-06-26)
Added a file-convention social card (`app/opengraph-image.tsx`, next/og 1200x630 wordmark) that cascades og:image + twitter:image to all 62 routes, a matching `twitter-image.tsx`, and a `%s — Navigator` title template (deep pages read e.g. "nav-loop — Navigator"). Verified live: https://navigator-site.vercel.app/opengraph-image returns a valid 1200x630 PNG; meta tags confirmed in built HTML.

**Remaining**: optional full brand identity (logo mark / palette / typography — site currently uses a text wordmark).

## Stale `jitd` plugin name — FIXED (2026-06-25, commit 36b06df)
Plugin was renamed jitd → navigator ~6 months ago but live install/usage docs still shipped the old name + wrong repo
(`jitd/official`, `nav-plugin`). Fixed: `docs/QUICK-START.md`, `.claude-plugin/README.md`, `docs/CONFIGURATION.md`,
`docs/DEPLOYMENT.md` (full jitd→navigator + nav-plugin→navigator pass), `skills/plugin-slash-command/SKILL.md` example
path, `.agent/system/project-architecture.md` + release SOP install examples. **Left intentional**: migration scripts
(`migrate-config.sh`, `post-install.sh`), legacy `/jitd:` detection in `nav-sync-claude`/`plugin-slash-command`
validators, CHANGELOG/release/archive history, `mem-036` rename pitfall. The site (`navigator-site`) was already clean
— Phase 2 authoring applied the correct install command on import. Note: `DEPLOYMENT.md` is still v1.0.x-era stale
beyond the name (shows a `commands` array, v1.0.0, hardcoded 92%/10x metrics) — separate cleanup if it matters.

## Phase 4 — Deployed (2026-06-24 on Vercel; moved to AWS 2026-10-08)
- **Production**: https://navigator.quantflow.studio — AWS since 2026-10-08. ECS service
  `navigator-docs` on the quantflow cluster (2 tasks, ALB host rule priority 40, health
  `/robots.txt`) behind CloudFront (alias on the shared distribution, wildcard cert); Route 53
  alias owned by stack `quantflow-domain-config` in `qf-studio/aws-infrastructure-pilot` (Nelya).
- **Source repo**: `qf-studio/navigator-docs` (private, local `~/Projects/startups/navigator-site`).
  `build.yml` → `ghcr.io/qf-studio/navigator-docs` on `main` and `prod-*`; `deploy-quantflow-aws.yml`
  mirrors to ECR `quantflow/navigator-docs` and deploys `quantflow-svc-navigator-docs`.
- **Future deploys**: push `main`, then `git tag prod-<version>-$(date +%s) && git push origin <tag>`
  (procedure: `.agent/sops/development/release-workflow.md` Step 7).
- Container-vs-Vercel parity checked 2026-10-07: standalone output, image optimizer off, CDN cache
  headers, favicon (health), sitemap enumerates every page (69), pagefind index served from
  `public/_pagefind`. The Vercel project `navigator-site` is retired.
- History: first live on Vercel 2026-06-24 (`navigator-site.vercel.app`); the custom domain waited
  on DNS until the AWS move replaced the Vercel CNAME plan. The Vercel project was deleted via
  CLI on 2026-10-08 (`vercel project rm navigator-site`); the site repo dropped its `.vercel` entries.

## Open questions (still needed for Phase 1–3)
1. **Brand identity** (logo/palette, OG image) — none exist yet; navbar uses a text wordmark for now.
2. **Pilot co-marketing**: keep Navigator's site product-pure (Pilot only as a docs integration page) or co-market the handoff on the landing?
3. **Business model**: always free/MIT, or future commercial tier? (affects CTA strategy)
4. **Skill docs**: hand-authored or auto-generated from SKILL.md frontmatter?

---

## Refs
- Research run: `wf_0777e387-af9`
- Site repo: `/Users/aleks.petrov/Projects/startups/navigator-site` (landing + docs shell, builds green)
- Landing raws: `navigator-site/docs/landing-page-raws.md`
- Docs IA: `navigator-site/docs/docs-site-IA.md`
- Pilot site reference: `/Users/aleks.petrov/Projects/startups/pilot/docs`
