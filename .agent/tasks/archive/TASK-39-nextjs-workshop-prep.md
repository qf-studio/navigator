# TASK-39: Next.js Workshop Prep — Templates, Patterns, Quickstart

**Status**: ✅ Completed — 2026-05-11 (bbcc598: templates + generators + NEXTJS-PATTERNS.md + validated dry run; workshop/ docs intentionally untracked in 2760653 — event-specific materials stay local; workshop delivered 2026-05-22; shipped in v6.12.0+ tags). Status closed retroactively 2026-07-09.
**Created**: 2026-05-11
**Workshop date**: 2026-05-22 (JSNation — Advanced Claude Code workshop)
**Priority**: High (11 days to ship)
**Depends on**: Live research of current Next.js 15+ App Router docs

---

## Summary

Extend Navigator's `frontend-component`, `backend-endpoint`, and `nav-init` skills with first-class Next.js (App Router) support, ship a `NEXTJS-PATTERNS.md` philosophy doc grounded in official docs, and provide a workshop quickstart so attendees can replicate the live demo afterward.

The workshop builds a mobile-first **Conference Companion App** (schedule, speaker profiles, search, favourites) live, on stage, using Navigator. Today Navigator generates Express endpoints and generic React components — neither of which works inside a Next.js App Router project without manual rewriting. This task closes that gap.

**Headline outcomes**:
- `frontend-component` generates Server Components, Client Components (with `'use client'`), `page.tsx`, and `layout.tsx` when Next.js is detected
- `backend-endpoint` generates `app/api/[resource]/route.ts` Route Handlers with Zod validation and `NextResponse`
- Tailwind v4 is the default styling when Next.js is detected
- `.agent/philosophy/NEXTJS-PATTERNS.md` becomes the canonical reference, cited from generated CLAUDE.md
- Workshop attendees can install Navigator + scaffold the same app in <10 minutes from `workshop/QUICKSTART.md`

---

## Problem Statement

### Today's gap (verified by audit)

| Skill | Current behavior | Next.js need |
|---|---|---|
| `frontend-component` | Generic React FC, CSS Modules, `import React from 'react'` | Server Components default, optional `'use client'`, Tailwind classes, `page.tsx`/`layout.tsx` naming |
| `backend-endpoint` | Express `router.get(...)` handler in `src/routes/` | `app/api/.../route.ts` exporting `GET`/`POST` named functions, returning `NextResponse.json(...)` |
| `nav-init` | Detects `"next"` in deps but doesn't change output | Should emit Next.js-aware CLAUDE.md + link `NEXTJS-PATTERNS.md` |
| `frontend-test` | Jest + RTL (compatible) | Needs note on async Server Component testing |
| Philosophy docs | Zero Next.js coverage | Need patterns doc grounded in current official docs |

The `examples/nextjs-saas/` reference exists but is **docs-only** (CLAUDE.md, READMEs, TASK-XX templates) — there is no code template that gets emitted by a generator.

### Why this matters for the workshop

The workshop pitches Navigator's value as **"deep preparation → fast execution."** If we open a fresh folder, run `nav-init`, and Navigator generates Express routes that don't fit Next.js, the demo's central claim collapses. The fix isn't a workshop-only shim; it's making Navigator legitimately Next.js-aware so attendees can use it on Monday morning.

---

## Scope

### In scope
1. **Templates**: 4 new for frontend, 1 new for backend (server action optional)
2. **Generator changes**: `--framework nextjs` flag on both generators, Tailwind default when Next.js detected
3. **Detection**: `nav-init/project_detector.py` surfaces `framework: "nextjs"` explicitly so CLAUDE.md and generators can branch
4. **Patterns doc**: `.agent/philosophy/NEXTJS-PATTERNS.md` (research-grounded)
5. **Workshop docs**: `workshop/QUICKSTART.md` + `workshop/CONFERENCE-APP-SPEC.md`
6. **End-to-end dry run**: fresh empty folder → conference app skeleton

### Out of scope (workshop-day add-ons)
- Server Actions template — defer unless research says we need it for the demo
- Visual regression for Next.js
- Vercel deploy automation (workshop does this manually via Vercel CLI)
- Skill *new* (`nextjs-app`) — explicitly chosen: extend existing skills, not fork

---

## Plan

### Phase 1 — Research (RUNNING in background)
- Pull current Next.js 15+ App Router patterns from official docs via WebFetch
- 12 buckets covered: file structure, server/client components, composition, data fetching, route handlers, server actions, loading/error, dynamic segments, metadata, Tailwind v4 setup, mobile-first breakpoints, `next/image`
- Output feeds NEXTJS-PATTERNS.md and template content

### Phase 2 — Templates (depends on Phase 1)
**New files** under `skills/frontend-component/templates/`:
- `nextjs-page-template.tsx` — async Server Component, default export, optional `searchParams`/`params` typing
- `nextjs-layout-template.tsx` — `RootLayout` shape, `children: React.ReactNode`, metadata export
- `nextjs-client-component-template.tsx` — `'use client'` on line 1, `useState`/`useEffect` ready, Tailwind classes
- `nextjs-server-component-template.tsx` — async function, `await fetch(...)` with cache option
- `tailwind-style-template.module.css` (or skip — Tailwind needs no module file)

**New file** under `skills/backend-endpoint/templates/`:
- `nextjs-route-template.ts` — exports `GET`, optional `POST`, uses `NextResponse`, Zod parse on body

### Phase 3 — Generator wiring
- `component_generator.py`: add `--framework` (default `react`, options `react|nextjs|vue`), `--variant` (`page|layout|client|server|simple`), Tailwind class injection on `nextjs`
- `endpoint_generator.py`: add `nextjs` to `--framework` choices, route generation path = `app/api/<resource>/route.ts`
- `style_generator.py`: when framework=nextjs → skip CSS module emission (Tailwind handles it) unless explicitly overridden
- `nav-init/project_detector.py`: add `framework` field to return dict (`nextjs|react|express|none`), wire into CLAUDE.md template

### Phase 4 — Docs
- `.agent/philosophy/NEXTJS-PATTERNS.md`: 12 patterns matching Phase 1 buckets, each with rule/why/code/source URL. Style matches `PATTERNS.md` and `ANTI-PATTERNS.md`
- Update generated `CLAUDE.md` template in `nav-init` to reference `NEXTJS-PATTERNS.md` when Next.js detected
- `workshop/QUICKSTART.md`: install Navigator → init in fresh folder → first component + route handler in <10 min
- `workshop/CONFERENCE-APP-SPEC.md`: the spec we'll demo against — schedule, speaker profile, search, favourites, mobile-first

### Phase 5 — Validation
- Fresh folder dry run: `~/Projects/tmp/nav-nextjs-test/`
- `npx create-next-app@latest .` → `nav-init` → generate page, client component, route handler
- Verify: TypeScript compiles, Tailwind classes render, `npm run dev` works, mobile viewport works
- Record friction → fix → re-run until clean

### Phase 6 — Ship
- Bump to v6.11.0 (skills additions = minor)
- Update CHANGELOG + release notes
- Commit + tag + publish
- Optional: stream the dry-run as a teaser

---

## Acceptance Criteria

- [ ] Research agent produces 12 patterns with official-doc URLs cited
- [ ] `frontend-component --framework nextjs --variant page` writes a valid `page.tsx` that runs in `next dev`
- [ ] `frontend-component --framework nextjs --variant client` produces a file with `'use client'` on line 1
- [ ] `backend-endpoint --framework nextjs` writes `app/api/<resource>/route.ts` with named `GET`/`POST` exports
- [ ] `nav-init` in a Next.js project emits CLAUDE.md that links to `NEXTJS-PATTERNS.md`
- [ ] `NEXTJS-PATTERNS.md` exists, ≥12 patterns, each cites a `nextjs.org` URL
- [ ] `workshop/QUICKSTART.md` walks fresh folder → working conference-app skeleton in <10 minutes
- [ ] End-to-end dry run produces a `next dev` server that serves a mobile-responsive page
- [ ] All Navigator unit tests still pass (`nav-workflow` 91 tests, `nav-simplify` 20 tests)
- [ ] No regression in non-Next.js component/endpoint generation (React + Express still work)

---

## Files Touched (estimated)

**New**:
- `skills/frontend-component/templates/nextjs-page-template.tsx`
- `skills/frontend-component/templates/nextjs-layout-template.tsx`
- `skills/frontend-component/templates/nextjs-client-component-template.tsx`
- `skills/frontend-component/templates/nextjs-server-component-template.tsx`
- `skills/backend-endpoint/templates/nextjs-route-template.ts`
- `.agent/philosophy/NEXTJS-PATTERNS.md`
- `workshop/QUICKSTART.md`
- `workshop/CONFERENCE-APP-SPEC.md`

**Modified**:
- `skills/frontend-component/functions/component_generator.py`
- `skills/frontend-component/functions/style_generator.py`
- `skills/frontend-component/SKILL.md`
- `skills/backend-endpoint/functions/endpoint_generator.py`
- `skills/backend-endpoint/SKILL.md`
- `skills/nav-init/functions/project_detector.py`
- `skills/nav-init/templates/CLAUDE.md` (the generated-CLAUDE template)
- `CHANGELOG.md`
- `releases/RELEASE-NOTES-v6.11.0.md` (new)
- `.claude-plugin/marketplace.json`, `.claude-plugin/plugin.json` (version bump)
- `.agent/.nav-config.json`, `README.md`, `CLAUDE.md`, `.agent/DEVELOPMENT-README.md` (version bump)

---

## Risk Register

| Risk | Mitigation |
|---|---|
| Research surfaces patterns we disagree with (e.g., default caching change in Next.js 15) | Flag explicitly in NEXTJS-PATTERNS.md, document the "why" |
| Templates drift from real `create-next-app` output | Phase 5 dry run uses real `create-next-app` as fixture |
| Workshop demo hits a bug on stage | Phase 5 must complete by **2026-05-19** to leave 3 days for fixes |
| Existing React tests break due to generator changes | Keep `--framework react` (default) behavior byte-identical; new behavior is opt-in via flag |

---

## Workshop Tie-In

The workshop opens with **Research** as the named first stage. We're literally doing it now (research agent → NEXTJS-PATTERNS.md). That sequence becomes a live talking point: "Navigator made me research the official docs before generating a single line of code. Here's the patterns doc that came out — these are exactly the patterns that will be encoded in the templates I'm about to invoke."
