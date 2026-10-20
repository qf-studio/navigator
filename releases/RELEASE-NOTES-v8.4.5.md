# Navigator v8.4.5 Release Notes

**Release Date**: 2026-10-20
**Type**: Patch — the mod is clean under `claude plugin validate` on Claude Code 2.1.299 (TASK-107)

## Changed

Claude Code 2.1.290 started to list every gating hook of a mod with or without a `.catch`
handler, and 2.1.299 set two new fields on `prompt.submit`. A research pass on 2026-10-19
compared the 2.1.299 plugin API with the 2.1.287 one Navigator was written against
(`.agent/research/claude-code-mods-2026-10-19/findings.md`). This release applies the three
findings that touch the shipped mod:

- **Gating hooks carry a fail-open `.catch`.** Since 2.1.290 a gating hook that throws or
  overruns its budget is skipped and the action goes on, unless its registration has a
  `.catch`. Navigator fails open by design, so one shared handler, `failOpen`, is the `.catch`
  of all 14 gating hooks: it passes the event on (`next(e)`) and counts the failure toward
  the runner's breaker, so three hook-level failures hand those ops to the Python dispatcher
  exactly as three op crashes do. `claude plugin validate .` on 2.1.299 now prints
  `gating hook with .catch` for each of them and no `without` line.
- **Slash commands pass `prompt.submit` unscored.** On 2.1.299 `e.command = { name, args }`
  is set when the submission runs a slash command. The mod returns `next(e)` first in that
  case, so the workflow gate, the intent brief, tier-1 answers and the reply modes never
  score a command line such as `/compact` or `/navigator:nav-start`. Kit test (a3) covers it.
  The classic `UserPromptSubmit` payload has no command field, so the Python ops are
  unchanged.
- **Manifest and README.** `.claude-plugin/marketplace.json` drops `displayName` and
  `metadata.breaking_changes`, two fields Claude Code ignores and now warns about.
  README leads both install blocks with the one-step form
  `/plugin install navigator --marketplace qf-studio/navigator` (Claude Code 2.1.275+); the
  two-step form stays for older versions.

Nothing changes for the person using Navigator: the gate, brief, reply modes, read guard and
stop gate behave as in 8.4.4. The floor stays Claude Code 2.1.287; `.catch` exists on
`Registration` there too.

Verified: `claude plugin validate .` passes with one baseline warning (CLAUDE.md at the plugin
root) on 2.1.299 and with none on 2.1.287; `make test-all` green; kit 165/165 on both
binaries; `make mod-typecheck` green.

## Upgrade

```bash
claude plugin update navigator@navigator-marketplace
```

Restart Claude Code after the update.
