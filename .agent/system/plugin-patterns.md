# Claude Code Plugin Development Patterns

**Framework**: Claude Code Plugin System (skills, agents, hooks, mods)
**Updated**: 2026-10-05

---

## Claude Code Plugin Best Practices

### 1. Slash Command Design

The plugin ships no `commands/` directory. Every user-facing action is a skill
(`skills/<name>/SKILL.md`), invoked by natural language or as `/navigator:<name>`.

**Pattern**: Imperative instructions for the model, deterministic work in a helper

```markdown
---
name: nav-start
description: Short description plus the phrases that auto-invoke it
allowed-tools: Read, Bash
version: 1.0.0
---

# Skill Title

Clear instructions for what the model should do:

1. Step 1: Action
2. Step 2: Action (call `functions/helper.py` for anything that must be exact)
3. Step 3: Verification

Use code blocks for examples:
\`\`\`bash
example command
\`\`\`
```

**Good Example** (`skills/nav-init/SKILL.md`):
- Clear steps (Create X, Copy Y, Generate Z)
- Examples of expected output
- Error handling instructions
- Success criteria

**Bad Example**:
- Vague instructions ("Set up the project")
- No examples
- No error handling
- Unclear success state

**Helper functions**: when a step must be deterministic (toggle a config block, validate a
release, resolve a plugin path), the skill calls a script under `skills/<name>/functions/`
(`feature_manager.py`, `release_validator.py`, `onboarding_paths.py`) instead of asking the
model to do it by hand.

### 2. Template Design Patterns

**Universal Templates Pattern**:
```markdown
# [Project Name] - Configuration

**Context**: [Brief description]
**Tech Stack**: [Your stack]

[Universal workflow - same for all projects]

---

## Project-Specific Section

[Customizable content with examples]

**Example (Next.js)**:
- Pattern 1
- Pattern 2

**Example (Django)**:
- Pattern 1
- Pattern 2
```

**Key Principles**:
- Placeholders in `[brackets]`
- Universal sections (Navigator workflow, token optimization)
- Customizable sections (code standards, integrations)
- Multiple framework examples
- The template describes behavior; the hook runtime enforces it. `templates/CLAUDE.md` is
  47 lines because workflow gating, read guarding and completion gating live in ops, not
  in prose the model may skip.

### 3. Marketplace Manifest Pattern

**Location**: `.claude-plugin/plugin.json` (what the host loads) and
`.claude-plugin/marketplace.json` (the marketplace entry)

```json
// plugin.json
{
  "name": "navigator",
  "version": "8.2.8",
  "skills": ["./skills/nav-graph", "./skills/nav-brief", "..."],
  "hooks": {
    "UserPromptSubmit": [{ "hooks": [{
      "type": "command",
      "command": "sh -c 'f=\"${CLAUDE_PLUGIN_ROOT:-...}/hooks/nav_dispatch.py\"; ...'",
      "timeout": 5
    }] }]
  },
  "types": "./types/index.d.ts",
  "experimental": { "themes": "./themes/" }
}

// marketplace.json
{
  "name": "navigator-marketplace",
  "metadata": { "version": "8.2.8" },
  "plugins": [{ "name": "navigator", "source": "./" }]
}
```

**Versioning**:
- Five files carry the version: `plugin.json` `version`, `marketplace.json`
  `metadata.version`, the README badge, `CLAUDE.md` `**Navigator Version**`,
  `.agent/.nav-config.json` `version`
- `./scripts/bump-version.sh X.Y.Z` updates all five and runs the release validator
- Use semantic versioning; tag releases in Git; the tag push publishes the release

---

## Common Patterns

### Pattern: Multi-File Creation Command

**Use Case**: nav-init creates the entire `.agent/` structure

**Implementation**:
1. Create folder structure (mkdir -p)
2. Copy templates with customization
3. Generate dynamic content (scan codebase)
4. Create config file (`.agent/.nav-config.json`)
5. Add `.gitignore` entries line by line (re-running must not duplicate them)
6. Verify setup
7. Show usage instructions

**Template** (from `skills/nav-init/SKILL.md`):
```markdown
### Step 1: Create Structure
Create folders...

### Step 2: Copy Templates
Copy X to Y and customize...

### Step 3: Generate Docs
Scan codebase for...

### Step 4: Configure
Create config file...

### Step 7: Create .gitignore Entries
grep -qxF "$line" .gitignore || echo "$line" >> .gitignore
```

### Pattern: Conditional Logic in Commands

**Use Case**: Different instructions based on project type

**Implementation**:
```markdown
## Detect Project Type

**Scan for**:
- `package.json` → Node.js project
- `requirements.txt` → Python project
- `go.mod` → Go project

**If Node.js**:
Do X...

**If Python**:
Do Y...

**If Go**:
Do Z...
```

### Pattern: Template Placeholder System

**Standard Placeholders**:
- `[Project Name]` → Project title
- `[Brief project description]` → 1-2 sentences
- `[Your tech stack]` → Technology list
- `[Date]` → Current date
- `[Key architectural principle]` → Main pattern

**Customizable Sections**:
```markdown
## Code Standards

[Customize for your project]

**Example (Next.js)**:
- Server Components by default
- 'use client' only for interactivity

**Example (Django)**:
- Class-Based Views preferred
- Type hints on all functions
```

### Pattern: Documentation Navigator

**Purpose**: Index that loads first (~2k tokens)

**Structure**:
```markdown
# Project - Documentation Navigator

## Quick Start
- New developer? Read X, Y, Z
- Starting feature? Do A, B, C
- Debugging? Check 1, 2, 3

## Documentation Index
[List all docs with "When to read"]

## When to Read What
[Scenario-based loading guide]
```

**Token Optimization**:
- Navigator always loads first
- Other docs loaded on-demand
- Never load all docs at once

---

## Runtime Patterns

The workflow is enforced by a hook runtime, not by prose. These patterns are how that
runtime is built; `.agent/system/project-architecture.md` section 4a describes the
components, `hooks/ops/README.md` the op module protocol.

### Pattern: One Op, Two Runtimes

Every behavior is an op with one name, one config key and two implementations:
`hooks/ops/<name>.py` (v7 Python, stdlib only) and `hooks/mod/ops/<name>.ts` (v8 mod).
Sixteen ops exist this way. An op change lands in both files in the same commit.

**Registration**:
- Mod: `hooks/hooks.json` is `{"modules": ["./mod/register.tsx"]}`. `register.tsx`
  subscribes to `prompt.submit`, `tool.call` (Read, mutating tools, Bash) and the
  `classic.*` events (SessionStart, Stop, PreCompact, PostCompact, SubagentStart,
  PostToolUseFailure, TaskCreated, TaskCompleted, ConfigChange, Setup), registers the
  `/nav` command, and routes each event through `hooks/mod/ops/index.ts` `EVENT_OPS` and
  `hooks/mod/runner.ts`.
- Python fallback: `.claude-plugin/plugin.json` `hooks` registers the same thirteen events
  as command hooks, each `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/nav_dispatch.py <Event>`.
  `nav_dispatch.py` is a shim over `nav_hook_lib.runtime.dispatch`, which consults
  `hooks/nav_hook_lib/registry.py` `EVENT_OPS`: ordered `OpSpec(name, phase, matcher,
  config_key, budget_ms)` rows per event.

**Dispatch contract** (identical in `runtime._dispatch` and `runner.ts`):
- Phases run `gates → responders → injectors → recorders`; a blocking gate short-circuits
  the phases to its right; gates are exempt from the soft deadline
- Within one event, list order is merge order; every op's result merges into exactly one
  JSON document
- Under `PILOT_EXECUTOR` the merge belt strips every blocking key
  (`config.is_pilot_executor`, `config.ts isPilotExecutor`: one policy point each)
- A missing or crashing op is skipped with a `meta.op_errors` note, never a crash

**Ownership handoff**: `hooks/mod/owns.ts` lists `OWNED` (all sixteen ops) and
`MIN_CC = '2.1.287'`. On a supporting host the mod announces the active subset through
`NAVIGATOR_MOD_OWNS`; `nav_hook_lib.config.mod_owns` is the only reader of that variable,
`runtime._dispatch` skips owned ops and returns immediately when every op of an event is
owned. Below `MIN_CC`, or where policy blocks mods, the announcement is empty and Python
runs everything. An op that crashes `BREAKER_LIMIT = 3` times is disowned and re-announced
mid-session, so Python takes it over without a restart.

**Rule**: an op joins `OWNED` in the same commit as its parity tests. Never register an
event with no op module behind it (the v5.1.0 lesson recorded in `registry.py`).

### Pattern: One Shared State File

Both runtimes read and write `.agent/.nav-runtime-state.json` (schema 2) so an op handed
across the breaker or across host versions sees the same state. Sections: `session`,
`turn`, `reads`, `completion`, `brief`, `jit`, `tier1`, `profile`, `compact`, `judge`,
`meta`, each with its own TTL (`SECTION_TTLS` in `hooks/mod/lib/state.ts`,
`nav_hook_lib/state.py`). Python writes atomically (tmp + `os.replace`) under an `flock` on
`.agent/.nav-runtime-state.lock` and proceeds without the lock after about two seconds; the
mod takes no lock because its events run sequentially; both fail open on a torn file.

**Rule**: one read and one write per event. No op keeps its own state file.

### Pattern: Generated Parity Fixtures

Python is the source of truth until v9. `scripts/gen_mod_data.py` emits:
- `hooks/mod/lib/gen/*.gen.ts`: config defaults, sentinel tags, budget clamps, scoring and
  judge tables, so the mod never hand-copies a constant
- `hooks/mod/tests/fixtures/*.gen.ts`: Python outputs for a fixed corpus per op group
  (`scripts/mod_fixtures/{toolops,stopops,lifeops,rejects}.py`)

The kit tests (`hooks/mod/tests/*.test.ts`, run by `make mod-test` = `claude plugin test .`)
compare the TypeScript ports byte for byte against those fixtures. `make mod-gen-check`
(`gen_mod_data.py --check`) fails when any generated file is stale; `make test-all` chains
`test mod-gen-check mod-validate mod-test`. The same idea gates the v7 ports against v6:
`tests/golden/` holds recorded v6 hook output that `nav_dispatch.py` must byte-match.

**Rule**: after any change to a Python table or op, run `python3 scripts/gen_mod_data.py`
and commit the regenerated files. Never edit a `*.gen.ts` by hand.

### Pattern: Config Off-Switches with Local Overrides

Every op is gated on `<config_key>.enabled` in `.agent/.nav-config.json`; the key is the
`OpSpec.config_key` (`workflow_enforcer_hook`, `read_guard_hook`, `brief_hook`, `tier1`,
`reply_modes`, `stop_completion`, `session_start_hook`, `workflow_state_hook`,
`compact_hook`, `reject_log`, ...). Missing blocks default safe through
`nav_hook_lib.config.DEFAULTS`; new blocking or outbound features seed off
(`stop_completion.continue_enabled`, `tier1.enabled`, `judge.enabled`,
`deep_research.enabled`).

**Layering**: `config.load()` and its mirror `hooks/mod/lib/config.ts` `loadConfig()`
deep-merge `DEFAULTS < .agent/.nav-config.json < .agent/.nav-config.local.json`. The
shared file is committed; the `.local` file is gitignored (nav-init writes the entry) and
is what `nav-features disable <feature> --local` edits. A contributor turns a feature off
for themselves without touching the team's file.

**Rule**: a feature needs three things to exist: a `DEFAULTS` block, a `FEATURES` row in
`skills/nav-features/functions/feature_manager.py`, and a migrator version block. The mod
reads the defaults from `hooks/mod/lib/gen/config-defaults.gen.ts`, never from a copy.

### Pattern: Plugin-Relative Paths

The host sets `CLAUDE_PLUGIN_ROOT` to the installed plugin directory. Nothing in the plugin
hardcodes an install path:
- `plugin.json` hook commands resolve
  `${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/marketplaces/navigator-marketplace}` and
  append `/hooks/nav_dispatch.py`, guarded by `if [ -f "$f" ]` so a missing file is a
  silent no-op, never an error
- Skills that shell out resolve the root in three steps (TASK-97): `CLAUDE_PLUGIN_ROOT`
  (hooks, tests), then `~/.config/navigator/plugin-root` (one line the session_start op
  writes on every start from the root it knows, `NAVIGATOR_CONFIG_HOME` overrides), then
  the marketplace clone for a GitHub install that never ran a session start. The Bash tool
  never sees `CLAUDE_PLUGIN_ROOT`, so the file is the path every skill command takes. The
  snippet is identical in every `SKILL.md` and pinned by `tests/test_skill_plugin_root.py`;
  the flat cache path (`plugins/cache/navigator-marketplace/navigator`) is never a root —
  the cache is versioned (`.../navigator/<version>/`)
- `hooks/nav_hook_lib/memory.py` reads `CLAUDE_PLUGIN_ROOT` first and the legacy
  `CLAUDE_PLUGIN_DIR` only as a fallback (the latter was never set by the host; the switch
  shipped in v6.15.7)
- `tests/harness-conformance/probe_s6.py` re-checks the binding in manifest hook commands
  per host version

**Rule**: `CLAUDE_PLUGIN_ROOT` with a documented fallback, and the file-exists guard.
Skills use the two-line resolver, never a hand-written fallback.
Project files are always relative to the project root (`.agent/...`), never to the plugin.

### Pattern: Reject Log

Deterministic refusals leave a trace a human can read. A refusing op (read-guard deny,
prompt-gate block, stop-gate block) attaches `reject: {reason, evidence}` to its blocking
result; the runtime strips that key before the merge and appends one JSON line to
`.agent/.nav-rejects.jsonl` from a single point (`runtime._log_reject`, `runner.ts
logReject`; line shape in `hooks/nav_hook_lib/rejects.py`, mirrored in `hooks/mod/lib/rejects.ts`).
The file is rewritten to the newest 500 lines once it passes 600, is gitignored, never enters
the model's context, and is read by `grep`, `tail` and the `/nav` pane (`l`). Under Pilot
the refusal is suppressed from output but still logged with `suppressed: true`.
`reject_log.enabled` defaults on.

**Rule**: the op names the reason; the runtime owns the file. No op writes the log itself.

### Pattern: Reply-Modes Table

Per-person reply modes (ADHD shape, STE sentences) are rows in one table, served by one op.
`hooks/nav_hook_lib/reply_modes.py` holds `MODES`: frozen `Mode(key, label, config_key,
state_name, rule_block, extra_on, extra_off)` rows; `hooks/mod/lib/reply_modes.ts` holds
the same rows and the rule blocks are byte-identical. Toggle phrases are generated from
`key` (`<key> mode on|off`, `enable <key> mode`, `<key> status`, ...) with exact matching
only, so a prompt that merely mentions a mode never flips it.

The op `prompt_modes` (`hooks/ops/prompt_modes.py`, `hooks/mod/ops/prompt_modes.ts`,
responder phase) either answers a toggle phrase via `decision: block` at zero model
invocation and writes `~/.config/navigator/<state_name>.json` (`NAVIGATOR_CONFIG_HOME`
overrides the directory), or injects the rule blocks of every mode that resolves on, joined
in table order. Resolution per mode: repo pin `<config_key>.on: true|false` > personal file
> off; `<config_key>.enabled: false` hides the mode; `reply_modes.enabled` gates the op.
`MAX_TOTAL_BLOCK_CHARS = 1600` is asserted over the sum of all blocks. Subagents never see
the blocks.

**Adding a mode**: append a row to both tables, add `"<key>_mode": {"enabled": True,
"on": None}` to `DEFAULTS`, the migrator and `FEATURES`, run `gen_mod_data.py`, add a
phrase and block test (`.agent/tasks/TASK-93-reply-modes-ste.md`).

**Rule**: table order is policy (shape rules before sentence rules). No per-mode op, no
per-mode phrase list.

---

## Testing Patterns

### Manual Testing Checklist

```markdown
**For a new or changed op**:
- [ ] Python module + test_<name>.py under hooks/ops/
- [ ] TypeScript twin under hooks/mod/ops/, added to ops/index.ts and owns.ts OWNED
- [ ] python3 scripts/gen_mod_data.py run; fixtures committed
- [ ] make test-all green; NAVIGATOR_MOD_OWNS= make test green (fallback path)
- [ ] Config block in DEFAULTS, FEATURES row, migrator block

**For a new skill**:
- [ ] Frontmatter name + description with trigger phrases
- [ ] Deterministic steps in functions/*.py with tests
- [ ] Works in a clean test project

**For a new template**:
- [ ] Template copies correctly
- [ ] Placeholders clear and documented
- [ ] Examples provided for common stacks

**For a version update**:
- [ ] ./scripts/bump-version.sh X.Y.Z (five locations agree)
- [ ] Release notes under releases/, CHANGELOG entry
- [ ] Committed, pushed, tagged; release.yml published the release
```

### Test Project Setup

```bash
# Create clean test environment
mkdir -p ~/Projects/tmp/nav-test
cd ~/Projects/tmp/nav-test

# Point to the working tree
/plugin marketplace add file:///Users/aleks.petrov/Projects/startups/navigator
/plugin install navigator

# Run a skill, then verify
# "Initialize Navigator in this project"
ls -la .agent/
cat .agent/.nav-config.json
```

Tests that spawn the dispatcher set `NAVIGATOR_CONFIG_HOME` to a temp dir so the person's
`~/.config/navigator/` switches stay out. Harness conformance (`tests/harness-conformance/`,
probes S1 to S6) is live-driven per host version and cannot run in CI;
`make conformance-check` only asserts a results file exists for the installed version.

---

## Error Handling Patterns

### Pattern: Graceful Degradation

**Example**: Project type detection

```markdown
### Detect Project Type

**Try to find**:
- package.json → Use Node.js patterns
- requirements.txt → Use Python patterns

**If not found**:
- Use generic templates
- Prompt user for tech stack
- Continue with manual configuration
```

**Runtime example**: `nav_dispatch.py` catches `BaseException` and exits 0; a hook must
never brick the host. A torn state file reads as empty. A lock timeout proceeds without the
lock. The typed judge (`judge.enabled`) leaves the keyword scorers in charge on timeout, a
missing key or any error. The mod's breaker hands a crashing op back to Python.

### Pattern: User Choice on Conflicts

**Example**: Folder already exists

```markdown
### Issue: .agent/ folder already exists

**Ask user**:
1. Merge (keep existing + add missing)
2. Overwrite (replace with fresh)
3. Cancel

**Handle each choice**:
- Merge: Only create missing files
- Overwrite: Backup existing → Replace
- Cancel: Exit safely
```

---

## Distribution Patterns

### Pattern: GitHub-Based Distribution

**Setup**:
1. Public GitHub repository (`qf-studio/navigator`, MIT)
2. Both manifests under `.claude-plugin/`
3. Version tags for releases; `.github/workflows/release.yml` publishes the GitHub release
   from `releases/RELEASE-NOTES-vX.Y.Z.md` on tag push
4. Never `gh release create` locally; it races the workflow

**User Installation**:
```bash
/plugin marketplace add qf-studio/navigator
/plugin install navigator
```

**Updates**:
- Navigator never updates itself from a hook; the mod shows a read-only notice when a newer
  release exists (`hooks/mod/lib/update.ts`, `auto_update.check_interval_hours`)
- Users run `claude plugin update navigator@navigator-marketplace` and restart the host
- GitHub CDN caches for 1-2 hours; `file://` bypasses the cache

### Pattern: Local Development

**For Testing**:
```bash
/plugin marketplace add file:///absolute/path/to/navigator
/plugin install navigator
```

**Benefits**:
- Instant updates (no cache)
- Test before publishing
- Rapid iteration

The mod hot-reloads inside a session; Python hooks are read on every event. Skill paths
are cached at session start, so a changed SKILL.md needs a restart.

---

## Token Efficiency Patterns

### Pattern: Navigator-First Loading

**Always load first**: Navigator (~2k tokens)

**Then load on-demand**:
- Task doc (~3k) if working on feature
- System doc (~5k) if need architecture
- SOP (~2k) if need process guide

**Total**: 7-12k tokens vs 150k (loading all docs)

**Enforced**: fan-out manual Reads that should be a Task agent are denied by `read_guard`
(`read_guard_hook.strict_block`); injected context (brief, memories, reply-mode blocks) is
clamped by `hooks/nav_hook_lib/budget.py` and its mirror `hooks/mod/lib/budget.ts`.

### Pattern: Compact Strategy

**Run nav-compact after**:
- Isolated sub-task completed
- Documentation updated
- SOP created
- Switching between unrelated tasks

**Don't compact when**:
- In middle of implementation
- Context needed for next step
- Debugging complex issue

`compact_marker` writes a context marker on PreCompact and appends the host's compact
summary to it on PostCompact (`compact_hook.enabled`); the `/nav` pane shows the compact
verdict.

---

## Common Mistakes to Avoid

### ❌ Loading All Templates at Once

**Bad**:
```markdown
Read all files in templates/
```

**Good**:
```markdown
Copy templates/CLAUDE.md to project root
Only read what's needed for current task
```

### ❌ Project-Specific Content in Templates

**Bad**:
```markdown
Use Next.js 15 with React 19
```

**Good**:
```markdown
[Your tech stack]

**Example (Next.js)**: Next.js 15 + React 19
**Example (Django)**: Django 5.0 + PostgreSQL
```

### ❌ Hardcoded Paths

**Bad**:
```markdown
Copy to /Users/user/project/
python3 ~/.claude/plugins/.../hooks/nav_dispatch.py
```

**Good**:
```markdown
Copy to current working directory
Detect project root via .git/ or package.json
"${CLAUDE_PLUGIN_ROOT:-<documented fallback>}/hooks/nav_dispatch.py"
```

### ❌ Version Mismatch

**Bad**: editing one of the five version locations by hand

**Good**:
```bash
./scripts/bump-version.sh 8.3.0   # all five files, then the validator
```

### ❌ Editing a Generated Table

**Bad**: changing a constant in `hooks/mod/lib/gen/config-defaults.gen.ts`

**Good**: change `hooks/nav_hook_lib/config.py` `DEFAULTS`, run `python3 scripts/gen_mod_data.py`,
commit both. `make mod-gen-check` catches the drift.

### ❌ Changing One Runtime Only

**Bad**: a fix in `hooks/ops/stop_completion.py` with no change to
`hooks/mod/ops/stop_completion.ts`

**Good**: both files in one commit, fixtures regenerated, `make test-all` and
`NAVIGATOR_MOD_OWNS= make test` both green.

### ❌ Op-Private State or Log Files

**Bad**: a new op writing `.agent/.nav-<op>-state.json`

**Good**: a section in `.agent/.nav-runtime-state.json`; refusals through `reject`, never
a private log.

---

## Performance Optimization

### Template Size Optimization

- **Target**: <400 lines per template (`DEVELOPMENT-README.md` is 377, `CLAUDE.md` 47)
- **Technique**: Use examples instead of exhaustive content
- **Token goal**: <5k tokens when filled out

### Hook Execution Speed

- **Budgets**: `OpSpec.budget_ms` is advisory per op; the event-level soft deadline is what
  the runtime applies, and gates always run
- **Host timeouts** (`plugin.json`): SessionStart 10 s, PostToolUse 10 s, PreCompact 30 s,
  PostCompact 10 s, every other event 5 s
- **Technique**: ops import lazily, one state read and write per event; the only network
  calls are the judge (off by default, 1.5 s timeout) and the session-start release check
  (at most every `auto_update.check_interval_hours`, never under Pilot)

### Distribution Size

- **No external dependencies**: Python stdlib and the host's mod API only
- **Tracked**: 839 files, about 12 MB including release notes and docs

---

## Future Patterns

Not built. Recorded here as the shape such work would take.

### Modular Plugin Architecture

```
nav-core/         # Base Navigator functionality
nav-linear/       # Linear integration
nav-slack/        # Slack notifications
nav-nextjs/       # Next.js-specific templates
```

**Benefits**:
- Users install only what they need
- Smaller plugin sizes
- Community extensions

### Community Template System

```
templates/
├── core/          # Universal (from plugin)
├── nextjs/        # Next.js-specific (community)
├── django/        # Django-specific (community)
└── go/            # Go-specific (community)
```

**Distribution**: Separate GitHub repos, installable via plugin

---

**Last Updated**: 2026-10-07 (TASK-97 plugin-root resolver)
**Pattern Version**: 2.0
