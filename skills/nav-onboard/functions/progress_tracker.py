#!/usr/bin/env python3
"""
Progress tracking for Navigator onboarding.

Manages PROGRESS.md in the per-person onboarding directory (see
onboarding_paths.onboarding_dir — outside the repo since GH-31) to track
learning completion. ``project_dir`` arguments identify the repo; nothing is
written under it.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from onboarding_paths import onboarding_dir as _onboarding_dir  # noqa: E402

FLOWS = ("quick_start", "full_education")
QUICK_START_ESSENTIALS = ["nav-start", "nav-marker", "nav-task"]


def init_progress(
    project_dir: str,
    flow_type: str,
    project_type: str,
    project_name: str,
    skills: Dict
) -> str:
    """
    Initialize progress tracking file.

    Args:
        project_dir: Project directory path
        flow_type: "quick_start" or "full_education"
        project_type: Detected project type
        project_name: Project name
        skills: Skill recommendations from skill_recommender

    Returns:
        Path to created progress file
    """
    if flow_type not in FLOWS:
        raise ValueError(f"flow_type must be one of {FLOWS}, got {flow_type!r}")
    skills = _normalize_skills(skills)

    onboarding_dir = _onboarding_dir(project_dir)
    onboarding_dir.mkdir(parents=True, exist_ok=True)

    progress_file = onboarding_dir / "PROGRESS.md"

    # Determine curriculum based on flow
    if flow_type == "quick_start":
        essential = list(QUICK_START_ESSENTIALS)
        development = skills.get("recommended_skills", [])[:1]  # Just first dev skill
    else:  # full_education
        essential = skills.get("essential_skills", [])
        development = skills.get("recommended_skills", [])

    # Build progress table
    essential_rows = []
    for i, skill in enumerate(essential, 1):
        essential_rows.append(f"| {i} | {skill} | pending | - | - |")

    dev_rows = []
    for i, skill in enumerate(development, len(essential) + 1):
        dev_rows.append(f"| {i} | {skill} | pending | - | - |")

    total_skills = len(essential) + len(development)

    # Format flow name
    flow_name = "Quick Start" if flow_type == "quick_start" else "Full Education"

    content = f"""# Navigator Onboarding Progress

**Started**: {datetime.now().strftime("%Y-%m-%d %H:%M")}
**Flow**: {flow_name}
**Project**: {project_name} ({project_type})

---

## Essential Skills

| # | Skill | Status | Completed | Notes |
|---|-------|--------|-----------|-------|
{chr(10).join(essential_rows)}

## Development Skills

| # | Skill | Status | Completed | Notes |
|---|-------|--------|-----------|-------|
{chr(10).join(dev_rows) if dev_rows else "| - | (none for this flow) | - | - | - |"}

---

**Progress**: 0/{total_skills} (0%)
**Next Task**: {essential[0] if essential else "complete"}

*Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M")}*
"""

    progress_file.write_text(content)

    # Also save structured data for programmatic access
    data_file = onboarding_dir / ".progress-data.json"
    data = {
        "started": datetime.now().isoformat(),
        "flow_type": flow_type,
        "project_type": project_type,
        "project_name": project_name,
        "essential_skills": essential,
        "development_skills": development,
        "progress": {skill: {"status": "pending", "completed": None, "notes": ""} for skill in essential + development},
        "total": total_skills,
        "completed": 0,
    }
    data_file.write_text(json.dumps(data, indent=2))

    return str(progress_file)


def _normalize_skills(skills) -> Dict:
    """Accept the recommender's dict or a bare list of skill ids (GH-35 #2)."""
    if skills is None:
        return {}
    if isinstance(skills, list):
        return {"essential_skills": [str(s) for s in skills], "recommended_skills": []}
    if isinstance(skills, dict):
        return skills
    raise ValueError("skills must be a recommendations object or a list of skill ids")


def update_progress(
    project_dir: str,
    skill_name: str,
    status: str,
    notes: str = ""
) -> Dict:
    """
    Update progress for a specific skill.

    Args:
        project_dir: Project directory path
        skill_name: Name of skill to update
        status: "pending", "in_progress", or "completed"
        notes: Optional notes about completion

    Returns:
        Updated progress summary
    """
    onboarding_dir = _onboarding_dir(project_dir)
    data_file = onboarding_dir / ".progress-data.json"

    if not data_file.exists():
        return {"error": "Progress not initialized. Run init first."}

    try:
        data = json.loads(data_file.read_text())
    except json.JSONDecodeError:
        return {"error": "Progress data corrupt"}

    progress = data.get("progress", {})
    if skill_name not in progress:
        return {"error": f"Unknown skill: {skill_name}"}

    # Update skill status
    progress[skill_name]["status"] = status
    if status == "completed":
        progress[skill_name]["completed"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        data["completed"] = sum(1 for s in progress.values() if s.get("status") == "completed")
    if notes:
        progress[skill_name]["notes"] = notes

    # Save updated data
    data_file.write_text(json.dumps(data, indent=2))

    # Regenerate markdown
    _regenerate_markdown(onboarding_dir, data)

    total = data.get("total", 0)
    completed = data.get("completed", 0)
    return {
        "skill": skill_name,
        "status": status,
        "completed": completed,
        "total": total,
        "percentage": round(completed / total * 100) if total > 0 else 0,
        "next_task": get_next_task(project_dir),
    }


def get_progress(project_dir: str) -> Dict:
    """
    Get current progress summary.

    Args:
        project_dir: Project directory path

    Returns:
        Progress summary dictionary
    """
    onboarding_dir = _onboarding_dir(project_dir)
    data_file = onboarding_dir / ".progress-data.json"

    if not data_file.exists():
        return {"initialized": False}

    try:
        data = json.loads(data_file.read_text())
    except json.JSONDecodeError:
        return {"error": "Progress data corrupt"}

    total = data.get("total", 0)
    completed = data.get("completed", 0)
    return {
        "initialized": True,
        "flow_type": data.get("flow_type"),
        "project_type": data.get("project_type"),
        "completed": completed,
        "total": total,
        "percentage": round(completed / total * 100) if total > 0 else 0,
        "skills": data.get("progress", {}),
        "next_task": get_next_task(project_dir),
    }


def get_next_task(project_dir: str) -> Optional[str]:
    """
    Determine the next task to complete.

    Args:
        project_dir: Project directory path

    Returns:
        Next skill name or None if complete
    """
    onboarding_dir = _onboarding_dir(project_dir)
    data_file = onboarding_dir / ".progress-data.json"

    if not data_file.exists():
        return None

    try:
        data = json.loads(data_file.read_text())
    except json.JSONDecodeError:
        return None
    return _next_from_data(data)


def _next_from_data(data: Dict) -> Optional[str]:
    """First non-completed skill in curriculum order, or None when all done."""
    all_skills = data.get("essential_skills", []) + data.get("development_skills", [])
    progress = data.get("progress", {})
    for skill in all_skills:
        if progress.get(skill, {}).get("status") != "completed":
            return skill
    return None


def _regenerate_markdown(onboarding_dir: Path, data: Dict) -> None:
    """Regenerate PROGRESS.md from data."""
    progress_file = onboarding_dir / "PROGRESS.md"

    # Build tables
    essential_rows = []
    for i, skill in enumerate(data["essential_skills"], 1):
        p = data["progress"][skill]
        status_icon = {"pending": "pending", "in_progress": "in_progress", "completed": "completed"}[p["status"]]
        completed = p["completed"] or "-"
        notes = p["notes"] or "-"
        essential_rows.append(f"| {i} | {skill} | {status_icon} | {completed} | {notes} |")

    dev_rows = []
    for i, skill in enumerate(data["development_skills"], len(data["essential_skills"]) + 1):
        p = data["progress"][skill]
        status_icon = {"pending": "pending", "in_progress": "in_progress", "completed": "completed"}[p["status"]]
        completed = p["completed"] or "-"
        notes = p["notes"] or "-"
        dev_rows.append(f"| {i} | {skill} | {status_icon} | {completed} | {notes} |")

    percentage = round(data["completed"] / data["total"] * 100) if data["total"] > 0 else 0
    next_task = _next_from_data(data) or "complete"

    flow_name = "Quick Start" if data["flow_type"] == "quick_start" else "Full Education"

    content = f"""# Navigator Onboarding Progress

**Started**: {data["started"][:16].replace("T", " ")}
**Flow**: {flow_name}
**Project**: {data["project_name"]} ({data["project_type"]})

---

## Essential Skills

| # | Skill | Status | Completed | Notes |
|---|-------|--------|-----------|-------|
{chr(10).join(essential_rows)}

## Development Skills

| # | Skill | Status | Completed | Notes |
|---|-------|--------|-----------|-------|
{chr(10).join(dev_rows) if dev_rows else "| - | (none for this flow) | - | - | - |"}

---

**Progress**: {data["completed"]}/{data["total"]} ({percentage}%)
**Next Task**: {next_task}

*Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M")}*
"""

    progress_file.write_text(content)


def format_progress_bar(completed: int, total: int, width: int = 30) -> str:
    """Generate ASCII progress bar."""
    if total == 0:
        return "[" + " " * width + "]"

    filled = int(width * completed / total)
    empty = width - filled
    return "[" + "=" * filled + " " * empty + "]"


def _read_json_arg(value: str):
    """A JSON argument given inline, as a file path, or ``-`` for stdin."""
    if value == "-":
        return json.load(sys.stdin)
    if os.path.isfile(value):
        with open(value, encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(value)


def _defaults_from_project(project_dir: str) -> Dict:
    """Analysis + recommendations computed for ``project_dir`` (lazy import, on demand)."""
    from project_analyzer import analyze_project
    from skill_recommender import recommend_skills
    analysis = analyze_project(project_dir)
    return {"analysis": analysis, "skills": recommend_skills(analysis, project_dir)}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Navigator onboarding progress tracker")
    parser.add_argument("--project-dir", default=".",
                        help="repo being onboarded; state lives outside it (default: .)")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create PROGRESS.md for a flow")
    init.add_argument("flow_type", choices=FLOWS)
    init.add_argument("project_type", nargs="?", default=None,
                      help="default: detected by project_analyzer.py")
    init.add_argument("--project-name", default=None, help="default: detected")
    init.add_argument("--skills", default=None, metavar="JSON",
                      help="skill_recommender.py output: inline JSON, a file, or - (stdin); "
                           "default: computed for --project-dir")

    update = sub.add_parser("update", help="set a skill's status")
    update.add_argument("skill_name")
    update.add_argument("status", choices=("pending", "in_progress", "completed"))
    update.add_argument("notes", nargs="?", default="")

    sub.add_parser("get", help="print the progress summary")
    sub.add_parser("next", help="print the next skill, or 'complete'")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    project_dir = args.project_dir

    if args.command == "init":
        skills = _read_json_arg(args.skills) if args.skills else None
        project_type, project_name = args.project_type, args.project_name
        if skills is None or project_type is None or project_name is None:
            computed = _defaults_from_project(project_dir)
            skills = computed["skills"] if skills is None else skills
            project_type = project_type or computed["analysis"].get("project_type", "unknown")
            project_name = project_name or computed["analysis"].get(
                "project_name", os.path.basename(os.path.realpath(project_dir)))
        print(init_progress(project_dir, args.flow_type, project_type, project_name, skills))
        return 0

    if args.command == "update":
        result = update_progress(project_dir, args.skill_name, args.status, args.notes)
        print(json.dumps(result, indent=2))
        return 1 if "error" in result else 0

    if args.command == "get":
        print(json.dumps(get_progress(project_dir), indent=2))
        return 0

    print(get_next_task(project_dir) or "complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
