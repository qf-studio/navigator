# Navigator v8.4.11 Release Notes

**Release Date**: 2026-10-20
**Type**: Patch — no dead key chips on the desktop pane (TASK-108)

## Fixed

- **Remote pane buttons carry no hotkey.** Claude Code Desktop 3.1623 on engine 2.1.299 reports
  the pane as focused after a click inside it while the composer keeps the keyboard, so a
  pressed `d` lands in the prompt box and no hotkey fires; and the desktop draws a key chip
  for every `hotkey`. The pane now passes no `hotkey` prop on remote surfaces: plain native
  buttons that press by click, no chip that promises a key. The terminal keeps every key
  (`m c r d l j`, `n`, `y x`, `p b s`). The v8.4.10 "keys arm when…" line is gone with the
  chips. The desktop gap is recorded in `.agent/system/plugin-patterns.md` with an issue
  draft for anthropics/claude-code.

Verified: kit 168/168 (a test asserts no `hotkey` on desktop buttons and `d` on the
terminal's); `make mod-typecheck` clean.

## Upgrade

```bash
claude plugin update navigator@navigator-marketplace
```

Restart Claude Code after the update.
