# Navigator v8.3.0 Release Notes — "Say the Word, Any Word"

**Release Date**: 2026-10-05
**Type**: Minor — reply modes as a table, STE mode (TASK-93)

## Summary

ADHD mode (v7.9.0) was one op with its phrases, file and rule block hardcoded. Adding a
second mode by copy would have doubled that. Instead the mode is now a row in a table and
one op serves every row. The second row is STE: the sentence rules of ASD-STE100
Simplified Technical English, Issue 9, for readers who want one idea per sentence, the
imperative for instructions and the active voice for everything else.

## What's New

### Reply modes table (TASK-93)

`hooks/nav_hook_lib/reply_modes.py` holds `MODES`: frozen rows with a key, a label, a
config block name, a personal file name and a rule block. Toggle phrases are generated
from the key (`<key> mode on|off`, `enable <key> mode`, `<key> status`, …), so a row needs
no phrase list. The mod mirrors the table in `hooks/mod/lib/reply_modes.ts`; the ADHD block
is byte-identical to v7.9.0 on both runtimes.

The new `prompt_modes` op replaces `prompt_adhd` on both runtimes (same registry row,
responder phase). A toggle phrase of any mode answers through `decision: block` at zero
model turn and writes that mode's file under `~/.config/navigator/`. Every other prompt
carries the blocks of all modes that resolve on, joined in table order with a blank line:
reply-shape rules (ADHD) first, sentence rules (STE) inside them. ADHD-only output is
unchanged from v8.2.8.

- New config: `reply_modes.enabled` (gates the op, seeds `true`) and
  `ste_mode: {enabled, on}` (same shape as `adhd_mode`). `<key>_mode.enabled: false`
  hides that one mode: its toggle phrase answers "disabled in this repo", nothing is
  written or injected.
- Session start prints one status line per mode that someone switched explicitly.
- `nav-features` lists `ste_mode`; `enable ste_mode` writes the personal file like
  `enable adhd_mode` does. The personal-switch branch now resolves the mode from the
  table instead of a hardcoded module.
- `MAX_TOTAL_BLOCK_CHARS` (1600) is asserted over the sum of all rule blocks so a new row
  cannot quietly double the per-prompt cost.

### STE mode

Say `ste mode on` or `use ste`; `ste mode off` or `stop ste` ends it. The block is a Part 1
subset of Issue 9: one idea per sentence, 20 words for instructions and 25 for
descriptions, the imperative for instructions, the active voice and present tense, one
instruction per sentence, paragraphs of six sentences or fewer, no gerunds, no noun
clusters over three words, one meaning per word, full sentences with articles. Error
output, test results and quoted text stay verbatim. The ~900-word controlled dictionary is
deliberately not applied: it cannot describe a hook runtime.

## Changed

- `prompt_adhd` → `prompt_modes` in the registry, `NAVIGATOR_MOD_OWNS`, `owns.ts` and the
  ops index. `nav_hook_lib/adhd.py`, `hooks/mod/lib/adhd.ts` and both `prompt_adhd` files
  are deleted; nothing outside the runtime imported them.
- Config migrator seeds `reply_modes` and `ste_mode` at 8.3.0.

## Adding a mode

One `Mode(...)` row in `reply_modes.py`, the same row in `reply_modes.ts`, a
`<key>_mode` block in `config.DEFAULTS` + the migrator + `.nav-config.json`, a `FEATURES`
entry with `personal: True`, then `python3 scripts/gen_mod_data.py`. See
`.agent/tasks/TASK-93-reply-modes-ste.md`.

Tests: Python `test_reply_modes.py` (15) + `test_prompt_modes.py` (18) replace the ADHD
files; kit +2 (`c4` stacking, `c5` disabled mode) and one new session-start parity case;
156 kit tests.
