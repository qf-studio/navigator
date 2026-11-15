#!/usr/bin/env python3
"""Render a route report in plain words from a task document and GitHub state (GH-50).

The source is the ``## Route`` section of a roadmap document (``.agent/roadmaps/*.md``) or
of a task document (``.agent/tasks/*.md``). A roadmap is the larger unit: its steps point
to task documents and tickets. A task document can hold the small route of one step.

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
``owner/repo#12``), a task document (``TASK-12``), the word ``operator``, and
``needs <step>[, <step>]``. The document holds no state words. The state comes from GitHub
(``gh api``) when ``gh`` answers, then from the Status line of the task document, then
from the checkbox. A step with no plain line is an error, not a guess.

The report has five sections: the goal, the roadmap in phases, side tracks, the queue now,
what waits for you. The script reads local files and ``gh`` only, and writes no files.

Usage:
  route_render.py [--doc PATH] [--agent-dir .agent] [--no-gh]
                  [--since FILE] [--short | --state | --list] [--format md|json]
                  [--with-list] [--gh-timeout SECONDS] [--today YYYY-MM-DD]
                  [--queue-label NAME ...]

  --doc PATH     the roadmap or task document (``--task`` is the same flag). Default: the
                 route selected in the /nav pane, else the first open roadmap, else the
                 last open task document with a route.
  --list         every route document of the project: roadmaps, then open task documents.
  --format json  the report (or the list) as JSON; the /nav pane reads it.

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
    from ops.compact_marker import is_in_progress as _doc_in_progress
except Exception:  # partial install: every document counts as open and idle
    def _doc_is_done(text: str) -> bool:
        return False

    def _doc_in_progress(text: str) -> bool:
        return False

ROUTE_RE = re.compile(r"^##\s+Route\s*$", re.IGNORECASE)
H2_RE = re.compile(r"^##\s")
H3_RE = re.compile(r"^###\s+(.+?)\s*$")
H1_RE = re.compile(r"^#\s+(.+?)\s*$")
CHECK_RE = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+(.+?)\s*$")
NUMBER_RE = re.compile(r"^(\d+[a-z]?)[.)]\s+(.*)$", re.IGNORECASE)
ATTRS_RE = re.compile(r"\s*\(([^()]*)\)\s*$")
REF_RE = re.compile(r"^(?:pr\s+)?((?:[\w.-]+/[\w.-]+)?#\d+)$", re.IGNORECASE)
TASK_REF_RE = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")
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

STATE_FILE = ".nav-runtime-state.json"   # section "route": {"active": "<path>"}, set by the pane

DONE, QUEUE, WORK, NEXT, BLOCKED, LATER = "done", "queue", "work", "next", "blocked", "later"
MARKS = {DONE: "✓", QUEUE: "●", WORK: "●", NEXT: "○", BLOCKED: "○", LATER: "○"}


class RouteError(Exception):
    """The task document cannot give a route report; the message names the cause."""


@dataclass
class Step:
    key: str                 # "3" for a route step, "side:1" for a side track
    text: str
    checked: bool
    number: str = ""         # "" for a side track
    ref: str = ""            # "#12" or "owner/repo#12"
    task: str = ""           # "TASK-12": the task document that holds this step's detail
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
    """(plain text, ref, task, operator, needs) — the trailing parenthesis when it is attributes."""
    none = (text, "", "", False, ())
    m = ATTRS_RE.search(text)
    if not m:
        return none
    ref, task, operator, needs, in_needs = "", "", False, [], False
    for token in (t.strip() for t in m.group(1).split(",")):
        low = token.lower()
        ref_m = REF_RE.match(token)
        if ref_m and not ref:
            ref, in_needs = ref_m.group(1), False
        elif TASK_REF_RE.match(token) and not task:
            task, in_needs = token, False
        elif low == "operator":
            operator, in_needs = True, False
        elif low.startswith("needs "):
            needs.extend(low[6:].replace("step", "").split())
            in_needs = True
        elif in_needs and STEP_ID_RE.match(token):
            needs.append(low)
        else:
            return none   # an ordinary parenthesis, part of the plain line
    if not all(STEP_ID_RE.match(n) for n in needs):
        return none
    return text[: m.start()].rstrip(), ref, task, operator, tuple(needs)


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
            text, ref, task, operator, needs = _attrs(body)
            index = len(route.side) + 1
            _check_plain(f"side track {index}", text)
            route.side.append(Step(key=f"side:{index}", text=text, checked=checked, ref=ref,
                                   task=task, operator=operator, needs=needs))
            continue
        numbered = NUMBER_RE.match(body)
        if not numbered:
            raise RouteError(f"a route step has no order number: '{body[:60]}'")
        number = numbered.group(1).lower()
        text, ref, task, operator, needs = _attrs(numbered.group(2))
        _check_plain(f"step {number}", text)
        if phase is None:
            phase = Phase(title="")
            route.phases.append(phase)
        phase.steps.append(Step(key=number, number=number, text=text, checked=checked,
                                ref=ref, task=task, operator=operator, needs=needs))
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

def _gh_one(ref: str, cwd: str, timeout: float = GH_TIMEOUT_S):
    repo, _, number = ref.partition("#")
    path = f"repos/{repo or '{owner}/{repo}'}/issues/{number}"
    try:
        out = subprocess.run(["gh", "api", path], cwd=cwd, capture_output=True, text=True,
                             timeout=timeout)
        return json.loads(out.stdout) if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def fetch_github(refs, cwd: str = ".", timeout: float = GH_TIMEOUT_S) -> dict:
    """{ref: issue JSON} for every ref ``gh`` answers; {} when ``gh`` is not installed."""
    refs = sorted(set(refs))
    if not refs or shutil.which("gh") is None:
        return {}
    with ThreadPoolExecutor(max_workers=GH_WORKERS) as pool:
        results = list(pool.map(lambda r: _gh_one(r, cwd, timeout), refs))
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


def task_statuses(tasks_dir: Path, ids) -> dict:
    """{task id: "done" | "work" | "open"} from the Status line of each task document found."""
    found = {}
    for task_id in sorted(set(ids)):
        paths = []
        for folder in (tasks_dir, tasks_dir / "archive"):
            paths += sorted(folder.glob(f"{task_id}-*.md")) + sorted(folder.glob(f"{task_id}.md"))
        for path in paths[:1]:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            found[task_id] = ("done" if _doc_is_done(text)
                              else "work" if _doc_in_progress(text) else "open")
    return found


def resolve(route: Route, github: dict, queue_labels=DEFAULT_QUEUE_LABELS, tasks=None) -> None:
    """Fill ``kind`` and ``state`` of every step: GitHub, the task document, the checkbox, order."""
    everything = route.steps + route.side
    tasks = tasks or {}
    for step in everything:
        data = github.get(step.ref) if step.ref else None
        if data:
            _from_github(step, data, queue_labels)
        status = tasks.get(step.task)
        if status == "done" and step.kind != DONE:
            step.kind, step.state = DONE, "Done"
        elif status == "work" and step.kind not in (DONE, QUEUE):
            step.kind, step.state = WORK, "In work"
        if step.checked and step.kind != DONE:
            step.kind, step.state = DONE, "Done"
    done = {s.number for s in route.steps if s.kind == DONE}
    next_given = False
    for step in everything:
        if step.kind in (DONE, QUEUE, WORK):
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
    ref = (f"PR {step.ref}" if step.is_pr else step.ref) if step.ref else ""
    names = [name for name in (step.task, ref) if name]
    if names:
        return " · ".join(names)
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


def _queue(route: Route) -> list:
    return [s for s in route.steps + route.side if s.kind in (QUEUE, WORK)]


def report_json(route: Route, source: str, github: bool, path: str, kind: str,
                since=None) -> dict:
    """The report as data: the /nav pane draws its route card from this."""
    def step_json(step: Step) -> dict:
        return {"key": step.key, "number": step.number, "text": step.text,
                "ticket": _ticket(step), "state": step.state, "kind": step.kind,
                "changed": _change(step, since)}
    steps = route.steps
    return {
        "doc": {"path": path, "id": route.task_id, "title": route.title, "kind": kind},
        "goal": route.goal,
        "source": source,
        "github": github,
        "phases": [{"title": phase.title,
                    "done": sum(1 for s in phase.steps if s.kind == DONE),
                    "total": len(phase.steps),
                    "steps": [step_json(s) for s in phase.steps]} for phase in route.phases],
        "side": [step_json(s) for s in route.side],
        "queue": [{"ticket": _ticket(s), "text": s.text} for s in _queue(route)],
        "waits": _waits(route),
        "done": sum(1 for s in steps if s.kind == DONE),
        "total": len(steps),
    }


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
    queue = _queue(route)
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


# --------------------------------------------------------------------------- documents

def _read(path: Path):
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _has_route(text: str) -> bool:
    return any(ROUTE_RE.match(line) for line in text.split("\n"))


def _selected(agent_dir: Path) -> str:
    """The route the user selected in the /nav pane ('' when none): a path under the project."""
    try:
        data = json.loads((agent_dir / STATE_FILE).read_text(encoding="utf-8"))
        active = data.get("route", {}).get("active", "")
        return active if isinstance(active, str) else ""
    except (OSError, ValueError, AttributeError):
        return ""


def _count(text: str, tasks_dir: Path):
    """(done, total) of a document's route from checkboxes and task documents; no GitHub."""
    try:
        route = parse_route(text)
    except RouteError:
        return 0, 0
    resolve(route, {}, tasks=task_statuses(tasks_dir, [s.task for s in route.steps if s.task]))
    return sum(1 for s in route.steps if s.kind == DONE), len(route.steps)


def list_routes(agent_dir: Path, tasks_dir=None) -> list:
    """Every route document: open roadmaps first, then open task documents, in name order.

    A roadmap needs a route section. A task document is listed with ``has_route`` false when
    it has none, so the pane can still select it. ``active`` marks the default document.
    """
    root = agent_dir.resolve().parent
    tasks_dir = tasks_dir or agent_dir / "tasks"
    rows = []
    for kind, folder in (("roadmap", agent_dir / "roadmaps"), ("task", tasks_dir)):
        for path in sorted(folder.glob("*.md")):
            text = _read(path)
            if text is None or path.name.upper().startswith("README") or _doc_is_done(text):
                continue
            has_route = _has_route(text)
            if kind == "roadmap" and not has_route:
                continue
            h1 = next((H1_RE.match(line).group(1) for line in text.split("\n")
                       if H1_RE.match(line)), path.stem)
            id_m = TASK_ID_RE.match(h1) or TASK_ID_RE.match(path.stem)
            done, total = _count(text, tasks_dir) if has_route else (0, 0)
            rows.append({
                "path": str(path.resolve().relative_to(root)), "kind": kind,
                "id": id_m.group(1) if id_m else "",
                "title": re.sub(r"^[A-Z][A-Z0-9]*-\d+\s*[:—–-]\s*", "", h1).strip(),
                "has_route": has_route, "done": done, "total": total, "active": False,
            })
    selected = _selected(agent_dir)
    chosen = next((r for r in rows if r["path"] == selected), None)
    if chosen is None:
        chosen = next((r for r in rows if r["kind"] == "roadmap"), None)
    if chosen is None:
        with_route = [r for r in rows if r["has_route"]]
        chosen = with_route[-1] if with_route else None
    if chosen is not None:
        chosen["active"] = True
    return rows


def find_doc(agent_dir: Path, tasks_dir=None) -> Path:
    """The default route document: the pane's selection, else a roadmap, else the last task."""
    active = next((r for r in list_routes(agent_dir, tasks_dir) if r["active"]), None)
    if active is None or not active["has_route"]:
        raise RouteError(f"no open roadmap or task document with a '## Route' section "
                         f"in {agent_dir}")
    return agent_dir.resolve().parent / active["path"]


def render_list(rows: list) -> str:
    if not rows:
        return "No route documents.\n"
    out = ["# Routes", ""]
    for row in rows:
        mark = "●" if row["active"] else "○"
        name = " — ".join(p for p in (row["id"], row["title"]) if p)
        count = f"{row['done']}/{row['total']}" if row["has_route"] else "no route section"
        out.append(f"- {mark} {name} · {count} · `{row['path']}`")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- CLI

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Route report from a roadmap or task document.")
    parser.add_argument("--doc", "--task", dest="doc",
                        help="roadmap or task document (default: the selected or first open one)")
    parser.add_argument("--agent-dir", default=".agent")
    parser.add_argument("--tasks-dir", help="the tasks folder (default: <agent-dir>/tasks)")
    parser.add_argument("--no-gh", action="store_true", help="no GitHub calls")
    parser.add_argument("--gh-timeout", type=float, default=GH_TIMEOUT_S,
                        help="seconds to wait for each GitHub answer (default 8)")
    parser.add_argument("--since", help="marker or JSON file with an earlier --state output")
    form = parser.add_mutually_exclusive_group()
    form.add_argument("--short", action="store_true", help="changed rows only (needs --since)")
    form.add_argument("--state", action="store_true", help="print the route state as JSON")
    form.add_argument("--list", action="store_true", help="list every route document")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    parser.add_argument("--with-list", action="store_true",
                        help="with --format json: add the route list under 'routes'")
    parser.add_argument("--today", help="YYYY-MM-DD (default: today)")
    parser.add_argument("--queue-label", action="append", default=None,
                        help="issue label that means 'in the queue' (repeatable)")
    args = parser.parse_args(argv)
    today = args.today or dt.date.today().isoformat()
    agent_dir = Path(args.tasks_dir).parent if args.tasks_dir else Path(args.agent_dir)
    tasks_dir = Path(args.tasks_dir) if args.tasks_dir else agent_dir / "tasks"
    as_json = args.format == "json"

    def emit(data) -> None:
        print(json.dumps(data, indent=2, ensure_ascii=False))

    if args.list:
        rows = list_routes(agent_dir, tasks_dir)
        emit(rows) if as_json else sys.stdout.write(render_list(rows))
        return 0
    routes = list_routes(agent_dir, tasks_dir) if as_json and args.with_list else None
    try:
        if args.short and not args.since:
            raise RouteError("the short form needs --since (a marker or a --state file)")
        path = Path(args.doc) if args.doc else find_doc(agent_dir, tasks_dir)
        markdown = _read(path)
        if markdown is None:
            raise RouteError(f"cannot read {path}")
        route = parse_route(markdown, fallback_id=path.stem)
        everything = route.steps + route.side
        refs = [s.ref for s in everything if s.ref]
        github = {} if args.no_gh else fetch_github(
            refs, cwd=str(path.resolve().parent), timeout=args.gh_timeout)
        tasks = task_statuses(tasks_dir, [s.task for s in everything if s.task])
        resolve(route, github, args.queue_label or DEFAULT_QUEUE_LABELS, tasks)
        since = load_since(Path(args.since)) if args.since else None
    except RouteError as exc:
        if as_json:
            emit({"error": str(exc), **({} if routes is None else {"routes": routes})})
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.state:
        emit(state_of(route, today))
        return 0
    if not refs:
        source = f"State from the checkboxes, {today}. The route has no tickets."
    elif github:
        missed = len(set(refs)) - len(github)
        note = f" GitHub did not answer for {missed} ticket(s)." if missed else ""
        source = f"State from GitHub and the checkboxes, {today}.{note}"
    else:
        source = f"State from the checkboxes, {today}. GitHub state is not available."
    if as_json:
        kind = "roadmap" if path.resolve().parent.name == "roadmaps" else "task"
        try:
            shown = str(path.resolve().relative_to(agent_dir.resolve().parent))
        except ValueError:
            shown = str(path)
        data = report_json(route, source, bool(github), shown, kind, since)
        emit(data if routes is None else {**data, "routes": routes})
        return 0
    sys.stdout.write(render_short(route, since) if args.short
                     else render_full(route, source, since))
    return 0


if __name__ == "__main__":
    sys.exit(main())
