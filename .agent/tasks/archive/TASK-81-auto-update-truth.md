# TASK-81: Auto-update — make the session-start check real, and the docs honest

**Status**: ✅ Released — v8.1.2, 2026-10-05 (the read-only notice itself since v8.0.0)

## Context

`auto_update.enabled` has shipped `true` since v5.5.0 and CLAUDE.md said "on session start,
Navigator checks for a newer plugin version and updates". In v7 that is false:

- `hooks/ops/session_start.py::_section_auto_update` runs `auto_updater.py --check-drift`
  only — read-only by design ("never mutating").
- The mutating path (`auto_update()` → `claude plugin marketplace update` +
  `claude plugin update`) is Step 1.5 of `skills/nav-start/SKILL.md`: a bash block the
  model must execute. Pilot's 2026-09-02 transcript shows the model echoing the template
  ("Auto-updated Navigator to v$NEW_VERSION") instead of running it.
- The drift line itself was wrong on 2026-09-06/09 ("behind plugin (v7.0.0)" while 7.2.0+
  was installed): `get_current_version()` parses `claude plugin list` from inside a hook.
- Result: Pilot ran 7.5.0 from 2026-09-13 until a manual `claude plugin update` on
  2026-09-19, through three releases, with auto-update "enabled".

**Contradiction**: updating from inside a hook improves freshness and worsens safety
(spawning the Claude CLI inside Claude Code, 10 s SessionStart budget, plugin cache in
use). Resolution: keep the hook read-only but make it *truthful and actionable*; keep
the mutating step in the skill but make it a single script call the model cannot
paraphrase; stop claiming self-update in docs unless an explicit in-hook switch is added.

## Plan

1. **session_start**: real check. Latest release from the GitHub releases API (4 s
   timeout, fail silent), installed version read from the plugin cache on disk
   (`get_installed_plugin_version`, highest version dir) — never from `claude plugin list`
   inside a hook. Emit one line: `Navigator 7.7.0 installed · 7.7.1 available · run:
   claude plugin update navigator@navigator-marketplace`. Respect `check_interval_hours`
   via a timestamp in runtime state so the network call is at most hourly. Under
   `PILOT_EXECUTOR`: no network.
2. **nav-start skill Step 1.5**: replace the bash block with one call
   (`auto_updater.py --apply --json`) whose parsed `status` drives the displayed lines;
   the skill text stops carrying `$NEW_VERSION` templates.
3. **Docs**: CLAUDE.md Auto-Update section, docs site `configuration/auto-update.mdx`,
   nav-upgrade/nav-start skill docs: "notifies on session start; updates when you run the
   command or say 'start my session'". If a future `auto_update.in_hook: true` switch is
   added, its risks are stated next to it.
4. **Tests**: session_start section with a fake release doc (newer / same / network
   error / interval not elapsed); version read from a fake cache tree; no subprocess to
   `claude` from the hook path (grep guard like the stderr one).

## Verify

- Fresh session in a project with an older installed plugin shows the one-line notice.
- `--verify-hooks` unchanged; SessionStart stays inside 10 s with the network call timing
  out.
- After a release: notice appears within `check_interval_hours` without any manual step.

Size: ~half a day.


## Progress (2026-10-02, branch v8)

- Point 1 → done in the v8 mod instead of the Python session_start op: `hooks/mod/lib/update.ts`,
  running version from the mod's own manifest, GitHub releases API with a 4 s race, interval via
  `$.store`, no network under Pilot, read-only toast. Python fallback keeps `--check-drift`.
- Point 2 → done: nav-start Step 1.5 is one `auto_updater.py` call whose JSON fields the model
  reports verbatim; the `$NEW_VERSION` template is gone.
- Point 3 (docs honesty) → TASK-84 step 9.

## Research + plan (2026-10-05, loop mode)

Research (navigator-research agent + direct reads) found three leftovers:

1. **Point 1 residual.** Both session-start ops run `auto_updater.py --check-drift`, whose
   `detect_version_drift` called `get_current_version()` → `claude plugin list` (10 s
   subprocess inside a 4 s hook budget). That is the 2026-09-06/09 wrong-drift-line source,
   still reachable from the hook on v8.1.1. Fix: `get_running_plugin_version()` (the
   script's own `.claude-plugin/plugin.json`), then the cache tree; the CLI is only used by
   the skill-side `auto_update()`.
2. **Point 3 docs.** Plugin repo: `nav-features` SKILL + `feature_manager.py` ("auto-updates
   on session start", "updates silently"), `nav-upgrade` SKILL ("opt-in", under Future),
   `nav-sync-claude` SKILL, `DEVELOPMENT-README` index. Docs site: `configuration/auto-update.mdx`
   body contradicts its own v8 callout (60 s timeout, reinstall fallback, "Auto-updated"
   transcript, "disabled still notifies" — false: disabled means no notice); `configuration/
   index.mdx`, `reference/nav-config-schema.mdx` (`last_check` is the skill's key, the mod
   stores `update_checked_at` / `update_latest` in `$.store`), `reference/plugin-ops.mdx`,
   `reference/migration.mdx`, `reference/troubleshooting.mdx`, `skills/nav-start.mdx`.
   `templates/CLAUDE.md` and `README.md` carry no claim. CLAUDE.md is already right.
3. **Point 4 tests.** Mod had newer / same / throttled / Pilot. Added: fetch failure leaves no
   notice and no `update_checked_at` (so the next start retries), manifest absent → no notice,
   `enabled: false` → no fetch, and no `process.run` of the Claude CLI from session start.
   Python: drift resolves from the manifest, then the cache, with `subprocess.run` patched to
   fail — the behavioral form of the "no `claude` from the hook path" guard.

Execution order: code + tests → plugin docs → site docs → `make test` + mod tests → site
build + deploy → archive + marker. The plugin change ships with the next release.

## Closed 2026-10-05

Shipped in this task: hook-safe drift check (`get_running_plugin_version` first, cache second,
CLI never), five new mod tests + five Python tests, plugin docs and the docs site rewritten to
"notifies on session start, never self-updates", golden fixture excludes the version-dependent
drift section (`tests/golden/README.md`, deviations).

Follow-ups, out of scope here:
- ~~The mod's release fetch has no `curl` fallback when `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`
  refuses `$.http.fetch` (the judge got one in TASK-84); on such machines the notice never fires.~~
  Done in TASK-98 (2026-10-07): opt-in `auto_update.curl_fallback`.
- The skill-side `auto_update()` still reads the current version via `claude plugin list`. Fine
  outside a hook; could reuse the manifest reader for one less subprocess.
