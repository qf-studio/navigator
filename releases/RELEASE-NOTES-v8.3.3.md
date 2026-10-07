# Navigator v8.3.3 Release Notes

**Release Date**: 2026-10-07
**Type**: Patch — one plugin-root resolver for skills (TASK-97); stop gate unknown-head read-only shapes (TASK-96)

## Fixed

- **Skill commands find the plugin again on every install kind.** `CLAUDE_PLUGIN_ROOT` is set
  for hook commands only; the Bash tool runs skill commands without it. The fallback on 60
  `SKILL.md` lines named `~/.claude/plugins/cache/navigator-marketplace/navigator`, which holds
  only version folders since the cache became versioned, so the second-line guard never fired
  and the path was wrong on every install. The session_start op (both runtimes) now writes the
  root it resolved to `~/.config/navigator/plugin-root` on every start (`NAVIGATOR_CONFIG_HOME`
  and `XDG_CONFIG_HOME` honoured, best-effort, after the `.agent` guard), and every skill
  resolves `PLUGIN_DIR` with one two-line snippet: env var → that file → the marketplace clone.
  `tests/test_skill_plugin_root.py` pins the snippet so the two forms cannot drift apart
  again. The plugin manifest's hook fallback is unchanged (hooks always get the variable).
- **A redirect target ends at the operator.** `ls 2>/dev/null; echo ok` captured `/dev/null;`
  and read as a write; the trailing `;`, `&` or `|` is now stripped before the `/dev/null`
  check.
- **Subshells, groups and functions are classified by their body.** `(cd x && git status)`,
  `{ ls; }` and `q() { ls; }` read as read-only; `(rm x)` and `q() { rm x; }` stay mutating.

## Changed

- **More read-only heads among the unknown ones.** `gh run watch`; `claude plugin
  list|validate|test|update` (`update` writes the plugin cache, never the tree;
  install/uninstall/enable/disable can rewrite a project `.claude/settings.json` and stay
  mutating); `python3 -m json.tool` (the only python form that reads); `awk` when the raw
  program holds no `>`; `make` when every target looks like `test|check|typecheck|validate`
  and none like `lint|format|build|install`. The `make` rule is the first relax-direction
  rule since TASK-71: a `make check` that formats files is caught by the tree digest on the
  next Stop. A turn that only runs the suite is therefore no longer a task action.
- Replay of a four-day window (`scripts/stop_gate_replay.py --days 4`): mutating 474 of 760
  calls before, 419 of 776 after; none of the flipped calls writes the tree.

Tests: Python +22/+22 parser cases, +4 op tests, +1 skill lint test (new `tests` entry in
`TEST_DIRS`); kit +2 direct tests, +8 stop transcripts and +1 lifeops case with every parity
fixture regenerated; 159 kit tests.
Task docs: `.agent/tasks/TASK-96-stop-gate-unknown-heads.md`,
`.agent/tasks/TASK-97-plugin-root-resolver.md`.
