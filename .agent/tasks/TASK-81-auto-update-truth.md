# TASK-81: Auto-update — make the session-start check real, and the docs honest

**Status**: 📐 Plan — 2026-09-23 (not started)

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
