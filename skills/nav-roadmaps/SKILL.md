---
name: nav-roadmaps
description: Show every roadmap document in the project's .agent/ tree as one table (title, path, kind, last date, status line) plus per-section ticket counts for ticket-table roadmaps. Auto-invoke when user says "show roadmaps", "list roadmaps", "which roadmaps are open", "roadmap table", "roadmap status", or "what roadmaps do we have".
allowed-tools: Bash, Read
version: 1.0.0
---

# Navigator Roadmaps

Render the open roadmaps of a Navigator project as a table. One row per roadmap document. One extra table per ticket-style roadmap with counts per section.

## When to Invoke

Invoke when the user says:
- "show roadmaps", "list roadmaps", "list me all the roadmaps we have open"
- "roadmap table", "roadmap status", "which roadmaps are open"
- "what roadmaps do we have", "roadmaps across repos"

Do NOT invoke when the user asks about one named roadmap. Read that file directly.

## What This Does

1. Finds roadmap documents under `.agent/`: files named `*roadmap*`, task docs whose H1 says roadmap, and program docs a roadmap names as its source plan. Markers and archives are skipped.
2. Classifies each document: `live`, `historical` (header note), `stub` (moved pointer), `program`. A live document whose newest header date is older than the threshold is flagged `stale Nd`.
3. Counts ticket rows (✅ 🚧 🎫 📋) per `##` section for ticket-table roadmaps.
4. Prints two Markdown tables. The agent adds a one-paragraph reading.

## Execution Steps

### Step 1: Check Navigator Initialized

```bash
if [ ! -d ".agent" ]; then
  echo "❌ Navigator not initialized in this project (no .agent/)"
  exit 1
fi
```

### Step 2: Run the Scanner

Add `--also <path>/.agent` for every sibling repo the user names or that the project CLAUDE.md
names as a split-docs home (example: console sessions also scan `../pilot/.agent`).

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"

python3 "$PLUGIN_DIR/skills/nav-roadmaps/functions/roadmap_scan.py" --root .agent [--also ../other-repo/.agent] [--stale-days 30]
```

Flags: `--format json` for machine output · `--stale-days N` (default 30) · `--excerpt N` status width (default 110) · `--today YYYY-MM-DD` for reproducible runs.

### Step 3: Present

1. Paste the scanner's Markdown verbatim. Do not retype the table.
2. Below it, add at most one short paragraph: which roadmap is the plan of record, which status lines are stale, and the one hygiene step that follows. No other commentary.
3. If a `stub` row appears, name the repo that holds the real document (the stub's header says where it moved).

## Output Format

See `templates/roadmap-table.md` for the shape and `examples/pilot-console-2026-11-08.md` for a real run across two repos.

## Rules

- The scanner reads headers only (first 15 lines) for title, kind, date and status. A status line that is a stacked `**Status**:` chain shows its first segment; the stale flag comes from the newest date anywhere in the header.
- `MM-DD` dates in status lines take the current year, or the previous year when that would be in the future.
- Rows in a section whose title contains "Legend" are not counted.
- The skill changes no files.
