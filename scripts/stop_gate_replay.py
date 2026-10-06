#!/usr/bin/env python3
"""Replay recent Bash tool calls through the stop gate's read-only classifier.

Buckets every mutating command by the FIRST segment that trips the classifier,
with heredoc bodies stripped first, so a "next over-fire bucket" claim comes
with a blame-head table instead of a keyword count (TASK-95: the heredoc
bucket named by TASK-94 measured zero once bucketed this way).

    python3 scripts/stop_gate_replay.py [--days 3] [--project <claude-projects-dir>] [--top 20]

Input: Claude Code transcripts (~/.claude/projects/<project>/*.jsonl, Bash tool_use
blocks). Output: counts on stdout. Nothing is written. Stdlib only.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks" / "ops"))
sys.path.insert(0, str(ROOT / "hooks"))

import stop_completion as sc  # noqa: E402

HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")
SEGMENT_RE = re.compile(r"\|\||&&|;|\n")
TWO_TOKEN_HEADS = {"git", "gh", "curl", "sed", "python3", "python", "make", "npm", "bun",
                   "claude", "vercel", "docker", "cargo", "go"}


def default_project_dir() -> str:
    # Claude Code names the project dir from the cwd with "/" and "." as "-".
    slug = "-" + str(Path.cwd().resolve()).strip("/").replace("/", "-").replace(".", "-")
    return os.path.expanduser(f"~/.claude/projects/{slug}")


def bash_commands(project_dir: str, days: float) -> list:
    cutoff = time.time() - days * 86400
    out = []
    for path in glob.glob(os.path.join(project_dir, "*.jsonl")):
        if os.path.getmtime(path) < cutoff:
            continue
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                try:
                    doc = json.loads(line)
                except ValueError:
                    continue
                message = doc.get("message")
                if not isinstance(message, dict):
                    continue
                for block in message.get("content") or []:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    if block.get("name") != "Bash":
                        continue
                    command = (block.get("input") or {}).get("command")
                    if isinstance(command, str):
                        out.append(command)
    return out


def strip_heredoc_bodies(command: str) -> str:
    """Drop every heredoc body (keep the command line) so body lines are not segments."""
    out, lines, i = [], command.split("\n"), 0
    while i < len(lines):
        match = HEREDOC_RE.search(lines[i])
        out.append(lines[i])
        i += 1
        if match:
            delimiter = match.group(2)
            while i < len(lines) and lines[i].lstrip("\t") != delimiter:
                i += 1
            i += 1
    return "\n".join(out)


def blame_head(command: str) -> str:
    segments = [s.strip() for s in SEGMENT_RE.split(strip_heredoc_bodies(command)) if s.strip()]
    bad = next((s for s in segments if not sc._bash_readonly(s)), None)
    if bad is None:
        return "(only a heredoc body or redirect)"
    tokens = bad.split()
    head = tokens[0] if tokens else "?"
    if head in TWO_TOKEN_HEADS and len(tokens) > 1:
        head = f"{head} {tokens[1][:14]}"
    return head


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay recent Bash tool calls through the stop gate classifier.")
    parser.add_argument("--days", type=float, default=3.0)
    parser.add_argument("--project", default=default_project_dir())
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args(argv)

    commands = bash_commands(args.project, args.days)
    mutating = [c for c in commands if not sc._bash_readonly(c)]
    heredocs = [c for c in mutating if HEREDOC_RE.search(c)]
    flips = [c for c in heredocs if sc._bash_readonly(strip_heredoc_bodies(c))]
    buckets = collections.Counter(blame_head(c) for c in mutating)
    samples = {}
    for c in mutating:
        samples.setdefault(blame_head(c), c.split("\n", 1)[0][:72])

    print(f"project: {args.project}")
    print(f"bash calls {len(commands)}, mutating {len(mutating)}, "
          f"heredoc among mutating {len(heredocs)}, "
          f"would flip if bodies were masked {len(flips)}")
    print()
    print(f"{'calls':>6}  {'blame head':30s}  example")
    for head, count in buckets.most_common(args.top):
        print(f"{count:6d}  {head:30s}  {samples[head]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
