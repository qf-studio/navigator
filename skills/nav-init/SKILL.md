---
name: nav-init
description: Initialize Navigator documentation structure in a project. Auto-invokes when user says "Initialize Navigator", "Set up Navigator", "Create Navigator structure", or "Bootstrap Navigator".
allowed-tools: Write, Bash, Read, Glob
version: 1.0.0
triggers:
  - "initialize navigator"
  - "init navigator"
  - "set up navigator"
  - "setup navigator"
  - "create navigator structure"
  - "bootstrap navigator"
  - "start navigator project"
---

# Navigator Initialization Skill

## Purpose

Creates the Navigator documentation structure (`.agent/`) in a new project, copies templates, and sets up initial configuration.

## When This Skill Auto-Invokes

- "Initialize Navigator in this project"
- "Set up Navigator documentation structure"
- "Create .agent folder for Navigator"
- "Bootstrap Navigator for my project"

## What This Skill Does

1. **Checks if already initialized**: Prevents overwriting existing structure
2. **Creates `.agent/` directory structure**:
   ```
   .agent/
   ├── DEVELOPMENT-README.md
   ├── .nav-config.json
   ├── tasks/
   ├── system/
   ├── sops/
   │   ├── integrations/
   │   ├── debugging/
   │   ├── development/
   │   └── deployment/
   └── grafana/
       ├── docker-compose.yml
       ├── prometheus.yml
       ├── grafana-datasource.yml
       ├── grafana-dashboards.yml
       ├── navigator-dashboard.json
       └── README.md
   ```
3. **Copies templates**: DEVELOPMENT-README.md, config, Grafana setup
5. **Auto-detects project info**: Name, tech stack (from package.json if available)
6. **Updates CLAUDE.md**: Adds Navigator-specific instructions to project
7. **Creates .gitignore entries**: Excludes temporary Navigator files

## Execution Steps

### 1. Check if Already Initialized

```bash
if [ -d ".agent" ]; then
    echo "✅ Navigator already initialized in this project"
    echo ""
    echo "To start a session: 'Start my Navigator session'"
    echo "To view documentation: Read .agent/DEVELOPMENT-README.md"
    exit 0
fi
```

### 2. Detect Project Information

Read `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, or similar to extract:
- Project name
- Tech stack
- Dependencies

**Fallback**: Use current directory name if no config found.

### 3. Create Directory Structure

Use Write tool to create:
```
.agent/
.agent/tasks/
.agent/system/
.agent/sops/integrations/
.agent/sops/debugging/
.agent/sops/development/
.agent/sops/deployment/
.agent/grafana/
```

### 4. Copy Templates

Copy from plugin's `templates/` directory to `.agent/`:

**DEVELOPMENT-README.md**:
- Replace `${PROJECT_NAME}` with detected project name
- Replace `${TECH_STACK}` with detected stack
- Replace `${DATE}` with current date

**`.nav-config.json`**:
```json
{
  "version": "5.5.0",
  "project_name": "${PROJECT_NAME}",
  "tech_stack": "${TECH_STACK}",
  "project_management": "none",
  "task_prefix": "TASK",
  "task_id_source": "local",
  "team_chat": "none",
  "auto_load_navigator": true,
  "compact_strategy": "conservative",
  "auto_update": {
    "enabled": true,
    "check_interval_hours": 1
  }
}
```

**Grafana Setup**:
Copy all Grafana dashboard files to enable metrics visualization:

```bash
# Find plugin installation directory
PLUGIN_DIR="${HOME}/.claude/plugins/marketplaces/navigator-marketplace"

# Copy Grafana files if plugin has them
if [ -d "${PLUGIN_DIR}/.agent/grafana" ]; then
  cp -r "${PLUGIN_DIR}/.agent/grafana/"* .agent/grafana/
  echo "✓ Grafana dashboard installed"
else
  echo "⚠️  Grafana files not found in plugin"
fi
```

Files copied:
- docker-compose.yml (Grafana + Prometheus stack)
- prometheus.yml (scrape config for Claude Code metrics)
- grafana-datasource.yml (Prometheus datasource config)
- grafana-dashboards.yml (dashboard provider config)
- navigator-dashboard.json (10-panel Navigator metrics dashboard)
- README.md (setup instructions)

### 5. Update Project CLAUDE.md

If `CLAUDE.md` exists:
- Append Navigator-specific sections
- Keep existing project customizations

If `CLAUDE.md` doesn't exist:
- Copy `templates/CLAUDE.md` to project root
- Customize with project info

### 6. Claude Code Hooks (Plugin Manifest)

**Navigator's lifecycle hooks ship with the plugin manifest** (`.claude-plugin/plugin.json`'s top-level `hooks` field) starting v6.13.0+. They are *not* merged into the project's `.claude/settings.json` — Claude Code only substitutes `${CLAUDE_PLUGIN_ROOT}` for hooks declared in a plugin manifest, so merging them into user settings (the prior approach) produced broken commands like `/hooks/X.py`.

The plugin registers the following hooks automatically when the plugin is installed:

1. **SessionStart** — injects Navigator context (navigator + active marker + config + graph + profile) into the session, eliminating ~6 Read tool calls at start (v6.9.0+)
2. **PreCompact** — writes a context marker before manual or silent auto-compact (v6.10.0+)
3. **PostCompact** — appends Claude Code's compact summary to the marker (v6.10.0+)
4. **Stop** — silent workflow-state writer; records whether WORKFLOW CHECK / NAVIGATOR_STATUS appeared (v6.11.0+)
5. **UserPromptSubmit** — prompt_gate + prompt_brief ops (Loop/Task mode trigger detection + optional strict_block gate; intent-brief injection)
6. **PreToolUse(Read)** — read_guard op (bulk-read circuit breaker)
7. **PostToolUse(Edit|Write|Bash)** — token monitor (warns at 70% / 85% context usage)
8. **PostToolUse(Edit|Write)** — task→graph sync and profile correction sync (v6.11.0+)

**Nothing for nav-init to do here.** The skill no longer writes to `.claude/settings.json` for hooks.

```
⚠️  RESTART REQUIRED to activate hooks after plugin install/update.
   Claude Code caches plugin manifest hooks at session start.
```

**Opt-out**: Users can disable any hook via `.agent/.nav-config.json`:
```json
{
  "session_start_hook":    { "enabled": false },
  "compact_hook":          { "enabled": false },
  "workflow_state_hook":   { "enabled": false },
  "task_graph_sync_hook":  { "enabled": false },
  "profile_sync_hook":     { "enabled": false },
  "workflow_enforcer_hook":{ "enabled": false }
}
```

(The hooks themselves read this config and short-circuit when disabled, so no settings.json mutation is needed.)

### 7. Create .gitignore Entries

Add each of these lines to `.gitignore` unless it is already present (check line by
line — re-running nav-init must not duplicate entries):
```
# Navigator context markers
.context-markers/

# Navigator temporary files
.agent/.nav-temp/

# Navigator hook-runtime session state (regenerated every turn, never shared)
.agent/.nav-runtime-state.json
.agent/.nav-runtime-state.lock

# Navigator reject log (one line per refusal; local diagnostics, TASK-88)
.agent/.nav-rejects.jsonl

# Navigator personal config override (per contributor, see nav-features --local)
.agent/.nav-config.local.json

# Navigator onboarding state (per person; lives under ~/.config/navigator since v7.8)
.agent/onboarding/
```

Idempotent append, one command:
```bash
for line in ".context-markers/" ".agent/.nav-temp/" \
            ".agent/.nav-runtime-state.json" ".agent/.nav-runtime-state.lock" \
            ".agent/.nav-rejects.jsonl" \
            ".agent/.nav-config.local.json" ".agent/onboarding/"; do
  grep -qxF "$line" .gitignore 2>/dev/null || echo "$line" >> .gitignore
done
```

### 8. Success Message

```
✅ Navigator Initialized Successfully!

Created structure:
  📁 .agent/                    Navigator documentation
  📁 .agent/tasks/              Implementation plans
  📁 .agent/system/             Architecture docs
  📁 .agent/sops/               Standard procedures
  📁 .agent/grafana/            Metrics dashboard
  📄 .agent/.nav-config.json    Configuration
  📄 CLAUDE.md                  Updated with Navigator workflow

Next steps:
  1. Start session: "Start my Navigator session"
  2. Optional: Enable metrics - see .agent/sops/integrations/opentelemetry-setup.md
  3. Optional: Launch Grafana - cd .agent/grafana && docker compose up -d

Token monitoring is active - you'll be warned when approaching context limits.

Documentation: Read .agent/DEVELOPMENT-README.md
```

## Error Handling

**If `.agent/` exists**:
- Don't overwrite
- Show message: "Already initialized"

**If templates not found**:
- Error: "Navigator plugin templates missing. Reinstall plugin."

**If no write permissions**:
- Error: "Cannot create .agent/ directory. Check permissions."

## Predefined Functions

### `project_detector.py`

```python
def detect_project_info(cwd: str) -> dict:
    """
    Detect project name and tech stack from config files.

    Checks (in order):
    1. package.json (Node.js)
    2. pyproject.toml (Python)
    3. go.mod (Go)
    4. Cargo.toml (Rust)
    5. composer.json (PHP)
    6. Gemfile (Ruby)

    Returns:
        {
            "name": "project-name",
            "tech_stack": "Next.js, TypeScript, Prisma",
            "detected_from": "package.json"
        }
    """
```

### `template_customizer.py`

```python
def customize_template(template_content: str, project_info: dict) -> str:
    """
    Replace placeholders in template with project-specific values.

    Placeholders:
    - ${PROJECT_NAME}
    - ${TECH_STACK}
    - ${DATE}
    - ${YEAR}

    Returns customized template content.
    """
```

### `settings_merger.py`

```python
def merge(target_path: Path, fragment: dict) -> dict:
    """
    Idempotent JSON merge for .claude/settings.json.

    - If target doesn't exist: create from fragment.
    - If target exists: deep-merge `hooks` arrays by event name; dedupe entries
      by command string. Preserves user-defined hooks and other top-level keys.
    - Refuses to clobber invalid JSON (exits 2).
    """
```

**Status (v6.13.0+)**: Retained as general-purpose JSON merger for non-hook
keys (permissions, mcpServers, etc.) that downstream skills may want to
preserve. Navigator no longer passes a hooks fragment through it — hooks now
ship with the plugin manifest (`.claude-plugin/plugin.json`). The hook-merging
code path is dead-for-Navigator but kept intact for safety (existing call
sites that already pass non-hook fragments continue to work).

## Examples

### Example 1: New Next.js Project

**User says**: "Initialize Navigator in this project"

**Skill detects**:
- `package.json` exists
- Name: "my-saas-app"
- Dependencies: next, typescript, prisma

**Result**:
- `.agent/` created
- DEVELOPMENT-README.md shows: "Project: My SaaS App"
- DEVELOPMENT-README.md shows: "Tech Stack: Next.js, TypeScript, Prisma"
- .nav-config.json has project_name: "my-saas-app"

### Example 2: Python Project

**User says**: "Set up Navigator"

**Skill detects**:
- `pyproject.toml` exists
- Name: "ml-pipeline"
- Dependencies: fastapi, pydantic, sqlalchemy

**Result**:
- `.agent/` created
- Tech stack: "FastAPI, Pydantic, SQLAlchemy"

### Example 3: Already Initialized

**User says**: "Initialize Navigator"

**Skill checks**:
- `.agent/` directory exists

**Result**:
```
✅ Navigator already initialized in this project

To start a session: 'Start my Navigator session'
```

## Integration with Other Skills

**nav-start skill**:
- Checks for `.agent/DEVELOPMENT-README.md`
- If missing, suggests: "Initialize Navigator first"

**nav-task skill**:
- Creates tasks in `.agent/tasks/`
- Requires initialization

**nav-sop skill**:
- Creates SOPs in `.agent/sops/`
- Requires initialization

## Version History

- **1.0.0** (2025-01-20): Initial implementation
  - Auto-detection of project info
  - Template customization
  - Grafana setup included
  - Error handling for existing installations

## Notes

- This skill replaces the deleted `/nav:init` command from v2.x
- Templates are copied from plugin installation directory
- Project info detection is best-effort (falls back to directory name)
- Safe to run multiple times (won't overwrite existing structure)
