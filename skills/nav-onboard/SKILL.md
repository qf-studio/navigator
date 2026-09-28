---
name: nav-onboard
description: Interactive onboarding for Navigator - learn by doing. Auto-invoke when user says "onboard me", "teach me Navigator", "how do I use Navigator", "Navigator tutorial", "learn Navigator", "new to Navigator", or "what skills should I use".
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion
version: 1.0.0
---

# Navigator Onboarding Skill

Interactive, hands-on learning experience for Navigator. Users complete actual tasks to learn workflows, not just read documentation.

## When to Invoke

Invoke this skill when the user:
- Says "onboard me", "teach me Navigator"
- Says "how do I use Navigator", "Navigator tutorial"
- Says "learn Navigator", "new to Navigator"
- Asks "what skills should I use"
- Says "help me get started with Navigator"
- First time using Navigator after init

**DO NOT invoke** if:
- User is asking about a specific skill (invoke that skill instead)
- User already completed onboarding (`.completed` exists in their personal onboarding
  dir — see Step 1; state is per person, never in the repo, since v7.8.0 / GH-31)
- User explicitly asks to skip onboarding

## Two Learning Flows

### Quick Start (~15 min)
For users who want to be productive fast:
- 4 essential skills with hands-on practice
- Generates personalized workflow guide
- Minimal philosophy, maximum doing

### Full Education (~45 min)
For users who want comprehensive understanding:
- Philosophy primer (context efficiency principles)
- All 5 essential skills with practice
- Project-specific development skills
- Complete workflow mastery

## Execution Steps

### Step 1: Resolve the Personal Onboarding Dir and Check Previous Onboarding

Onboarding state (progress, workflow guide, completion marker) is **per person and per
repo**, stored under `~/.config/navigator/onboarding/<repo-id>/` (or
`$NAVIGATOR_ONBOARDING_HOME/<repo-id>/`), never inside the repository. Two contributors on
the same repo each get their own run; nothing lands in tracked paths (GH-31).

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/navigator-marketplace/navigator}"
[ -d "$PLUGIN_DIR" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
NAV_ONBOARD_DIR=$(python3 "$PLUGIN_DIR/skills/nav-onboard/functions/onboarding_paths.py" .)
if [ -f "$NAV_ONBOARD_DIR/.completed" ]; then
  echo "COMPLETED"
else
  echo "NOT_COMPLETED"
fi
```

**If completed**: Ask if user wants to re-do onboarding or just view their workflow guide
(`$NAV_ONBOARD_DIR/MY-WORKFLOW.md`).

**If the project has its own setup skill** (e.g. `.claude/skills/onboard/` or a
`SKILL.md` whose name contains "onboard"/"setup"), mention it and suggest running it
first; Navigator onboarding teaches the workflow, not the project.

**Legacy state**: a pre-v7.8.0 `.agent/onboarding/` in the repo is ignored (nav-init
gitignores it now). Do not read `.completed` from there.

### Step 2: Analyze Project

Run project analyzer to detect tech stack:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/navigator-marketplace/navigator}"
[ -d "$PLUGIN_DIR" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-onboard/functions/project_analyzer.py"
```

**Output structure**:
```json
{
  "project_name": "my-app",
  "project_type": "fullstack",
  "frontend_framework": "Next.js",
  "backend_framework": "Express",
  "database": "PostgreSQL",
  "testing_framework": "Jest",
  "has_navigator": true
}
```

### Step 3: Generate Skill Recommendations

Run skill recommender based on project analysis:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/navigator-marketplace/navigator}"
[ -d "$PLUGIN_DIR" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-onboard/functions/skill_recommender.py"
```

**Output structure**:
```json
{
  "essential_skills": ["nav-start", "nav-marker", "nav-task", "nav-sop", "nav-compact"],
  "recommended_skills": ["frontend-component", "backend-endpoint"],
  "optional_skills": ["visual-regression", "product-design"],
  "workflow_order": ["nav-start", "nav-task", "frontend-component", "nav-sop", "nav-marker", "nav-compact"]
}
```

### Step 4: Present Flow Choice

Show detection results and ask user to choose flow:

```
Navigator Onboarding

I've analyzed your project:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Project: [project_name]
Type: [project_type]
Stack: [tech_stack]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Based on your project, I recommend these skills:

Essential (all projects):
  1. nav-start     - Start sessions efficiently
  2. nav-marker    - Save progress checkpoints
  3. nav-task      - Document what you build
  4. nav-sop       - Capture solutions for reuse
  5. nav-compact   - Clear context without losing work

For your [project_type] project:
  6. [recommended_skill_1] - [description]
  7. [recommended_skill_2] - [description]

Choose your learning path:

[Q] Quick Start (~15 min)
    Learn 4 essential skills with hands-on practice
    Get productive immediately

[F] Full Education (~45 min)
    Complete Navigator mastery
    Philosophy + all relevant skills + practice

Your choice [Q/F]:
```

### Step 5: Initialize Progress Tracking

Create the personal onboarding directory and progress file (`$NAV_ONBOARD_DIR` from
Step 1; the functions below create it themselves):

```bash
mkdir -p "$NAV_ONBOARD_DIR"
```

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/navigator-marketplace/navigator}"
[ -d "$PLUGIN_DIR" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
# Run progress_tracker.py init
python3 "$PLUGIN_DIR/skills/nav-onboard/functions/progress_tracker.py" init [flow_type] [project_type]
```

Creates `$NAV_ONBOARD_DIR/PROGRESS.md`:
```markdown
# Navigator Onboarding Progress

**Started**: [date]
**Flow**: Quick Start | Full Education
**Project**: [name] ([type])

---

## Essential Skills

| # | Skill | Status | Completed | Notes |
|---|-------|--------|-----------|-------|
| 1 | nav-start | pending | - | - |
| 2 | nav-marker | pending | - | - |
| 3 | nav-task | pending | - | - |
| 4 | nav-sop | pending | - | - |
| 5 | nav-compact | pending | - | - |

## Development Skills

| # | Skill | Status | Completed | Notes |
|---|-------|--------|-----------|-------|
| 6 | [skill] | pending | - | - |

---

**Progress**: 0/[total] (0%)
**Next Task**: nav-start

*Last Updated: [timestamp]*
```

### Step 6: Execute Learning Tasks

For each skill in the curriculum, follow this pattern:

#### 6.1: Present Task

Read the learning task file and present to user:

```bash
cat skills/nav-onboard/learning-tasks/[task-file].md
```

Present in this format:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TASK [N]/[TOTAL]: [Skill Name]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Task description and context]

DO THIS NOW:
━━━━━━━━━━━
Type: "[exact command to type]"

WHAT SHOULD HAPPEN:
━━━━━━━━━━━━━━━━━━━
[Expected output description]

Ready? Type the command above, then say "done" when complete.
```

#### 6.2: Wait for User Action

User types the command (e.g., "Start my Navigator session").

The relevant skill executes automatically.

User says "done" or similar when ready to continue.

#### 6.3: Validate Completion

Run task validator:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/navigator-marketplace/navigator}"
[ -d "$PLUGIN_DIR" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-onboard/functions/task_validator.py" [skill_name]
```

**Validation checks per skill**:
- `nav-start`: User confirmation (session displayed)
- `nav-marker`: File exists in `.agent/.context-markers/`
- `nav-task`: File exists in `.agent/tasks/`
- `nav-sop`: File exists in `.agent/sops/`
- `nav-compact`: `.active` file exists in `.context-markers/`

#### 6.4: Update Progress

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/navigator-marketplace/navigator}"
[ -d "$PLUGIN_DIR" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-onboard/functions/progress_tracker.py" update [skill_name] completed "[notes]"
```

#### 6.5: Show Progress and Continue

```
✅ Task Complete: [skill_name]

Progress: [N]/[TOTAL] ([percentage]%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[progress bar visualization]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PRO TIP:
[Skill-specific best practice]

Next up: [next_skill_name]

Continue? [Y/n]
```

### Step 7: Generate Personalized Workflow

After all tasks complete, generate workflow guide:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/navigator-marketplace/navigator}"
[ -d "$PLUGIN_DIR" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-onboard/functions/workflow_generator.py"
```

Creates `$NAV_ONBOARD_DIR/MY-WORKFLOW.md` with:
- Project-specific workflow diagram
- Daily workflow checklist
- Quick reference table with all skill triggers
- Best practices for user's stack

### Step 8: Completion Summary

Mark onboarding complete and show summary:

```bash
date -u +%Y-%m-%dT%H:%M:%SZ > "$NAV_ONBOARD_DIR/.completed"
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎉 NAVIGATOR ONBOARDING COMPLETE!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You've learned:
✅ nav-start     - Start sessions efficiently
✅ nav-marker    - Save progress checkpoints
✅ nav-task      - Document implementations
✅ nav-sop       - Capture solutions
✅ nav-compact   - Manage context
✅ [dev skills]  - Build [project_type] features

Your personalized workflow:
📄 $NAV_ONBOARD_DIR/MY-WORKFLOW.md   (personal, outside the repo)

Quick Reference:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
| Action              | Say This                         |
|---------------------|----------------------------------|
| Start session       | "Start my Navigator session"     |
| Save progress       | "Create checkpoint [name]"       |
| Document feature    | "Create task doc for [feature]"  |
| Capture solution    | "Create SOP for [issue]"         |
| Clear context       | "Clear context and preserve"     |
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

What's Next?
1. Start your first real session: "Start my Navigator session"
2. Keep MY-WORKFLOW.md open as reference
3. Create markers before breaks
4. Document what you build

Happy coding! 🚀
```

## Learning Tasks Reference

### Essential Skills (All Projects)

| Order | Skill | Task File | What User Does | Validation |
|-------|-------|-----------|----------------|------------|
| 1 | nav-start | 01-nav-start.md | "Start my Navigator session" | Session summary displayed |
| 2 | nav-marker | 02-nav-marker.md | "Create checkpoint learning-test" | File in `.context-markers/` |
| 3 | nav-task | 03-nav-task.md | "Create task doc for learning-feature" | File in `.agent/tasks/` |
| 4 | nav-sop | 04-nav-sop.md | "Create SOP for learning-debugging" | File in `.agent/sops/` |
| 5 | nav-compact | 05-nav-compact.md | "Clear context and preserve markers" | `.active` file created |

### Development Skills (Project-Specific)

| Project Type | Skill | Task File |
|--------------|-------|-----------|
| Frontend | frontend-component | 06-frontend-component.md |
| Frontend | frontend-test | 07-frontend-test.md |
| Backend | backend-endpoint | 06-backend-endpoint.md |
| Backend | backend-test | 07-backend-test.md |
| Fullstack | Both frontend + backend skills | Sequential |

## Quick Start Curriculum

Tasks 1-4 only:
1. nav-start (3 min)
2. nav-marker (3 min)
3. nav-task (4 min)
4. One dev skill matching project (5 min)

Total: ~15 minutes

## Full Education Curriculum

### Part 1: Philosophy (5 min)
- Read `.agent/philosophy/CONTEXT-EFFICIENCY.md`
- Understand why Navigator exists
- Key principle: load what you need, when you need it

### Part 2: Session Management (10 min)
- Task 1: nav-start
- Task 2: nav-marker
- Task 5: nav-compact

### Part 3: Documentation (10 min)
- Task 3: nav-task
- Task 4: nav-sop

### Part 4: Development Skills (15-20 min)
- Project-specific skills
- Hands-on practice with real components/endpoints

### Part 5: Summary (5 min)
- Generate MY-WORKFLOW.md
- Review quick reference
- Next steps

Total: ~45 minutes

## Predefined Functions

### project_analyzer.py
Extends `nav-init/functions/project_detector.py` with:
- Project type classification (frontend/backend/fullstack)
- Database detection
- Testing framework detection
- Navigator status check

### skill_recommender.py
Maps project analysis to skill recommendations:
- Essential skills (always included)
- Recommended skills (based on project type)
- Optional skills (advanced features)
- Workflow order (suggested sequence)

### onboarding_paths.py
Resolves the per-person onboarding directory for a repo (`onboarding_dir`,
`repo_id`, `completed_marker`); CLI prints it. Every other function routes through it.

### progress_tracker.py
Manages `PROGRESS.md` in the personal onboarding dir:
- Initialize progress file
- Update task status
- Calculate completion percentage
- Determine next task

### task_validator.py
Validates task completion:
- File existence checks
- Content validation
- User confirmation prompts

### workflow_generator.py
Generates `MY-WORKFLOW.md` in the personal onboarding dir:
- Project-specific workflow
- Daily checklist
- Quick reference table
- Best practices

## Error Handling

### Navigator Not Initialized
```
⚠️  Navigator not initialized in this project.

Run nav-init first, then come back to onboarding.

Would you like to initialize Navigator now? [Y/n]
```

### Task Validation Failed
```
⚠️  Couldn't verify task completion.

Expected: [what should exist]
Found: [what was found]

Options:
1. Retry the task
2. Skip this task
3. Mark as complete anyway

Your choice [1-3]:
```

### User Wants to Skip
```
Skipping [skill_name].

Note: You can always learn this skill later by saying:
"Teach me [skill_name]"

Continuing to next task...
```

## Success Criteria

Onboarding is successful when:
- [ ] User completed at least 3 essential skill tasks
- [ ] `$NAV_ONBOARD_DIR/PROGRESS.md` shows progress
- [ ] `$NAV_ONBOARD_DIR/MY-WORKFLOW.md` generated
- [ ] `$NAV_ONBOARD_DIR/.completed` marker created
- [ ] `git status` shows no onboarding files (state is outside the repo)
- [ ] User knows how to start sessions and save progress

## Notes

- Real files created during onboarding (not sandboxed)
- Files created can be deleted later if unwanted
- Progress persists across sessions, per person: `~/.config/navigator/onboarding/<repo-id>/`
  (`<repo-id>` = dirname + 8-char hash of the checkout path; `NAVIGATOR_ONBOARDING_HOME`
  overrides the base)
- Can re-run onboarding anytime (asks to overwrite)
- Learning tasks designed for 3-5 minutes each
