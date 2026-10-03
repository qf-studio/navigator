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

### `/nav`: one screen, cards

What you see by default is a surprise or a press; the readouts wait behind `d`:

- **context**: fill and a bar, one verdict (`compact safe` / `good moment to compact` /
  `compact due`), and the fill over the last turns as a braille area in a subdued gradient
  (grom's stat texture, `github.com/qf-studio/grom`); a flat trend draws dim;
- **session**: with the Prometheus of `.agent/grafana/` (port 9092) answering, today's cost,
  tokens and cache hit rate, the 7-day cost and commit count, and tokens/min over two hours
  as the same braille area;
  without it, Claude Code's own cost and rate-limit window, the phase, and the graph size.
  Read on `/nav`, on `r`, and after every completed turn, never under Pilot; one probe first,
  so a stopped stack costs one refused connection per turn. The task list, marker and memories
  reload after a turn that wrote under `.agent/`, and after `/clear`, `/resume` or `/compact`. `dashboard.enabled: false` turns it off; `dashboard.prometheus_url` points
  it at another Prometheus on this machine (loopback URLs only; read with `curl`, so it works
  with `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` set and nothing leaves the host);
- **reads** (behind `d`): Read calls this session and how many were docs; `use an Agent`
  when a turn read three or more code files;
- **judge** (only after a judged prompt): the typed judge's verdict in words
  (`task · substantial · unclear`), what Navigator did with it (`→ brief shown`, `task mode`,
  `loop mode`, `direct`), and the axes where it overrode the keyword rule; `j` opens the
  session tally per axis. With `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` set, Claude Code
  refuses the mod's fetch; the judge then goes through `curl` (key and body via environment and
  stdin), so enabling the judge and providing a key is what decides, as in the Python runtime;
- **next**: the destination (the goal Claude states in a brief, else the active task), then the
  current leg as a button (`● 9/14  Docs: …`, turns spent on it): `n` or Enter submits
  `Do the next leg of TASK-84: …` as your prompt. Under it the leg after, with an ETA from the
  pace so far (turns per finished leg × seconds per turn × legs left), and the newest marker.
  Legs come from the task's checklist, else the numbered steps of its plan section
  (`## Work breakdown`, `## Implementation plan`, …) with `### Step n — … ✅` progress headings
  marking them done, else research → impl → verify → complete;
- **off route** (only while drifting): two prompts in a row that share nothing with the
  destination open a warning with **park** (writes a parked task stub), **back**, or **switch**;
- **memories**: up to three recalled for the open tasks, one line each; `▸` pins one into the
  next prompt;
- **tasks** (behind `d`): up to five marked in progress, the destination marked.
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
