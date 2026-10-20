# Navigator v8.4.7 Release Notes

**Release Date**: 2026-10-20
**Type**: Patch — two desktop pane fixes after the v8.4.6 screenshot (TASK-108)

## Fixed

- **Trend charts are one row tall.** On Claude Code Desktop an `Svg` is drawn as an image, and
  an image whose markup has no intrinsic size (v8.4.6 wrote `width="100%"`) falls back to
  300 × 150 CSS pixels, so the context and session trends filled their cards. The markup now
  carries an absolute width and height (the surface clamps the width to the slot) and the
  element a `height` prop of 28 pixels.
- **A gap between cards.** The terminal shows a row between card frames on its own; the
  desktop stacked them edge to edge. Remote surfaces now get one cell of `rowGap` between
  cards and between the stacked top cards; the terminal tree is unchanged.

Verified: kit 167/167; the terminal pane is byte-identical to v8.4.6.

## Upgrade

```bash
claude plugin update navigator@navigator-marketplace
```

Restart Claude Code after the update.
