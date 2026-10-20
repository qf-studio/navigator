# Navigator v8.4.10 Release Notes

**Release Date**: 2026-10-20
**Type**: Patch — two desktop pane fixes after the v8.4.9 screenshot (TASK-108)

## Fixed

- **One cell of gap between the side-by-side top cards.** v8.4.8 set three, about 50 pixels
  on the desktop; one cell (about 24 pixels with the frames) matches the row gap between
  stacked cards. The terminal tree is unchanged.
- **The pane says what arms its hotkeys.** A hotkey presses only while the pane holds the
  keyboard (`isFocused`). The terminal hands it over on `/nav`; a desktop grants that focus
  only over an empty composer, and a mod cannot take it. On a remote surface the key row now
  carries a dim line while the pane is not focused: click inside it, or use the buttons.

Verified: kit 168/168 (a new test mounts an unfocused desktop pane); `make mod-typecheck`
clean.

## Upgrade

```bash
claude plugin update navigator@navigator-marketplace
```

Restart Claude Code after the update.
