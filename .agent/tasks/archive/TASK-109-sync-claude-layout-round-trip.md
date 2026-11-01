# TASK-109: nav-sync-claude — layout round trip for files without the template's shape

**Status**: ✅ Released in v8.4.12 — 2026-11-01
**Priority**: High
**Owner**: Navigator maintainers
**Follows**: TASK-105 (faithful extract + generate, v8.4.3)

## Problem

On 2026-11-01 `nav-sync-claude` (plugin 8.4.11) run against the Pilot project's CLAUDE.md
(qf-studio/pilot, commit a3c773952) produced a preview with 98 changed lines. That file
never had the template's shape: no `## Context`, the title `# Pilot: AI That Ships Your
Tickets`, a one-line preamble, 13 non-template `##` sections with `###` subsections and
fenced bash blocks, and the runtime paragraph plus the stamp lines inside
`## Navigator Integration`. Five defects:

1. The title became `# [Project Name] - Claude Code Configuration` and the description,
   tech-stack and core-principle placeholders were rendered: `extract` only accepted a
   `<Name> - Claude Code Configuration` title and only read `## Context`.
2. A custom section lost everything after its first fenced bash block: the header regex
   (`^#{1,2}\s`) matched `# comment` lines inside the fence, so the section ended there.
   The `### Rules` subsection after the block was gone.
3. `## Quick Start` (a fenced block only), `## Code Standards`, `## Configuration` and
   `## Commit Guidelines` vanished: they were in `STANDARD_SECTIONS`, so not custom, but
   the template no longer renders them.
4. The runtime paragraph appeared twice: `## Navigator Integration` was a custom section,
   so the template's `## Navigator` was inserted beside it, old stamps included.
5. Custom sections were re-anchored to the template's order (`## Forbidden Actions` and
   `## Project-Specific Code Standards` above `## Who is reading this file?`).

## Model

The project's CLAUDE.md is the truth for its layout. `extract` records the title, the
preamble and every `##` section in order, bodies byte for byte, with fenced code blocks
kept whole (``` and ~~~ fences). It names the section Navigator owns: `## Navigator`, or
the section whose body carries the `**Navigator runtime...**:` paragraph.

`generate` renders that layout back and replaces only Navigator-owned text: the
`## Navigator` body, or the runtime paragraph in place inside the project's own section
(header and every other line kept), plus the two stamp lines wherever the file keeps them.
Template sections the project lacks are added after the template section that precedes
them: `## Context` only as the two stamp lines when the file has no stamps anywhere (no
placeholders), `## Navigator` only when no section carries the paragraph, the standards
and forbidden sections with the template's defaults (`## Code Standards` is the
standards section under its older name). A round trip on a current file changes only the
two stamp lines. A hand-edited runtime paragraph is replaced by the template's: that is
the one piece of prose the sync exists to update, and the preview shows it.

The flat lists (`code_standards`, `forbidden_actions`, `custom_sections`,
`custom_section_anchors`) stay in the JSON. Customizations without a `sections` layout
(hand-written JSON) still render through the template as in TASK-105.

## Changes

- `skills/nav-sync-claude/functions/claude_updater.py`
  - `_scan_headers` / `_section_bodies`: fence-aware header scan; `extract_section`,
    `_replace_section_body` and `_insert_custom_sections` use it (exact title match,
    case-insensitive).
  - `extract_customizations` adds `title`, `preamble`, `sections`, `navigator_section`,
    `has_context`; `project_name` falls back to the whole title. `STANDARD_SECTIONS`
    shrinks to the sections the flat lists render; the runtime-owning section is not a
    custom section.
  - `_render_from_layout` (new, used when `sections` is present) and
    `_render_from_lists` (the TASK-105 path); `SECTION_ALIASES`.
- `skills/nav-sync-claude/SKILL.md`: extract keys and the two generate modes.
- Tests: `LayoutRoundTripTests` (Pilot-shaped fixture: no Context, colon title, preamble,
  fence with `# comment` lines then `###`, fence-only section, `## Quick Start`,
  `## Code Standards`, paragraph + stamps under `## Navigator Integration`, source order;
  outdated paragraph replaced in place; exact `## Navigator` takes the template body;
  a file with neither paragraph nor stamps gets both without placeholders; CLI parity;
  extract stable across a second sync), `FenceAwareHeaderTests`.

## Verify

```bash
cd skills/nav-sync-claude/functions && python3 -m unittest discover -p "test_*.py"
```

On the Pilot file at a3c773952 the preview now differs only in the runtime paragraph
(Pilot's copy was a hand-edited `(v7+)` variant); with a matching paragraph, only the
two stamp lines. The other five local project files (pilot-console, pilot-pr,
pilot-cloud-infra, pilotcloud-site, pilot-console-ui) and this repo's CLAUDE.md were
smoke-run the same way.
