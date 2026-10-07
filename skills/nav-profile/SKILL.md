---
name: nav-profile
description: Manage user preferences and corrections for bilateral modeling. Auto-learns from session corrections. Use when user says "save my preferences", "remember I like...", or auto-triggers after corrections.
allowed-tools: Read, Write, Edit, Bash
version: 1.0.0
---

# Navigator Profile Skill

Manage user preferences for bilateral modeling - enabling Claude to understand and adapt to your working style, technical preferences, and past corrections.

## Why This Exists (Theory of Mind)

Based on Riedl & Weidmann 2025 research on Human-AI Synergy:
- Theory of Mind (ToM) is the key differentiator in human-AI collaboration success
- Users with higher ToM achieve 23-29% performance boost
- **Bilateral modeling** completes the ToM loop: Claude models you, you model Claude

This skill enables Claude to:
- Remember your preferences across sessions
- Learn from corrections without you repeating them
- Adapt communication style to your level
- Build a persistent mental model of YOU

## When to Invoke

**Auto-invoke when**:
- User says "save my preferences", "remember I like..."
- User says "update my profile", "change my preference for..."
- After detecting a correction pattern (auto-learn mode)
- User says "show my profile", "what do you know about me?"

**DO NOT invoke if**:
- User is creating a context marker (use nav-marker)
- User wants session-specific preferences only
- User explicitly says "just for this session"

## Profile Location

`.agent/.user-profile.json` (git-ignored, session-persistent)

## Execution Steps

### Step 1: Determine Action

**SHOW** (viewing profile):
```
User: "Show my profile", "What do you remember about me?"
→ Display current profile
```

**UPDATE** (explicit preference):
```
User: "Remember I prefer functional style", "Save that I like concise explanations"
→ Update specific preference
```

**LEARN** (auto-detect correction):
```
[Internal trigger after correction detected]
→ Extract and save correction pattern
```

**RESET** (clear profile):
```
User: "Reset my profile", "Clear my preferences"
→ Confirm and delete profile
```

### Step 2: Load or Initialize Profile

**Check if profile exists**:
```bash
if [ -f ".agent/.user-profile.json" ]; then
  echo "Profile exists"
else
  echo "No profile found, will create new"
fi
```

**Initialize new profile** (if not exists):
```json
{
  "version": "1.0",
  "created": "{YYYY-MM-DD}",
  "last_updated": "{YYYY-MM-DD}",
  "preferences": {
    "communication": {
      "verbosity": "balanced",
      "confirmation_threshold": "high-stakes",
      "explanation_style": "examples"
    },
    "technical": {
      "preferred_frameworks": [],
      "code_style": "mixed",
      "testing_preference": "tdd"
    },
    "workflow": {
      "autonomous_commits": true,
      "auto_compact_threshold": 80,
      "marker_before_risky": true
    }
  },
  "corrections": [],
  "goals": []
}
```

### Step 3A: Show Profile (If SHOW Action)

**Display current profile**:
```
Your Navigator Profile
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Communication Preferences:
- Verbosity: {verbosity}
- Confirmation: {confirmation_threshold} (when to verify understanding)
- Explanations: {explanation_style}

Technical Preferences:
- Preferred frameworks: {frameworks or "none set"}
- Code style: {code_style}
- Testing: {testing_preference}

Workflow Preferences:
- Autonomous commits: {autonomous_commits}
- Auto-compact at: {auto_compact_threshold}% context
- Markers before risky changes: {marker_before_risky}

Learned Corrections ({count}):
{recent_corrections_list}

Active Goals ({count}):
{active_goals_list}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Last updated: {last_updated}
```

### Step 3B: Update Profile (If UPDATE Action)

**Parse preference from user input**:
```
User: "Remember I prefer functional style"
→ Category: technical
→ Field: code_style
→ Value: functional

User: "I like concise explanations"
→ Category: communication
→ Field: verbosity
→ Value: concise
```

**Map common expressions to profile fields**:

| User Says | Category | Field | Value |
|-----------|----------|-------|-------|
| "concise", "brief", "short" | communication | verbosity | concise |
| "detailed", "thorough" | communication | verbosity | detailed |
| "always confirm" | communication | confirmation_threshold | always |
| "skip confirmations" | communication | confirmation_threshold | never |
| "functional style" | technical | code_style | functional |
| "OOP style" | technical | code_style | oop |
| "prefer React" | technical | preferred_frameworks | [append "react"] |
| "prefer Express" | technical | preferred_frameworks | [append "express"] |

**Update and save**:
```json
// Update specific field
profile.preferences[category][field] = value;
profile.last_updated = "{YYYY-MM-DD}";

// Write to file
Write(".agent/.user-profile.json", JSON.stringify(profile, null, 2));
```

**Confirm update**:
```
✅ Profile updated!

Changed: {category}.{field}
From: {old_value}
To: {new_value}

This will affect future sessions.
```

### Step 3C: Auto-Learn Correction (If LEARN Action) [AUTO-TRIGGER]

**IMPORTANT**: This action triggers automatically - no explicit skill invocation needed.

**When to detect corrections** (monitor ALL conversations):
- User says "No, I meant...", "Actually...", "Not X, use Y"
- User repeats a correction they gave before
- User shows frustration at repeated mistake

**Trigger patterns to watch for**:
```
"No, ..." → Direct correction
"I said ..." → Repeated instruction
"Actually, ..." → Clarification
"Not X, Y" → Substitution
"Always use ..." → Rule establishment
"Never do ..." → Anti-pattern
"I prefer ..." → Preference
```

**When detected**:
```
User: "No, I meant plural /users not /user"
→ Correction detected: REST naming convention preference
→ Auto-save to profile (silent)
```

**Extract correction pattern**:
```python
correction = {
  "date": "{YYYY-MM-DD}",
  "context": "{what we were doing}",
  "original": "{what I said/generated}",
  "corrected_to": "{what user wanted}",
  "pattern": "{generalized rule}",
  "confidence": "high|medium|low"
}
```

**Add to corrections list**:
```json
profile.corrections.push(correction);

// Keep last 20 corrections (rolling window)
if (profile.corrections.length > 20) {
  profile.corrections.shift();
}
```

**Silently acknowledge** (don't interrupt flow):
```
[Internal log: Correction saved to profile]
```

**Sync to Knowledge Graph** (if enabled in config):
```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
# Check if knowledge graph integration is enabled
if [ -f ".agent/knowledge/graph.json" ]; then
  # Convert correction to memory
  python3 "$PLUGIN_DIR/skills/nav-graph/functions/correction_to_memory.py" \
    --action convert-one \
    --correction-json '{"pattern": "{pattern}", "context": "{context}", "confidence": "{confidence}"}' \
    --graph-path .agent/knowledge/graph.json

  # [Internal log: Correction synced to knowledge graph as memory]
fi
```

This creates a pitfall/pattern/learning memory in the knowledge graph, making the correction available via "What do we know about X?" queries.

**Periodically surface learnings** (every 5 corrections):
```
📚 I've learned from your corrections:
- REST endpoints should use plural nouns
- You prefer functional components over class components
- TypeScript strict mode is required

These will be applied in future sessions.
```

### Step 3D: Reset Profile (If RESET Action)

**Confirm before delete**:
```
⚠️  This will delete your Navigator profile:
- {X} saved preferences
- {Y} learned corrections
- {Z} active goals

This cannot be undone.

Delete profile? [y/N]
```

**If confirmed**:
```bash
rm .agent/.user-profile.json
```

**Confirm deletion**:
```
✅ Profile deleted

Future sessions will start fresh.
To rebuild, use "Save my preferences" as you work.
```

### Step 4: Update Goals (Optional)

**If user mentions a goal**:
```
User: "I'm working on the OAuth feature"
→ Add/update goal in profile
```

**Goal structure**:
```json
{
  "name": "oauth-feature",
  "started": "{YYYY-MM-DD}",
  "context": "OAuth implementation for user login",
  "status": "in-progress",
  "last_mentioned": "{YYYY-MM-DD}"
}
```

**Goal cleanup** (auto-archive goals not mentioned in 7 days):
```json
// Move to completed if not mentioned recently
goals.forEach(goal => {
  if (daysSince(goal.last_mentioned) > 7) {
    goal.status = "completed-or-abandoned";
  }
});
```

### Step 5: Confirm Action

**For explicit actions (SHOW, UPDATE, RESET)**:
Show confirmation message.

**For auto-learn (LEARN)**:
Silent acknowledgment, periodic summaries.

---

## Profile Schema Reference

```json
{
  "version": "1.0",
  "created": "2025-12-09",
  "last_updated": "2025-12-09",

  "preferences": {
    "communication": {
      "verbosity": "concise|balanced|detailed",
      "confirmation_threshold": "always|high-stakes|never",
      "explanation_style": "examples|theory|both"
    },
    "technical": {
      "preferred_frameworks": ["react", "express", "etc"],
      "code_style": "functional|oop|mixed",
      "testing_preference": "tdd|bdd|manual"
    },
    "workflow": {
      "autonomous_commits": true|false,
      "auto_compact_threshold": 70-90,
      "marker_before_risky": true|false
    }
  },

  "corrections": [
    {
      "date": "2025-12-09",
      "context": "creating API endpoint",
      "original": "Created /user endpoint",
      "corrected_to": "Should be /users (plural)",
      "pattern": "REST endpoints use plural nouns",
      "confidence": "high"
    }
  ],

  "goals": [
    {
      "name": "oauth-feature",
      "started": "2025-12-07",
      "context": "OAuth implementation for user login",
      "status": "in-progress",
      "last_mentioned": "2025-12-09"
    }
  ]
}
```

---

## Integration with Other Skills

### nav-start (Session Start)
Loads profile automatically:
```markdown
### Step 3.5: Load User Profile

If `.agent/.user-profile.json` exists:
- Load preferences into context
- Apply confirmation threshold
- Note active goals
- Show: "Loaded preferences from profile"
```

### nav-marker (Context Markers)
Preserves profile reference:
```markdown
## Profile State
- Preferences loaded: ✅
- Corrections this session: {count}
- Goals active: {goal_names}
```

### All ToM Checkpoints
Respect profile settings:
```markdown
// Before showing verification checkpoint
if (profile.preferences.communication.confirmation_threshold === "never") {
  // Skip verification
} else if (profile.preferences.communication.confirmation_threshold === "high-stakes") {
  // Only verify for complex operations
}
```

---

## Auto-Learn Triggers

**Correction patterns to detect**:

| User Pattern | Extracted Learning |
|--------------|-------------------|
| "No, I meant..." | Direct correction |
| "Actually, prefer..." | Preference correction |
| "Not X, use Y" | Substitution correction |
| "Always do X" | Rule establishment |
| "Never do Y" | Anti-pattern |
| "I like when you..." | Positive preference |
| "Stop doing X" | Negative preference |

**Confidence scoring**:
- **High**: Explicit correction with reasoning
- **Medium**: Correction without explanation
- **Low**: Implicit preference from behavior

---

## Privacy & Data

**Profile is**:
- Git-ignored (`.agent/.user-profile.json`)
- Local only (not synced)
- User-controlled (can delete anytime)
- Session-persistent (survives context clears)

**Profile does NOT store**:
- Code snippets
- File contents
- Conversation history
- Sensitive data

---

## Success Criteria

Profile management succeeds when:
- [ ] Profile loads at session start
- [ ] Preferences affect behavior (verbosity, confirmations)
- [ ] Corrections persist across sessions
- [ ] Auto-learn captures patterns silently
- [ ] Goals track user's current focus
- [ ] Reset cleanly removes all data

---

## Best Practices

**Good profile usage**:
- "Remember I prefer concise explanations" (clear preference)
- "Save that I use functional components" (specific)
- "Show my profile" (verify what's stored)

**Avoid**:
- Storing sensitive information
- Over-correcting (let auto-learn work)
- Resetting frequently (defeats purpose)

---

**This skill enables bilateral Theory of Mind - Claude understanding you as well as you understanding Claude** 🧠
