# TASK-84: Navigator v8 — mod-first runtime with Python fallback

**Status**: 🚧 In Progress — branch `v8` (26 commits, head e0b416a), built and verified headless; awaiting interactive dogfood + go-ahead to release. One v8.0.0 release at parity.

## Context

Navigator v7 enforces its workflow through 16 Python ops behind one shell dispatcher
(`hooks/nav_dispatch.py` → `nav_hook_lib.runtime`), 13 Claude Code events, stdin/stdout JSON,
sentinel stripping, an fcntl-locked state file. Claude Code 2.1.287 added **mods**: in-process
JS/TS hook modules with context injection, deny/drop, `$.state`, a UI layer and typed kit tests.
The TASK-83 spike (`mods/nav-status/`, commits d2384e4..d0b001a) proved injection, a live
band and `/nav` pane with token savings, a Pilot theme, and a Python handoff
(`NAVIGATOR_MOD_OWNS` + `config.mod_owns`). User decisions (2026-10-02):

- **Mod-first, Python fallback**: every op gets a mod implementation; Python ops stay and step
  aside when the mod is loaded (older CC, managed policies blocking mods, crashes). Python
  deleted in v9.
- **One v8.0.0 release**, built on branch `v8`, released once at parity.

Outcome: Navigator works the same or better on CC ≥ 2.1.287 with no Python on the hook hot
path, ships the pane/band/theme to everyone, and degrades to v7 behaviour everywhere else.

## Facts from research that shape the design

- `session.start` does **not** fire after `/clear`/`/resume`; re-injection belongs on
  `classic.SessionStart`.
- Classic results have **no `systemMessage`** → `config_guard`/`setup` move to `$.ui.toast`.
- `agent.spawn` cannot inject context; `classic.SubagentStart` reads `additionalContext`.
- Core tool results carry `isReadOnly` → stop_completion can count real mutations (fixes the
  mem-077 read-only over-fire without a Bash classifier).
- A hook's 10 s limit excludes time inside `next()` and `$` calls → compact_marker's 25 s
  budget is fine via `$.process.run`.
- No `$.fs.rename` (no atomic write); `$.env.get` takes literal names only (judge's
  configurable `api_key_env` unsupported in the mod).
- Runtime uses only part of `scoring.py` (detect_workflow, LOOP_TRIGGERS, score_ambiguity):
  ~800 of 1348 LOC to port.
- `.agent/.nav-runtime-state.json` has external readers (nav-stats skill, claude_updater,
  gate remedy text) → project-scoped sections stay in that file.
- Stray non-kit tests would be picked up by `claude plugin test .`:
  `src/utils/__tests__/logger.test.ts`, `skills/frontend-component/templates/test-template.test.tsx`.
- CI runs Python only (`make test`); nothing runs the mod tests today.

## Target architecture

```
.claude-plugin/plugin.json   classic hooks stay inline (unchanged) + "types", "experimental.themes"
hooks/hooks.json             {"modules": ["./mod/register.tsx"]}      (auto-discovered, proven in spike)
types/index.d.ts             PluginState['navigator'] (spike contract, renamed)
themes/pilot.json            moved from mods/nav-status/themes
hooks/mod/
  register.tsx               wiring only: event → runner(event, ops) + ui (band, /nav pane)
  owns.ts                    OWNED op names, CC version gate, sets NAVIGATOR_MOD_OWNS
  runner.ts                  phases gates>responders>injectors>recorders, gate short-circuit,
                             Pilot belt, per-op try/catch, circuit breaker (3 crashes → hand to Python)
  ops/<op>.ts                one per Python op, run(ctx) => OpResult | null (Python dict contract)
  lib/config.ts              DEFAULTS<shared<local; isPilotExecutor() = sole PILOT_EXECUTOR read
  lib/*.gen.ts               config defaults + scoring tables generated from Python (source of truth until v9)
  lib/scoring.ts judge.ts state.ts sentinels.ts budget.ts py.ts ($.process.run of skill scripts)
  ui/                        spike's adhd.ts, status.ts, nav.ts, ui.ts
  tests/*.test.ts, tests/fixtures/*.gen.ts
```

- **Handoff, one policy point each side**: tokens are op names (`'adhd'` → `'prompt_adhd'`).
  `runtime._dispatch` skips owned ops next to `_config_allows`, and fast-exits before config
  load/state lock when every op of the event is owned. The per-op check in `prompt_adhd.py:63`
  goes away. The mod sets the env in `session.start` and again at the top of
  `classic.SessionStart` before `next(e)` (modules run before settings hooks).
- **Version gate**: CC < 2.1.287 → mod owns nothing, all hooks pass through.
- **Pilot**: `runner.ts` strips `drop`/`deny`/`block` under `PILOT_EXECUTOR` (port of
  `runtime._suppress_blocking`); grep test keeps the literal in `lib/config.ts` only.
- **Classic chain rule**: always `const r = await next(e)` then merge; never short-circuit
  (user's own settings hooks run beneath).
- **State**: session-scoped sections (session, turn, reads, completion, brief, jit) and UI →
  `$.state` via default-merging readers (mem-080). Project sections (tier1, judge, profile,
  compact) → `.agent/.nav-runtime-state.json` schema 2, `meta.writer: "mod"`, written only on
  change. `$.store` only for plugin-global prefs.

## Per-op mapping

| Op | Mod event | Result | Change vs v7 |
|---|---|---|---|
| session_start | classic.SessionStart | `{...r, additionalContext}` | same text (golden parity); health line → toast |
| prompt_gate | prompt.submit (gate) | context, or `{drop}` | remedy text no longer says "edit state file"; plugin-origin prompts skipped |
| prompt_tier1 | prompt.submit (responder) | `{drop: answer}` | — (off by default) |
| prompt_adhd | prompt.submit (responder) | as spike | token rename |
| prompt_brief | prompt.submit (injector) | context | judge via lib/judge.ts |
| read_guard | tool.call Read | `{deny}` at 5, warn as context at 3 | warn now reaches the model |
| jit_memory, graph_sync, profile_sync | tool.call Edit/Write/MultiEdit/NotebookEdit (+ classic.TaskCreated/Completed) | pass-through / context | scripts via $.process.run |
| stop_completion + stop_state | one classic.Stop hook, gate then recorder | `{...r, block}` once | mutation from `isReadOnly` (mem-077 fix); reads `e.last_assistant_message`, no transcript scraping |
| compact_marker | classic.PreCompact / PostCompact | pass-through | not `session.compact` (fires on precompute) |
| subagent_context | classic.SubagentStart | additionalContext | — (off) |
| failure_diagnosis | classic.PostToolUseFailure | additionalContext | — (off) |
| config_guard, setup | classic.ConfigChange / Setup | pass-through + toast | systemMessage → toast |

## Scoring and judge parity

- Port only the runtime-used scoring functions; tables generated into `scoring-data.gen.ts`.
- `tests/golden/record_mod_parity.py` runs Python on a corpus (judge_eval 60 prompts, real-session
  set, golden payloads, op unit-test prompts, ~500 mutations: case, punctuation, unicode,
  sentinels, trigger echo) and writes `hooks/mod/tests/fixtures/*.gen.ts`; `--check` in CI.
- Kit tests assert deep equality for scorecards and per-op results (context/drop/deny/block).
- Use explicit ASCII regex classes (Python `\b`/`\w` ≠ JS).
- Judge: TypeSafe client on `$.http.fetch` with recorded request/response parity;
  `TYPESAFE_API_KEY` + `~/.config/typesafe/api_key` only. `judge.provider: "claude"`
  (`$.model.classify`) as an off-by-default experiment, evaluated on the real-session sheet.

## Work breakdown (branch `v8`; every step keeps `make test` + mod CI green)

| # | Step | Size |
|---|---|---|
| 0 | Baseline: `claude plugin validate --strict .` on main; conformance `cc-2.1.287.json`; mod probes M1–M7 (incl. `modules` key on CC 2.1.241, `{block}` forces exactly one continuation, `disableAllHooks` honoured, mods under `-p`) | M |
| 1 | Move mod into the plugin per layout; rename state to `navigator`; `$.plugin.root` paths; gitignore root `.claude-plugin/types/`; delete `mods/`; move stray tests; CI `mod` job pinned to CC 2.1.287 (`validate --strict`, `plugin test`); `make mod-test`, `make test-all` | M |
| 2 | Python: op-name tokens, skip in one place, fast-exit; tests incl. golden "all owned → empty output, no state write"; extend guard test | S |
| 3 | TS foundation: runner, owns, config(+gen), state, sentinels, budget, py; kit tests for Pilot belt, breaker, version gate, default-merging | M |
| 4 | Scoring + judge port with parity generator and `--check` | L |
| 5a | prompt.submit group: gate, tier1, adhd, brief (add to OWNED with their parity tests) | L |
| 5b | tool.call group: read_guard, jit_memory, graph_sync, profile_sync; failure_diagnosis | M |
| 5c | classic.Stop pair with `isReadOnly` mutation tracking | M |
| 5d | Lifecycle: session_start, compact_marker, subagent_context, config_guard, setup, Task events | M |
| 6 | Release tooling: validator checks hooks.json module exists, every OWNED op is in `registry.EVENT_OPS` with an `ops/<name>.ts`, optional `claude plugin validate`; release.yml mod job | S |
| 7 | Delete v6 shims (`scoring.v6_exports` :25/:726/:1340-1348 and the skills/*/functions re-export files + their tests) | S |
| 8 | TASK-81: mod checks latest GitHub release via `$.http.fetch` and toasts the update command; Python keeps `--check-drift`; fix self-update claims in docs | S |
| 9 | Docs: CLAUDE.md "Navigator Runtime (v8)" table (op → mod event → Python fallback, min CC 2.1.287); DEVELOPMENT-README; system/project-architecture + plugin-patterns; nav-sync-claude template; docs site sync; `RELEASE-NOTES-v8.0.0.md` with behaviour changes | M |
| 10 | Dogfood (below), bump to 8.0.0 via `scripts/bump-version.sh`, tag, CI release | M |

Task doc: `.agent/tasks/TASK-84-v8-mod-runtime.md` created in step 0 from this plan.

## Verification

1. `make test`: goldens byte-identical with the env unset; all-owned dispatch prints nothing and
   writes no state.
2. `claude plugin validate --strict .`, `claude plugin test .`, `record_mod_parity.py --check`.
3. Headless matrix `claude -p --plugin-dir .` × {mod loaded, not} × {PILOT_EXECUTOR unset, set}:
   loop-trigger prompt, ambiguous prompt, 6 Reads, task-doc edit, `/compact`, a subagent.
   Assert from stream-json + `.agent`: graph updated, marker written, state schema 2; under
   Pilot no drop/deny/block; WORKFLOW CHECK, NAV-BRIEF and the session doc each exactly once.
4. Interactive dogfood: startup inject once; `/clear`/`/resume` re-inject; `/compact` marker;
   ADHD toggle; `/nav` pane; loop-trigger drop; read deny at 5; stop_completion with loop mode,
   read-only turn no longer over-fires; subagent context; config-change toast; hot reload.
5. Fallback proofs: v8 plugin on CC 2.1.241 → Python does everything; `allowManagedModsOnly`
   → env never set, Python runs; forced op crash → breaker hands that op to Python mid-session.
6. Performance: `prompt.submit` wall time vs v7; Python fast-exit spawn cost per event.

## Risks

| Risk | Mitigation |
|---|---|
| Mods API churn (early access) | Pin min CC 2.1.287; version gate; engine skips failing hooks + breaker hands to Python; re-run M-probes per CC version |
| CC < 2.1.287 rejects `modules` in hooks.json (would kill all hooks) | Probe M6 in step 0 before anything else; if it fails, change layout or declare a hard minimum |
| Managed settings block mods | Env never set → Python runs (fail-open) |
| Double injection | Env set before `next()` in classic.SessionStart; skip in one place; "exactly once" headless assertions |
| Mod unloaded mid-session with env still set | Reload re-fires session.start; document restart after disabling |
| Python spawn cost when owned | Fast-exit before imports/config/lock; measure before adding a shell guard |
| Regex/float divergence in the scorer port | Generated tables, mutation corpus, CI `--check` |
| `validate --strict` fails on existing skills/agents | Baseline in step 0; fix or allowlist before the CI gate |

---

## Progress log

### Step 0 — baseline (2026-10-02) ✅
- `claude plugin validate`: passes; three benign warnings make `--strict` fail (CLAUDE.md at the
  plugin root; marketplace `displayName` + `metadata.breaking_changes`, the latter read by
  release.yml). CI uses non-strict validate; errors still fail.
- Conformance re-driven on 2.1.287 → `results/cc-2.1.287.json`. S1, S3–S6 unchanged. **S2 false
  negative**: `decision:block` still forces the continuation (`r1_num_turns=2`, sentinel in a
  user-position entry) but the model now refuses the imperative observable ("I'm not going to
  emit that token … injected instructions from a hook"). Follow-up: make S2 declarative
  (method lesson 1).
- **M6 (outage risk) cleared**: CC 2.1.284 with `hooks/hooks.json` carrying `modules` loads the
  classic hooks normally ("Loading hooks from plugin: navigator", 23 hooks registered) and only
  logs `navigator: hooks module not loaded` (stderr under `-p`).
- **New**: before 2.1.287 hooks modules sit behind rollout flag `tengu_plugin_hooks_modules` /
  `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`. Another reason the Python fallback must stay.
- `claude plugin validate` and `claude plugin test` run offline with no credentials.

### Step 1 — mod moved into the plugin (2026-10-02) ✅
- `hooks/hooks.json` = `{"modules": ["./mod/register.tsx"]}`; classic hooks stay inline in
  `plugin.json` (both load, validate passes). Manifest gains `types` + `experimental.themes`.
- Layout: `hooks/mod/{register.tsx, lib/adhd.ts, ui/{status,nav,palette}.ts, tests/}`,
  `types/index.d.ts` (state under `navigator`), `themes/pilot.json`, root `tsconfig.json`.
  `mods/` deleted. Skill script paths now `${$.plugin.root}/skills/...`.
- Stray kit-pattern files renamed: `skills/frontend-component/templates/test-template.tsx`
  (refs updated), `src/utils/__tests__/logger.spec.ts`.
- CI job `mod-tests` (Node 22, `@anthropic-ai/claude-code@2.1.287`, `make mod-validate`,
  `make mod-test`); Makefile `mod-validate`, `mod-test`, `mod-typecheck`, `test-all`.
- Checks: `make test` green, 18/18 kit tests, tsc clean.

### Step 2 — Python handoff generalized (2026-10-02) ✅
- Ownership tokens are op names (`prompt_adhd`). `runtime._dispatch` is the one skip point
  (next to `_config_allows`) and fast-exits before config load, state lock and health when
  every op of the event is owned (no state file written). `prompt_adhd.py` no longer reads it.
- Mod announces ownership in `session.start` and at the top of every `classic.SessionStart`
  (before `next`, so the Python SessionStart child already sees it).
- Tests: `ModOwnershipTest` (skip, fast-exit no state write, unset runs all); dispatcher-level
  `HandoffTest` (owned → no ADHD block, unowned → block); kit test (n). make test green, 19/19.

### Step 3 — TS foundation (2026-10-02) ✅
- **Architecture constraint found**: the engine's static scan follows `$` only into functions
  declared in the hooks module itself, never across an import ("$ is passed to announce,
  imported from ./owns"). So `register.tsx` builds an `Io` port (`ioOf($)`, each method a direct
  `$.noun.method` call) and imported modules (lib/, ops/, owns, runner) take `io`. `validate`
  still lists every API call ("via ioOf"). State atoms used by the breaker live in register.tsx.
- Files: `hooks/mod/lib/{types,config,sentinels,budget,project,context,adhd}.ts`,
  `hooks/mod/{owns,runner}.ts`, `hooks/mod/ops/{index,prompt_adhd}.ts`.
- `scripts/gen_mod_data.py` generates `lib/gen/config-defaults.gen.ts`, `lib/gen/sentinels.gen.ts`
  and `tests/fixtures/foundation.gen.ts` (strip/clamp parity) from Python; `--check` in CI
  (`make mod-gen-check`).
- Runner mirrors `_dispatch`: phase order, gate short-circuit, Pilot belt, registry-order merge,
  per-op crash isolation, breaker at 3 crashes → `disown` + re-announce (Python takes over).
  Version gate: CC < 2.1.287 owns nothing.
- `prompt_adhd` runs through the runner; ops run only inside a Navigator project (v7 parity —
  the spike injected ADHD everywhere).
- Guard: `ModPilotPolicyPointTest` keeps `PILOT_EXECUTOR` to register.tsx (io read),
  lib/config.ts (decision), lib/types.ts.
- Checks: 32/32 kit tests (stripAll + clamp byte parity), tsc clean, make test green.

### Step 4 — scoring + judge port (2026-10-02) ✅
- `hooks/mod/lib/scoring.ts`: contains_phrase, loop triggers, additive complexity,
  detect_workflow + judge overlay, ambiguity heuristic + judged blend. Tables generated
  (`lib/gen/scoring-data.gen.ts`).
- Regex trap handled: Python `\b \w \d \s` are Unicode-aware, JS `\b` is ASCII-only even
  with `u`. Word class `[\p{L}\p{N}_]` and an exact `\b` emulation via lookarounds; `\p{Nd}`
  for digits; `\-` is a syntax error in `u` mode outside classes (not escaped).
- Parity corpus (`tests/fixtures/scoring.gen.ts`): judge_eval.json prompts, prompts mined from
  the Python test files, hand cases (unicode, sentinels, trigger echo), × 6 mutations → 852
  prompts; detect_workflow and score_ambiguity match byte for byte. The private
  judge_eval_real.json is deliberately not used (gitignored data).
- `hooks/mod/lib/judge.ts`: settings, redact, build_request, parse_response → Judgment, key from
  `TYPESAFE_API_KEY` or `~/.config/typesafe/api_key`, POST via `$.http.fetch` raced against
  `$.clock.sleep` (fetch has no timeout). Custom `api_key_env` unsupported in the mod (literal
  env names only). Parity on the 60 recorded responses: request, verdicts, judged scoring.
- 44/44 kit tests, tsc clean, gen --check clean, make test green.

### Step 5a — prompt-time ops in the mod (2026-10-02) ✅
- **Plan change: state stays in the shared schema-2 file.** `lib/state.ts` ports
  `state.load/save`; mod and Python read/write `.agent/.nav-runtime-state.json`, so an op handed
  across (breaker, older CC, partial ownership) sees the same state. No flock in the mod: events
  are sequential (modules run before settings hooks). `$.state` stays UI-only.
- Owned: `prompt_gate`, `prompt_tier1`, `prompt_adhd`, `prompt_brief` (registry order). Python's
  UserPromptSubmit dispatch now fast-exits (every op owned).
- Parity (all byte-identical, judge off, no graph): 3,600 gate/brief cases over three config
  variants × three prior check states; 168 tier-1 cases incl. telemetry state written.
- Kit limits learned: imports over 1 MiB are refused (fixtures compact + split per variant);
  `as const` on huge literals blows up tsc (explicit row types for big fixtures).
- Note for the release step: `tests/fixtures/tier1.gen.ts` embeds the plugin version, so the
  version bump must re-run `scripts/gen_mod_data.py`.
- Headless check with the mod loaded: a "Run until done" prompt yields exactly one WORKFLOW CHECK
  (**correction**: the comparison run with `CLAUDE_CODE_DISABLE_FUNCTION_HOOKS=1` was NOT Python-only —
  neither that variable nor `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=0` disables mods on 2.1.287; the real
  fallback leg is the 2.1.284 binary, see step 10); Bash sees
  `NAVIGATOR_MOD_OWNS=prompt_gate,prompt_tier1,prompt_adhd,prompt_brief`.
- CLI gotcha: `--debug` takes an optional filter, so `claude -p --debug "<prompt>"` swallows the
  prompt. Put the prompt first: `claude -p "<prompt>" --debug`.
- `scripts/gen_mod_data.py` now also loads `scripts/mod_fixtures/*.py` (each exports TARGETS), so
  op groups add fixture builders without editing the generator.

### Step 7 — v6 shims deleted (2026-10-02) ✅ (done early, in parallel with forks 5b–5d)
- `scoring.v6_exports` / `_V6_EXPORTS` and `V6ExportsTest` removed.
- Deleted `skills/nav-start/functions/workflow_detector.py`, `skills/nav-brief/functions/ambiguity_scorer.py`
  (no remaining caller); their test suites now import `scoring` directly with unchanged assertions.
- `skills/nav-workflow/functions/{complexity_detector,skill_detector}.py` are still run by the
  nav-workflow skill, so they stay as explicit thin CLIs importing scoring by name (no v6_exports).
- `.claude/worktrees/` git-ignored (agent worktrees live inside the repo).

### Step 6 — release tooling (2026-10-02) ✅
- `release_validator.py --verify-mod`: one hooks module declared and present; every `OWNED` op is
  in `registry.py` (Python fallback exists) and has `hooks/mod/ops/<name>.ts`; `gen_mod_data.py
  --check` clean. 5 unit tests incl. one against the real repo.
- release.yml: `--verify-mod` in validate; new `validate-mod` job (CC 2.1.287, `make mod-validate`,
  `make mod-test`); `release` needs both.
- `scripts/bump-version.sh` regenerates mod data (tier1 fixture embeds the plugin version).

### Step 8 — TASK-81 update notice in the mod (2026-10-02) ✅ (point 1 of TASK-81)
- `hooks/mod/lib/update.ts` + `checkForUpdate` in register.tsx (session.start): running version from
  the mod's own manifest (no `claude plugin list` in a hook); latest stable from the GitHub
  releases API raced against a 4 s sleep; throttled by `auto_update.check_interval_hours` via
  `$.store`; no network under Pilot; read-only toast "Navigator X installed · Y available · run:
  claude plugin update navigator@navigator-marketplace". `auto_update` accepted as bool or block.
- Remaining TASK-81 points (skill Step 1.5 single script call, docs honesty) → step 9.
- To reconcile at 5d integration: the ported session_start `auto_update` context section
  (Python `--check-drift`) vs this toast — keep one.

### Steps 5b + 5c — tool-call and Stop ops (2026-10-02) ✅ (parallel forks, merged a2dc3d6, 16dfa2c)
- 5b: read_guard, jit_memory, graph_sync, profile_sync, failure_diagnosis — ~560 replayed cases
  (read sequences, edit/lifecycle payloads with sync argv, failure payloads) byte-identical.
- 5c: stop_completion (exit_gate inlined, pure-JS SHA-256 for the tree digest) + stop_state —
  1,008 + 1,080 cases over 36 transcripts, config/prior-state variants, real and faked git.
- Wiring (b131992): Read → read_guard before `next` (deny) and its warn after as context;
  Edit/Write/NotebookEdit → PostToolUse ops after a successful call; classic.TaskCreated /
  TaskCompleted → graph_sync; classic.PostToolUseFailure → failure_diagnosis; classic.Stop →
  [stop_completion, stop_state], `{...r, block}`. `OpResult.ack`, `Merged.notes` added.
  `MultiEdit` is not a tool on CC 2.1.287 (matcher drops it). 11 ops owned.
- **Live probe**: headless mutating turn with the mod owning the Stop pair → stop_completion's
  `{block}` on classic.Stop forced the continuation (num_turns=3, the model answered with the
  exit signal). The mod's Stop block works like v7's decision:block.
- Follow-ups kept out of parity: isReadOnly mutation tracking (mem-077 fix) and preferring
  `e.last_assistant_message` — need their own fixtures; candidates for v8.1.

### Step 5d — lifecycle ops (2026-10-02) ✅ (fork, merged 1bde46c)
- session_start (v6 golden reproduces byte for byte), compact_marker (Pre/Post), subagent_context,
  config_guard, setup — 75 recorded scenarios at parity. Python string/JSON/float semantics in
  `lib/life-py.ts`; health surfacing in `lib/life-health.ts`.
- Wiring: classic.SessionStart announces ownership before `next`, then runs session_start with the
  health line leading the clamped context (runtime._surface_health parity); PreCompact/PostCompact
  pass-through; SubagentStart/Setup add `additionalContext`; ConfigChange/Setup `system_message`
  → `$.ui.toast`. Io: `stat`, `localOffsetMinutes`.
- **All 16 registry ops are owned by the mod.** `test_real_repo_mod_owns_every_registry_op` locks it.
- Parity fixes found on the way: `clamp` counts code points like Python (astral fixtures added);
  crash bookkeeping mirrors `_handle_op_crash` (class name only, ISO ts, health file).
- 82 kit tests, 10 files.

### Step 10 (automated part) — verification matrix (2026-10-02) ✅
| Leg | Ownership seen by Bash | WORKFLOW CHECK | session doc | ADHD block |
|---|---|---|---|---|
| CC 2.1.287, mod loaded | all 16 ops | 1 | 1 | 1 |
| CC 2.1.284 (mods rollout-gated off) = Python fallback | `[]` | 1 | 2* | 1 |
| CC 2.1.287 + `PILOT_EXECUTOR=1` | all 16 | 0 | — | 0 (toggle phrase reaches the model, 1 turn) |
\* the second copy is the personal `.claude/settings.local.json` dogfood hooks (working-tree
dispatcher for SessionStart/Read/Stop on top of the plugin's hooks). With the mod they fast-exit;
on the fallback both inject. Local setup, not a product issue (it also explains the doubled
session block in v7 dogfood sessions).
- Toggle phrase without Pilot: dropped with **0 model turns**. Stop block forces one continuation
  (num_turns=3 probe, step 5c).
- Latency, prompt path (judge on, memory recall on): mod `prompt.submit` 200 ms vs Python dispatcher
  median 407 ms (spawn incl.). A fully owned Python hook still costs ~38 ms per event (spawn +
  fast exit); a shell-level guard could remove it later (would extend the single-policy guard).
- Shell gotcha: `ls` is aliased to `eza` on this machine, so `ls -t` does not sort by time; use
  `/bin/ls -t` to find the newest debug log.

### Left before release (needs the user)
1. Interactive dogfood: `/clear` and `/resume` re-inject once; `/compact` writes a marker; `/nav`;
   hot reload mid-session; a subagent gets context; config-change toast; `/theme` → Pilot.
2. Go-ahead for the outward steps: merge `v8` → `main`, `scripts/bump-version.sh 8.0.0`, CHANGELOG,
   tag push (CI publishes the release), docs-site sync + `vercel --prod`.
3. Optional: drop the `.claude/settings.local.json` dogfood hooks (redundant with the plugin).

### Route view (2026-10-02, after Threads feedback) ✅
Navigator as a car navigator: **destination** (a goal Claude states in a brief, else the active
task), **route** (the active task's `- [ ]` checklist, else research → impl → verify → complete;
the current waypoint is a dot, no "you are here"), **next** + time on the waypoint, **fuel
(context)** with turns left and a compact nudge, **saved**, **on this route** memories, tasks
behind `t`. **Off route**: two consecutive substantive prompts (4+ content words) sharing no word
stem with the destination open a warning panel with park (writes a `📋 Parked` task stub) / back /
switch. Band is one quiet dim line: `→ destination · waypoint`, `⚠ off route · /nav`, or nothing.
UI-only change: ops, parity and the Python fallback untouched. 92 kit tests (pure route model +
pane/band integration). Files: `hooks/mod/ui/route.ts`, register.tsx pane/band.

### Route steps replace "on this route" memories (2026-10-02, dogfood feedback) ✅
Memories in the pane read as a list of decisions, not a way to the goal, and TASK-84 itself showed
the generic phases because it has no `- [ ]` checklist. The route panel now lists the steps one
per line (`✓ 12 done · last: …`, `● 9   Docs …`, `○ 10  Dogfood …`, `+ n more`, title
`route · 13/14`). Steps come from `parseSteps`: checklist first, else the numbered table rows or
list items of the first plan section (`## Work breakdown` / `implementation` / `plan` / `steps` /
`phases`), done by ✅, ~~strike~~, or a `### Step n — … ✅` progress heading (a parenthetical after
the number, `Step 10 (automated part)`, is partial). Labels drop markup, parentheticals and
`; details`, capped at 60 for the band. Removed: the memories panel, ▸ pinning, the per-prompt
concept recall (one `memory_recall.py` spawn per refresh and per prompt); prompt-time memory
injection by the ops is unchanged. 94 kit tests.
Follow-up: the whole route is listed, not a fold — passed steps gray (`dim`), current in the
accent and bold, steps ahead light (`label`); routes over 16 lines keep the last passed step and
fold the earlier ones (`✓ n earlier`), cutting the tail as `+ n more`. Colors asserted in (s2).
Pane order: fuel (context) + saved on top, then destination (or off route), route, tasks.

### Band format (e0b416a)
`on route: Ship v8 · ● verify 3/5 · next: run headless matrix` · `low fuel: … · compact after this
waypoint` · `off route: <topic> · /nav to park or go back` · empty otherwise. The next-action
fallback skips table rows and intent-brief fields.

---

## ▶ Resume here (next session)

1. **Restart the dogfood terminal from the repo root**: `claude --plugin-dir "$PWD"` (plugin name
   `navigator`). Sessions started on the old `mods/nav-status` path keep the deleted spike in
   memory and never reload.
2. **Dogfood checklist**: `/nav` route view (destination, route dot, off-route after 2 detour prompts,
   park/back/switch), band states, `/clear` + `/resume` re-inject once, `/compact` writes a marker,
   a subagent gets context, a config edit toasts, `/theme` → Pilot, hot reload mid-session.
3. **Release (needs explicit go-ahead)**: merge `v8` → `main`; `scripts/bump-version.sh 8.0.0`
   (regenerates mod data); CHANGELOG entry; set the date in `releases/RELEASE-NOTES-v8.0.0.md` and
   add the route view to it; tag `v8.0.0` + push (CI `validate` + `validate-mod` + publish); docs site
   sync + `vercel --prod` from the site dir (no git remote).
4. **8.1 candidates**: isReadOnly mutation tracking in stop_completion (mem-077 over-fire),
   prefer `last_assistant_message` in stop_state, band reason when Navigator intervenes, shell-level
   fast-exit guard (~38 ms Python spawn per owned event), `$.model.classify` judge experiment.
5. Optional: remove the personal `.claude/settings.local.json` dogfood hooks (double session doc on
   the Python fallback).
