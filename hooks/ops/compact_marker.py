#!/usr/bin/env python3
"""hooks/ops/compact_marker — Pre/PostCompact recorder (TASK-61 Phase 2).

Byte-parity port of hooks/nav_pre_compact.py + hooks/nav_post_compact.py in
one op file; ``run(ctx)`` branches on ``ctx.event``. Marker behavior is
unchanged (markers stay the channel per the routing matrix):

  - PreCompact: write a heuristic marker (git state, active tasks,
    transcript summary) to .agent/.context-markers/ and point .active at it.
  - PostCompact: append Claude Code's compact summary to the marker .active
    names; silently no-op when PreCompact never fired.

Both branches return ``{"ack": True}`` — the runtime then emits the bare
``{}`` doc the v6 hooks printed (golden parity). Timestamps come from
``ctx.now`` (runtime-injected) for testability; v6 used datetime.now().
v6's stderr diagnostics are dropped (mem-034: ops never write stderr).
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

# The dispatcher shim puts hooks/ on sys.path; colocated tests pin it too.
from nav_hook_lib import config, hio

NO_SUMMARY_PLACEHOLDER = "_[no summary provided by Claude Code]_"

# Path-shaped token: a slash/word run ending in a known source extension at a
# word boundary. Real path characters must precede the dot, so prose like
# "see the .py docs" is NOT captured while "hooks/token_monitor.py" is.
_PATH_RE = re.compile(r"[\w./-]+\.(?:tsx|json|md|ts|py|sh|js)\b")

PRE_COMPACT_NOTE = (
    "_Written by Navigator PreCompact hook. The companion PostCompact hook "
    "will append Claude Code's summary below once compact completes._"
)


def _local_dt(ctx) -> datetime:
    """ctx.now (epoch seconds) as a local naive datetime — v6 datetime.now()."""
    return datetime.fromtimestamp(float(ctx.now))


# ---------------------------------------------------------------------------
# Heuristic transcript summarization (v6 nav_pre_compact verbatim; mirrors
# skills/nav-marker/functions/marker_compressor.py)
# ---------------------------------------------------------------------------

def _flatten_transcript(transcript_path: Path) -> str:
    """Read the JSONL transcript and flatten to plain text for heuristic scan.

    Deliberately NOT nav_hook_lib.transcript: that reader drops raw non-JSON
    lines and tool input/output blocks this flatten keeps (v6 parity).
    """
    if not transcript_path.is_file():
        return ""
    lines_out = []
    try:
        with transcript_path.open("r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    lines_out.append(raw)
                    continue
                # Claude Code transcripts: nested message.content, various shapes
                msg = obj.get("message") or obj
                content = msg.get("content") if isinstance(msg, dict) else None
                if isinstance(content, str):
                    lines_out.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            text = (block.get("text") or block.get("input")
                                    or block.get("output"))
                            if isinstance(text, str):
                                lines_out.append(text)
                            elif text is not None:
                                lines_out.append(
                                    json.dumps(text, default=str)[:2000])
    except Exception:
        return ""
    return "\n".join(lines_out)


def _compress_context(text: str, max_length: int = 5000) -> str:
    """Heuristic compressor — files/code/errors/recent context (v6 verbatim)."""
    if not text:
        return "_[transcript unavailable]_"

    lines = text.split("\n")
    # Sample head + tail so paths/markers from both the conversation's start
    # (task setup) and end (recent work) survive; only the mid-section is
    # dropped when the transcript is long.
    scan_lines = lines[:100] + lines[-100:] if len(lines) > 200 else lines

    code_blocks = []
    file_paths = []
    errors = []

    in_code_block = False
    code_buffer = []

    for line in scan_lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code_block:
                code_blocks.append("\n".join(code_buffer))
                code_buffer = []
            in_code_block = not in_code_block
        elif in_code_block:
            code_buffer.append(line)

        file_paths.extend(_PATH_RE.findall(line))

        low = line.lower()
        if "error" in low or "failed" in low or "traceback" in low:
            errors.append(stripped)

    # "Recent" = the true tail of the transcript, independent of sampling.
    recent_context = lines[-20:]

    parts = []
    if file_paths:
        unique = list(dict.fromkeys(file_paths))[:10]
        parts.append("**Files/paths mentioned**:\n" + "\n".join(unique))
    if code_blocks:
        parts.append(
            "**Code snippets**:\n```\n" + "\n\n".join(code_blocks[:3]) + "\n```")
    if errors:
        unique_err = list(dict.fromkeys(errors))[:5]
        parts.append("**Errors / issues**:\n" + "\n".join(unique_err))
    parts.append("**Recent conversation**:\n" + "\n".join(recent_context))

    compressed = "\n\n---\n\n".join(parts)
    if len(compressed) > max_length:
        compressed = compressed[:max_length] + "\n\n[... truncated ...]"
    return compressed


# ---------------------------------------------------------------------------
# Git state capture (v6 verbatim, minus stderr diagnostics)
# ---------------------------------------------------------------------------

def _git(args: list, cwd: Path):
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=3,
        )
        if out.returncode != 0:
            return None
        return out.stdout.strip()
    except Exception:
        return None


def _git_state(root: Path) -> str:
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], root) or "(unknown)"
    head = _git(["log", "-1", "--oneline"], root) or "(no commits)"
    status = _git(["status", "--short"], root) or ""
    recent = _git(["log", "--oneline", "-5"], root) or ""

    parts = [
        f"**Branch**: `{branch}`",
        f"**HEAD**: `{head}`",
    ]
    if status:
        parts.append("**Working tree**:\n```\n" + status + "\n```")
    else:
        parts.append("**Working tree**: clean")
    if recent:
        parts.append("**Recent commits**:\n```\n" + recent + "\n```")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Active task hint (v6 verbatim)
# ---------------------------------------------------------------------------

# The `**Status**:` / `**Status:**` / `Status:` line, tolerant like task_to_graph.py.
_STATUS_LINE = re.compile(
    r"(?im)^[>\s]*\*{0,2}\s*status\s*\*{0,2}\s*:\s*\*{0,2}\s*(.+?)\s*$"
)
_IN_PROGRESS_WORDS = re.compile(r"\bin[ -]progress\b", re.IGNORECASE)


def is_in_progress(text: str) -> bool:
    """True when a task doc is in progress (TASK-91).

    With a Status line only that line decides (🚧 or the phrase "in progress"), so prose
    that quotes the phrase elsewhere — TASK-67's own doc does — no longer counts. Docs
    without a Status line keep the legacy whole-head scan. Mirrored in
    hooks/mod/lib/tasks.ts.
    """
    match = _STATUS_LINE.search(text)
    if match:
        value = match.group(1)
        return "🚧" in value or bool(_IN_PROGRESS_WORDS.search(value))
    low = text.lower()
    return "in progress" in low or "in-progress" in low or "🚧" in text


def _active_task_hint(root: Path):
    tasks_dir = root / ".agent" / "tasks"
    if not tasks_dir.is_dir():
        return None
    candidates = []
    try:
        for path in sorted(tasks_dir.glob("*.md")):
            if path.name.upper().startswith("README"):
                continue
            head = hio.safe_read(path, max_bytes=400) or ""
            if is_in_progress(head):
                title = next(
                    (
                        line.lstrip("# ").strip()
                        for line in head.splitlines()
                        if line.startswith("#")
                    ),
                    path.stem,
                )
                candidates.append(f"- `{path.name}` — {title}")
            if len(candidates) >= 5:
                break
    except Exception:
        return None
    if not candidates:
        return None
    return "**In-progress tasks**:\n" + "\n".join(candidates)


# ---------------------------------------------------------------------------
# PreCompact branch
# ---------------------------------------------------------------------------

def _build_marker(ctx, root: Path, cfg: dict):
    """Return (filename, body) for the marker file (v6 _build_marker)."""
    payload = ctx.payload
    trigger = payload.get("trigger") or "manual"
    if trigger not in ("manual", "auto"):
        trigger = "manual"
    session_id = payload.get("session_id") or "unknown"
    now_dt = _local_dt(ctx)
    ts = now_dt.strftime("%Y-%m-%d-%H%M")
    filename = f"before-compact-{trigger}-{ts}.md"

    if trigger == "manual":
        trigger_desc = "user ran /compact"
    else:
        trigger_desc = "Claude Code auto-compacted"
    header_lines = [
        f"# Before Compact ({trigger})",
        "",
        f"**Date**: {now_dt.isoformat(timespec='seconds')}",
        f"**Trigger**: `{trigger}` ({trigger_desc})",
        f"**Session**: `{session_id}`",
        "",
        PRE_COMPACT_NOTE,
        "",
    ]

    sections = ["\n".join(header_lines)]

    if cfg["include_git_state"]:
        sections.append("## Git State\n\n" + _git_state(root))

    task_hint = _active_task_hint(root)
    if task_hint:
        sections.append("## Active Tasks\n\n" + task_hint)

    if cfg["include_transcript_summary"]:
        tpath_raw = payload.get("transcript_path")
        if tpath_raw:
            tpath = Path(tpath_raw).expanduser()
            flat = _flatten_transcript(tpath)
            summary = _compress_context(flat, max_length=cfg["char_budget"] - 1000)
        else:
            summary = "_[transcript_path not provided]_"
        sections.append("## Conversation Summary (heuristic)\n\n" + summary)

    body = "\n\n---\n\n".join(sections) + "\n"
    if len(body) > cfg["char_budget"]:
        body = body[: cfg["char_budget"] - 60] + "\n\n[... truncated to char budget ...]\n"
    return filename, body


def _pre_compact(ctx, root: Path) -> dict:
    cfg = {
        "include_transcript_summary": bool(config.get(
            ctx.config, "compact_hook.include_transcript_summary", True)),
        "include_git_state": bool(config.get(
            ctx.config, "compact_hook.include_git_state", True)),
        "char_budget": int(config.get(ctx.config, "compact_hook.char_budget", 8000)),
    }
    try:
        markers_dir = root / ".agent" / ".context-markers"
        markers_dir.mkdir(parents=True, exist_ok=True)

        filename, body = _build_marker(ctx, root, cfg)
        (markers_dir / filename).write_text(body, encoding="utf-8")
        (markers_dir / ".active").write_text(filename + "\n", encoding="utf-8")
    except Exception:
        pass  # v6 posture: a marker-write failure never blocks compact
    return {"ack": True}


# ---------------------------------------------------------------------------
# PostCompact branch
# ---------------------------------------------------------------------------

def _post_compact(ctx, root: Path) -> dict:
    append_enabled = bool(config.get(
        ctx.config, "compact_hook.append_post_compact_summary", True))
    if not append_enabled:
        return {"ack": True}

    markers_dir = root / ".agent" / ".context-markers"
    active_name = hio.safe_read(markers_dir / ".active", max_bytes=200)
    if not active_name:
        return {"ack": True}  # PreCompact didn't fire — nothing to append to

    active_name = active_name.strip()
    marker_path = markers_dir / active_name
    if not marker_path.is_file():
        return {"ack": True}

    summary = ctx.payload.get("compact_summary") or NO_SUMMARY_PLACEHOLDER
    if isinstance(summary, (dict, list)):
        summary = json.dumps(summary, indent=2, default=str)
    summary = str(summary).strip()

    appended_at = _local_dt(ctx).isoformat(timespec="seconds")
    try:
        with marker_path.open("a", encoding="utf-8") as fh:
            fh.write("\n\n---\n\n")
            fh.write("## Compact Summary (Claude Code)\n\n")
            fh.write(f"_Appended by PostCompact hook at {appended_at}._\n\n")
            fh.write(summary + "\n")
    except Exception:
        pass
    return {"ack": True}


def run(ctx):
    root = hio.project_root(ctx.payload)
    if not (root / ".agent").is_dir():
        return None
    if ctx.event == "PreCompact":
        return _pre_compact(ctx, root)
    if ctx.event == "PostCompact":
        return _post_compact(ctx, root)
    return None
