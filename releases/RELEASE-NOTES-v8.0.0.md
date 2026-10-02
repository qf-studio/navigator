# Navigator v8.0.0 Release Notes — "In Process"

**Release Date**: TBD (branch `v8`)
**Type**: Major — the hook runtime becomes a Claude Code mod (TASK-84); the Python runtime stays as
the fallback

## Summary

Navigator's workflow used to run as Python processes that Claude Code started on every hook
event and talked to through stdin and stdout. In v8 the same ops run inside Claude Code as a
**mod** (Claude Code 2.1.287 or newer): no process per event, real state, and a user interface.
Every op was ported with byte parity against the Python version, measured on generated
corpora rather than spot checks. Python stays registered and takes over automatically on older
Claude Code, where an organization blocks mods, or for any op that crashes three times in a
session. Nothing to configure.

## What's New

### The Navigator mod (TASK-84)

- `hooks/hooks.json` names `hooks/mod/register.tsx`; the classic hooks in `plugin.json` are
  unchanged. On Claude Code ≥ 2.1.287 the mod runs all 16 ops; it announces them in
  `NAVIGATOR_MOD_OWNS` and the Python dispatcher skips them (fast exit when an event is fully
  owned).
- One shared state file, `.agent/.nav-runtime-state.json` (schema 2), so an op handed between
  the runtimes mid-session sees the same state.
- Parity: `scripts/gen_mod_data.py` runs the real Python ops over generated corpora (852
  scorer prompts, 60 recorded judge responses, ~3,600 prompt-op cases, ~560 tool-op cases,
  ~2,100 Stop cases, plus lifecycle cases) and writes fixtures the mod's kit tests must match
  byte for byte. `make test-all` runs both runtimes' suites.

### `/nav`: the route view

Navigator keeps the path short and tells you where you are:

- **destination**: the goal Claude states in a brief, else the active task;
- **route**: the steps to the destination, listed one per line: the task's checklist, else the
  numbered steps of its plan section (`## Work breakdown`, `## Implementation plan`, …) with
  `### Step n — … ✅` progress headings marking them done, else research → impl → verify →
  complete. Done steps fold into one line; the current step is dotted; the next action and how
  long you've been on it follow;
- **off route**: two prompts in a row that share nothing with the destination open a warning
  with **park** (writes a parked task stub), **back**, or **switch**;
- **fuel (context)**: fill, turns left, and when to compact; **saved**: tokens kept out of
  context (docs loaded vs the `.agent/` tree, subagent work); tasks behind `t`.
- A one-line **band** above the prompt: `on route: Ship v8 · ● verify 3/5 · next: …`,
  `low fuel: …`, `off route: …`, or nothing.
- A **Pilot** custom theme (`/theme` → Pilot) shipped through the plugin manifest.

### Truthful update notice (TASK-81)

At session start the mod compares its own version with the latest GitHub release (at most
every `auto_update.check_interval_hours`, never under Pilot) and shows the update command.
Navigator never updates itself from a hook. The nav-start skill's Step 1.5 now runs
`auto_updater.py` once and reports its JSON instead of a template the model could echo.

## Behavior changes

- **read_guard's warning reaches the model** as context at the warn threshold (v7 printed it to
  stderr only). The block at the escalate threshold is unchanged.
- **config_guard and setup** notices appear as toasts (mod classic results carry no
  `systemMessage`).
- **Judge key**: the mod reads `TYPESAFE_API_KEY` or `~/.config/typesafe/api_key`; a custom
  `judge.api_key_env` name is honored only by the Python fallback.
- **Matchers**: `MultiEdit` is no longer a tool on Claude Code 2.1.287; the mod watches Edit,
  Write and NotebookEdit.

## Removed

- The v6 scorer shims `skills/nav-start/functions/workflow_detector.py` and
  `skills/nav-brief/functions/ambiguity_scorer.py`, and `scoring.v6_exports`. The nav-workflow
  CLIs (`complexity_detector.py`, `skill_detector.py`) stay as thin entry points.

## Requirements and fallback

- Mods need Claude Code **2.1.287+**. Older versions load the classic hooks exactly as v7 did
  (verified on 2.1.284: `hooks/hooks.json` with `modules` is tolerated).
- `allowManagedModsOnly`, `disableAllHooks` or a refused mod leave the Python runtime in charge.
- Conformance re-driven on 2.1.287 (`tests/harness-conformance/results/cc-2.1.287.json`); probe
  S2 now measures delivery, not obedience: `decision:block` still forces the continuation.

## Upgrade

```
claude plugin update navigator@navigator-marketplace
```

Restart Claude Code afterwards. Then try `/nav`, and `/theme` → Pilot.
