#!/usr/bin/env python3
"""graph_sync op — task doc → knowledge-graph sync (TASK-61 Phase 3).

Parity port of hooks/nav_task_graph_sync.py. PostToolUse recorder: when an
Edit/Write call touched `.agent/tasks/TASK-*.md` and the knowledge graph is
initialized, runs `task_to_graph.py --action add` (upsert by node_id, per the
v6 Q1 verification) in a subprocess. Pure side effect.

v6 fidelity:
  - The registry matcher is coarse (Edit|Write|MultiEdit|NotebookEdit) but the
    v6 manifest fired on Edit|Write only — this op filters back down to that
    surface. MultiEdit and NotebookEdit payloads (the latter carry
    ``notebook_path``, not ``file_path``) are skipped silently: v6 never saw
    them, so the op emits nothing for them.
  - v6 printed a bare ``{}`` doc on every Edit|Write branch; ``{"ack": True}``
    reproduces that byte shape (golden: graph_sync.json).
  - stderr diagnostics keep the v6 message text and route through the result
    ``stderr`` key — nav_hook_lib.sentinels owns the only emitter (mem-034).
  - ``.agent/`` presence and ``task_graph_sync_hook.enabled`` gates are
    runtime-owned (dispatch early-out + OpSpec.config_key).

No ctx.pilot_executor check on purpose: v6 ran this hook under Pilot too (it
blocks nothing), and the runtime belt covers blocking keys anyway.

TASK-62 Phase 5 extension — TaskCreated/TaskCompleted lifecycle events (no
spike dependency; both EVENT registrations survived the validate-or-drop step
on CC 2.1.205): a dedicated event branch pulls a task-doc path from the
lifecycle payload (shape not harness-pinned, hence the defensive key sweep)
and runs the same upsert. No path resolvable to ``.agent/tasks/TASK-*.md`` ⇒
silent — the v6 `{}` ack contract belongs to the PostToolUse surface only.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from nav_hook_lib import hio

# The exact v6 manifest surface; the coarse registry matcher is wider.
V6_TOOLS = frozenset({"Edit", "Write"})

# TASK-62: native lifecycle events feeding the graph (event-branch guarded).
LIFECYCLE_EVENTS = frozenset({"TaskCreated", "TaskCompleted"})

# Payload keys swept for a task-doc path on lifecycle events (shape unpinned).
LIFECYCLE_PATH_KEYS = ("task_path", "file_path", "path", "task_file")

# Any `<PREFIX>-<n>` doc: TASK-12, GH-57 (task_id_source: github, GH-32), LIN-9 …
TASK_PATH_RE = re.compile(r"\.agent/tasks/([A-Z][A-Z0-9]*[-_]\d+[\w\-.]*)\.md$")

SYNC_TIMEOUT_SECONDS = 8


def _resolve_plugin_dir() -> Path | None:
    """v6 _resolve_plugin_dir, with the file-relative fallback at op depth."""
    env = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_DIR")
    if env and Path(env).is_dir():
        return Path(env)
    candidates = [
        Path.home() / ".claude" / "plugins" / "cache" / "navigator-marketplace" / "navigator",
        Path.home() / ".claude" / "plugins" / "marketplaces" / "navigator-marketplace",
    ]
    for candidate in candidates:
        if (candidate / "skills" / "nav-graph").is_dir():
            return candidate
    here = Path(__file__).resolve().parent.parent.parent  # hooks/ops/ -> repo root
    if (here / "skills" / "nav-graph").is_dir():
        return here
    return None


def _validate_task_path(candidate, root: Path) -> Path | None:
    """Absolute task-doc path when ``candidate`` names one under root, else None."""
    if not isinstance(candidate, str) or not candidate:
        return None
    path = Path(candidate)
    if not path.is_absolute():
        path = root / candidate
    try:
        rel = path.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return None
    if not TASK_PATH_RE.search(rel.as_posix()):
        return None
    if not path.is_file():
        return None  # was deleted or never landed — nothing to sync
    return path


def _extract_task_path(payload: dict, root: Path) -> Path | None:
    """Absolute task-doc path when this tool call touched one, else None (v6 logic)."""
    tool_input = payload.get("tool_input") or {}
    return _validate_task_path(tool_input.get("file_path"), root)


def _lifecycle_task_path(payload: dict, root: Path) -> Path | None:
    """First payload candidate resolving to a task doc on a lifecycle event."""
    task = payload.get("task")
    sources = [payload] + ([task] if isinstance(task, dict) else [])
    for source in sources:
        for key in LIFECYCLE_PATH_KEYS:
            path = _validate_task_path(source.get(key), root)
            if path is not None:
                return path
    return None


def _sync(task_path: Path, graph_path: Path, stderr_lines: list) -> None:
    """Run task_to_graph.py; append v6-shaped diagnostics to stderr_lines."""
    plugin_dir = _resolve_plugin_dir()
    if plugin_dir is None:
        stderr_lines.append("nav_task_graph_sync: plugin dir not found")
        return
    syncer = plugin_dir / "skills" / "nav-graph" / "functions" / "task_to_graph.py"
    if not syncer.is_file():
        stderr_lines.append(f"nav_task_graph_sync: {syncer} missing")
        return
    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(syncer),
                "--action", "add",
                "--task-path", str(task_path),
                "--graph-path", str(graph_path),
            ],
            capture_output=True,
            text=True,
            timeout=SYNC_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        stderr_lines.append("nav_task_graph_sync: subprocess timeout")
        return
    except Exception as exc:
        stderr_lines.append(f"nav_task_graph_sync: subprocess failure: {exc}")
        return
    if proc.returncode != 0:
        stderr_lines.append(
            f"nav_task_graph_sync: sync failed (rc={proc.returncode}): "
            f"{(proc.stderr or proc.stdout).strip()[:300]}"
        )
    else:
        stderr_lines.append(f"nav_task_graph_sync: upserted {task_path.name}")


def _run_lifecycle(ctx):
    """TaskCreated/TaskCompleted branch: upsert the referenced task doc, if any."""
    payload = ctx.payload
    root = hio.project_root(payload)
    graph_path = root / ".agent" / "knowledge" / "graph.json"
    if not graph_path.is_file():
        return None  # no graph initialized — nothing to feed
    task_path = _lifecycle_task_path(payload, root)
    if task_path is None:
        return None  # payload names no task doc — silent (no v6 ack contract here)
    stderr_lines: list = []
    _sync(task_path, graph_path, stderr_lines)
    return {"stderr": "\n".join(stderr_lines)} if stderr_lines else None


def run(ctx):
    if ctx.event in LIFECYCLE_EVENTS:
        return _run_lifecycle(ctx)

    payload = ctx.payload
    if payload.get("tool_name") not in V6_TOOLS:
        return None  # MultiEdit/NotebookEdit: outside the v6 surface — silent skip

    result = {"ack": True}  # v6 printed {} on every Edit|Write branch
    stderr_lines: list = []
    root = hio.project_root(payload)

    graph_path = root / ".agent" / "knowledge" / "graph.json"
    if graph_path.is_file():  # no graph initialized — skip silently (v6)
        task_path = _extract_task_path(payload, root)
        if task_path is not None:
            _sync(task_path, graph_path, stderr_lines)

    if stderr_lines:
        result["stderr"] = "\n".join(stderr_lines)
    return result
