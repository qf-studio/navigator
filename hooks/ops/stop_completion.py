#!/usr/bin/env python3
"""stop_completion op — Stop-event forced-continuation gate (TASK-62 Phase 2).

Channel: mem-051 (S2, CC 2.1.205) — Stop ``continue: true`` is a NO-OP;
``decision: block`` + reason IS the forced-continuation mechanism (exactly
one continuation; the reason is injected as 'Stop hook feedback:'). The
emitter is signals.stop_block; ``continue`` is never touched here.

Dual condition (BOTH must hold to continue):
  1. completion indicators UNMET — the exit_gate.evaluate_exit vocabulary
     (code_committed, tests_passing, code_simplified, docs_updated,
     ticket_closed, marker_created) read from state ``completion.indicators``
     and evaluated by skills/nav-loop/functions/exit_gate.py when importable
     (file-location import so the op stays standalone); the vendored
     vocabulary + min-heuristics fallback below covers a missing skill tree
     (a sync test pins the vendored constants against the skill source).
  2. NO nav-signal v3 ``exit`` in the last assistant text (signals.parse over
     strip_all()'d text, mem-034; frozen pilot-signal v2 blocks also count).

Circuit breaker, layered (risk register):
  - ``completion.stop_fuse`` consumed on emit — single-shot per turn. Re-armed
    ONLY by the stop_state reset barrel at the next CLEAN turn end (when this
    gate blocks, the runtime short-circuits stop_state: a forced continuation
    is the same turn, so the fuse deliberately survives it — after a forced
    continuation the very next turn stays suppressed until the barrel runs).
  - ``completion.held_count`` capped at stop_completion.max_continues
    (default 2); reset to 0 by the same stop_state barrel (slot name verified
    against ops/stop_state.py reset_turn_slots).
  - ``stop_hook_active`` short-circuit — the harness belt mem-051 proved real.
  - NEVER continues on a turn without mutating tool_use (mem-037: stamping /
    blocking on conversational turns deadlocked the v6 enforcer). Tool names
    come from the whole turn span of the transcript (nav_hook_lib.transcript
    entries scanned back to the last real user prompt — the final assistant
    message is usually text-only, so stop_state's single-message reader would
    read every real turn as non-mutating); the mutating vocabulary is
    stop_state.TASK_ACTION_TOOLS (one vocabulary, no drift). Bash-only turns
    are further classified by command allowlists (TASK-70) and, above that,
    by working-tree digest evidence (TASK-71): an unchanged
    ``git status --porcelain`` digest across consecutive Stops overrules a
    vocabulary-mutating classification — ops turns (daemon restarts, sqlite
    reads, sibling-repo work) stop reading as "mutated the codebase".
  - Kill switches: stop_completion.enabled AND stop_completion.continue_enabled
    must BOTH be truthy (both seed OFF in config.DEFAULTS; a missing block is
    off). ctx.pilot_executor disables unconditionally, regardless of config —
    two loop supervisors must not fight.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path

from nav_hook_lib import config, hio, memory, sentinels, signals, transcript

try:  # package context (runtime imports ops.stop_completion)
    from . import stop_state
except ImportError:  # bare sibling context (unittest discovery from ops/)
    import stop_state

# Vendored from skills/nav-loop/functions/exit_gate.py (documented indicator
# vocabulary + MIN_HEURISTICS_DEFAULT). Kept in sync by a test that reads the
# skill source; used only when the file-location import below is unavailable.
INDICATOR_VOCABULARY = (
    "code_committed",
    "tests_passing",
    "code_simplified",
    "docs_updated",
    "ticket_closed",
    "marker_created",
)
MIN_HEURISTICS = 2

EXIT_GATE_RELPATH = Path("skills") / "nav-loop" / "functions" / "exit_gate.py"

DEFAULT_MAX_CONTINUES = 2

# Tool names whose tool_use input carries an on-disk file path (TASK-65).
FILE_PATH_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})

# A turn ran the test suite when a Bash command matches this (mem-034: only
# fixed patterns, never transcript text, ever reach the reason string).
TEST_CMD_RE = re.compile(r"\b(make test|pytest|(python3?\s+-m\s+)?unittest)\b")

# Read-only Bash classification (TASK-70): TASK_ACTION_TOOLS counts Bash
# wholesale, so pure-inspection turns (grep/ls/git status) false-fired the
# gate as "mutated the codebase". A Bash-only turn is mutating only if some
# command falls OUTSIDE this allowlist; unknown commands stay mutating (the
# gate may over-fire on odd inspection commands, never under-fire on writes).
READONLY_BASH_CMDS = frozenset({
    "ls", "find", "grep", "rg", "cat", "head", "tail", "wc", "echo", "pwd",
    "which", "file", "stat", "tree", "du", "df", "type", "env", "printenv",
    "uname", "whoami", "date", "diff",
    # TASK-71: inspection staples observed false-firing live (2026-07-16).
    "ps", "sort", "uniq", "cut", "tr", "jq", "basename", "dirname",
    "realpath", "readlink", "printf", "read", "sleep", "true", "false",
    "test", "[", "[[",
    # TASK-85: inspection staples observed false-firing live (2026-10-03).
    "lsof", "pgrep", "nproc", "sw_vers",
})
# curl reads unless it names an output file (TASK-85): any short flag cluster
# carrying o/O (-o, -O, -sSo) or a long --output*/--remote-name* flag writes.
_CURL_WRITE_LONG = ("--output", "--remote-name")
READONLY_GIT_SUBCMDS = frozenset({
    "status", "log", "diff", "show", "branch", "rev-parse", "describe",
    "shortlog", "blame", "remote", "ls-files",
    # TASK-71: object/ref inspection; fetch writes refs, never the tree.
    "fetch", "ls-tree", "ls-remote", "cat-file", "show-ref", "rev-list",
})
# gh resolved by subcommand PAIR, mirroring the git pattern (TASK-71): the
# CLI mixes reads (pr view) and writes (pr merge) under one head. Unlisted
# pairs stay mutating — same over-fire-only direction as unknown commands.
READONLY_GH_SUBCMDS = frozenset({
    "pr view", "pr list", "pr checks", "pr diff", "pr status",
    "issue view", "issue list", "issue status",
    "run view", "run list", "workflow view", "workflow list",
    "release view", "release list", "repo view", "label list",
    "search prs", "search issues", "search code", "search repos",
})
_BASH_SEGMENT_SPLIT = re.compile(r"\|\||&&|;|\||\n")
# Innermost $(...) / `...` command substitutions (TASK-71): their content is
# validated as a command in its own right, then removed so the outer text's
# heads and assignments tokenize cleanly (`LOG=$(ls)` -> `LOG=`).
_SUBSTITUTION_RE = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# Output redirects: any target other than /dev/null or a file descriptor
# (&1, &2) makes the segment mutating — closes the `echo x > file` hole that
# allowlisted heads opened (TASK-71; safe direction, quoted '>' may over-fire).
_REDIRECT_RE = re.compile(r"[0-9]*>>?\s*(\S+)")
# Shell words that wrap another command in the same segment — stripped, then
# the remainder is classified. `for` is standalone: its segment holds only
# the loop variable and word list; the body arrives as later segments.
_TRANSPARENT_HEADS = frozenset({
    "if", "elif", "then", "else", "do", "while", "until", "!", "time",
})
_STANDALONE_HEADS = frozenset({"for", "done", "fi", "esac", "case"})


def _load_exit_gate():
    """skills/nav-loop/functions/exit_gate.py as a module, or None.

    File-location import (no sys.path mutation) resolved through the lib's
    plugin-root resolver; ANY failure degrades to the vendored fallback so
    the op is importable and functional standalone.
    """
    try:
        plugin_dir = memory._plugin_dir()  # the lib's plugin-root resolver
        if plugin_dir is None:
            return None
        path = plugin_dir / EXIT_GATE_RELPATH
        if not path.is_file():
            return None
        spec = importlib.util.spec_from_file_location("nav_loop_exit_gate", path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def _evaluate_heuristics(filtered: dict):
    """(heuristics_satisfied, met) via exit_gate.evaluate_exit or the fallback."""
    gate = _load_exit_gate()
    if gate is not None:
        try:
            result = gate.evaluate_exit(
                filtered, exit_signal=False, min_heuristics=MIN_HEURISTICS
            )
            met = int(result.get("heuristics_met", 0))
            return bool(result.get("heuristics_satisfied", met >= MIN_HEURISTICS)), met
        except Exception:
            pass
    met = sum(1 for name in INDICATOR_VOCABULARY if filtered.get(name))
    return met >= MIN_HEURISTICS, met


def _collect_tool_evidence(name: str, block: dict, file_paths: list, bash_uses: list):
    """Pull observable evidence out of one tool_use block (TASK-65).

    File-mutating tools contribute their target path (file_path or, for
    notebooks, notebook_path); Bash contributes ``(tool_use_id, command)`` so
    the caller can pair it with the is_error of the FOLLOWING tool_result.
    """
    inp = block.get("input")
    if not isinstance(inp, dict):
        return
    if name in FILE_PATH_TOOLS:
        for key in ("file_path", "notebook_path"):
            val = inp.get(key)
            if isinstance(val, str) and val:
                file_paths.append(val)
    elif name == "Bash":
        cmd = inp.get("command")
        if isinstance(cmd, str):
            bash_uses.append((block.get("id"), cmd))


def _turn_scan(payload: dict):
    """(last_assistant_text, turn_tool_names, evidence) for the ENDING turn.

    Tool names are collected across every assistant message back to the last
    genuine user prompt (string content or a text block — tool_result-only
    user entries are transcript plumbing, not a turn boundary). The text is
    the LAST assistant message's text, with the harness-provided inline
    ``last_assistant_message`` winning when present (v6 precedence) — but the
    inline field carries no tool information, so tools always come from the
    transcript (an inline-only payload therefore reads as non-mutating and
    never continues; the safe direction under mem-037).

    ``evidence`` (TASK-65) is gathered over the SAME turn span so the
    completion-indicator populator sees observable turn results: file paths
    from Edit/Write/MultiEdit/NotebookEdit inputs, and each Bash command paired
    with whether its matching tool_result was is_error (matched by
    tool_use_id; an unmatched command defaults to not-errored).
    """
    text = ""
    tools: set = set()
    file_paths: list = []
    bash_uses: list = []          # (tool_use_id, command) in the turn span
    result_errors: dict = {}      # tool_use_id -> is_error(bool)
    tpath = payload.get("transcript_path")
    entries = transcript.tail_entries(tpath) if tpath else []
    for obj in reversed(entries):
        msg = obj.get("message") or obj
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")
        if role == "user":
            if isinstance(content, str) and content.strip():
                break  # genuine user prompt: turn boundary
            if isinstance(content, list):
                if any(
                    isinstance(block, dict) and block.get("type") == "text"
                    for block in content
                ):
                    break
                for block in content:  # tool_result plumbing: harvest is_error
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_result":
                        tid = block.get("tool_use_id")
                        if isinstance(tid, str):
                            result_errors[tid] = bool(block.get("is_error"))
            continue  # tool_result plumbing rides the user role
        if role != "assistant":
            continue
        chunks = []
        if isinstance(content, str):
            chunks.append(content)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if isinstance(block.get("text"), str):
                    chunks.append(block["text"])
                if block.get("type") == "tool_use" and isinstance(block.get("name"), str):
                    name = block["name"]
                    tools.add(name)
                    _collect_tool_evidence(name, block, file_paths, bash_uses)
        if chunks and not text:
            text = "\n".join(chunks)
    inline = payload.get("last_assistant_message")
    if isinstance(inline, str) and inline.strip():
        text = inline
    bash = [(cmd, result_errors.get(tid, False)) for tid, cmd in bash_uses]
    return text, tools, {"file_paths": file_paths, "bash": bash}


def _bash_readonly(command) -> bool:
    """True when every command in a Bash string is a read-only tool.

    Segments split on ``&&``/``||``/``;``/``|``/newline. Before the head
    check (TASK-71): ``$(...)``/backtick substitutions are validated
    recursively then removed; output redirects to anything but /dev/null or
    a file descriptor are mutating; leading ``VAR=`` assignments and
    control-flow words are stripped; ``git`` and ``gh`` resolve by
    subcommand; ``command -v`` is a lookup. Anything unrecognized → False
    (mutating) so writes are never missed.
    """
    if not isinstance(command, str) or not command.strip():
        return True
    text = command
    while True:  # peel substitutions innermost-out; text strictly shrinks
        matches = list(_SUBSTITUTION_RE.finditer(text))
        if not matches:
            break
        for match in matches:
            if not _bash_readonly(match.group(1) or match.group(2) or ""):
                return False
        text = _SUBSTITUTION_RE.sub("", text)
    for match in _REDIRECT_RE.finditer(text):
        target = match.group(1)
        if target != "/dev/null" and not target.startswith("&"):
            return False
    for segment in _BASH_SEGMENT_SPLIT.split(text):
        tokens = segment.strip().split()
        while tokens and (
            tokens[0] in _TRANSPARENT_HEADS or _ASSIGNMENT_RE.match(tokens[0])
        ):
            tokens = tokens[1:]
        if not tokens:
            continue  # assignment-only / bare control-flow segment
        head = tokens[0]
        if head in _STANDALONE_HEADS:
            continue
        if head == "command":
            rest = tokens[1:]
            if rest and rest[0] in ("-v", "-V"):
                continue  # pure lookup: prints a path, executes nothing
            tokens = rest
            if not tokens:
                continue
            head = tokens[0]
        if head == "git":
            sub = next((t for t in tokens[1:] if not t.startswith("-")), "")
            if sub not in READONLY_GIT_SUBCMDS:
                return False
        elif head == "gh":
            pair = [t for t in tokens[1:] if not t.startswith("-")][:2]
            if " ".join(pair) not in READONLY_GH_SUBCMDS:
                return False
        elif head == "curl":
            if any(_curl_writes(t) for t in tokens[1:]):
                return False
        elif head not in READONLY_BASH_CMDS:
            return False
    return True


def _curl_writes(token: str) -> bool:
    if token.startswith("--"):
        return token.startswith(_CURL_WRITE_LONG)
    return token.startswith("-") and ("o" in token or "O" in token)


# TASK-85: the tree digest is a property of the repo, not the session, and is
# compared per session: `tree.digests[session_id]` lives outside the
# session-scoped `completion` section, so a Stop in another session sharing
# this repo cannot erase it. Bounded to the most recent sessions.
TREE_DIGESTS_MAX = 8


def _prev_digest(ctx, completion: dict):
    sid = getattr(ctx, "session_id", None)
    tree = ctx.state.get("tree")
    digests = tree.get("digests") if isinstance(tree, dict) else None
    if sid and isinstance(digests, dict) and isinstance(digests.get(sid), str):
        return digests[sid]
    return completion.get("tree_digest")


def _record_digest(ctx, digest: str) -> None:
    sid = getattr(ctx, "session_id", None)
    if not sid:
        return
    tree = ctx.state.get("tree")
    if not isinstance(tree, dict):
        tree = {}
        ctx.state["tree"] = tree
    digests = tree.get("digests")
    if not isinstance(digests, dict):
        digests = {}
        tree["digests"] = digests
    digests.pop(sid, None)
    digests[sid] = digest
    while len(digests) > TREE_DIGESTS_MAX:
        del digests[next(iter(digests))]


def _turn_mutating(tools: set, evidence: dict, prev_digest=None,
                   digest=None) -> bool:
    """Did this turn actually mutate anything? (TASK-70 refinement of mem-037.)

    Vocabulary stays anchored to stop_state.TASK_ACTION_TOOLS (no drift);
    the refinement is that a Bash-ONLY action turn is mutating only when at
    least one of its commands is not read-only. A Bash tool_use with no
    harvested command reads as non-mutating — the safe direction (mem-037:
    never block a turn that did no work).

    Tree evidence overrules vocabulary (TASK-71): when the working-tree
    digest at this Stop equals the one recorded at the previous Stop, a
    Bash-only turn did not mutate THIS codebase — whatever its commands were
    named (daemon restarts, sqlite reads, sibling-repo work). File tools and
    Task/Agent turns never take this path: subagents and Edit/Write carry
    their own mutation evidence. Missing digests fall back to vocabulary.
    """
    action = tools & stop_state.TASK_ACTION_TOOLS
    if not action:
        return False
    if action - {"Bash"}:
        return True
    if not any(not _bash_readonly(cmd) for cmd, _ in evidence.get("bash", ())):
        return False
    if prev_digest is not None and digest is not None and prev_digest == digest:
        return False
    return True


def _git_clean(root) -> bool:
    """True when the git working tree at ``root`` is clean.

    ``git status --porcelain`` with a ~2s timeout: empty stdout AND
    returncode 0 → clean. ANY failure/timeout/non-repo → False (mem-034:
    subprocess output never touches stderr or the reason string).
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root), capture_output=True, text=True, timeout=2,
        )
    except Exception:
        return False
    return result.returncode == 0 and not result.stdout.strip()


def _tree_digest(root):
    """sha256 hex of ``git status --porcelain`` at ``root``, or None.

    The digest is the turn-to-turn working-tree fingerprint for TASK-71
    mutation evidence (kept separate from _git_clean so tests patching one
    never affect the other). ANY failure/timeout/non-repo → None; callers
    treat None as 'no evidence' and fall back to vocabulary classification.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root), capture_output=True, text=True, timeout=2,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return hashlib.sha256(result.stdout.encode("utf-8", "replace")).hexdigest()


def _derive_indicators(evidence: dict, cfg, payload: dict) -> dict:
    """Completion indicators inferred from OBSERVABLE turn evidence (TASK-65).

    Only True entries are returned; the caller ORs these with any explicit
    ``completion.indicators`` state (a state True still wins). The six-name
    vocabulary is covered as follows:

      code_committed   git working tree clean at the project root.
      tests_passing    a turn Bash command ran the suite and did NOT error.
      docs_updated     a turn touched a ``*.md`` file.
      marker_created   a turn touched a path under ``/.context-markers/``.
      ticket_closed    True only when no PM tool is configured
                       (project_management == 'none' → nothing to close). With
                       a PM configured this stays best-effort False: closing a
                       real ticket needs a PM API call this hook must not make.
      code_simplified  left unmet — no reliable observable signal exists for
                       "code was simplified" from transcript/disk evidence.
    """
    indicators = {}
    if _git_clean(hio.project_root(payload)):
        indicators["code_committed"] = True
    for command, is_error in evidence.get("bash", ()):
        if not is_error and TEST_CMD_RE.search(command or ""):
            indicators["tests_passing"] = True
            break
    paths = evidence.get("file_paths", ())
    if any(isinstance(p, str) and p.endswith(".md") for p in paths):
        indicators["docs_updated"] = True
    if any(isinstance(p, str) and "/.context-markers/" in p for p in paths):
        indicators["marker_created"] = True
    if config.get(cfg, "project_management", "none") == "none":
        indicators["ticket_closed"] = True
    return indicators


def _max_continues(cfg) -> int:
    value = config.get(cfg, "stop_completion.max_continues", DEFAULT_MAX_CONTINUES)
    try:
        result = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_CONTINUES
    return result if result >= 0 else DEFAULT_MAX_CONTINUES


def _held_count(completion: dict) -> int:
    value = completion.get("held_count", 0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return int(value)


def _reason(met: int, unmet: list) -> str:
    # Fixed strings + indicator names only — no payload/transcript text can
    # echo through the injected 'Stop hook feedback:' message (mem-034).
    return (
        "Navigator stop_completion: this turn mutated the codebase but looks "
        f"unfinished — {met}/{len(INDICATOR_VOCABULARY)} completion indicators met "
        f"(unmet: {', '.join(unmet)}) and no completion signal was emitted. "
        "Continue and finish the outstanding work (commit, tests, docs, ticket, "
        "marker — as applicable). When the task is genuinely complete, end your "
        "reply with an HTML-comment-wrapped exit signal so the user never sees "
        'it: <!-- nav-signal:v3:{"type":"exit","reason":"..."} --> . '
        "This forced continuation is single-shot for this turn."
    )


def run(ctx):
    # Unconditional Pilot disable — regardless of config (plan decision:
    # two loop supervisors must not fight). The runtime merge belt is the
    # backstop; this check is the mechanism.
    if ctx.pilot_executor:
        return None
    payload = ctx.payload
    if payload.get("stop_hook_active"):
        return None  # already inside a Stop chain (harness belt, mem-051)

    # Both kill switches must be truthy; both seed OFF (config.DEFAULTS), so
    # a missing block means off. The registry config gate covers .enabled
    # too; re-checked here for standalone callers.
    if not config.get(ctx.config, "stop_completion.enabled", False):
        return None
    if not config.get(ctx.config, "stop_completion.continue_enabled", False):
        return None

    stored = ctx.state.get("completion")
    completion = stored if isinstance(stored, dict) else {}
    # TASK-71 tree evidence: capture the working-tree digest at EVERY armed
    # Stop — before the fuse/cap short-circuits — so the next turn compares
    # against this turn's true end state. stop_hook_active stops return
    # above without capturing: a forced continuation's writes land in the
    # NEXT comparison, which can only over-fire, never under-fire.
    prev_digest = _prev_digest(ctx, completion)
    digest = _tree_digest(hio.project_root(payload))
    if digest is not None and digest != prev_digest:
        if ctx.state.get("completion") is not completion:
            ctx.state["completion"] = completion
        completion["tree_digest"] = digest
        _record_digest(ctx, digest)
    if completion.get("stop_fuse"):
        return None  # single-shot per turn; re-armed by the stop_state barrel
    held = _held_count(completion)
    if held >= _max_continues(ctx.config):
        return None  # continue-counter cap (belt under the fuse)

    text, tools, evidence = _turn_scan(payload)
    if not _turn_mutating(tools, evidence, prev_digest, digest):
        return None  # mem-037: never continue a non-mutating turn (TASK-70/71)

    clean = sentinels.strip_all(text)  # mem-034: never scan unstripped text
    if any(sig.get("type") == "exit" for sig in signals.parse(clean)):
        return None  # explicit completion signal wins

    # Observable turn evidence (TASK-65) OR'd with any explicit state
    # indicators — a state True still wins, so other writers keep counting.
    state_ind = completion.get("indicators")
    state_ind = state_ind if isinstance(state_ind, dict) else {}
    derived = _derive_indicators(evidence, ctx.config, payload)
    filtered = {
        name: bool(state_ind.get(name)) or bool(derived.get(name))
        for name in INDICATOR_VOCABULARY
    }
    satisfied, met = _evaluate_heuristics(filtered)
    if satisfied:
        return None

    # Emit: consume the fuse + count the hold BEFORE returning the block.
    if ctx.state.get("completion") is not completion:
        ctx.state["completion"] = completion
    completion["stop_fuse"] = True
    completion["held_count"] = held + 1
    completion["signal"] = {
        "exit_seen": False,
        "heuristics_met": met,
        "held_at": ctx.now,
    }
    unmet = [name for name in INDICATOR_VOCABULARY if not filtered.get(name)]
    # Channel shape from the spike-proven emitter (mem-051): decision:block
    # + reason; continue:true is never used (it is a no-op).
    doc = json.loads(signals.stop_block(_reason(met, unmet)))
    return {"decision": doc["decision"], "reason": doc["reason"]}
