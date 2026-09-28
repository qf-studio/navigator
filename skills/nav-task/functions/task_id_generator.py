#!/usr/bin/env python3
"""
Task ID generation for nav-task.

Two sources (``task_id_source`` in .agent/.nav-config.json, default ``local``):

- ``local``  — next sequential ``{prefix}-NN`` from the files in ``.agent/tasks/``.
  Fine for a solo repo; two contributors branching at the same time can both
  mint the same number (GH-32).
- ``github`` — create the GitHub issue first (``gh issue create``) and use its
  number: ``GH-<n>``. Issue numbers are allocated by GitHub, so no two branches
  can produce the same ID. Pilot already addresses tasks as ``GH-<n>``.

CLI:
    task_id_generator.py [agent_dir] [prefix]                 # legacy positional, local
    task_id_generator.py --source local|github|auto [--agent-dir D] [--prefix P]
                         [--title T] [--body B] [--body-file F] [--label L ...] [--repo R]

``--source auto`` (default) reads ``task_id_source`` from the config. In github
mode ``--title`` is required; the issue body defaults to a one-line pointer to
the task doc that nav-task is about to write. Output: the ID on stdout
(``TASK-12`` / ``GH-57``); with ``--json`` also the issue URL.
"""

import argparse
import json
import os
import re
import subprocess
import sys

LOCAL = "local"
GITHUB = "github"
SOURCES = (LOCAL, GITHUB)
GITHUB_PREFIX = "GH"
DEFAULT_BODY = "Task doc will be added under .agent/tasks/ by nav-task."


def get_next_task_id(agent_dir=".agent", prefix="TASK"):
    """
    Scan tasks/ directory and return next available {prefix}-XX ID.

    Args:
        agent_dir: Path to .agent directory (default: .agent)
        prefix: Task ID prefix (default: TASK)

    Returns:
        str: Next task ID (e.g., "TASK-10")
    """
    tasks_dir = os.path.join(agent_dir, "tasks")

    if not os.path.exists(tasks_dir):
        return f"{prefix}-01"

    # Find all task files matching TASK-XX.md or TASK-XX-name.md
    task_pattern = re.compile(rf"{re.escape(prefix)}-(\d+)(?:-.*)?\.md")
    task_numbers = []

    for filename in os.listdir(tasks_dir):
        if filename == "archive":  # Skip archive directory
            continue

        match = task_pattern.match(filename)
        if match:
            task_numbers.append(int(match.group(1)))

    if not task_numbers:
        return f"{prefix}-01"

    # Get next sequential number
    next_num = max(task_numbers) + 1
    return f"{prefix}-{next_num:02d}"


def read_task_id_source(agent_dir=".agent"):
    """``task_id_source`` from .nav-config.json; ``local`` when unset or unreadable."""
    try:
        with open(os.path.join(agent_dir, ".nav-config.json"), encoding="utf-8") as handle:
            value = json.load(handle).get("task_id_source", LOCAL)
    except (OSError, ValueError, AttributeError):
        return LOCAL
    return value if value in SOURCES else LOCAL


_ISSUE_URL = re.compile(r"/issues/(\d+)\s*$")


def parse_issue_number(gh_stdout):
    """Issue number from the URL ``gh issue create`` prints, or None."""
    for line in reversed((gh_stdout or "").strip().splitlines()):
        match = _ISSUE_URL.search(line.strip())
        if match:
            return int(match.group(1))
    return None


def create_github_task_id(title, body=DEFAULT_BODY, labels=(), repo=None, runner=None):
    """
    Create the GitHub issue and return ("GH-<n>", url).

    Raises RuntimeError with gh's stderr when the create fails or the number
    cannot be read; the caller must not fall back to a local number silently,
    because that would reintroduce the collision this mode exists to avoid.
    """
    if not title or not title.strip():
        raise ValueError("github task ids need --title (it becomes the issue title)")
    runner = runner or subprocess.run
    cmd = ["gh", "issue", "create", "--title", title.strip(), "--body", body or DEFAULT_BODY]
    for label in labels or ():
        cmd += ["--label", label]
    if repo:
        cmd += ["--repo", repo]
    try:
        proc = runner(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        raise RuntimeError("gh CLI not found on PATH; install it or set task_id_source: local")
    if proc.returncode != 0:
        raise RuntimeError(f"gh issue create failed ({proc.returncode}): "
                           f"{(proc.stderr or proc.stdout).strip()[:400]}")
    number = parse_issue_number(proc.stdout)
    if number is None:
        raise RuntimeError(f"could not read the issue number from gh output: "
                           f"{proc.stdout.strip()[:200]!r}")
    return f"{GITHUB_PREFIX}-{number}", proc.stdout.strip().splitlines()[-1]


def _build_parser():
    parser = argparse.ArgumentParser(description="nav-task ID generator")
    parser.add_argument("positional", nargs="*", help="legacy: [agent_dir] [prefix]")
    parser.add_argument("--agent-dir", default=None)
    parser.add_argument("--prefix", default=None)
    parser.add_argument("--source", choices=(LOCAL, GITHUB, "auto"), default="auto",
                        help="auto = task_id_source from .nav-config.json (default local)")
    parser.add_argument("--title", default="", help="issue title (github source)")
    parser.add_argument("--body", default="", help="issue body (github source)")
    parser.add_argument("--body-file", default="", help="issue body from a file")
    parser.add_argument("--label", action="append", default=[], help="issue label (repeatable)")
    parser.add_argument("--repo", default=None, help="OWNER/REPO for gh (default: current)")
    parser.add_argument("--json", action="store_true", help="print {id, source, url}")
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    agent_dir = args.agent_dir or (args.positional[0] if len(args.positional) > 0 else ".agent")
    prefix = args.prefix or (args.positional[1] if len(args.positional) > 1 else "TASK")
    source = read_task_id_source(agent_dir) if args.source == "auto" else args.source

    url = ""
    if source == GITHUB:
        body = args.body
        if args.body_file:
            with open(args.body_file, encoding="utf-8") as handle:
                body = handle.read()
        try:
            task_id, url = create_github_task_id(args.title, body or DEFAULT_BODY,
                                                 args.label, args.repo)
        except (RuntimeError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    else:
        task_id = get_next_task_id(agent_dir, prefix)

    if args.json:
        print(json.dumps({"id": task_id, "source": source, "url": url}))
    else:
        print(task_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
