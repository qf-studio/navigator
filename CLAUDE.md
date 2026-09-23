# Navigator: Finish What You Start

Sessions that last. AI that learns. Features that ship.

## Why This Exists

**The problem**: AI coding sessions crash at exchange 5-7. Context window fills with
documentation you never use.

**Navigator's solution**: Context engineering — load what you need, when you need it.
150k → 12k tokens (92% reduction).

**Result**: Sessions go 20+ exchanges. Features actually ship.

**Proven**: OpenTelemetry-verified, not estimates. Session efficiency scores 94/100.

**Version history**: see [CHANGELOG.md](./CHANGELOG.md) for the full release log, or
[releases/](./releases/) for per-version notes.

---

## Core Principle

**Context engineering beats bulk loading.**

Not "load everything just in case." Not "better safe than sorry."
Strategic loading saves 92% of context for actual work.

**New to this approach?** Read the philosophy:
- `.agent/philosophy/CONTEXT-EFFICIENCY.md` - Why Navigator exists
- `.agent/philosophy/ANTI-PATTERNS.md` - Common mistakes (upfront loading, etc.)
- `.agent/philosophy/PATTERNS.md` - What works and why

---

## Navigator Runtime (v7)

As of v7.0.0, Navigator's workflow is enforced by the hook runtime — a single dispatcher
(`hooks/nav_dispatch.py` → `nav_hook_lib.runtime.dispatch`) routing op modules in
`hooks/ops/`. The v6 prose mandates that used to live in this file — the WORKFLOW CHECK
block requirement, the session-start ritual, the forbidden-actions list, loop exit rules,
and intent-brief instructions — are retired as mandates. Each behavior lives on as an op
with a config off-switch in `.agent/.nav-config.json`:

| Behavior | Op | Off-switch |
|---|---|---|
| Workflow gating | prompt_gate | `workflow_enforcer_hook.enabled`, `.strict_block` |
| Intent briefs on ambiguous prompts | prompt_brief | `brief_hook.enabled` |
| Repeated-Read guard | read_guard | `read_guard_hook.enabled`, `.strict_block` |
| Session context injection | session_start | `session_start_hook.enabled` |
| Workflow/loop state recording | stop_state | `workflow_state_hook.enabled` |
| Completion gate (forced continuation) | stop_completion | `stop_completion.continue_enabled` |
| Tier-1 instant answers | prompt_tier1 | `tier1.enabled`, per rule via `tier1.rules` |
| Context markers around compaction | compact_marker | `compact_hook.enabled` |
| Typed judge behind the prompt scorers | judge (lib, used by prompt_gate + prompt_brief) | `judge.enabled` |

`stop_completion.continue_enabled`, `tier1.enabled` and `judge.enabled` ship OFF (new blocking
or outbound features seed off). Setting the `PILOT_EXECUTOR` environment variable disables interactive/blocking hook
behavior across all ops (single policy point: `nav_hook_lib.config.is_pilot_executor`).

The sections below describe those behaviors so humans and models know what to expect.
This text is documentation, not the mechanism.

### Session Start

"Start my Navigator session" remains the friendly way to begin: it loads
`.agent/DEVELOPMENT-README.md` (docs index, ~2k tokens) and current task context (~3k).
Session context is injected at session start — enforced by session_start (hook runtime);
this text is documentation, not the mechanism.

### Workflow Gating

Task-shaped prompts are scored for loop triggers ("run until done", "keep going",
"iterate until") and complexity (>= 0.5 → Task Mode; below → direct execution). The v6
"show a WORKFLOW CHECK block before every task" mandate is retired; gating happens on
UserPromptSubmit — enforced by prompt_gate (hook runtime); this text is documentation,
not the mechanism.

### Documentation Loading

Read `.agent/DEVELOPMENT-README.md` first, then lazy-load task/system/SOP docs on demand:
~12k tokens per session vs ~150k loading everything. Fan-out manual Reads that should be
Task agents are guarded on PreToolUse — enforced by read_guard (hook runtime); this text
is documentation, not the mechanism.

Update docs as you go: "Archive TASK-XX documentation" after a feature, "Create an SOP for
debugging [issue]" after solving something novel.

### Autonomous Task Completion

When implementation is complete, Navigator's finish protocol runs without human prompts:
simplify (if enabled), commit, archive the plan, close the ticket (if configured), create
a completion marker, suggest compact. Exceptions that ask first: secrets in uncommitted
files, multiple unrelated tasks touched, failing tests. Completion indicators are recorded
on Stop — enforced by stop_state (hook runtime); this text is documentation, not the
mechanism. When indicators show unfinished work and no explicit exit signal is present,
one continuation may be forced (capped by `stop_completion.max_continues`, off by default,
always off under `PILOT_EXECUTOR`) — enforced by stop_completion (hook runtime); this text
is documentation, not the mechanism.

### Loop Mode

"Run until done: ..." activates structured iteration: NAVIGATOR_STATUS blocks, progress
phases (INIT → RESEARCH → IMPL → VERIFY → COMPLETE), and stagnation detection. The v6
dual-condition exit rules are no longer prose mandates: exit evaluation reuses the
`exit_gate.evaluate_exit` indicator vocabulary and runs on Stop — enforced by stop_state
and stop_completion (hook runtime); this text is documentation, not the mechanism.
Configuration and full behavior: `loop_mode` block + `skills/nav-loop/SKILL.md`.

### Intent Briefs

Ambiguity ≠ complexity. Ambiguous task-shaped prompts get a NAV-BRIEF injection (plus
relevant knowledge-graph memories) prompting a one-screen intent brief — Goal / Scope /
Approach / Limits / Verify / Won't do / Contradiction — with max 2 open questions before
files change. Contradiction is the optional TRIZ row ("improving X worsens Y", usually
`none`); when declared, prior resolutions are queried from the knowledge graph before
Approach is filled (`brief_hook.contradiction_field` toggles the row). On substantial
tasks a declared contradiction hands off to `nav-triz`, which drafts three candidates from
different separation modes and recommends one (`skills/nav-triz/SKILL.md`).
Injection happens on UserPromptSubmit — enforced by prompt_brief (hook runtime); this text
is documentation, not the mechanism. Passthrough: "just do it", "quick fix", "skip the
brief". Full behavior: `skills/nav-brief/SKILL.md`.

### Tier-1 Instant Answers

A narrow exact-match command set (`nav stats`, `show features`, `list markers`,
`graph health`, `nav version`) can be answered deterministically with zero model
invocation — enforced by prompt_tier1 (hook runtime); this text is documentation, not the
mechanism. Off by default; toggle per rule via `tier1.rules`.

### Smart Compact

Compact after an isolated sub-task, a docs update, or a task switch; not mid-feature or
mid-debug. Context markers are captured around compaction — enforced by compact_marker
(hook runtime); this text is documentation, not the mechanism.

---

## Features Beyond the Runtime

### Theory of Mind (v5.0.0)

Bilateral modeling from Riedl & Weidmann 2025: verification checkpoints on high-stakes
skills, preference learning (nav-profile), quality-drop detection (nav-diagnose),
intent-capturing markers (nav-marker). Configure via the `tom_features` block.

### Code Simplification (v5.4.0)

Clarity over brevity, functionality preserved absolutely: flatten nested ternaries, early
returns, descriptive names. Runs post-implementation before commit, during Loop Mode
VERIFY, or on demand ("simplify this code"). Configure via the `simplification` block.

### Auto-Update (v5.5.0)

**Known gap (TASK-81, 2026-09-23)**: in v7 the SessionStart op only runs a read-only
version-drift check; nothing in the hook runtime updates the plugin. The updating path is
Step 1.5 of the nav-start skill, prose the model may or may not execute. Until TASK-81
ships, update by hand after each release:
`claude plugin update navigator@navigator-marketplace` (restart required afterward —
Claude Code caches skill paths at session start). `auto_update.enabled` currently only
controls the drift notice.

### Task Mode (v5.6.0)

Substantial work (complexity >= 0.5, no matching skill) gets phase guidance:
RESEARCH → PLAN → IMPL → VERIFY → COMPLETE. Skills keep their own workflows (Task Mode
defers); trivial tasks run direct. Activation scoring runs at prompt time — enforced by
prompt_gate (hook runtime); this text is documentation, not the mechanism.

### Project Knowledge Graph (v6.0.0)

One query interface across tasks, SOPs, system docs, markers, and experiential memories:
"What do we know about auth?", "Remember this pitfall: ...". Configure via the
`knowledge_graph` block; details in `skills/nav-graph/SKILL.md`.

| Type | Meaning |
|---|---|
| Pattern | "We use X for Y" |
| Pitfall | "Watch out for X" |
| Decision | "We chose X because Y" — may carry a TRIZ contradiction it resolved (`--action contradictions`) |
| Learning | "X usually means Y" |

### TRIZ Divergent Solving (v7.1.0 – v7.2.0)

Decisions may carry the contradiction they resolved (`--action contradictions` lists them).
When a brief declares a contradiction on a substantial task, or you ask "find a better
solution for X", `nav-triz` drafts three candidates from different separation modes, each
with a named downside, and recommends one. Details: `skills/nav-triz/SKILL.md`.

### Deep Research (v7.3.0 – v7.4.0)

"Deep research on X" runs a web research pipeline in subagents: three-lens search plan,
parallel fetchers into fenced source notes, one writer, one adversarial critic, one
patcher limited to Read+Edit, then a deterministic ship gate before typed Key findings
become graph memories with URLs as evidence, each tagged with its fetch date and
content-hash prefix so a later reader can tell which page version supported the claim.
Every source carries the search lens that found it (`canonical`, `breadth`,
`adversarial`, `gap`) into the Sources table, and no finding may rest on a single
`breadth` source. Reports are answer-first: a fixed Summary
block (Answer, bullets, counter-position), an At-a-glance table for comparisons, one
section per item, and a paragraph cap the gate enforces (`reference/REPORT-FORMAT.md`).
Ships OFF (`deep_research.enabled`); runs live under `.agent/research/<slug>/`. For
codebase questions use the `navigator-research` agent.
Details: `skills/nav-deep-research/SKILL.md`.

### Code Intelligence (v7.5.0)

When a language-server plugin from the official marketplace is enabled (pyright-lsp,
typescript-lsp, gopls-lsp, …), `navigator-research` uses the `LSP` tool for symbol
questions — references, definition, outline, hover — and falls back to Grep when the
tool is absent. Nothing bundled, no config key: the plugin's presence is the toggle.
Measured on this repo (TASK-76): a who-calls question dropped from 9 requests / 284k
context tokens to 5 / 142k with the complete call-site list; convention questions are
unaffected. `scripts/agent_tool_counts.py` gives real per-tool counts from a transcript.

---

### Typed Prompt Judge (v7.7.0)

The loop-trigger, complexity and ambiguity scorers are keyword matchers, and they misfire
on text that merely contains a trigger phrase (a pasted report header reading "Loop mode"
put a session into Loop Mode on 2026-09-19). With `judge.enabled`, one request per prompt
to a typed-decision model (TypeSafe Jev, `POST /v1/systemone`) answers eight questions at
once: is this a task, does it ask for autonomous iteration, complexity on a four-level
rubric, ambiguity on three, and whether scope / limits / approach / verification are
stated. Each axis overrides its heuristic only when decisive (noul outside the
`[noul_low, noul_high]` band, score confidence at `min_confidence` or above); undecided
axes, timeouts, a missing key or any error leave the heuristic in charge, byte for byte.
Measured on 60 labeled prompts (TASK-79): tier accuracy 38 → 53 of 60, task-shapedness
43 → 54, at ~0.7 s and ~$0.00003 per prompt. Ships OFF: the prompt leaves the machine
(secret-redacted, head-capped to `max_state_chars`). Enable with "enable judge"; the key
comes from `TYPESAFE_API_KEY` or `~/.config/typesafe/api_key`, never from the committed
config. Verify with `python3 hooks/nav_hook_lib/judge.py --check`; session start names the
key source or warns when none is found. Setup SOP:
`.agent/sops/integrations/typesafe-judge-setup.md`. Replay the eval with `scripts/judge_eval.py`.

---

## Agents vs Skills - Token Optimization Strategy

- **Agents** = research and exploration (separate context, 60-80% token savings):
  multi-file searches, unfamiliar code, pattern discovery.
- **Skills** = execution and consistency (predefined functions/templates): features
  following patterns, boilerplate, project conventions.

| Scenario | Use |
|---|---|
| "How does auth work?" | Agent |
| "Find all endpoints" | Agent |
| "Create component" | Skill |
| "Add endpoint" | Skill |
| "Generate boilerplate" | Skill |

Prefer a Task agent over manually Reading many files (fan-out Reads are guarded — enforced
by read_guard (hook runtime); this text is documentation, not the mechanism).
With an LSP plugin installed the research agent uses `LSP` for symbol questions and Grep
otherwise (`agents/navigator-research.md`, Phase 1.5).

---

## Workflow Discipline

- **Research before scaffolding**: For new projects/features, state phase
  (research / design / decomposition / implementation) in your first message
  and wait for confirmation before writing code.
- **Parallel for fan-out**: When the task is "apply pattern to N similar
  files", dispatch N parallel Task agents up front — do not start sequentially
  and wait to be corrected. (Proven: workshop restyle = 41% line reduction.)
- **Reframe, don't re-litigate**: When the user corrects with "No X, we are
  doing Y", drop X entirely from outputs. Do not include the rejected framing
  in new artifacts.
- **State hypothesis before exploring**: For debugging, name the suspected
  failure mode and the file/artifact you'll inspect first. If the user
  pinned a specific failure, do not wander into adjacent systems.

---

## Code Standards

- **Architecture**: KISS, DRY, SOLID principles
- **Components**: Framework best practices
- **TypeScript**: Strict mode (if applicable), no `any` without justification
- **Line Length**: Max 100 characters
- **Testing**: High coverage (backend 90%+, frontend 85%+)

Repository policy (plain repo etiquette, not runtime-enforced):
- No Claude Code mentions in commits/code
- No package.json modifications without approval
- Never commit secrets/API keys/.env files
- Don't delete tests without replacement

The v6 "Forbidden Actions" mandate list (skip-workflow-check, ignore-loop-triggers,
load-all-docs, etc.) is retired: those behaviors are config policy now — enforced by
prompt_gate and read_guard (hook runtime); this text is documentation, not the mechanism.

---

## Development Workflow

1. **Start Session** → session context injected (session_start op)
2. **Select Task** → Load task doc (`.agent/tasks/TASK-XX.md`)
3. **Research** → Task agent for multi-file searches
4. **Plan** → TodoWrite for complex tasks
5. **Implement** → Follow patterns, write tests
6. **Verify** → Run tests, confirm functionality
7. **Simplify** → Code clarity improvements (if enabled)
8. **Complete** → Commit, document, close ticket, create marker
9. **Compact** → Clear context for next task

---

## Documentation System

```
.agent/
├── DEVELOPMENT-README.md      # Navigator (always load first)
├── tasks/                     # Implementation plans
├── system/                    # Architecture docs
└── sops/                      # Standard Operating Procedures
    ├── integrations/
    ├── debugging/
    ├── development/
    └── deployment/
```

Load strategy: navigator (~2k) + current task (~3k) + system doc as needed (~5k) + SOP if
required (~2k) ≈ 12k tokens, vs ~150k loading everything.

Natural language commands:
- "Initialize Navigator in this project" (first-time setup)
- "Start my Navigator session" (begin work)
- "Archive TASK-XX documentation" (after feature)
- "Create an SOP for debugging [issue]" (after solving issue)
- "Create context marker [name]" (save point)
- "Clear context and preserve markers" (compact)

Slash commands (legacy, still work): `/nav:init`, `/nav:start`, `/nav:marker`,
`/nav:compact`

---

## Project Management Integration (Optional)

Supported: Linear (MCP), GitHub Issues (gh), Jira (API), GitLab (glab), or none.
If configured: read ticket → plan in `.agent/tasks/` → implement → update system docs →
archive + close on completion → notify team chat.

---

## Commit Guidelines

- Format: `type(scope): description`
- Reference ticket: `feat(feature): implement X TASK-XX`
- No Claude Code mentions
- Concise and descriptive

---

## Configuration

Navigator config in `.agent/.nav-config.json` (minimal subset shown; the live file also
carries `tom_features`, `loop_mode`, `task_mode`, `knowledge_graph`, `multi_agent`, and
the `*_hook` toggle blocks; missing blocks default safe via `nav_hook_lib.config.DEFAULTS`):

```json
{
  "version": "7.0.0",
  "project_management": "none",
  "task_prefix": "TASK",
  "team_chat": "none",
  "auto_load_navigator": true,
  "compact_strategy": "conservative",
  "simplification": { "enabled": true, "trigger": "post-implementation", "scope": "modified" },
  "auto_update": { "enabled": true, "check_interval_hours": 1 },
  "dispatcher": { "enabled": true },
  "tier1": { "enabled": false, "rules": {} },
  "stop_completion": { "enabled": false, "continue_enabled": false, "max_continues": 2 },
  "deep_research": { "enabled": false },
  "judge": { "enabled": false, "model": "jev-latest", "timeout_ms": 1500 }
}
```

---

## Success Metrics

- Context efficiency: <70% token usage typical, <12k tokens loaded, 10+ exchanges without
  compact, zero session restarts mid-feature.
- Documentation: 100% features have task docs, 90%+ integrations have SOPs, system docs
  updated within 24h, zero repeated mistakes.
- Productivity: 10x more work per token, docs found within 30 seconds, new developers
  productive in 48 hours.

---

**For complete Navigator documentation**: See `.agent/DEVELOPMENT-README.md`

**Last Updated**: 2026-09-23
**Navigator Version**: 7.7.1
