---
name: nav-stats
description: Display session efficiency report showing token savings, cache performance, and optimization recommendations. Use when user asks "show my stats", "how efficient am I?", "show session metrics", or wants to see Navigator's impact.
allowed-tools: Bash, Read
version: 1.0.0
---

# Navigator Session Statistics Skill

Show real-time efficiency reporting with baseline comparisons, making Navigator's value quantifiable and shareable.

## When to Invoke

Invoke this skill when the user:
- Says "show my stats", "show session stats", "show metrics"
- Asks "how efficient am I?", "how much did I save?"
- Says "show my Navigator report", "efficiency report"
- Wants to see token savings or session performance
- Says "show impact", "prove Navigator works"

**DO NOT invoke** if:
- User just started session (< 5 messages)
- Navigator not initialized in project
- User asking about specific metrics only (answer directly)

## Execution Steps

### Step 1: Check Navigator Initialized

Verify Navigator is set up:

```bash
if [ ! -f ".agent/DEVELOPMENT-README.md" ]; then
  echo "❌ Navigator not initialized in this project"
  echo "Run 'Initialize Navigator' first"
  exit 1
fi
```

### Step 2: Run Enhanced Session Stats

Execute the enhanced session statistics script:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/navigator-marketplace/navigator}"
[ -d "$PLUGIN_DIR" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"

# Check if enhanced script exists
if [ ! -f "$PLUGIN_DIR/scripts/session-stats.sh" ]; then
  echo "❌ Session stats script not found"
  echo "Reinstall or update Navigator to restore scripts/session-stats.sh"
  exit 1
fi

# Run stats script
bash "$PLUGIN_DIR/scripts/session-stats.sh"
```

This script outputs shell-parseable variables:
- `BASELINE_TOKENS` - Total size of all .agent/ docs
- `LOADED_TOKENS` - Actually loaded in session (estimated)
- `TOKENS_SAVED` - Difference
- `SAVINGS_PERCENT` - Percentage saved
- `EFFICIENCY_SCORE` - 0-100 score
- `CACHE_EFFICIENCY` - From OpenTelemetry
- `CONTEXT_USAGE_PERCENT` - Estimated context fill
- `TIME_SAVED_MINUTES` - Estimated time saved

### Step 3: Calculate Efficiency Score

Use predefined function to calculate score:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/navigator-marketplace/navigator}"
[ -d "$PLUGIN_DIR" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"

# Extract metrics from session-stats.sh
source <(bash "$PLUGIN_DIR/scripts/session-stats.sh")

# Calculate efficiency score using predefined function
EFFICIENCY_SCORE=$(python3 "$PLUGIN_DIR/skills/nav-stats/functions/efficiency_scorer.py" \
  --tokens-saved-percent ${SAVINGS_PERCENT} \
  --cache-efficiency ${CACHE_EFFICIENCY} \
  --context-usage ${CONTEXT_USAGE_PERCENT})
```

### Step 4: Format and Display Report

Use predefined function to format visual report:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/navigator-marketplace/navigator}"
[ -d "$PLUGIN_DIR" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"

# Generate formatted report
python3 "$PLUGIN_DIR/skills/nav-stats/functions/report_formatter.py" \
  --baseline ${BASELINE_TOKENS} \
  --loaded ${LOADED_TOKENS} \
  --saved ${TOKENS_SAVED} \
  --savings-percent ${SAVINGS_PERCENT} \
  --cache-efficiency ${CACHE_EFFICIENCY} \
  --context-usage ${CONTEXT_USAGE_PERCENT} \
  --efficiency-score ${EFFICIENCY_SCORE} \
  --time-saved ${TIME_SAVED_MINUTES}
```

**Output Format**:
```
╔══════════════════════════════════════════════════════╗
║          NAVIGATOR EFFICIENCY REPORT                 ║
╚══════════════════════════════════════════════════════╝

📊 TOKEN USAGE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Documentation loaded:        12,000 tokens
Baseline (all docs):        150,000 tokens
Tokens saved:               138,000 tokens (92% ↓)

💾 CACHE PERFORMANCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Cache efficiency:              100.0% (perfect)

📈 SESSION METRICS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Context usage:                      35% (excellent)
Efficiency score:                94/100 (excellent)

⏱️  TIME SAVED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Estimated time saved:          ~42 minutes

💡 WHAT THIS MEANS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Navigator loaded 92% fewer tokens than loading all docs.
Your context window is 65% available for actual work.

🎯 RECOMMENDATIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Excellent efficiency - keep using lazy-loading strategy
✅ Context usage healthy - plenty of room for work

Share your efficiency: Take a screenshot! #ContextEfficiency
```

### Step 4.4: Judge Telemetry Row (v7.7.1+)

If `.agent/.nav-runtime-state.json` carries a `judge` section with `calls > 0`, append one row:

```
Typed judge ({model}): {calls} calls | {failed} failed | {latency_last_ms} ms last, {latency_max_ms} ms max
  axes: {overridden} overridden / {agreed} agreed / {undecided} undecided
```

Sum the per-axis `axes.<axis>.<outcome>` counters for the three outcome totals. "Overridden"
means the judge changed a decision the keyword heuristic had made; "undecided" means the
answer fell inside the noul band or below the confidence floor and the heuristic answered.
Many undecided → the band is too wide for this project; many overrides on an axis that keeps
being wrong → tighten it or disable. Omit the row when the section is absent or `calls` is 0.

### Step 4.5: Tier-1 Telemetry Row (v7.0.0+)

If `.agent/.nav-runtime-state.json` (schema 2) carries a `tier1` section, append one row to the
report:

```
Tier-1 responder: {hits} zero-token answers | {false_positives} suspected false positives
```

A false positive = a Tier-1 hit followed by a near-identical re-prompt (the user wanted the model
after all). Rising false positives mean the exact-match table is intercepting prompts it should
not — suggest disabling the offending rule via `tier1.rules.<id>: false`. Omit the row when the
section is absent or tier1 is disabled.

### Step 5: Add Context-Specific Recommendations

Based on efficiency score, provide actionable advice:

**If efficiency_score < 70**:
```
⚠️  RECOMMENDATIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  Token savings below target (70%+)
→ Check: Are you loading more docs than needed?
→ Tip: Use navigator to find docs, don't load all upfront

Read more: .agent/philosophy/CONTEXT-EFFICIENCY.md
```

**If context_usage > 80%**:
```
⚠️  RECOMMENDATIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  Context usage high (80%+)
→ Consider: Create context marker and compact
→ Tip: Compact after completing sub-tasks

Read more: .agent/philosophy/ANTI-PATTERNS.md
```

**If cache_efficiency < 80%**:
```
⚠️  RECOMMENDATIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  Cache efficiency low (<80%)
→ Check: CLAUDE.md properly configured?
→ Tip: Ensure prompt caching enabled

Read more: .agent/philosophy/PATTERNS.md (Caching pattern)
```

## Predefined Functions

### `efficiency_scorer.py`

Calculate Navigator efficiency score (0-100) based on:
- Token savings (40 points)
- Cache efficiency (30 points)
- Context usage (30 points)

**Usage**:
```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/navigator-marketplace/navigator}"
[ -d "$PLUGIN_DIR" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"

python3 "$PLUGIN_DIR/skills/nav-stats/functions/efficiency_scorer.py" \
  --tokens-saved-percent 92 \
  --cache-efficiency 100 \
  --context-usage 35
```

**Output**: `94` (integer score)

### `report_formatter.py`

Format efficiency metrics into visual, shareable report.

**Usage**:
```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/navigator-marketplace/navigator}"
[ -d "$PLUGIN_DIR" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"

python3 "$PLUGIN_DIR/skills/nav-stats/functions/report_formatter.py" \
  --baseline 150000 \
  --loaded 12000 \
  --saved 138000 \
  --savings-percent 92 \
  --cache-efficiency 100 \
  --context-usage 35 \
  --efficiency-score 94 \
  --time-saved 42
```

**Output**: Formatted ASCII report (see Step 4)

## Philosophy Integration

**Context Engineering Principle**: Measurement validates optimization

From `.agent/philosophy/PATTERNS.md`:
> "Measure to validate. Navigator tracks real metrics, not estimates."

This skill proves:
- **Token savings** are real (baseline comparison)
- **Cache efficiency** works (OpenTelemetry data)
- **Context usage** is healthy (window not overloaded)
- **Time saved** is quantifiable (6s per 1k tokens)

## User Experience

**User says**: "Show my stats"

**Skill displays**:
1. Visual efficiency report
2. Clear metrics (tokens, cache, context)
3. Interpretation ("What this means")
4. Actionable recommendations

**User can**:
- Screenshot and share (#ContextEfficiency)
- Understand Navigator's impact
- Optimize workflow based on recommendations
- Validate context engineering principles

## Example Output Scenarios

### Scenario 1: Excellent Efficiency (Score 94)

User following lazy-loading pattern, cache working perfectly:
- 92% token savings ✅
- 100% cache efficiency ✅
- 35% context usage ✅
- Score: 94/100

**Recommendation**: Keep it up! Share your efficiency.

### Scenario 2: Fair Efficiency (Score 72)

User loading too many docs upfront:
- 65% token savings ⚠️
- 95% cache efficiency ✅
- 55% context usage ✅
- Score: 72/100

**Recommendation**: Review lazy-loading strategy. Load docs on-demand.

### Scenario 3: Poor Efficiency (Score 48)

User not using Navigator patterns:
- 45% token savings ❌
- 70% cache efficiency ⚠️
- 85% context usage ❌
- Score: 48/100

**Recommendation**: Read philosophy docs. Consider /nav:compact. Review CLAUDE.md.

## Success Metrics

**After using this skill, users should**:
- Understand their efficiency score
- See quantified token savings
- Know what to improve (if anything)
- Feel motivated to share results

**Long-term impact**:
- Users screenshot reports and share
- "Navigator saved me 138k tokens" becomes common
- Efficiency becomes visible, not abstract
- Continuous improvement through measurement

---

**This skill makes Navigator's value tangible and shareable.**
