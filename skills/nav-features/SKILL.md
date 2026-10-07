---
name: nav-features
description: Show and toggle Navigator features. Auto-invoke when user says "show features", "enable/disable feature", "my navigator settings", or "configure navigator".
allowed-tools: Read, Write, Bash
version: 1.0.0
---

# Navigator Features Skill

Display and toggle Navigator features with an interactive table. Helps users understand what's enabled and customize their setup.

## When to Invoke

Invoke this skill when the user:
- Says "show my features", "navigator features", "what features are enabled"
- Says "enable [feature]", "disable [feature]", "turn on/off [feature]"
- Says "configure navigator", "my navigator settings"
- Asks "what can navigator do?", "what features are available?"

**DO NOT invoke** if:
- User is asking about project features (not Navigator)
- User is in middle of implementation
- Just starting session (use nav-start instead)

## Execution Steps

### Step 1: Read Current Configuration

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-features/functions/feature_manager.py" show
```

This displays the feature table (one row per configurable Navigator feature, current version's number in the header):

```
v<version> Features:

┌─────────────────────────┬────────┬───────────────────────────────────────────────┐
│ Feature                 │ Status │ Description                                   │
├─────────────────────────┼────────┼───────────────────────────────────────────────┤
│ task_mode               │ [x]    │ Auto-detects task complexity, defers to sk... │
│ tom_features            │ [x]    │ Verification checkpoints, user profile, di... │
│ loop_mode               │ [ ]    │ Autonomous loop execution (enable when nee... │
│ simplification          │ [x]    │ Post-implementation code cleanup with Opus    │
│ auto_update             │ [x]    │ Update notice on session start                │
│ knowledge_graph         │ [x]    │ Unified project knowledge + experiential m... │
│ compact_hook            │ [x]    │ Injects rich summary into compacted sessions  │
│ workflow_enforcer_hook  │ [x]    │ Enforces WORKFLOW CHECK block before task ... │
│ read_guard_hook         │ [x]    │ Warns on excessive Reads (push to agents)     │
│ workflow_state_hook     │ [x]    │ Tracks current task/phase across the session  │
│ task_graph_sync_hook    │ [x]    │ Auto-syncs task files into the knowledge g... │
│ profile_sync_hook       │ [x]    │ Auto-captures preferences/corrections into... │
│ dispatcher              │ [x]    │ Single hook dispatcher runtime (nav_dispat... │
│ tier1                   │ [ ]    │ Zero-token answers for whitelisted prompts    │
│ stop_completion         │ [ ]    │ Completion gate on Stop (decision:block)      │
│ reject_log              │ [x]    │ One JSONL line per refusal (.agent/.nav-re... │
│ jit_memory              │ [ ]    │ Injects relevant memories after tool use      │
│ subagent_context        │ [ ]    │ Injects project context into subagents (2k)   │
│ failure_diagnosis       │ [ ]    │ Surfaces graph pitfalls on tool failures      │
│ judge                   │ [ ]    │ Jev judgments overlay the prompt scorers      │
│ adhd_mode               │ [ ]    │ Per-person reply shaping (one next action,... │
│ ste_mode                │ [ ]    │ STE sentence rules, personal switch           │
│ config_guard            │ [x]    │ Warns when .nav-config.json edits break JSON  │
│ setup_hook              │ [x]    │ One-line runtime status on the Setup event    │
└─────────────────────────┴────────┴───────────────────────────────────────────────┘

All v<version> features configured.
```

### Step 2: Handle Toggle Request (If Applicable)

If user requested to enable/disable a feature:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
# Enable a feature
python3 "$PLUGIN_DIR/skills/nav-features/functions/feature_manager.py" enable task_mode

# Disable a feature
python3 "$PLUGIN_DIR/skills/nav-features/functions/feature_manager.py" disable loop_mode

# Personal toggle (team repo): write to .agent/.nav-config.local.json, not the shared file
python3 "$PLUGIN_DIR/skills/nav-features/functions/feature_manager.py" disable judge --local
```

**Personal overrides (v7.8.0+)**: `.agent/.nav-config.json` is committed and shared.
`.agent/.nav-config.local.json` is gitignored (nav-init adds it) and merges over the
shared file last — DEFAULTS < shared < local — in both the hook runtime and this
script. Use `--local` when the user says "for me only", "just on my machine", or has
no key for a shared-on feature (typical: `disable judge --local`). `show` marks rows
the local file decides with `L` and prints a legend; toggling the shared value while a
local override exists prints a warning so nobody wonders why nothing changed.

**Supported features**:

Core (config-toggled):
- `task_mode` - Unified workflow orchestration
- `tom_features` - Theory of Mind (verification checkpoints, profile, diagnostics)
- `loop_mode` - Autonomous loop execution
- `simplification` - Code cleanup before commit
- `auto_update` - Update notice on session start; the update is one command
- `knowledge_graph` - Unified project knowledge + memories (v6.0.0)

Hooks (config-toggled, edit with caution):
- `compact_hook` - Pre-compact summary injection
- `workflow_enforcer_hook` - Mandatory WORKFLOW CHECK block (disabling weakens guardrails)
- `read_guard_hook` - Anti upfront-loading guard
- `workflow_state_hook` - Tracks task/phase across the session
- `task_graph_sync_hook` - Auto-syncs tasks into knowledge graph
- `profile_sync_hook` - Auto-captures profile corrections

v7 hooks runtime (config-toggled; new blocking/injecting features ship OFF):
- `dispatcher` - Single hook dispatcher runtime (`nav_dispatch`); ON by default —
  disabling turns off ALL hook ops at once
- `tier1` - Zero-token answers for whitelisted prompts (per-rule flags live under
  `tier1.rules.*` in `.agent/.nav-config.json`; edit those directly)
- `stop_completion` - Completion gate on Stop via decision:block
  (`stop_completion.continue_enabled` stays false; `max_continues` caps at 2)
- `reject_log` - one JSON line per refusal (read-guard deny, prompt-gate block, stop-gate
  block) in `.agent/.nav-rejects.jsonl`, both runtimes, bounded to 500 lines; observes only,
  so it ships on. `/nav` shows it behind `l`.
- `jit_memory` - Just-in-time memory injection after tool use
- `subagent_context` - Project context injection into subagents
  (`subagent_context.budget_chars`, default 2000)
- `failure_diagnosis` - Graph-pitfall injection on PostToolUseFailure (ships OFF)
- `judge` - Typed prompt judge (TypeSafe Jev) behind the loop/complexity/ambiguity
  scorers (ships OFF). Needs a key: `TYPESAFE_API_KEY` or `~/.config/typesafe/api_key`,
  never inside `.nav-config.json`. After `enable judge`, show the key hint the toggle
  prints and point to `.agent/sops/integrations/typesafe-judge-setup.md`
- `adhd_mode` - ADHD-friendly reply shape (one next action first, deadlines bold,
  lists capped, no preamble). The switch is the person's: `enable adhd_mode` writes
  `~/.config/navigator/adhd-mode.json`, not the repo, and the user can also just say
  `adhd mode on` / `adhd mode off` at any prompt (answered by the hook, zero model
  turn). `--local` pins `adhd_mode.on` in `.nav-config.local.json`; a repo pin wins
  over the personal switch. `adhd_mode.enabled` only makes the machinery available
- `ste_mode` - Simplified Technical English sentences (ASD-STE100 Part 1: one idea per
  sentence, 20 words, imperative, active voice, no gerunds). Same personal-switch
  mechanics as `adhd_mode`: `enable ste_mode` writes `~/.config/navigator/ste-mode.json`,
  or say `ste mode on` / `use ste` / `ste mode off` at any prompt. Both modes may be on;
  the ADHD block comes first and the STE block applies inside it
- `config_guard` - systemMessage warning on invalid `.nav-config.json` edits
  (safety surface, ON by default)
- `setup_hook` - One-line runtime status on the Setup event (safety surface,
  ON by default)

**After toggle, show updated table**.

### Step 3: Explain Feature (If Asked)

If user asks about a specific feature, provide details:

**task_mode**:
```
Task Mode (v5.6.0)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Auto-detects task complexity and routes appropriately:
- Simple tasks → Direct execution
- Skill matches → Defers to skill workflow
- Substantial → Task Mode phases (RESEARCH→COMPLETE)

Config: task_mode.enabled, complexity_threshold (0.5)
```

**tom_features**:
```
Theory of Mind (v5.0.0)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Human-AI collaboration improvements:
- Verification checkpoints for high-stakes skills
- User profile (nav-profile) - remembers preferences
- Quality detection (nav-diagnose) - catches drift

Config: tom_features.verification_checkpoints, profile_enabled
```

**loop_mode**:
```
Loop Mode (v5.1.0)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"Run until done" capability:
- Structured completion signals (NAVIGATOR_STATUS)
- Dual-condition exit (heuristics + EXIT_SIGNAL)
- Stagnation detection prevents infinite loops

Trigger: "run until done", "loop mode"
Config: loop_mode.enabled, max_iterations (5)
```

**simplification**:
```
Code Simplification (v5.4.0)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Automatic code clarity improvements:
- Runs post-implementation, before commit
- Clarity over brevity, functionality preserved
- Uses Opus model for best results

Trigger: "simplify this code"
Config: simplification.enabled, trigger, scope
```

**auto_update**:
```
Auto-Update (v5.5.0)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Read-only update notice on session start (v8: Navigator never updates itself from a hook):
- Compares the running version with the latest GitHub release, at most every
  `check_interval_hours`, never under Pilot
- Shows `claude plugin update navigator@navigator-marketplace` when one is newer
- "Start my Navigator session" applies it (nav-start Step 1.5); restart Claude Code after
- Never blocks session start; disabled means no check and no notice
- Under `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` the engine refuses the fetch; opt in with
  `curl_fallback: true` to repeat the same GET through curl (ships off)

Config: auto_update.enabled, check_interval_hours (1), curl_fallback (false)
```

## Predefined Functions

### functions/feature_manager.py

**Purpose**: Display and toggle Navigator features

**Usage**:
```bash
# Show all features
python3 feature_manager.py show

# Show for first session (includes welcome message)
python3 feature_manager.py show --first-session

# Enable a feature
python3 feature_manager.py enable task_mode

# Disable a feature
python3 feature_manager.py disable loop_mode

# Disable only for this contributor (.agent/.nav-config.local.json, gitignored)
python3 feature_manager.py disable judge --local

# Get feature details
python3 feature_manager.py info task_mode
```

**Output**: Formatted feature table or status message

## Error Handling

**Config not found**:
```
❌ .nav-config.json not found

Run "Initialize Navigator in this project" first.
```

**Unknown feature**: lists all available feature names (see Supported features section above). The error message is generated dynamically from the FEATURES dict, so it stays current as features are added.

## Success Criteria

- [ ] Feature table displayed correctly
- [ ] Toggle updates config file
- [ ] Updated table shown after toggle
- [ ] Feature details available on request

## Notes

This skill is triggered on first session (via nav-start) to help users understand available features and optionally disable unused ones to save tokens.
