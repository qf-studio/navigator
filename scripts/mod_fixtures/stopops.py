"""Parity fixtures for the Stop ops port (TASK-84 step 5c).

Runs the REAL hooks/ops/stop_completion.py and hooks/ops/stop_state.py over synthetic
transcripts, payload / config / prior-state variants and git outcomes, and records the
result dict plus the state each op leaves behind. `git status --porcelain` is either
faked (clean / dirty / non-repo / timeout) or run for real in temp repos; every outcome is
recorded so the TS io.run mock replays it. Written compact and split by group (the mod
test kit refuses imports over 1 MiB).
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import types
from pathlib import Path

import gen_mod_data as g

ROOT = g.ROOT
FIXTURES = ROOT / "hooks" / "mod" / "tests" / "fixtures"
NOW = 1700000000.25
DIRTY = " M hooks/x.py\n?? notes.md\n"

ROW = ("ReadonlyArray<{ group: string; transcript: string | null; payload: Record<string, unknown>; "
       "config: string; prior: Record<string, unknown>; git: string; pilot: boolean; "
       "gitResult: { exitCode: number; stdout: string } | null; result: unknown; "
       "after: Record<string, unknown> }>")


# ---- transcripts -------------------------------------------------------------------------

def _user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def _user_blocks(blocks):
    return {"type": "user", "message": {"role": "user", "content": blocks}}


def _asst(content):
    return {"type": "assistant", "message": {"role": "assistant", "content": content}}


def _text(t):
    return {"type": "text", "text": t}


def _tool(tid, name, inp):
    block = {"type": "tool_use", "name": name, "input": inp}
    if tid is not None:
        block["id"] = tid
    return block


def _result(tid, is_error=False):
    return {"type": "tool_result", "tool_use_id": tid, "is_error": is_error, "content": "ok"}


def _bash_turn(*cmds, errors=()):
    entries = [_user("do the thing")]
    for i, cmd in enumerate(cmds):
        tid = f"b{i}"
        entries.append(_asst([_text(f"step {i}"), _tool(tid, "Bash", {"command": cmd})]))
        entries.append(_user_blocks([_result(tid, i in errors)]))
    entries.append(_asst([_text("Done with the commands.")]))
    return entries


CHECK_TABLE = ("┌──────────┐\n│ WORKFLOW CHECK │\n└──────────┘\nNAVIGATOR_STATUS\nPhase: IMPL\n"
               "Next Action: run tests")


def _transcripts() -> dict:
    sample = (ROOT / "hooks" / "nav_hook_lib" / "fixtures" / "transcript-sample.jsonl").read_text()
    t = {
        "conv": [_user("hi"), _asst([_text("hello there")])],
        "edit_py": [_user("fix"), _asst([_text("working"), _tool("t1", "Edit", {"file_path": "/r/x.py"})]),
                    _user_blocks([_result("t1")]), _asst([_text("Done.")])],
        "edit_md_marker": [_user("doc it"),
                           _asst([_tool("w1", "Write", {"file_path": "/r/README.md"}),
                                  _tool("w2", "Write", {"file_path": "/r/.agent/.context-markers/m.md"})]),
                           _user_blocks([_result("w1"), _result("w2")]), _asst([_text("Written.")])],
        "notebook": [_user("nb"), _asst([_tool("n1", "NotebookEdit", {"notebook_path": "/r/a.ipynb"})]),
                     _asst([_text("nb done")])],
        "bash_ro": _bash_turn("grep -rn foo . | head", "git status", "ls -la && wc -l x",
                              "git log --oneline -3", "gh pr view 3"),
        "bash_mut": _bash_turn("rm -rf build"),
        "bash_redirect": _bash_turn("echo hi > out.txt"),
        "bash_devnull": _bash_turn("echo ok > /dev/null 2>&1", "ls 2>&1"),
        "bash_subst_ro": _bash_turn("LOG=$(ls) && echo $LOG", "X=`date` true"),
        "bash_subst_mut": _bash_turn("X=`rm a` echo"),
        "bash_commit": _bash_turn("git add -A && git commit -m x"),
        "bash_tests_ok": _bash_turn("make test", "python3 -m unittest discover"),
        "bash_tests_err": _bash_turn("pytest -q", "sed -i s/a/b/ f", errors=(0,)),
        "bash_tests_mut": _bash_turn("pytest -q && touch done"),
        "bash_gh_merge": _bash_turn("gh pr merge 3 --squash"),
        "bash_control": _bash_turn("for f in *.py; do wc -l $f; done", "if test -f x; then cat x; fi",
                                   "command -v jq", "time ls"),
        "bash_command_rm": _bash_turn("command rm x"),
        # TASK-94: quoted operators are arguments; a quoted redirect target is still a write.
        "bash_quoted_ro": _bash_turn('grep -n "a\\|b" f | head -3', "gh pr view 1 --jq '.a | .b'",
                                     'printf "%s | %s\\n" a b', "grep '>' f"),
        "bash_quoted_mut": _bash_turn('echo "x" > "$F"', 'sh -c "ls"'),
        # TASK-95: a mutating Bash command naming a .md is a docs edit; a read-only one is not;
        # `make mod-test` is a test run.
        "bash_md_edit": _bash_turn("sed -i '' 's/a/b/' docs/README.md"),
        # TASK-95: an untracked path the turn itself wrote keeps the tree dirty (git "untracked").
        "edit_untracked": [_user("scratch"), _asst([_tool("u1", "Write", {"file_path": "/r/scratch/new.py"})]),
                           _asst([_text("drafted; more to do")])],
        "bash_md_read": _bash_turn("grep -n foo README.md | head"),
        "bash_kit_tests": _bash_turn("make mod-test"),
        "agent": [_user("research"), _asst([_tool("a1", "Agent", {"prompt": "look"})]),
                  _user_blocks([_result("a1")]), _asst([_text("Agent finished.")])],
        # TASK-92: read-only subagents are not task actions; unknown types still are.
        "agent_ro": [_user("research"),
                     _asst([_tool("a1", "Agent", {"prompt": "look", "subagent_type": "navigator:navigator-research"}),
                            _tool("b1", "Bash", {"command": "grep -rn foo . | head"})]),
                     _user_blocks([_result("a1"), _result("b1")]), _asst([_text("Agent finished.")])],
        "agent_explore": [_user("find"), _asst([_tool("a1", "Task", {"prompt": "look", "subagent_type": "Explore"})]),
                          _user_blocks([_result("a1")]), _asst([_text("Found it.")])],
        "agent_general": [_user("do"), _asst([_tool("a1", "Agent", {"prompt": "fix", "subagent_type": "general-purpose"})]),
                          _user_blocks([_result("a1")]), _asst([_text("Agent finished.")])],
        "agent_ro_edit": [_user("fix"), _asst([_tool("a1", "Agent", {"prompt": "look", "subagent_type": "Explore"}),
                                               _tool("e1", "Edit", {"file_path": "/r/x.py"})]),
                          _user_blocks([_result("a1"), _result("e1")]), _asst([_text("Done.")])],
        "exit_signal": [_user("ship"), _asst([_tool("e1", "Edit", {"file_path": "/r/a.py"})]),
                        _asst([_text('Done.\n<!-- nav-signal:v3:{"type":"exit","reason":"done"} -->')])],
        "v2_signal": [_user("ship"), _asst([_tool("e1", "Edit", {"file_path": "/r/a.py"})]),
                      _asst([_text('Done.\n```pilot-signal\n{"v": 2, "type": "exit"}\n```')])],
        "bad_signal": [_user("ship"), _asst([_tool("e1", "Edit", {"file_path": "/r/a.py"})]),
                       _asst([_text('nav-signal:v3:{"type":"exitt"}\nnav-signal:v3:{bad json}\n'
                                    '  nav-signal:v3:{"type":"status"}  ')])],
        "check_block": [_user("go"), _asst([_text(CHECK_TABLE), _tool("e1", "Edit", {"file_path": "/r/a.py"})]),
                        _asst([_text("Finished.")])],
        "check_last": [_user("go"), _asst([_tool("e1", "Edit", {"file_path": "/r/a.py"})]),
                       _asst([_text(CHECK_TABLE)])],
        "sentinel_echo": [_user("go"),
                          _asst([_text("<nav-workflow-block>\nWORKFLOW CHECK\n</nav-workflow-block>\nok"),
                                 _tool("b1", "Bash", {"command": "rm x"})])],
        "content_str": [_user("q"), {"type": "assistant", "message": {"role": "assistant",
                                                                      "content": "Phase: VERIFY then more"}}],
        "no_message": [_user("q"), {"role": "assistant", "content": [_text("raw entry"),
                                                                     _tool("r1", "Write", {"file_path": "x"})]}],
        "boundary": [_user("old"), _asst([_tool("o1", "Edit", {"file_path": "/r/old.py"})]),
                     _user_blocks([_text("new prompt as block")]), _asst([_text("just talking")])],
        "multi_text": [_user("q"), _asst([_text("first"), _tool("e1", "Edit", {"file_path": "/r/a.md"}),
                                          _text("second")]),
                       _user_blocks([_result("e1")]), _asst([_text("last a"), _text("last b")])],
        "no_id": [_user("q"), _asst([_tool(None, "Bash", {"command": "make test"})]),
                  _user_blocks([_result("zzz", True)]), _asst([_text("ran")])],
        "phase_word": [_user("q"), _asst([_text("xPhase: IMPL and Phase:COMPLETEd and Phase:  INIT")])],
    }
    out = {name: "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries)
           for name, entries in t.items()}
    out["sample"] = sample
    out["u2028"] = (json.dumps(_user("q")) + "\n"
                    + json.dumps(_asst([_text("split here"), _tool("u1", "Edit", {"file_path": "a"})]),
                                 ensure_ascii=False) + "\n"
                    + json.dumps(_asst([_text("tail text"), _tool("u2", "Bash", {"command": "ls"})])) + "\n")
    out["junk"] = ("\n\n not json\n[1,2]\n42\n" + json.dumps(_user("q")) + "\n"
                   + json.dumps(_asst([_tool("j1", "Bash", {"command": "mkdir x"})])) + "\n"
                   + '{"truncated": ')
    out["crlf"] = out["edit_py"].replace("\n", "\r\n")
    out["empty"] = ""
    return out


# ---- variants ----------------------------------------------------------------------------

PAYLOADS = {
    "transcript": {},
    "inline_plain": {"last_assistant_message": "All set. WORKFLOW CHECK shown. Phase: COMPLETE"},
    "inline_exit": {"last_assistant_message": 'Done <!-- nav-signal:v3:{"type":"exit"} -->'},
    "inline_ws": {"last_assistant_message": "   "},
    "active": {"stop_hook_active": True},
}

SC_ON = {"stop_completion": {"enabled": True, "continue_enabled": True}}
COMPLETION_CONFIGS = {
    "on": SC_ON,
    "off": {},
    "enabled_only": {"stop_completion": {"enabled": True}},
    "max0": {"stop_completion": {"enabled": True, "continue_enabled": True, "max_continues": 0}},
    "max_str": {"stop_completion": {"enabled": True, "continue_enabled": True, "max_continues": "3"}},
    "max_bad": {"stop_completion": {"enabled": True, "continue_enabled": True, "max_continues": "x"}},
    "max_neg": {"stop_completion": {"enabled": True, "continue_enabled": True, "max_continues": -1}},
    "pm": {**SC_ON, "project_management": "linear"},
}
STATE_CONFIGS = {"default": {}, "rg_off": {"read_guard_hook": {"enabled": False}}}


def _completion_priors() -> dict:
    dirty_digest = hashlib.sha256(DIRTY.encode("utf-8")).hexdigest()
    return {
        "none": {},
        "fuse": {"completion": {"stop_fuse": True}},
        "held1": {"completion": {"held_count": 1}},
        "held2": {"completion": {"held_count": 2}},
        "held_bool": {"completion": {"held_count": True, "stop_fuse": False}},
        "indicators": {"completion": {"indicators": {"code_simplified": True, "docs_updated": 1}}},
        "same_digest": {"completion": {"tree_digest": dirty_digest, "held_count": 0}},
        "nondict": {"completion": "x"},
    }


STATE_PRIORS = {
    "none": {},
    "full": {"turn": {"signals": {"check_shown": True}}, "reads": {"turn_count": 5},
             "completion": {"tree_digest": "abc", "stop_fuse": True, "held_count": 2},
             "tier1": {"hits": 1}},
    "bad_completion": {"completion": [], "meta": {"op_errors": []}},
}

GITS = {
    "clean": {"exitCode": 0, "stdout": ""},
    "dirty": {"exitCode": 0, "stdout": DIRTY},
    # TASK-95: only untracked paths → counts as clean for code_committed.
    "untracked": {"exitCode": 0, "stdout": "?? scratch/\n?? notes.md\n"},
    "nonrepo": {"exitCode": 128, "stdout": ""},
    "raise": None,
}


def _merge(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


@contextlib.contextmanager
def _git(mode: str, recorded: list):
    """Patch subprocess.run for `git status --porcelain`; record what the op saw."""
    real = subprocess.run

    def fake(argv, *args, **kwargs):
        if list(argv) != ["git", "status", "--porcelain"]:
            return real(argv, *args, **kwargs)
        if mode.startswith("real"):
            res = real(argv, *args, **kwargs)
            recorded.append({"exitCode": res.returncode, "stdout": res.stdout})
            return res
        spec = GITS[mode]
        if spec is None:
            raise subprocess.TimeoutExpired(argv, 2)
        recorded.append(dict(spec))
        return subprocess.CompletedProcess(argv, spec["exitCode"], spec["stdout"], "")

    subprocess.run = fake
    try:
        yield
    finally:
        subprocess.run = real


def _real_repo(base: Path, dirty: bool) -> Path:
    repo = base / ("real-dirty" if dirty else "real-clean")
    (repo / ".agent").mkdir(parents=True)
    (repo / "a.txt").write_text("a\n")
    git = ["git", "-c", "user.name=n", "-c", "user.email=e@x", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(git + ["commit", "-q", "-m", "init"], cwd=repo, check=True)
    if dirty:
        (repo / "a.txt").write_text("changed\n")
        (repo / "new.md").write_text("n\n")
    return repo


def _ops():
    sys.path.insert(0, str(ROOT / "hooks" / "ops"))
    import stop_completion  # noqa: E402
    import stop_state  # noqa: E402
    return stop_completion, stop_state


def _run_case(op, tdir: Path, cwd: Path, case: dict, cfg_patch: dict) -> dict:
    payload = dict(case["payload"])
    payload["cwd"] = str(cwd)
    if case["transcript"] is not None:
        payload["transcript_path"] = str(tdir / f"{case['transcript']}.jsonl")
    state = copy.deepcopy(case["prior"])
    ctx = types.SimpleNamespace(event="Stop", payload=payload, config=_merge(g.config.DEFAULTS, cfg_patch),
                                state=state, pilot_executor=case["pilot"], now=NOW, session_id="s")
    recorded: list = []
    with _git(case["git"], recorded):
        result = op.run(ctx)
    case["gitResult"] = recorded[0] if recorded else (None if case["git"] == "raise" else None)
    if case["git"] == "raise":
        case["gitResult"] = None
    case["result"] = result
    case["after"] = state
    return case


def _build() -> dict:
    stop_completion, stop_state = _ops()
    transcripts = _transcripts()
    priors = _completion_priors()
    groups: dict = {"completion_a": [], "completion_b": [], "completion_c": [], "state": []}
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        tdir = base / "t"
        tdir.mkdir()
        for name, text in transcripts.items():
            (tdir / f"{name}.jsonl").write_bytes(text.encode("utf-8"))
        proj = base / "proj"
        (proj / ".agent").mkdir(parents=True)
        repos = {"real-clean": _real_repo(base, False), "real-dirty": _real_repo(base, True)}

        def case(group, transcript, payload, config, prior_name, prior, git, pilot=False, op=None):
            c = {"group": group, "transcript": transcript, "payload": PAYLOADS[payload], "config": config,
                 "prior": prior, "git": git, "pilot": pilot}
            cfgs = COMPLETION_CONFIGS if op is stop_completion else STATE_CONFIGS
            cwd = repos.get(git, proj)
            groups[group].append(_run_case(op, tdir, cwd, c, cfgs[config]))

        names = list(transcripts) + ["__missing__", None]
        for name in names:
            for git in ("clean", "dirty", "untracked", "nonrepo", "raise", "real-clean", "real-dirty"):
                case("completion_a", name, "transcript", "on", "none", {}, git, op=stop_completion)
            case("completion_a", name, "transcript", "on", "none", {}, "dirty", pilot=True, op=stop_completion)
            for pname, prior in priors.items():
                case("completion_b", name, "transcript", "on", pname, prior, "dirty", op=stop_completion)
            for cname in COMPLETION_CONFIGS:
                case("completion_c", name, "transcript", cname, "none", {}, "dirty", op=stop_completion)
            for payload in PAYLOADS:
                case("completion_c", name, payload, "on", "none", {}, "clean", op=stop_completion)
            for payload in PAYLOADS:
                for cname in STATE_CONFIGS:
                    for pname, prior in STATE_PRIORS.items():
                        case("state", name, payload, cname, pname, prior, "clean", op=stop_state)
    return {"transcripts": transcripts, **groups}


_CACHE: dict = {}


def _data() -> dict:
    if not _CACHE:
        _CACHE.update(_build())
    return _CACHE


def _group_file(group: str):
    def build() -> str:
        return g.HEADER + "\n" + g.ts_const("CASES", _data()[group], ROW, compact=True)
    return build


def _meta() -> str:
    data = _data()
    return (g.HEADER + "\n"
            + g.ts_const("TRANSCRIPTS", data["transcripts"], "Readonly<Record<string, string>>", compact=True)
            + "\n" + g.ts_const("COMPLETION_CONFIGS", COMPLETION_CONFIGS)
            + "\n" + g.ts_const("STATE_CONFIGS", STATE_CONFIGS)
            + "\n" + g.ts_const("NOW", NOW))


TARGETS = {
    FIXTURES / "stopops-meta.gen.ts": _meta,
    FIXTURES / "stopops-completion-a.gen.ts": _group_file("completion_a"),
    FIXTURES / "stopops-completion-b.gen.ts": _group_file("completion_b"),
    FIXTURES / "stopops-completion-c.gen.ts": _group_file("completion_c"),
    FIXTURES / "stopops-state.gen.ts": _group_file("state"),
}
