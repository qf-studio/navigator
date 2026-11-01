# Navigator v8.4.12 Release Notes

**Release Date**: 2026-11-01
**Type**: Patch — nav-sync-claude keeps the project's layout (TASK-109)

## Fixed

- **A customised CLAUDE.md survives the sync.** On a project file that never had the
  template's shape (no `## Context`, a title without ` - Claude Code Configuration`, custom
  sections with fenced bash blocks and `###` subsections, the runtime paragraph under
  `## Navigator Integration`) the 8.4.11 sync rendered placeholders, cut every section at
  its first fenced block, dropped `## Quick Start` and `## Code Standards`, added a second
  runtime paragraph and re-ordered the sections. `extract` now records the title, the
  preamble and every `##` section in source order, bodies byte for byte, with ``` and
  `~~~` fences kept whole. `generate` renders that layout back and replaces only what
  Navigator owns: the `## Navigator` body, or the `**Navigator runtime**` paragraph in
  place under the project's own header, plus the two stamp lines wherever the file keeps
  them. A template section the project lacks is added after the one that precedes it;
  `## Context` only as the two stamp lines when the file has no stamps, never with
  description or tech-stack placeholders. Hand-written customizations without a
  `sections` layout still render through the template as in v8.4.3.

Verified: 65 tests in `skills/nav-sync-claude/functions` (12 new: a Pilot-shaped fixture,
CLI parity, paragraph replaced in place, exact `## Navigator`, fence scanner); `make test`
green; the Pilot CLAUDE.md preview went from 98 changed lines to the runtime paragraph.

## Upgrade

```bash
claude plugin update navigator@navigator-marketplace
```

Restart Claude Code after the update.
