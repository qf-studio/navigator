# TASK-84: Navigator v8 — mod-first runtime with Python fallback

**Status**: 🚧 In Progress — branch `v8`, started 2026-10-02. One v8.0.0 release at parity.

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
  (same count as the Python-only run, `CLAUDE_CODE_DISABLE_FUNCTION_HOOKS=1`); Bash sees
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
