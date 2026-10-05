"""Reject log — one JSONL line per refusal the runtime makes (TASK-88).

Navigator gates deterministically (read guard deny, prompt gate exit 2, stop
gate block) but until v8.2 kept only tallies: no reason, no time. A refusing
op attaches a ``reject`` summary to its blocking result; ``runtime._dispatch``
(and the mod's ``runOps``) strips that key before the merge and appends ONE
line here. The file never enters the model's context: it is read by humans
(``grep``, ``tail``) and by the ``/nav`` pane.

Line shape (fixed key order; the mod produces the identical bytes):

    {"ts": "...", "session": "...", "event": "Stop", "op": "stop_completion",
     "tool": "Read"?, "reason": "...", "evidence": {...}, "suppressed": true?}

``tool`` appears on tool events only; ``suppressed`` only when the refusal
was computed under Pilot and the merge belt stripped it (Pilot is the
autonomous case that needs the record most). Bounded: once the file passes
``REWRITE_AT`` lines it is rewritten with the newest ``KEEP_LINES``.
"""
from __future__ import annotations

import json
from pathlib import Path

try:
    from . import hio
except ImportError:  # top-level module under per-directory unittest discovery
    import hio

REJECTS_FILE_NAME = ".nav-rejects.jsonl"
REJECTS_PATH = ".agent/" + REJECTS_FILE_NAME
KEEP_LINES = 500
REWRITE_AT = 600


def line(ts: str, session, event: str, op: str, tool, reject: dict,
         suppressed: bool = False) -> str:
    """Serialize one refusal; compact separators match JSON.stringify byte for byte."""
    doc: dict = {"ts": ts, "session": session, "event": event, "op": op}
    if isinstance(tool, str) and tool:
        doc["tool"] = tool
    doc["reason"] = str(reject.get("reason") or "")
    evidence = reject.get("evidence")
    doc["evidence"] = evidence if isinstance(evidence, dict) else {}
    if suppressed:
        doc["suppressed"] = True
    return json.dumps(doc, separators=(",", ":"), ensure_ascii=False)


def append(agent_dir, text: str) -> bool:
    """Append one line; rewrite with the newest KEEP_LINES once past REWRITE_AT."""
    path = Path(agent_dir) / REJECTS_FILE_NAME
    try:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError:
        existing = ""
    lines = [ln for ln in existing.split("\n") if ln]
    lines.append(text)
    if len(lines) > REWRITE_AT:
        lines = lines[-KEEP_LINES:]
    return hio.atomic_write_text(path, "\n".join(lines) + "\n")
