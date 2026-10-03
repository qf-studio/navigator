---
name: nav-sync-claude
description: Sync project CLAUDE.md to the installed Navigator version, preserving customizations. Use when user says "sync CLAUDE.md", "update CLAUDE.md", or when detecting outdated Navigator configuration.
allowed-tools: Read, Write, Edit, Bash
version: 1.0.0
---

# Navigator CLAUDE.md Updater Skill

Update project's CLAUDE.md to latest Navigator version (v3.1) while preserving project-specific customizations.

## When to Invoke

Invoke this skill when the user:
- Says "update my CLAUDE.md", "migrate CLAUDE.md to v3"
- Says "update Navigator configuration", "fix my CLAUDE.md"
- Mentions outdated commands like "/nav:start" and wants to upgrade
- Complains that Claude doesn't understand Navigator workflow

**DO NOT invoke** if:
- CLAUDE.md already references v3.1 and natural language commands
- User is editing CLAUDE.md for project-specific reasons (not Navigator updates)
- Working on plugin's root CLAUDE.md (not user projects)

## Execution Steps

### Step 1: Detect Current CLAUDE.md Version

Check if CLAUDE.md exists and detect version:

```bash
if [ ! -f "CLAUDE.md" ]; then
  echo "❌ No CLAUDE.md found in current directory"
  echo ""
  echo "Run 'Initialize Navigator in this project' first."
  exit 1
fi
```

Use `version_detector.py` to analyze CLAUDE.md:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/navigator-marketplace/navigator}"
[ -d "$PLUGIN_DIR" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-sync-claude/functions/version_detector.py" CLAUDE.md
```

This script checks for:
- Version markers (e.g., "Navigator Version: 3.1.0")
- Slash command references (`/nav:start`, `/nav:doc`, etc.)
- Skills vs commands language
- Natural language examples

**Outputs**:
- `outdated` - Has `/nav:` commands or v1/v2 markers
- `current` - Already v3.1 with natural language
- `unknown` - Can't determine (custom/non-Navigator file)

**If `current`**:
```
✅ CLAUDE.md is already up to date (v3.1)

No migration needed.
```
Exit successfully.

**If `unknown`**:
```
⚠️  CLAUDE.md doesn't appear to be a Navigator file

This might be a custom configuration. Manual review recommended.
Proceed with migration anyway? [y/N]
```

If user declines, exit. If accepts, continue.

### Step 2: Backup Current CLAUDE.md

Always create backup before modifying:

```bash
cp CLAUDE.md CLAUDE.md.backup
echo "📦 Backup created: CLAUDE.md.backup"
```

### Step 3: Extract Project-Specific Customizations

Use `claude_updater.py` to parse current CLAUDE.md:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/navigator-marketplace/navigator}"
[ -d "$PLUGIN_DIR" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-sync-claude/functions/claude_updater.py" extract CLAUDE.md > /tmp/nav-customizations.json
```

This extracts:
- **Project name** (from title)
- **Project description** (from Context section)
- **Tech stack** (languages, frameworks)
- **Code standards** (custom rules beyond Navigator defaults)
- **Forbidden actions** (project-specific restrictions)
- **PM tool configuration** (Linear, GitHub, Jira, etc.)
- **Custom sections** (anything not in Navigator template)

### Step 4: Generate Updated CLAUDE.md

Apply latest template with extracted customizations:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/navigator-marketplace/navigator}"
[ -d "$PLUGIN_DIR" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
# Template fetching now automatic via get_template_path():
# 1. Tries GitHub (version-matched)
# 2. Falls back to bundled if offline
python3 "$PLUGIN_DIR/skills/nav-sync-claude/functions/claude_updater.py" generate \
  --customizations /tmp/nav-customizations.json \
  --template "$PLUGIN_DIR/templates/CLAUDE.md" \
  --output CLAUDE.md
```

**Template Source Priority**:
1. **GitHub** (version-matched): Fetches from `https://raw.githubusercontent.com/qf-studio/navigator/v{version}/templates/CLAUDE.md`
   - Matches installed plugin version (e.g., v4.3.0)
   - Always up-to-date with release
   - Works with pre-releases
2. **Bundled** (fallback): Uses `templates/CLAUDE.md` from installed plugin
   - Offline fallback
   - Guaranteed availability

**What this does**:
1. Loads template (GitHub or bundled)
2. Replaces placeholders with extracted data
3. Preserves custom sections
4. Updates Navigator workflow to natural language
5. Removes slash command references
6. Adds skills explanation

### Step 5: Show Diff and Confirm

Display changes for user review:

```bash
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📝 CHANGES TO CLAUDE.MD"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Show unified diff
diff -u CLAUDE.md.backup CLAUDE.md || true

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
```

### Step 6: Verify and Commit

Show summary of changes:

```
✅ CLAUDE.md Updated to v3.1

Key changes:
  ✓ Removed slash command references (e.g., /nav:start)
  ✓ Added natural language examples ("Start my Navigator session")
  ✓ Added skills architecture explanation
  ✓ Updated Navigator workflow section
  ✓ Preserved your project-specific customizations:
    - Tech stack: [list]
    - Code standards: [count] custom rules
    - Forbidden actions: [count] custom rules

Backup saved: CLAUDE.md.backup

Next steps:
  1. Review changes: git diff CLAUDE.md
  2. Test: "Start my Navigator session" should work
  3. Commit: git add CLAUDE.md && git commit -m "chore: update CLAUDE.md to Navigator v3.1"
  4. Remove backup: rm CLAUDE.md.backup

Rollback if needed: mv CLAUDE.md.backup CLAUDE.md
```

### Step 7: Update .nav-config.json

If config exists, migrate to latest version with new sections:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/navigator-marketplace/navigator}"
[ -d "$PLUGIN_DIR" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
if [ -f ".agent/.nav-config.json" ]; then
  python3 "$PLUGIN_DIR/skills/nav-sync-claude/functions/config_migrator.py" .agent/.nav-config.json
fi
```

**What this does**:
1. Detects current config version
2. Adds missing sections based on version:
   - v5.4.0+: `simplification` config
   - v5.5.0+: `auto_update` config
   - v5.6.0+: `task_mode` config
3. Updates version marker to current

**Example output**:
```
✅ Config migrated: v5.4.0 → v5.6.0

Changes:
  + auto_update: (new section added)
  + task_mode: (new section added)
  ~ version: 5.4.0 → 5.6.0
```

**Dry run** (preview changes without applying):
```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/navigator-marketplace/navigator}"
[ -d "$PLUGIN_DIR" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-sync-claude/functions/config_migrator.py" .agent/.nav-config.json --dry-run
```

## Predefined Functions

### functions/version_detector.py

**Purpose**: Detect CLAUDE.md version (outdated, current, unknown)

**Usage**:
```bash
python3 version_detector.py CLAUDE.md
```

**Output**: Prints one of: `outdated`, `current`, `unknown`

**Exit codes**:
- 0: Success (version detected)
- 1: File not found
- 2: Parse error

**Detection logic**:
1. Check for version marker: `Navigator Version: X.X.X`
2. Check for slash commands: `/nav:start`, `/jitd:`, etc.
3. Check for natural language examples: `"Start my Navigator session"`
4. Check for skills section

**Heuristics**:
- Has `/nav:` → outdated
- Version < 3.0 → outdated
- Version >= 3.0 + natural language → current
- No version + no Navigator markers → unknown

### functions/claude_updater.py

**Purpose**: Extract customizations and generate updated CLAUDE.md

**Usage**:
```bash
# Extract customizations
python3 claude_updater.py extract CLAUDE.md > customizations.json

# Generate updated file
python3 claude_updater.py generate \
  --customizations customizations.json \
  --template ../../templates/CLAUDE.md \
  --output CLAUDE.md
```

**Extract mode** outputs JSON:
```json
{
  "project_name": "MyApp",
  "description": "Brief project description",
  "tech_stack": ["Next.js", "TypeScript", "PostgreSQL"],
  "code_standards": ["Custom rule 1", "Custom rule 2"],
  "forbidden_actions": ["Custom restriction 1"],
  "pm_tool": "github",
  "custom_sections": {
    "Deployment": "Custom deployment instructions..."
  }
}
```

**Generate mode**:
1. Loads template
2. Replaces `[Project Name]` with `project_name`
3. Replaces `[Brief project description]` with `description`
4. Replaces `[List your technologies...]` with `tech_stack`
5. Appends custom code standards
6. Appends custom forbidden actions
7. Inserts custom sections at end

### functions/config_migrator.py

**Purpose**: Migrate .nav-config.json to latest version, adding missing sections

**Usage**:
```bash
# Migrate config (applies changes)
python3 config_migrator.py .agent/.nav-config.json

# Preview changes without applying
python3 config_migrator.py .agent/.nav-config.json --dry-run

# JSON output
python3 config_migrator.py .agent/.nav-config.json --json
```

**Version-specific configs added**:
- v5.4.0: `simplification` (code clarity improvements)
- v5.5.0: `auto_update` (auto-update on session start)
- v5.6.0: `task_mode` (unified workflow orchestration)

**Output example**:
```
✅ Config migrated: v5.4.0 → v5.6.0

Changes:
  + auto_update: (new section added)
  + task_mode: (new section added)
  ~ version: 5.4.0 → 5.6.0
```

**Exit codes**:
- 0: Success (config migrated or already current)
- 1: Error (file not found, invalid JSON)

## Error Handling

**No CLAUDE.md found**:
```
❌ No CLAUDE.md found in current directory

This project doesn't appear to have Navigator initialized.
Run "Initialize Navigator in this project" first.
```

**Backup failed**:
```
❌ Failed to create backup: CLAUDE.md.backup

Check file permissions and disk space.
```

**Parse error**:
```
❌ Failed to parse CLAUDE.md

The file might be corrupted or have unusual formatting.
Manual review required.

Backup saved at: CLAUDE.md.backup
```

**Template not found**:
```
❌ Navigator template not found

This might be a plugin installation issue.
Try reinstalling Navigator plugin: /plugin update navigator
```

## Success Criteria

Migration is successful when:
- [ ] CLAUDE.md backed up successfully
- [ ] Version detected correctly
- [ ] Customizations extracted
- [ ] New file generated with v3.1 template
- [ ] Project-specific content preserved
- [ ] Diff shown to user for review
- [ ] Commit instructions provided

## Rollback Procedure

If migration fails or user is unhappy:

```bash
# Restore backup
mv CLAUDE.md.backup CLAUDE.md

# Or compare and manually fix
diff CLAUDE.md.backup CLAUDE.md
```

## Notes

This skill:
- **Preserves all customizations** (tech stack, standards, restrictions)
- **Non-destructive** (always creates backup)
- **Idempotent** (running multiple times is safe)
- **Transparent** (shows diff before finalizing)

**What gets updated**:
- Navigator version marker
- Slash commands → natural language
- Workflow examples
- Skills vs commands explanation
- Token optimization strategy

**What gets preserved**:
- Project name and description
- Tech stack
- Code standards
- Forbidden actions
- PM tool configuration
- Custom sections

## Related Skills

- **nav-init**: Initialize Navigator in new project (creates CLAUDE.md from scratch)
- **nav-start**: Start session (uses updated CLAUDE.md)
- **nav-task**: Task documentation (benefits from updated workflow)

## Examples

### Example 1: Simple Update

```
User: "Update my CLAUDE.md to v3.1"