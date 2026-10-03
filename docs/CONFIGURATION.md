# Navigator Configuration Guide

Complete guide to configuring Navigator for your project and workflow.

---

## Configuration File

Navigator settings stored in `.agent/.nav-config.json`:

```json
{
  "version": "1.0.0",
  "project_management": "none",
  "task_prefix": "TASK",
  "team_chat": "none",
  "auto_load_navigator": true,
  "compact_strategy": "conservative"
}
```

Created automatically by `/nav:init`, customizable anytime.

---

## Project Management Integration

### Option 1: Linear (Recommended)

**Setup**:
1. Install Linear MCP:
   ```bash
   claude mcp add linear-server
   ```

2. Configure in `.nav-config.json`:
   ```json
   {
     "project_management": "linear",
     "task_prefix": "QF"
   }
   ```

3. Test connection:
   ```typescript
   list_issues({ assignee: "me" })
   ```

**Features**:
- Auto-pull ticket details
- Link docs to Linear issues
- Update ticket status from docs
- Create comments with SOP links

**Usage**:
```bash
/nav:update-doc feature QF-123
```

Automatically:
- Reads Linear issue QF-123
- Extracts title, description, acceptance criteria
- Creates implementation plan
- Links back to Linear

### Option 2: GitHub Issues

**Setup**:
1. Install GitHub CLI:
   ```bash
   brew install gh  # macOS
   # or https://cli.github.com
   ```

2. Authenticate:
   ```bash
   gh auth login
   ```

3. Configure in `.nav-config.json`:
   ```json
   {
     "project_management": "github",
     "task_prefix": "GH"
   }
   ```

4. Test:
   ```bash
   gh issue list
   ```

**Features**:
- Read issue details via gh CLI
- Link docs to GitHub issues
- Create comments with doc links

**Usage**:
```bash
/nav:update-doc feature GH-456
```

Uses `gh issue view 456` to get details.

### Option 3: Jira

**Setup**:
1. Configure Jira API:
   ```json
   {
     "project_management": "jira",
     "task_prefix": "PROJ",
     "jira": {
       "url": "https://yourcompany.atlassian.net",
       "email": "your@email.com",
       "api_token": "env:JIRA_API_TOKEN"
     }
   }
   ```

2. Set environment variable:
   ```bash
   export JIRA_API_TOKEN="your-api-token"
   ```

**Features**:
- Read issue details via API
- Link docs to Jira issues
- Update issue status

**Usage**:
```bash
/nav:update-doc feature PROJ-789
```

### Option 4: None (Manual)

**Setup**:
```json
{
  "project_management": "none",
  "task_prefix": "TASK"
}
```

**Features**:
- Manual documentation from conversation context
- No automatic ticket integration
- Simple, no dependencies

**Usage**:
```bash
/nav:update-doc feature TASK-123
```

You provide context manually, Navigator creates docs.

---

## Team Chat Integration

### Option 1: Slack (via MCP)

**Setup**:
1. Install Slack MCP:
   ```bash
   claude mcp add slack
   ```

2. Configure in `.nav-config.json`:
   ```json
   {
     "team_chat": "slack",
     "slack": {
       "engineering_channel": "C09HCNM09GV",
       "announcements_channel": "C09HF3HP554"
     }
   }
   ```

**Features**:
- Auto-notify team of doc updates
- Share SOPs to engineering channel
- Announce feature completions

**Triggers**:
- Feature complete → Post to announcements
- SOP created → Post to engineering
- Daily doc updates → Post to engineering

### Option 2: Discord

**Setup**:
1. Create Discord webhook
2. Configure in `.nav-config.json`:
   ```json
   {
     "team_chat": "discord",
     "discord": {
       "webhook_url": "env:DISCORD_WEBHOOK",
       "dev_channel_id": "123456789"
     }
   }
   ```

3. Set environment variable:
   ```bash
   export DISCORD_WEBHOOK="your-webhook-url"
   ```

**Features**:
- Post updates via webhook
- Share docs with team

### Option 3: None

**Setup**:
```json
{
  "team_chat": "none"
}
```

**Use when**:
- Solo developer
- Small team that doesn't need notifications
- Prefer manual updates

---

## Navigator Behavior

### Auto-Load Navigator

**Enabled** (default):
```json
{
  "auto_load_navigator": true
}
```

Every session automatically loads `.agent/DEVELOPMENT-README.md` (2k tokens).

**Disabled**:
```json
{
  "auto_load_navigator": false
}
```

You manually load navigator when needed. Saves 2k tokens if working on isolated task.

---

## Compact Strategy

### Conservative (Default)

**Config**:
```json
{
  "compact_strategy": "conservative",
  "compact_trigger_percent": 70
}
```

**Behavior**:
- Compact after major milestones only
- Trigger at 70%+ token usage
- Between unrelated epics

**Best for**: Deep work on single feature, complex debugging

### Aggressive

**Config**:
```json
{
  "compact_strategy": "aggressive",
  "compact_trigger_percent": 50
}
```

**Behavior**:
- Compact after every sub-task
- Trigger at 50%+ token usage
- Frequent context clearing

**Best for**: Multiple short tasks, exploratory work

### Manual

**Config**:
```json
{
  "compact_strategy": "manual"
}
```

**Behavior**:
- Never auto-suggest compact
- User runs `/nav:compact` explicitly

**Best for**: Experienced users who know when to compact

---

## Custom Templates

### Override Default Templates

Create `.agent/.templates/` with custom versions:

```
.agent/
├── .templates/
│   ├── task-template.md          # Custom task doc format
│   ├── sop-template.md           # Custom SOP format
│   └── system-template.md        # Custom system doc format
```

Navigator uses custom templates if they exist, otherwise uses plugin defaults.

### Example: Custom Task Template

```markdown
# TASK-XX: [Feature]

## Business Context
[Why this matters to business]

## Technical Implementation
[How to build it]

## Success Criteria
[How to verify]
```

Save to `.agent/.templates/task-template.md`, Navigator uses it automatically.

---

## Documentation Structure Customization

### Add Custom System Docs

Edit `.agent/DEVELOPMENT-README.md` to add custom docs:

```markdown
### System Architecture (`system/`)

#### [Project Architecture](./system/project-architecture.md)
...

#### [Database Schema](./system/database-schema.md)  # Custom
**When to read**: Working with database

**Contains**:
- Table structures
- Relationships
- Indexes
- Migration history
```

Then create:
```bash
/nav:update-doc system database
```

### Add Custom SOP Categories

Create new category in `.agent/sops/`:

```
.agent/sops/
├── integrations/
├── debugging/
├── development/
├── deployment/
└── security/          # Custom category
    └── auth-setup.md
```

Update navigator to include new category.

---

## Advanced Configuration

### Token Budget Customization

```json
{
  "token_budget": {
    "navigator_max": 2500,
    "task_doc_max": 3500,
    "system_doc_max": 5500,
    "sop_max": 2500,
    "session_target": 12000
  }
}
```

Navigator warns if docs exceed limits.

### Documentation Freshness

```json
{
  "freshness": {
    "system_docs_max_age_days": 7,
    "warn_outdated": true,
    "auto_regenerate": false
  }
}
```

Navigator warns if system docs haven't been updated in 7 days.

### Context Markers

```json
{
  "context_markers": {
    "enabled": true,
    "location": ".agent/.context-markers/",
    "auto_save_on_compact": true
  }
}
```

Automatically saves context markers when running `/nav:compact`.

---

## Environment Variables

### Recommended Setup

```bash
# .env (add to .gitignore)
LINEAR_API_KEY=your-linear-key
JIRA_API_TOKEN=your-jira-token
SLACK_WEBHOOK=your-slack-webhook
DISCORD_WEBHOOK=your-discord-webhook
```

Reference in config:
```json
{
  "linear": {
    "api_key": "env:LINEAR_API_KEY"
  }
}
```

**Never commit secrets to git!**

---

## Team Configuration

### Commit Configuration to Git

**Recommended**:
```gitignore
# .gitignore

# Don't commit secrets
.env
.env.local

# Share Navigator config with team
# .agent/.nav-config.json  # Commented out = committed
```

**Benefits**:
- Team uses same settings
- Consistent documentation structure
- Shared PM/chat integration

### Personal Configuration

Create `.agent/.nav-config.local.json`:

```json
{
  "extends": ".nav-config.json",
  "overrides": {
    "auto_load_navigator": false,
    "compact_strategy": "aggressive"
  }
}
```

Add to .gitignore:
```gitignore
.agent/.nav-config.local.json
```

---

## Migration Guide

### From Manual Documentation

**Before**: Docs scattered across README, wiki, Notion

**After**: Centralized in `.agent/`

**Steps**:
1. Run `/nav:init`
2. Copy existing docs to `.agent/system/`
3. Update navigator to index them
4. Use `/nav:update-doc` going forward

### From Other Documentation System

**Before**: Custom doc structure

**After**: Navigator structure

**Steps**:
1. Map existing docs to Navigator categories:
   - Implementation plans → `.agent/tasks/`
   - Architecture docs → `.agent/system/`
   - Procedures → `.agent/sops/`
2. Convert to Navigator templates
3. Update navigator

---

## Troubleshooting

### Configuration Not Loading

**Check**:
1. File exists: `.agent/.nav-config.json`
2. Valid JSON (no syntax errors)
3. Required fields present

**Fix**: Run `/nav:init` to regenerate

### Integration Not Working

**Linear**:
- Check: `linear-server` MCP installed
- Test: `list_issues({ assignee: "me" })`

**GitHub**:
- Check: `gh` CLI installed
- Test: `gh auth status`

**Jira**:
- Check: API token valid
- Test: API endpoint reachable

### Auto-Load Not Working

**Check**: `.nav-config.json`:
```json
{
  "auto_load_navigator": true
}
```

If false, navigator won't auto-load.

---

## Best Practices

### For Solo Developers

**Minimal config**:
```json
{
  "project_management": "none",
  "team_chat": "none",
  "auto_load_navigator": true,
  "compact_strategy": "conservative"
}
```

Simple, no integrations, focus on personal knowledge base.

### For Small Teams (2-5)

**Collaborative config**:
```json
{
  "project_management": "github",
  "team_chat": "discord",
  "auto_load_navigator": true,
  "compact_strategy": "conservative"
}
```

Commit config to git, share docs via GitHub.

### For Enterprises

**Full integration**:
```json
{
  "project_management": "linear",
  "team_chat": "slack",
  "auto_load_navigator": true,
  "compact_strategy": "conservative",
  "freshness": {
    "warn_outdated": true
  }
}
```

Full PM/chat integration, documentation freshness checks.

---

## Support

- **Issues**: [GitHub Issues](https://github.com/qf-studio/navigator/issues)
- **Discussions**: [Community](https://github.com/qf-studio/navigator/discussions)
- **Examples**: See [examples/](../examples/) for complete configs

---

**Start configuring**: Edit `.agent/.nav-config.json` after `/nav:init` 🚀
