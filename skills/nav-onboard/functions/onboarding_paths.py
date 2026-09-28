#!/usr/bin/env python3
"""
Where nav-onboard keeps its state — per person, outside the repo (GH-31).

Onboarding progress, the personal workflow guide and the completion marker used
to live in ``<repo>/.agent/onboarding/``. In a shared repo the first contributor
to commit them made every later contributor's onboarding skip (``.completed``
existed) and put personal files into git. State now lives under the user's
config home, keyed by repo:

    $NAVIGATOR_ONBOARDING_HOME/<repo-id>/            (explicit override, tests)
    $XDG_CONFIG_HOME/navigator/onboarding/<repo-id>/ (default: ~/.config/...)

``<repo-id>`` is ``<dirname>-<sha1(realpath)[:8]>`` so two checkouts of the same
project on one machine do not share state and two projects with the same
directory name do not collide.

CLI: ``python3 onboarding_paths.py [project_dir]`` prints the directory.
"""

import hashlib
import os
import sys
from pathlib import Path

ENV_OVERRIDE = "NAVIGATOR_ONBOARDING_HOME"
STATE_FILES = ("PROGRESS.md", "MY-WORKFLOW.md", ".progress-data.json", ".completed")


def repo_id(project_dir: str = ".") -> str:
    real = os.path.realpath(project_dir)
    name = os.path.basename(real) or "root"
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in name)[:40]
    return f"{safe}-{hashlib.sha1(real.encode('utf-8')).hexdigest()[:8]}"


def onboarding_home() -> Path:
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "navigator" / "onboarding"


def onboarding_dir(project_dir: str = ".") -> Path:
    """Per-person, per-repo onboarding state directory (not created here)."""
    return onboarding_home() / repo_id(project_dir)


def completed_marker(project_dir: str = ".") -> Path:
    return onboarding_dir(project_dir) / ".completed"


if __name__ == "__main__":
    print(onboarding_dir(sys.argv[1] if len(sys.argv) > 1 else "."))
