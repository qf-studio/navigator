# Navigator v8.4.9 Release Notes

**Release Date**: 2026-10-20
**Type**: Patch — one desktop pane fix after the v8.4.8 screenshot (TASK-108)

## Fixed

- **Stacked cards no longer carry a doubled gap.** v8.4.8 set `columnGap` on the top Box for
  the side-by-side layout, and the desktop read that gap as vertical space when the same Box
  stacks its cards (every sidebar). Each gap is now set only along the axis the Box flows:
  `rowGap` 1 when stacked, `columnGap` 3 side by side. The terminal tree is unchanged.

Verified: kit 167/167; `make mod-typecheck` clean.

## Upgrade

```bash
claude plugin update navigator@navigator-marketplace
```

Restart Claude Code after the update.
