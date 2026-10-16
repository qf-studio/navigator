#!/usr/bin/env python3
"""
Task validation for Navigator onboarding.

Validates whether learning tasks have been completed. With ``practice=True`` the checks
run against the practice sandbox (``practice.practice_root``), which mirrors ``.agent/``
outside the repo (GH-35); the exercises write there and the repo stays untouched.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from practice import practice_root  # noqa: E402


def validate_task(project_dir: str, skill_name: str, practice: bool = False) -> Dict:
    """
    Validate if a learning task has been completed.

    Args:
        project_dir: Project directory path
        skill_name: Name of skill to validate
        practice: Check the practice sandbox instead of the repo

    Returns:
        Validation result dictionary
    """
    validators = {
        "nav-start": _validate_nav_start,
        "nav-marker": _validate_nav_marker,
        "nav-task": _validate_nav_task,
        "nav-sop": _validate_nav_sop,
        "nav-compact": _validate_nav_compact,
        "frontend-component": _validate_frontend_component,
        "backend-endpoint": _validate_backend_endpoint,
        "frontend-test": _validate_frontend_test,
        "backend-test": _validate_backend_test,
        "database-migration": _validate_database_migration,
    }

    validator = validators.get(skill_name)
    if not validator:
        return {
            "valid": False,
            "method": "unknown",
            "reason": f"No validator for skill: {skill_name}",
            "suggestion": "Mark as complete manually if you've done the task",
        }

    root = practice_root(project_dir) if practice else Path(project_dir)
    result = validator(root)
    result["mode"] = "practice" if practice else "repo"
    result["root"] = str(root)
    return result


def _validate_nav_start(project_dir: Path) -> Dict:
    """
    Validate nav-start task.

    Since session start is conversational, we rely on user confirmation.
    """
    return {
        "valid": True,
        "method": "user_confirmation",
        "message": "Session start validated via user confirmation",
        "note": "nav-start is conversational - no file artifacts to check",
    }


def _validate_nav_marker(project_dir: Path) -> Dict:
    """
    Validate nav-marker task.

    Checks for marker file containing 'learning' in the name.
    """
    markers_dir = project_dir / ".agent" / ".context-markers"

    if not markers_dir.exists():
        return {
            "valid": False,
            "method": "file_check",
            "reason": "No .context-markers directory found",
            "suggestion": "Create a marker with: 'Create checkpoint learning-test'",
        }

    # Look for learning-related marker
    markers = list(markers_dir.glob("*.md"))
    learning_markers = [m for m in markers if "learning" in m.stem.lower()]

    if learning_markers:
        # Check if recently created (within last hour)
        recent = [m for m in learning_markers if _is_recent(m)]
        if recent:
            return {
                "valid": True,
                "method": "file_check",
                "marker_file": str(recent[0]),
                "message": f"Found learning marker: {recent[0].name}",
            }
        else:
            return {
                "valid": True,
                "method": "file_check",
                "marker_file": str(learning_markers[0]),
                "message": f"Found learning marker (older): {learning_markers[0].name}",
                "note": "Marker exists but was created earlier",
            }

    # Check for any recent marker
    recent_markers = [m for m in markers if _is_recent(m)]
    if recent_markers:
        return {
            "valid": True,
            "method": "file_check",
            "marker_file": str(recent_markers[0]),
            "message": f"Found recent marker: {recent_markers[0].name}",
            "note": "No 'learning' marker, but recent marker found",
        }

    return {
        "valid": False,
        "method": "file_check",
        "reason": "No learning marker found",
        "suggestion": "Create a marker with: 'Create checkpoint learning-test'",
    }


def _validate_nav_task(project_dir: Path) -> Dict:
    """
    Validate nav-task task.

    Checks for task file containing 'learning' in the name.
    """
    tasks_dir = project_dir / ".agent" / "tasks"

    if not tasks_dir.exists():
        return {
            "valid": False,
            "method": "file_check",
            "reason": "No tasks directory found",
            "suggestion": "Create a task with: 'Create task doc for learning-feature'",
        }

    # Look for learning-related task
    tasks = list(tasks_dir.glob("*.md"))
    learning_tasks = [t for t in tasks if "learning" in t.stem.lower()]

    if learning_tasks:
        return {
            "valid": True,
            "method": "file_check",
            "task_file": str(learning_tasks[0]),
            "message": f"Found learning task: {learning_tasks[0].name}",
        }

    # Check for any recent task
    recent_tasks = [t for t in tasks if _is_recent(t)]
    if recent_tasks:
        return {
            "valid": True,
            "method": "file_check",
            "task_file": str(recent_tasks[0]),
            "message": f"Found recent task: {recent_tasks[0].name}",
            "note": "No 'learning' task, but recent task found",
        }

    return {
        "valid": False,
        "method": "file_check",
        "reason": "No learning task found",
        "suggestion": "Create a task with: 'Create task doc for learning-feature'",
    }


def _validate_nav_sop(project_dir: Path) -> Dict:
    """
    Validate nav-sop task.

    Checks for SOP file in any category.
    """
    sops_dir = project_dir / ".agent" / "sops"

    if not sops_dir.exists():
        return {
            "valid": False,
            "method": "file_check",
            "reason": "No sops directory found",
            "suggestion": "Create an SOP with: 'Create SOP for debugging test-failures'",
        }

    # Look in all SOP categories
    categories = ["debugging", "integrations", "development", "deployment"]
    all_sops = []

    for category in categories:
        category_dir = sops_dir / category
        if category_dir.exists():
            all_sops.extend(list(category_dir.glob("*.md")))

    if not all_sops:
        return {
            "valid": False,
            "method": "file_check",
            "reason": "No SOP files found",
            "suggestion": "Create an SOP with: 'Create SOP for debugging test-failures'",
        }

    # Look for learning-related or recent SOP
    learning_sops = [s for s in all_sops if "learning" in s.stem.lower() or "test" in s.stem.lower()]
    if learning_sops:
        return {
            "valid": True,
            "method": "file_check",
            "sop_file": str(learning_sops[0]),
            "message": f"Found SOP: {learning_sops[0].name}",
        }

    recent_sops = [s for s in all_sops if _is_recent(s)]
    if recent_sops:
        return {
            "valid": True,
            "method": "file_check",
            "sop_file": str(recent_sops[0]),
            "message": f"Found recent SOP: {recent_sops[0].name}",
        }

    # Any SOP counts
    return {
        "valid": True,
        "method": "file_check",
        "sop_file": str(all_sops[0]),
        "message": f"Found SOP: {all_sops[0].name}",
        "note": "Using existing SOP (not from learning task)",
    }


def _validate_nav_compact(project_dir: Path) -> Dict:
    """
    Validate nav-compact task.

    Checks for .active file in context-markers.
    """
    markers_dir = project_dir / ".agent" / ".context-markers"
    active_file = markers_dir / ".active"

    if active_file.exists():
        return {
            "valid": True,
            "method": "file_check",
            "active_file": str(active_file),
            "message": "Compact initiated - .active marker set",
        }

    # Check for any recent marker that might indicate compact was run
    if markers_dir.exists():
        markers = list(markers_dir.glob("*.md"))
        compact_markers = [m for m in markers if "compact" in m.stem.lower()]
        if compact_markers:
            return {
                "valid": True,
                "method": "file_check",
                "marker_file": str(compact_markers[0]),
                "message": "Found compact marker (may have been restored already)",
            }

    return {
        "valid": False,
        "method": "file_check",
        "reason": "No .active marker file found",
        "suggestion": "Run compact with: 'Clear context and preserve markers'",
    }


def _validate_frontend_component(project_dir: Path) -> Dict:
    """
    Validate frontend-component task.

    Checks for component files with 'onboarding' or 'demo' in name.
    """
    # Common component directories
    search_dirs = [
        project_dir / "src" / "components",
        project_dir / "components",
        project_dir / "app" / "components",
        project_dir / "src",
    ]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue

        # Look for onboarding/demo related files
        for pattern in ["**/[Oo]nboarding*", "**/[Dd]emo*"]:
            matches = list(search_dir.glob(pattern))
            if matches:
                return {
                    "valid": True,
                    "method": "file_check",
                    "component_path": str(matches[0]),
                    "message": f"Found component: {matches[0].name}",
                }

    return {
        "valid": False,
        "method": "file_check",
        "reason": "No onboarding/demo component found",
        "suggestion": "Create component with: 'Create component OnboardingDemo'",
    }


def _validate_backend_endpoint(project_dir: Path) -> Dict:
    """
    Validate backend-endpoint task.

    Checks for route/endpoint files with 'onboarding' or 'demo' in name.
    """
    # Common route directories
    search_dirs = [
        project_dir / "src" / "routes",
        project_dir / "src" / "api",
        project_dir / "routes",
        project_dir / "api",
        project_dir / "app" / "api",
    ]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue

        # Look for onboarding/demo related files
        for pattern in ["**/[Oo]nboarding*", "**/[Dd]emo*"]:
            matches = list(search_dir.glob(pattern))
            if matches:
                return {
                    "valid": True,
                    "method": "file_check",
                    "endpoint_path": str(matches[0]),
                    "message": f"Found endpoint: {matches[0].name}",
                }

    return {
        "valid": False,
        "method": "file_check",
        "reason": "No onboarding/demo endpoint found",
        "suggestion": "Create endpoint with: 'Add endpoint /api/onboarding-demo'",
    }


def _validate_frontend_test(project_dir: Path) -> Dict:
    """Validate frontend-test task."""
    return _validate_test_file(project_dir, "frontend")


def _validate_backend_test(project_dir: Path) -> Dict:
    """Validate backend-test task."""
    return _validate_test_file(project_dir, "backend")


def _validate_test_file(project_dir: Path, test_type: str) -> Dict:
    """Generic test file validation."""
    # Look for test files
    patterns = ["**/*.test.ts", "**/*.test.tsx", "**/*.test.js", "**/*.spec.ts", "**/*_test.py", "**/*_test.go"]

    for pattern in patterns:
        matches = list(project_dir.glob(pattern))
        recent = [m for m in matches if _is_recent(m)]
        if recent:
            return {
                "valid": True,
                "method": "file_check",
                "test_file": str(recent[0]),
                "message": f"Found recent test: {recent[0].name}",
            }

    return {
        "valid": True,
        "method": "user_confirmation",
        "message": f"Test validation relies on user confirmation",
        "note": "No recent test files found, but task may still be complete",
    }


def _validate_database_migration(project_dir: Path) -> Dict:
    """Validate database-migration task."""
    # Common migration directories
    migration_dirs = [
        project_dir / "prisma" / "migrations",
        project_dir / "migrations",
        project_dir / "db" / "migrations",
        project_dir / "alembic" / "versions",
    ]

    for migration_dir in migration_dirs:
        if migration_dir.exists():
            migrations = list(migration_dir.glob("*"))
            recent = [m for m in migrations if _is_recent(m)]
            if recent:
                return {
                    "valid": True,
                    "method": "file_check",
                    "migration_path": str(recent[0]),
                    "message": f"Found recent migration: {recent[0].name}",
                }

    return {
        "valid": True,
        "method": "user_confirmation",
        "message": "Migration validation relies on user confirmation",
        "note": "No recent migrations found, but task may still be complete",
    }


def _is_recent(path: Path, hours: int = 1) -> bool:
    """Check if file was modified within the last N hours."""
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        return datetime.now() - mtime < timedelta(hours=hours)
    except (OSError, ValueError):
        return False


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a nav-onboard learning task")
    parser.add_argument("skill_name")
    parser.add_argument("--project-dir", default=".", help="repo being onboarded")
    parser.add_argument("--practice", action="store_true",
                        help="check the practice sandbox, not the repo")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    result = validate_task(args.project_dir, args.skill_name, practice=args.practice)
    print(json.dumps(result, indent=2))
    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    sys.exit(main())
