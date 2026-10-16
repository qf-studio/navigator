#!/usr/bin/env python3
"""
Practice sandbox for nav-onboard exercises (GH-35).

The learning tasks used to run the real skills: "Create task doc for learning-feature"
wrote a tracked file under ``.agent/tasks/`` and, with ``task_id_source: github``, opened
a real issue in the team repo. Onboarding is a rehearsal, so every exercise now renders
the artifact the real skill would create into the person's onboarding dir instead:

    <onboarding_dir>/practice/.agent/.context-markers/   nav-marker, nav-compact
    <onboarding_dir>/practice/.agent/tasks/              nav-task
    <onboarding_dir>/practice/.agent/sops/debugging/     nav-sop

The sandbox mirrors ``.agent/`` so ``task_validator.py --practice`` runs its usual checks
against it. Nothing under the repo changes and ``gh`` is never run: in the github case
the result carries ``would_create_issue`` (title, labels, body) for display only.

CLI::

    practice.py [--project-dir .] run <skill> [--name NAME]
    practice.py [--project-dir .] list
    practice.py [--project-dir .] clean
    practice.py [--project-dir .] dir
"""

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from onboarding_paths import onboarding_dir  # noqa: E402

PRACTICE_SUBDIR = "practice"
DEFAULT_NAMES = {
    "nav-marker": "learning-test",
    "nav-task": "learning-feature",
    "nav-sop": "test-failures",
    "nav-compact": "before-compact",
}
REAL_COMMANDS = {
    "nav-marker": 'Create checkpoint learning-test',
    "nav-task": 'Create task doc for learning-feature',
    "nav-sop": 'Create SOP for debugging test-failures',
    "nav-compact": 'Clear context and preserve markers',
}
PRACTICE_SKILLS = tuple(DEFAULT_NAMES)
GITHUB_PLACEHOLDER_ID = "GH-NEW"


def practice_root(project_dir: str = ".") -> Path:
    """Sandbox root for a repo; contains a mirrored ``.agent/`` once an exercise ran."""
    return onboarding_dir(project_dir) / PRACTICE_SUBDIR


def read_nav_config(project_dir: str) -> Dict:
    """``.agent/.nav-config.json`` of the repo, ``{}`` when missing or unreadable."""
    path = Path(project_dir) / ".agent" / ".nav-config.json"
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "practice"


def _stamp(now: datetime) -> str:
    return now.strftime("%Y-%m-%d-%H%M")


def _next_local_task_id(project_dir: str, prefix: str) -> str:
    """The id the local source would mint next, read from ``.agent/tasks/`` (read-only)."""
    tasks_dir = Path(project_dir) / ".agent" / "tasks"
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)")
    highest = 0
    if tasks_dir.is_dir():
        for path in tasks_dir.glob(f"{prefix}-*.md"):
            match = pattern.match(path.name)
            if match:
                highest = max(highest, int(match.group(1)))
    return f"{prefix}-{highest + 1:02d}"


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _marker_content(name: str, now: datetime, note: str) -> str:
    return f"""# Context Marker: {name}

**Created**: {now.strftime("%Y-%m-%d %H:%M")}
**Mode**: practice (nav-onboard sandbox, not in the repo)

## Conversation Summary

{note}

## Files Modified

None. Practice markers record nothing from the repo.

## Current Focus

Learning how a context marker preserves a session.

## Next Steps

1. Finish the onboarding curriculum.
2. Create a real marker before your next break: "Create checkpoint <name>".

## Restore Instructions

A real marker restores with "Load marker {name}". This practice marker is only an example.
"""


def _task_content(task_id: str, title: str, now: datetime) -> str:
    return f"""# {task_id}: {title}

**Created**: {now.strftime("%Y-%m-%d")}
**Status**: Planning
**Priority**: Medium
**Complexity**: Low
**Mode**: practice (nav-onboard sandbox, not in the repo)

---

## Context

[Describe the problem, feature request, or improvement needed]

**Problem**: [What needs to be solved?]

## Implementation Plan

1. [First step]
2. [Second step]

## Technical Decisions

- [Decision and why]

## Files Modified

- [path] — [what changed]

## Success Criteria

- [ ] [How to verify completion]
"""


def _sop_content(title: str, now: datetime) -> str:
    return f"""# SOP: {title}

**Category**: debugging
**Created**: {now.strftime("%Y-%m-%d")}
**Mode**: practice (nav-onboard sandbox, not in the repo)

## Context

[When does this problem appear?]

## The Problem

### Symptoms

- [What you see]

### Root Cause

[Why it happens]

## The Solution

### Step 1: [Action]

```bash
# command
```

## Prevention

- [How to avoid it next time]
"""


def run_practice(project_dir: str, skill: str, name: Optional[str] = None,
                 now: Optional[datetime] = None) -> Dict:
    """Render the artifact ``skill`` would create, into the sandbox. Never runs ``gh``."""
    if skill not in PRACTICE_SKILLS:
        return {"error": f"No practice exercise for skill: {skill}",
                "practice_skills": list(PRACTICE_SKILLS)}
    now = now or datetime.now()
    name = name or DEFAULT_NAMES[skill]
    root = practice_root(project_dir)
    agent = root / ".agent"
    created: List[Path] = []
    would_create_issue = None
    headline = ""

    if skill == "nav-marker":
        path = agent / ".context-markers" / f"{_stamp(now)}_{_slug(name)}.md"
        created.append(_write(path, _marker_content(
            name, now, "Practice marker created during Navigator onboarding.")))
        headline = f"Marker: {name}"

    elif skill == "nav-task":
        config = read_nav_config(project_dir)
        prefix = str(config.get("task_prefix", "TASK"))
        source = str(config.get("task_id_source", "local"))
        title = name.replace("-", " ").strip().capitalize()
        if source == "github":
            task_id = GITHUB_PLACEHOLDER_ID
            would_create_issue = {
                "title": title,
                "labels": [],
                "body": "Task created from Navigator (nav-task).",
                "note": "Practice mode shows the issue and does not create it.",
            }
        else:
            task_id = _next_local_task_id(project_dir, prefix)
        path = agent / "tasks" / f"{task_id}-{_slug(name)}.md"
        created.append(_write(path, _task_content(task_id, title, now)))
        headline = f"Task: {task_id}-{_slug(name)} (id source: {source})"

    elif skill == "nav-sop":
        title = name.replace("-", " ").strip().capitalize()
        path = agent / "sops" / "debugging" / f"{_slug(name)}.md"
        created.append(_write(path, _sop_content(title, now)))
        headline = f"SOP: debugging/{_slug(name)}"

    elif skill == "nav-compact":
        marker_name = f"{_slug(name)}-{_stamp(now)}"
        marker = agent / ".context-markers" / f"{marker_name}.md"
        created.append(_write(marker, _marker_content(
            marker_name, now, "Practice compact: state saved before clearing context.")))
        created.append(_write(agent / ".context-markers" / ".active", marker.name + "\n"))
        headline = f"Marker: {marker_name} (.active set)"

    preview = created[0].read_text(encoding="utf-8").splitlines()[:12]
    return {
        "skill": skill,
        "mode": "practice",
        "headline": headline,
        "practice_root": str(root),
        "created": [str(p) for p in created],
        "would_create_issue": would_create_issue,
        "preview": preview,
        "real_command": REAL_COMMANDS[skill],
        "repo_untouched": True,
    }


def list_practice(project_dir: str) -> Dict:
    root = practice_root(project_dir)
    files = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()) \
        if root.exists() else []
    return {"practice_root": str(root), "files": files}


def clean_practice(project_dir: str) -> Dict:
    root = practice_root(project_dir)
    existed = root.exists()
    shutil.rmtree(root, ignore_errors=True)
    return {"practice_root": str(root), "removed": existed}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="nav-onboard practice sandbox")
    parser.add_argument("--project-dir", default=".",
                        help="repo being onboarded; the sandbox lives outside it")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="render what a skill would create, into the sandbox")
    run.add_argument("skill", choices=PRACTICE_SKILLS)
    run.add_argument("--name", default=None, help="marker/task/SOP name")
    sub.add_parser("list", help="files in the sandbox")
    sub.add_parser("clean", help="remove the sandbox")
    sub.add_parser("dir", help="print the sandbox path")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "run":
        result = run_practice(args.project_dir, args.skill, args.name)
    elif args.command == "list":
        result = list_practice(args.project_dir)
    elif args.command == "clean":
        result = clean_practice(args.project_dir)
    else:
        print(practice_root(args.project_dir))
        return 0
    print(json.dumps(result, indent=2))
    return 1 if "error" in result else 0


if __name__ == "__main__":
    sys.exit(main())
