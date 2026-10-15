# TASK-105: nav-sync-claude — faithful extract + generate

**Status**: ✅ Implemented — 2026-10-15 (PR pending; not released)
**Priority**: High
**Owner**: Navigator maintainers

## Problem

On 2026-10-15, `nav-sync-claude` run against an up-to-date project CLAUDE.md
(Navigator 8.4.2) produced a wrong file. Six defects:

1. The hook-liveness guard looked for `.agent/.nav-runtime-state.json` beside the
   `--output` path, so a dry run to `/tmp/x.md` checked `/private/tmp/.agent/`.
2. The output kept the template's own `Navigator Version: 7.0.0-alpha` and
   `Last Updated: 2026-07-10`.
3. `**Core Principle**` became the template placeholder.
4. Multi-line bullets lost their continuation lines.
5. Custom `##` sections appeared twice: under "Additional Project Standards" (the
   standards section ran until a known header name) and again under "Custom Project
   Sections".
6. A template default the project had removed (`**Testing**`) came back, and the
   `[Customize for your project's framework and patterns]` placeholder stayed.

## Model

The project's CLAUDE.md is the truth for everything the template leaves to the project.
`extract` records it verbatim: description and core principle with line breaks, every
standards and forbidden bullet (template defaults the project kept, multi-line
continuations with their indentation), every custom section with the standard section it
precedes (`custom_section_anchors`), and `source_dir`. `generate` renders the installed
template's structure around that content and stamps the two header lines. A round trip
on an already-current file changes only `**Last Updated**` and `**Navigator Version**`.

## Changes

- `skills/nav-sync-claude/functions/claude_updater.py`
  - `extract_section` ends at the next `#`/`##` header, whatever its name.
  - `_list_items` keeps continuation lines; `_field_value` reads multi-line fields.
  - `generate_updated_claude_md(..., version=None, today=None)` replaces the standards
    and forbidden bodies, re-inserts custom sections before their anchors, stamps the
    installed plugin version (`installed_plugin_version`: nearest
    `.claude-plugin/plugin.json` above the script, then the home-directory lookup) and
    today's date.
  - `resolve_project_root`: `--project-root`, else `source_dir`, else cwd. Never
    `--output`.
  - CLI: `--project-root`, `--stamp-version`, `--stamp-date`.
  - Title regex needs whitespace around the dash (`acme-site` stays `acme-site`).
- `templates/CLAUDE.md`: stamp lines set to the current release (nav-init copies it).
- `skills/nav-sync-claude/SKILL.md`: extract/generate documentation and the dry-run flow.
- Tests: `test_claude_updater.py` gains `FaithfulRoundTripTests`, `StampTests`,
  `ProjectRootTests` on a fixture shaped like the failing file; guard tests run with the
  project as cwd. `test_template_shape.py`: the pristine template extracts exactly its
  own default bullets.

## Verify

```bash
cd skills/nav-sync-claude/functions && python3 -m unittest discover -p "test_*.py"
```
