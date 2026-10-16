# Navigator v8.4.4 Release Notes

**Release Date**: 2026-10-16
**Type**: Patch — nav-onboard runs as documented; practice tasks never touch the repo (TASK-106)

Closes [qf-studio/navigator#35](https://github.com/qf-studio/navigator/issues/35).

## Fixed

A contributor on a team repo ran the nav-onboard Quick Start as `skills/nav-onboard/SKILL.md`
describes. It failed in two places, and its exercises opened a real GitHub issue and wrote
tracked files under `.agent/`. Five defects, each with a regression test:

- **`skill_recommender.py` crashed with no input.** It read an analysis from stdin
  unconditionally. It now analyzes the project itself (`[project_dir]`); `--analysis FILE|-`
  keeps the piped form.
- **`progress_tracker.py init` wanted five positional arguments.** The documented
  `init quick_start` works: the tracker derives project type, name and skills from the
  analyzer and recommender (`--project-dir`, `--project-type`, `--project-name`,
  `--skills FILE|-` override). `update <skill> <status> [notes]`, `get` and `next` match the
  SKILL.md. A bare skill list is accepted as `essential_skills`.
- **Curriculum `task_file` names came from list position.** They resolve against
  `learning-tasks/` on disk (`02-nav-marker`, `03-nav-task`, `04-nav-sop`, `05-nav-compact`,
  `06-dev-skill`); a test asserts every file exists.
- **Full Education read `.agent/philosophy/CONTEXT-EFFICIENCY.md` from the project.** The file
  ships only with the plugin; the entry now carries the plugin's absolute path.
- **Exercises changed shared repo state.** New `practice.py` (`run <skill>`, `list`, `clean`,
  `dir`) renders what nav-marker, nav-task, nav-sop and nav-compact would create into a
  sandbox under `~/.config/navigator/onboarding/<repo-id>/practice/.agent/`, outside the repo.
  With `task_id_source: github` it reports `would_create_issue` (title, labels, body head) and
  never runs `gh`. `task_validator.py <skill> --practice` checks the sandbox. Learning tasks
  02–05 explain practice mode and keep the real command in a "Later, for real" box.

Also: `.agent/ONBOARDING.md` in a project extends the tutorial when present; SKILL.md 1.1.0
documents practice mode, the one-line command forms and cleanup at completion.

Tests: `test_onboard_flow.py` runs recommender → tracker → practice → validator on a fresh
nav-init-shaped repo; the repo is byte-identical afterwards, `git status` stays clean, and a
fake `gh` on PATH fails the test if called. Full `make test` green.

## Upgrade

```bash
claude plugin update navigator@navigator-marketplace
```

Restart Claude Code after the update.
