# Navigator Quick Start Guide

Get Navigator running in your project in 5 minutes.

---

## What You'll Get

✅ Context-efficient documentation (92% token reduction)
✅ Navigator-first loading pattern
✅ Living docs that update as code evolves
✅ 86%+ context available for actual work

---

## Installation

### Step 1: Install Plugin

```bash
# Via Claude Code marketplace
/plugin marketplace add qf-studio/navigator
/plugin install navigator
```

### Step 2: Initialize in Your Project

```bash
# Navigate to your project
cd /path/to/your/project

# Initialize Navigator
/nav:init
```

This creates:
```
your-project/
├── CLAUDE.md                  # Project configuration & workflow
└── .agent/
    ├── DEVELOPMENT-README.md  # Navigator (start here)
    ├── tasks/                 # Feature plans
    ├── system/                # Architecture
    │   ├── project-architecture.md
    │   └── tech-stack-patterns.md
    └── sops/                  # Procedures
        ├── integrations/
        ├── debugging/
        ├── development/
        └── deployment/
```

### Step 3: Customize Configuration

Edit `CLAUDE.md` (project root):

```markdown
# [Your Project Name] - Claude Code Configuration

## Context
[Your project description]

**Tech Stack**: [Your stack]
**Core Principle**: [Key architectural principle]

## Navigator Workflow (CRITICAL)
...
```

Edit `.agent/DEVELOPMENT-README.md` (navigator):

```markdown
# [Your Project Name] - Development Documentation Navigator

**Project**: [Your project description]
**Tech Stack**: [Your stack]
**Updated**: 2025-10-09

...
```

Replace placeholders with your project details.

---

## Basic Usage

### Every Session Starts With

```
Read .agent/DEVELOPMENT-README.md
```

This loads your documentation navigator (~2k tokens) instead of all docs (~150k tokens).

### Working on a Feature

```bash
# After completing feature
/nav:update-doc feature TASK-123
```

This:
1. Creates implementation plan in `.agent/tasks/`
2. Updates system docs based on what you built
3. Prompts for SOP creation if new patterns emerged

### Solving an Issue

```bash
# After solving novel issue
/nav:update-doc sop debugging auth-errors
```

This creates a Standard Operating Procedure so you never solve the same issue twice.

### Changing Architecture

```bash
# After major code changes
/nav:update-doc system architecture
```

This updates system docs to reflect current codebase state.

### Clearing Context

```bash
# When switching tasks or running low on tokens
/nav:compact
```

This clears conversation history while preserving essential context.

---

## Token Savings Example

### Before Navigator
```
Session start:
- Load all docs: 150,000 tokens
- Available for work: 50,000 tokens (25%)
- Session restarts: 3-4 per feature

Result: Constant context overflow
```

### With Navigator
```
Session start:
- Load navigator: 2,000 tokens
- Load current task: 3,000 tokens
- Load relevant system doc: 5,000 tokens
Total: 10,000 tokens

- Available for work: 190,000 tokens (95%)
- Session restarts: 0

Result: Work all day without restart
```

**Savings**: 140k tokens (70% of budget) available for actual work

---

## Real-World Workflow

### Morning: Start New Feature

```bash
# 1. Start Claude Code session

# 2. Load navigator (Navigator does this automatically if configured)
Read .agent/DEVELOPMENT-README.md

# 3. Check what you're working on
Check task management tool (Linear/Jira/etc)

# 4. Load only relevant docs
Read .agent/tasks/TASK-123-feature.md  # If continuing
Read .agent/system/project-architecture.md  # If needed

# Token usage: ~10k (5%)
# Context available: 95%
```

### Afternoon: Complete Feature

```bash
# Feature implemented, tests passing, ready to document

# 1. Archive implementation
/nav:update-doc feature TASK-123

# This creates:
# - .agent/tasks/TASK-123-feature.md (implementation plan)
# - Updates .agent/system/ docs if architecture changed
# - Prompts for SOP if new pattern emerged

# 2. Clear context for next task
/nav:compact

# Token usage back to: ~5k (2.5%)
# Ready for next feature
```

### Evening: Quick Bug Fix

```bash
# 1. Load navigator
Read .agent/DEVELOPMENT-README.md

# 2. Check for known issue
Check .agent/sops/debugging/

# 3. Fix bug

# 4. Document solution
/nav:update-doc sop debugging cache-invalidation

# This creates:
# - .agent/sops/debugging/cache-invalidation.md
# - Prevents repeat issue

# 5. Compact
/nav:compact
```

**Total work**: 3 separate tasks
**Peak token usage**: 15% (vs 70%+ without Navigator)
**Session restarts**: 0 (vs 2-3 without Navigator)

---

## Configuration (Optional)

### Project Management Integration

```bash
# During /nav:init, configure:

Project Management Tool:
  1. Linear (MCP integration)
  2. GitHub Issues
  3. Jira
  4. None (manual docs)

Choice: 1

Task Prefix: TASK
```

Benefits:
- Auto-link docs to tickets
- Pull ticket details automatically
- Update ticket status from docs

### Team Chat Integration

```bash
Team Chat (optional):
  1. Slack
  2. Discord
  3. Teams
  4. None

Choice: 4  # None is fine for solo/small teams
```

Benefits:
- Notify team of doc updates
- Share SOPs automatically
- Announce feature completions

---

## Common Workflows

### Scenario 1: Solo Developer

**Setup**: No PM tool, no team chat

**Workflow**:
1. Start session → Load navigator
2. Work on feature → Load task doc + system docs
3. Complete → `/nav:update-doc feature TASK-XX`
4. Compact → `/nav:compact`

**Benefit**: Personal knowledge base grows, zero session restarts

### Scenario 2: Small Team (2-5)

**Setup**: GitHub Issues, optional Discord

**Workflow**:
1. Check GitHub Issues for assignment
2. Load navigator + relevant docs (10k tokens)
3. Implement feature
4. Document → `/nav:update-doc feature GH-123`
5. Notify team → Discord post (if configured)
6. Compact → `/nav:compact`

**Benefit**: Shared team knowledge, consistent patterns

### Scenario 3: Enterprise Team

**Setup**: Linear, Slack

**Workflow**:
1. Linear MCP → `list_issues({ assignee: "me" })`
2. Load navigator + task doc (12k tokens)
3. Implement feature
4. Document → `/nav:update-doc feature LIN-456`
5. Linear MCP → Update ticket status
6. Slack notification → Team knows it's done
7. Compact → `/nav:compact`

**Benefit**: Full integration, team stays synced, docs always current

---

## Troubleshooting

### Issue: "Can't find .agent/ folder"

**Solution**: Run `/nav:init` first to set up structure

### Issue: "Loading too many tokens"

**Solution**: Check you're loading navigator first, not all docs
- ✅ Read .agent/DEVELOPMENT-README.md (2k)
- ❌ Read .agent/**/*.md (150k)

### Issue: "Documentation out of date"

**Solution**: Run `/nav:update-doc system architecture` to refresh from codebase

### Issue: "Don't know what to document"

**Solution**: Navigator has "When to Read What" guide
- Implementing feature? Create task doc
- Solved issue? Create SOP
- Changed architecture? Update system doc

---

## Next Steps

### Week 1: Build the Habit

- [ ] Start every session with navigator
- [ ] Complete 1 feature → `/nav:update-doc feature`
- [ ] Solve 1 issue → `/nav:update-doc sop`
- [ ] Run `/nav:compact` after each task

### Week 2: See the Benefits

- [ ] Check token usage (should be <20% average)
- [ ] Count session restarts (should be 0)
- [ ] Review your `.agent/` knowledge base
- [ ] Notice how much context you retain

### Week 3: Optimize

- [ ] Customize templates for your project
- [ ] Add custom system docs if needed
- [ ] Fine-tune compact strategy
- [ ] Share with team (if applicable)

### Month 1: Measure Impact

Metrics to track:
- Token usage per session
- Session restarts (should be 0)
- Documentation coverage (% features documented)
- Time to find info (should be <30 seconds)

---

## Support

- **Documentation**: [Full Docs](./README.md)
- **Configuration**: [Configuration Guide](./CONFIGURATION.md)
- **Issues**: [GitHub Issues](https://github.com/qf-studio/navigator/issues)
- **Community**: [GitHub Discussions](https://github.com/qf-studio/navigator/discussions)

---

## Summary

**5-Minute Setup**:
1. `/plugin install navigator`
2. `/nav:init`
3. Customize navigator

**Daily Usage**:
1. Load navigator first (2k tokens)
2. Load only what's needed (10k total)
3. Document as you go (`/nav:update-doc`)
4. Compact between tasks (`/nav:compact`)

**Result**: 92% token reduction, zero session restarts, 10x productivity

**Start now**: `/nav:init` 🚀
