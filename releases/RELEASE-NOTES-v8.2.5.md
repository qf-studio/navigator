# Navigator v8.2.5 Release Notes

**Release Date**: 2026-10-05
**Type**: Patch — narrow-pane text (TASK-88 follow-up)

## Fixed

- **Judge row.** At about 46 columns the model version wrapped into the row (`jev-1.13` / `.0`)
  and squeezed the verdict to `task · small · uncl…`. Below 72 columns the version now sits on
  its own dim line under the verdict; the verdict line wraps instead of truncating. The row
  layout is unchanged.
- **Next card.** The task title, the `→ next` action and the marker name wrap onto a second
  line when stacked instead of ending in `…`. The label column stays so the rows still align.

Tests: 149 kit tests (+1: the pane at 72 and at 46 columns, asserting where the version lands
and that the title is whole). Memories and task rows keep truncating on both layouts by design.
