# Coloring the /nav Pane and the Pilot Theme

**SOP ID**: DEV-004
**Category**: Development
**Last Updated**: 2026-10-05
**Version**: 1.0.0
**Verified on**: Claude Code 2.1.287, Ghostty 1.3.1, Navigator 8.2.5

---

## When to Use This SOP

- The `/nav` pane background does not match the chat background.
- A card, value or label in the pane needs a new color.
- The terminal theme changes and the Pilot theme should follow it.
- A new Claude Code version adds or renames a theme key.

---

## How the Colors Compose

Three layers paint what you see. Each one wins over the one below it.

| Layer | Owner | File | What it paints |
|---|---|---|---|
| Terminal | Ghostty | `themes/pilot.ghostty` → `~/.config/ghostty/themes/pilot` | Base background, foreground, the 16 ANSI colors |
| Claude Code theme | `custom:pilot` | `themes/pilot.json` → `~/.claude/themes/pilot.json` | Chat chrome: bubbles, borders, diffs, **pane background** |
| Pane content | Navigator mod | `hooks/mod/ui/palette.ts` (`PALETTE`) | Text and glyphs inside the pane cards |

Claude Code cannot read the terminal background. Any surface it paints with a theme key
is an opaque color. The pane is one such surface: it is drawn with the theme key
`composerSidebarBackground`. The `dark` base defaults that key to neutral grey
`rgb(38, 38, 38)`, so a custom theme that does not set it gets a grey pane on whatever
background the terminal has.

**Rule**: the Ghostty `background` and the theme's `composerSidebarBackground` carry the
same hex. Today that value is `#14181f`. Change both or neither.

---

## Procedure

### 1. Change the shared background

1. Edit `background` and `cursor-text` in `themes/pilot.ghostty`.
2. Edit `composerSidebarBackground` in `themes/pilot.json` to the same hex.
3. Keep `userMessageBackground` (`#1c2128`) one visible step lighter than the background,
   otherwise user bubbles disappear.
4. Install both files (step 4) and verify (step 5).

### 2. Change a pane text color

1. Edit `PALETTE` in `hooks/mod/ui/palette.ts`. The seven roles are `accent`, `success`,
   `warning`, `error`, `border`, `label`, `dim`.
2. Mirror the change in `themes/pilot.json` so the chat chrome stays in the same family
   (`claude`/`suggestion` ↔ `accent`, `success`, `warning`/`remember`, `error`,
   `subtle`/`promptBorder` ↔ `border`, `text` ↔ `label`, `inactive` ↔ `dim`).
3. Mirror it in the ANSI slots of `themes/pilot.ghostty` so plain shell output matches.
4. Run `make mod-test`. The mod hot-reloads in the running session; `/nav` shows the result.

### 3. Add a Claude Code theme key

1. List the keys the installed binary knows (the custom theme accepts any of them):

```bash
CC="$HOME/.local/share/claude/versions/$(claude --version | cut -d' ' -f1)"
python3 - "$CC" <<'PY'
import re, sys
d = open(sys.argv[1], 'rb').read()
i = d.find(b'composerSidebarBackground:"ansi:blackBright"')
seg = d[i-1200:i+100].decode('utf8', 'replace')
print(sorted(set(re.findall(r'([a-zA-Z_]+):"(?:ansi|rgb|#)', seg))))
PY
```

2. Add the key under `overrides` in `themes/pilot.json`. Values are `#rrggbb`, `rgb(r, g, b)`
   or `ansi:<name>`.
3. Unknown keys are ignored silently, so verify by eye (step 5).

### 4. Install

```bash
cp themes/pilot.json ~/.claude/themes/pilot.json
cp themes/pilot.ghostty ~/.config/ghostty/themes/pilot
ghostty +validate-config
```

The installed theme is a plain copy, not a symlink. The plugin manifest ships `themes/`
(`.claude-plugin/plugin.json`), so a release refreshes the plugin cache copy; the file under
`~/.claude/themes/` is only replaced by this copy.

### 5. Verify

1. Ghostty: `cmd+shift+,` reloads the config. `ghostty +show-config | grep '^background'`
   prints the new hex.
2. Claude Code: run `/theme` and pick Pilot again. A restart is only needed when the pick
   does not repaint.
3. Open `/nav`. The pane background, the chat background and the area under the prompt
   must be one color; user bubbles must still stand out.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Pane grey, chat dark | `composerSidebarBackground` missing from `pilot.json` | Add it with the terminal hex (step 1) |
| Pane and chat match, bubbles invisible | `userMessageBackground` equals the background | Lift bubbles by ~8 units per channel |
| Pane card text off-palette | `PALETTE` edited without `pilot.json`, or vice versa | Mirror per the table in step 2 |
| Ghostty ignores the theme | File not under `~/.config/ghostty/themes/` or name mismatch | `theme = "pilot"` must equal the file name |
| Nothing changes after editing `pilot.json` | Theme read at selection time | `/theme` → Pilot, else restart |

Ghostty `background` is global for the window. Zellij panes and other tabs inherit it, so
a change here recolors every tab, not only Claude Code.

---

## Related

- `themes/pilot.json`, `themes/pilot.ghostty`, `hooks/mod/ui/palette.ts`
- `.agent/tasks/TASK-83-mods-spike.md` (where the custom theme was introduced)
- Pilot TUI palette: `~/.claude/skills/pilot-design/SKILL.md`
