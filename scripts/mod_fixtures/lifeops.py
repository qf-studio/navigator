"""Parity fixtures for the lifecycle ops (TASK-84 step 5d).

Runs the REAL Python ops (session_start, compact_marker, subagent_context, config_guard,
setup) on scenario projects materialized under a temp root, with the skill scripts and `git`
replaced by stubs that print recorded outputs. Records the op result and every file the op
wrote. The temp root is rewritten to the placeholder ``/T`` so fixtures are machine
independent; the TS tests replay the same files, env and stub outputs in memory.
"""
from __future__ import annotations

import contextlib
import copy
import json
import os
import sys
import tempfile
import time
import types
from pathlib import Path

import gen_mod_data as g

ROOT = g.ROOT
sys.path.insert(0, str(ROOT / "hooks" / "ops"))

FIXED_NOW = 1790000000.0  # 2026-09-21T14:13:20Z
GOLDEN_AGENT = ROOT / "tests" / "golden" / "fixtures" / "agent"
GOLDEN_SESSION = ROOT / "tests" / "golden" / "goldens" / "session_start.json"
PLACEHOLDER = "/T"
SCRIPTS = {
    "graph_manager.py": "skills/nav-graph/functions/graph_manager.py",
    "memory_recall.py": "skills/nav-graph/functions/memory_recall.py",
    "auto_updater.py": "skills/nav-start/functions/auto_updater.py",
}
STUB = (
    "import json, os, sys\n"
    "spec = json.loads(os.environ.get('STUB_{key}', '{{}}'))\n"
    "sys.stdout.write(spec.get('out', ''))\n"
    "sys.exit(spec.get('code', 0))\n"
)
GIT_STUB = (
    "#!/usr/bin/env python3\n"
    "import json, os, sys\n"
    "table = json.loads(os.environ.get('STUB_GIT', '{}'))\n"
    "spec = table.get(' '.join(sys.argv[1:]), {'out': '', 'code': 1})\n"
    "sys.stdout.write(spec.get('out', ''))\n"
    "sys.exit(spec.get('code', 0))\n"
)
ENV_KEYS = ("HOME", "NAVIGATOR_CONFIG_HOME", "XDG_CONFIG_HOME", "TYPESAFE_API_KEY",
            "CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DIR", "PATH", "TZ", "STUB_GIT",
            "STUB_GRAPH_MANAGER_PY", "STUB_MEMORY_RECALL_PY", "STUB_AUTO_UPDATER_PY")

README = (
    "# Project Navigator\r\n\r\n- **Current Task:** TASK-84 v8 runtime\r\n\r\nSome text.\n"
    "Unicode: naïve café 😀\n"
)
CONFIG = {
    "version": "7.9.0", "project_management": "none", "task_prefix": "TASK", "team_chat": "none",
    "loop_mode": {"enabled": True}, "task_mode": {"enabled": True, "threshold": 0.5},
    "knowledge_graph": {"enabled": True}, "auto_update": {"enabled": False},
    "tom_features": {"verification_checkpoints": True, "ratio": 1.0, "tiny": 1e-07,
                     "name": "naïve ✓", "big": 10000000000000000.0},
}
PROFILE = {
    "preferences": {"communication": {"verbosity": "concise"}, "score": 2.0},
    "corrections": [{"n": i, "note": f"fix {i}"} for i in range(7)],
    "goals": ["ship v8"],
}
TASKS = {
    ".agent/tasks/README.md": "# Tasks index\n",
    ".agent/tasks/TASK-00-prose.md": "# TASK-00: Prose\n\n**Status**: ✅ Implemented\n\n"
    "Docs whose line is plain `In Progress` were recorded as in progress 🚧 before.\n",
    ".agent/tasks/TASK-01-alpha.md": "# TASK-01: Alpha thing\n\n**Status**: 🚧 In Progress\n",
    ".agent/tasks/TASK-02-beta.md": "Intro line\n## TASK-02: Beta\nstatus: `done`\n",
    ".agent/tasks/TASK-03-gamma.md": "no heading here, in-progress soon\n",
    ".agent/tasks/.hidden.md": "# Hidden: also globbed\n",
    ".agent/tasks/notes.txt": "not markdown\n",
}
GRAPH = {"stats": {"total_nodes": 3}, "concept_index": {}}
STUB_GRAPH = {"out": "Knowledge Graph Statistics\n==========================\nTotal Nodes: 195\n"}
STUB_RECALL = {"out": "- PITFALL: \"x\" (90%)\n\n- DECISION: \"y\" (95%)\n- PATTERN: \"z\" (80%)\n"}
STUB_DRIFT = {"out": json.dumps({"has_drift": True, "message": "Config 7.1.0 behind plugin 7.9.0."})}
GIT_OK = {
    "rev-parse --abbrev-ref HEAD": {"out": "v8\n"},
    "log -1 --oneline": {"out": "abc1234 feat: thing\n"},
    "status --short": {"out": " M hooks/mod/x.ts\n?? new.md\n"},
    "log --oneline -5": {"out": "abc1234 feat: thing\ndef5678 fix: other\n"},
}
TRANSCRIPT = "\n".join([
    json.dumps({"message": {"role": "user", "content": "edit hooks/mod/runner.ts please"}}),
    json.dumps({"message": {"role": "assistant", "content": [
        {"type": "text", "text": "```\nconst x = 1\n```\nDone with src/a.py"},
        {"type": "tool_use", "input": {"file_path": "hooks/ops/x.py", "n": 1.5}},
        {"type": "tool_result", "output": ""},
        {"type": "tool_result", "output": 0},
    ]}}),
    "not json at all: Traceback (most recent call last)",
    json.dumps({"type": "summary", "content": "Error: failed to build"}),
    "",
    json.dumps({"message": None, "content": ["x", {"text": None, "input": None, "output": False}]}),
])


def _base_files():
    files = {".agent/.nav-config.json": json.dumps(CONFIG, indent=2)}
    return files


def _scenarios():
    """(op, event, name, files, payload_extra, env, stubs, git, mtimes)."""
    s = []
    full = {
        **_base_files(), **TASKS,
        ".agent/DEVELOPMENT-README.md": README,
        ".agent/.context-markers/.active": "m-1.md\n",
        ".agent/.context-markers/m-1.md": "# Marker one\nbody\n",
        ".agent/.user-profile.json": json.dumps(PROFILE),
        ".agent/knowledge/graph.json": json.dumps(GRAPH),
        ".agent/.nav-workflow-state.json": "{\"v6\": true}",
        ".agent/.nav-read-counter.json": "{\"count\": 3}",
    }
    stubs = {"graph_manager.py": STUB_GRAPH, "memory_recall.py": STUB_RECALL,
             "auto_updater.py": STUB_DRIFT}
    for source in ("startup", "resume", "clear", "compact", None):
        s.append(("session_start", "SessionStart", f"full-{source}", full,
                  {"source": source} if source else {}, {}, stubs, {}, {}))
    s.append(("session_start", "SessionStart", "archive-exists",
              {**full, ".agent/.nav-v6-state.bak/.nav-workflow-state.json": "{\"old\": 1}"},
              {"source": "startup"}, {}, stubs, {}, {}))
    s.append(("session_start", "SessionStart", "minimal-bad-loop-mode",
              {".agent/.nav-config.json": json.dumps({"version": "7.9.0", "loop_mode": True})},
              {}, {}, {}, {}, {}))
    big = {**full, ".agent/DEVELOPMENT-README.md": "# Big\n" + ("lorem ipsum dolor sit amet\n" * 400)}
    s.append(("session_start", "SessionStart", "truncated", big, {}, {}, stubs, {}, {}))
    sections = {**full, ".agent/.nav-config.json": json.dumps({
        **CONFIG, "session_start_hook": {"include_sections": ["config", "tasks", "marker"],
                                         "char_budget": 3000},
        "knowledge_graph": {"enabled": True, "auto_surface_relevant": False}})}
    s.append(("session_start", "SessionStart", "custom-sections", sections, {}, {}, stubs, {}, {}))
    for label, drift in (("no-drift", {"out": json.dumps({"has_drift": False})}),
                         ("not-json", {"out": "oops"}), ("not-dict", {"out": "[1]"}),
                         ("no-message", {"out": json.dumps({"has_drift": 1, "message": ""})}),
                         ("missing", None)):
        st = dict(stubs)
        if drift is None:
            st.pop("auto_updater.py")
        else:
            st["auto_updater.py"] = drift
        s.append(("session_start", "SessionStart", f"drift-{label}", full, {}, {}, st, {}, {}))
    s.append(("session_start", "SessionStart", "marker-missing",
              {**full, ".agent/.context-markers/.active": "gone.md"}, {"source": "resume"},
              {}, stubs, {}, {}))
    s.append(("session_start", "SessionStart", "graph-helper-missing", full, {}, {},
              {"memory_recall.py": STUB_RECALL}, {}, {}))
    judge_cfg = {**CONFIG, "judge": {"enabled": True, "model": "jev-x"}}
    s.append(("session_start", "SessionStart", "judge-env-key",
              {**full, ".agent/.nav-config.json": json.dumps(judge_cfg)}, {},
              {"TYPESAFE_API_KEY": " k-1 "}, stubs, {}, {}))
    s.append(("session_start", "SessionStart", "judge-no-key",
              {**full, ".agent/.nav-config.json": json.dumps(judge_cfg)}, {}, {}, stubs, {}, {}))
    s.append(("session_start", "SessionStart", "adhd-personal-on",
              {**full, "cfg/adhd-mode.json": json.dumps({"on": True})}, {},
              {"NAVIGATOR_CONFIG_HOME": "{T}/p/cfg"}, stubs, {}, {}))
    s.append(("session_start", "SessionStart", "modes-adhd-on-ste-pinned-off",
              {**full, "cfg/adhd-mode.json": json.dumps({"on": True}),
               ".agent/.nav-config.json": json.dumps({**CONFIG, "ste_mode": {"on": False}})},
              {}, {"NAVIGATOR_CONFIG_HOME": "{T}/p/cfg"}, stubs, {}, {}))
    s.append(("session_start", "SessionStart", "profile-weird",
              {**full, ".agent/.user-profile.json": json.dumps(
                  {"preferences": None, "corrections": "abcdefgh", "goals": {"a": 1}})},
              {}, {}, stubs, {}, {}))

    golden = {f".agent/{p.relative_to(GOLDEN_AGENT).as_posix()}": p.read_text(encoding="utf-8")
              for p in sorted(GOLDEN_AGENT.rglob("*")) if p.is_file()}
    golden["notes.md"] = (GOLDEN_AGENT.parent / "notes.md").read_text(encoding="utf-8")
    s.append(("session_start", "SessionStart", "golden-fixture", golden, {"source": "startup"},
              {}, {}, {}, {}))

    # compact_marker
    cm ={**_base_files(), **TASKS, ".agent/tasks/TASK-04.md": "# Four\n\n**Status:** 🚧 Shipping\n",
          ".agent/tasks/TASK-05.md": "# Five\n\n> Status: in-progress\n", ".agent/tasks/TASK-06.md": "# Six in progress\n",
          ".agent/tasks/TASK-07.md": "# Seven in progress\n", "t.jsonl": TRANSCRIPT}
    for trig in ("manual", "auto", "weird", None):
        payload = {"transcript_path": "{T}/p/t.jsonl", "session_id": "sess-1"}
        if trig:
            payload["trigger"] = trig
        s.append(("compact_marker", "PreCompact", f"pre-{trig}", cm, payload, {}, {}, GIT_OK, {}))
    s.append(("compact_marker", "PreCompact", "pre-git-fail", cm, {}, {}, {}, {}, {}))
    s.append(("compact_marker", "PreCompact", "pre-tilde-transcript", cm,
              {"transcript_path": "~/t.jsonl"}, {"HOME": "{T}/p"}, {}, GIT_OK, {}))
    bad_line = {**cm, "t.jsonl": TRANSCRIPT + "\n[1, 2]\n"}
    s.append(("compact_marker", "PreCompact", "pre-transcript-nondict", bad_line,
              {"transcript_path": "{T}/p/t.jsonl"}, {}, {}, GIT_OK, {}))
    tight = {**cm, ".agent/.nav-config.json": json.dumps({**CONFIG, "compact_hook": {
        "char_budget": 1200, "include_git_state": False}})}
    long_t = {**tight, "t.jsonl": "\n".join(f"line {i} touching src/f{i}.ts error" for i in range(260))}
    s.append(("compact_marker", "PreCompact", "pre-tight", long_t,
              {"transcript_path": "{T}/p/t.jsonl"}, {}, {}, GIT_OK, {}))
    off = {**cm, ".agent/.nav-config.json": json.dumps({**CONFIG, "compact_hook": {
        "include_transcript_summary": False}})}
    s.append(("compact_marker", "PreCompact", "pre-no-transcript", off, {}, {}, {}, GIT_OK, {}))
    post = {**cm, ".agent/.context-markers/.active": "m.md\n", ".agent/.context-markers/m.md": "# M\r\nbody\n"}
    for label, summary in (("str", "  The summary.  "), ("dict", {"a": [1, 2.5], "b": "ü"}),
                           ("none", None), ("empty", "")):
        payload = {} if summary is None else {"compact_summary": summary}
        s.append(("compact_marker", "PostCompact", f"post-{label}", post, payload, {}, {}, {}, {}))
    s.append(("compact_marker", "PostCompact", "post-no-active", cm, {}, {}, {}, {}, {}))
    s.append(("compact_marker", "PostCompact", "post-dangling",
              {**cm, ".agent/.context-markers/.active": "nope.md"}, {}, {}, {}, {}, {}))

    # subagent_context
    sc = {**_base_files(), ".agent/knowledge/graph.json": "{}",
          ".agent/DEVELOPMENT-README.md": README}
    s.append(("subagent_context", "SubagentStart", "full",
              {**sc, ".agent/.context-markers/.active": " m-active.md \n"}, {}, {},
              {"memory_recall.py": STUB_RECALL}, {}, {}))
    s.append(("subagent_context", "SubagentStart", "mtime-fallback",
              {**sc, ".agent/.context-markers/a.md": "a", ".agent/.context-markers/b.md": "b",
               ".agent/.context-markers/c.txt": "c"}, {}, {}, {"memory_recall.py": {"out": ""}}, {},
              {".agent/.context-markers/a.md": 1700000300, ".agent/.context-markers/b.md": 1700000100,
               ".agent/.context-markers/c.txt": 1700000900}))
    s.append(("subagent_context", "SubagentStart", "readme-dash",
              {**sc, ".agent/DEVELOPMENT-README.md": "intro\n  - current task :  Port the stop gate  \nx"},
              {}, {}, {"memory_recall.py": STUB_RECALL}, {}, {}))
    tiny = {**sc, ".agent/.nav-config.json": json.dumps({**CONFIG, "subagent_context": {
        "enabled": True, "budget_chars": 50}, "knowledge_graph": {"max_session_memories": 2}})}
    s.append(("subagent_context", "SubagentStart", "budget-50", tiny, {}, {},
              {"memory_recall.py": STUB_RECALL}, {}, {}))
    s.append(("subagent_context", "SubagentStart", "nothing",
              {**_base_files()}, {}, {}, {}, {}, {}))

    # config_guard
    for i, raw in enumerate(CONFIG_TEXTS):
        s.append(("config_guard", "ConfigChange", f"shared-{i}", {".agent/.nav-config.json": raw},
                  {}, {}, {}, {}, {}))
    s.append(("config_guard", "ConfigChange", "local-bad",
              {".agent/.nav-config.json": "{}", ".agent/.nav-config.local.json": "{\"a\": tru}"},
              {}, {}, {}, {}, {}))
    s.append(("config_guard", "ConfigChange", "both-bad",
              {".agent/.nav-config.json": "[1", ".agent/.nav-config.local.json": "{x}"},
              {}, {}, {}, {}, {}))

    # setup
    for label, files in (
        ("bare", {".agent/.nav-config.json": "{}"}),
        ("full", {".agent/.nav-config.json": json.dumps({"version": "7.9.0"}),
                  ".agent/knowledge/graph.json": "{}", ".agent/.nav-runtime-state.json": "{}"}),
        ("numeric-version", {".agent/.nav-config.json": json.dumps({"version": 8.5})}),
        ("dispatcher-off", {".agent/.nav-config.json": json.dumps({"dispatcher": {"enabled": False}})}),
    ):
        s.append(("setup", "Setup", label, files, {}, {}, {}, {}, {}))
    return s


CONFIG_TEXTS = [
    "{}", "  \n", "", "[1, 2]", "\"str\"", "42", "4.5", "true", "null",
    "{\"a\": 1", "{\"a\" 1}", "{a: 1}", "{\"a\": 1 \"b\": 2}", "{\"a\": tru}",
    "{\n  \"a\": [1, {\"b\": }]\n}", "{\"a\": \"line\nbreak\"}", "{\"a\": \"bad \\q escape\"}",
    "{\"a\": \"\\u12zz\"}", "{\"a\": 1}x", "{\"a\": 1}\r\n\r\n  junk", "\ufeff{}",
    "{\"s\": \"\\ud83d\\ude00 ok\"}", "[NaN, Infinity]", "{\"a\": -}", "{\"a\": 01}",
    "{\"k\": \"unterminated", "{\"x\":\n\n  [1,\n   2\n   3]}", "naïve",
]


def _write_tree(base: Path, files: dict, mtimes: dict) -> None:
    for rel, content in files.items():
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))
    for rel, ts in mtimes.items():
        os.utime(base / rel, (ts, ts))
    (base / ".agent").mkdir(exist_ok=True)


def _snapshot(base: Path) -> dict:
    out = {}
    for path in sorted(base.rglob("*")):
        if path.is_file():
            out[path.relative_to(base).as_posix()] = path.read_bytes().decode("utf-8", "replace")
    return out


@contextlib.contextmanager
def _env(values: dict):
    saved = {k: os.environ.get(k) for k in ENV_KEYS}
    try:
        for k in ENV_KEYS:
            if k not in ("PATH",):
                os.environ.pop(k, None)
        os.environ.update(values)
        if "TZ" in values:
            time.tzset()
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        time.tzset()


def _run_case(t: Path, scenario) -> dict:
    op_name, event, name, files, payload_extra, env, stubs, git, mtimes = scenario
    project = t / "p"
    plugin = t / "plugin"
    bindir = t / "bin"
    for d in (project, plugin, bindir):
        if d.exists():
            import shutil
            shutil.rmtree(d)
    for script, rel in SCRIPTS.items():
        if script in stubs:
            (plugin / rel).parent.mkdir(parents=True, exist_ok=True)
            (plugin / rel).write_text(STUB.format(key=script.upper().replace(".", "_")))
    (plugin / "skills" / "nav-start").mkdir(parents=True, exist_ok=True)
    bindir.mkdir(parents=True)
    (bindir / "git").write_text(GIT_STUB)
    (bindir / "git").chmod(0o755)
    _write_tree(project, files, mtimes)
    before = _snapshot(project)

    sub = lambda v: json.loads(json.dumps(v).replace("{T}", str(t)))  # noqa: E731
    env_values = {k: sub(v) for k, v in env.items()}
    env_values.setdefault("HOME", str(t / "home"))
    full_env = {
        **env_values, "CLAUDE_PLUGIN_ROOT": str(plugin), "TZ": "UTC",
        "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}",
        "STUB_GIT": json.dumps(git),
        **{f"STUB_{k.upper().replace('.', '_')}": json.dumps(v) for k, v in stubs.items()},
    }
    payload = {"cwd": str(project), **sub(payload_extra)}
    module = __import__(op_name)
    with _env(full_env):
        from nav_hook_lib import config as nav_config
        ctx = types.SimpleNamespace(event=event, payload=copy.deepcopy(payload),
                                    config=nav_config.load(project), state={},
                                    pilot_executor=False, now=FIXED_NOW)
        result = module.run(ctx)
    after = _snapshot(project)
    written = {k: v for k, v in after.items() if before.get(k) != v}
    record = {
        "op": op_name, "event": event, "name": name,
        "files": {k: v for k, v in files.items()},
        "mtimes": {k: v * 1000 for k, v in mtimes.items()},
        "env": {k: v for k, v in env_values.items()},
        "stubs": {k: v["out"] for k, v in stubs.items()},
        "git": git, "payload": payload, "result": result, "written": written,
    }
    text = json.dumps(record).replace(str(t), PLACEHOLDER)
    return json.loads(text)


_CACHE = {}


def _all_cases() -> list:
    if "cases" not in _CACHE:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp).resolve()
            sys.path.insert(0, str(ROOT / "hooks"))
            _CACHE["cases"] = [_run_case(t, sc) for sc in _scenarios()]
    return _CACHE["cases"]


ROW = ("ReadonlyArray<{ op: string; event: string; name: string; files: Record<string, string>; "
       "mtimes: Record<string, number>; env: Record<string, string>; stubs: Record<string, string>; "
       "git: Record<string, { out: string; code?: number }>; payload: Record<string, unknown>; "
       "result: unknown; written: Record<string, string> }>")


def _golden_context() -> str:
    """additionalContext of the recorded v6 SessionStart golden (dispatcher envelope)."""
    stdout = json.loads(GOLDEN_SESSION.read_text(encoding="utf-8"))["stdout"]
    return json.loads(stdout)["hookSpecificOutput"]["additionalContext"]


def _fixture(op: str):
    def build() -> str:
        cases = [c for c in _all_cases() if c["op"] == op]
        text = g.HEADER + "\n" + g.ts_const("LIFE_CASES", cases, ROW, compact=True)
        if op == "session_start":
            text += "\n" + g.ts_const("GOLDEN_SESSION_CONTEXT", _golden_context(), "string")
        return text
    return build


TARGETS = {
    ROOT / "hooks/mod/tests/fixtures" / f"lifeops-{op}.gen.ts": _fixture(op)
    for op in ("session_start", "compact_marker", "subagent_context", "config_guard", "setup")
}
