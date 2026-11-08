#!/usr/bin/env python3
"""Find the roadmap documents under one or more ``.agent/`` trees and render them as tables.

A roadmap is: a file whose name contains ``roadmap``; a task doc whose H1 contains
``roadmap``; or a program doc that a roadmap names as its ``Source plan`` / ``Task doc``.
Markers, archives and caches are skipped.

For each document the scanner reads the header region (first ``HEADER_LINES`` lines) and
reports: title, kind, the newest full date in the header, and the ``**Status**:`` or
``**As of**:`` value. Documents whose body is a ticket table (rows carrying ✅ 🚧 🎫 📋)
get a second table with counts per ``##`` section.

Kinds:
  live        – a plan still in use
  historical  – header carries a "historical doc" note
  stub        – header says the doc "Moved" elsewhere (pointer stub)
  program     – a task doc referenced by a roadmap as its source plan

Usage:
  roadmap_scan.py [--root .agent] [--also ../pilot/.agent ...] [--format md|json]
                  [--stale-days 30] [--today YYYY-MM-DD] [--excerpt 110]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

HEADER_LINES = 15
SKIP_PARTS = {".context-markers", "archive", "node_modules", "__pycache__", ".git"}
DATE_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
SHORT_DATE_RE = re.compile(r"(?<![\d-])(\d{2})-(\d{2})(?![\d-])")  # status lines write 11-04 for 2026-11-04
H1_RE = re.compile(r"^#\s+(.+?)\s*$")
STATUS_RE = re.compile(r"\*\*(Status|As of)\*\*\s*:\s*(.+)$")
SOURCE_RE = re.compile(r"\*\*(Source plan|Task doc|Source)\*\*\s*:\s*(.+)$")
TASK_REF_RE = re.compile(r"(TASK-\d+[\w-]*\.md)")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
EMPHASIS_RE = re.compile(r"\*\*|`")

# Row markers in priority order: a row with ✅ counts as merged even if 🎫 appears later.
MARKERS = (("✅", "merged"), ("🚧", "in_flight"), ("🎫", "filed"), ("📋", "not_filed"))
COUNT_KEYS = [key for _, key in MARKERS]


def _skip(path: Path) -> bool:
    return any(part in SKIP_PARTS for part in path.parts)


def _header(text: str) -> list[str]:
    return text.split("\n")[:HEADER_LINES]


def _title(lines: list[str], fallback: str) -> str:
    for line in lines:
        m = H1_RE.match(line)
        if m:
            return m.group(1)
    return fallback


def _last_date(lines: list[str], today: dt.date) -> str | None:
    """Newest date in the header. ``MM-DD`` takes this year, or last year when that lands in the future."""
    found = []
    for line in lines:
        for y, mo, d in DATE_RE.findall(line):
            try:
                found.append(dt.date(int(y), int(mo), int(d)))
            except ValueError:
                continue
        for mo, d in SHORT_DATE_RE.findall(DATE_RE.sub("", line)):
            try:
                cand = dt.date(today.year, int(mo), int(d))
            except ValueError:
                continue
            if cand > today:
                cand = cand.replace(year=today.year - 1)
            found.append(cand)
    return max(found).isoformat() if found else None


def _status(lines: list[str], width: int) -> str:
    for line in lines:
        m = STATUS_RE.search(line)
        if m:
            return _plain(m.group(2), width)
    return ""


def _plain(s: str, width: int) -> str:
    s = MD_LINK_RE.sub(r"\1", s)
    s = EMPHASIS_RE.sub("", s)
    s = s.replace("|", "/").strip()
    if len(s) > width:
        s = s[: width - 1].rstrip() + "…"
    return s


def _kind(lines: list[str]) -> str:
    head = "\n".join(lines[:8]).lower()
    if "**moved" in head or head.startswith("# ") and "\n**moved" in head:
        return "stub"
    if "historical doc" in head:
        return "historical"
    return "live"


def _source_refs(lines: list[str]) -> list[str]:
    refs: list[str] = []
    for line in lines:
        m = SOURCE_RE.search(line)
        if m:
            refs.extend(TASK_REF_RE.findall(m.group(2)))
    return refs


def _repo_label(root: Path) -> str:
    """``/x/pilot-console/.agent`` → ``pilot-console``; a bare ``.agent`` → its parent's name."""
    r = root.resolve()
    return r.parent.name if r.name == ".agent" else r.name


def _short(title: str, width: int = 72) -> str:
    return title if len(title) <= width else title[: width - 1].rstrip() + "…"


def _ticket_counts(text: str) -> list[dict]:
    """Count marker rows per ``##`` section. Returns [] when no row carries a marker."""
    sections: list[dict] = []
    current: dict | None = None
    for line in text.split("\n"):
        if line.startswith("## "):
            current = {"section": _plain(line[3:], 60), "rows": 0, **{k: 0 for k in COUNT_KEYS}}
            sections.append(current)
            continue
        if not line.startswith("|") or current is None:
            continue
        if re.match(r"^\|\s*:?-+", line):
            continue
        for mark, key in MARKERS:
            if mark in line:
                current[key] += 1
                current["rows"] += 1
                break
    return [s for s in sections if s["rows"] > 0 and "legend" not in s["section"].lower()]


def _discover(root: Path) -> list[Path]:
    hits: set[Path] = set()
    if not root.is_dir():
        return []
    for path in root.rglob("*.md"):
        if _skip(path.relative_to(root)):
            continue
        if "roadmap" in path.name.lower():
            hits.add(path)
            continue
        if path.parent.name == "tasks":
            try:
                first = path.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0]
            except OSError:
                continue
            if "roadmap" in re.sub(r"\([^)]*\)", "", first).lower():
                hits.add(path)
    return sorted(hits)


def scan_root(root: Path, today: dt.date, stale_days: int, width: int) -> list[dict]:
    docs: list[dict] = []
    seen: set[Path] = set()
    queue = _discover(root)
    program_refs: set[str] = set()
    while queue:
        path = queue.pop(0)
        if path in seen:
            continue
        seen.add(path)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = _header(text)
        kind = "program" if path.name in program_refs else _kind(lines)
        last = _last_date(lines, today)
        if last is None:
            last = dt.date.fromtimestamp(path.stat().st_mtime).isoformat()
            last_src = "mtime"
        else:
            last_src = "header"
        age = (today - dt.date.fromisoformat(last)).days
        docs.append(
            {
                "root": str(root),
                "repo": _repo_label(root),
                "path": str(path.relative_to(root)),
                "title": _title(lines, path.stem),
                "kind": kind,
                "last_date": last,
                "last_date_source": last_src,
                "age_days": age,
                "stale": kind == "live" and age > stale_days,
                "status": _status(lines, width),
                "tickets": _ticket_counts(text) if kind != "stub" else [],
            }
        )
        for ref in _source_refs(lines):
            candidate = root / "tasks" / ref
            if candidate.is_file() and candidate not in seen:
                program_refs.add(ref)
                queue.append(candidate)
    order = {"live": 0, "program": 1, "historical": 2, "stub": 3}
    docs.sort(key=lambda d: (order.get(d["kind"], 9), d["path"]))
    return docs


def render_md(roots: list[Path], docs: list[dict], today: dt.date) -> str:
    out: list[str] = []
    labels = ", ".join(f"{_repo_label(r)} ({r})" if len(roots) > 1 else str(r) for r in roots)
    out.append(f"## Roadmaps — {labels} ({today.isoformat()})")
    out.append("")
    if not docs:
        out.append("No roadmap documents found.")
        return "\n".join(out)
    multi = len(roots) > 1
    head = "| # | Roadmap | Path | Kind | Last date | Status |"
    sep = "|---|---|---|---|---|---|"
    out += [head, sep]
    for i, d in enumerate(docs, 1):
        kind = d["kind"]
        if d["stale"]:
            kind += f" · stale {d['age_days']}d"
        date = d["last_date"] + ("~" if d["last_date_source"] == "mtime" else "")
        path = f"{d['repo']}: {d['path']}" if multi else d["path"]
        status = d["status"] or "—"
        out.append(f"| {i} | {_short(d['title'])} | `{path}` | {kind} | {date} | {status} |")
    for d in docs:
        if not d["tickets"]:
            continue
        out.append("")
        out.append(f"### Tickets — {_short(d['title'])}")
        out.append("")
        out.append("| Section | Rows | ✅ Merged | 🚧 In flight | 🎫 Filed | 📋 Not filed |")
        out.append("|---|---|---|---|---|---|")
        tot = {k: 0 for k in ["rows", *COUNT_KEYS]}
        for s in d["tickets"]:
            out.append(
                f"| {s['section']} | {s['rows']} | {s['merged']} | {s['in_flight']} | {s['filed']} | {s['not_filed']} |"
            )
            for k in tot:
                tot[k] += s[k]
        if len(d["tickets"]) > 1:
            out.append(
                f"| **Total** | {tot['rows']} | {tot['merged']} | {tot['in_flight']} | {tot['filed']} | {tot['not_filed']} |"
            )
    stale = [d for d in docs if d["stale"]]
    if stale:
        out.append("")
        names = ", ".join(_short(re.split(r" — |: ", re.sub(r"^Roadmap:\s*", "", d["title"]))[0], 40) for d in stale)
        out.append(f"Stale live roadmaps (header date older than the threshold): {names}.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".agent", help="primary .agent directory (default: .agent)")
    ap.add_argument("--also", action="append", default=[], help="extra .agent directory to scan (repeatable)")
    ap.add_argument("--format", choices=("md", "json"), default="md")
    ap.add_argument("--stale-days", type=int, default=30)
    ap.add_argument("--today", default=None, help="YYYY-MM-DD (default: today)")
    ap.add_argument("--excerpt", type=int, default=110, help="status excerpt width")
    args = ap.parse_args(argv)

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    roots = [Path(args.root), *(Path(p) for p in args.also)]
    docs: list[dict] = []
    for root in roots:
        if not root.is_dir():
            print(f"warning: {root} is not a directory, skipped", file=sys.stderr)
            continue
        docs.extend(scan_root(root, today, args.stale_days, args.excerpt))

    if args.format == "json":
        print(json.dumps({"today": today.isoformat(), "roots": [str(r) for r in roots], "roadmaps": docs}, indent=2, ensure_ascii=False))
    else:
        print(render_md(roots, docs, today))
    return 0


if __name__ == "__main__":
    sys.exit(main())
