# TASK-97: One plugin-root resolver for skills

**Status**: ✅ Implemented — 2026-10-07 (option A, hook-written file + two-line snippet; released in v8.3.3)

## Origin

Two `CLAUDE_PLUGIN_ROOT` fallbacks coexist:

| Fallback | Uses | Where | Exists? |
|---|---|---|---|
| `$HOME/.claude/plugins/cache/navigator-marketplace/navigator` | 60 | 15 `SKILL.md` files | The directory exists but holds only version folders (`8.3.1/`, `8.3.2/`); `skills/` is one level deeper. The `[ -d ] \|\|` second line never fires because the directory is there. |
| `$HOME/.claude/plugins/marketplaces/navigator-marketplace` | 18 | `plugin.json` hooks, `nav-start` Step 1.5, `docs/DEPLOYMENT.md` | On GitHub installs: yes (marketplace source `"./"`, so the clone root is the plugin root). On this machine: no (the marketplace is a local directory source). |

Two facts decide the fix:

1. **`CLAUDE_PLUGIN_ROOT` is set for hook commands and unset in the Bash tool.** Hooks
   never need the fallback; every skill command always does.
2. **The cache path is versioned.** Any flat cache fallback is wrong for every install.
   Fallback A has therefore been broken since the cache layout changed; skills work only
   because the model is told "Base directory for this skill: …" and sometimes substitutes it.

## Change

**A. The hook publishes the root; skills read it.** The session_start op (both runtimes) knows
the real root (`CLAUDE_PLUGIN_ROOT` in Python, `ctx.io.pluginRoot` in the mod) and writes it
to `~/.config/navigator/plugin-root` (one line, atomic, via `personal.py` / the mod's `io.write`;
`NAVIGATOR_CONFIG_HOME` overrides). Written on every session start, so an update or a
version bump is reflected on the next start.

**B. One resolver line in every skill.** Replace both fallback forms with:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-$HOME/.config/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
```

Order: the env var (hooks, tests) → the file the hook wrote (every skill, every install
kind) → the marketplace clone (GitHub installs that never ran a session start). The repo
itself is covered: a directory-source marketplace writes the repo path into the file.

**C. A lint test pins the snippet.** `skills/nav-release/functions/test_release_validator.py`
(or a new `tests/test_skill_plugin_root.py`) asserts every `SKILL.md` that mentions
`CLAUDE_PLUGIN_ROOT` uses exactly the two lines above and nothing else, so the two forms
cannot drift apart again. `plugin.json` keeps the marketplaces fallback (hooks always get the
var; the fallback is documentation).

**D. Docs.** `.agent/system/plugin-patterns.md` and `docs/DEPLOYMENT.md` describe the three-step
order; `tests/golden/README.md` keeps its note.

## Result (2026-10-07)

Option A shipped. `session_start` (Python `_publish_plugin_root`, mod `publishPluginRoot`)
writes `<config home>/plugin-root` after the `.agent` guard on every start; a write failure
never costs the injection. The snippet honours `XDG_CONFIG_HOME` like `personal.config_home()`:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
```

60 cache-fallback pairs across 18 skills replaced, plus the four odd forms (nav-init's bare
marketplaces path, nav-start's auto_updater line, nav-upgrade's product-design `cd`,
nav-deep-research's `find` over the cache). `tests/test_skill_plugin_root.py` (new `tests`
entry in `TEST_DIRS`) pins the snippet, the guard and the shared indent, and forbids the flat
cache path. Verified with `CLAUDE_PLUGIN_ROOT` unset on this machine: the snippet resolves
the repo and lists `skills/`. Parity: lifeops case `plugin-root-published` records the write.

## Won't do

- Reading `~/.claude/plugins/installed_plugins.json` from skills: a Claude Code internal
  file; the hook already has the authoritative value for free.
- Changing the hook-side fallback in `plugin.json` (TASK-53 precedent; `--verify-hooks`
  `[unset]` failures on directory-source machines stay known and harmless).

## Verify

- Python: session_start writes the file (both the op test and a lifeops parity case with a
  recorded write); `test_skill_plugin_root` passes on all 15 skills.
- Manual: `unset CLAUDE_PLUGIN_ROOT; bash -c '<snippet>; ls "$PLUGIN_DIR/skills" | head -2'`
  prints skills on this machine and on a GitHub install.
- `make test`, `make mod-gen-check mod-test`.

## Refs

- `skills/*/SKILL.md` (15 files, 60 lines), `.claude-plugin/plugin.json` (18 hook commands)
- `hooks/ops/session_start.py`, `hooks/mod/ops/session_start.ts`, `hooks/nav_hook_lib/personal.py`
- `.claude-plugin/marketplace.json` `"source": "./"`; `~/.claude/plugins/known_marketplaces.json`
- v6.15.1 notes in `plugin.json` (the marketplaces fallback rationale)
