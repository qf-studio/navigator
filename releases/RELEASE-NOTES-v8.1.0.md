# Navigator v8.1.0 Release Notes — "Show Me the Decisions"

**Release Date**: 2026-10-03
**Type**: Minor — the judge's decision trail and labeling in `/nav` (TASK-86); the plugin is now
published by QuantFlow Studio

## Added

- **Judge trail behind `j`** (`/nav`): under the session tally, the last eight judged prompts,
  one line each — `14:03 · task · substantial · unclear  "make the onboarding better"`.
- **Label from the pane**: while the latest decision is unlabeled, `y` confirms the judge's
  verdict as the label and `x` disputes it. Labels land in `~/.config/navigator/judge-labels.json`
  (the personal config dir, like the ADHD switch) in the shape `scripts/judge_label.py` and
  `scripts/judge_eval.py --fixture` read: a confirmed verdict scores immediately; a disputed one
  has `tier: null`, so `judge_label.py label --fixture ~/.config/navigator/judge-labels.json`
  walks it for the real label later. Entries are deduped by prompt text.

## Changed

- Navigator is a QuantFlow Studio plugin: `plugin.json` author and `marketplace.json` owner,
  README and security contact, and every live install path and link now say
  `qf-studio/navigator` and `quantflow.studio`. The old `alekspetrov/navigator` path redirects;
  existing installs keep updating.
- The release-check URL, `auto_updater.py`, `version_detector.py`, `plugin_updater.py`,
  `claude_updater.py` and `check-version.sh` read the `qf-studio` repo directly.

Tests: 128 kit tests; Python suites unchanged except fixtures that name the repo.
Design: `.agent/tasks/TASK-86-judge-trail-labels.md`.
