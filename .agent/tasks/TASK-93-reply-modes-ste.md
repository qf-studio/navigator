# TASK-93: Reply modes — one table, one op; STE mode joins ADHD mode

**Status**: ✅ Released — v8.3.0, 2026-10-05

## Origin

A session on 2026-10-05 compared ASD-STE100 (Simplified Technical English, Issue 9,
January 2025) with ADHD mode (TASK-82). Same category, different layer: ADHD mode shapes
the reply (ordering, caps, numbering, closing action); STE shapes the sentence (one idea,
20 words, imperative, active voice, no gerunds). The user tested STE live for three turns
and asked for it as a switch. Then: "we might have more, so this needs to be easy to update
and clear reading matters" — a generic registry, not a second copy of `prompt_adhd`.

## Design

**One table.** `hooks/nav_hook_lib/reply_modes.py` holds `MODES`, a tuple of frozen `Mode`
rows: `key` (the word in toggle phrases), `label`, `config_key`, `state_name`, `rule_block`,
optional extra phrases. Toggle phrases are generated from `key` (`<key> mode on|off`,
`enable <key> mode`, `<key> status`, …), so a new row needs no phrase list. The mirror is
`hooks/mod/lib/reply_modes.ts` with the same rows; the two rule blocks are byte-identical
across runtimes and the ADHD block is unchanged from v7.9.0.

**One op.** `prompt_modes` (Python `hooks/ops/prompt_modes.py`, mod
`hooks/mod/ops/prompt_modes.ts`) replaces `prompt_adhd`. Responder phase, same row position.
A toggle phrase of any mode answers via `decision: block` and writes that mode's personal
file. Otherwise every enabled mode that resolves on contributes its block; blocks join with
a blank line in table order. ADHD-only output is byte-identical to v8.2.8 (no trailer).

**Order is policy.** Shape rules (ADHD) come first, sentence rules (STE) second; the STE
block ends with "inside any reply-shape rules above". The table order is the merge order.

**Config.** `reply_modes.enabled` gates the op (seeds true). Each mode keeps its own block
`<key>_mode: {enabled, on}`: `enabled: false` makes that mode invisible (its toggle phrase
answers "disabled in this repo", nothing is written or injected); `on: true|false` pins,
`null` defers to `~/.config/navigator/<key>-mode.json`. Resolution per mode is unchanged:
repo pin > personal file > off.

**Cost cap.** `MAX_TOTAL_BLOCK_CHARS = 1600` is asserted by tests over the sum of all
rule blocks, so a new row cannot quietly double the per-prompt cost.

**STE block.** A Part 1 subset of Issue 9 (sentence length, imperative, active voice,
present tense, one instruction per sentence, paragraph cap, no gerunds, no noun clusters,
one meaning per word, full sentences). The ~900-word dictionary is deliberately out: it
cannot describe a hook runtime, and full STE would delete the answer. Extra phrases:
`use ste`, `stop ste`.

## Change

- [x] `nav_hook_lib/reply_modes.py` (table + shared functions); `adhd.py` deleted.
- [x] `ops/prompt_modes.py`; `prompt_adhd.py` deleted. Registry row, config DEFAULTS
      (`reply_modes`, `ste_mode`), session-start notice loops the table.
- [x] Mod: `lib/reply_modes.ts`, `ops/prompt_modes.ts`; `owns.ts`, `ops/index.ts`,
      `register.tsx` import, `session_start.ts` notice; fixtures regenerated.
- [x] nav-features: `ste_mode` row; the personal-switch branch resolves the mode from the
      table instead of a hardcoded module. Migrator `8.3.0` block.
- [x] Tests: `test_reply_modes.py`, `test_prompt_modes.py` (replace the ADHD files; cover
      both rows + stacking + disabled mode); registry/config/session-start/feature-manager
      tests updated; kit +2 (`c4` stack, `c5` disabled); one new session-start parity case.
- [x] Docs: CLAUDE.md, DEVELOPMENT-README, project-architecture, nav-features SKILL.md,
      CHANGELOG, release notes.

## Adding a mode

1. Append a `Mode(...)` row to `MODES` in `reply_modes.py` and the same row in
   `reply_modes.ts`. Keep the block declarative, under 900 chars, starting with
   `<LABEL> MODE: on (personal setting; "<key> mode off" ends it)`.
2. Add `"<key>_mode": {"enabled": True, "on": None}` to `config.DEFAULTS`, the migrator
   version block, `.agent/.nav-config.json`, and a `FEATURES` entry with `personal: True`.
3. `python3 scripts/gen_mod_data.py`; add a phrase/block test to `test_reply_modes.py`.

## Won't do (this task)

Terse / non-native / demo modes; mutual-exclusion pairs; a pane card; the STE dictionary;
a Stop-time linter for sentence rules (STE is mechanically checkable; revisit if labeled
replies show drift).

## Verify

```
NAVIGATOR_MOD_OWNS= make test
make mod-gen-check mod-validate mod-test mod-typecheck
```

Live: `use ste` → dropped prompt with "STE mode: on (personal, …/ste-mode.json)"; next
prompt's context carries `ADHD MODE: on (` then `STE MODE: on (`; `/nav` session start
shows both status lines.

## Refs

- `.agent/tasks/TASK-82-adhd-mode.md` (the first row and the personal-switch design)
- ASD-STE100 Issue 9: https://www.asd-ste100.org/ (free download; Issue 10 due 2028-01)
