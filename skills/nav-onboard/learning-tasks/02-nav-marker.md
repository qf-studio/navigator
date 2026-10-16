# Learning Task 2: Creating Context Markers

**Skill**: nav-marker
**Time**: 3-5 minutes
**Difficulty**: Beginner

## Why This Matters

Context markers are "save points" for your AI sessions. When you take a break or clear context, the marker preserves what you were working on. A 130k token conversation compresses to ~3k tokens - 97% reduction.

## The Task

### Step 1: Create a Marker

**DO THIS NOW:**
```
Type: "Create checkpoint learning-test"
```

**Practice mode**: during onboarding this command runs in the practice sandbox (your personal onboarding dir, outside the repo). The real skill writes to `.agent/.context-markers/`. Nothing in the repo changes and no GitHub issue is opened. Type the same words later, outside onboarding, and the real skill runs.

### Step 2: Observe What Happens

**WHAT SHOULD HAPPEN:**

1. System creates the marker file (practice: `<practice>/.agent/.context-markers/`)
2. Marker captures:
   - What you were working on
   - Files you modified (if any)
   - Technical decisions made
   - Next steps

You should see:
```
✅ Context marker created!

Marker: learning-test
File: <practice>/.agent/.context-markers/[timestamp]_learning-test.md
Size: ~2-3 KB

This marker captures:
- Session summary
- Current focus
- Next steps

To restore later: "Load marker learning-test"
```

### Step 3: Verify the Marker

**DO THIS:**
```
Ask: "Show me the marker file that was just created"
```

You should see structured content:
- Conversation Summary
- Files Modified
- Current Focus
- Technical Decisions
- Next Steps

## Validation

This task is complete when:
- [ ] Marker created with "Create checkpoint learning-test"
- [ ] File exists in the practice `.agent/.context-markers/`
- [ ] Marker contains session summary

**Automatic check**: `task_validator.py nav-marker --practice` finds
`.context-markers/*learning-test*.md` in the sandbox.

## Pro Tip

Create markers:
- Before breaks (lunch, EOD)
- Before risky refactors
- At milestones (feature complete)
- Before clearing context

Good names: `before-refactor`, `auth-complete`, `eod-friday`
Bad names: `temp`, `test1`, `asdf`

## What You Learned

1. Markers compress 130k → 3k tokens (97% reduction)
2. They preserve context across sessions
3. Create them before breaks and risky changes

---

**When done, say "done" to continue to the next task.**
