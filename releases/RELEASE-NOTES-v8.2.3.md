# Navigator v8.2.3 Release Notes

**Release Date**: 2026-10-05
**Type**: Patch — `/nav` on a narrow terminal (TASK-88 follow-up)

## Fixed

- **The pane follows its real width.** It asks for 72 columns; a narrow split gives it less,
  and the layout was computed for 72 regardless: three top cards at 31/43/26 percent of about
  60 columns truncated every line (`good moment t…`, `toke…`, `2 rejects …`), the sparklines
  degraded to `…`, and the footer broke `l: rejects` into one letter per line. The render now
  reads `bodyColumns`; below 72 the top cards stack full-width, the trend and judge-trail
  widths come from the real width, and the button row wraps whole buttons.

Tests: 148 kit tests (+1: the layout helper at 120, 72, 71, 60 and 10 columns). The kit mounts
the pane at its default 72 columns.
