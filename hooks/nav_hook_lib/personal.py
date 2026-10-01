#!/usr/bin/env python3
"""nav_hook_lib.personal — per-person settings outside the repo (TASK-82).

Some switches belong to the person, not the project: ADHD mode is the first.
They live as small JSON files under the user's config home, never in
``.agent/`` (which is shared) and never in ``.nav-config.local.json`` (which is
per checkout). Same precedent as nav-onboard's per-person state (GH-31).

    $NAVIGATOR_CONFIG_HOME/<name>.json              (explicit override, tests)
    $XDG_CONFIG_HOME/navigator/<name>.json          (default: ~/.config/navigator)

Reads never raise: a missing or corrupt file is ``{}``. Writes are atomic
(hio.atomic_write_text) and report success as a bool. Stdlib + siblings only.
"""
from __future__ import annotations

import os
from pathlib import Path

from . import hio

ENV_OVERRIDE = "NAVIGATOR_CONFIG_HOME"


def config_home() -> Path:
    """Directory for per-person Navigator settings (not created here)."""
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "navigator"


def path(name: str) -> Path:
    return config_home() / f"{name}.json"


def read(name: str) -> dict:
    """The settings dict for ``name``; ``{}`` when missing, corrupt or not an object."""
    data = hio.safe_json(path(name))
    return data if isinstance(data, dict) else {}


def write(name: str, obj: dict) -> bool:
    """Atomically persist ``obj`` for ``name``. False on any failure."""
    return hio.atomic_write_json(path(name), obj)
