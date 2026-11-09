# TASK-53: Correct plugin hook env var (CLAUDE_PLUGIN_DIR → CLAUDE_PLUGIN_ROOT)

**Status**: ✅ Implemented — 2026-06-08 (shipped in v6.15.7)
**Priority**: High
**Source**: Surfaced while fixing a token_monitor 404 in a downstream project; root-caused to a wrong env-var name in the plugin manifest.

---

## Context

Every Navigator lifecycle hook referenced `${CLAUDE_PLUGIN_DIR}`, which Claude Code
**has never defined**. The three documented plugin path variables are
`${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}`, `${CLAUDE_PROJECT_DIR}`
([plugins reference](https://code.claude.com/docs/en/plugins-reference#environment-variables)).

Consequence: the variable always expanded to empty, so the manifest's
`${CLAUDE_PLUGIN_DIR:-$HOME/.claude/plugins/marketplaces/navigator-marketplace}`
fallback **always fired**. Since v6.13.0 (hooks moved into the plugin manifest),
every install resolved its hooks against the marketplace checkout (tracks `main`)
rather than the installed/versioned cache dir. Invisible while `main` == release;
it broke when the published v6.15.6 manifest referenced `token_monitor.py` (retired
on `main` by wp5) — the fallback path 404'd, throwing a `PostToolUse` error on every
tool call. The v6.14.0/v6.15.1 "silent-fail" saga (`mem-036`) was chasing this
without finding the root cause. The same class of typo was fixed once before for
`CLAUDE_PROJECT_ROOT` → `CLAUDE_PROJECT_DIR` (v6.9.0) but never connected to the
plugin variable.

## Implementation

`CLAUDE_PLUGIN_DIR` → `CLAUDE_PLUGIN_ROOT` across all live runtime and guidance:

- `.claude-plugin/plugin.json` — 8 hook commands now `${CLAUDE_PLUGIN_ROOT:-…}`
  (marketplace path retained only as last-resort fallback; the primary now resolves
  to the installed version).
- `hooks/nav_session_start.py`, `nav_profile_sync.py`, `nav_task_graph_sync.py` —
  `_resolve_plugin_dir()` reads `CLAUDE_PLUGIN_ROOT` first, then `CLAUDE_PLUGIN_DIR`
  (back-compat), then the existing cache/marketplace candidates.
- `skills/nav-release/functions/release_validator.py` + its test — `--verify-hooks`
  smoke-tests under set/unset `CLAUDE_PLUGIN_ROOT`.
- ~17 skill `SKILL.md` files — bash snippets + prose.
- `skills/nav-upgrade/functions/migrate_hooks_out_of_settings.py` docstring;
  `.agent/knowledge/memories/patterns/mem-027.md` forward guidance.

Preserved (history, not bugs): CHANGELOG, prior release notes, `marketplace.json`
metadata, task postmortems, `mem-036`, `graph.json`, the v6.14.0 guard quote in
`nav-release/SKILL.md`, and the 3 hooks' `CLAUDE_PLUGIN_DIR` back-compat fallback.

## Acceptance Criteria

- [x] `release_validator --verify-hook-paths` → 8/8 resolve
- [x] `release_validator --verify-hooks` → 16/16 pass (set + unset `CLAUDE_PLUGIN_ROOT`); SessionStart emits full payload in both
- [x] `make test` green (hooks 50/50, release validator 10/10, migrate 7/7)
- [x] No live runtime/guidance reference to `CLAUDE_PLUGIN_DIR` remains; only history + intentional back-compat + legacy test fixtures
- [x] All five version files at 6.15.7

## Out of Scope

- Skill `SKILL.md` snippets run via the model's Bash tool (not a plugin subprocess)
  may not receive `CLAUDE_PLUGIN_ROOT`; their cache-base fallback (missing the
  version segment) is a separate latent issue, not addressed here.
- Rewriting historical references.

## Technical Decisions

- Kept the marketplace fallback in the manifest as defense-in-depth rather than going
  bare `${CLAUDE_PLUGIN_ROOT}` — the primary now resolves, so the fallback never fires,
  but it preserves graceful behavior if Claude Code ever omits the var.
- Kept `CLAUDE_PLUGIN_DIR` as a secondary read in the Python hooks for back-compat with
  any environment still exporting the old name.

## Verify

```bash
python3 skills/nav-release/functions/release_validator.py --verify-hook-paths
python3 skills/nav-release/functions/release_validator.py --verify-hooks
make test
```

## Done

- [x] Runtime + guidance swept, tests green, version bumped, notes + CHANGELOG written.

## Refs

- Release notes: `releases/RELEASE-NOTES-v6.15.7.md`
- Related history: `mem-036`, `releases/RELEASE-NOTES-v6.13.0.md`, `v6.14.0`, `v6.15.1`
- Docs: https://code.claude.com/docs/en/plugins-reference#environment-variables
