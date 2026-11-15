#!/usr/bin/env python3
"""Render a route report in plain words from a task document and GitHub state (GH-50).

The source is the ``## Route`` section of a task document:

    ## Route

    ### Phase 1: The gate reads the status line
    - [x] 1. Read the status from one shared function. (#48)
    - [ ] 2. Show done documents as one count line. (#49, needs 1)
    - [ ] 3. Install the plugin on the build machine. (operator, needs 2)

    ### Side tracks
    - [ ] Repair the test target on macOS. (#52)

    ### Waits for you
    - [ ] Decide the release number.

A step is one checkbox line: an order number, a plain line that says what the step does,
and an optional trailing parenthesis with the ticket (``#12``, ``PR #12``,
``owner/repo#12``), the word ``operator``, and ``needs <step>[, <step>]``. The document
holds no state words. The state comes from GitHub (``gh api``) when ``gh`` answers, and
from the checkboxes otherwise. A step with no plain line is an error, not a guess.

The report has five sections: the goal, the roadmap in phases, side tracks, the queue now,
what waits for you. The script reads local files and ``gh`` only, and writes no files.

Usage:
  route_render.py [--task PATH] [--tasks-dir .agent/tasks] [--no-gh]
                  [--since FILE] [--short | --state] [--today YYYY-MM-DD]
                  [--queue-label NAME ...]

  --since FILE   a context marker or JSON file that holds an earlier ``--state`` output;
                 changed rows are marked. ``--short`` prints only the changed rows.
  --state        print the route state as JSON (a marker stores it for the next session).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

# One status reader per runtime: done/open comes from the hook runtime's predicate.
_HOOKS_DIR = Path(__file__).resolve().parents[3] / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))
try:
    from ops.compact_marker import is_done as _doc_is_done
except Exception:  # partial install: every document counts as open
    def _doc_is_done(text: str) -> bool:
        return False

ROUTE_RE = re.compile(r"^##\s+Route\s*$", re.IGNORECASE)
H2_RE = re.compile(r"^##\s")
H3_RE = re.compile(r"^###\s+(.+?)\s*$")
H1_RE = re.compile(r"^#\s+(.+?)\s*$")
CHECK_RE = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+(.+?)\s*$")
NUMBER_RE = re.compile(r"^(\d+[a-z]?)[.)]\s+(.*)$", re.IGNORECASE)
ATTRS_RE = re.compile(r"\s*\(([^()]*)\)\s*$")
REF_RE = re.compile(r"^(?:pr\s+)?((?:[\w.-]+/[\w.-]+)?#\d+)$", re.IGNORECASE)
STEP_ID_RE = re.compile(r"^\d+[a-z]?$", re.IGNORECASE)
CODE_RE = re.compile(r"^([A-Z]{1,3}\d+[a-z]?)(?=$|[\s:.)\-—–])")
WORD_RE = re.compile(r"[A-Za-z]{2,}")
GOAL_RE = re.compile(r"^\s*\*\*Goal\*\*\s*:\s*(.*)$", re.IGNORECASE)
TASK_ID_RE = re.compile(r"^([A-Z][A-Z0-9]*-\d+)\b")
FENCE_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)

SIDE_TITLE = "side tracks"
WAITS_TITLE = "waits for you"
DEFAULT_QUEUE_LABELS = ("pilot", "in-progress", "in progress", "queued")
GH_TIMEOUT_S = 8
GH_WORKERS = 6

DONE, QUEUE, NEXT, BLOCKED, LATER = "done", "queue", "next", "blocked", "later"
MARKS = {DONE: "✓", QUEUE: "●", NEXT: "○", BLOCKED: "○", LATER: "○"}


class RouteError(Exception):
    """The task document cannot give a route report; the message names the cause."""


@dataclass
class Step:
    key: str                 # "3" for a route step, "side:1" for a side track
    text: str
    checked: bool
    number: str = ""         # "" for a side track
    ref: str = ""            # "#12" or "owner/repo#12"
    operator: bool = False
    needs: tuple = ()
    kind: str = ""           # filled by resolve(): done / queue / next / blocked / later
    state: str = ""          # the words the reader sees
    is_pr: bool = False


@dataclass
class Phase:
    title: str
    steps: list = field(default_factory=list)


@dataclass
class Route:
    task_id: str
    title: str
    goal: str
    phases: list = field(default_factory=list)
    side: list = field(default_factory=list)
    waits: list = field(default_factory=list)   # open decision lines, plain text

    @property
    def steps(self) -> list:
        return [step for phase in self.phases for step in phase.steps]


# --------------------------------------------------------------------------- parse

def _section(lines: list) -> list:
    start = next((i for i, line in enumerate(lines) if ROUTE_RE.match(line)), None)
    if start is None:
        raise RouteError("the task document has no '## Route' section")
    rest = lines[start + 1:]
    end = next((i for i, line in enumerate(rest) if H2_RE.match(line)), len(rest))
    return rest[:end]


def _goal(lines: list) -> str:
    for i, line in enumerate(lines):
        m = GOAL_RE.match(line)
        if not m:
            continue
        parts = [m.group(1)]
        for follow in lines[i + 1:]:
            stripped = follow.strip()
            if parts[0] or len(parts) > 1:
                if not stripped:
                    break
            elif not stripped:
                continue
            if stripped.startswith(("#", "**", "---")):
                break
            parts.append(stripped)
        goal = " ".join(p.strip() for p in parts if p.strip())
        if goal and not goal.startswith("["):
            return goal
    raise RouteError("the task document has no '**Goal**:' text in its Context section")


def _attrs(text: str):
    """(plain text, ref, operator, needs) — the trailing parenthesis when it is attributes."""
    m = ATTRS_RE.search(text)
    if not m:
        return text, "", False, ()
    ref, operator, needs, in_needs = "", False, [], False
    for token in (t.strip() for t in m.group(1).split(",")):
        low = token.lower()
        ref_m = REF_RE.match(token)
        if ref_m and not ref:
            ref, in_needs = ref_m.group(1), False
        elif low == "operator":
            operator, in_needs = True, False
        elif low.startswith("needs "):
            needs.extend(low[6:].replace("step", "").split())
            in_needs = True
        elif in_needs and STEP_ID_RE.match(token):
            needs.append(low)
        else:
            return text, "", False, ()   # an ordinary parenthesis, part of the plain line
    if not all(STEP_ID_RE.match(n) for n in needs):
        return text, "", False, ()
    return text[: m.start()].rstrip(), ref, operator, tuple(needs)


def _check_plain(name: str, text: str) -> None:
    code = CODE_RE.match(text)
    if code:
        raise RouteError(f"{name} starts with an internal code '{code.group(1)}'; "
                         "write what the step does in plain words")
    if len(WORD_RE.findall(re.sub(r"`[^`]*`", "", text))) < 2:
        raise RouteError(f"{name} has no plain line that says what it does")


def parse_route(markdown: str, fallback_id: str = "") -> Route:
    lines = markdown.split("\n")
    h1 = next((H1_RE.match(line).group(1) for line in lines if H1_RE.match(line)), fallback_id)
    id_m = TASK_ID_RE.match(h1) or TASK_ID_RE.match(fallback_id)
    task_id = id_m.group(1) if id_m else ""
    title = re.sub(r"^[A-Z][A-Z0-9]*-\d+\s*[:—–-]\s*", "", h1).strip()
    route = Route(task_id=task_id, title=title, goal=_goal(lines))
    mode, phase = "phase", None
    for line in _section(lines):
        heading = H3_RE.match(line)
        if heading:
            name = heading.group(1)
            low = name.lower()
            mode = "side" if low == SIDE_TITLE else "waits" if low == WAITS_TITLE else "phase"
            phase = None
            if mode == "phase":
                phase = Phase(title=name)
                route.phases.append(phase)
            continue
        check = CHECK_RE.match(line)
        if not check:
            continue
        checked, body = check.group(1) != " ", check.group(2).replace("**", "")
        if mode == "waits":
            if not checked:
                route.waits.append(body)
            continue
        if mode == "side":
            text, ref, operator, needs = _attrs(body)
            index = len(route.side) + 1
            _check_plain(f"side track {index}", text)
            route.side.append(Step(key=f"side:{index}", text=text, checked=checked, ref=ref,
                                   operator=operator, needs=needs))
            continue
        numbered = NUMBER_RE.match(body)
        if not numbered:
            raise RouteError(f"a route step has no order number: '{body[:60]}'")
        number = numbered.group(1).lower()
        text, ref, operator, needs = _attrs(numbered.group(2))
        _check_plain(f"step {number}", text)
        if phase is None:
            phase = Phase(title="")
            route.phases.append(phase)
        phase.steps.append(Step(key=number, number=number, text=text, checked=checked,
                                ref=ref, operator=operator, needs=needs))
    steps = route.steps
    if not steps:
        raise RouteError("the '## Route' section has no steps")
    numbers = [s.number for s in steps]
    for number in numbers:
        if numbers.count(number) > 1:
            raise RouteError(f"step {number} appears more than once")
    for step in steps + route.side:
        for need in step.needs:
            if need not in numbers:
                name = f"step {step.number}" if step.number else "a side track"
                raise RouteError(f"{name} needs step {need}, which the route does not have")
    return route


# --------------------------------------------------------------------------- GitHub

def _gh_one(ref: str, cwd: str):
    repo, _, number = ref.partition("#")
    path = f"repos/{repo or '{owner}/{repo}'}/issues/{number}"
    try:
        out = subprocess.run(["gh", "api", path], cwd=cwd, capture_output=True, text=True,
                             timeout=GH_TIMEOUT_S)
        return json.loads(out.stdout) if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def fetch_github(refs, cwd: str = ".") -> dict:
    """{ref: issue JSON} for every ref ``gh`` answers; {} when ``gh`` is not installed."""
    refs = sorted(set(refs))
    if not refs or shutil.which("gh") is None:
        return {}
    with ThreadPoolExecutor(max_workers=GH_WORKERS) as pool:
        results = list(pool.map(lambda r: _gh_one(r, cwd), refs))
    return {ref: data for ref, data in zip(refs, results) if isinstance(data, dict)}


def _day(stamp) -> str:
    return stamp[:10] if isinstance(stamp, str) and len(stamp) >= 10 else ""


def _with_day(word: str, stamp) -> str:
    day = _day(stamp)
    return f"{word} {day}" if day else word


def _from_github(step: Step, data: dict, queue_labels) -> None:
    """Set kind/state from a GitHub issue or pull request; leaves them empty when open and idle."""
    pull = data.get("pull_request")
    step.is_pr = isinstance(pull, dict)
    closed = data.get("state") == "closed"
    if step.is_pr and pull.get("merged_at"):
        step.kind, step.state = DONE, _with_day("Merged", pull.get("merged_at"))
    elif step.is_pr and closed:
        step.state = "Closed, not merged"
    elif step.is_pr:
        step.kind, step.state = QUEUE, "In the queue now"
    elif closed and data.get("state_reason") == "not_planned":
        step.kind, step.state = DONE, _with_day("Closed, not planned", data.get("closed_at"))
    elif closed:
        step.kind, step.state = DONE, _with_day("Done", data.get("closed_at"))
    else:
        labels = {str(l.get("name", "")).lower() for l in data.get("labels") or []
                  if isinstance(l, dict)}
        if data.get("assignees") or labels & {q.lower() for q in queue_labels}:
            step.kind, step.state = QUEUE, "In the queue now"


def resolve(route: Route, github: dict, queue_labels=DEFAULT_QUEUE_LABELS) -> None:
    """Fill ``kind`` and ``state`` of every step: GitHub first, the checkbox next, then order."""
    everything = route.steps + route.side
    for step in everything:
        data = github.get(step.ref) if step.ref else None
        if data:
            _from_github(step, data, queue_labels)
        if step.checked and step.kind != DONE:
            step.kind, step.state = DONE, "Done"
    done = {s.number for s in route.steps if s.kind == DONE}
    next_given = False
    for step in everything:
        if step.kind in (DONE, QUEUE):
            continue
        unmet = [n for n in step.needs if n not in done]
        prefix = f"{step.state}; " if step.state else ""
        if unmet:
            names = " and ".join(unmet)
            step.kind = BLOCKED
            step.state = f"{prefix}Blocked: needs step{'s' if len(unmet) > 1 else ''} {names}"
        elif step.number and not next_given:
            step.kind, step.state, next_given = NEXT, f"{prefix}Next", True
        else:
            step.kind, step.state = LATER, f"{prefix}Later" if step.number else f"{prefix}Open"


# --------------------------------------------------------------------------- state

def state_of(route: Route, today: str) -> dict:
    return {"task": route.task_id, "date": today,
            "steps": {s.key: s.state for s in route.steps + route.side}}


def load_since(path: Path) -> dict:
    """The ``steps`` map of an earlier ``--state`` output, from a JSON file or a marker."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RouteError(f"cannot read --since file {path}: {exc.strerror or exc}")
    candidates = [text] + FENCE_RE.findall(text)
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("steps"), dict):
            return data["steps"]
    raise RouteError(f"--since file {path} holds no route state (run --state to make one)")


def _change(step: Step, since) -> str:
    """'' when unchanged or no baseline; else the note for the reader."""
    if since is None:
        return ""
    before = since.get(step.key)
    if before is None:
        return "new"
    return "" if before == step.state else f"was: {before}"


# --------------------------------------------------------------------------- render

def _ticket(step: Step) -> str:
    if step.ref:
        return f"PR {step.ref}" if step.is_pr else step.ref
    return "Operator step" if step.operator else "Not filed"


def _line(step: Step, since) -> str:
    head = f"{step.number}. " if step.number else ""
    change = _change(step, since)
    tail = f"  ← changed ({change})" if change else ""
    return f"- {MARKS[step.kind]} {head}{step.text} — {_ticket(step)} · {step.state}{tail}"


def _waits(route: Route) -> list:
    items = [f"Do the operator step {s.number}: {s.text}" for s in route.steps
             if s.operator and s.kind == NEXT]
    items += [f"Do the operator step: {s.text}" for s in route.side
              if s.operator and s.kind not in (DONE, BLOCKED)]
    items += [f"Review {_ticket(s)}: {s.text}" for s in route.steps + route.side
              if s.is_pr and s.kind == QUEUE]
    return items + list(route.waits)


def render_full(route: Route, source: str, since=None) -> str:
    name = " — ".join(p for p in (route.task_id, route.title) if p)
    out = [f"# Route report: {name}", "", f"_{source}_", "", "## 1. The goal", "", route.goal,
           "", "## 2. The roadmap"]
    for phase in route.phases:
        done = sum(1 for s in phase.steps if s.kind == DONE)
        count = f"{done} of {len(phase.steps)} done"
        out += ["", f"**{phase.title} ({count})**" if phase.title else f"**Steps ({count})**"]
        out += [_line(step, since) for step in phase.steps]
    if since is not None:
        gone = sorted(set(since) - {s.key for s in route.steps + route.side})
        if gone:
            out += ["", f"Removed from the route since the last report: {', '.join(gone)}."]
    out += ["", "## 3. Side tracks", ""]
    out += [_line(step, since) for step in route.side] or ["None."]
    queue = [s for s in route.steps + route.side if s.kind == QUEUE]
    out += ["", "## 4. The queue now", ""]
    out += [f"- {_ticket(s)}: {s.text}" for s in queue] or ["Nothing is in the queue."]
    waits = _waits(route)
    out += ["", "## 5. What waits for you", ""]
    out += [f"{i}. {item}" for i, item in enumerate(waits, 1)] or ["Nothing."]
    return "\n".join(out) + "\n"


def render_short(route: Route, since: dict) -> str:
    everything = route.steps + route.side
    changed = [s for s in everything if _change(s, since)]
    name = route.task_id or route.title
    out = [f"# Route report (short): {name}", ""]
    out += [_line(step, since) for step in changed]
    gone = sorted(set(since) - {s.key for s in everything})
    if gone:
        out.append(f"- Removed from the route: {', '.join(gone)}.")
    out.append(f"unchanged: {len(everything) - len(changed)}")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- CLI

def find_task(tasks_dir: Path) -> Path:
    """The last open task document (file-name order) that has a route section."""
    found = None
    for path in sorted(tasks_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if any(ROUTE_RE.match(line) for line in text.split("\n")) and not _doc_is_done(text):
            found = path
    if found is None:
        raise RouteError(f"no open task document with a '## Route' section in {tasks_dir}")
    return found


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Route report from a task document.")
    parser.add_argument("--task", help="task document (default: the last open one with a route)")
    parser.add_argument("--tasks-dir", default=".agent/tasks")
    parser.add_argument("--no-gh", action="store_true", help="state from the checkboxes only")
    parser.add_argument("--since", help="marker or JSON file with an earlier --state output")
    form = parser.add_mutually_exclusive_group()
    form.add_argument("--short", action="store_true", help="changed rows only (needs --since)")
    form.add_argument("--state", action="store_true", help="print the route state as JSON")
    parser.add_argument("--today", help="YYYY-MM-DD (default: today)")
    parser.add_argument("--queue-label", action="append", default=None,
                        help="issue label that means 'in the queue' (repeatable)")
    args = parser.parse_args(argv)
    today = args.today or dt.date.today().isoformat()
    try:
        if args.short and not args.since:
            raise RouteError("the short form needs --since (a marker or a --state file)")
        path = Path(args.task) if args.task else find_task(Path(args.tasks_dir))
        try:
            markdown = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RouteError(f"cannot read {path}: {exc.strerror or exc}")
        route = parse_route(markdown, fallback_id=path.stem)
        refs = [s.ref for s in route.steps + route.side if s.ref]
        github = {} if args.no_gh else fetch_github(refs, cwd=str(path.resolve().parent))
        resolve(route, github, args.queue_label or DEFAULT_QUEUE_LABELS)
        since = load_since(Path(args.since)) if args.since else None
    except RouteError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.state:
        print(json.dumps(state_of(route, today), indent=2, ensure_ascii=False))
        return 0
    if not refs:
        source = f"State from the checkboxes, {today}. The route has no tickets."
    elif github:
        missed = len(set(refs)) - len(github)
        note = f" GitHub did not answer for {missed} ticket(s)." if missed else ""
        source = f"State from GitHub and the checkboxes, {today}.{note}"
    else:
        source = f"State from the checkboxes, {today}. GitHub state is not available."
    sys.stdout.write(render_short(route, since) if args.short
                     else render_full(route, source, since))
    return 0


if __name__ == "__main__":
    sys.exit(main())
