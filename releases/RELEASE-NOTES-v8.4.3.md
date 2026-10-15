# Navigator v8.4.3 Release Notes

**Release Date**: 2026-10-15
**Type**: Patch — nav-sync-claude extract + generate are faithful (TASK-105)

## Fixed

Run on an up-to-date project CLAUDE.md, `nav-sync-claude` produced a wrong file. Six defects,
each with a regression test on a fixture shaped like that file:

- **The liveness guard checked the wrong directory.** It looked for
  `.agent/.nav-runtime-state.json` beside `--output`, so a dry run to `/tmp/x.md` was refused.
  The project root is now `--project-root`, else the `source_dir` that `extract` recorded,
  else the current directory. A dry run writes anywhere.
- **The output carried the template's own version and date.** Generate stamps
  `**Navigator Version**` with the installed plugin version and `**Last Updated**` with today;
  `--stamp-version` / `--stamp-date` override them.
- **`**Core Principle**` became the placeholder.** Extract keeps it, multi-line.
- **Multi-line bullets lost their continuation lines.** Bullets keep them with their
  indentation.
- **Custom `##` sections appeared twice.** A section ends at the next `#`/`##` header,
  whatever its name, and each custom section goes back before the standard section it
  preceded. No more "Additional Project Standards" or "Custom Project Sections" wrappers.
- **A removed template default came back.** The project's standards and forbidden lists
  replace the template's lists (template defaults the project kept stay; a default it removed
  stays removed); the `[Customize ...]` placeholder goes with them.

A round trip on an already-current file changes only the two stamp lines. The customizations
JSON gains `core_principle`, `violations_marker`, `custom_section_anchors` and `source_dir`;
`code_standards` and `forbidden_actions` are now the project's full lists.
`templates/CLAUDE.md` carries the current version and date (nav-init copies it).

Tests: `test_claude_updater.py` +18 (faithful round trip, stamps, project root);
`test_template_shape.py` expects the pristine template's own default bullets; 53 in the skill
suite, full `make test` green.
