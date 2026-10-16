# TASK-106: nav-onboard runs as documented; practice tasks never touch shared state

**Status**: ✅ Released in v8.4.4 — 2026-10-16 (PR #39)
**Priority**: High
**Source**: [qf-studio/navigator#35](https://github.com/qf-studio/navigator/issues/35)
**Owner**: Navigator maintainers

## Problem

A second contributor on a team repo (Navigator 7.8.0) ran the nav-onboard Quick Start as
`skills/nav-onboard/SKILL.md` describes. It failed in two places and its exercises changed
shared repo state:

1. `skill_recommender.py` with no input calls `json.load(sys.stdin)` and crashes.
2. `progress_tracker.py init` needs five positional args; the docs show two. A list for
   `skills_json` raises `AttributeError`.
3. Curriculum `task_file` names come from the position in the list (`02-nav-task.md`),
   not from the files on disk (`03-nav-task.md`).
4. Full Education reads `.agent/philosophy/CONTEXT-EFFICIENCY.md` from the project. The
   file ships only with the plugin.
5. The nav-task exercise opens a real GitHub issue when `task_id_source: github`. The
   nav-task and nav-sop exercises write tracked files under `.agent/`.

## Model

Onboarding is a rehearsal. Every exercise renders the artifact the real skill would
create, but into the personal onboarding dir (`onboarding_paths.onboarding_dir()/practice/`,
outside the repo, GH-31). The sandbox mirrors `.agent/` so the validator runs unchanged
against either root. `practice.py` is the only writer; it reads `task_id_source` and, in the
github case, prints the issue it would open (title, labels, body head) and never runs `gh`.
`practice.py clean` removes the sandbox; `.completed` keeps the record.

The CLIs compute their own inputs: the recommender analyzes the project when no analysis is
given, the tracker derives project type, name and skills from the analyzer and recommender.
The documented one-line forms work; the piped forms still work.

## Changes

- `skills/nav-onboard/functions/skill_recommender.py`
  - `task_file_for(skill_id)` resolves against `learning-tasks/` on disk; development
    skills map to `06-dev-skill.md`.
  - Philosophy entry carries the plugin's absolute path.
  - `project_tutorial`: `.agent/ONBOARDING.md` in the project, when present (team repos
    extend the tutorial instead of replacing it).
  - CLI: `[project_dir]`, `--analysis FILE|-`.
- `skills/nav-onboard/functions/progress_tracker.py`
  - argparse CLI: `init <quick_start|full_education> [--project-dir] [--project-type]
    [--project-name] [--skills FILE|-]`; `update <skill> <status> [notes]`; `get`; `next`.
  - `init_progress` accepts a skills list as `essential_skills`.
- `skills/nav-onboard/functions/practice.py` (new): `run <skill>`, `list`, `clean`,
  `dir`. Never imports or runs `gh`.
- `skills/nav-onboard/functions/task_validator.py`: `--practice` validates the sandbox;
  positional `[project_dir]` defaults to `.`.
- `skills/nav-onboard/learning-tasks/02..05`: practice-mode wording; the real command stays
  in a "Later, for real" box.
- `skills/nav-onboard/SKILL.md`: steps 3, 5, 6 use the one-line forms; Full Education
  reads the plugin's philosophy copy; new "Practice mode" section; project tutorial hook.
- Tests: `test_onboard_flow.py` — recommender → tracker → validator path on a fresh
  nav-init-shaped project; every curriculum `task_file` exists; `task_id_source: github`
  with a fake `gh` on PATH that fails the test when called; `git status` of the project is
  unchanged after all exercises.

## Verify

```bash
cd skills/nav-onboard/functions && python3 -m unittest discover -p "test_*.py"
```
