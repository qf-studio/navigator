"""Parity fixtures for the tool-event ops (TASK-84 step 5b).

Runs the REAL Python ops (read_guard, jit_memory, graph_sync, profile_sync,
failure_diagnosis) over temp projects and records each result dict plus the state left
behind. Subprocesses and memory recall are faked deterministically: every scripted
subprocess outcome and every argv the op passed is recorded, so the TS tests replay the
same outcomes and assert the same argv. Temp paths are mapped to /r (project root) and /p
(plugin root); sys.executable is mapped to python3.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path

import gen_mod_data as g

ROOT = g.ROOT
sys.path.insert(0, str(ROOT / "hooks" / "ops"))
sys.path.insert(0, str(ROOT / "hooks"))

import failure_diagnosis  # noqa: E402
import graph_sync  # noqa: E402
import jit_memory  # noqa: E402
import profile_sync  # noqa: E402
import read_guard  # noqa: E402
from nav_hook_lib import config  # noqa: E402

CASE_TYPE = ("ReadonlyArray<{ op: string; event: string; payload: Record<string, unknown>; "
             "config: Record<string, unknown>; state: Record<string, unknown>; now: number; "
             "exists: string[]; files: Record<string, string>; "
             "runs: ReadonlyArray<{ rc?: number; stdout?: string; stderr?: string; raise?: string; "
             "message?: string }>; summary: string | null; "
             "expected: { result: unknown; state: unknown; argv: unknown; concepts: unknown } }>")
SEQ_TYPE = ("ReadonlyArray<{ variant: string; config: Record<string, unknown>; "
            "prior: Record<string, unknown>; steps: ReadonlyArray<{ payload: Record<string, unknown>; "
            "now: number; result: unknown; state: unknown }> }>")


def _cfg(patch: dict) -> dict:
    cfg = json.loads(json.dumps(config.DEFAULTS))
    for key, value in patch.items():
        if isinstance(value, dict):
            cfg.setdefault(key, {}).update(value)
        else:
            cfg[key] = value
    return cfg


class _Mapper:
    def __init__(self, root: Path, plugin: Path):
        self.pairs = [(str(plugin), "/p"), (str(root), "/r"), (sys.executable, "python3")]

    def __call__(self, value):
        if isinstance(value, str):
            for real, fake in self.pairs:
                value = value.replace(real, fake)
            return value
        if isinstance(value, list):
            return [self(v) for v in value]
        if isinstance(value, dict):
            return {k: self(v) for k, v in value.items()}
        return value


def _ctx(event, payload, cfg, state, now):
    return types.SimpleNamespace(event=event, payload=payload, config=cfg, state=state,
                                 pilot_executor=False, now=now)


class _FakeRun:
    """Stands in for subprocess.run: scripted outcomes in order, argv recorded."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.argv = []

    def __call__(self, cmd, **_kwargs):
        self.argv.append(list(cmd))
        outcome = self.outcomes.pop(0) if self.outcomes else {"rc": 0, "stdout": "", "stderr": ""}
        if outcome.get("raise") == "timeout":
            raise subprocess.TimeoutExpired(cmd, 8)
        if outcome.get("raise") == "failure":
            raise OSError(outcome["message"])
        return subprocess.CompletedProcess(cmd, outcome["rc"], outcome.get("stdout", ""),
                                           outcome.get("stderr", ""))


def _tree(root: Path) -> list:
    return sorted(str(p) for p in root.rglob("*") if p.is_file())


# ---- read_guard: sequences carrying state across reads -----------------------------------

def _read_guard_sequences(root: Path, mapper: _Mapper) -> list:
    r = str(root)

    def read(path, tool_id=None, tool="Read"):
        payload = {"tool_name": tool, "tool_input": {"file_path": path}, "cwd": r}
        if tool_id is not None:
            payload["tool_use_id"] = tool_id
        return payload

    steps = [
        (read(f"{r}/.agent/tasks/a.md", "t1"), 1000.0),
        (read(f"{r}/.agent/tasks/a.md", "t1"), 1001.0),
        (read(f"{r}/.agent/DEVELOPMENT-README.md", "t2"), 1002.0),
        (read(".agent/system/x.md", "t3"), 1003.0),
        (read(f"{r}/src/main.py", "t4"), 1004.0),
        (read(".agent/research/run/n.md", "t5"), 1005.0),
        (read(f"{r}/.agent/sops/s.md"), 1006.0),
        (read(f"{r}/.agent/sops/s.md"), 1007.0),
        (read(".agent/../.agent/tasks/b.md", "t6"), 1008.0),
        (read("../outside.md", "t7"), 1009.0),
        (read(f"{r}/.agent", "t8"), 1010.0),
        (read(f"{r}/.agent/tasks/z.md", "t9", tool="Grep"), 1011.0),
        (read("", "t10"), 1012.0),
        ({"tool_name": "Read", "tool_input": {}, "cwd": r}, 1013.0),
        (read(f"{r}/.agent/tasks/c.md", "t11"), 1500.0),
        (read(f"{r}/.agent/tasks/d.md", "t12"), 1501.0),
        (read(f"{r}/.agent/tasks/e.md", "t13"), 1502.0),
        (read(f"{r}/.agent/tasks/f.md", "t14"), 1503.0),
        (read(f"{r}/.agent/tasks/g.md", "t15"), 1504.0),
    ]
    variants = {
        "defaults": {},
        "lenient": {"read_guard_hook": {"strict_block": False}},
        "tight": {"read_guard_hook": {"warn_threshold": 2, "escalate_threshold": 3}},
        "allow-tasks": {"read_guard_hook": {"allowlist": ["tasks/", "DEVELOPMENT-README.md"]}},
        "no-stale": {"read_guard_hook": {"stale_after_seconds": 0}},
    }
    priors = {
        "empty": {},
        "carried": {"reads": {"turn_count": 4, "updated_at": 999.0, "seen_tool_uses": ["t1"]}},
        "no-ts": {"reads": {"turn_count": 2}},
        "bad": {"reads": "bad"},
    }
    out = []
    for vname, patch in variants.items():
        cfg = _cfg(patch)
        for pname, prior in priors.items():
            state = copy.deepcopy(prior)
            recorded = []
            for payload, now in steps:
                result = read_guard.run(_ctx("PreToolUse", payload, cfg, state, now))
                recorded.append({"payload": mapper(payload), "now": now, "result": mapper(result),
                                 "state": mapper(copy.deepcopy(state))})
            out.append({"variant": f"{vname}/{pname}", "config": patch, "prior": prior,
                        "steps": recorded})
    return out


# ---- single-step cases --------------------------------------------------------------------

def _case(op, module, event, payload, cfg_patch, state, root, plugin, mapper, now=1000.0,
          runs=(), summary=None, exists_extra=()):
    cfg = _cfg(cfg_patch)
    before = copy.deepcopy(state)
    fake = _FakeRun(runs)
    concepts_seen = []
    real_run, real_recall = subprocess.run, failure_diagnosis.memory.recall

    def fake_recall(concepts=None, **_kwargs):
        concepts_seen.append(list(concepts or []))
        return summary or ""

    subprocess.run = fake
    failure_diagnosis.memory.recall = fake_recall
    try:
        result = module.run(_ctx(event, payload, cfg, state, now))
    finally:
        subprocess.run = real_run
        failure_diagnosis.memory.recall = real_recall
    exists = [mapper(p) for p in _tree(root) + _tree(plugin)] + list(exists_extra)
    files = {mapper(p): Path(p).read_text() for p in _tree(root) if p.endswith(".json")}
    return {
        "op": op, "event": event, "payload": mapper(payload), "config": cfg_patch,
        "state": mapper(before), "now": now, "exists": sorted(set(exists)), "files": files,
        "runs": list(runs), "summary": summary,
        "expected": {"result": mapper(result), "state": mapper(state),
                     "argv": mapper(fake.argv),
                     "concepts": concepts_seen[0] if concepts_seen else None},
    }


def _edit_payload(root, tool, path=None, notebook=None):
    tool_input = {}
    if path is not None:
        tool_input["file_path"] = path
    if notebook is not None:
        tool_input["notebook_path"] = notebook
    return {"tool_name": tool, "tool_input": tool_input, "cwd": str(root)}


def _edit_cases(root: Path, plugin: Path, mapper: _Mapper) -> list:
    r = str(root)
    cases = []
    jit_paths = [f"{r}/hooks/ops/x.py", "hooks/nav_dispatch.py", f"{r}/hooks/x.ts",
                 f"{r}/skills/a.py", f"{r}/../hooks/x.py", "", "./hooks//lib/y.py"]
    jit_states = [{}, {"jit": {"injected": ["mem-034"]}},
                  {"jit": {"injected": ["mem-034", "mem-035"]}}, {"jit": {"injected": "bad"}},
                  {"jit": {"other": 1}}]
    for path in jit_paths:
        for state in jit_states:
            cases.append(_case("jit_memory", jit_memory, "PostToolUse",
                               _edit_payload(root, "Edit", path), {}, copy.deepcopy(state),
                               root, plugin, mapper))
    cases.append(_case("jit_memory", jit_memory, "PostToolUse",
                       _edit_payload(root, "NotebookEdit", "", "hooks/n.py"), {}, {},
                       root, plugin, mapper))

    ok = {"rc": 0, "stdout": "added node\n", "stderr": ""}
    outcomes = [ok, {"rc": 1, "stdout": "", "stderr": "  bad graph " + "x" * 400 + " \n"},
                {"rc": 2, "stdout": "  only stdout  ", "stderr": ""},
                {"raise": "timeout"}, {"raise": "failure", "message": "boom"}]
    task_paths = [f"{r}/.agent/tasks/TASK-12-x.md", ".agent/tasks/GH-57-y.md",
                  f"{r}/.agent/tasks/notes.md", f"{r}/.agent/tasks/TASK-99-missing.md",
                  ".agent/tasks/../tasks/TASK-12-x.md", f"{r}/../.agent/tasks/TASK-12-x.md"]
    for tool in ("Edit", "Write", "MultiEdit"):
        for path in task_paths:
            for outcome in outcomes[:2] if tool != "Edit" else outcomes:
                cases.append(_case("graph_sync", graph_sync, "PostToolUse",
                                   _edit_payload(root, tool, path), {}, {}, root, plugin, mapper,
                                   runs=[outcome]))
    for event in ("TaskCreated", "TaskCompleted"):
        for payload in ({"task_path": ".agent/tasks/TASK-12-x.md"},
                        {"task": {"path": f"{r}/.agent/tasks/GH-57-y.md"}},
                        {"file_path": "README.md", "task": {"task_file": "nope.md"}}, {}):
            for outcome in outcomes[:3]:
                cases.append(_case("graph_sync", graph_sync, event, {**payload, "cwd": r}, {}, {},
                                   root, plugin, mapper, runs=[outcome]))

    profile = f"{r}/.agent/.user-profile.json"
    for state in ({}, {"profile": {"last_synced_count": 1}}, {"profile": {"last_synced_count": 3}},
                  {"profile": {"last_synced_count": None}}, {"profile": "bad"}):
        for outcome in outcomes:
            cases.append(_case("profile_sync", profile_sync, "PostToolUse",
                               _edit_payload(root, "Write", profile), {}, copy.deepcopy(state),
                               root, plugin, mapper, runs=[outcome]))
    for path in (".agent/.user-profile.json", f"{r}/other.json", f"{r}/.agent/missing/.user-profile.json"):
        cases.append(_case("profile_sync", profile_sync, "PostToolUse",
                           _edit_payload(root, "Edit", path), {}, {}, root, plugin, mapper,
                           runs=[ok]))
    cases.append(_case("profile_sync", profile_sync, "PostToolUse",
                       _edit_payload(root, "MultiEdit", profile), {}, {}, root, plugin, mapper))
    return cases


def _graphless_cases(root: Path, plugin: Path, mapper: _Mapper) -> list:
    """Same edits with no knowledge graph: both syncs must stay silent."""
    r = str(root)
    graph = root / ".agent" / "knowledge" / "graph.json"
    graph.rename(graph.with_suffix(".bak"))
    try:
        return [
            _case("graph_sync", graph_sync, "PostToolUse",
                  _edit_payload(root, "Edit", f"{r}/.agent/tasks/TASK-12-x.md"), {}, {},
                  root, plugin, mapper, runs=[{"rc": 0, "stdout": "", "stderr": ""}]),
            _case("graph_sync", graph_sync, "TaskCreated",
                  {"task_path": ".agent/tasks/TASK-12-x.md", "cwd": r}, {}, {}, root, plugin, mapper),
            _case("profile_sync", profile_sync, "PostToolUse",
                  _edit_payload(root, "Write", f"{r}/.agent/.user-profile.json"), {}, {},
                  root, plugin, mapper, runs=[{"rc": 0, "stdout": "", "stderr": ""}]),
        ]
    finally:
        graph.with_suffix(".bak").rename(graph)


def _failure_cases(root: Path, plugin: Path, mapper: _Mapper) -> list:
    r = str(root)
    summaries = [
        None, "",
        "- PITFALL: \"pytest fixture leaks NAVIGATOR_CONFIG_HOME\" (90%)\n"
        "- PATTERN: \"pytest runs per directory\" (80%)\n"
        "- PITFALL: \"unrelated memory about docs\" (70%)",
        "  - pitfall: \"lowercase pytest hit\" (60%)\n- PITFALLé \"unicode boundary pytest\" (50%)\n"
        "- PITFALL pytest one\n- PITFALL pytest two\n- PITFALL pytest three\n- PITFALL pytest four",
    ]
    payloads = [
        {"tool_name": "Bash", "error": "pytest: error: unrecognized arguments --fixture-leak"},
        {"tool_name": "Bash", "tool_response": "Traceback: KeyError in pytest_config"},
        {"tool_name": "Edit", "tool_response": {"stderr": "  ", "message": "old_string not found in docs"}},
        {"tool_name": "Bash", "error": "error failed exception"},
        {"tool_name": "", "error": "pytest broke"},
        {"error": "pytest broke"},
        {"tool_name": "Bash", "error_message": "<nav-workflow-block>pytest</nav-workflow-block> plain"},
        {"tool_name": "Read", "message": "   "},
    ]
    cases = []
    for payload in payloads:
        for summary in summaries:
            cases.append(_case("failure_diagnosis", failure_diagnosis, "PostToolUseFailure",
                               {**payload, "cwd": r}, {}, {}, root, plugin, mapper,
                               summary=summary))
    return cases


def _build():
    with tempfile.TemporaryDirectory() as tmp_root, tempfile.TemporaryDirectory() as tmp_plugin:
        root = Path(tmp_root).resolve()
        plugin = Path(tmp_plugin).resolve()
        functions = plugin / "skills" / "nav-graph" / "functions"
        functions.mkdir(parents=True)
        (functions / "task_to_graph.py").write_text("# stub\n")
        (functions / "correction_to_memory.py").write_text("# stub\n")
        agent = root / ".agent"
        (agent / "knowledge").mkdir(parents=True)
        (agent / "knowledge" / "graph.json").write_text("{}")
        (agent / "tasks").mkdir()
        for name in ("TASK-12-x.md", "GH-57-y.md", "notes.md"):
            (agent / "tasks" / name).write_text("# t\n")
        (agent / ".user-profile.json").write_text(json.dumps({"corrections": [1, 2, 3]}))
        mapper = _Mapper(root, plugin)
        saved = os.environ.get("CLAUDE_PLUGIN_ROOT")
        os.environ["CLAUDE_PLUGIN_ROOT"] = str(plugin)
        try:
            seqs = _read_guard_sequences(root, mapper)
            edits = _edit_cases(root, plugin, mapper) + _graphless_cases(root, plugin, mapper)
            failures = _failure_cases(root, plugin, mapper)
            # A plugin dir without the sync scripts: the "<syncer> missing" diagnostics.
            for name in ("task_to_graph.py", "correction_to_memory.py"):
                (functions / name).unlink()
            edits += [
                _case("graph_sync", graph_sync, "PostToolUse",
                      _edit_payload(root, "Edit", f"{root}/.agent/tasks/TASK-12-x.md"), {}, {},
                      root, plugin, mapper),
                _case("profile_sync", profile_sync, "PostToolUse",
                      _edit_payload(root, "Write", f"{root}/.agent/.user-profile.json"), {}, {},
                      root, plugin, mapper),
            ]
        finally:
            if saved is None:
                os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
            else:
                os.environ["CLAUDE_PLUGIN_ROOT"] = saved
    return seqs, edits, failures


_CACHE = {}


def _data():
    if not _CACHE:
        _CACHE["seqs"], _CACHE["edits"], _CACHE["failures"] = _build()
    return _CACHE


def _read_guard_file() -> str:
    return g.HEADER + "\n" + g.ts_const("READ_GUARD_SEQUENCES", _data()["seqs"], SEQ_TYPE, compact=True)


def _edit_file() -> str:
    return g.HEADER + "\n" + g.ts_const("EDIT_CASES", _data()["edits"], CASE_TYPE, compact=True)


def _failure_file() -> str:
    return g.HEADER + "\n" + g.ts_const("FAILURE_CASES", _data()["failures"], CASE_TYPE, compact=True)


TARGETS = {
    ROOT / "hooks/mod/tests/fixtures/toolops-readguard.gen.ts": _read_guard_file,
    ROOT / "hooks/mod/tests/fixtures/toolops-edit.gen.ts": _edit_file,
    ROOT / "hooks/mod/tests/fixtures/toolops-failure.gen.ts": _failure_file,
}
