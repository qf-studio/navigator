#!/usr/bin/env python3
"""hooks/ops/session_start — SessionStart injector (TASK-61 Phase 1).

Byte-parity port of hooks/nav_session_start.py: identical section builders,
section ordering, header, and char-budget truncation. Only the delivery
moved — the op returns ``additional_context`` and the dispatcher wraps it in
the SessionStart hookSpecificOutput envelope, byte-identical to the v6 doc
(proven by tests/golden/test_parity.py). v6's failure-path stderr
diagnostics are dropped: ops never write stderr (mem-034; sentinels owns the
only emitter) and the parity gate covers stdout + exit code.

New in v7 (sanctioned by TASK-61 — internal state files only): the three v6
per-hook state files are ARCHIVED (copied, never deleted, first snapshot
wins) to .agent/.nav-v6-state.bak/ — the schema-2 runtime state file
replaces them as a clean break. .agent/.context-markers/ is user save-point
data, NOT session-scoped state: this op only ever reads it (test-asserted).

Belt note: the op applies the v6 session_start_hook.char_budget truncation
(default 9500, footer "[truncated: ask nav-start for full detail]") BEFORE
returning; the runtime's budget.clamp(SessionStart)=9500 belt only re-cuts
when a user config raises char_budget above 9500.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# The dispatcher shim puts hooks/ on sys.path; colocated tests pin it too.
from nav_hook_lib import config, hio

SENTINEL = "<!-- nav-session-start-injected:v1 -->"
CHAR_BUDGET = 9500  # v6 default; leaves headroom under Claude Code's 10k cap
TRUNCATION_FOOTER = "\n\n[truncated: ask nav-start for full detail]"

DEFAULT_SECTIONS = (
    "navigator", "marker", "config", "graph", "profile", "tasks", "auto_update",
)

# v6 per-hook state files replaced by .agent/.nav-runtime-state.json (schema 2).
LEGACY_STATE_FILES = (
    ".nav-workflow-state.json",
    ".nav-read-counter.json",
    ".nav-profile-sync-state.json",
)
ARCHIVE_DIR_NAME = ".nav-v6-state.bak"


# ---------------------------------------------------------------------------
# Legacy state archival (v7 clean break — copy, never delete, idempotent)
# ---------------------------------------------------------------------------

def _archive_legacy_state(agent_dir: Path) -> None:
    """Copy the v6 per-hook state files into .nav-v6-state.bak/.

    Never deletes the sources; an existing archive copy is never overwritten
    (first snapshot wins — the archive is a v6 keepsake, not a mirror), so
    repeated session starts are idempotent. Best-effort: any failure is
    swallowed — archival must never cost the user their context injection.
    """
    try:
        sources = [agent_dir / name for name in LEGACY_STATE_FILES]
        sources = [source for source in sources if source.is_file()]
        if not sources:
            return
        archive_dir = agent_dir / ARCHIVE_DIR_NAME
        archive_dir.mkdir(parents=True, exist_ok=True)
        for source in sources:
            destination = archive_dir / source.name
            if destination.exists():
                continue
            shutil.copy2(source, destination)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Section builders (verbatim v6 ports; stderr diagnostics dropped)
# ---------------------------------------------------------------------------

def _section_navigator(root: Path):
    nav = hio.safe_read(root / ".agent" / "DEVELOPMENT-README.md", max_bytes=8_000)
    if not nav:
        return None
    return f"## Navigator Index (.agent/DEVELOPMENT-README.md)\n\n{nav}"


def _section_active_marker(root: Path):
    active = root / ".agent" / ".context-markers" / ".active"
    name = hio.safe_read(active, max_bytes=200)
    if not name:
        return None
    name = name.strip()
    if not name:
        return None
    marker_file = root / ".agent" / ".context-markers" / name
    body = hio.safe_read(marker_file, max_bytes=6_000)
    if not body:
        return f"## Active Marker\n\n`{name}` referenced but file missing."
    return (
        f"## Active Marker: `{name}`\n\n"
        f"User was working on this before compact. Offer to resume.\n\n"
        f"{body}"
    )


def _section_config(root: Path):
    # RAW user config on purpose (not ctx.config): v6 summarized the file as
    # written — layered defaults would fill absent keys and change the bytes.
    cfg = hio.safe_json(root / ".agent" / ".nav-config.json")
    if not cfg:
        return None
    summary = {
        "version": cfg.get("version"),
        "project_management": cfg.get("project_management"),
        "task_prefix": cfg.get("task_prefix"),
        "team_chat": cfg.get("team_chat"),
        "loop_mode": (cfg.get("loop_mode") or {}).get("enabled"),
        "task_mode": (cfg.get("task_mode") or {}).get("enabled"),
        "knowledge_graph": (cfg.get("knowledge_graph") or {}).get("enabled"),
        "tom_features": cfg.get("tom_features"),
        "auto_update": (cfg.get("auto_update") or {}).get("enabled"),
    }
    return (
        "## Navigator Config (.agent/.nav-config.json)\n\n"
        f"```json\n{json.dumps(summary, indent=2)}\n```"
        + _judge_notice(cfg.get("judge"))
    )


def _judge_notice(block) -> str:
    """One line (or a setup hint) when the typed judge is enabled (TASK-79).

    Silent unless the raw config enables the judge, so the v6 config bytes are
    untouched for everyone else. Names the key *source*, never the key.
    """
    if not isinstance(block, dict) or not block.get("enabled"):
        return ""
    try:
        from nav_hook_lib import judge
        cfg_settings = judge.settings({"judge": block})
        source = judge.key_source(cfg_settings)
        if source:
            return f"\n\nTyped judge: on ({cfg_settings.get('model')}, key from {source})."
        return ("\n\n⚠️  Typed judge is enabled but no API key was found — the keyword "
                "heuristics are answering. " + judge.setup_hint(cfg_settings))
    except Exception:
        return ""


def _section_user_profile(root: Path):
    profile = hio.safe_json(root / ".agent" / ".user-profile.json")
    if not profile:
        return None
    prefs = profile.get("preferences", {})
    corrections = profile.get("corrections", [])
    goals = profile.get("goals", [])
    body = {
        "preferences": prefs,
        "recent_corrections": corrections[-5:] if corrections else [],
        "goals": goals[-5:] if goals else [],
    }
    return (
        "## User Profile (Theory of Mind)\n\n"
        "Apply these preferences for this session.\n\n"
        f"```json\n{json.dumps(body, indent=2, default=str)}\n```"
    )


def _section_graph_stats(root: Path, plugin_dir):
    graph_path = root / ".agent" / "knowledge" / "graph.json"
    if not graph_path.is_file():
        return None
    if plugin_dir is None:
        return ("## Knowledge Graph\n\nGraph present at "
                f"{graph_path} (stats unavailable: plugin dir unknown).")
    manager = plugin_dir / "skills" / "nav-graph" / "functions" / "graph_manager.py"
    if not manager.is_file():
        return "## Knowledge Graph\n\nGraph present (stats helper not found)."
    try:
        out = subprocess.run(
            [
                sys.executable,
                str(manager),
                "--action",
                "stats",
                "--graph-path",
                str(graph_path),
            ],
            capture_output=True,
            text=True,
            timeout=4,
        )
        text = (out.stdout or "").strip()
        if not text:
            return None
        return f"## Knowledge Graph Stats\n\n```\n{text[:1500]}\n```"
    except Exception:
        return None


def _section_auto_update(root: Path, plugin_dir):
    """Read-only version-drift notice (v6 --check-drift mode, never mutating)."""
    if plugin_dir is None:
        return None
    updater = plugin_dir / "skills" / "nav-start" / "functions" / "auto_updater.py"
    if not updater.is_file():
        return None
    config_path = root / ".agent" / ".nav-config.json"
    try:
        out = subprocess.run(
            [
                sys.executable,
                str(updater),
                "--check-drift",
                "--config-path",
                str(config_path),
            ],
            capture_output=True,
            text=True,
            timeout=4,
        )
        raw = (out.stdout or "").strip()
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not data.get("has_drift"):
            return None
        message = data.get("message") or "Navigator version drift detected."
        return f"## Auto-Update\n\n⚠️  {message}"
    except Exception:
        return None


def _section_open_tasks(root: Path):
    tasks_dir = root / ".agent" / "tasks"
    if not tasks_dir.is_dir():
        return None
    entries = []
    try:
        for path in sorted(tasks_dir.glob("*.md")):
            if path.name.upper().startswith("README"):
                continue
            head = hio.safe_read(path, max_bytes=600) or ""
            title = next(
                (
                    line.lstrip("# ").strip()
                    for line in head.splitlines()
                    if line.startswith("#")
                ),
                path.stem,
            )
            status = "open"
            for line in head.splitlines():
                low = line.lower()
                if "status" in low and ":" in low:
                    status = line.split(":", 1)[1].strip().strip("*` ")
                    break
            entries.append(f"- `{path.name}` — {title} [{status}]")
            if len(entries) >= 20:
                entries.append("- … (more in .agent/tasks/)")
                break
    except Exception:
        return None
    if not entries:
        return None
    return "## Open Tasks\n\n" + "\n".join(entries)


def _section_relevant_memories(root: Path, plugin_dir, limit: int):
    """Graph memories relevant to open tasks + active marker (v6 verbatim)."""
    graph_path = root / ".agent" / "knowledge" / "graph.json"
    if not graph_path.is_file() or plugin_dir is None:
        return None
    recall = plugin_dir / "skills" / "nav-graph" / "functions" / "memory_recall.py"
    if not recall.is_file():
        return None
    try:
        out = subprocess.run(
            [
                sys.executable,
                str(recall),
                "--auto",
                "--agent-dir",
                str(root / ".agent"),
                "--graph-path",
                str(graph_path),
                "--limit",
                str(limit),
                "--format",
                "compact",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        text = (out.stdout or "").strip()
        if not text:
            return None
        return (
            "## Relevant Memories\n\n"
            "Prior knowledge matching your open tasks/marker — factor these "
            "in before planning.\n\n" + text[:1200]
        )
    except Exception:
        return None


def _resolve_plugin_dir():
    env = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_DIR")
    if env:
        path = Path(env)
        if path.is_dir():
            return path
    home_plugins = Path.home() / ".claude" / "plugins"
    candidates = [
        home_plugins / "cache" / "navigator-marketplace" / "navigator",
        home_plugins / "marketplaces" / "navigator-marketplace",
    ]
    for candidate in candidates:
        if (candidate / "skills" / "nav-start").is_dir():
            return candidate
    # File-relative fallback: hooks/ops/session_start.py -> repo root.
    here = Path(__file__).resolve().parent.parent.parent
    if (here / "skills" / "nav-start").is_dir():
        return here
    return None


# ---------------------------------------------------------------------------
# Body assembly (v6 _build_payload minus the root/enabled guards the
# dispatcher already owns: .agent presence and session_start_hook.enabled)
# ---------------------------------------------------------------------------

def _build_body(ctx, root: Path):
    cfg = ctx.config
    include_sections = config.get(
        cfg, "session_start_hook.include_sections", list(DEFAULT_SECTIONS))
    char_budget = int(config.get(cfg, "session_start_hook.char_budget", CHAR_BUDGET))
    surface_memories = bool(
        config.get(cfg, "knowledge_graph.auto_surface_relevant", True))
    max_memories = int(config.get(cfg, "knowledge_graph.max_session_memories", 5))

    plugin_dir = _resolve_plugin_dir()
    source = ctx.payload.get("source") or "startup"
    sections_enabled = set(include_sections)

    header_lines = [
        SENTINEL,
        "# Navigator Session Start",
        f"_source: {source}_",
        "",
        (
            "This block was injected by the SessionStart hook — Navigator content "
            "is already in your context. Do NOT re-Read these files. Render the "
            "session summary directly from this data."
        ),
        "",
    ]
    if source == "resume":
        header_lines.insert(
            2, "**RESUMED FROM PREVIOUS SESSION** — prioritize active marker.")

    sections = []

    def add(name, builder):
        if name not in sections_enabled:
            return
        try:
            out = builder()
        except Exception:
            return
        if out:
            sections.append(out)

    # Order: small high-signal sections first, navigator (biggest) last so
    # truncation eats its tail rather than dropping config/profile/graph.
    # On resume, marker also hoisted to top.
    if source == "resume":
        add("marker", lambda: _section_active_marker(root))
    add("config", lambda: _section_config(root))
    add("auto_update", lambda: _section_auto_update(root, plugin_dir))
    add("graph", lambda: _section_graph_stats(root, plugin_dir))
    if surface_memories:
        sections_enabled.add("memories")
        add("memories", lambda: _section_relevant_memories(
            root, plugin_dir, max_memories))
    add("profile", lambda: _section_user_profile(root))
    add("tasks", lambda: _section_open_tasks(root))
    if source != "resume":
        add("marker", lambda: _section_active_marker(root))
    add("navigator", lambda: _section_navigator(root))

    body = "\n".join(header_lines) + "\n\n" + "\n\n---\n\n".join(sections)

    if len(body) > char_budget:
        body = body[: char_budget - len(TRUNCATION_FOOTER)] + TRUNCATION_FOOTER
    return body


def run(ctx):
    root = hio.project_root(ctx.payload)
    agent_dir = root / ".agent"
    if not agent_dir.is_dir():
        return None
    _archive_legacy_state(agent_dir)
    body = _build_body(ctx, root)
    if not body:
        return None
    return {"additional_context": body}
