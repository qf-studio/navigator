# Changelog

All notable changes to Navigator are recorded here. Detailed per-version notes live in [`releases/`](./releases/); each link below points to the full file. Versions without a release notes file have only summary lines.

This project follows [Semantic Versioning](https://semver.org/). The authoritative source of truth for versions is [`.claude-plugin/marketplace.json`](./.claude-plugin/marketplace.json) — see [`sops/development/version-management.md`](./.agent/sops/development/version-management.md).

---

## [v7.7.1] — 2026-09-23 — "Count What the Judge Does"

Override telemetry and real-session eval tooling for the typed judge (TASK-80, workstreams
A and B). No behavior change to gating; `judge` still ships off.
→ [Full release notes](./releases/RELEASE-NOTES-v7.7.1.md)

- **Per-axis counters** in runtime state (`judge` section, 30-day TTL): calls, failures,
  last/max latency, and for loop / complexity / task / ambiguity whether the judge
  overrode the keyword decision, agreed, or stayed undecided. Counters only, no prompt text.
- **`nav stats`** carries two judge lines; the nav-stats skill report gains a row.
- **`scripts/judge_label.py`** extract / label / sheet / import / status: builds a
  private, gitignored set of real prompts from local transcripts (secret-redacted,
  deduplicated, subagent and hook echoes filtered) and labels it one key per prompt.
  `scripts/judge_eval.py` skips unlabeled rows.
- First live read after four days, 92 judged prompts: 4 overrides, all on the task axis;
  loop and complexity agreed every time. Recorded in TASK-80.

---

## [v7.7.0] — 2026-09-19 — "Judge, Then Fall Back"

The prompt-time keyword scorers get a typed judge behind them (TASK-79). One request per
prompt to TypeSafe's Jev answers eight typed questions; each axis overrides its heuristic
only when decisive and falls back otherwise. Ships OFF.
→ [Full release notes](./releases/RELEASE-NOTES-v7.7.0.md)

- **`nav_hook_lib/judge.py`**: stdlib client, secret redaction before send, head cap,
  1.5 s fuse, fail-open to `None`; one cached call per dispatch via `judge.for_ctx`.
- **Blend points** `scoring.detect_workflow`, `score_ambiguity`, `score` accept
  `judgment=`; `None` keeps the exact heuristic bytes (v6 parity tests unchanged).
- **prompt_gate / prompt_brief** consume the judgment; the WORKFLOW CHECK block gains a
  "Judged by <model> (<ms>)" line only when a judgment was used.
- **Config block `judge`** (`enabled: false`, `model`, `timeout_ms`, `min_confidence`,
  `noul_low` / `noul_high`, key env/file, `max_state_chars`); listed by `show features`.
- **Eval harness** `scripts/judge_eval.py` + 60 labeled prompts with recorded responses:
  tier 38 → 53/60, task-shaped 43 → 54/60; thresholds set from the sweep.
- **Setup path**: `enable judge` prints the key hint; `python3 hooks/nav_hook_lib/judge.py
  --check` verifies key source + a live round trip; session start names the key source
  or warns when none is found; SOP `sops/integrations/typesafe-judge-setup.md`.

---

## [v7.6.0] — 2026-09-14 — "Provenance, Not Reputation"

Deep research now records which search lens found each source and refuses to let a
finding rest on a single generic-search hit (TASK-78). Provenance is a fact recorded at
fetch time, so the gate can check it; source quality stays a judgment for the critic.
→ [Full release notes](./releases/RELEASE-NOTES-v7.6.0.md)

- **Lens travels end to end**: `canonical`, `breadth`, `adversarial`, `gap` from the
  search queue into the source note, the writer's digest and the report's Sources table.
- **Thirteenth gate check** `findings-corroborated`: no Key finding may cite a single
  `breadth`-lens source. A lone `canonical` or `adversarial` source still passes. Reports
  without a lens column are exempt.
- **Fifth critic pass** (Corroboration) flags the same case at severity major, with the
  fix path: cite a corroborating source on disk, or move the claim to Open questions.

---

## [v7.5.1] — 2026-09-14 — "Provenance"

Deep-research memories now say when and which version of a page supported each claim:
every cited URL carries `fetched YYYY-MM-DD, sha256 <12 hex>` from the run's local
source note (TASK-77). Also fixes the parser that dropped citations from wrapped Key
findings bullets, which had left the first live report's memories without URLs.
→ [Full release notes](./releases/RELEASE-NOTES-v7.5.1.md)

- **`functions/report_to_graph.py`**: `provenance_by_url()` tags cited URLs from the
  local notes; URL-only when notes are absent.
- **`functions/report_parse.py`**: `key_findings()` joins wrapped bullet lines before
  extracting type, text and cites; trailing punctuation no longer floats.
- **Tests**: four new cases; dry-run on the WebGPU report goes from 0/12 to 12/12
  memories with URL evidence, all tagged.

---

## [v7.5.0] — 2026-09-13 — "Code Intelligence"

`navigator-research` uses Claude Code's `LSP` tool for symbol questions when a
language-server plugin is enabled and falls back to Grep otherwise (TASK-76). Nothing is
bundled and there is no config key: the plugin's presence is the toggle. Additive.
→ [Full release notes](./releases/RELEASE-NOTES-v7.5.0.md)

- **`agents/navigator-research.md`**: `LSP` in `tools:`; new Phase 1.5 (availability
  check, question→operation table, one-retry rule for the server's first-request
  indexing race, static-imports-only caveat, never for conventions); Sampling Report
  gains an `LSP calls:` line.
- **`scripts/agent_tool_counts.py`**: per-tool call counts and per-request-deduplicated
  token usage from any transcript JSONL, the ground truth behind the A/B (6 tests).
- **Measured on this repo**: a who-calls question dropped from 9 requests / 284k context
  tokens to 5 / 142k with the complete call-site list; convention questions unchanged.

---

## [v7.4.0] — 2026-09-12 — "Readable Reports"

nav-deep-research reports are answer-first (TASK-75): a fixed Summary block, an At-a-glance
table for comparisons, one section per atomic item with lead sentence + bullets, and a
700-character paragraph cap enforced by the ship gate. Additive; no config change.
→ [Full release notes](./releases/RELEASE-NOTES-v7.4.0.md)

- **`reference/REPORT-FORMAT.md`**: the layout, rules, fix path per gate failure, abridged
  example; the writer reads it before drafting.
- **Ship gate**: two new checks (twelve total) — `summary-scannable` (`**Answer:**` line +
  ≥ 2 bullets) and `no-wall-of-text` (no paragraph, blockquote, or bullet over 700 chars;
  tables/headings/code exempt; detail names the section). `## Open questions` is now a
  required section.
- **Agents**: writer takes `report_format` and plans the At-a-glance table + Answer sentence
  first; patcher keeps the cap and the Answer line when applying hunks.
- **Steps**: step 3 pre-check covers the six structural checks; step 6 ship message is a
  short bullet block + the Summary verbatim.

## [v7.3.0] — 2026-09-10 — "Deep Research"

Web deep research (TASK-74): `nav-deep-research` skill — a question in, a cited report out,
conclusions in the knowledge graph. Ships OFF (`deep_research.enabled`). One hook default
changed: read-guard allowlist entries ending in `/` match by prefix (`research/` exempt).
→ [Full release notes](./releases/RELEASE-NOTES-v7.3.0.md)

- **nav-deep-research**: thin router + six step files loaded fresh per step (decompose →
  sweep → draft → critique → patch → ship); verbatim query as the contract for every
  subagent; recovery table + `resume`.
- **Four agents**: `deep-research-fetcher` (sonnet), `-writer`, `-critic` (no Edit),
  `-patcher` (Read+Edit only) — critic emits findings, patcher applies hunks, nobody
  regenerates the report.
- **Source notes** under `.agent/research/<slug>/sources/` wrapped in a
  `<nav-untrusted-source>` fence (forged tags neutralized, URL escaped); canonical-URL
  dedup; blocked/skipped classification; bodies gitignored, `refetch` rebuilds.
- **Ship gate** (`ship_gate.py`): ten deterministic checks (citations resolve, notes exist,
  no fence leak, no unresolved critical findings, Sources never shrink, min sources…);
  exit 1 blocks the ship.
- **Graph ingestion**: typed `## Key findings` bullets → memories with cited URLs as
  evidence, via the existing `research_to_graph` path.
- **Config**: `deep_research` block (OFF), `VERSION_CONFIGS["7.3.0"]`, features-table row.
- **Hyperresearch handoff**: if the project has `.hyperresearch/`, the skill defers to it
  and only ingests its final report.

## [v7.2.0] — 2026-09-10 — "Three Candidates"

TRIZ Phase 2 (TASK-73): `nav-triz` skill — divergent solving for declared contradictions.
Additive, new skill only.
→ [Full release notes](./releases/RELEASE-NOTES-v7.2.0.md)

- **nav-triz**: three candidates from different TRIZ separation modes, mandatory "worsens"
  cell, one recommendation, capture back to the graph; fires only on explicit ask or a
  declared contradiction on a substantial task.
- **`triz_suggest.py`**: deterministic principle prompts (one per separation mode) + prior
  resolutions from the knowledge graph; always exits 0; generic fallback labelled.
- **`reference/PRINCIPLES.md`**: separation modes with repo examples, ~20 mapped
  principles, the non-transferring list.
- **Hand-offs**: nav-brief, navigator-research Phase 0.5, nav-workflow RESEARCH.

## [v7.1.0] — 2026-09-10 — "Contradictions"

TRIZ Phase 1 (TASK-72): Navigator starts asking for a *better* solution, not just a fast one.
Additive, no hook-path or state changes.
→ [Full release notes](./releases/RELEASE-NOTES-v7.1.0.md)

- **Brief**: optional `Contradiction` row ("improving X worsens Y" or `none`); declared
  contradictions trigger a prior-resolutions lookup before `Approach`. Off-switch
  `brief_hook.contradiction_field`.
- **Decision memories**: optional `**Contradiction**` / `**Separation**` / `**Principle**`
  footer fields (`add-memory --contradiction/--separation/--principle`); `reconcile` syncs
  them disk → node (`field_updates`; new `--fields-only` to skip registering unindexed files).
  Untagged memories byte-identical.
- **Query**: `graph_manager.py --action contradictions [--filter]`; recall renders ` ↔ A vs B`.
- **Agents**: `navigator-research` Phase 0.5 (Ideal Final Result + reuse inventory),
  `task-planner` step 1.5 + IFR line, nav-workflow RESEARCH bullets.
- **Retrofit**: 11 decisions tagged in this repo's graph.

## [v7.0.0] — 2026-09-01 — "Hooks as Runtime"

Complete hooks-runtime transformation (TASK-57..63), hardened by ~7 weeks of dogfood
(TASK-65..71) and gated per TASK-64 (full S1–S6 conformance re-drive on ship-week CC 2.1.241;
RC soak/Pilot sign-off waived on dogfood evidence — see the task doc's Gate Outcome).
→ [Full release notes](./releases/RELEASE-NOTES-v7.0.0.md)

- **Spike-first**: six hook channels empirically verified on CC 2.1.205 (mem-050..055);
  conformance suite checked in (`tests/harness-conformance/`, `make conformance-check`).
- **nav_hook_lib**: shared stdlib runtime (hio, config, state schema-2 w/ flock + fail-closed
  session scoping, sentinels sole-stderr-emitter, unified scoring + 49-prompt corpus, signals
  v3 + pilot-v2 compat, transcript, budget, memory).
- **nav_dispatch**: one fail-open dispatcher per event replaces nine hook scripts;
  gates→responders→injectors→recorders pipeline; PILOT_EXECUTOR merge belt; dispatch-health
  surfacing; sh-guard manifest commands (stale-clone fails open).
- **Golden parity**: all nine v6 behaviors byte-matched via recorded corpus before any new
  behavior; nine old hook files deleted.
- **New capabilities**: prompt_tier1 zero-token answers (decision:block, five exact commands,
  seeded off), stop_completion forced-continuation gate (decision:block, full breaker, seeded
  off), jit_memory + failure_diagnosis declarative injection, subagent_context (2k),
  config_guard, setup, TaskCreated/TaskCompleted graph sync — 13 validated manifest events.
- **Config + docs**: additive VERSION_CONFIGS["7.0.0"] (blocking features seed off),
  templates/CLAUDE.md 206→47 lines, root CLAUDE.md 988→331 (mandates → hook annotations),
  nav-sync-claude refuses regeneration without observed hook liveness.

**Dogfood hardening (2026-07-10/11, TASK-65..70)** — fixes from live use of the alpha:

- **Tier-1 grot cards**: zero-token answers render as rounded-frame TUI cards (Pilot design
  language); the sentinel wrapper was dropped after live evidence that block reasons render
  as plain text (Tier-1 stays self-safe via its exact-match + 48-char rail).
- **stop_completion evidence populator (TASK-65)**: completion indicators derive from
  observable turn evidence — git tree clean, test command ran without error, `.md`/marker
  paths touched — OR'd with explicit state; committed+tested turns now pass the gate.
- **read_guard double-increment (TASK-66)**: PreToolUse fires twice per Read tool-use;
  counting is now idempotent per tool_use_id.
- **Task-status vocabulary (TASK-67)**: plain-text statuses (`Implemented`, `In Progress`,
  …) map to canonical graph statuses; previously only emoji forms were recognized.
- **Tuning (TASK-68)**: tier1 near-miss telemetry uses explicit similarity rules;
  subagent_context injects a deterministic top-K under the 2k budget.
- **Invisible exit signals + Bash classifier (TASK-70)**: nav-signal v3 exit lines may be
  HTML-comment-wrapped — hidden by GFM rendering in assistant output (verified live; hook
  block reasons render plain, the opposite verdict — per-channel discipline). Read-only
  Bash turns (`grep`/`ls`/`git status`…) no longer count as mutating, killing
  stop_completion false-fires on inspection turns.
- **Ops-turn false-fires (TASK-71, 2026-07-16)**: shell-aware read-only Bash classifier
  (parses `gh pr view`, assignment heads, tests, loops) + tree-digest mutation evidence
  replacing whole-tree `git status` cleanliness that a busy shared repo pinned False forever.
- **Pilot context-injection headers (bf04077)**: templates carry the 3 headers Pilot's
  `loadProjectContext` extracts.
- **Conformance on CC 2.1.241 (2026-09-01)**: S1–S6 re-driven for the release gate — all
  channel verdicts identical to 2.1.205; S6 probe's own `$PWD` string-prefix gate fixed
  (realpath'd cwd, method-lesson-2 class).

---

## [v6.18.1] — 2026-07-09

**Patch: table-separator rows ingested as decision memories + re-sync duplication.** Found live by nav-brief's own memory recall minutes after v6.18.0: `extract_decisions` skipped separator rows only on exact `'---'`/`'-'` match, so wide cells (`|----------|`) became 95%-confidence decision memories; `add_task_to_graph` also re-created every decision on re-sync (a TASK-54 double-sync cloned 6 memories). Skip is now `re.fullmatch(r'[-:\s]+')`; re-sync dedupes against existing decision summaries. Source-repo graph cleaned (7 nodes pruned, files archived to `resolved/`, health 85→100). 4 regression tests. → [Full release notes](./releases/RELEASE-NOTES-v6.18.1.md)

## [v6.18.0] — 2026-07-09

**New skill + hook `nav-brief` — intent-brief enforcement for ambiguous prompts (TASK-56).** The expensive failure mode is rework, not context overflow: ambiguous task prompts get implemented on guessed scope, then corrected over 2-4 exchanges. A new `UserPromptSubmit` hook (`hooks/nav_brief.py`, sibling entry to `workflow_enforcer.py`) scores each prompt for **ambiguity** — a third axis, deliberately separate from both complexity scorers per TASK-48 precedent (`skills/nav-brief/functions/ambiguity_scorer.py`: question/confirmation zero-out gates, task-verb base 0.5, vague-scope bonus, credits for file paths / numbers / limiter words / acceptance criteria; word-boundary regex only). At/above threshold it injects a `NAV-BRIEF` instruction plus relevant graph memories (via `memory_recall.py --concepts`, 3s timeout, silent degradation, 1200-char budget); the `nav-brief` skill then renders a one-screen INTENT BRIEF (Goal/Scope/Approach/Limits/Verify/Won't-do), asks max 2 open questions, waits for confirmation, and raises `BRIEF DRIFT` if implementation later exceeds confirmed scope. Never blocks — exit 0 + stdout only (mem-034: exit 2 on UserPromptSubmit stops the model entirely). Config: `brief_hook {enabled, ambiguity_threshold: 0.5, memory_budget_chars: 1200}`; `PILOT_EXECUTOR` bypass for autonomous dispatch. 42 new tests (25 scorer, 16 hook subprocess, 1 two-hook composition case in the smoke suite). v1 is stateless; pending-brief tracking, strict gating, and briefs-shown metrics are explicitly deferred. → [Full release notes](./releases/RELEASE-NOTES-v6.18.0.md)

**Also: updater guards against phantom-update loops.** `version_detector.py` now validates each release tag's `plugin.json` version (via raw.githubusercontent.com, newest-first, fail-open on network errors) before offering it — a tag published without a matching version bump was previously offered every session and "updated" without ever changing the installed version.

## [v6.17.1] — 2026-07-06

**Hotfix: consumer-graph writes crashed on missing `concept_index`.** `add_node`/`remove_node`/`add_edge` assumed `concept_index` and `edges` keys exist — pilot-style consumer graphs lack them, so the first task_to_graph sync after v6.17.0 died with `KeyError`. Now `setdefault`s. 3 regression tests (pilot-shaped fixture). → [Full release notes](./releases/RELEASE-NOTES-v6.17.1.md)

## [v6.17.0] — 2026-07-06

**Close the memory loop — memories now surface automatically and can't silently rot.** Motivated by a live consumer-repo audit (pilot, 2026-07-05/06) that found 52 of 84 memory files with zero graph presence, 42 freeform concept tags, 19 superseded memories that would have been served as truth, and zero automatic recall — `auto_surface_relevant` had been a config flag + prose since v6.0.0 that no code read. This release implements it: the SessionStart hook injects a `## Relevant Memories` block (top-N by concept overlap with open tasks + active marker, gated by `knowledge_graph.auto_surface_relevant`, `timeout=3` third subprocess, placed truncation-safe), and `nav-task` Step 2.5 writes a `## Known Pitfalls & Patterns` section into new task docs — both via one new deterministic ranker, `memory_recall.py` (alias-resolved concept overlap → confidence; resolved excluded; never touches `concept_index`, so consumer graphs without one work by construction). Write side: `add_memory` is fail-loud and ordered (file before node, rollback on failed save; all 4 programmatic call sites wrap), concepts validate against the vocabulary at the CLI boundary (`--allow-new-concept` to extend), and `graph_builder` rebuilds **preserve** the memories/files buckets they previously wiped (`--no-preserve-memories` to opt out). Maintenance: new `--action reconcile` (drift report + `--execute` registration of unindexed files), `health_check` gains score-affecting broken-file-link/unindexed-file counts (⚠️ drifted consumer graphs will see scores drop — intended) + advisory concept-drift, `repair` prunes orphaned `concept_index` entries, `prune --execute` archives backing files so reconcile can't resurrect them. Lifecycle: `--action resolve-memory` marks superseded memories (`resolved: true`, `superseded_by`, `supersedes` edge, file → `resolved/`) — excluded from recall, skipped by stale/decay, flagged `[resolved]` in queries. 46 new tests; live-validated against the pilot graph (85 memories, `file:` schema).

→ [Full release notes](./releases/RELEASE-NOTES-v6.17.0.md)

## [v6.16.0] — 2026-06-15

**New skill `nav-pilot` — the Navigator → Pilot dispatch handoff.** "dispatch TASK-XX to Pilot" resolves the task doc, uses its H1 as the issue title, dispatches via `gh issue create --label pilot --body-file`, and writes the issue URL back into `## Refs`. One-way by design; spec validation stays Pilot's job.

→ [Full release notes](./releases/RELEASE-NOTES-v6.16.0.md)

## [v6.15.7] — 2026-06-08

**The hook env var never existed — `${CLAUDE_PLUGIN_DIR}` → `${CLAUDE_PLUGIN_ROOT}`.** Every Navigator lifecycle hook referenced `${CLAUDE_PLUGIN_DIR}`, a variable Claude Code has never defined (the three documented plugin path vars are `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}`, `${CLAUDE_PROJECT_DIR}`). The wrong name always expanded to empty, so the `:-fallback` always fired — meaning every install since hooks moved into the manifest (v6.13.0) resolved its hooks against the **marketplace checkout** (which tracks `main`) rather than the **installed version**. This stayed invisible while `main` matched the release. It became visible the instant they diverged: the published v6.15.6 manifest still referenced `token_monitor.py` (retired on `main` by the audit work), so the fallback path 404'd and threw a `PostToolUse` error on every tool call — the exact symptom the v6.14.0/v6.15.1 "silent-fail" saga (`mem-036`) chased without identifying this root cause. Fix: `CLAUDE_PLUGIN_DIR` → `CLAUDE_PLUGIN_ROOT` across `plugin.json` (8 hook commands; marketplace path kept only as a last-resort fallback that now never fires because the primary resolves), the 3 subprocess hooks (`ROOT`-first read, `DIR` back-compat), `release_validator --verify-hooks`, ~17 skill `SKILL.md` files, the `migrate_hooks` docstring, and `mem-027`. Historical references left intact (CHANGELOG, prior notes, `marketplace.json` metadata, `mem-036`, the v6.14.0 guard quote). Verified: `--verify-hook-paths` 8/8, `--verify-hooks` 16/16 under set+unset `CLAUDE_PLUGIN_ROOT`, full `make test` green. This is also the first tagged release since v6.15.6, so it publishes the audit-remediation batch **wp1–wp11** (TASK-43..52 + TASK-25) that had accumulated unreleased on `main` — including the `--verify-hook-paths` gate the v6.15.6 notes flagged as a follow-up.

→ [Full release notes](./releases/RELEASE-NOTES-v6.15.7.md)

## [v6.15.6] — 2026-06-02

**Critical hook-manifest fix — every installed user hit a per-Bash-call error.** `.claude-plugin/plugin.json` still registered a `PostToolUse(Bash)` hook pointing at `hooks/nav_commit_reminder.py`, a file deleted in `a2b4e59` (v6.15.5) when the commit-reminder probe was retired. That cleanup touched `.claude/settings.json` and `templates/` but missed the canonical published manifest — `plugin.json` is what ships to every installed user, while `.claude/settings.json` is only the dev backstop, so the source repo masked the regression locally. Effect on installed users: every `Bash` tool call invoked `python3 .../hooks/nav_commit_reminder.py` and failed with `can't open file … No such file or directory`. Fix removes the dead block (`PostToolUse` is now `token_monitor` on `Edit|Write|Bash`, plus `nav_task_graph_sync` and `nav_profile_sync` on `Edit|Write`). Also corrected `.agent/DEVELOPMENT-README.md`, which still documented "ten hooks" and listed `nav_commit_reminder.py` as live — now nine, table row removed, version references synced to 6.15.6. Surfaced by a 10-dimension, adversarially-verified project audit. Follow-up (not in this patch): a release-time validator step that asserts every hook command path in `plugin.json` resolves to an existing `hooks/` file, so a deleted hook can never ship registered again.

→ [Full release notes](./releases/RELEASE-NOTES-v6.15.6.md)

## [v6.15.5] — 2026-05-26

**Workflow Discipline section added to CLAUDE.md**, codifying four interruption-reducing rules surfaced by the 2026-05-25 Claude Code Insights audit (428 messages, 25 sessions, 5-day window). Rules: (1) research before scaffolding — state phase in first message and wait for confirmation, (2) parallel for fan-out — dispatch N parallel Task agents up front when applying a pattern to N similar files (proven 41% line reduction in workshop restyle), (3) reframe don't re-litigate — drop rejected framings entirely from outputs, (4) state hypothesis before exploring — name suspected failure mode before tool use during debugging. Docs-only patch, zero code paths affected. Section inserted before existing `## Code Standards` (~line 747). Also gitignores `.agent/.marker-log` (Navigator marker-creation log file that was unnecessarily showing as untracked in repo status). Smoke-tests the post-bfe3b26 / 25614fc `release.yml` pipeline on a low-risk patch.

→ [Full release notes](./releases/RELEASE-NOTES-v6.15.5.md)

## [v6.15.4] — 2026-05-21

**nav-task template upgraded to a Pilot-compatible superset shape.** The canonical template had drifted from how task docs are actually written — active docs (TASK-37, TASK-40, TASK-example) had organically converged on `## Acceptance Criteria / ## Out of Scope / ## References` while the writer still emitted `## Implementation Plan / ## Success Metrics / ## Testing Plan / ## Done`. This release codifies the drift. New shape: rename `## Implementation Plan` → `## Implementation`; add `## Acceptance Criteria` (with `- [ ]` items), `## Out of Scope`, `## Refs`; drop `## Success Metrics` and `## Testing Plan` (folded into Acceptance Criteria), `## Dependencies` and `## Completion Checklist` (no parsers, redundant with Done/Refs). Updates both writers in lockstep — `skills/nav-task/functions/task_formatter.py` (the Python writer used via `--title/--id` CLI) and `skills/nav-task/SKILL.md` Step 3A create template (the LLM-instruction template Claude follows for natural-language invocation). Also closes a latent inconsistency: the archive template at `SKILL.md:193` already said `## Implementation`; only the create template was the laggard. Pilot's spec_validator regex (`^##\s+(Acceptance|Implementation|Context|Background|Approach|Design|Refs)\b` at `pilot/internal/adapters/github/spec_validator.go:22`) matches four headings in the new template — `gh issue create --body-file .agent/tasks/TASK-XX.md` passes the structural check without any flag, and no `pilot` label is required (polling label is deployment-configurable). Preserved `## Verify` and `## Done` verbatim — `verify_extractor.py:34,69` has hardcoded regex literals that would silently return empty results on rename. Kept `## Technical Decisions` — `task_to_graph.py:90-121` extracts decision memories from it. Audit traced every parser before the rename: hooks are heading-agnostic, knowledge graph uses full-text keyword scan with no heading dependency, no test fixtures lock the old shape. Existing `.agent/tasks/*.md` docs in user projects unaffected. Verified end-to-end: `verify_extractor` round-trips a freshly generated TASK-99 sample, extracting 3 commands and 4 done criteria correctly.

→ [Full release notes](./releases/RELEASE-NOTES-v6.15.4.md)

## [v6.15.3] — 2026-05-18

**`workflow_enforcer` deadlock on question/non-task turns fixed.** `nav_workflow_state.py` (Stop hook) previously stamped `check_shown=false` on every assistant turn that didn't contain the "WORKFLOW CHECK" string — including `AskUserQuestion`-only turns and pure-text replies (session-start summaries, clarifiers). If the next user prompt contained a Loop Mode trigger (`"run until done"`), `workflow_enforcer.py` (UserPromptSubmit) blocked with exit 2 and the only recovery paths were the three manual escape hatches in the block message. Reproduced in the wild: assistant asked a resume-or-review clarifier via `AskUserQuestion`, user declined, user typed `"Run until done via loop mode"` → block. Fix: tristate `check_shown` — `True` when CHECK block present, `False` only when the prior turn used a codebase-mutating tool (`Edit`, `Write`, `MultiEdit`, `NotebookEdit`, `Bash`, `Task`/`Agent`) without showing it, `None` ("n/a") otherwise. Enforcer already gates on `check_shown is False`, so `None` falls through to soft-warn cleanly. State file gains a `tools_used` field for transparency. Four-case smoke test passes: question-only → null, edit-without-check → false (still blocks), edit-with-check → true, pure-text-reply → null.

→ [Full release notes](./releases/RELEASE-NOTES-v6.15.3.md)

## [v6.15.2] — 2026-05-15

**Four v6.15.1 follow-ups landed.** (1) `nav-graph add-memory` CLI no longer silently overwrites on-disk memory files. `_next_memory_id` now scans both graph nodes AND `memories/**/mem-*.md` on disk; `--node-id` is honored when provided (was silently ignored); `create_memory_file` raises `FileExistsError` on collision instead of `write_text`'ing over the existing file. Caught when `mem-034.md` was nearly destroyed during the v6.15.1 release work. (2) Graph reconciliation: `mem-034` and `mem-035` (both pre-existing pitfalls on disk, never registered in the graph) added — graph and disk now both at 36 memories, zero drift. (3) `nav-release --verify-hooks` mode: smoke-tests every plugin manifest hook command via `bash` with `$CLAUDE_PLUGIN_DIR` both bound and explicitly unset; flags the v6.14.0 regression signature (payload-emitting hook silently exits 0 with no stdout, no stderr). Coverage targets `SessionStart`, `PreCompact`, `PostCompact`; other events are silent-by-design and not flagged. Verified end-to-end by re-applying the v6.14.0 guard to `SessionStart` in a temp manifest and confirming the validator flags it correctly. (4) `skills/nav-sync-claude/skill.md` renamed to `SKILL.md` for case consistency — required `git mv -f` because macOS APFS is case-insensitive. Clears `release_validator --verify-tag` false-positive.

→ [Full release notes](./releases/RELEASE-NOTES-v6.15.2.md)

## [v6.15.1] — 2026-05-15

**Two hook silent-fail fixes exposed by a workshop-prep audit.** (1) Three hook scripts (`nav_session_start`, `nav_profile_sync`, `nav_task_graph_sync`) had stale `jitd-marketplace` hardcoded in their `_resolve_plugin_dir` fallback chains; renamed to `navigator-marketplace` matching the current cache path. Tier-2 and tier-3 fallbacks were silently missing on every install — `auto_updater.py` and `nav-sync-claude/claude_updater.py` already used the correct name, these three scripts were missed during the rename. (2) The v6.14.0 manifest-level shell guard `if [ -n "$CLAUDE_PLUGIN_DIR" ]; then ... fi` silently no-opped every hook when the variable was unset — it protected `workflow_enforcer` from the v6.14.0 chicken-and-egg, but turned `SessionStart`, `PreCompact`, and seven other hooks into invisible no-ops in projects without a project-local `.claude/settings.json` backstop. Confirmed in the wild: a fresh Claude Code v2.1.142 session in a Nav-initialized project showed no `SessionStart` injection despite plugin and config being correct. Replaced the guard with shell parameter-expansion fallback (`${CLAUDE_PLUGIN_DIR:-$HOME/.claude/plugins/marketplaces/navigator-marketplace}/hooks/X.py`) — uses the env var when set, falls back to the flat marketplaces path otherwise (maintained by Claude Code for every plugin install, contains all 10 hook scripts). No regression to the v6.14.0 fix: `workflow_enforcer.py` still receives a valid script path when `CLAUDE_PLUGIN_DIR` is unset and exits 0 on non-loop-trigger prompts. Smoke-verified: sentinel injection works with `CLAUDE_PLUGIN_DIR` both set and unset; `workflow_enforcer` exits 0 cleanly in the unset case. Missing path now produces a python stderr error instead of silent exit 0 — silent-fail mode eliminated. **Restart Claude Code after upgrade so the patched manifest is re-registered.**

→ [Full release notes](./releases/RELEASE-NOTES-v6.15.1.md)

## [v6.15.0] — 2026-05-15

**`nav-features` exposes the full configurable surface.** The feature table previously showed five entries and silently omitted eight features that already existed in `.nav-config.json` — the v6.0.0 Knowledge Graph (`knowledge_graph.enabled`), Multi-Agent orchestration (`multi_agent.enabled`), and six lifecycle hooks (`compact_hook`, `workflow_enforcer_hook`, `read_guard_hook`, `workflow_state_hook`, `task_graph_sync_hook`, `profile_sync_hook`). All eight are now listed and toggleable via `nav-features`. The install-check entry renamed from `multi_claude` → `multi_claude_scripts` to disambiguate from the new `multi_agent` config flag — the former is a PATH-based shell-script presence check, the latter is a config toggle for the `nav-multi` skill; sharing the name was actively misleading. Fixed `simplification.default` to `True` (was `False`, but the shipping config and CLAUDE.md both already treat it as on). Widened the name column 15 → 23 chars to fit `workflow_enforcer_hook`. SKILL.md sample output regenerated and supported-features list split into Core / Hooks / Install-based with a caution note on disabling guardrail hooks. No code paths beyond the FEATURES dict and table formatter changed; toggle round-trip verified clean for new entries.

→ [Full release notes](./releases/RELEASE-NOTES-v6.15.0.md)

## [v6.14.0] — 2026-05-12

**Defensive hook guards + two skill renames.** (1) Every command declared in `.claude-plugin/plugin.json`'s `hooks` field is now wrapped in `if [ -n "$CLAUDE_PLUGIN_DIR" ]; then ... fi`. v6.13.0 moved hook distribution into the plugin manifest so `${CLAUDE_PLUGIN_DIR}` would substitute correctly — but some installs still see the variable expand to empty when the plugin is registered but not fully loaded into the active session's plugin context. Because `workflow_enforcer.py` runs on every `UserPromptSubmit`, the unset variable turned into a hard block on every prompt including `/nav:init` (chicken-and-egg: can't initialize Navigator to recover because the hook blocks the init command). The shell guard fails open (exit 0) when the variable is unset and runs normally when it's bound. All ten hooks across SessionStart, PreCompact, PostCompact, Stop, UserPromptSubmit, PreToolUse:Read, and three PostToolUse matchers got the same treatment. (2) `nav-update-claude` → `nav-sync-claude` and `nav-task-mode` → `nav-workflow`. A 29-skill catalog audit flagged these two pairs as pure naming collisions: `nav-update-claude` collided with `nav-upgrade` on the "update" verb (one syncs `CLAUDE.md` to the installed version, the other updates the plugin binary; `nav-upgrade` calls `nav-sync-claude` as Step 4 — orchestration, not duplication); `nav-task-mode` collided with `nav-task` on the "task" verb (one manages `.agent/tasks/` docs, the other is the workflow phase orchestrator). Zero functional overlap in either pair. Clean rename, no backwards-compat aliases. Auto-invocation triggers unchanged. Live cross-refs in `plugin.json`, `marketplace.json` skills array, `nav-upgrade`, `nav-simplify`, `DEVELOPMENT-README.md`, current task docs, SOPs, knowledge graph, and `mem-011` updated. Historical refs in `CHANGELOG.md`, prior release notes, and `.agent/tasks/archive/*` left alone.

→ [Full release notes](./releases/RELEASE-NOTES-v6.14.0.md)

## [v6.13.0] — 2026-05-12

**Hook distribution moved from user settings.json to plugin manifest; three latent bugs resolved.** Closes upstream #7, #8, #9. (1) Hooks previously shipped via `templates/claude-settings-hooks.json`, which `nav-init` and `nav-upgrade` merged into each user's `.claude/settings.json` through `settings_merger.py`. Merged commands referenced `${CLAUDE_PLUGIN_DIR}`, but Claude Code only substitutes that variable for hooks declared in a plugin manifest — not for hooks defined in a project's settings. The shell expanded the unset var to empty and every hook command became `/hooks/X.py`, failing on every Stop, PreCompact, and PostToolUse event in fresh installs. Now declared at the top of `.claude-plugin/plugin.json` under a `hooks` field; the variable substitutes correctly. (2) `hooks/workflow_enforcer.py` was wired under `PreToolUse` (matcher `Edit|Write|Bash|Task`) but the script reads stdin as if invoked under `UserPromptSubmit` — the two events deliver different payloads, so the hook always exited 0 and its blocking branch was unreachable. Re-wired under `UserPromptSubmit` in the new manifest. Added `PILOT_EXECUTOR` env-var escape hatch for autonomous-executor subprocess use cases. (3) `skills/nav-update-claude/functions/config_migrator.py` had a hardcoded `CURRENT_VERSION = "5.7.0"` and used `!=` for the migration decision, so any project on a newer config was rewritten *down* to the stale literal. Now reads CURRENT_VERSION at import from `.claude-plugin/plugin.json` via pathlib upward walk; uses the existing `version_less_than` helper to gate the assignment. New `skills/nav-upgrade/functions/migrate_hooks_out_of_settings.py` removes the now-redundant Navigator hook entries from existing users' `.claude/settings.json` on next upgrade (conservative match: command must contain both `hooks/` and one of 10 Navigator basenames; writes `.pre-migrate.<ts>` backup; idempotent). `templates/claude-settings-hooks.json` deleted — no longer the distribution channel. 25/25 tests green (11 settings_merger + 7 migrate_hooks + 7 config_migrator).

→ [Full release notes](./releases/RELEASE-NOTES-v6.13.0.md)

## [v6.12.1] — 2026-05-11

**Course-correction patch after v6.12.0 live verification.** Live test exposed three problems. (1) PreToolUse stdout AND `hookSpecificOutput.additionalContext` are silent to the model — the dual-channel emit in v6.12.0 was dead code. The read guard fired and counted correctly, but warnings never surfaced. Captured as `mem-035`. (2) `hooks/nav_read_guard.py` upgraded with `strict_block: true` (default) — at count ≥ `escalate_threshold` the hook exits 2 with sentinel-wrapped `<nav-read-guard-block>` stderr addressing the user with four recovery options. The counter IS the state-file ground truth mem-027's three-condition gate needs (this same hook wrote it on prior invocations). Warn path moved from dead stdout to stderr. (3) The plugin's shipped `.claude/settings.json` was missing 5 of 7 lifecycle hooks — fresh installs never got SessionStart, PreCompact, PostCompact, Stop, or PostToolUse Edit/Write auto-syncs unless they ran `nav-init`. Synced with `templates/claude-settings-hooks.json`. Template corrected: `workflow_enforcer.py` moved from `PreToolUse` (where it would silently no-op — the hook reads `data.get("prompt")` which only exists on `UserPromptSubmit`) back to `UserPromptSubmit`. New `hooks/nav_commit_reminder.py` ships as a 20-line probe to characterize PostToolUse output channels for Opp 5 in v6.12.2. 6/6 smoke-test scenarios green.

→ [Full release notes](./releases/RELEASE-NOTES-v6.12.1.md)

## [v6.12.0] — 2026-05-11

**Phase 3 of TASK-38 begins — `.agent/` bulk-read guard (Opp 6).** New `hooks/nav_read_guard.py` fires on `PreToolUse` Read, counts non-allowlisted `.agent/` reads per turn in `.agent/.nav-read-counter.json`. Warns at 3+ ("use a Task or Explore agent"), escalates at 5+ ("matches the bulk-load anti-pattern, risk: 50k+ tokens"). Allowlist exempts the four files Navigator itself reads on legitimate session start: `DEVELOPMENT-README.md`, `.nav-config.json`, `.user-profile.json`, `knowledge/graph.json`. `hooks/nav_workflow_state.py` extended with `_reset_read_counter()` so the counter clears every turn. Ships warn-only — a raw read count fails mem-027's three-condition gate (no state-file confirmation of "model is actively bulk-loading"); a blocking variant is deferred behind a future `strict_block` flag if telemetry shows warnings are ignored. Dual-channel output (`hookSpecificOutput.additionalContext` + plain stdout) for OQ-2 defensive. 7/7 smoke-test scenarios pass including the recursive-trigger check (warn messages contain no LOOP_TRIGGERS). Opp 5 (commit reminder) targets v6.12.1.

→ [Full release notes](./releases/RELEASE-NOTES-v6.12.0.md)

## [v6.11.2] — 2026-05-11

**workflow_enforcer UX fixes after live verification.** Shipped right after v6.11.1 once the first real block surfaced two issues. (1) The stderr "Action:" line addressed Claude — but `UserPromptSubmit` exit 2 blocks the prompt *before* the model runs, so any instruction to Claude was dead text. Message rewritten to address the user with three concrete recovery options. (2) The stderr quoted the matched trigger phrase verbatim (e.g., `loop trigger 'run until done' detected`). Claude Code echoes blocked stderr into the next prompt's context — so the next prompt re-matched the same trigger and re-blocked. Observed live as nested blocks. Fix: wrap stderr in `<nav-workflow-block>...</nav-workflow-block>` sentinel; hook strips sentinel-wrapped sections from incoming prompts before LOOP_TRIGGERS matching runs. Soft-warn stdout suppressed when blocking (was leaking the trigger phrase). Pitfall captured at `mem-034`. 3/3 scenarios green including the explicit recursive-block case.

→ [Full release notes](./releases/RELEASE-NOTES-v6.11.2.md)

## [v6.11.1] — 2026-05-11

**Phase 2 lifecycle hook — first blocking hook in Navigator (TASK-38).** `hooks/workflow_enforcer.py` upgraded from soft-warn (`exit 0`) to hard-block (`exit 2`) when (a) prompt contains a Loop Mode trigger, (b) `.agent/.nav-workflow-state.json` shows prior-turn `check_shown=false`, and (c) `workflow_enforcer_hook.strict_block=true` (default). Gated on the state file written by v6.11.0's Opp 2 writer — the block fires only when the prior turn empirically skipped the WORKFLOW CHECK block, keeping false-positive rate near zero. Missing state file falls back to soft-warn (Phase 1 projects unaffected by upgrade). Stderr message surfaced to Claude includes reason + recovery action + opt-out path. New config section `workflow_enforcer_hook.{enabled, strict_block}` in `.agent/.nav-config.json`. 5/5 smoke-test scenarios pass. Architectural precedent established: Navigator hooks may block, but only when a deterministic state file confirms the violation.

→ [Full release notes](./releases/RELEASE-NOTES-v6.11.1.md)

## [v6.11.0] — 2026-05-11

**Phase 1 lifecycle hooks — TASK-38 hook-migration roadmap kickoff.** Three new silent side-effect hooks migrate "model, remember to..." rules from CLAUDE.md prose into deterministic Python. `hooks/nav_task_graph_sync.py` (Opp 4) fires `PostToolUse` on `Write|Edit` matching `.agent/tasks/TASK-*.md` — runs `task_to_graph.py --action add` to upsert the task into the knowledge graph. `hooks/nav_workflow_state.py` (Opp 2) fires every `Stop` — reads the last assistant message, records `check_shown`/`nav_status_shown`/`loop_phase` into `.agent/.nav-workflow-state.json`. Silent infrastructure for the Phase 2 blocking workflow_enforcer. `hooks/nav_profile_sync.py` (Opp 3) fires `PostToolUse` on writes to `.user-profile.json` — diffs corrections array against `last_synced_count`, runs `correction_to_memory.py` only when array grew. Zero injected tokens across all three hooks. Q1 verified: `add_node` upserts by node_id (no duplicates). All 11 settings_merger tests still pass. Smoke-tested live: Opp 3 synced 4 backlogged corrections to the graph as a side effect of being wired up.

→ [Full release notes](./releases/RELEASE-NOTES-v6.11.0.md)

## [v6.10.3] — 2026-05-11

**settings_merger safety pass — don't kill user hooks on init.** Pre-emptive hardening before TASK-38 (v6.11 roadmap) widens the hook surface through the same merger. `settings_merger.py` now writes atomically (tempfile + `os.replace`, no partial-write corruption), supports `--dry-run` for preview, and surfaces non-list incoming hook values via stderr instead of skipping them silently. `nav-init` Step 6 detects foreign hooks (anything not matching Navigator's known commands) before merging, lists them, and asks the user via AskUserQuestion before proceeding. Both `nav-init` and `nav-upgrade` now write timestamped backups (`.pre-nav-init.{YYYYMMDD-HHMMSS}`, `.pre-upgrade.{ts}`) instead of a single overwriting `.backup` — re-running upgrade no longer loses the pristine pre-Navigator backup. New `test_settings_merger.py` covers 11 cases (fresh install, preserves user same/different event, idempotent rerun, dedupe by command, top-level keys, invalid JSON aborts, empty file aborts, non-list skip warning, dry-run no write, atomic write under simulated failure) — all pass in <10ms. No new features.

→ [Full release notes](./releases/RELEASE-NOTES-v6.10.3.md)

## [v6.10.2] — 2026-05-11

**Auto-updater fix — SessionStart auto-update now actually works.** The `"Auto-update failed. Run nav-upgrade manually."` banner shown at the top of every session was the result of three stacked bugs in `skills/nav-start/functions/auto_updater.py`. (1) The plugin was being referenced by its unqualified name `navigator` — Claude Code requires the qualified form `navigator@navigator-marketplace` and rejects the bare name. (2) Even with the qualified name, `claude plugin update` reported "already at latest" because the local marketplace cache was stale; Claude Code does not auto-refresh it before update. A new `refresh_marketplace()` helper now runs `claude plugin marketplace update navigator-marketplace` first. (3) `get_current_version` parsed `claude plugin list` expecting the version on the same line as the plugin name, but the actual output puts `Version: X.Y.Z` on a separate indented line — so the regex always missed and the auto-updater short-circuited with "Could not detect current Navigator version" before the version comparison ever ran. Parser now scans forward from the plugin entry header. End-to-end verified: auto-updater reports accurate `current_version` and either `up-to-date` or `updated` correctly.

→ [Full release notes](./releases/RELEASE-NOTES-v6.10.2.md)

## [v6.10.1] — 2026-05-11

**Bug fixes for code generators + hook filename.** Four fixes surfaced by a full workshop-prep audit. `frontend-component` template no longer leaves a bare interface identifier in generated TSX — `${PROPS_INTERFACE}` placeholder split into `${PROPS_INTERFACE_BLOCK}` (full body, with a sensible default) and `${PROPS_INTERFACE}` (name only for the `React.FC<>` type ref). `backend-endpoint` template no longer leaks an unevaluated JS ternary into generated Express routes — `${MIDDLEWARE_CHAIN ? MIDDLEWARE_CHAIN + ',' : ''}` replaced with a `${MIDDLEWARE_BLOCK}` that the generator pre-computes as either a clean middleware line or an empty string. `hooks/monitor-tokens.py` renamed to `hooks/token_monitor.py` so the filename matches both the in-tree settings template and the rest of the hook directory (`workflow_enforcer.py`, `nav_session_start.py`, `nav_pre_compact.py`, `nav_post_compact.py`) — previously, fresh installs configured Claude Code to call a file that didn't exist and token monitoring silently never ran. `nav-loop` `test_exit_gate.test_empty_dict` assertion synced with `TOTAL_INDICATORS=6` (was stale at 5). No new features, no behavior changes for working flows.

→ [Full release notes](./releases/RELEASE-NOTES-v6.10.1.md)

## [v6.10.0] — 2026-05-11

**PreCompact + PostCompact hooks — compact-resilient markers.** Pairs with v6.9.0 SessionStart to close the session-lifecycle loop. Navigator state now survives every compact, including silent auto-compacts that users previously didn't even notice happening. New `hooks/nav_pre_compact.py` fires on every manual `/compact` or auto-compact: reads the JSONL transcript, runs the same heuristic summarizer as `marker_compressor.py`, captures git state + active tasks, writes `.agent/.context-markers/before-compact-{manual,auto}-{ts}.md` and sets `.active`. The trigger token in the filename makes silent auto-compacts visible. New `hooks/nav_post_compact.py` appends Claude Code's official `compact_summary` to the same marker after compact completes, so restores get both heuristic and authoritative summaries. `nav-compact` skill Step 0 detects the hook and skips manual marker creation when installed (single source of truth). Opt-out via `compact_hook.enabled: false`; legacy projects fall back to manual nav-compact flow automatically.

→ [Full release notes](./releases/RELEASE-NOTES-v6.10.0.md)

## [v6.9.0] — 2026-05-11

**SessionStart hook for zero-Read context injection.** Claude Code's `SessionStart` hook now pre-loads Navigator state (navigator + active marker + config + graph stats + user profile + open tasks + auto-update) into the model's context window via `additionalContext` — before the first user turn. The `nav-start` skill detects a sentinel and skips its 6 file reads, eliminating ~35k tokens per session start in local measurement (73.3k → 37.8k). New `hooks/nav_session_start.py` builds the parity payload (9500-char cap, source-aware: `--resume` hoists marker first); new `skills/nav-init/functions/settings_merger.py` provides idempotent `.claude/settings.json` merging that preserves user-defined hooks. Templates fix `${CLAUDE_PROJECT_ROOT}` (non-existent) → `${CLAUDE_PROJECT_DIR}` (actual Claude Code env var). Opt-out via `session_start_hook.enabled: false`; legacy projects fall back to the Read-based path automatically.

→ [Full release notes](./releases/RELEASE-NOTES-v6.9.0.md)

## [v6.8.0] — 2026-05-11

**nav-simplify ROI scoring shipped.** TASK-37 implementation: cost/benefit ROI gate so the simplifier can decline to simplify when the math doesn't favor it. New `cost_analyzer.py` adds four cost signals (touch lines, file LOC, git recency, import references); benefit composed of issue density + severity impact + active-diff signal. Three-tier gate (`skip` / `suggest` / `apply`) with configurable thresholds. Opt-in via `simplification.scoring.mode: "roi"` — default stays `"complexity"` for backward compat. 20 unit tests cover scoring math and gate logic. Calibrated on this repo's actual files; ROI ordering matches intuition (active-diff messy files prioritize; stable clean files de-prioritize).

→ [Full release notes](./releases/RELEASE-NOTES-v6.8.0.md)

## [v6.7.0] — 2026-05-11

**Release workflow hardening + nav-simplify ROI design.** Replaced `softprops/action-gh-release@v2` with native `gh release create` — closes the last Node.js 20 deprecation warning by removing the third-party Node action entirely (uses the runner's pre-installed GitHub CLI). Design pass for `nav-simplify` complexity-cost scoring captured in TASK-37: cost/benefit ROI gate so the simplifier can decline to simplify when the math doesn't favor it (opt-in via `simplification.scoring.mode`; weights need real-data calibration before implementation).

→ [Full release notes](./releases/RELEASE-NOTES-v6.7.0.md)

## [v6.6.0] — 2026-05-11

**Release hygiene + Loop Mode flexibility.** Compact maintenance pass: GitHub Actions bumped to Node.js 24-ready versions (`checkout@v5`, `action-gh-release@v2`) ahead of June 2026 deprecation; `loop_mode.periodic_interval` (default 3) parameterizes the previously-hardcoded `iteration_approval: "periodic"` cadence for tunable overnight runs; `nav-multi` documents branch-per-run convention (`nav-multi/{SESSION_ID}`) for parallel workflow safety.

→ [Full release notes](./releases/RELEASE-NOTES-v6.6.0.md)

## [v6.5.0] — 2026-05-11

**Execution-layer parity completion.** v6.4.0 fixed the bugs; v6.5.0 closes the parity gaps with the research agent. New `execution_to_graph.py` mirrors `research_to_graph.py`. All 5 code-writing skills (frontend-component, backend-endpoint, database-migration, backend-test, frontend-test) emit `execution_summary` JSON for ingestion. Phase 0 (graph check) added as Step 0 on the three primary code-writing skills. `code_analyzer.py` auto-detects indent unit (fixes 4-space false positives). `backend-test` / `frontend-test` expanded from 38-line stubs to working skills with the same Phase 0 → generate → verify → summary pattern.

→ [Full release notes](./releases/RELEASE-NOTES-v6.5.0.md)

## [v6.4.0] — 2026-05-11

**Execution-layer parity pass.** Self-audit of the execution layer (skills that write code + orchestration that wraps them) using v6.3.0's sharpened `navigator-research` agent surfaced 10 concrete bugs and gaps. All fixed: `workflow_enforcer.py` hook wired (was dead code), test skill triggers route correctly, `nav-simplify` no longer silently pauses autonomous flows, Loop Mode thresholds aligned via shared constants, `stagnation_detector` gains `--autonomous` mode, `nav-multi` SESSION_ID collision fixed, 12 execution-layer concept aliases added to the graph, `$SKILL_BASE_DIR` removed.

→ [Full release notes](./releases/RELEASE-NOTES-v6.4.0.md)

## [v6.3.0] — 2026-05-11

**Structured research output + autonomous Loop Mode.** `navigator-research` agent emits a `research_findings` JSON block that `research_to_graph.py` ingests into the knowledge graph — research persists across sessions. Loop Mode gains `iteration_approval`, `never_pause_on_stagnation`, and `stagnation_diversify_strategy` for overnight runs (inspired by karpathy/autoresearch's NEVER STOP directive). New ANTI-PATTERN #9: Context Flooding from Command Output. Four nav-graph reliability fixes (memory ID collision, file backing, concept aliases, batch I/O).

→ [Full release notes](./releases/RELEASE-NOTES-v6.3.0.md)

## [v6.2.2] — 2026-02-13

Portable `timeout` in `tests/test-monitor.sh` for macOS (GNU timeout → gtimeout → background-process fallback).

## [v6.2.1] — 2026-02-12

Release packaging bump.

## [v6.1.0] — 2026-01-23

**Multi-Agent Production.** Parallel Claude agents with visual dashboard. Natural language trigger ("Run multi-agent workflow for TASK-XX"). 5 role templates (orchestrator, implementer, tester, reviewer, documenter) with minimal context (~5k each). Real-time terminal dashboard. 3x faster than sequential. Reliability fixes for research tasks.

## [v6.0.0] — 2026-01-23

**Project Knowledge Graph.** Unified search across tasks, SOPs, system docs, and experiential memories. Patterns, pitfalls, decisions, and learnings persist across sessions. Query via "What do we know about X?". Auto-surfaces relevant memories on session start.

## [v5.9.0]

**Workflow Enforcement.** Mandatory WORKFLOW CHECK block before task responses. Loop Mode and Task Mode triggers auto-detected. Complexity scoring. Hook-based enforcement available.

## [v5.8.0]

**Auto-Update Project Sync.** Auto-update syncs project config after plugin update. Version drift detection. Restart prompt after mid-session updates.

## [v5.7.0] — 2026-01-22

**Feature Management.** View and toggle Navigator features via `nav-features` skill. Shows feature table on first session after install/update.

→ [Full release notes](./releases/RELEASE-NOTES-v5.7.0.md)

## [v5.6.0] — 2026-01-22

**Task Mode.** Unified workflow orchestration that coordinates between skills, loop mode, and direct execution. Auto-detects complexity and defers to appropriate handler.

→ [Full release notes](./releases/RELEASE-NOTES-v5.6.0.md)

## [v5.5.0]

**Auto-Update on Session Start.** Automatic plugin updates when newer version detected. Zero friction for daily releases.

## [v5.4.0]

**Code Simplification.** `nav-simplify` skill. Multi-Claude simplifier role. Autonomous completion integration. Loop Mode VERIFY phase integration. Based on Anthropic's internal code-simplifier pattern: clarity over brevity, functionality preserved absolutely.

## [v5.3.0]

**Task Verification Enhancement.** Verify/Done sections in task docs. `verify_extractor.py`. Multi-Claude Review integration.

## [v5.2.0] — 2026-01-20

**"Finish What You Start" positioning.** README rewrite, benefit-first documentation.

→ [Full release notes](./releases/RELEASE-NOTES-v5.2.0.md)

## [v5.1.0] — 2026-01-13

**Loop Mode.** Structured completion signals (NAVIGATOR_STATUS block). Dual-condition exit gates (heuristics + EXIT_SIGNAL). Stagnation detection circuit breaker. Phases INIT → RESEARCH → IMPL → VERIFY → COMPLETE. Inspired by Ralph's autonomous loop framework.

→ [Full release notes](./releases/RELEASE-NOTES-v5.1.0.md)

## [v5.0.0]

**Theory of Mind integration.** Based on Riedl & Weidmann 2025 research. `nav-profile` (bilateral modeling), `nav-diagnose` (quality detection), ToM verification checkpoints for high-stakes skills, enhanced markers capturing user intent.

## [v4.7.0] — 2025-12-09

Interactive onboarding skill (`nav-onboard`) with hands-on learning.

→ [Full release notes](./releases/RELEASE-NOTES-v4.7.0.md)

## [v4.6.0] — 2025-11-28

Native agents, token monitoring hooks, architecture optimization.

→ [Full release notes](./releases/RELEASE-NOTES-v4.6.0.md)

## [v4.5.0] — 2025-11-02

Multi-Claude workflow reliability fixes: retry logic, timeout monitoring, state persistence, workflow resume (`sub-claude-monitor.sh`, `resume-workflow.sh`). Enhanced marker verification with central logging.

→ [Full release notes](./releases/RELEASE-NOTES-v4.5.0.md)

## [v4.3.1] — 2025-11-01

Fixed template drift and professional pre-release upgrade flow. `nav-update-claude` now fetches templates from GitHub (version-matched). `nav-upgrade` presents interactive pre-release choice. Zero template drift.

→ [Full release notes](./releases/RELEASE-NOTES-v4.3.1.md)

## [v4.3.0] — 2025-11-01

Multi-Claude agentic workflow automation (experimental). Automated multi-Claude orchestration scripts for parallel execution. Task agents enabled in sub-Claude phases for 60-80% token savings. Failure reporting and recovery guidance.

→ [Full release notes](./releases/RELEASE-NOTES-v4.3.0.md)

## [v4.0.0] — 2025-10-24

**Major transformation: tool → complete framework.** Comprehensive education layer (learning guides, interactive examples, decision frameworks). Philosophical foundation documented (context efficiency manifesto, patterns, anti-patterns). Real metrics validation (`nav-stats` skill with efficiency scoring).

→ [Full release notes](./releases/RELEASE-NOTES-v4.0.0.md)

## [v3.4.0] — 2025-10-22

→ [Full release notes](./releases/RELEASE-NOTES-v3.4.0.md)

## [v3.3.1] — 2025-10-21

→ [Full release notes](./releases/RELEASE-NOTES-v3.3.1.md)

## [v3.3.0] — 2025-10-21

Visual Regression Integration Skill.

→ [Full release notes](./releases/RELEASE-NOTES-v3.3.0.md)

## [v3.2.0] — 2025-10-21

Product Design Skill with Figma MCP Integration.

→ [Full release notes](./releases/RELEASE-NOTES-v3.2.0.md)

## [v3.1.0] — 2025-10-20

OpenTelemetry Session Statistics. Replaced file-size estimation with official Claude Code metrics.

→ [Full release notes](./releases/RELEASE-NOTES-v3.1.0.md)

## [v3.0.0]

**Breaking: removed all slash commands (`/nav:*`).** Skills-only architecture. Use natural language: "Start my Navigator session".

---

For releases prior to v3.0, see the [GitHub Releases page](https://github.com/alekspetrov/navigator/releases).
