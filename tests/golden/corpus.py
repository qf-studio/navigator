#!/usr/bin/env python3
"""Golden-corpus plumbing shared by record_goldens.py and test_parity.py (TASK-61 Phase 0).

One corpus case per v6 hook surface. Each goldens/<surface>.json stores the VERBATIM
captured payload plus the v6 script's recorded stdout + exit code. Replays (recorder and
parity runner) rebuild a fresh tmp project from fixtures/ and rewrite exactly two payload
fields at run time — `cwd` (the capture-time scratch project no longer exists) and
`transcript_path` (points at fixtures/transcript.jsonl) — every other byte is untouched.

Environment discipline (see README.md):
  - HOME is pointed at an empty tmp dir so machine state (installed plugins, drift check)
    cannot leak into recorded or replayed output (keeps session_start deterministic).
  - CLAUDE_PROJECT_DIR / CLAUDE_USER_MESSAGE / PILOT_EXECUTOR / CLAUDE_PLUGIN_DIR are
    stripped: payload `cwd` is the only root signal, and PILOT_EXECUTOR would silence
    the UserPromptSubmit surfaces (mem-036 class of silent no-op).
  - CLAUDE_PLUGIN_ROOT is the repo root when "set"; the unset variant removes it
    (mem-036: both paths must be exercised).

Stdlib only.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

GOLDEN_DIR = Path(__file__).resolve().parent
REPO_ROOT = GOLDEN_DIR.parent.parent
GOLDENS = GOLDEN_DIR / "goldens"
FIXTURES = GOLDEN_DIR / "fixtures"
HOOKS_DIR = REPO_ROOT / "hooks"
DISPATCH = HOOKS_DIR / "nav_dispatch.py"

# The nine v6 hook surfaces (order = registry/manifest order within each event).
SURFACES: dict[str, dict[str, str]] = {
    "session_start": {"event": "SessionStart", "script": "nav_session_start.py"},
    "prompt_gate": {"event": "UserPromptSubmit", "script": "workflow_enforcer.py"},
    "prompt_brief": {"event": "UserPromptSubmit", "script": "nav_brief.py"},
    "read_guard": {"event": "PreToolUse", "script": "nav_read_guard.py"},
    "graph_sync": {"event": "PostToolUse", "script": "nav_task_graph_sync.py"},
    "profile_sync": {"event": "PostToolUse", "script": "nav_profile_sync.py"},
    "stop_state": {"event": "Stop", "script": "nav_workflow_state.py"},
    "pre_compact": {"event": "PreCompact", "script": "nav_pre_compact.py"},
    "post_compact": {"event": "PostCompact", "script": "nav_post_compact.py"},
}

# Env vars that must never leak from the developer machine into a corpus run.
STRIPPED_ENV_VARS = (
    "CLAUDE_PROJECT_DIR",
    "CLAUDE_USER_MESSAGE",
    "CLAUDE_PLUGIN_DIR",
    "PILOT_EXECUTOR",
)

RUN_TIMEOUT_SECONDS = 30


def load_golden(surface: str) -> dict:
    return json.loads((GOLDENS / f"{surface}.json").read_text(encoding="utf-8"))


def build_project(base: Path) -> Path:
    """Materialize a fresh scratch project (fixtures/agent -> .agent, notes.md)."""
    project = base / "project"
    shutil.copytree(FIXTURES / "agent", project / ".agent")
    shutil.copy2(FIXTURES / "notes.md", project / "notes.md")
    return project


def build_env(home: Path, plugin_root: str | None) -> dict:
    env = os.environ.copy()
    for var in STRIPPED_ENV_VARS:
        env.pop(var, None)
    env["HOME"] = str(home)
    # TASK-82: per-person settings never leak from the developer's machine.
    env["NAVIGATOR_CONFIG_HOME"] = str(home / ".config" / "navigator")
    env.pop("XDG_CONFIG_HOME", None)
    if plugin_root is None:
        env.pop("CLAUDE_PLUGIN_ROOT", None)
    else:
        env["CLAUDE_PLUGIN_ROOT"] = plugin_root
    return env


def rewrite_payload(payload: dict, project: Path) -> dict:
    """The ONLY sanctioned payload rewrites: capture-time cwd + transcript fixture path."""
    rewritten = dict(payload)
    if "cwd" in rewritten:
        rewritten["cwd"] = str(project)
    if "transcript_path" in rewritten:
        rewritten["transcript_path"] = str(FIXTURES / "transcript.jsonl")
    return rewritten


def run_case(argv: list, payload: dict, project: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *argv],
        input=json.dumps(rewrite_payload(payload, project)),
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT_SECONDS,
    )


def run_v6(surface: str, payload: dict, project: Path, env: dict) -> subprocess.CompletedProcess:
    script = HOOKS_DIR / SURFACES[surface]["script"]
    return run_case([str(script)], payload, project, env)


def run_dispatcher(event: str, payload: dict, project: Path,
                   env: dict) -> subprocess.CompletedProcess:
    return run_case([str(DISPATCH), event], payload, project, env)
