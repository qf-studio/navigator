# TASK-74: nav-deep-research — web deep research for Navigator

**Status**: ✅ Released v7.3.0 + live run verified — 2026-09-10 (ships OFF by default; enabled in this repo for dogfood)

**Follow-up**: report layout made answer-first with two extra gate checks in v7.4.0 (TASK-75).

## Context

**Problem**: Navigator's research is codebase research (`agents/navigator-research.md`)
feeding the knowledge graph. There was no path from "what does the world know about X"
to a cited report and graph memories.

**Reference**: hyperresearch (github.com/jordan-gibbs/hyperresearch), a 16-step Claude
Code deep-research harness. We ported its light tier natively: no pip dependencies, no
SQLite vault, no academic APIs, no browser lane. Existing codebase research is untouched.

**Contradiction resolved**: deeper research (many sources, many steps) worsens
Navigator's lean context budget. Separation in space: fetching, drafting, critique and
patching run in subagents; the main session sees digests, findings and the final report.
Ships OFF (repo precedent: new feature value vs regression risk → opt-in toggle).

## Implementation

- `skills/nav-deep-research/SKILL.md` — thin router: enabled check, functions-dir
  resolver, pipeline table, spawn contract, invariants, recovery table, hyperresearch
  handoff. Step procedures in `steps/1-decompose.md … 6-ship.md` are loaded with `Read`
  when each step starts (hyperresearch's context-rot defense without six plugin.json
  entries).
- `agents/deep-research-fetcher.md` (sonnet; Bash, Read, Write, WebSearch, WebFetch),
  `deep-research-writer.md` (opus; Read, Write, Bash), `deep-research-critic.md` (opus;
  Read, Grep, Bash, Write — no Edit), `deep-research-patcher.md` (opus; Read, Edit,
  Write — no Bash). Every prompt opens with the spawn-contract slots.
- `skills/nav-deep-research/functions/` (stdlib, 64 unit tests):
  - `research_run.py` — `init/step/set/resume/status/list`; manifest first, artifact
    scan fallback; `backend: hyperresearch` when `.hyperresearch/` exists.
  - `untrusted.py` — `<nav-untrusted-source url="…">` fence with treat-as-data preamble,
    forged-tag neutralization, escaped URL attribute.
  - `source_store.py` — `fetch/write/list/digest/refetch`; canonical-URL dedup,
    blocked/skipped classification, 40k clamp, sha256, html.parser text extraction.
  - `report_parse.py` — the citation contract (`[n]`, Sources table, typed Key findings).
  - `ship_gate.py` — ten deterministic checks, exit 1 on failure, `ship.json` only on
    pass.
  - `report_to_graph.py` — Key findings bullets → `research_to_graph.ingest_findings`
    with cited URLs folded into evidence text (no graph schema change).
- `hooks/ops/read_guard.py` — allowlist entries ending in `/` match by prefix;
  `research/` added to `DEFAULT_ALLOWLIST` and `config.DEFAULTS` (subagents reading
  many source notes in one turn would otherwise hit the escalate threshold).
- Config: `deep_research` block in `hooks/nav_hook_lib/config.py` DEFAULTS,
  `VERSION_CONFIGS["7.3.0"]` in the migrator, `FEATURES["deep_research"]` in
  nav-features. Defaults: enabled false, max_sources 30, min_sources 8, fetchers 4,
  max_full_reads 10, critic_enabled true, models fetcher sonnet / others opus.
- Wiring: `.claude-plugin/plugin.json` skills entry; `.gitignore`
  `.agent/research/*/sources/`; Makefile TEST_DIRS; cross-refs in
  `agents/navigator-research.md` and `skills/nav-graph/SKILL.md`.

## Workspace layout

```
.agent/research/<slug>/
├── query.md              verbatim query (gospel)
├── run.json              manifest: steps, atomic_items, meta
├── search-plan.md        three-lens search table (step 1)
├── sources/NNN.md        fenced notes (gitignored; refetch rebuilds)
├── report.md             written once (step 3), patched by hunks (step 5)
├── findings/critic.json  critic output (step 4)
├── patch-log.json        applied / rejected / unresolved (step 5)
└── ship.json             gate result, only on pass (step 6)
```

## Verification

- `make test` green (hooks 639, nav_hook_lib 307, golden 27, deep-research 64, migrator,
  features).
- WP7 end-to-end dry run DONE 2026-09-10 on "current status of free-threaded CPython"
  (`.agent/research/current-status-free-threaded-no-gil/`): 16 URLs → 15 ok + 1 blocked (429);
  writer 3031 words / 15 cited; critic 20 findings (1 critical: ignored 33% Mandelbrot outlier),
  every quote anchored; patcher applied 20/20; gate 10/10; removing one Sources row by hand
  fails `citations-resolve` + `sources-not-shrunk`; ingestion validated against a temp graph
  copy (11 memories, no errors) and deliberately NOT written to Navigator's own graph
  (off-topic); resume returns the right step from both manifest and stale-manifest artifact
  scan. Dry-run finding fixed: parallel fetchers raced on `next_id` → exclusive-create
  allocation (b58ea45). Caveat: the plugin agent types are not installed until the next
  release, so the dry run used general-purpose agents carrying the agent prompts; the
  frontmatter tool locks are therefore unverified live.
- Live re-run on the released plugin (2026-09-10, after restart, real
  `navigator:deep-research-*` agent types): "current state of WebGPU support across Chrome,
  Firefox and Safari" (`.agent/research/current-state-webgpu-support-across-chrome/`): 22/22
  URLs ok across 4 parallel fetchers with unique ids; writer 3533 words / 22 cited, pre-check
  10/10; critic 10 findings (2 critical) + 1 structural converted to an anchored finding;
  patcher applied 11/11 with Read+Edit+Write only (diff vs pre-patch copy: 69 lines changed,
  0.90 similarity — patched, not regenerated); gate 10/10. Tool locks verified live.
- Original plan for WP7 (kept for the post-release re-run): WP7 end-to-end dry run — enable `deep_research`, `fetchers: 2`,
  `max_sources: 8`, run a question with a known answer; confirm the read guard does not
  block the writer, the gate fails when a citation is removed by hand and passes after
  restore, `report_to_graph.py --dry-run` lists the memories, and `resume` returns step
  3 after killing the session mid-draft. Spot-check three citations.

## Accepted limitations

- WebFetch fallback returns model-summarized text; such sources (`fetch_method:
  webfetch`) may be paraphrased, never quoted. The gate has no verbatim oracle.
- WebSearch quality varies; one gap wave and `min_sources` are the backstop.
- Sources are gitignored; re-critiquing an old run needs `source_store.py refetch`.
- `source_store.py fetch` makes allowlist-free outbound HTTP from Bash: stdlib only, no
  cookies, 2 MB read cap, 20 s timeout.
- No PDF extraction: PDF URLs are recorded as `skipped`.

## Not done (future)

- Full tier (loci analysis, multi-draft synthesis, four critics).
- Source quality scoring, retraction checks, open-access recovery.
- Cross-run vault: each run is independent; reuse happens via the knowledge graph.
