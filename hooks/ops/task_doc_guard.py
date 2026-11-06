#!/usr/bin/env python3
"""task_doc_guard op — hand-written task doc gate (GH-40).

PreToolUse gate (matcher ``Write|Edit|Bash|Skill``). The workflow says a task
doc under ``.agent/tasks/`` comes from ``/nav-task`` (recall step, template, ID
from the generator); nothing enforced it, and a session wrote a doc with a Bash
heredoc and skipped the recall. This op closes that:

  - ``Skill`` branch (recorder): when ``tool_input.skill`` ends with
    ``nav-task`` (``nav-task``, ``navigator:nav-task``), set
    ``state['skills'].nav_task_ran = true``. ``skills`` is session-scoped
    (state.SESSION_SCOPED_SECTIONS), so a new session starts with it false.
  - ``Write``/``Edit`` branch: the gate fires when ``tool_input.file_path`` is a
    NEW file (does not exist yet) directly under ``.agent/tasks/`` whose name
    matches ``^{task_prefix}-\\d+.*\\.md$``.
  - ``Bash`` branch: the same test on the targets of a redirect (``>``, ``>>``,
    heredoc ``cat > f <<EOF``), ``tee``, ``cp`` and ``mv`` in the command.

Editing an existing doc is allowed, and so is anything outside
``.agent/tasks/`` itself (``.agent/tasks/archive/`` included: ``mv`` into the
archive is how a finished doc is filed).

``strict_block`` true (default) → exit 2 + sentinel-wrapped stderr, the
deny-only channel (mem-035/mem-054: no advisory stdout). ``strict_block``
false → stderr advisory, exit 0. ``ctx.pilot_executor`` short-circuits the
whole op (PILOT passthrough, as prompt_gate): the executor writes its own
task docs.

``.agent/`` presence and ``task_doc_guard_hook.enabled`` are runtime-owned
(dispatch early-out + OpSpec.config_key).
"""
from __future__ import annotations

import re
import shlex
from pathlib import Path

from nav_hook_lib import config, hio, sentinels

SKILL_SUFFIX = "nav-task"
MAX_NAME_CHARS = 120

# Heredoc bodies are data, not commands: a `> .agent/tasks/TASK-1.md` line
# inside one must not trip the Bash scan. Drops from the line after the
# `<<[-]'TAG'` opener through the closing TAG line.
_HEREDOC = re.compile(
    r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?(?:\n[ \t]*\2[ \t]*(?=\n|$)|\Z)", re.DOTALL
)
# `>` / `>>` redirect (also `2>`, `&>`; not `>&2`, not a heredoc `<<`).
_REDIRECT = re.compile(r"(?<![<>])(?:\d*|&)>>?\s*(\"[^\"\n]+\"|'[^'\n]+'|[^\s\"'<>|;&()]+)")
_SEGMENT_SPLIT = re.compile(r"\|\||&&|[;|\n]")


def _task_pattern(cfg):
    prefix = config.get(cfg, "task_prefix", "TASK")
    if not isinstance(prefix, str) or not prefix:
        prefix = "TASK"
    return re.compile(r"^" + re.escape(prefix) + r"-\d+.*\.md$")


def _is_new_task_doc(raw: str, root: Path, pattern) -> str | None:
    """Basename when ``raw`` names a not-yet-existing task doc directly under
    ``.agent/tasks/``, else None."""
    raw = raw.strip()
    if not raw or "$" in raw or "`" in raw:
        return None  # unresolvable shell expansion: cannot be judged, allow
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        resolved = path.resolve()
        tasks_dir = (root / ".agent" / "tasks").resolve()
        if resolved.parent != tasks_dir or not pattern.match(resolved.name):
            return None
        if resolved.exists():
            return None  # editing an existing doc is allowed
    except OSError:
        return None
    return resolved.name


def _unquote(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]
    return token


def _segment_tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def _bash_targets(command: str) -> list[str]:
    """Candidate write targets in a shell command: redirects, tee, cp, mv."""
    command = _HEREDOC.sub("", command)
    targets = [_unquote(m.group(1)) for m in _REDIRECT.finditer(command)]
    for segment in _SEGMENT_SPLIT.split(command):
        tokens = _segment_tokens(segment)
        while tokens and ("=" in tokens[0] or tokens[0] in ("sudo", "command", "env")):
            tokens = tokens[1:]  # VAR=x prefixes and wrappers
        if not tokens:
            continue
        args = [t for t in tokens[1:] if not t.startswith("-")]
        head = Path(tokens[0]).name
        if head == "tee":
            targets.extend(args)
        elif head in ("cp", "mv") and len(args) >= 2:
            targets.append(args[-1])
    return targets


def _target_task_doc(payload, root: Path, pattern) -> str | None:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    tool = payload.get("tool_name")
    if tool in ("Write", "Edit"):
        file_path = tool_input.get("file_path")
        if isinstance(file_path, str):
            return _is_new_task_doc(file_path, root, pattern)
        return None
    if tool == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str):
            return None
        for target in _bash_targets(command):
            name = _is_new_task_doc(target, root, pattern)
            if name:
                return name
    return None


def _record_skill(ctx) -> None:
    tool_input = ctx.payload.get("tool_input")
    skill = tool_input.get("skill") if isinstance(tool_input, dict) else None
    if not isinstance(skill, str) or not skill.strip().endswith(SKILL_SUFFIX):
        return
    skills = ctx.state.get("skills")
    if not isinstance(skills, dict):
        skills = {}
    skills["nav_task_ran"] = True
    ctx.state["skills"] = skills


def _safe_name(name: str) -> str:
    cleaned = "".join(ch for ch in name if ch.isprintable())
    return cleaned[:MAX_NAME_CHARS]


def _block_text(name: str) -> str:
    body = (
        f"Navigator task-doc-guard: {_safe_name(name)} is a new task doc written "
        "by hand.\n"
        "  Why: task docs come from /nav-task (it recalls related memories, "
        "fills the template and takes the ID from the generator). "
        "/nav-task has not run in this session.\n"
        "  How to proceed (your choice):\n"
        "    1. Run /nav-task, then write the doc it prepares.\n"
        "    2. Disable strict enforcement: set "
        "task_doc_guard_hook.strict_block=false in .agent/.nav-config.json.\n"
        "    3. Disable the guard: set task_doc_guard_hook.enabled=false."
    )
    return sentinels.wrap("nav-task-doc-guard-block", body)


def run(ctx):
    if ctx.pilot_executor:
        return None  # PILOT passthrough: the executor writes its own task docs

    payload = ctx.payload
    tool = payload.get("tool_name")
    if tool == "Skill":
        _record_skill(ctx)
        return None
    if tool not in ("Write", "Edit", "Bash"):
        return None  # defensive: the registry matcher already restricts the tools

    skills = ctx.state.get("skills")
    if isinstance(skills, dict) and skills.get("nav_task_ran") is True:
        return None

    root = hio.project_root(payload)
    name = _target_task_doc(payload, root, _task_pattern(ctx.config))
    if name is None:
        return None

    if config.get(ctx.config, "task_doc_guard_hook.strict_block", True):
        return {
            "exit_code": 2,
            "stderr": _block_text(name),
            "reject": {
                "reason": "new task doc written without /nav-task this session",
                "evidence": {"tool": tool, "file": _safe_name(name)},
            },
        }
    return {"stderr": (
        f"[nav-task-doc-guard] {_safe_name(name)} is a new task doc written by hand; "
        "/nav-task has not run this session. Run /nav-task for the recall step, "
        "the template and a generated ID."
    )}
