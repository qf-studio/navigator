# Navigator Plugin - Project Architecture

**Tech Stack**: Python 3 (stdlib only) hook runtime, TypeScript mod, Markdown skills and
templates, JSON manifests and configuration, Bash scripts
**Updated**: 2026-10-05

---

## Technology Stack

### Core Technologies
- **Python 3 (stdlib only)**: the v7 hook runtime (`hooks/nav_dispatch.py`,
  `hooks/nav_hook_lib/`, `hooks/ops/`); the source of truth for every op until v9
- **TypeScript**: the v8 mod (`hooks/mod/`), one in-process module that runs the same ops,
  the `/nav` pane, the status band and the Pilot theme
- **Markdown**: skills (`skills/*/SKILL.md`), agents (`agents/*.md`), templates, docs
- **JSON**: plugin and marketplace manifests, `.agent/.nav-config.json`, runtime state
- **Bash**: release and version scripts under `scripts/`, the `Makefile`
- **Git + GitHub Actions**: version control, tag-triggered release publication

### Claude Code Plugin System
- **Plugin manifest**: `.claude-plugin/plugin.json` (skills, hooks, types, themes)
- **Marketplace**: `.claude-plugin/marketplace.json` (one plugin, source `./`)
- **Mod registration**: `hooks/hooks.json` (`modules: ["./mod/register.tsx"]`)
- **Skills**: `skills/<name>/SKILL.md` (31 directories); no `commands/` directory
- **Agents**: `agents/*.md` (six definitions)
- **Templates**: `templates/*.md` (five files, copied by nav-init)

---

## Project Structure

```
navigator/
├── .claude-plugin/              # Plugin manifest for marketplace
│   ├── plugin.json              # Skills, hooks (Python fallback), types, themes
│   ├── marketplace.json         # Marketplace entry (name, owner, version)
│   ├── README.md                # Marketplace description
│   └── types/                   # Engine-written mod types (laid on first load)
│
├── hooks/                       # The runtime
│   ├── hooks.json               # Mod registration: modules -> mod/register.tsx
│   ├── mod/                     # v8 mod: register.tsx, runner.ts, owns.ts, lib/, ops/, ui/
│   │   ├── lib/gen/             # Tables generated from Python (do not edit)
│   │   └── tests/               # Kit tests + generated parity fixtures
│   ├── nav_dispatch.py          # v7 Python dispatcher shim (fallback runtime)
│   ├── nav_hook_lib/            # runtime, registry, config, state, scoring, judge, ...
│   └── ops/                     # One Python module per op + its tests
│
├── skills/                      # 31 skills (nav-start, nav-init, nav-features, ...)
├── agents/                      # navigator-research, task-planner, deep-research-*
├── templates/                   # CLAUDE.md, DEVELOPMENT-README.md, task/sop/system
├── themes/                      # pilot.json, pilot.ghostty
├── types/                       # index.d.ts (pane/band state types)
├── scripts/                     # bump-version.sh, gen_mod_data.py, judge_eval.py, ...
├── tests/                       # golden/ (v6 corpus), harness-conformance/ (probes)
├── docs/                        # User and maintainer guides
├── releases/                    # Per-version release notes
├── examples/nextjs-saas/        # Example project
│
├── .agent/                      # Navigator for this repo (meta!)
│   ├── DEVELOPMENT-README.md    # Development navigator
│   ├── tasks/                   # Feature implementation plans (+ archive/)
│   ├── system/                  # Architecture docs
│   ├── sops/                    # Development SOPs
│   ├── grafana/                 # Local Prometheus/Grafana for the pane's session card
│   └── .nav-config.json         # Shared config (local override is gitignored)
│
├── CLAUDE.md                    # Navigator configuration for this repo
├── Makefile                     # test, mod-test, mod-gen-check, mod-validate, test-all
├── README.md                    # Public readme
└── CHANGELOG.md                 # Release log
```

---

## Key Components

### 1. Plugin Manifest (`.claude-plugin/marketplace.json`)

Two manifests carry the version, kept in sync by `scripts/bump-version.sh`:

```json
// .claude-plugin/plugin.json
{
  "name": "navigator",
  "version": "8.2.8",
  "skills": ["./skills/nav-graph", "..."],
  "hooks": { "SessionStart": [ /* python3 nav_dispatch.py SessionStart */ ], "...": [] },
  "types": "./types/index.d.ts",
  "experimental": { "themes": "./themes/" }
}

// .claude-plugin/marketplace.json
{
  "name": "navigator-marketplace",
  "metadata": { "version": "8.2.8" },
  "plugins": [{ "name": "navigator", "source": "./" }]
}
```

**Purpose**: `plugin.json` is what the host loads: the skill list, the Python fallback
hooks (thirteen events, each a `sh -c` command that resolves
`${CLAUDE_PLUGIN_ROOT}/hooks/nav_dispatch.py <Event>`), the pane types and the theme
directory. `marketplace.json` is the marketplace entry.

**Version locations** (`scripts/bump-version.sh <version>` updates all five and runs the
release validator): `plugin.json` `version`, `marketplace.json` `metadata.version`, the
README badge, `CLAUDE.md` `**Navigator Version**`, `.agent/.nav-config.json` `version`.

**Update when**: Releasing a new version (`skills/nav-release/SKILL.md`).

### 2. Slash Commands

The plugin registers no `commands` block and has no `commands/` directory. The invocation
surface is skills: each `skills/<name>/SKILL.md` carries a frontmatter `description` with
its trigger phrases, and the host exposes it as `/navigator:<name>`. Natural language is
the documented entry point ("Start my Navigator session", "Initialize Navigator in this
project", "Archive TASK-XX documentation").

**Format** (`skills/<name>/SKILL.md`):
```markdown
---
name: nav-start
description: Short description plus the phrases that auto-invoke it
---

# Skill Title

Step-by-step instructions, with `functions/*.py` helpers next to the SKILL.md when the
skill needs deterministic work (feature_manager.py, release_validator.py, ...).
```

**Core skills**: `nav-init` (one-time setup), `nav-start` (every session), `nav-task`
(create/archive task docs), `nav-sop`, `nav-marker`, `nav-compact`, `nav-features`
(toggle config blocks, `--local` for personal overrides), `nav-release`.

### 3. Templates (`templates/*.md`)

**Purpose**: Copied to user projects during nav-init

**Design Principles**:
- Universal (no project-specific content)
- Placeholder-based (`[Project Name]`, `[Tech Stack]`)
- Customizable sections marked clearly
- Examples for common stacks (Next.js, Django, Go)

**Templates**:
- `CLAUDE.md` (47 lines) → project configuration stub; the runtime, not this file,
  enforces the workflow
- `DEVELOPMENT-README.md` (377 lines) → documentation navigator
- `task-template.md` → feature planning
- `sop-template.md` → process documentation
- `system-template.md` → architecture documentation

### 4a. Hook runtime (`hooks/`)

Since v7 the workflow is enforced by a hook runtime, not prose; since v8.0.0 that runtime is a
Claude Code **mod** (`hooks/hooks.json` → `hooks/mod/register.tsx`, CC ≥ 2.1.287) with the v7
Python dispatcher (`hooks/nav_dispatch.py` → `nav_hook_lib.runtime`) as the fallback.

**Two runtimes, one op set.** `hooks/nav_hook_lib/registry.py` is the declarative
`EVENT_OPS` table: per hook event an ordered list of `OpSpec(name, phase, matcher,
config_key, budget_ms)`. Phases run `gates → responders → injectors → recorders`; a
blocking gate short-circuits the rest; results merge in registry order into one JSON
document. `hooks/mod/ops/index.ts` mirrors the same table for the mod, and
`hooks/mod/runner.ts` mirrors `runtime._dispatch` (phases, Pilot belt, per-op crash
isolation). Sixteen ops exist twice: `hooks/ops/<name>.py` and `hooks/mod/ops/<name>.ts`.

**Ownership.** `hooks/mod/owns.ts` lists the ops the mod runs (`OWNED`, all sixteen) and
announces the active subset through `NAVIGATOR_MOD_OWNS`. `config.mod_owns` is the only
reader of that variable on the Python side; `runtime._dispatch` skips owned ops and exits
immediately when every op of an event is owned. An op that crashes three times in a session
(`BREAKER_LIMIT`) is disowned and re-announced, so Python runs it for the rest of the session.
On a host older than 2.1.287 the mod owns nothing and Python runs everything.

**Shared state.** Both runtimes read and write `.agent/.nav-runtime-state.json` (schema 2:
`session`, `turn`, `reads`, `completion`, `brief`, `jit`, `tier1`, `profile`, `compact`,
`judge`, `meta`; `hooks/nav_hook_lib/state.py`, `hooks/mod/lib/state.ts`). Python writes it
atomically (tmp + rename, with a lock file); the mod has no lock because its events run
sequentially, and readers fail open on a torn file.

**Parity.** `scripts/gen_mod_data.py` emits config defaults, sentinel tags, budget clamps,
scoring and judge tables as TypeScript under `hooks/mod/lib/gen/` and Python outputs for a
fixed corpus under `hooks/mod/tests/fixtures/`; the kit tests (`hooks/mod/tests/*.test.ts`)
compare the ports byte for byte. `make mod-gen-check` fails when any generated file is stale;
`make test-all` = `test mod-gen-check mod-validate mod-test`.

**Reject log.** Every refusal either runtime makes (read-guard deny, prompt-gate block,
stop-gate block) is one JSON line in `.agent/.nav-rejects.jsonl` (TASK-88, v8.2.0): the op
attaches `reject: {reason, evidence}` to its blocking result, the runtime strips it and
appends the line from one point (`runtime._log_reject` / `runner.ts logReject`), rewritten
to the newest 500 lines once past 600, `reject_log.enabled` default on, `suppressed: true`
under Pilot. The file never enters the model's context; the `/nav` pane reads it behind `l`.

**What the mod adds**: the `/nav` pane (`hooks/mod/ui/nav.ts`, `route.ts`, `trip.ts`,
`palette.ts`, `status.ts`), the status band, the Pilot theme (`themes/`) and the read-only
update notice (`hooks/mod/lib/update.ts`).

Local-only files under `.agent/`: `.nav-runtime-state.json`, `.nav-runtime-state.lock`,
`.nav-dispatch-health.json`, `.nav-rejects.jsonl`, `.nav-config.local.json` (all in this
repo's `.gitignore`; nav-init writes the state, lock, rejects, local-config and onboarding
lines into user projects).
Details: `CLAUDE.md` "Navigator Runtime (v8)", `tasks/archive/TASK-84-v8-mod-runtime.md`,
`hooks/ops/README.md` (op module protocol).

### 4. Documentation (`docs/*.md`)

**Purpose**: User-facing and maintainer-facing guides

**Files**:
- `QUICK-START.md` → installation and first session
- `CONFIGURATION.md` → all configuration options
- `DEPLOYMENT.md` → how the plugin is packaged and published (maintainer-facing)
- `ARCHITECTURE.md`, `ARCHITECTURE-DIAGRAMS.md` → how skills, agents and docs combine
- `MIGRATION.md`, `upgrades/` → version-to-version upgrade guides
- `PERFORMANCE.md`, `GRAFANA-DASHBOARD.md`, `VERSION-CHECK.md`

**Target Audience**: Plugin users for the first three; maintainers for the rest

---

## Development Workflow

### Local Testing

```bash
# 1. Unit tests: Python ops, lib, dispatcher shim, shell tests
make test

# 2. Mod: regenerate tables + fixtures from Python, then validate and run the kit
python3 scripts/gen_mod_data.py
make mod-gen-check mod-validate mod-test     # needs the claude CLI >= 2.1.287
make test-all                                # all of the above

# 3. Load the working tree as a plugin in another project
/plugin marketplace add file:///Users/aleks.petrov/Projects/startups/navigator
/plugin install navigator

# 4. Harness conformance (live-driven, per host version; cannot run in CI)
make conformance-check                       # expects tests/harness-conformance/results/cc-<v>.json
```

Tests that spawn the dispatcher must set `NAVIGATOR_CONFIG_HOME` to a temp dir so the
person's `~/.config/navigator/` switches do not leak in. `NAVIGATOR_MOD_OWNS= make test`
runs the Python ops as if the mod owned nothing.

### Release Process

**Semantic Versioning**:
- Patch (8.2.8): bug fixes, docs updates
- Minor (8.3.0): new features, new ops or skills
- Major (9.0.0): breaking changes

**Steps** (`skills/nav-release/SKILL.md`, `.agent/sops/development/release-workflow.md`):
1. `./scripts/bump-version.sh X.Y.Z` (five version locations, validator asserts agreement)
2. Write `releases/RELEASE-NOTES-vX.Y.Z.md` and the CHANGELOG entry
3. `make test-all`; hook smoke test when hooks or `plugin.json` changed
4. Commit, `git push origin main`
5. `git tag -a vX.Y.Z` and `git push origin vX.Y.Z`; the tag triggers
   `.github/workflows/release.yml`, which publishes the GitHub release
6. Never run `gh release create` locally (it races the workflow)
7. `claude plugin update navigator@navigator-marketplace`, restart the host, sync the
   docs site

---

## Plugin Distribution

### GitHub Repository
- **URL**: https://github.com/qf-studio/navigator
- **Owner**: QuantFlow Studio
- **License**: MIT
- **Public**: Yes

### Installation by Users

```bash
# Add marketplace
/plugin marketplace add qf-studio/navigator

# Install plugin
/plugin install navigator

# Update later (Navigator never updates itself from a hook)
claude plugin update navigator@navigator-marketplace
```

Restart the host after an update; skill paths are cached at session start.

### Caching Issues

**Problem**: GitHub CDN caches for hours

**Solutions**:
- Specific commit: `qf-studio/navigator#<sha>`
- Local file: `file:///path/to/navigator`
- Wait 1-2 hours for CDN refresh

---

## Configuration System

### Plugin Config (`.agent/.nav-config.json`)

Created during nav-init in user projects. Minimal subset:

```json
{
  "version": "8.3.0",
  "project_management": "none",  // linear|github|jira|gitlab|none
  "task_prefix": "TASK",
  "task_id_source": "local",     // local (next TASK-NN) | github (gh issue first → GH-<n>)
  "team_chat": "none",           // slack|discord|teams|none
  "auto_load_navigator": true,
  "compact_strategy": "conservative",
  "reject_log": { "enabled": true },
  "reply_modes": { "enabled": true },
  "adhd_mode": { "enabled": true, "on": null },
  "ste_mode": { "enabled": true, "on": null }
}
```

**Purpose**: User project configuration, committed and shared with the team. Every op has
an off-switch here: the `OpSpec.config_key` block (`workflow_enforcer_hook`,
`read_guard_hook`, `brief_hook`, `tier1`, `reply_modes`, `stop_completion`,
`session_start_hook`, `workflow_state_hook`, `compact_hook`, ...) gates the op on
`<config_key>.enabled`. Missing blocks default safe via `nav_hook_lib.config.DEFAULTS`;
`stop_completion.continue_enabled`, `tier1.enabled`, `judge.enabled` and
`deep_research.enabled` seed off.

**Layering**: `hooks/nav_hook_lib/config.py` `load()` and its mirror
`hooks/mod/lib/config.ts` `loadConfig()` deep-merge `DEFAULTS < .agent/.nav-config.json <
.agent/.nav-config.local.json`.

**Personal override** (v7.8.0, GH-30): `.agent/.nav-config.local.json`, gitignored by nav-init,
merged last by both runtimes and by `skills/nav-features/functions/feature_manager.py`
(`--local` writes it). A contributor toggles features for themselves without touching the
shared file.

**Pilot posture**: `PILOT_EXECUTOR` set in the environment disables interactive and blocking
behavior in both runtimes (`nav_hook_lib.config.is_pilot_executor`, `hooks/mod/lib/config.ts`
`isPilotExecutor`); refusals are still logged with `suppressed: true`.

**Other per-person state outside the repo** (v7.8.0, GH-31): nav-onboard progress, workflow
guide and `.completed` live under `~/.config/navigator/onboarding/<repo-id>/`
(`skills/nav-onboard/functions/onboarding_paths.py`; `NAVIGATOR_ONBOARDING_HOME` overrides).

**Per-person switches** (v7.9.0 TASK-82, v8.3.0 TASK-93): `hooks/nav_hook_lib/personal.py`
keeps small JSON files under `~/.config/navigator/<name>.json` (`NAVIGATOR_CONFIG_HOME`
overrides). Reply modes are the users: `hooks/nav_hook_lib/reply_modes.py` holds the `MODES`
table (ADHD, STE), each row with its own file (`<key>-mode.json` `{"on": true}`, written when
the user says `<key> mode on`) and its own repo block `<key>_mode` that pins (`on: true|false`),
defers (`null`) or hides the mode (`enabled: false`); `reply_modes.enabled` gates the single
`prompt_modes` op. Resolution per mode: repo pin > personal file > off. Blocks stack in table
order. The mirror table is `hooks/mod/lib/reply_modes.ts`; the rule blocks are byte-identical
across runtimes, and `MAX_TOTAL_BLOCK_CHARS = 1600` is asserted by tests over their sum.
Adding a mode: `.agent/tasks/TASK-93-reply-modes-ste.md` "Adding a mode".

**Plugin root for skills** (v8.3.3 TASK-97): `CLAUDE_PLUGIN_ROOT` is set for hook commands
only; the Bash tool runs skill commands without it. The session_start op (Python
`_publish_plugin_root`, mod `publishPluginRoot`) writes the root it runs from to
`~/.config/navigator/plugin-root` (one line, atomic, after the `.agent` guard, best-effort)
on every start. Every `SKILL.md` resolves `PLUGIN_DIR` with the same two lines: env var →
that file → `~/.claude/plugins/marketplaces/navigator-marketplace`;
`tests/test_skill_plugin_root.py` pins the snippet. The flat cache path is never a root (the
cache is versioned, `.../navigator/<version>/`). On a directory-source marketplace the root
is the repo itself; on a GitHub install it is the versioned cache dir.

**Stop gate Bash classifier** (`hooks/ops/stop_completion.py` `_bash_readonly`, mirror
`hooks/mod/lib/stop-bash.ts` `bashReadonly`): a Bash-only turn is a task action only when some
command is not provably read-only, so the gate may over-fire but never under-fire. Quoted spans
are masked (TASK-94); `$(…)` substitutions are classified recursively; a redirect to anything
but `/dev/null` or a descriptor writes (the target ends at `;&|`, TASK-96); subshell, group
and function bodies are classified by what runs inside (TASK-96); heads resolve by allowlist,
by subcommand pair for `git`, `gh` and `claude plugin`, by flag for `curl`/`sed`, by target
for `make` (test-shaped only, the one relax-direction rule), by program text for `awk`, and
`python3 -m json.tool` is the only python form that reads. Unknown heads (`python3 -c`,
scripts) stay mutating by design; the tree digest catches a wrong read-only verdict on the
next Stop. `scripts/stop_gate_replay.py --days N` buckets recent calls by blame head so every
new rule comes with a measured flip count (TASK-95/96).

**Not committed to plugin repo**: Generated per-project

---

## Code Quality Standards

- **Python**: stdlib only under `hooks/` (guard test in `test_config.py`); every op in
  `hooks/ops/<name>.py` with `run(ctx) -> dict | None` and a `test_<name>.py` beside it
- **TypeScript**: strict mode; the mod's `lib/` is pure where it mirrors Python, I/O goes
  through the `Io` interface so the kit can drive it; `hooks/mod/lib/gen/` is never edited
- **Both runtimes change together**: an op change lands in `.py` and `.ts` in the same
  commit, then `python3 scripts/gen_mod_data.py`, then `make test-all`
- **Line length**: max 100 characters
- **Templates**: universal content only, placeholders in brackets
- **Skills**: clear step-by-step instructions; deterministic parts in `functions/*.py`
- **Repository policy**: no host-product mentions in commits, no secrets, no deleted tests
  without replacement

---

## Testing Strategy

### Manual Testing Checklist

- [ ] nav-init creates the `.agent/` structure, `CLAUDE.md`, `.nav-config.json` and the
      `.gitignore` entries in a clean project
- [ ] "Start my Navigator session" injects the session context (session_start op)
- [ ] A task-shaped prompt is gated; a repeated Read is denied and appears in
      `.agent/.nav-rejects.jsonl`
- [ ] `adhd mode on` / `ste mode on` answer with zero model turn and write
      `~/.config/navigator/<key>-mode.json`
- [ ] `/nav` opens the pane; the band shows phase, context and next action
- [ ] `NAVIGATOR_MOD_OWNS= make test` passes (Python fallback path)
- [ ] `make test-all` passes (generated tables fresh, manifest valid, kit green)

### Test Projects

- `/Users/aleks.petrov/Projects/tmp/nav-test` → Clean test environment
- `tests/golden/` → recorded v6 hook behavior; `nav_dispatch.py` output must byte-match
- `tests/harness-conformance/` → live probes S1–S6 per host version, results under
  `results/cc-<version>.json`

---

## Token Optimization

### Plugin Repo (This Codebase)
- CLAUDE.md: ~15k tokens
- .agent/DEVELOPMENT-README.md: ~2k tokens
- System docs: ~3k tokens each
- **Total**: ~23k tokens (on-demand loading)

### User Projects (After nav-init)
- CLAUDE.md: template is 47 lines; the workflow lives in the runtime, not the file
- .agent/DEVELOPMENT-README.md: ~2k tokens (read first)
- System docs: ~5k tokens each (lazy-loaded)
- Injected context per prompt: brief, memories and reply-mode blocks are budget-clamped
  (`hooks/nav_hook_lib/budget.py`, mirrored in `hooks/mod/lib/budget.ts`)
- **Total**: ~12k tokens for a typical session

---

## Performance Metrics

### Plugin Efficiency
- Template count: 5
- Skills: 31; agents: 6; ops: 16 (each in Python and TypeScript)
- Tracked files: 839, about 12 MB (release notes and docs included)
- No external runtime dependencies: Python stdlib and the host's mod API only

### User Impact
- Setup time: 2 minutes (nav-init)
- Token reduction: 92% (12k vs 150k)
- Context available: 86%+
- Session restarts: 0

---

## Future Enhancements

### Potential Features
- [ ] Integration-specific plugins (nav-linear, nav-slack)
- [ ] Further example projects beyond `examples/nextjs-saas`
- [ ] More reply modes as table rows (TASK-93 "Won't do": terse, non-native, demo)
- [ ] Submit to Anthropic official marketplace

### Extensibility
- Modular integration plugins
- Community-contributed templates
- Framework-specific extensions

---

**Last Updated**: 2026-10-07 (v8 runtime: mod + Python fallback, ownership, shared state,
parity fixtures, reject log; skills replace the commands directory; release via tag push;
config layering and reply-modes table TASK-93; plugin-root file TASK-97; stop gate Bash
classifier summary TASK-96)
**Version**: 8.3.3
