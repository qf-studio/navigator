# Navigator: Context-Efficient AI Development

## The Problem I Kept Hitting

I was working on a feature in Claude Code. Loaded all my project docs at session start—seemed smart. "Better to have everything available," I thought.

Five exchanges in, Claude started forgetting my recent changes. Six exchanges, it hallucinated a function that didn't exist. Seven exchanges, session died. Context window full.

I checked: **150,000 tokens loaded**. Only used **8,000**.

**I was wasting 94% of my context window on documentation I never needed.**

## The Realization

This wasn't a bug. This was my workflow.

Every AI coding session, same pattern:
- Load everything upfront ("just in case")
- Context fills with irrelevant data
- AI gets overwhelmed
- Session crashes
- Start over
- Repeat

**The default approach—load everything—was the problem.**

## What I Built

Navigator: A framework for loading only what you need, when you need it.

**How it works**:
1. Start with a 2k-token navigator (index of what exists)
2. Navigate to what you need (task docs, system architecture)
3. Load on-demand (3-5k tokens per document)
4. Progressive refinement (fetch metadata, drill down if needed)

**Result**: 150k → 12k tokens. **92% reduction.**

Not estimates. Real data, verified with OpenTelemetry.

## Why It Works

**The principle**: Load what you need, when you need it.

Not "load everything just in case."
Not "better safe than sorry."

Strategic loading beats bulk loading.

---

## Understanding Context Efficiency

**Philosophy & Principles**:
- [Context Efficiency Manifesto](./philosophy/CONTEXT-EFFICIENCY.md) — Why Navigator exists
- [Anti-Patterns](./philosophy/ANTI-PATTERNS.md) — Common mistakes (upfront loading, etc.)
- [Success Patterns](./philosophy/PATTERNS.md) — What works and why

**Learning Guides**:
- [Context Budgets](./learning/CONTEXT-BUDGETS.md) — Token allocation
- [Preprocessing vs LLM](./learning/PREPROCESSING-VS-LLM.md) — Tool selection
- [Progressive Refinement](./learning/PROGRESSIVE-REFINEMENT.md) — Metadata → details
- [Token Optimization](./learning/TOKEN-OPTIMIZATION.md) — Complete strategy

**Hands-on**:
- [TRY-THIS-LAZY-LOADING.md](./learning/examples/TRY-THIS-LAZY-LOADING.md)
- [TRY-THIS-AGENT-SEARCH.md](./learning/examples/TRY-THIS-AGENT-SEARCH.md)
- [TRY-THIS-MARKERS.md](./learning/examples/TRY-THIS-MARKERS.md)

**Decision frameworks**:
- [When to Compact](./learning/frameworks/WHEN-TO-COMPACT.md)
- [Agent vs Manual Read](./learning/frameworks/AGENT-VS-MANUAL.md)
- [Preprocessing Decision Tree](./learning/frameworks/PREPROCESSING-DECISION-TREE.md)

---

## Project Quick Start

**Project**: Claude Code plugin for Navigator
**Tech**: Markdown skills, JSON manifests, Python hook scripts
**Plugin version**: see `.claude-plugin/plugin.json` (currently v6.18.1)

**New here?** Read in order:
1. [Project Architecture](./system/project-architecture.md) — plugin structure, manifest, hook wiring
2. [Plugin Patterns](./system/plugin-patterns.md) — skill / hook / function design

**Working on a feature**:
1. Check `.agent/tasks/` for in-flight work
2. Read the relevant system doc
3. Check `.agent/sops/` for a matching procedure
4. Test in `/Users/aleks.petrov/Projects/tmp/nav-test`

**Fixing a bug**:
1. Check `.agent/sops/debugging/` for known issues
2. Query the knowledge graph: `"What do we know about <topic>?"` — `mem-*` pitfalls cover hook composition, blocking semantics, output channels, recursive-block traps
3. After fixing, capture the lesson as a memory or SOP if novel

---

## Task Completion Protocol (Autonomous)

When implementation is complete, run these without prompting:

1. **Simplify** code (if enabled and code was modified)
2. **Commit** with conventional message
3. **Archive** the task doc into `.agent/tasks/archive/`
4. **Close** the PM ticket (if configured)
5. **Create** a completion marker
6. **Suggest** a compact

**Exception cases — ask first**:
- Secrets in uncommitted files
- Multiple unrelated tasks modified
- Tests failing or implementation incomplete

---

## Documentation Structure

```
.agent/
├── DEVELOPMENT-README.md     ← this navigator
├── tasks/                    ← in-flight implementation plans (archive/ for shipped)
├── system/                   ← architecture documentation
├── sops/                     ← Standard Operating Procedures
│   ├── development/
│   ├── deployment/
│   ├── integrations/
│   └── debugging/
├── philosophy/               ← context-efficiency manifesto + patterns
├── learning/                 ← guides, examples, decision frameworks
├── knowledge/                ← project knowledge graph (graph.json + memories/)
├── research/                 ← nav-deep-research runs (query, report, gate; sources/ gitignored)
└── examples/                 ← real workflow case studies
```

### Research Reports (research/)

- `research/current-state-webgpu-support-across-chrome/report.md` — WebGPU support across Chrome, Firefox, Safari: status, platforms, limitations, per-engine feature table (22 sources, 2026-09-10; first live run on v7.3.0 plugin agents)
- `research/current-status-free-threaded-no-gil/report.md` — Free-threaded CPython as of September 2026: versions, single-thread cost, NumPy/pandas/Django readiness (15 sources, 2026-09-10; TASK-74 dry run)

---

## In-Flight Tasks

See `.agent/tasks/*.md` for current plans. Shipped work lives in `.agent/tasks/archive/`.

Current active threads (as of 2026-09-28; v7.0.0 tagged 2026-09-01, v7.1.0 + v7.2.0 TRIZ and v7.3.0 deep-research releases 2026-09-10, v7.4.0 readable reports 2026-09-12, v7.5.0 LSP-aware research 2026-09-13, v7.5.1 research provenance + v7.6.0 source lens 2026-09-14, v7.7.0 typed prompt judge 2026-09-19, v7.7.1 judge telemetry 2026-09-23, v7.8.0 team-repo batch 2026-09-28, v7.9.0 ADHD mode + multi-Claude removal 2026-10-01 — docs site synced through v7.8.0):

**v7.0.0 program — "Hooks as Runtime"** — ALPHA COMPLETE 2026-07-10 (uncommitted→committed same
day; local testing phase, no release tagged; critical path 57→59→60→61→62→64 all landed, 58/63
parallel both landed):
- **TASK-57** ✅ — spike: six channel verdicts recorded as mem-050..055 (CC 2.1.205)
- **TASK-58** ✅ — harness-conformance suite + checked-in cc-2.1.205 results, make conformance-check
- **TASK-59** ✅ — nav_hook_lib: nine stdlib modules, 217+ tests, scoring corpus ≤1 tier
- **TASK-60** ✅ — nav_dispatch fail-open dispatcher + registry + manifest rewrite (p95 ~41ms)
- **TASK-61** ✅ — nine v6 hooks ported to ops at golden byte-parity; old hooks deleted
- **TASK-62** ✅ — prompt_tier1, stop_completion, jit_memory, failure_diagnosis, subagent_context,
  config_guard, setup, graph_sync lifecycle events (13 manifest events, all validated)
- **TASK-63** ✅ — VERSION_CONFIGS["7.0.0"] additive migrator, template 47 lines, root CLAUDE.md
  annotated (mandates → hook enforcement), nav-sync-claude liveness guard
- **TASK-64** — release gate NOT run (alpha is local-only by decision 2026-07-10); RC soak,
  Pilot sign-off, and rollback doc remain before any v7.0.0 tag

**Dogfood hardening** (live use of the alpha, 2026-07-10/11):
- **TASK-65** ✅ — stop_completion indicators derived from observable turn evidence
  (git clean, test cmd ran, .md/marker touched) instead of unpopulated state
- **TASK-66** ✅ — read_guard double-increment fixed (idempotent per tool_use_id;
  PreToolUse fires twice per Read)
- **TASK-67** ✅ — task-status vocabulary: plain-text statuses map to canonicals
- **TASK-68** ✅ — tier1 near-miss similarity telemetry + subagent_context deterministic top-K
- **TASK-69** ✅ — use-case content for the landing/docs site (work in navigator-site repo)
- **TASK-70** ✅ — exit signals accept HTML-comment wrapping (invisible in assistant output;
  verified live) + read-only Bash classifier kills "mutated the codebase" false-fires
- Tier-1 answers render as grot-style TUI cards (Pilot design language); sentinel wrapper
  dropped — block reasons render as plain text, so Tier-1 is self-safe via exact-match rail

Other threads:
- **GH-30…34** ✅ — team-repo batch, specced as GitHub issues (no TASK docs): personal
  config override `.nav-config.local.json` + `nav-features --local` (#30), per-person
  onboarding state under `~/.config/navigator/onboarding/<repo-id>/` (#31),
  `task_id_source: github` → `GH-<n>-slug.md` docs with PREFIX-<n> regexes in index /
  graph sync / lifecycle (#32), nav-init gitignore of runtime state + local config +
  onboarding (#33), deep-research ok-write supersedes blocked/skipped stub (#34).
  Released v7.9.0 2026-10-01 (`releases/RELEASE-NOTES-v7.9.0.md`: ADHD mode TASK-82, multi-Claude
  removal); v7.8.0 2026-09-28 (`releases/RELEASE-NOTES-v7.8.0.md`); docs site synced incl.
  a new `/skills/nav-features` page. First release whose specs live only in issues — the
  precedent for `task_id_source: github` in this repo, not yet switched on here
- **TASK-93** ✅ (v8.3.0, 2026-10-05) — Reply modes: `nav_hook_lib/reply_modes.py` holds the
  `MODES` table (ADHD, STE) and `ops/prompt_modes.py` replaces `prompt_adhd`;
  `hooks/mod/lib/reply_modes.ts` + `ops/prompt_modes.ts` mirror it. STE = ASD-STE100 Part 1
  sentence rules, `use ste` / `ste mode off`, own file `~/.config/navigator/ste-mode.json`,
  own block `ste_mode`. Blocks stack in table order (shape before sentences);
  `MAX_TOTAL_BLOCK_CHARS` asserted. Adding a mode = one row per runtime + a config block
  (recipe in `tasks/archive/TASK-93-reply-modes-ste.md`). Docs site synced with v8.3.1
- **TASK-82** ✅ — ADHD mode, now row 1 of `reply_modes.MODES` (TASK-93); the files named
  below were deleted in v8.3.0 and are listed for history only:
  `ops/prompt_adhd.py` + `nav_hook_lib/adhd.py` + `personal.py`.
  Exact phrases `adhd mode on|off|status` answer via decision:block (zero model turn) and
  write the person's switch (`~/.config/navigator/adhd-mode.json`); while on, the reply-shape
  rule block (~206 tokens) rides every UserPromptSubmit; repo pin `adhd_mode.on`. Released
  v7.9.0 2026-10-01 together with the hard removal of the multi-Claude orchestration (skills,
  scripts, templates, SOPs, `multi_agent` block; TASK-25 archived). Lessons: subprocess test
  suites must set `NAVIGATOR_CONFIG_HOME` or a developer's own switch leaks into golden/
  dispatch output; `stop_completion` reads `python3 - <<EOF` heredocs as mutating (unknown
  command → over-fire direction), so read-only diagnostic turns can trigger a forced
  continuation in this repo where `continue_enabled` is on. Docs site synced same day
- **TASK-83** ✅ — Claude Code mods spike: `mods/nav-status/` (in-process band + ADHD
  injection, loaded via `--plugin-dir`); Python op defers through `config.mod_owns`.
  The spike became the v8 runtime (TASK-84, v8.0.0); `mods/nav-status/` is superseded by
  `hooks/mod/` (`tasks/TASK-83-mods-spike.md`).
- **TASK-97** ✅ (v8.3.3, 2026-10-07) — one plugin-root resolver for skills. `CLAUDE_PLUGIN_ROOT`
  is unset in the Bash tool and the old cache fallback lacked the version segment, so
  session_start now writes the real root to `~/.config/navigator/plugin-root` on every start
  and every `SKILL.md` reads it with one two-line snippet (env var → file → marketplace
  clone), pinned by `tests/test_skill_plugin_root.py`
  (`tasks/archive/TASK-97-plugin-root-resolver.md`).
- **TASK-96** ✅ (v8.3.3, 2026-10-07) — stop gate read-only shapes among unknown heads:
  `2>/dev/null;` no longer captured as a write, `(`/`{`/`name() {` bodies classified by
  what runs inside, `gh run watch`, `claude plugin list|validate|test|update`, `python3 -m
  json.tool`, `awk` without `>` and `make` with only test-shaped targets read; four-day
  replay mutating 474 → 419, no real write flipped
  (`tasks/archive/TASK-96-stop-gate-unknown-heads.md`).
- **TASK-95** ✅ (v8.3.2, 2026-10-06) — stop gate `code_committed` no longer fails on untracked
  paths (`??` lines skipped unless the turn touched them), a mutating Bash command that names a
  `.md` counts as `docs_updated`, `make mod-test` counts as a test run. The heredoc bucket
  TASK-94 named next was measured at 0 flips (every heredoc feeds `python3 -` or follows a
  `>`) and is retired; `scripts/stop_gate_replay.py` buckets mutating calls by blame head
  (`tasks/archive/TASK-95-stop-gate-untracked-files-heredoc-retired.md`).
- **TASK-94** ✅ (v8.3.1, 2026-10-05) — the Bash read-only classifier masks quoted spans before
  the redirect and segment scans, so `grep "a\|b"`, `--jq '.a | .b'` and `printf "%s | %s"`
  no longer read as mutating; 134 of 522 verdicts in a three-day replay flip, zero real
  writes (`tasks/archive/TASK-94-bash-classifier-quote-aware.md`).
- **TASK-92** ✅ (v8.2.8, 2026-10-05) — stop gate no longer fires on turns whose only action is
  a read-only subagent (Explore, Plan, claude-code-guide, navigator-research, task-planner);
  unknown agent types still count as mutating (`tasks/archive/TASK-92-readonly-agents-not-task-actions.md`).
- **TASK-91** ✅ (v8.2.7, 2026-10-05) — in-progress task detection (the `/nav` next card and
  the compact marker's task list) reads the `**Status**` line only; a finished doc that quotes
  "in progress" in prose no longer surfaces as the destination
  (`tasks/archive/TASK-91-in-progress-status-line.md`).
- **TASK-90** ✅ (v8.2.6, 2026-10-05) — stop gate no longer fires on Bash-only turns that
  `cd` or call `/bin/ls`: `cd` is read-only, absolute-path heads resolve to their basename
  before the allowlist lookup (`tasks/archive/TASK-90-stop-gate-cd-and-path-heads.md`).
- **TASK-89** ✅ (v8.1.2, 2026-10-05) — the `/nav` pane follows Bash edits, `git mv` /
  commits and subagent runs (not only Edit/Write), and the next card advances mid-turn from the
  active doc's checklist (`tasks/archive/TASK-89-pane-follows-bash-and-agent-edits.md`).
- **TASK-88** ✅ (v8.2.0, 2026-10-05) — reject log: a refusing op attaches `reject: {reason,
  evidence}`; the runtime (one append point per runtime) writes one JSON line to
  `.agent/.nav-rejects.jsonl`, bounded to 500, `reject_log.enabled` default on, `suppressed: true`
  under Pilot; `/nav` shows today's count under reads and the tail behind `l`
  (`tasks/archive/TASK-88-reject-log.md`). Follow-up patches v8.2.1–v8.2.5: rejects on two
  lines, the next row keeps one sentence of the reply, and below 72 columns the top cards
  stack, the gauge fills the card, the judge version takes its own line and the next card
  wraps (`hooks/mod/ui/nav.ts` `paneLayout`).
- **TASK-87** ✅ (v8.1.1, 2026-10-04) — reads made through read-only Bash (`cat`, `sed -n`,
  `head`, `grep`…) count in the `/nav` reads card like the Read tool; `sed` without `-i` joins
  the read-only allowlist in both runtimes (`tasks/archive/TASK-87-bash-reads-count.md`).
- **TASK-86** ✅ (v8.1.0, 2026-10-03) — judge decision trail behind `j` in `/nav` and `y`/`x`
  labeling into `~/.config/navigator/judge-labels.json`, the shape `scripts/judge_label.py` and
  `judge_eval.py --fixture` read (`tasks/archive/TASK-86-judge-trail-labels.md`).
- **TASK-85** ✅ (v8.0.1, 2026-10-03) — stop_completion over-fired on read-only turns when
  two sessions shared a repo: the tree digest now lives per session in `tree.digests` outside the
  session-scoped `completion`; `lsof`/`pgrep`/`curl` (no output flag) join the read-only
  allowlist; the mod also trusts Claude Code's `isReadOnly` on every Bash call of a turn
  (`tasks/archive/TASK-85-stop-gate-shared-state.md`).
- **TASK-84** ✅ (v8.0.0, 2026-10-03) — v8 runtime: all 16 ops in the mod at byte parity (Python stays as fallback),
  `/nav` cards (context · session, Prometheus-fed when the local stack answers · judge verdict
  after a judged prompt · next = the current leg as a press with an ETA, legs from the checklist
  or numbered plan · off-route park/back/switch · memories with pinning · reads and tasks behind
  `d`), one-line
  band, Pilot theme, update notice (TASK-81), v6 shims deleted, `--verify-mod` release gate.
  Released as v8.0.0 after a live dogfood day (`tasks/archive/TASK-84-v8-mod-runtime.md`,
  section "Resume here").
- **TASK-81** ✅ — auto-update truth: read-only release notice from the mod (v8.0.0),
  nav-start Step 1.5 is one `auto_updater.py` call, the hook drift check reads the plugin
  manifest instead of `claude plugin list`, docs and site say "notifies, never self-updates"
  (2026-10-05, `tasks/archive/TASK-81-auto-update-truth.md`)
- **TASK-80** ✅ closed 2026-10-05 — judge phase 2: override telemetry + labeling tooling
  shipped v7.7.1; 286 judged prompts in this repo (task overridden 39, ambiguity 20); real-set
  labeling not pursued (0/365), memory rerank rejected without an eval
  (`tasks/archive/TASK-80-judge-phase2-plan.md`).
- **TASK-79** ✅ — typed prompt judge: `nav_hook_lib/judge.py` asks Jev (TypeSafe) eight
  typed questions per prompt; decisive axes override the loop-trigger / complexity /
  ambiguity keyword scorers in prompt_gate + prompt_brief, everything else falls back.
  60-prompt eval: tier 38 → 53/60. Ships OFF (`judge.enabled`), ON in this repo. Released
  v7.7.0 2026-09-19; next surface (own task): memory relevance rerank in memory_recall.py
- **TASK-78** ✅ — source lens + corroboration: the search lens (canonical/breadth/
  adversarial/gap) travels from the queue into the note, the digest and the Sources
  table; thirteenth gate check rejects a finding resting on a single breadth source;
  fifth critic pass flags it first (shipped v7.6.0)
- **TASK-77** ✅ — research provenance: every cited URL in a deep-research memory carries
  `fetched YYYY-MM-DD, sha256 <12 hex>` from the local source note; wrapped Key findings
  bullets keep their cites (parser joined continuation lines) (shipped v7.5.1)
- **TASK-76** ✅ — LSP-aware research: `navigator-research` lists the `LSP` tool and uses it
  for symbol questions when a language-server plugin is present (Phase 1.5), Grep
  otherwise; `scripts/agent_tool_counts.py` counts tool calls per transcript; A/B on this
  repo halves context on a who-calls question (shipped v7.5.0)
- **TASK-75** ✅ — readable research reports: answer-first Summary, At-a-glance table,
  per-item sections, 700-char paragraph cap enforced by two new gate checks; writer
  reads `reference/REPORT-FORMAT.md` (shipped v7.4.0)
- **TASK-74** ✅ — nav-deep-research: web deep research (router + 6 step files, 4 agents,
  fenced source notes, deterministic ship gate, graph ingestion); ships OFF via
  `deep_research.enabled`; released v7.3.0, live run on plugin agents verified 2026-09-10
- **TASK-72** ✅ — TRIZ Phase 1: Contradiction row in the brief, optional
  contradiction/separation/principle on decision memories, `--action contradictions` query,
  IFR + reuse-inventory questions in research/planner agents (shipped v7.1.0)
- **TASK-73** ✅ — TRIZ Phase 2: `nav-triz` skill (three candidates from different
  separation modes + recommendation), `triz_suggest.py`, software-mapped principles reference
- **TASK-15** 📋 — marketing strategy & community adoption; postponed 2026-10-05 (owner posts on Threads + LinkedIn directly); refreshed 2026-10-05 against v8.2.7: seven live legs (Threads cut, drafts decision, screen capture, Show HN, CONTRIBUTING, marker-compression re-measure, monthly metrics), 2025 plan retired in an appendix
- **TASK-35** — project memory (research)
- **TASK-37** — nav-simplify complexity / cost scoring (design)
- **TASK-55** — landing + docs site: built + deployed (navigator-site.vercel.app); only DNS cutover left

Closed 2026-07-09: TASK-05/13 (superseded by TASK-55), TASK-39 (workshop delivered 2026-05-22), TASK-42 (audit roadmap complete incl. wp12 security re-sweep), TASK-56 (nav-brief, shipped v6.18.0).

For shipped scope, query the knowledge graph or browse `CHANGELOG.md` / `releases/RELEASE-NOTES-*.md`.

---

## System Architecture

- [Project Architecture](./system/project-architecture.md) — plugin file layout, skill manifest, hook registration, settings flow
- [Plugin Patterns](./system/plugin-patterns.md) — skill design, predefined functions, hook lifecycle, three-layer Model/Hooks/Harness discipline

---

## Standard Operating Procedures

**Development**:
- [Release Workflow](./sops/development/release-workflow.md) — canonical end-to-end release SOP (SSOT, 6-file bump, CI publish, semver)
- [Autonomous Completion](./sops/development/autonomous-completion.md) — what to do without being asked
- [Pane Theme Colors](./sops/development/pane-theme-colors.md) — Ghostty bg ↔ `composerSidebarBackground` ↔ pane `PALETTE`; keys list, install, verify (DEV-004)

**Integrations**:
- [OpenTelemetry Setup](./sops/integrations/opentelemetry-setup.md) — real-time session metrics, ROI measurement
- [Typed Prompt Judge Setup](./sops/integrations/typesafe-judge-setup.md) — TypeSafe key, `enable judge`, `--check`, config keys, troubleshooting (v7.7.0)

**Deployment**:
- [Plugin Release](./sops/deployment/plugin-release.md) — pre-release checklist, tag → CI workflow, post-release verification

**Debugging**:
- [Knowledge-Graph Memory Corruption](./sops/debugging/knowledge-graph-memory-corruption.md) — diagnose junk/duplicate memories, clean via remove-node + resolved/ archiving, fix the ingester
- Document as discovered. Capture novel diagnoses as memories in the knowledge graph (`mem-XXX.md` under `.agent/knowledge/memories/`).

---

## Lifecycle Hooks (v8: mod first, v7 dispatcher as fallback)

**v8 (TASK-84)**: every op also exists as TypeScript in the Navigator **mod**
(`hooks/hooks.json` → `hooks/mod/register.tsx`, Claude Code ≥ 2.1.287). The mod runs the ops
in-process, announces what it owns in `NAVIGATOR_MOD_OWNS`, and the Python dispatcher below
skips owned ops (one check in `runtime._dispatch`, fast exit when an event is fully owned).
Both share `.agent/.nav-runtime-state.json`. Layout: `hooks/mod/{register.tsx, runner.ts,
owns.ts, ops/, lib/, ui/, tests/}`; `$` never crosses an import (an `Io` port built in
register.tsx does). Parity: `scripts/gen_mod_data.py` runs the Python ops over generated
corpora and writes `hooks/mod/tests/fixtures/*.gen.ts`; `make mod-test` asserts byte equality;
`release_validator.py --verify-mod` gates releases. UI: `/nav` pane, status band, Pilot theme.
Pane model is pure (`hooks/mod/ui/route.ts` steps + band, `ui/trip.ts` Prometheus queries); the
trip panel reads the `.agent/grafana/` Prometheus (:9092) with `curl`, loopback only, because
`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` makes the engine refuse every plugin `$.http.fetch`.

The v7 description below still applies to the Python fallback.

Navigator registers ONE hook command per Claude Code event via the plugin manifest (`.claude-plugin/plugin.json`): `python3 hooks/nav_dispatch.py <event>`. The dispatcher loads shared runtime services from `hooks/nav_hook_lib/` (config layering, schema-2 state, sentinels/redaction, budget clamps) and routes each event to the ops registered in `hooks/nav_hook_lib/registry.py`, executing them in phase order (gate → injector → recorder). The nine v6 per-hook scripts were ported byte-parity to `hooks/ops/` in TASK-61 and deleted; `tests/golden/` locks the recorded v6 stdout/exit behavior.

Hook commands resolve via `${CLAUDE_PLUGIN_ROOT}` (the installed plugin directory) with a marketplace-path fallback (mem-036: the unset-env path is contract-tested, never a silent no-op). Per-turn/session state lives in `.agent/.nav-runtime-state.json` (`"schema": 2`); the v6 per-hook state files are archived to `.agent/.nav-v6-state.bak/` by the SessionStart op — never deleted, `.agent/.context-markers/` untouched.

### What ships

| Op (`hooks/ops/`) | Event (phase) | Purpose |
| --- | --- | --- |
| `session_start.py` | SessionStart (injector) | Inject navigator + active marker + config + graph stats + profile into context; emit `<!-- nav-session-start-injected:v1 -->` sentinel so `nav-start` skips re-Reads; archive v6 state files to `.nav-v6-state.bak/` |
| `compact_marker.py` | PreCompact + PostCompact (recorder) | PreCompact: snapshot conversation + git state + active tasks into `before-compact-{manual,auto}-{ts}.md`, set `.active` marker. PostCompact: append Claude Code's compact summary to that marker |
| `graph_sync.py` | PostToolUse Write/Edit on `.agent/tasks/TASK-*.md` (recorder) | Upsert task node into the knowledge graph |
| `stop_state.py` | Stop (recorder) | Record per-turn signal (`check_shown` tristate, `nav_status_shown`, `loop_phase`, `tools_used`) into the schema-2 state file; the single audited turn-lifecycle reset barrel (read counter + tier-1 fuse slot + continue-counter slot) |
| `profile_sync.py` | PostToolUse Write/Edit on `.user-profile.json` (recorder) | Convert new corrections into graph memories |
| `prompt_gate.py` | UserPromptSubmit (gate) | Soft-warn on Loop Mode trigger, hard-block (exit 2) when prior turn skipped WORKFLOW CHECK AND `strict_block=true` (config key stays `workflow_enforcer_hook`) |
| `prompt_brief.py` | UserPromptSubmit (injector) | Score prompt ambiguity (TASK-56, shipped v6.18.0); on ambiguous task-shaped prompts inject a NAV-BRIEF instruction + relevant graph memories so the model renders an intent brief before implementing. Never blocks (exit 0 only — mem-034). Composes with `prompt_gate` on the same event. Live-validated 2026-07-09: full cycle (brief → confirmation → BRIEF DRIFT on scope growth → re-confirmation) ran on a real bug, and the hook's own memory recall surfaced the graph corruption fixed in v6.18.1 — see `sops/debugging/knowledge-graph-memory-corruption.md` |
| `prompt_modes.py` | UserPromptSubmit (responder) | Reply modes (TASK-82 ADHD, TASK-93 STE): exact phrases `<key> mode on/off/status` for every row of `reply_modes.MODES` flip or report that mode's personal switch (`~/.config/navigator/<key>-mode.json`) via decision:block at zero model invocation; while any mode is on, injects the active rule blocks (table order) on every prompt ahead of the brief. Repo pin `<key>_mode.on` wins, `<key>_mode.enabled: false` hides a mode; silent under Pilot and while the mod owns the op (`config.mod_owns`) |
| `read_guard.py` | PreToolUse Read on `.agent/` (gate) | Count non-allowlisted reads per turn; warn at 3, block at 5 (`strict_block=true`); deny-only channel (mem-035) |

### Composition lessons captured

- **mem-027** — three-layer Model / Hooks / Harness architecture; blocking-hook gating discipline
- **mem-034** — UserPromptSubmit exit-2 bypasses the model; stderr addresses the user; recursive-block trap via echoed trigger phrases
- **mem-035** — PreToolUse `stdout` and `hookSpecificOutput.additionalContext` are silently dropped; only `exit 2` + stderr affect behavior
- **mem-037** — Stop hook emitting state on non-task turns deadlocks the next loop-trigger prompt; emit conditionally (v6.15.3 tristate fix)

Query: `"What do we know about hooks?"` returns the full memory set + their cross-edges.

### Configuration

Each op keeps its v6 `*_hook.enabled` toggle in `.agent/.nav-config.json` (config keys unchanged: `session_start_hook`, `compact_hook`, `task_graph_sync_hook`, `workflow_state_hook`, `profile_sync_hook`, `workflow_enforcer_hook`, `brief_hook`, `read_guard_hook`). Defaults are all `true`. The two gates (`prompt_gate` via `workflow_enforcer_hook`, `read_guard` via `read_guard_hook`) additionally take `strict_block`. `brief_hook` additionally takes `ambiguity_threshold` (default 0.5) and `memory_budget_chars` (default 1200). See `nav-features` skill for the interactive toggle UI.

Since v7.8.0 (GH-30) `nav_hook_lib.config.load` reads two files over `DEFAULTS`: the committed `.agent/.nav-config.json`, then the gitignored `.agent/.nav-config.local.json` (personal; dict-wise merge, scalars replace; missing or corrupt local file changes nothing). `nav-features enable|disable <feature> --local` writes the local file; `show` marks locally decided rows with `L`; `config_guard` validates both files. Top-level `task_id_source` (`local` | `github`, GH-32) tells nav-task where a new ID comes from.

---

## When to Read What

**Scenario: adding a new skill**
1. This navigator
2. `system/plugin-patterns.md` → skill structure
3. Look at a similar shipped skill in `skills/`
4. Use `nav-skill-creator` skill or hand-author
5. Register in `.claude-plugin/plugin.json` skills array

**Scenario: changing hook behavior**
1. Read the relevant hook in `hooks/`
2. Check `mem-027/034/035/037` for composition constraints
3. If changing a blocking hook: explicit design review against three-layer architecture
4. Add an end-to-end smoke test that covers the cooperating-hook composition, not just unit behavior

**Scenario: answering a question about the codebase or the outside world**
1. Codebase → the `navigator-research` agent. With a language-server plugin installed
   (pyright-lsp, typescript-lsp, gopls-lsp) it uses the `LSP` tool for symbol questions
   and Grep otherwise; see its Phase 1.5
2. Outside world → `"Deep research on X"` (nav-deep-research, ships OFF via
   `deep_research.enabled`). Output lands in `research/<slug>/` and the graph
3. Either way, check the knowledge graph first: `"What do we know about X?"`

**Scenario: releasing a new version**
1. `sops/development/release-workflow.md`
2. Run `release_validator.py --check-all` and `--verify-hooks`
3. `./scripts/bump-version.sh X.Y.Z` — updates the five canonical version files
   (marketplace.json, plugin.json, README.md badge, CLAUDE.md, .nav-config.json) and
   re-validates. Author `releases/RELEASE-NOTES-vX.Y.Z.md` and the CHANGELOG entry by hand
4. Commit both (feature commit, then `chore(release): prepare vX.Y.Z`), push, then tag →
   CI publishes via `release.yml`. Never `gh release create` locally
5. Verify with `release_validator.py --verify-tag vX.Y.Z`
6. If `release.yml` fails only on `test_user_prompt_submit_p95_under_200ms`, it is runner
   noise (p95 vs a 200 ms ceiling): `gh run rerun <id> --failed`, then re-verify. Never
   `gh release create` locally. `--verify-hooks` `[unset]` failures on this laptop are the
   missing `~/.claude/plugins/marketplaces/` fallback dir, not a regression
7. Sync the docs site (`~/Projects/startups/navigator-site`, no git remote): `lib/version.ts`,
   touched skill/config pages, `bun run build && vercel --prod --yes`, then curl the live
   version string

**Scenario: investigating a session deadlock or unexpected block**
1. Read `.agent/.nav-runtime-state.json` — the single schema-2 state file every op reads
   and writes. `turn` is what the Stop ops recorded, `reads` the read-guard counter,
   `completion` the stop-completion indicators, `meta.op_errors` any op that failed open.
   (`.nav-workflow-state.json` and `.nav-read-counter.json` are frozen v6 files, kept for
   forensics only — nothing writes them since v7.0.0.)
2. Reproduce the event headlessly: `echo '<payload>' | python3 hooks/nav_dispatch.py <Event>`
3. Query `"What do we know about hooks?"` for known pitfalls
4. If novel, capture as `mem-XXX.md` under `.agent/knowledge/memories/pitfalls/`

---

## Token Optimization Strategy

**Per session**:
- Always: `DEVELOPMENT-README.md` (~2k tokens) — injected by SessionStart hook, not Read
- Current work: task doc (~3k)
- As needed: system doc (~4-6k)
- If helpful: SOP (~2k)
- **Total**: ~9-13k vs ~150k loading everything (90%+ savings)

The SessionStart hook itself eliminates ~6 Read calls and ~1.5-2k tokens of tool-call ceremony per session boot.

---

## Development Workflow

```bash
# Local plugin testing
/plugin marketplace add file:///Users/aleks.petrov/Projects/startups/navigator
/plugin install navigator

# Test changes in nav-test
cd ~/Projects/tmp/nav-test
# invoke skill or hook via natural language
```

**Release**: see `sops/development/release-workflow.md`.

---

## Natural Language Reference

```
"Start my Navigator session"
"Initialize Navigator in this project"
"Archive TASK-XX documentation"
"Create an SOP for debugging [issue]"
"Update system architecture documentation"
"What do we know about <topic>?"
"Deep research on <topic>"            # web research → cited report → graph memories
"Find a better solution for <X>"      # nav-triz, when a contradiction is declared
"Enable judge"                        # typed prompt judge; needs TYPESAFE_API_KEY (sops/integrations/typesafe-judge-setup.md)
"Remember this pitfall: ..."
"Clear context and preserve markers"
"Release plugin"
```

---

**Last Updated**: 2026-10-07 (v8.3.3 — TASK-96 stop gate unknown-head read-only shapes + TASK-97 one plugin-root resolver; v8.3.2 — TASK-95 stop gate ignores untracked paths, heredoc bucket retired; v8.3.1 — TASK-94 quote-aware Bash classifier; v8.3.0 — TASK-93 reply modes table + STE mode, `prompt_adhd` → `prompt_modes`; v8.2.8 — TASK-92 read-only subagents are not task actions; v8.2.7 — TASK-91 in-progress detection reads the Status line; v8.2.6 — TASK-90 stop-gate over-fire on `cd` / `/bin/ls`; v8.2.0–v8.2.5 — reject log TASK-88 + five `/nav` pane patches: rejects two lines, next row one sentence, narrow layout below 72 columns, stacked gauge/judge/next adapt; TASK-80 closed by decision; v8.1.x — judge trail TASK-86, Bash reads TASK-87, pane follows all doc edits TASK-89, hook-safe drift check TASK-81; v8.0.0 — mod runtime TASK-84; v7.9.0 — ADHD mode TASK-82 + multi-Claude removal; v7.8.0 — team-repo batch GH-30…34: local config override, per-person onboarding, GitHub task IDs, nav-init gitignore, deep-research stub supersede; v7.7.1 — judge override telemetry + real-session eval tooling TASK-80; v7.7.0 typed prompt judge TASK-79; earlier: source lens + `findings-corroborated` gate check TASK-78 v7.6.0)
**Powered By**: Navigator (Complete Framework)
