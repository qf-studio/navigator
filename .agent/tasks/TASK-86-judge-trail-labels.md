# TASK-86: Judge decision trail and labeling from the /nav pane

**Status**: ✅ Released — v8.1.0, 2026-10-03
**Origin**: TASK-84 8.1 candidate 2; TypeSafe asked to "see the decisions" (TASK-80 surface).

## Goal

Behind `j` in `/nav`: the session tally (there since v8.0.0) plus the last decisions, one line
each — time, verdict, effect, the prompt's head — and two keys that turn dogfood into eval data:
`y` confirms the judge's verdict as the label, `x` disputes it. Labels land in the personal
`~/.config/navigator/judge-labels.json` in the exact shape `scripts/judge_label.py` and
`scripts/judge_eval.py --fixture` read, so a disputed prompt shows up in `judge_label.py label`
for a proper label later and a confirmed one scores immediately.

## Design

- `NavJudge` gains `text` (the prompt, secret-redacted, head-capped at `max_state_chars`),
  `at`, and `label?: confirmed | disputed`; `judgeTrail` atom keeps the last 20.
- `labelFromVerdict`: `loop` → LOOP; `chat` → DIRECT/false/false; level substantial|large →
  TASK, else DIRECT; `unclear` → ambiguous. A dispute writes `tier: null` (the labeler's
  "unlabeled" predicate) with `disputed: true` and the judge's verdict kept as `judged`.
- Label file: `{ "_doc", "prompts": [ { text, tier, task, ambiguous, project, source: "pane",
  at, judged } ] }`, deduped by text. Personal dir resolved like the ADHD switch
  (`NAVIGATOR_CONFIG_HOME` / `XDG_CONFIG_HOME` / `~/.config`).
- Python side unchanged: `judge_label.py label --fixture ~/.config/navigator/judge-labels.json`
  walks disputes; `judge_eval.py --fixture …` scores the confirmed ones.

## Verify

Kit tests: label derivation, dedupe, trail lines, pane press → file content. Live: `j`, `y`,
then `python3 scripts/judge_eval.py --fixture ~/.config/navigator/judge-labels.json`.

## Done (2026-10-03)

`NavJudge` carries `text`/`at`/`label`; `judgeTrail` atom (20); the judge card behind `j` lists
the last 8 as `HH:MM · verdict  "prompt head"` (✓ / ✗ once labeled) under the tally, with
`y: verdict right` / `x: wrong` while the latest is unlabeled. `labelLatest` writes
`<personal dir>/judge-labels.json` through `withLabel` (dedupe by text, malformed file reset);
`lib/adhd.ts` gained `personalDir`. Tests: `nav.test.ts` (label derivation, dedupe, trail line),
`register.test.ts` (u) extended + (u3). 128 kit tests. Not in the trail: the effect — it is on
the main judge line and did not fit the pane width with the prompt head.
