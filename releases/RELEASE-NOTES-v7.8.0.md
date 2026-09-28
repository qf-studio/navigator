# Navigator v7.8.0 Release Notes — "One Repo, Many People"

**Release Date**: 2026-09-28
**Type**: Minor — team-repo features and fixes from the 2026-09-28 issue batch (GH-30 … GH-34)

## Summary

Everything in Navigator's `.agent/` used to assume one person per checkout. This release
makes the shared parts shareable and the personal parts personal: a per-contributor config
override, onboarding state outside the repo, GitHub-allocated task IDs, and the gitignore
entries nav-init should have written all along. One deep-research fix rides along.

## What's New

### Personal config override (GH-30)

`.agent/.nav-config.json` stays committed and shared. A new `.agent/.nav-config.local.json`
(gitignored) merges over it last — DEFAULTS < shared < local — in the hook runtime
(`nav_hook_lib.config.load`) and in `nav-features`. A contributor without a TypeSafe key
turns the judge off for themselves only:

```bash
python3 skills/nav-features/functions/feature_manager.py disable judge --local
```

`show` marks rows the local file decides with `L` and prints a legend; `info` names the
override; toggling the shared value while a local override shadows it prints a warning.
`config_guard` validates the local file the same way it validates the shared one.

### GitHub-issue task IDs (GH-32)

`task_id_source: github` in the config makes `nav-task` create the GitHub issue first and
name the doc `GH-<n>-<slug>.md`. Issue numbers are allocated by GitHub, so two contributors
branching at once can never mint the same ID, and Pilot already addresses tasks as
`GH-<n>`. A failing `gh` (no auth, no network) is an error, never a silent local number.
The default stays `local` (sequential `TASK-NN`). Index updates, graph sync and the
TaskCreated/TaskCompleted lifecycle events now accept any `PREFIX-<n>` filename.

```bash
python3 skills/nav-task/functions/task_id_generator.py --title "Add OAuth" --label pilot --json
# {"id": "GH-57", "source": "github", "url": "https://github.com/o/r/issues/57"}
```

## Bug Fixes

- **nav-onboard state is per person** (GH-31). Progress, the personal workflow guide and
  the `.completed` marker live under `~/.config/navigator/onboarding/<repo-id>/`
  (`NAVIGATOR_ONBOARDING_HOME` overrides the base; `<repo-id>` is the directory name plus
  an 8-character hash of the checkout path). Nothing is written inside the repo, so one
  contributor's finished onboarding no longer makes everyone else's skip. A pre-existing
  `.agent/onboarding/` in the repo is ignored. When the project has its own setup skill,
  nav-onboard points to it first.
- **nav-init gitignore** (GH-33) now appends `.agent/.nav-runtime-state.json`, its `.lock`,
  `.agent/.nav-config.local.json` and `.agent/onboarding/`, each only if absent, so a
  fresh repo's first `git add -A` no longer commits hook session state.
- **Deep-research fallback notes** (GH-34). `source_store write` used to dedup on the
  canonical URL regardless of status, so the WebFetch fallback after a blocked raw fetch
  was silently dropped and the 403 stub won. An `ok` write now replaces a `blocked` or
  `skipped` stub under the stub's id (`superseded: true`), a retry of a stub is allowed,
  and ok notes still dedup as before. The fetcher agent is told not to delete stubs by hand.

## Breaking Changes

None. Existing `TASK-NN` docs, the shared config file and every default are unchanged.
Onboarding runs completed before 7.8.0 are not migrated; re-run `nav-onboard` once if you
want the personal workflow guide back.

## Tests

`make test` green. Two new suites are wired into the Makefile: `skills/nav-features/functions`
(personal override layering) and `skills/nav-task/functions` (local and GitHub ID sources,
fake `gh` on PATH). Config, config_guard, graph_sync, task_to_graph, source_store and
nav-onboard suites gained cases for the new behavior.

## Getting Started

```bash
claude plugin update navigator@navigator-marketplace   # then restart Claude Code
```

Existing projects need no config change. Team repos: run the nav-init gitignore step once
(the six lines in `skills/nav-init/SKILL.md` §7), and set `"task_id_source": "github"` if
you want issue-numbered task docs.
