# TASK-83: Claude Code mods spike — `nav-status`

**Status**: ✅ Spike complete — 2026-10-02 (mod under `mods/nav-status/`, not shipped in the
plugin; loaded via `--plugin-dir`). Next decision: v8 runtime port, see "Next".

## Why

Claude Code 2.1.287 added **mods**: JS/TS hook modules that run in-process
(`register(on, options)`, middleware hooks `($, e, next)`), with `prompt.submit` context
injection, `$.state` atoms, a UI layer (`ui.render` on AbovePrompt / Pane / Spinner), and
`claude plugin test`. Navigator's v7 runtime does the same job through Python ops behind a
shell dispatcher (stdin/stdout JSON, sentinel stripping, atomic state file). Before any port,
one small mod had to prove the three hard parts: context injection, a live band the shell
path cannot draw at all, and a clean handoff so the Python op steps aside when the mod is
loaded and stays the fallback when it is not.

## What was built

```
mods/nav-status/
  .claude-plugin/plugin.json   manifest, types: ./types/index.d.ts
  hooks/hooks.json             {"modules": ["./register.tsx"]}
  hooks/register.tsx           session.start, prompt.submit, turn.complete, ui.render
  hooks/adhd.ts                pure mirror of nav_hook_lib/adhd.py + prompt_adhd reasons
  hooks/status.ts              pure: phase regex (= stop_state.py), Next Action, band line
  hooks/register.test.ts       11 kit tests, in-memory FS, both surfaces
  types/index.d.ts             PluginState contract: nav-status.status
  tsconfig.json                engine-written, extends the laid types
```

- **ADHD mode, mod-owned while loaded**: same resolution (repo `adhd_mode.on` pin > personal
  `adhd-mode.json` > off), same toggle phrases, same reason texts, delivered as
  `prompt.submit` `context` and `{drop: reason}` instead of hook stdout.
- **Handoff**: `session.start` runs `$.env.set('NAVIGATOR_MOD_OWNS', 'adhd')`;
  `config.mod_owns("adhd")` (new, beside `is_pilot_executor`) makes `prompt_adhd` return
  None. Unset var = no mod = Python keeps the job. The single-policy-point guard test in
  `test_config.py` now covers both env vars.
- **Band**: `[nav] phase IMPL · ctx 42% · next: run tests` above the prompt, from
  `turn.complete` (`e.answer`, main loop only) and `$.session.usage().context.percent`.
  Quiet before the first turn, under a survey, and for subagent turns.

### Navigator pane (added 2026-10-02, commit 0f71fcd)

`/nav` opens a pane (`hooks/nav.ts` pure parsing + a `ui.render {component: Pane,
requestId: nav}` hook): in-progress task + loop phase, context fill bar from
`$.session.usage()`, compact hint, newest marker, Read counts with a fan-out nudge, up to
four relevant memories from `memory_recall.py --auto` with `▸` to pin one into the next
prompt once, hotkeys `m` marker / `c` compact / `g` graph health / `r` refresh. State lives
in `$.state` atoms and reloads on `classic.SessionStart` (clear/resume/fork), since `/clear`
resets `$.state` and `session.start` does not fire again. 13 kit tests on both surfaces.

## Verified

| Check | Result |
|---|---|
| `claude plugin validate mods/nav-status --strict` | passes; lists 4 events, env reads/writes, state key |
| `claude plugin test mods/nav-status` | 11 / 11 |
| `npx tsc -p mods/nav-status --noEmit` | clean (global `tsc` is a broken pnpm shim) |
| `make test` | all unit tests pass (incl. 3 new HandoffTest, 4 ModOwnsTest) |
| `claude -p --plugin-dir mods/nav-status` + Bash `echo $NAVIGATOR_MOD_OWNS` | `adhd` — `$.env.set` reaches spawned children |
| Dispatcher with/without the var | 1 / 0 ADHD blocks |
| Model-side count of `ADHD MODE: on (` with the mod loaded | exactly 1 (no double injection) |
| Band drawn in a live terminal | ✅ 2026-10-02: `[nav] phase IMPL · ctx 4% · next: run the mod tests` above the input box |

Live check, as run (band seen, debug log shows the hook answering `ui.render` with its own tree, no refusal):
```
claude --plugin-dir "$PWD/mods/nav-status" --debug
```
Type `adhd mode` (dropped, status line shown, no model turn), then a prompt whose reply has
`Phase: IMPL` / `Next Action:` and look for the band above the prompt.

## API facts learned (2.1.287)

- The static scan needs **string literals** in `$.env.get/set` names and in `atom({plugin,
  key})` refs; a `const` indirection fails the module load.
- A destructured binding named `on` inside a hook is refused as shadowing the registrar.
- `$` in a hooks module is `EngineInterface` (from `claude-code`); in tests it is `Engine`
  from `claude-code/testing`.
- Test bottom hooks answer mods-API events with `{ value }` / `{ deny }`; the bottom
  `ui.render` must answer `{ type: 'engine', ref: 0 }` or `$.ui.mount` rejects.
- `turn.complete` input is `{ answer, agentId?, ... }`, not `{ text }` (that is the result).
- `claude -p` loads `--plugin-dir` mods fresh; `session.start` fires with `surface: null`.

## Next

1. Decide the v8 shape: port the UserPromptSubmit ops (gate, brief, tier1, adhd) to one mod
   with the Python ops kept as `classic.*` fallback for CC < 2.1.287.
2. `$.model.classify` as a replacement for the TypeSafe judge (no key, no egress).
3. `$.state`/`$.store` for `.nav-runtime-state.json`; `session.compact` for compact_marker.
4. Ship question: a mod inside the navigator plugin needs `hooks/hooks.json` with both
   `modules` and the classic `hooks`; today the manifest inlines hooks in `plugin.json`.
