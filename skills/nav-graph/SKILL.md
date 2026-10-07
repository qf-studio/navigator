---
name: nav-graph
description: Query project knowledge graph. Search across tasks, SOPs, memories, and concepts. Use when user asks "what do we know about X?", "show everything related to X", or "remember this pattern/pitfall/decision".
allowed-tools: Read, Write, Edit, Bash
version: 1.0.0
---

# Navigator Knowledge Graph Skill

Query and manage the unified project knowledge graph. Surfaces relevant knowledge from tasks, SOPs, system docs, and experiential memories.

## Why This Exists

Navigator v6.0.0 introduces the Project Knowledge Graph:
- **Unified search**: Query across all knowledge types with one interface
- **Experiential memory**: Patterns, pitfalls, decisions, learnings persist
- **Context-aware retrieval**: Load only relevant knowledge (~1-2k tokens)
- **Relationship traversal**: Find related concepts and documents

## When to Invoke

**Query triggers**:
- "What do we know about X?"
- "Show everything related to X"
- "Any pitfalls for X?"
- "What decisions about X?"
- "Find all knowledge about X"

**Memory capture triggers**:
- "Remember this pattern: ..."
- "Remember this pitfall: ..."
- "Remember we decided: ..."
- "Remember this learning: ..."

**Graph management triggers**:
- "Initialize knowledge graph"
- "Rebuild knowledge graph"
- "Show graph stats"

## Graph Location

`.agent/knowledge/graph.json` (~1-2k tokens, loaded on query)

## Execution Steps

### Step 1: Determine Action

**QUERY** (searching knowledge):
```
User: "What do we know about authentication?"
→ Query graph by concept
```

**CAPTURE** (storing memory):
```
User: "Remember: auth changes often break session tests"
→ Create new memory node
```

**INIT** (building graph):
```
User: "Initialize knowledge graph"
→ Build graph from existing docs
```

**STATS** (viewing graph):
```
User: "Show graph stats"
→ Display graph statistics
```

### Step 2: Load or Initialize Graph

**Check if graph exists**:
```bash
if [ -f ".agent/knowledge/graph.json" ]; then
  echo "Graph exists"
else
  echo "No graph found, will initialize"
fi
```

**Initialize if not exists**:
```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_builder.py" \
  --agent-dir .agent \
  --output .agent/knowledge/graph.json
```

### Step 3A: Query Knowledge (If QUERY Action)

**Extract concept from user input**:
```
User: "What do we know about testing?"
→ Concept: testing

User: "Any pitfalls for auth?"
→ Concept: auth (normalized to authentication)
```

**Run query**:
```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_manager.py" \
  --action query \
  --concept "testing" \
  --graph-path .agent/knowledge/graph.json
```

**Display results**:
```
Knowledge Graph: "testing"

TASKS (3)
  - TASK-30: Task Verification Enhancement (completed)
  - TASK-17: Visual Regression Integration (completed)
  - TASK-11: Project Skills Generation (completed)

MEMORIES (2)
  - PITFALL: "Auth changes break session tests" (90%)
  - PATTERN: "Always run unit tests before integration" (85%)

SOPs (1)
  - visual-regression-setup

FILES (5)
  - skills/backend-test/*
  - skills/frontend-test/*

Load details: "Read TASK-30" or "Show testing memories"
```

### Step 3B: Capture Memory (If CAPTURE Action)

**Parse memory from user input**:
```
User: "Remember this pitfall: auth changes often break session tests"
→ Type: pitfall
→ Summary: "auth changes often break session tests"
→ Concepts: [auth, testing]

User: "Remember we decided to use JWT over sessions for scaling"
→ Type: decision
→ Summary: "use JWT over sessions for scaling"
→ Concepts: [auth, architecture]
```

**Determine memory type**:

| User Says | Memory Type |
|-----------|-------------|
| "pattern", "we use", "approach" | pattern |
| "pitfall", "watch out", "careful" | pitfall |
| "decided", "chose", "because" | decision |
| "learned", "discovered", "realized" | learning |

**Create memory**:
```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_manager.py" \
  --action add-memory \
  --memory-type pitfall \
  --summary "auth changes often break session tests" \
  --concepts "auth,testing" \
  --confidence 0.9 \
  --graph-path .agent/knowledge/graph.json
```

**Write guarantees (v6.17.0+)**: the backing `.md` is written BEFORE the
graph node and failures fail loudly (no more path-points-at-nothing nodes);
a failed graph save rolls the file back. Concepts are validated against the
graph's concept vocabulary — an unknown concept rejects the write and lists
the valid vocabulary. Pass `--allow-new-concept` to register genuinely new
concepts instead. Graphs without a curated vocabulary skip validation.

**Decisions may carry a TRIZ contradiction (TASK-72)**. When a decision
resolved a real tension (improving A worsened B), record it so future
sessions can ask "how did we resolve this kind of problem before":

```bash
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_manager.py" \
  --action add-memory --memory-type decision \
  --summary "ship new blocking features OFF by default" \
  --concepts "release,configuration" --confidence 0.95 \
  --contradiction "feature value vs regression risk" \
  --separation condition \
  --principle "dynamization (config toggle)"
```

All three flags are optional and free text; keep `--contradiction` under
~60 chars ("A vs B") because it is appended to recall lines. Separation
modes (which TRIZ move resolved it):

| Separation | Meaning | Software example |
|---|---|---|
| time | A now, B later | re-export shims for one major, delete next (mem-063) |
| space | A here, B there | single redacting emitter module; ops never print (mem-065) |
| condition | A when X, B otherwise | confirm + dry-run only on high-stakes dispatch (mem-043) |
| level | A at part level, B at system level | atomic tmp+rename state file over per-op writes (mem-064) |

Query by contradiction (every filter word must match, case-insensitive,
across contradiction + summary + principle; always exits 0):

```bash
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_manager.py" \
  --action contradictions --filter "rollback"
# Contradictions "rollback" (2)
#   - DECISION: "..." (95%) ↔ clean codebase vs rollback safety [separation: time]
#       principle: prior counter-action
```

Tagged memories also render with a ` ↔ A vs B` suffix in session-start and
nav-brief recall. Hand-tagging an existing decision = append the three
footer lines after `**Concepts**:` in its `.md`, then
`graph_maintenance.py --action reconcile --execute --fields-only` (see
Reconcile below; `--fields-only` keeps a pruned `resolved/` archive from
being re-registered under fresh ids).

**Optionally create detailed memory file**:
```markdown
# Pitfall: Auth Changes Break Session Tests

## Summary
Auth changes often break session tests due to...

## Context
Discovered during TASK-XX when...

## Recommended Approach
When modifying auth, always run...

## Related
- TASK-12: V3 Skills-Only
- SOP: autonomous-completion
```

**Confirm capture**:
```
Memory captured: mem-001

Type: Pitfall
Summary: "auth changes often break session tests"
Concepts: auth, testing
Confidence: 90%

This will be surfaced when working on auth or testing topics.
```

### Step 3C: Initialize Graph (If INIT Action)

**Build from existing docs**:
```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_builder.py" \
  --agent-dir .agent \
  --output .agent/knowledge/graph.json
```

**Display results**:
```
Knowledge Graph Initialized

Scanned:
  - Tasks: 35
  - SOPs: 12
  - System docs: 3
  - Markers: 8

Extracted:
  - Concepts: 15
  - Relationships: 47

Graph saved to .agent/knowledge/graph.json

Query with: "What do we know about [topic]?"
```

**Rebuild safety (v6.17.0+)**: re-running the builder over an existing graph
PRESERVES the `memories` and `files` buckets and their edges — memories carry
graph-only fields no scan can reconstruct, and rebuilds used to wipe them
silently. Pass `--no-preserve-memories` for an intentional from-scratch
rebuild.

### Step 3D: Show Stats (If STATS Action)

**Display graph statistics**:
```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_manager.py" \
  --action stats \
  --graph-path .agent/knowledge/graph.json
```

**Output**:
```
Knowledge Graph Statistics
==========================
Total Nodes: 65
Total Edges: 47
Memories: 5
Last Updated: 2025-01-23T10:30:00Z

By Type:
  Tasks: 35
  SOPs: 12
  System: 3
  Markers: 8
  Concepts: 15
  Memories: 5
```

### Step 4: Find Related (Optional)

**If user asks for related items**:
```
User: "What's related to TASK-29?"
```

**Run traversal**:
```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_manager.py" \
  --action related \
  --node-id "TASK-29" \
  --max-depth 2 \
  --graph-path .agent/knowledge/graph.json
```

---

## Memory Types

### Pattern
"We use X for Y in this project"
- Reusable approaches
- Project conventions
- Best practices

### Pitfall
"Watch out for X when touching Y"
- Common mistakes
- Gotchas
- Failure modes

### Decision
"We chose X over Y because Z"
- Architecture decisions
- Technology choices
- Trade-off rationale

### Learning
"X usually means Y in this codebase"
- Project-specific knowledge
- Error interpretations
- Domain insights

---

## Confidence System

**Base confidence**:
- Correction-based: 0.8
- Explicit capture: 0.9

**Decay**:
- 1% per week since last validation

**Boost**:
- +5% per use (max +25%)

**Threshold**:
- Below 0.3: Candidate for pruning
- Above 0.7: Reliable memory

---

## Integration with Other Skills

### nav-start (Session Start)
Loads graph stats on session start:
```
Knowledge graph: 65 nodes, 5 memories
Relevant: 2 memories for current context
```

### nav-task (Task Creation)
Auto-extracts concepts from new tasks:
```
Creating TASK-35: Project Memory
Extracted concepts: knowledge, memory, graph
Added to graph.
```

### nav-profile (Corrections)
Corrections auto-create memories via `correction_to_memory.py`:
```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
# When correction detected in nav-profile:
python3 "$PLUGIN_DIR/skills/nav-graph/functions/correction_to_memory.py" \
  --action convert-one \
  --correction-json '{"pattern": "...", "context": "...", "confidence": "high"}'

# Output:
[Correction detected]
→ Type: pitfall (based on pattern analysis)
→ Concepts: [auth, testing] (auto-extracted)
→ Created memory: mem-002
→ Added to graph
```

**Sync all corrections**:
```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-graph/functions/correction_to_memory.py" \
  --action sync \
  --profile-path .agent/.user-profile.json \
  --graph-path .agent/knowledge/graph.json
```

### nav-marker (Context Markers)
Markers reference graph state:
```
## Graph State
- Memories surfaced: mem-001, mem-003
- Concepts active: auth, testing
```

### navigator-research (Codebase Exploration Agent)

The `navigator-research` agent emits a structured `research_findings` JSON block alongside its markdown summary. After the agent returns, ingest those findings as graph memories via `research_to_graph.py`:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
# Save the JSON block from the agent output to a file (or pipe via stdin)
python3 "$PLUGIN_DIR/skills/nav-graph/functions/research_to_graph.py" findings.json

# Or from stdin
cat findings.json | python3 "$PLUGIN_DIR/skills/nav-graph/functions/research_to_graph.py" -

# Validate without writing
python3 "$PLUGIN_DIR/skills/nav-graph/functions/research_to_graph.py" findings.json --dry-run
```

**Trigger phrases**:
- "Ingest research findings"
- "Save these findings to the graph"
- (Automatic, when a navigator-research invocation completes — orchestrator may auto-ingest)

**Defaults**:
- Confidence: `0.7` (lower than corrections/explicit captures — research is inference)
- Memory types accepted: `pattern`, `pitfall`, `decision`, `learning`
- Invalid entries are skipped with a printed error (exit code 1 if any errors)
- Evidence path (e.g. `src/auth.ts:42`) is embedded into the memory summary

**Schema**: see the `Output Format` section of `agents/navigator-research.md` for the full JSON shape the agent emits.

### nav-deep-research (Web Research Skill)

Web research runs (`skills/nav-deep-research`) ingest through the same path: after the ship gate
passes, `report_to_graph.py --run <slug>` turns every typed `## Key findings` bullet of the report
into a memory whose evidence is the cited source URL(s), then calls `research_to_graph.ingest_findings`.
Same 0.7 confidence and memory types; no schema change.

---

## Configuration

In `.agent/.nav-config.json`:
```json
{
  "knowledge_graph": {
    "enabled": true,
    "auto_capture_corrections": true,
    "auto_capture_decisions": true,
    "auto_surface_relevant": true,
    "max_session_memories": 5,
    "confidence_decay_rate": 0.01,
    "staleness_threshold_days": 90,
    "git_tracked": true
  }
}
```

**Note**: `confidence_decay_rate` and `staleness_threshold_days` are consumed
only by the manual `graph_maintenance` commands (`--action decay` /
`--action stale`). They are **not** applied automatically on session start —
decaying a git-tracked file every session would create constant churn. Run
decay/staleness manually when curating the graph.

---

## Graph Maintenance

### Health Check
```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_maintenance.py" --action health
```

Output:
```
Knowledge Graph Health Check
========================================
Total Nodes: 133
Total Edges: 706
Memories: 37 (37 high confidence)
Tasks: 38
Concepts: 16
Orphan Nodes: 0
Duplicate Edges: 0
Dangling Edges: 0
Confidence Out-of-Range: 0

Health Score: 100/100

No integrity issues detected!

Advisory (not scored):
  - 8 potential memory conflicts (heuristic, advisory)
  - 3 stale memories (not validated in 90+ days)
```

`Duplicate Edges`, `Dangling Edges`, and `Confidence Out-of-Range` are the
integrity gate — all three should read `0` on a healthy graph. If they don't,
run `--action repair` (below).

v6.17.0 adds disk-vs-graph checks: `Broken File Links` (node references a
file that doesn't exist) and `Unindexed Memory Files` (files on disk with no
node — the drift class a 2026-07 audit found at 52/84 in a consumer repo)
are score-affecting; concept-vocabulary drift and archived `resolved/` files
without nodes are advisory. Pass `--root <project-root>` when running from
another directory.

### Reconcile Disk vs Graph (v6.17.0+)
Report drift between memory files on disk and graph nodes; `--execute`
registers unindexed files (type from parent dir, `resolved/` parent →
`resolved: true`, frontmatter/heading parsing with conservative fallbacks —
0.5 confidence when unknown) and copies TRIZ footer fields
(`**Contradiction**` / `**Separation**` / `**Principle**`, TASK-72) from disk
onto already-indexed nodes (reported as `field_updates`; never clears a
field removed on disk, never re-syncs `summary`). Broken-link nodes are
never auto-deleted and concept refs are never rewritten — those two are
report-and-hint only:
```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
# Dry-run report
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_maintenance.py" --action reconcile
# Register unindexed files + apply TRIZ field updates
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_maintenance.py" --action reconcile --execute
# TRIZ field updates only (safe when resolved/ holds deliberately pruned files)
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_maintenance.py" --action reconcile --execute --fields-only
```

### Resolve / Supersede a Memory (v6.17.0+)
When a memory stops being true (bug fixed, decision reversed, guidance
codified elsewhere), do NOT delete it — resolve it. The node gets
`resolved: true` (+ `superseded_by` and a `supersedes` edge when a newer
memory replaces it) and the backing file moves to the sibling `resolved/`
directory. Resolved memories are excluded from session-start surfacing and
task-doc recall, skipped by stale/decay sweeps, and flagged `[resolved]` in
query output:
```bash
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_manager.py" \
  --action resolve-memory --node-id mem-012 [--superseded-by mem-045]
```

### Memory Recall (v6.17.0+)
Deterministic relevance ranking used by the SessionStart hook and nav-task
Step 2.5 — also useful standalone:
```bash
# Explicit concepts (markdown for task docs, compact for terse output)
python3 "$PLUGIN_DIR/skills/nav-graph/functions/memory_recall.py" \
  --concepts "auth,testing" --format markdown --limit 5
# Auto mode: concepts from open task nodes + active context marker
python3 "$PLUGIN_DIR/skills/nav-graph/functions/memory_recall.py" \
  --auto --agent-dir .agent --limit 5
```
Scoring: concept overlap (alias-resolved), then confidence; resolved
memories excluded; silent (exit 0, no output) when nothing matches.
Compatible with consumer graphs that use `file:` keys and lack a
`concept_index`.

### Repair Integrity Defects
Idempotently dedupe `(from, to, type)` edge rows, drop edges that reference a
missing node id, and normalize out-of-range memory confidences (a value like
`90.0` is treated as `90%` → `0.9`). Safe to re-run:
```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_maintenance.py" --action repair
```

### Conflict Detection
Find memories that may contradict each other. **Advisory only** — a
high-false-positive keyword heuristic that does **not** affect the health score:
```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_maintenance.py" --action conflicts
```

### Stale Memory Detection
Find memories not validated in 90+ days:
```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_maintenance.py" --action stale --stale-days 90
```

### Low Confidence Pruning
Find and optionally remove low-confidence memories:
```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
# Preview what would be removed
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_maintenance.py" --action prune --threshold 0.3 --dry-run

# Actually remove (use with caution)
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_maintenance.py" --action prune --threshold 0.3 --execute
```

### Apply Decay (experimental, manual-only)
Reduce confidence based on time since each memory's last decay. **Idempotent** —
running it twice on the same day is a no-op (each memory tracks `last_decayed`).
The rate defaults to `knowledge_graph.confidence_decay_rate` when `--decay-rate`
is omitted. This is **not** wired to any hook; run it manually when curating:
```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_maintenance.py" --action decay
```

---

## Token Budget

| Component | Tokens | When |
|-----------|--------|------|
| graph.json (50 nodes) | ~1000 | On query |
| graph.json (200 nodes) | ~2000 | On query |
| Memory summaries (5) | ~500 | On session start |
| Full memory detail | ~500 each | On request |

**Session overhead**: ~1.3k tokens

---

## Success Criteria

Graph skill succeeds when:
- [ ] Query returns relevant results across knowledge types
- [ ] Memories persist and are surfaced appropriately
- [ ] Concepts connect related items
- [ ] Confidence decay/boost works
- [ ] Graph stays under 2k tokens overhead

---

## Best Practices

**Good queries**:
- "What do we know about auth?" (specific concept)
- "Any pitfalls for testing?" (scoped type)
- "Show everything related to TASK-29" (node traversal)

**Good memory capture**:
- "Remember: we use X for Y" (clear pattern)
- "Remember this pitfall: X breaks Y" (specific issue)
- "Remember we decided X because Y" (rationale included)

**Avoid**:
- Overly broad queries ("What do we know?")
- Storing code snippets in memories (use paths instead)
- Capturing obvious knowledge (focus on project-specific insights)

---

**This skill transforms Navigator from stateless assistant to knowledge-aware team member**
