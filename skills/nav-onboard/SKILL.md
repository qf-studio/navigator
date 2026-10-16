---
name: nav-onboard
description: Interactive onboarding for Navigator - learn by doing. Auto-invoke when user says "onboard me", "teach me Navigator", "how do I use Navigator", "Navigator tutorial", "learn Navigator", "new to Navigator", or "what skills should I use".
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion
version: 1.1.0
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
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
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

**If the project ships its own tutorial text** (`.agent/ONBOARDING.md`, reported by the
recommender as `project_tutorial`), present it after the Navigator curriculum (Step 6.6).
That is how a team repo extends the tutorial instead of replacing it.

### Practice Mode (GH-35)

Every exercise in Steps 6.1–6.4 is a rehearsal. When the user types an exercise command
("Create checkpoint learning-test", "Create task doc for learning-feature", "Create SOP for
debugging test-failures", "Clear context and preserve markers"), do **not** invoke the real
skill. Run the practice sandbox instead:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-onboard/functions/practice.py" run [skill_name]
```

It renders the artifact the real skill would create under
`$NAV_ONBOARD_DIR/practice/.agent/` (mirrors the repo's `.agent/`, outside the repo),
prints a `preview` and the `real_command`, and never runs `gh`. With
`task_id_source: github` the nav-task result carries `would_create_issue` (title, labels,
body): show it, say that practice does not create it. `git status` in the repo stays
unchanged throughout onboarding; `practice.py clean` removes the sandbox at the end
(Step 8). The real skills run as usual once onboarding is over.

### Step 2: Analyze Project

Run project analyzer to detect tech stack:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
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

Run the skill recommender. With no arguments it analyzes the current directory itself
(no stdin needed); `--analysis FILE` or `project_analyzer.py | skill_recommender.py --analysis -`
reuses the Step 2 output:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-onboard/functions/skill_recommender.py"
```

**Output structure**:
```json
{
  "essential_skills": ["nav-start", "nav-marker", "nav-task", "nav-sop", "nav-compact"],
  "recommended_skills": ["frontend-component", "backend-endpoint"],
  "optional_skills": ["visual-regression", "product-design"],
  "workflow_order": ["nav-start", "nav-task", "frontend-component", "nav-sop", "nav-marker", "nav-compact"],
  "curriculum": {"quick_start": [{"skill": "nav-start", "task_file": "01-nav-start.md"}, "..."],
                 "full_education": ["..."]},
  "project_tutorial": null
}
```

Each curriculum entry's `task_file` is a file that exists in `learning-tasks/` (essential
skills: `01-nav-start.md` … `05-nav-compact.md`; every development skill:
`06-dev-skill.md`). The Full Education philosophy entry's `file` is the plugin's absolute
`.agent/philosophy/CONTEXT-EFFICIENCY.md`; projects do not carry that file.

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
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-onboard/functions/progress_tracker.py" init [quick_start|full_education]
```

`init` detects project type and name and computes the skill list itself. Override with
`[project_type]`, `--project-name`, or `--skills FILE|-` (the Step 3 JSON; a bare list of
skill ids is accepted as the essential list). `--project-dir` names the repo when the
command does not run from its root; every subcommand accepts it.

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

Read the learning task file named by the curriculum entry's `task_file` and present it:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
cat "$PLUGIN_DIR/skills/nav-onboard/learning-tasks/[task_file]"
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

- `nav-start` and the development skills run for real (nav-start reads only; a
  development skill scaffolds code the user asked for, in their working tree).
- `nav-marker`, `nav-task`, `nav-sop`, `nav-compact`: run the practice sandbox
  (see "Practice Mode" above), show its `preview`, `headline` and, when present,
  `would_create_issue`.

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-onboard/functions/practice.py" run [skill_name]
```

User says "done" or similar when ready to continue.

#### 6.3: Validate Completion

Run task validator:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-onboard/functions/task_validator.py" [skill_name] --practice
```

`--practice` checks the sandbox; without it the same checks run against the repo (for the
development skills, which build in the working tree, omit the flag). Exit code 0 = valid.

**Validation checks per skill** (sandbox paths under `$NAV_ONBOARD_DIR/practice/`):
- `nav-start`: User confirmation (session displayed)
- `nav-marker`: File exists in `.agent/.context-markers/`
- `nav-task`: File exists in `.agent/tasks/`
- `nav-sop`: File exists in `.agent/sops/`
- `nav-compact`: `.active` file exists in `.context-markers/`

#### 6.4: Update Progress

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-onboard/functions/progress_tracker.py" update [skill_name] completed "[notes]"
```

`progress_tracker.py next` prints the next skill (or `complete`).

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

#### 6.6: Project Tutorial (when the repo ships one)

If Step 3 reported a `project_tutorial` path, read it and present it after the last
Navigator task, under its own heading. It is the project's text; do not rewrite it.

### Step 7: Generate Personalized Workflow

After all tasks complete, generate workflow guide:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-onboard/functions/project_analyzer.py" > "$NAV_ONBOARD_DIR/.analysis.json"
python3 "$PLUGIN_DIR/skills/nav-onboard/functions/skill_recommender.py" --analysis "$NAV_ONBOARD_DIR/.analysis.json" > "$NAV_ONBOARD_DIR/.skills.json"
python3 "$PLUGIN_DIR/skills/nav-onboard/functions/workflow_generator.py" . "$NAV_ONBOARD_DIR/.analysis.json" "$NAV_ONBOARD_DIR/.skills.json"
```

Creates `$NAV_ONBOARD_DIR/MY-WORKFLOW.md` with:
- Project-specific workflow diagram
- Daily workflow checklist
- Quick reference table with all skill triggers
- Best practices for user's stack

### Step 8: Completion Summary

Mark onboarding complete and show summary:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-onboard/functions/practice.py" clean
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
| 2 | nav-marker | 02-nav-marker.md | "Create checkpoint learning-test" | Sandbox file in `.context-markers/` |
| 3 | nav-task | 03-nav-task.md | "Create task doc for learning-feature" | Sandbox file in `.agent/tasks/` |
| 4 | nav-sop | 04-nav-sop.md | "Create SOP for debugging test-failures" | Sandbox file in `.agent/sops/` |
| 5 | nav-compact | 05-nav-compact.md | "Clear context and preserve markers" | Sandbox `.active` file |

Tasks 2–5 run in the practice sandbox (see "Practice Mode").

### Development Skills (Project-Specific)

| Project Type | Skill | Task File |
|--------------|-------|-----------|
| Frontend | frontend-component, frontend-test | 06-dev-skill.md (Option A) |
| Backend | backend-endpoint, backend-test | 06-dev-skill.md (Option B) |
| Fullstack | Both frontend + backend skills | 06-dev-skill.md, sequential |

## Quick Start Curriculum

Tasks 1-4 only:
1. nav-start (3 min)
2. nav-marker (3 min)
3. nav-task (4 min)
4. One dev skill matching project (5 min)

Total: ~15 minutes

## Full Education Curriculum

### Part 1: Philosophy (5 min)
- Read the plugin's `.agent/philosophy/CONTEXT-EFFICIENCY.md` (the curriculum entry's
  `file` is the absolute path; nav-init does not copy it into projects)
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
Maps project analysis to skill recommendations (`[project_dir]`, `--analysis FILE|-`;
analyzes the project itself when no analysis is given):
- Essential skills (always included)
- Recommended skills (based on project type)
- Optional skills (advanced features)
- Workflow order (suggested sequence)
- Curriculum with `task_file` names resolved against `learning-tasks/` on disk
- `project_tutorial`: `.agent/ONBOARDING.md` when the repo ships one

### practice.py
The practice sandbox (`run <skill>`, `list`, `clean`, `dir`): renders what nav-marker,
nav-task, nav-sop and nav-compact would create under `$NAV_ONBOARD_DIR/practice/.agent/`.
Reads `task_id_source` and shows `would_create_issue` instead of running `gh`.

### onboarding_paths.py
Resolves the per-person onboarding directory for a repo (`onboarding_dir`,
`repo_id`, `completed_marker`); CLI prints it. Every other function routes through it.

### progress_tracker.py
Manages `PROGRESS.md` in the personal onboarding dir (`init <flow>`, `update`, `get`,
`next`; `--project-dir` names the repo, default `.`):
- Initialize progress file (detects project type, name and skills by default)
- Update task status
- Calculate completion percentage
- Determine next task

### task_validator.py
Validates task completion (`<skill> [--project-dir .] [--practice]`):
- File existence checks (in the sandbox with `--practice`)
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
- [ ] `git status` is unchanged by the practice tasks and no GitHub issue was opened
- [ ] User knows how to start sessions and save progress

## Notes

- Tasks 2–5 write only to the practice sandbox; `practice.py clean` removes it at the end
- Development-skill tasks scaffold real code in the working tree (the user asked for it)
- Progress persists across sessions, per person: `~/.config/navigator/onboarding/<repo-id>/`
  (`<repo-id>` = dirname + 8-char hash of the checkout path; `NAVIGATOR_ONBOARDING_HOME`
  overrides the base)
- Can re-run onboarding anytime (asks to overwrite)
- Learning tasks designed for 3-5 minutes each
