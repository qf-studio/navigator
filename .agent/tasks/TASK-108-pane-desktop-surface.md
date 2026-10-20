# TASK-108: /nav pane and intent brief draw correctly on the desktop surface

**Status**: ✅ Completed — 2026-10-20; released in v8.4.6 (cb8a244) + v8.4.7 (95ec927: trend Svg intrinsic size, card gap) + v8.4.8 (9c7e441: column gap between top cards) + v8.4.9 (210ebba: gap per axis); first desktop screenshot verified gauge, labels, leg press, memories, key row
**Priority**: Medium
**Source**: three screenshots of 2026-10-20 (terminal pane, desktop chat brief, desktop sidebar
pane); `.agent/research/claude-code-mods-2026-10-19/claude-code.d.ts-2.1.299.txt` (line
numbers below refer to that file); `findings.md` §4
**Owner**: Navigator maintainers

## Problem

The `/nav` pane is drawn for one surface: the terminal, where every glyph is one cell wide and
`wrap="truncate-end"` cuts a row at the frame. Claude Code Desktop draws the same tree over the
wire as a flex div and styled spans (d.ts 12617) in a proportional face. Everything the pane
sizes in cells breaks there, and the intent brief, which the model writes as a box of `│` and
`─`, falls apart in the chat for the same reason.

What the docs say that matters:

| Fact | Where |
|---|---|
| `e.surface` on `ui.render` is `'terminal' \| 'desktop' \| 'vscode' \| 'mobile'`; narrow on it | d.ts 9960–9965, 10617 |
| `viewport.columns` / `bodyColumns` are cells "over the advance of its code font"; a proportional span does not keep that width | d.ts 10630–10636 |
| `Text.mono` / `tabular` draw the code face on the desktop, but they are new in 2.1.299 and the engine refuses unknown Text props ("Others are refused") | d.ts 1700–1712 (mono/tabular), 12623; absent in the 2.1.287 types |
| `Box` spacing and `width` in cells are "the same on every surface"; `backgroundColor` is a Box prop | d.ts 897, 1012, 12324 |
| `Svg` is the remote surfaces' vector leaf, present in the `desktop`, `vscode`, `mobile` tables on 2.1.287 and 2.1.299; absent on `terminal` | d.ts 3870–3900, 12678 |
| `Button` children (a chip plus a wrapped Text in one pressable) are 2.1.295+; on 2.1.287 a Button is a label alone | d.ts 9713; findings §4 |
| The test kit mounts the pane per surface and reads the tree, never the paint | d.ts 28–60; `register.test.ts` `SURFACES` |

Floor stays `MIN_CC = 2.1.287`. So the fix uses `e.surface`, Box columns, Box gauges and Svg,
not `mono`, `tabular`, `weight` or Button children.

## Defects → cause → fix

Desktop sidebar (screenshot 3):

| # | Defect | Cause | Fix |
|---|---|---|---|
| D1 | Context gauge wraps onto a second line | `gauge(percent, gaugeWidth)` is a string of `█▓░` sized from `bodyColumns`; the desktop's fallback glyphs are wider than a code-font cell, and `truncate-end` is Ink's | On remote surfaces draw the gauge as a `Box` row: a filled `Box` with `backgroundColor={ctxColor}` and `width="35%"` beside a dim remainder, `height={1}`; terminal keeps the glyph gauge |
| D2 | Context trend shows as a floating column of dots | `brailleArea` rows are mostly spaces; proportional spaces collapse the x axis | On remote surfaces draw the trend as an `Svg` (`<polyline>` area, `preserveAspectRatio="none"`, `width="100%"`, the card's gradient as `<linearGradient>`), `alt` = the last value; terminal keeps braille |
| D3 | `→ then`, `marker`, task-id labels do not line up | `padEnd(TASK_LABEL)` pads with spaces | Replace every `padEnd` label with a `Box width={TASK_LABEL} flexShrink={0}` column on every surface; the terminal looks the same (cells), the desktop aligns |
| D4 | Memory rows wrap under the pin button, full width | `Box row` holds a Button then a Text; the desktop wraps the span under the button | Pin button in a `Box flexShrink={0}`, text in a `Box flexGrow={1} flexShrink={1}`; in the narrow layout memories use `wrap="wrap"` (hanging indent by the column) |
| D5 | Leg button is one truncated native button holding the whole leg text | `label` is `● 1/12  <leg>`; a desktop button is one line | Label becomes `● 1/12` (hotkey `n`, same prompt); the leg text is a sibling `Text` with `wrap` in a `flexGrow` Box. Same shape on the terminal: test at `register.test.ts:489` changes to find `● 2/3` and the leg text separately |
| D6 | Key row `·` separators sit between native buttons and the row wraps oddly | `<Text>·</Text>` between Buttons | Drop the separators on remote surfaces; `columnGap` already spaces the buttons. Terminal keeps them |
| D7 | Judge, next and tasks rows truncate mid-word on the desktop | `truncate-end` | In the narrow layout (which the sidebar always is) every informational row uses `wrap="wrap"`; `truncate-end` stays for the wide terminal layout only |
| D8 | `tokens/min` tail and judge trail lines sized `sessionInner - 12` / `cols - 4` | cell arithmetic | Covered by D2 (Svg) and D7 (wrap) |

Not a defect: the desktop session card shows `$22.86 5h 7% · phase — · graph 761 nodes`
because that session has no Prometheus (the `t === null` branch); correct.

Desktop chat (screenshot 2):

| # | Defect | Cause | Fix |
|---|---|---|---|
| B1 | The INTENT BRIEF box of `│ … │` and `─` breaks: right edges drift, rows wrap | The model writes box-drawing text outside a code fence; the desktop draws replies in a proportional face. `skills/nav-brief/SKILL.md:45` shows the box inside a fence as an *example*; the injected context (`briefLines`) names the fields but not the shape, so the model improvises | The shape rule goes into the injected context, which the model always sees: one new line in `briefLines` (TS) and `prompt_brief.py` (Python), byte-identical: `Shape: a bullet list, one line per field (**Goal** …), or a fenced text block; no box-drawing glyphs.` `SKILL.md` template becomes the bullet form with the fenced box as the alternative |
| B2 | `prompt_gate` injects a `┌ WORKFLOW CHECK ┐` box into context | model may echo it | Out of scope: it is context, not a reply; CLAUDE.md retired the echo mandate. Note only |

## Decisions

1. **Branch on `e.surface`, not on width.** `const remote = e.surface !== 'terminal'`. Width
   still picks `narrow`; the surface picks the primitives. Policy never keys on it (d.ts
   9962: a rendering fact, not a trust signal).
2. **No new engine floor.** `mono`, `tabular`, `weight`, Button children are 2.1.295+/2.1.299
   props; the 2.1.287 engine refuses unknown Text props. Box and Svg exist on both.
3. **Svg only where the terminal has its own glyph form.** Gauge and trend. Everything else is
   Box layout, identical on both surfaces.
4. **Brief shape lives in the hook text.** The skill is advisory; the injected context is the
   contract. Parity fixtures regenerate.

## Steps

1. `hooks/mod/ui/palette.ts`: add pure `areaSvg(values, color, rows): string` and
   `gaugeSvg`-free Box helper data (`gaugeFill(percent): string` returning the `width`
   percentage). Tests in `nav.test.ts`: fixed inputs → exact SVG strings; empty series → flat
   line; `isFlat` → dim stroke.
2. `hooks/mod/register.tsx` pane hook: `remote` flag; D1–D8 as above. Extract three small
   element builders to keep the hook readable: `labelRow(label, body)`, `gaugeRow`, `trendRows`.
   The static scan rule (mem: `$` followed only inside the hooks module) is unaffected: the
   builders take elements, not `$`.
3. `hooks/mod/tests/register.test.ts`: the existing `for (const surface of SURFACES)` pass
   asserts per surface: on `desktop` the tree has an `Svg` under the context card and no
   `Text` whose text matches `/[▓░⠀-⣿]/`; on `terminal` the reverse; no Text contains
   `TASK_LABEL`-padded runs of spaces on either; the leg Button's text is `● 2/3` and the leg
   label is a separate Text; no `·` Text in the key row on `desktop`.
4. `hooks/mod/ops/prompt_brief.ts` + `hooks/ops/prompt_brief.py` + `test_prompt_brief.py`: the
   shape line (B1). `python3 scripts/gen_mod_data.py` regenerates `ops-brief-tight.gen.ts`
   and `ops-defaults.gen.ts`; `make mod-test` asserts byte parity.
5. `skills/nav-brief/SKILL.md`: bullet template first, fenced box as the alternative; one
   sentence on why (proportional font on the desktop).
6. Docs: `.agent/system/plugin-patterns.md` gains a "surfaces" paragraph (narrow on
   `e.surface`; cells vs proportional; Svg on remote; props floor); CHANGELOG entry;
   `.agent/DEVELOPMENT-README.md` Recent line.

## Verify

- `make mod-test` (kit on 2.1.287 and 2.1.299, `env -u NAVIGATOR_MOD_OWNS` in-session) green;
  `claude plugin validate .` unchanged (only the CLAUDE.md root warning).
- Terminal: `/nav` at 72 and 46 columns byte-identical to today except D3/D5 (label column,
  short leg button).
- Desktop: open `/nav` in the Code tab sidebar; compare with screenshot 3: gauge on one line,
  trend an area, labels aligned, memories wrap with indent, leg button short, key row clean.
  A screenshot is the acceptance artifact; the kit cannot see paint.
- Desktop chat: an ambiguous prompt produces a bullet-list brief, no `│`.

## Won't do

- Bump `MIN_CC` for `mono`/`tabular`/Button children (separate decision, TASK-84 list).
- Touch the band (`AbovePrompt`): not in the screenshots; audit it after this lands.
- Change `prompt_gate`'s WORKFLOW CHECK box (B2).
- Site sync and release: follow the usual release after merge.

## Risks

- The desktop's Box `backgroundColor` and percentage `width` are documented, not yet seen in
  this repo: if the gauge Box does not fill, fall back to an Svg gauge (same primitive as D2).
- Svg string size is bounded (131072 chars); the area polyline for 32 points is a few hundred.
- Terminal snapshot tests that read full row text (`→ then    add surface`,
  `register.test.ts:648`) change to a label + text pair.

## Open questions (max 2)

1. Brief shape on the desktop: bullet list (ADHD/STE friendly, proposed) or fenced box
   (byte-identical to the terminal)?
2. Should the terminal also take the Box label column and short leg button (proposed: yes, one
   tree shape; only gauge/trend branch on the surface)?
