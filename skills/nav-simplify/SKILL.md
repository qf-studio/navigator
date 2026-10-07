---
name: nav-simplify
description: Simplify and refine code for clarity, consistency, and maintainability while preserving all functionality. Focuses on recently modified code. Auto-invoke after implementation skills or on-demand.
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
version: 1.0.0
model: opus
---

# Navigator Code Simplification Skill

Simplify recently modified code for clarity, consistency, and maintainability while preserving exact functionality. Based on Anthropic's internal code-simplifier pattern.

## Core Principle

**Clarity over brevity. Functionality preserved absolutely.**

You are an expert code simplification specialist. Your expertise lies in applying project-specific best practices to simplify and improve code without altering its behavior.

## When to Invoke

**Auto-invoke after**:
- `backend-endpoint` skill completes
- `frontend-component` skill completes
- `database-migration` skill completes
- Any implementation task with code changes

**Manual invoke when user says**:
- "simplify this code"
- "review for clarity"
- "clean up recent changes"
- "refactor for readability"
- "simplify modified files"

**DO NOT invoke if**:
- No code was modified (docs-only changes)
- User explicitly says "skip simplification"
- Files are configuration only (JSON, YAML)

## Execution Steps

### Step 1: Identify Modified Code

**Option A: Git-based detection (preferred)**

```bash
# Get files modified in current session/commits
git diff --name-only HEAD~3 -- '*.ts' '*.tsx' '*.js' '*.jsx' '*.py' '*.go' '*.rs' 2>/dev/null || \
git diff --name-only --cached -- '*.ts' '*.tsx' '*.js' '*.jsx' '*.py' '*.go' '*.rs' 2>/dev/null || \
git diff --name-only -- '*.ts' '*.tsx' '*.js' '*.jsx' '*.py' '*.go' '*.rs'
```

**Option B: User-specified scope**

If user mentions specific files or directories, use those instead.

**Option C: Recent conversation context**

Analyze conversation for files that were written/edited in this session.

### Step 2: Load Simplification Configuration

Check for project-specific configuration:

```bash
if [ -f ".agent/.nav-config.json" ]; then
  python3 -c "import json; c=json.load(open('.agent/.nav-config.json')); s=c.get('simplification',{}); print('auto_apply=' + str(s.get('auto_apply', False)).lower()); print('enabled=' + str(s.get('enabled', True)).lower())"
fi
```

Default configuration:
```json
{
  "simplification": {
    "enabled": true,
    "trigger": "post-implementation",
    "scope": "modified",
    "model": "opus",
    "skip_patterns": ["*.test.*", "*.spec.*", "*.md", "*.json", "*.yaml"],
    "max_file_size": 50000,
    "auto_apply": false,
    "preserve_comments": true
  }
}
```

#### Autonomous context check (CRITICAL)

After loading config, determine the invocation mode:

**Autonomous** (no human in the loop):
- Invoked from `nav-loop` VERIFY or COMPLETE phase
- Invoked from `nav-workflow` COMPLETE phase
- `NAV_AUTONOMOUS=1` env var set
- Triggered by autonomous-completion protocol

**Interactive** (human reviewing):
- Direct user request ("simplify this code")
- Mid-implementation manual invocation

**Decision matrix**:

| `auto_apply` | Context | Action |
|---|---|---|
| `true` | autonomous | Apply directly (Step 7 silent) |
| `true` | interactive | Apply directly, show summary |
| `false` | autonomous | **SKIP simplification entirely** — emit warning, return to caller. Never pause an autonomous flow waiting for approval. |
| `false` | interactive | Show diff per file, prompt for approval |

When skipping in autonomous-mode-with-false, emit:
```
⚠️  nav-simplify skipped: auto_apply=false but invoked autonomously.
   To enable: set simplification.auto_apply=true in .agent/.nav-config.json
   To disable cleanly: set simplification.enabled=false
```

### Step 3: Read Project Standards

**Load from CLAUDE.md** (required):

```
Read(file_path: "CLAUDE.md")
```

Extract coding standards:
- Preferred patterns (function vs arrow, explicit returns)
- Naming conventions
- Import ordering
- Error handling patterns
- Framework-specific guidelines

### Step 4: Analyze Each File

For each modified file, analyze for simplification opportunities:

**Complexity Indicators** (look for):
- Deep nesting (> 3 levels)
- Long functions (> 50 lines)
- Redundant code patterns
- Unclear variable names
- Nested ternary operators
- Over-abstraction
- Dead code
- Inconsistent patterns

**Run analysis**:
```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
# Pass --scoring roi to enable cost/benefit gating (default: complexity,
# legacy behavior).
python3 "$PLUGIN_DIR/skills/nav-simplify/scripts/code_analyzer.py" --file "$file" --scoring roi
```

### Step 4.5: ROI Gate (when scoring.mode = "roi")

If `simplification.scoring.mode` is `"roi"` in `.agent/.nav-config.json` (or `--scoring roi` was passed), the analyzer emits `benefit_score`, `cost_score`, `roi_score`, and a `gate_action` field. Honor the gate:

| `gate_action` | Behavior |
|---|---|
| `skip` | Skip this file. Emit a one-line reason with ROI math. Continue to next file. |
| `suggest` | Force interactive mode for this file regardless of `auto_apply`. Show diff + reason. |
| `apply` | Proceed with Step 5+ as normal (honor `auto_apply`). |

**Skip emission format**:
```
⏭️  {file} — low ROI (B={B}/10, C={C}/10, ROI={R}). Skipping.
   {reason}
```

`{reason}` summarizes the dominant cost factor (e.g., "stable file (412 days), 8 import references" or "below skip_below threshold").

**Mode is opt-in.** When `scoring.mode == "complexity"` (default), Step 4.5 is a no-op and behavior is unchanged from prior versions.

### Step 5: Apply Simplification Rules

**Anthropic Simplification Rules**:

1. **Preserve Functionality**: Never change what the code does - only how it does it. All original features, outputs, and behaviors must remain intact.

2. **Apply Project Standards**: Follow CLAUDE.md coding standards:
   - Use ES modules with proper import sorting
   - Prefer `function` keyword over arrow functions (if project standard)
   - Use explicit return type annotations
   - Follow proper React/Vue component patterns
   - Use proper error handling patterns
   - Maintain consistent naming conventions

3. **Enhance Clarity**:
   - Reduce unnecessary complexity and nesting
   - Eliminate redundant code and abstractions
   - Improve readability through clear names
   - Consolidate related logic
   - Remove unnecessary comments that describe obvious code
   - **AVOID nested ternary operators** - use switch/if-else
   - **Choose clarity over brevity** - explicit > compact

4. **Maintain Balance** - Avoid over-simplification that could:
   - Reduce code clarity or maintainability
   - Create overly clever solutions
   - Combine too many concerns
   - Remove helpful abstractions
   - Prioritize "fewer lines" over readability
   - Make code harder to debug or extend

### Step 6: Generate Simplified Code

For each file with improvements:

1. Read current file content
2. Apply simplification rules
3. Verify functionality unchanged (logic review)
4. Generate diff or replacement

**Output format**:
```
📝 Simplifying: {filename}

Changes:
- [Line X] Flattened nested ternary to switch statement
- [Line Y] Extracted repeated logic to helper function
- [Line Z] Renamed `x` to `userCount` for clarity

Diff:
```diff
- const result = a ? (b ? c : d) : e;
+ let result;
+ if (a && b) {
+   result = c;
+ } else if (a) {
+   result = d;
+ } else {
+   result = e;
+ }
```
```

### Step 7: Apply Changes

Branch on the decision matrix from Step 2:

**Autonomous + `auto_apply: false`**: skip entirely, emit the warning, return.

**Autonomous + `auto_apply: true`**: apply each change directly with `Edit()`. Do not prompt.

**Interactive + `auto_apply: true`**: apply directly, show summary at end.

**Interactive + `auto_apply: false`**: show diff per file, prompt `Apply this change? [y/N]`, apply only on yes.

When applying:
```
Edit(
  file_path: "{file}",
  old_string: "{original}",
  new_string: "{simplified}"
)
```

### Step 8: Generate Summary

```
╔══════════════════════════════════════════════════════╗
║                                                      ║
║  🧹 Code Simplification Complete                     ║
║                                                      ║
╚══════════════════════════════════════════════════════╝

📊 Summary:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Files analyzed:    {N}
Files simplified:  {M}
Changes applied:   {X}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📝 Changes by category:
• Clarity improvements:     {count}
• Nesting reduction:        {count}
• Naming improvements:      {count}
• Pattern consolidation:    {count}

✅ Functionality: Preserved (no behavior changes)
✅ Standards: Applied from CLAUDE.md

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Predefined Functions

### scripts/code_analyzer.py

**Purpose**: Analyze code file for simplification opportunities

**Arguments**:
- `--file`: Path to file to analyze
- `--standards`: Path to CLAUDE.md (optional)
- `--output`: Output format (json, text)

**Returns**:
```json
{
  "file": "src/utils/auth.ts",
  "issues": [
    {
      "line": 45,
      "type": "nested_ternary",
      "severity": "medium",
      "suggestion": "Convert to switch or if-else"
    },
    {
      "line": 78,
      "type": "deep_nesting",
      "severity": "high",
      "depth": 5,
      "suggestion": "Extract to helper function"
    }
  ],
  "complexity_score": 7.2,
  "recommended_actions": 3
}
```

When invoked with `--scoring roi` (or `simplification.scoring.mode == "roi"`), the output additionally contains:

```json
{
  "benefit_score": 6.1,
  "cost_score": 4.3,
  "roi_score": 1.4,
  "gate_action": "suggest",
  "scoring_explanation": {
    "benefit": {"issue_density": 0.4, "severity_impact": 5.2, "in_active_diff": true},
    "cost": {"estimated_touch_lines": 32, "file_loc": 287, "days_since_modified": 12, "import_references": 3},
    "thresholds": {"skip_below": 0.5, "suggest_below": 1.5, "auto_apply_at": 1.5},
    "cost_floor": 0.5
  }
}
```

### scripts/simplification_rules.py

**Purpose**: Apply project-specific simplification rules

**Arguments**:
- `--file`: Path to file
- `--claude-md`: Path to CLAUDE.md for project standards
- `--dry-run`: Preview changes without applying

**Returns**: Simplified code with change annotations

### scripts/change_reporter.py

**Purpose**: Generate human-readable change summary

**Arguments**:
- `--changes`: JSON array of changes made
- `--format`: Output format (markdown, text, json)

**Returns**: Formatted change report

## Configuration Options

Add to `.agent/.nav-config.json`:

```json
{
  "simplification": {
    "enabled": true,
    "trigger": "post-implementation",
    "scope": "modified",
    "model": "opus",
    "skip_patterns": ["*.test.*", "*.spec.*"],
    "max_file_size": 50000,
    "auto_apply": false,
    "preserve_comments": true,
    "rules": {
      "avoid_nested_ternary": true,
      "max_nesting_depth": 3,
      "max_function_length": 50,
      "prefer_explicit_returns": true,
      "consolidate_imports": true
    },
    "scoring": {
      "mode": "complexity",
      "skip_below": 0.5,
      "suggest_below": 1.5,
      "auto_apply_at": 1.5,
      "cost_floor": 0.5
    }
  }
}
```

**Options**:
- `enabled`: Enable/disable simplification
- `trigger`: "manual" | "post-implementation" | "pre-commit"
- `scope`: "modified" | "staged" | "all"
- `model`: Preferred model for simplification (opus recommended)
- `skip_patterns`: Glob patterns to skip
- `max_file_size`: Skip files larger than this (bytes)
- `auto_apply`: Apply changes without confirmation
- `preserve_comments`: Keep meaningful comments
- `rules`: Specific simplification rules
- `scoring.mode`: `"complexity"` (legacy, default) or `"roi"` (opt-in cost/benefit gating)
- `scoring.skip_below`: ROI threshold below which files are skipped entirely
- `scoring.auto_apply_at`: ROI threshold at and above which auto-apply is honored
- `scoring.cost_floor`: Minimum cost denominator to prevent ROI explosions

## Integration Points

### Autonomous Completion

When integrated with autonomous completion protocol:

```
Implement → Verify → **Simplify** → Commit → Archive
```

Simplification runs automatically after verification passes, before commit.

### Loop Mode

Added to VERIFY phase completion indicators:
```
Completion Indicators:
  [x] Tests passing
  [x] Code simplified  ← Added
  [ ] Documentation updated
```

## Examples

### Example 1: Nested Ternary Simplification

**Before**:
```typescript
const status = isLoading ? 'loading' : hasError ? 'error' : isSuccess ? 'success' : 'idle';
```

**After**:
```typescript
function getStatus(isLoading: boolean, hasError: boolean, isSuccess: boolean): string {
  if (isLoading) return 'loading';
  if (hasError) return 'error';
  if (isSuccess) return 'success';
  return 'idle';
}

const status = getStatus(isLoading, hasError, isSuccess);
```

### Example 2: Deep Nesting Reduction

**Before**:
```typescript
function processUser(user: User) {
  if (user) {
    if (user.isActive) {
      if (user.hasPermission) {
        if (user.email) {
          sendEmail(user.email);
        }
      }
    }
  }
}
```

**After**:
```typescript
function processUser(user: User) {
  if (!user?.isActive) return;
  if (!user.hasPermission) return;
  if (!user.email) return;

  sendEmail(user.email);
}
```

### Example 3: Unclear Naming

**Before**:
```typescript
const x = users.filter(u => u.a && !u.d).map(u => u.n);
```

**After**:
```typescript
const activeUserNames = users
  .filter(user => user.isActive && !user.isDeleted)
  .map(user => user.name);
```

## Error Handling

**File too large**:
```
⚠️  Skipping {filename} ({size} bytes)
    Exceeds max_file_size limit ({limit} bytes)

    Override with: "simplify {filename} --force"
```

**No changes needed**:
```
✅ {filename} - Already follows best practices
   No simplification opportunities found.
```

**Functionality risk detected**:
```
⚠️  Potential behavior change detected in {filename}

    Line {N}: Changing conditional logic

    Review required before applying:
    [Show diff]

    Apply this change? [y/N]:
```

## Success Criteria

Simplification is successful when:
- [ ] All modified files analyzed
- [ ] Functionality preserved (verified)
- [ ] Project standards applied (from CLAUDE.md)
- [ ] No nested ternaries remain
- [ ] Nesting depth ≤ 3 levels
- [ ] Clear variable/function names
- [ ] Change summary generated

## Notes

- **Model preference**: Opus recommended for quality judgment
- **Scope default**: Only recently modified files (avoid churn)
- **Skip tests**: Test files usually follow different patterns
- **Preserve intent**: Comments explaining "why" should be kept
- **No over-optimization**: Clarity > minimal lines

This skill integrates Anthropic's internal code-simplifier pattern into Navigator's workflow, ensuring code quality before commit.
