# Navigator v8.2.4 Release Notes

**Release Date**: 2026-10-05
**Type**: Patch — the context gauge fills a stacked card (TASK-88 follow-up)

## Fixed

- **Full-width gauge when stacked.** v8.2.3 stacks the top cards below 72 columns, but the
  context gauge kept the 10 cells it has in the three-card row, leaving a short bar in a
  full-width card. Stacked, the gauge now takes the rest of the line after the percentage
  (never fewer than the row's 10 cells); in the row layout nothing changes.

Tests: the layout helper asserts the gauge width at 120, 72, 60 and 16 columns (148 kit tests).
