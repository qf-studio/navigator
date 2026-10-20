# Navigator v8.4.8 Release Notes

**Release Date**: 2026-10-20
**Type**: Patch — one desktop pane fix after the v8.4.7 screenshot (TASK-108)

## Fixed

- **A gap between the side-by-side top cards.** v8.4.7 added a row of gap between stacked
  cards on remote surfaces; the context, session and reads cards in the wide layout still
  touched. The top row now carries three cells of `columnGap` on remote surfaces (a cell
  across is a code-font advance, about a third of a row). The terminal tree is unchanged.

Verified: kit 167/167.

## Upgrade

```bash
claude plugin update navigator@navigator-marketplace
```

Restart Claude Code after the update.
