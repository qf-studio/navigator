# Navigator v8.4.6 Release Notes

**Release Date**: 2026-10-20
**Type**: Patch — the `/nav` pane and the intent brief draw correctly on Claude Code Desktop (TASK-108)

## Fixed

The `/nav` pane was drawn for one surface: the terminal, where every glyph is one cell wide.
Claude Code Desktop draws the same tree in a proportional face, so in the desktop sidebar the
context gauge wrapped onto a second line, the braille trend floated as a column of dots, the
`→ then` / `marker` / task-id label columns drifted, memory rows wrapped under their pin, and
the leg button was one truncated native button holding the whole leg text. In the chat, the
intent brief's box of `│` and `─` fell apart for the same reason.

- **One tree, two surfaces.** The pane hook branches on `e.surface`: the terminal keeps its
  glyph gauge and braille trend; a remote surface (desktop, VS Code, the phones) draws the
  gauge as a Box fill and the trend as an `Svg` area of the same series. Everything else is
  layout that is the same on both: label columns are a Box of `TASK_LABEL` cells instead of
  a `padEnd` of spaces, the leg press is the short `● k/n` beside the leg text, memory rows
  wrap with a hanging indent, the stacked layout (every sidebar) wraps rows instead of
  truncating them, and the key row drops the `·` between native buttons.
- **The brief is a bullet list.** The injected `NAV-BRIEF` context now says so in both
  runtimes (`prompt_brief.py`, `prompt_brief.ts`, parity fixtures regenerated): one line per
  field, or a fenced text block; never box-drawing glyphs in the reply. `nav-brief`'s
  template is the bullet form.
- **Engine floor unchanged.** `Text.mono`, `tabular`, `weight` and Button children are
  2.1.295+ props that the 2.1.287 engine refuses, so the pane uses none of them. `Svg`,
  Box `width`/`height`/`backgroundColor` and `e.surface` exist on both.

On the terminal the only visible changes are the short leg button and the label column.
Pattern: `.agent/system/plugin-patterns.md` "One Tree, Two Surfaces".

Verified: kit 167/167 with per-surface assertions (`terminal` keeps glyphs; `desktop` has an
`Svg`, no glyphs, no `·`); `make test` and the Python op tests green; `claude plugin validate .`
unchanged.

## Upgrade

```bash
claude plugin update navigator@navigator-marketplace
```

Restart Claude Code after the update.
