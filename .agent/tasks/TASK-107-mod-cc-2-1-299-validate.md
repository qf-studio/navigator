# TASK-107: Mod clean under `claude plugin validate` on Claude Code 2.1.299

**Status**: ✅ Completed — 2026-10-19; released in v8.4.5 (2026-10-20)
**Priority**: Medium
**Source**: `.agent/research/claude-code-mods-2026-10-19/findings.md` §1, §2, §6 (mem-108..113)
**Owner**: Navigator maintainers

## Problem

`claude plugin validate .` on Claude Code 2.1.299 printed 14 lines of
`gating hook without .catch` for the mod (`hooks/mod/register.tsx`), two
`Unknown field` warnings for `.claude-plugin/marketplace.json` (`displayName`,
`metadata.breaking_changes`) and advice to add a one-step install line to the README.
The verdict stayed "passed with warnings", `claude plugin test .` stayed 164/164, so nothing
was broken. The list still hid the one warning that matters (CLAUDE.md at the plugin root)
and said nothing about the policy behind the 14 hooks.

Since 2.1.290 a gating hook that throws, overruns its budget or (2.1.299 only) is asked
beneath its own `$` call is skipped and the action goes on, unless its registration carries a
`.catch`. 2.1.299 also set two new fields on `prompt.submit`: `e.command = { name, args }`
when the submission runs a slash command, and `e.isMeta` on a prompt the person did not type.

## Decision: keep fail-open, say so in code

Navigator's gating hooks fail open by design. A failed hook is skipped by the engine; the
runner counts each op crash and after three (`owns.BREAKER_LIMIT`) hands the op back to the
Python dispatcher for the rest of the session. A `.catch` that denies would turn a Navigator
bug into a blocked tool call or a dropped prompt. So the handler passes the event on.

One shared handler, `failOpen`, is the `.catch` of all 14 gating hooks:

- `next.called` true: `next(e)` replays what the hook's last call settled to; false: it runs
  the hooks beneath once. Either way the action goes on, as it did without a handler.
- The failure counts toward the breaker: `owns.noteCrash` for every op the event serves
  (`EVENT_OPS`), so three hook-level failures hand those ops to Python exactly as three op
  crashes inside the runner do. A hook with no ops (`tool.call{tool=Bash}`) counts under its
  own name, which disowns nothing.
- `re-entry` counts nothing: the engine says it is no fault, the handler's `$` calls would
  reject, and 2.1.301 stopped asking the handler for it.
- The static scan accepts only a function literal or the name of one as a `.catch` handler,
  not a call that returns one. So `failOpen` is one named function and derives the event
  from the payload (`hook_event_name` on classic events, `tool` on tool.call, prompt.submit
  otherwise) instead of taking it as an argument.
- `.catch` exists on `Registration` in the 2.1.287 types too, so the floor holds.

## Changes

1. `hooks/mod/register.tsx`
   - `failedEvent` + `failOpen`; `.catch(failOpen)` on the 14 gating hooks: classic
     SessionStart, PreCompact, PostCompact, SubagentStart, ConfigChange, Setup, TaskCreated,
     TaskCompleted, PostToolUseFailure, Stop; tool.call Read, Edit|Write|NotebookEdit, Bash;
     prompt.submit.
   - `prompt.submit` returns `next(e)` first when `e.command` is set, so the gate, brief,
     tier-1 and reply-mode ops never score a slash command line. Read as
     `(e as { command?: unknown }).command` because the engine-laid types beside the mod are
     still the 2.1.287 ones. `e.isMeta` is left alone: a meta prompt is text the model reads,
     and the ops' answer to it is the same as before this task.
2. `hooks/mod/tests/register.test.ts`: test (a3) raises `prompt.submit` with
   `command: { name: 'loop', args: ... }` on a loop-trigger line with the ADHD switch on and
   asserts no drop, no context and the text unchanged; the same line typed as a prompt gets
   the ADHD block.
3. `.claude-plugin/marketplace.json`: `displayName` and `metadata.breaking_changes` removed.
   Nothing reads them: `scripts/`, `.github/`, `skills/nav-release`, the docs site
   (`../navigator-site`) were grepped; `release.yml` mentions `breaking_changes` only in a
   comment on a branch that was removed earlier. The 58-entry changelog array lives on in git
   history and `CHANGELOG.md`. The spike harness copy under `tests/harness-conformance/`
   is not validated and was left as is.
4. `README.md`: `/plugin install navigator --marketplace qf-studio/navigator` as the first
   install line in both install blocks; the two-step form stays for older Claude Code.
5. `.github/workflows/test.yml`: the comment on `make mod-validate` names the one remaining
   baseline warning.

## Python side

The classic `UserPromptSubmit` payload carries `prompt` (and `user_message`) only, no
command field; a leading `/` is the only hint and a prompt may start with a path. The Python
ops run only where the mod does not own them (Claude Code before 2.1.287, a mod policy block,
or after the breaker), and the engines that raise `prompt.submit` with `command` are the ones
where the mod owns the ops. So the guard is mod-only. The ops themselves are unchanged in
both runtimes; parity fixtures (`make mod-gen-check`) are untouched.

## Verified 2026-10-19

- `claude plugin validate .` on 2.1.299: no `gating hook without .catch`, no marketplace
  `Unknown field`; 14 lines of `gating hook with .catch`; one warning left (CLAUDE.md root).
  On the 2.1.287 binary: `Validation passed`, no warnings.
- `env -u NAVIGATOR_MOD_OWNS make test-all`: exit 0 (Python suites, mod-gen-check,
  mod-validate, mod-test 165/165). `make mod-typecheck` green against the 2.1.287 types
  laid beside the mod.
- `claude plugin test .` on the 2.1.287 binary: 165/165 (CI pins 2.1.287).
- Graph memory mem-114 (pattern) records the shared fail-open `.catch`.

## Not in scope

- Version bump and release.
- `isMeta` handling; `$.http.fetch` policy relaxation (findings §3); UI typed colors
  (findings §4). Candidates for a later task.
- CLAUDE.md at the plugin root: validate says it is not loaded as project context; it is this
  repo's own instructions file, not shipped context, so the warning stays.
