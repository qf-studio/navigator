# Learning Task 4: Capturing Solutions for Reuse

**Skill**: nav-sop
**Time**: 4-5 minutes
**Difficulty**: Beginner

## Why This Matters

SOPs (Standard Operating Procedures) capture HOW to solve problems. When you debug a tricky issue, the SOP ensures you never waste time solving it again. This is institutional knowledge that compounds over time.

## The Task

### Step 1: Create an SOP

**DO THIS NOW:**
```
Type: "Create SOP for debugging test-failures"
```

**Practice mode**: during onboarding this command runs in the practice sandbox (your personal onboarding dir, outside the repo). The real skill writes to `.agent/sops/<category>/`. Nothing in the repo changes and no GitHub issue is opened. Type the same words later, outside onboarding, and the real skill runs.

### Step 2: Observe What Happens

**WHAT SHOULD HAPPEN:**

1. SOP file created in the practice `.agent/sops/debugging/`
2. Template includes problem, solution, prevention
3. Categories: debugging, integrations, development, deployment

You should see:
```
✅ SOP created!

SOP: debugging-test-failures
File: <practice>/.agent/sops/debugging/test-failures.md
Category: debugging

Template includes:
- Problem Description
- Root Cause
- Solution Steps
- Prevention Checklist
```

### Step 3: Review the Template

**DO THIS:**
```
Ask: "Show me the SOP that was created"
```

The SOP template has:
- **Problem**: What went wrong
- **Symptoms**: How it manifests
- **Root Cause**: Why it happened
- **Solution**: Step-by-step fix
- **Prevention**: How to avoid recurrence

### Step 4: Understand SOP Categories

SOPs are organized by type:
- `debugging/` - Bug fixes and troubleshooting
- `integrations/` - Third-party service setup
- `development/` - Coding workflows and patterns
- `deployment/` - Release and infrastructure

## Validation

This task is complete when:
- [ ] SOP created with "Create SOP for debugging test-failures"
- [ ] File exists in the practice `.agent/sops/debugging/`
- [ ] Template structure visible

**Automatic check**: `task_validator.py nav-sop --practice` finds a file in
`sops/*/` in the sandbox.

## Pro Tip

The best time to create an SOP is RIGHT AFTER solving a problem:
- Context is fresh
- Solution is validated
- Details are accurate

Future you (or teammates) will thank you when:
- Same error appears 6 months later
- New team member hits the same issue
- You forgot the obscure fix

**SOP vs Task Doc:**
- Task: What we built (the feature)
- SOP: How we solved problems (the knowledge)

## What You Learned

1. SOPs capture problem-solving knowledge
2. Create them immediately after solving issues
3. Categories help organize by type (debugging, integrations, etc.)

---

**When done, say "done" to continue to the next task.**
