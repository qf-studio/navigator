#!/usr/bin/env python3
"""nav_hook_lib.runtime — the v7 dispatch pipeline (TASK-60 Phases 2/3).

One dispatch() call per hook event. The shim (hooks/nav_dispatch.py) parses
argv/stdin and delegates here; this module owns the whole pipeline:

    load config once -> config.is_pilot_executor() once -> state.lock ->
    state.load once -> ops (gates -> responders -> injectors -> recorders) ->
    merge -> state.save once -> DispatchResult

Contract highlights (TASK-60 dispatch contract):
  - Fail-open everywhere: dispatch() never raises; a dispatch-level failure
    returns DispatchResult(None, 0, <sentinel line>) and best-effort records
    health. A project without .agent/ degrades silently (no output, no
    writes — Navigator must not scaffold foreign projects).
  - Phase pipeline: ops execute in phase order gates -> responders ->
    injectors -> recorders (stable registry order within a phase). A GATE
    result carrying decision / permission deny / nonzero exit_code
    short-circuits all rightward phases; sibling gates still run.
  - Soft deadline: EVENT_TIMEOUTS minus a 0.5s margin, checked before each
    non-gate op. Gates are EXEMPT — they always run (mem-037: gate inputs are
    never starved or half-written). A deadline-skipped op leaves a
    {op, error: "deadline-skipped", ts} note in meta.op_errors — an
    observability note, not a crash (no sentinel, no health write).
  - Per-op isolation: an op crash appends {op, error, ts} to state
    meta.op_errors, emits ONE `[nav-dispatch-error]` sentinel line (exception
    class name only — payload/prompt text NEVER reaches stderr, mem-034),
    writes the health file, and siblings still run. Isolation catches
    BaseException (KeyboardInterrupt re-raised): v6 hooks use sys.exit as
    control flow, so a SystemExit from an op is crash-class — its exit code
    is recorded in the note but NEVER propagated. op_errors and the health
    file store the exception CLASS only (same redaction as the sentinel
    line) so payload/prompt text cannot persist or echo into model context.
    A missing op module is the normal state until TASK-61 lands: op_errors
    note only, no sentinel, no health write.
  - Merge rules: additional_context concatenated in registry order then
    budget.clamp(text, event); first decision:'block' wins; permission deny
    beats ask; `continue` is false-wins (AND): the key is emitted (as false)
    ONLY when some op explicitly set continue_ False — continue:false is the
    only meaningful emission (mem-051), true is the harness default and is
    omitted; exit_code = max of op exit_codes (a deliberate gate exit-2
    survives); stderr lines joined. Exactly one output document on stdout,
    or None. `ack` (TASK-61 parity): when some op set ack truthy and the
    merged document would otherwise be EMPTY, the bare `{}` doc is emitted —
    the v6 side-effect hooks' acknowledgment shape; any real output key
    subsumes it.
  - Pilot merge belt: when config.is_pilot_executor() is true, every
    blocking key is stripped from op results BEFORE merging (decision /
    reason, permission deny/ask, nonzero exit_code, continue_ False);
    non-blocking output (contexts, state writes, system_message) flows
    normally. Ops SHOULD still check ctx.pilot_executor to skip wasted
    work — the belt guarantees no block escapes regardless (the v6 failure
    class was one missed per-hook check = interactive block under Pilot).
  - Channels route through nav_hook_lib.signals: proven-envelope events
    (SessionStart / SubagentStart / PostToolUse / PostToolUseFailure) emit
    hookSpecificOutput.additionalContext; UserPromptSubmit context-only
    output uses the v6-proven plain-stdout channel (signals.
    user_prompt_context) and folds into the JSON doc only when other keys
    are present; events with no spike-proven context channel drop context
    silently (mem-035 discipline).
  - Health: any op/dispatch error writes .agent/.nav-dispatch-health.json
    (atomic via hio). The next SessionStart dispatch with surfaced:false
    PREPENDS one short line to additional_context (before op contexts,
    pre-clamp — the line is <=160 chars and budget losses come from the
    tail, so a full budget cannot silently eat it) and flips surfaced:true.

Documented deviations from the contract letter:
  - sentinels.TAGS has no "nav-dispatch-error" entry and the lib is frozen
    for this task, so the bracketed `[nav-dispatch-error]` line is formatted
    here (with zero payload-derived text, satisfying mem-034 by
    construction); the shim routes it to stderr via DispatchResult.stderr.
  - UserPromptSubmit context-only output is plain text, not JSON — the only
    v6-proven delivery channel for that event (see signals module).

Cold-start discipline: op modules and the registry import lazily inside
dispatch(); scoring/memory/transcript are never imported here
(UserPromptSubmit dispatch must stay <=200ms p95).

Pure Python stdlib only.
"""
from __future__ import annotations

import importlib
import json
import re
import time
import types
from dataclasses import dataclass
from datetime import datetime, timezone

try:
    from . import budget, config, hio, rejects, signals, state
except ImportError:  # top-level module under per-directory unittest discovery
    import budget
    import config
    import hio
    import rejects
    import signals
    import state

# Manifest timeouts per event (seconds); the soft deadline is timeout - margin,
# checked BEFORE each non-gate op. Gates always run (mem-037). PostToolUse and
# PostCompact keep their v6 10s allowance (two v6 PostToolUse hooks had 10s
# EACH; PostCompact had 10s) — 5s shared would be a silent regression.
EVENT_TIMEOUTS = {"SessionStart": 10, "PostToolUse": 10, "PreCompact": 30, "PostCompact": 10}
DEFAULT_TIMEOUT_SECONDS = 5
DEADLINE_MARGIN_SECONDS = 0.5

# Pipeline phase order. Unknown phases sort after recorders (deadline-subject).
PHASE_ORDER = ("gates", "responders", "injectors", "recorders")

# Op modules live at hooks/ops/<name>.py; the shim puts hooks/ on sys.path.
OPS_PACKAGE = "ops"

# Crash-surfacing sentinel prefix (see module docstring on why it is
# formatted here rather than via sentinels.wrap).
ERROR_SENTINEL = "[nav-dispatch-error]"

HEALTH_FILE_NAME = ".nav-dispatch-health.json"

# OpSpec.matcher applies only to tool events (tested against tool_name).
_TOOL_MATCHER_EVENTS = ("PreToolUse", "PostToolUse")

_ERROR_TEXT_LIMIT = 200
_SURFACE_LINE_LIMIT = 160

# Separator for concatenated additional_context strings (registry order).
_CONTEXT_SEPARATOR = "\n"


@dataclass
class DispatchResult:
    """Merged outcome of one dispatch: stdout doc (or None), exit code, stderr."""

    stdout: str | None = None
    exit_code: int = 0
    stderr: str | None = None


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _make_clock(now):
    """Normalize the injectable ``now`` into a zero-arg clock callable.

    None -> time.time; a callable is used as-is (tests inject advancing
    clocks for deadline coverage); a number becomes a constant clock.
    """
    if now is None:
        return time.time
    if callable(now):
        return now
    value = float(now)
    return lambda: value


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _describe_error(error) -> str:
    """Class-only error text for state/health records.

    Exception MESSAGES are dropped everywhere they could persist or surface:
    they can embed payload/prompt text (including loop triggers), and health
    lines re-enter model context at SessionStart. Same redaction rule as
    _error_line. SystemExit is the one enrichment: its integer exit code is
    recorded (an int cannot echo payload text); a string code is dropped.
    """
    if isinstance(error, SystemExit):
        code = error.code
        suffix = f" code={code}" if code is None or isinstance(code, int) else ""
        return f"SystemExit{suffix}"
    if isinstance(error, BaseException):
        return type(error).__name__
    return " ".join(str(error).split())[:_ERROR_TEXT_LIMIT]


def _error_line(event: str, op_name: str, error) -> str:
    """The ONE stderr sentinel line for a crash.

    Carries only the exception class name — never the message, so payload /
    prompt text cannot echo into stderr (mem-034).
    """
    kind = type(error).__name__ if isinstance(error, BaseException) else str(error)
    return f"{ERROR_SENTINEL} event={event} op={op_name} error={kind}"


def _note_op_error(runtime_state: dict, op_name: str, error_text: str, ts: float) -> None:
    """Append {op, error, ts} to state meta.op_errors (bounded by state.save)."""
    meta = runtime_state.setdefault("meta", {})
    errors = meta.get("op_errors")
    if not isinstance(errors, list):
        errors = []
        meta["op_errors"] = errors
    errors.append({"op": op_name, "error": error_text, "ts": _iso(ts)})


def _record_health(agent_dir, event: str, op_name: str, error_text: str, ts: float) -> None:
    """Overwrite the dispatch health file with the latest error (atomic)."""
    doc = {
        "last_error": {"ts": _iso(ts), "event": event, "op": op_name, "error": error_text},
        "surfaced": False,
    }
    hio.atomic_write_json(agent_dir / HEALTH_FILE_NAME, doc)


def _surface_health(agent_dir):
    """Return the one-line surfacing string when an unsurfaced error exists.

    Flips surfaced:true on the health file so the notice appears exactly once.
    Returns None when there is nothing to surface.
    """
    path = agent_dir / HEALTH_FILE_NAME
    doc = hio.safe_json(path)
    if not doc or doc.get("surfaced") is not False:
        return None
    last = doc.get("last_error")
    if not isinstance(last, dict):
        return None
    line = "nav-dispatch: last dispatch error: {}/{}: {}".format(
        last.get("event", "?"), last.get("op", "?"), last.get("error", "")
    )[:_SURFACE_LINE_LIMIT]
    doc["surfaced"] = True
    hio.atomic_write_json(path, doc)
    return line


def _default_registry() -> dict:
    """Lazy-import registry.EVENT_OPS; {} when the module is absent (fail-open)."""
    try:
        try:
            from . import registry as registry_module
        except ImportError:
            import registry as registry_module
    except Exception:
        return {}
    table = getattr(registry_module, "EVENT_OPS", None)
    return table if isinstance(table, dict) else {}


def _phase_rank(spec) -> int:
    phase = getattr(spec, "phase", None)
    try:
        return PHASE_ORDER.index(phase)
    except ValueError:
        return len(PHASE_ORDER)


def _config_allows(cfg: dict, spec) -> bool:
    """OpSpec.config_key gate: <key>.enabled must not be explicitly false."""
    key = getattr(spec, "config_key", None)
    if not key:
        return True
    return bool(config.get(cfg, f"{key}.enabled", True))


def _matcher_allows(spec, event: str, payload: dict) -> bool:
    """OpSpec.matcher regex vs payload tool_name; tool events only; None = always."""
    matcher = getattr(spec, "matcher", None)
    if not matcher or event not in _TOOL_MATCHER_EVENTS:
        return True
    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str):
        return False
    try:
        return re.fullmatch(matcher, tool_name) is not None
    except re.error:
        return False  # invalid matcher regex: skip the op (fail-open)


def _is_blocking(result: dict) -> bool:
    """True when a gate result must short-circuit all rightward phases."""
    if result.get("decision"):
        return True
    if result.get("permission_decision") == "deny":
        return True
    exit_code = result.get("exit_code")
    return isinstance(exit_code, int) and exit_code != 0


def _suppress_blocking(result: dict) -> dict:
    """Pilot merge belt: strip every blocking key from one op result.

    Applied to EVERY op result when pilot_executor is true, before merging
    and before the gate short-circuit check — so a would-block gate neither
    blocks nor starves rightward phases under Pilot. Non-blocking output
    (additional_context, system_message, stderr) passes through untouched.
    Ops SHOULD still check ctx.pilot_executor to skip wasted work; this belt
    guarantees no block escapes even when one forgets (the v6 failure class).
    """
    cleaned = dict(result)
    cleaned.pop("decision", None)
    cleaned.pop("reason", None)
    if cleaned.get("permission_decision") in ("deny", "ask"):
        cleaned.pop("permission_decision", None)
        cleaned.pop("permission_reason", None)
    code = cleaned.get("exit_code")
    if isinstance(code, int) and not isinstance(code, bool) and code != 0:
        cleaned.pop("exit_code")
    if cleaned.get("continue_") is False:
        cleaned.pop("continue_")
    return cleaned


def _import_op(name: str):
    return importlib.import_module(f"{OPS_PACKAGE}.{name}")


def _log_reject(result: dict, cfg, agent_dir, event: str, op_name: str, payload: dict,
                session_id, pilot_executor: bool, ts: float) -> dict:
    """TASK-88: the ONE reject-log append point in the Python runtime.

    A refusing op attaches ``reject: {reason, evidence}`` to its blocking
    result. The key is always stripped before the merge (it is bookkeeping,
    not output); a line is appended only when the result actually blocks and
    ``reject_log.enabled`` is true. Under Pilot the merge belt will strip the
    block next, so the line carries ``suppressed: true`` — the refusal was
    computed, not applied. A failed append never reaches the op or the user.
    """
    if "reject" not in result:
        return result
    cleaned = dict(result)
    reject = cleaned.pop("reject")
    if not isinstance(reject, dict) or not _is_blocking(cleaned):
        return cleaned
    if not config.get(cfg, "reject_log.enabled", True):
        return cleaned
    tool = payload.get("tool_name") if event in _TOOL_MATCHER_EVENTS else None
    try:
        rejects.append(agent_dir, rejects.line(
            _iso(ts), session_id, event, op_name, tool, reject, suppressed=pilot_executor))
    except Exception:
        pass
    return cleaned


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def _merge_outputs(event: str, outcomes: list, extra_context_line):
    """Merge op results into (stdout_doc_or_None, exit_code, op_stderr_lines).

    ``outcomes`` is a list of (registry_index, result_dict); merge rules apply
    in registry order regardless of phase execution order.
    ``extra_context_line`` (the health surfacing line, <=160 chars) is
    PREPENDED before op contexts pre-clamp: budget.clamp cuts from the tail,
    so a full event budget can never silently eat it.
    """
    contexts: list[str] = []
    system_messages: list[str] = []
    stderr_lines: list[str] = []
    continue_values: list[bool] = []
    decision_reason = None
    permission = None  # (decision, reason)
    exit_code = 0
    ack = False  # v6 `{}` acknowledgment (TASK-61 parity; see docstring)

    for _, result in sorted(outcomes, key=lambda item: item[0]):
        if result.get("ack"):
            ack = True
        context = result.get("additional_context")
        if isinstance(context, str) and context:
            contexts.append(context)
        if decision_reason is None and result.get("decision") == "block":
            decision_reason = str(result.get("reason") or "")
        perm = result.get("permission_decision")
        if perm in ("deny", "ask"):
            if permission is None or (perm == "deny" and permission[0] != "deny"):
                permission = (perm, str(result.get("permission_reason") or ""))
        if "continue_" in result:
            continue_values.append(bool(result.get("continue_")))
        code = result.get("exit_code")
        if isinstance(code, int) and not isinstance(code, bool):
            exit_code = max(exit_code, code)
        err = result.get("stderr")
        if isinstance(err, str) and err:
            stderr_lines.append(err)
        message = result.get("system_message")
        if isinstance(message, str) and message:
            system_messages.append(message)

    if extra_context_line:
        contexts.insert(0, extra_context_line)  # health line survives the clamp
    context_text = ""
    if contexts:
        context_text = budget.clamp(_CONTEXT_SEPARATOR.join(contexts), event)

    doc: dict = {}
    if decision_reason is not None:
        doc["decision"] = "block"
        doc["reason"] = decision_reason
    hook_output: dict = {}
    if permission is not None:
        hook_output["permissionDecision"] = permission[0]
        if permission[1]:
            hook_output["permissionDecisionReason"] = permission[1]

    plain_stdout = None
    if context_text:
        try:
            envelope = json.loads(signals.additional_context(event, context_text))
            hook_output.update(envelope["hookSpecificOutput"])
        except ValueError:
            if event == "UserPromptSubmit":
                bare = not doc and not hook_output and not continue_values \
                    and not system_messages
                if bare:
                    # v6-proven plain-stdout channel (signals module docstring).
                    plain_stdout = signals.user_prompt_context(context_text)
                else:
                    hook_output["additionalContext"] = context_text
            # else: no spike-proven context channel for this event — drop
            # silently (mem-035 discipline; ops for these events must not
            # rely on context delivery).

    if hook_output:
        hook_output.setdefault("hookEventName", event)
        doc["hookSpecificOutput"] = hook_output
    if continue_values and not all(continue_values):
        # false-wins (AND): continue:false is the only meaningful emission
        # (mem-051) — true is the harness default, so it is never emitted.
        doc["continue"] = False
    if system_messages:
        doc["systemMessage"] = "\n".join(system_messages)

    if plain_stdout is not None:
        stdout = plain_stdout
    elif doc:
        stdout = json.dumps(doc)
    elif ack:
        # TASK-61 parity: v6 side-effect hooks print a bare `{}` doc as a
        # pure acknowledgment. An op returning {"ack": True} reproduces it
        # when the merge is otherwise empty; real output keys subsume it.
        stdout = "{}"
    else:
        stdout = None
    return stdout, exit_code, stderr_lines


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def dispatch(event, payload, registry=None, now=None) -> DispatchResult:
    """Run every registered op for ``event`` and merge one output document.

    ``registry`` overrides registry.EVENT_OPS (testability with synthetic
    ops); ``now`` injects the clock — None (wall clock), a float (frozen),
    or a callable (advancing test clock). Never raises.
    """
    if not isinstance(payload, dict):
        payload = {}
    if not isinstance(event, str) or not event:
        return DispatchResult(None, 0, None)
    try:
        return _dispatch(event, payload, registry, now)
    except KeyboardInterrupt:
        raise
    except BaseException as exc:  # fail-open: dispatch-level crash never propagates
        _record_dispatch_failure(event, payload, exc, now)
        return DispatchResult(None, 0, _error_line(event, "dispatch", exc))


def _record_dispatch_failure(event, payload, exc, now) -> None:
    """Best-effort health record for a dispatch-level crash. Never raises."""
    try:
        agent_dir = hio.project_root(payload) / ".agent"
        if agent_dir.is_dir():
            _record_health(agent_dir, event, "dispatch", _describe_error(exc),
                           _make_clock(now)())
    except Exception:
        pass


def _handle_op_crash(runtime_state, agent_dir, event, op_name, error, ts,
                     error_lines) -> None:
    """Op-crash bookkeeping: op_errors note + sentinel line + health write."""
    text = _describe_error(error)
    _note_op_error(runtime_state, op_name, text, ts)
    error_lines.append(_error_line(event, op_name, error))
    _record_health(agent_dir, event, op_name, text, ts)


def _dispatch(event: str, payload: dict, registry, now) -> DispatchResult:
    clock = _make_clock(now)
    start = clock()
    root = hio.project_root(payload)
    agent_dir = root / ".agent"
    if not agent_dir.is_dir():
        return DispatchResult(None, 0, None)  # not a Navigator project

    table = registry if registry is not None else _default_registry()
    specs = table.get(event) or []
    if specs and all(config.mod_owns(str(getattr(s, "name", ""))) for s in specs):
        # v8 handoff (TASK-84): the loaded Navigator mod runs every op of this event.
        # Exit before config load, state lock and health so a Python spawn costs nothing.
        return DispatchResult(None, 0, None)

    cfg = config.load(root)  # ONCE per dispatch
    if not config.get(cfg, "dispatcher.enabled", True):
        return DispatchResult(None, 0, None)  # global kill switch
    pilot_executor = config.is_pilot_executor()  # ONCE per dispatch (plan §5)

    timeout = EVENT_TIMEOUTS.get(event, DEFAULT_TIMEOUT_SECONDS)
    deadline = start + timeout - DEADLINE_MARGIN_SECONDS
    session_id = payload.get("session_id")

    outcomes: list = []  # (registry_index, result_dict)
    error_lines: list = []

    with state.lock(agent_dir):
        runtime_state = state.load(agent_dir, session_id=session_id, now=clock())
        ctx = types.SimpleNamespace(
            event=event,
            payload=payload,
            config=cfg,
            state=runtime_state,
            pilot_executor=pilot_executor,
            now=start,
            session_id=session_id,
        )

        gate_blocked = False
        ordered = sorted(enumerate(specs), key=lambda item: _phase_rank(item[1]))
        for index, spec in ordered:
            is_gate = getattr(spec, "phase", None) == "gates"
            op_name = str(getattr(spec, "name", ""))
            if not _config_allows(cfg, spec):
                continue
            if config.mod_owns(op_name):  # the one v8 handoff point (TASK-84)
                continue
            if not _matcher_allows(spec, event, payload):
                continue
            if not is_gate:  # gates are exempt from both cuts
                if gate_blocked:
                    continue
                if clock() > deadline:
                    # Observability note, not a crash: no stderr, no health.
                    _note_op_error(runtime_state, op_name, "deadline-skipped",
                                   clock())
                    continue
            try:
                module = _import_op(op_name)
            except ModuleNotFoundError as exc:
                if exc.name in (OPS_PACKAGE, f"{OPS_PACKAGE}.{op_name}"):
                    # Normal until TASK-61 lands: note only, no sentinel/health.
                    _note_op_error(runtime_state, op_name, "op module not found",
                                   clock())
                    continue
                _handle_op_crash(runtime_state, agent_dir, event, op_name, exc,
                                 clock(), error_lines)
                continue
            except KeyboardInterrupt:
                raise
            except BaseException as exc:
                _handle_op_crash(runtime_state, agent_dir, event, op_name, exc,
                                 clock(), error_lines)
                continue
            try:
                result = module.run(ctx)
            except KeyboardInterrupt:
                raise
            except BaseException as exc:
                # BaseException on purpose: v6 hooks sys.exit() as control
                # flow — a SystemExit here is crash-class, its exit code is
                # recorded in the note but NEVER propagated (a bare
                # `except Exception` would let exit N reach the harness).
                _handle_op_crash(runtime_state, agent_dir, event, op_name, exc,
                                 clock(), error_lines)
                continue
            if result is None:
                continue
            if not isinstance(result, dict):
                error = TypeError(
                    "op returned " + type(result).__name__ + ", expected dict or None"
                )
                _handle_op_crash(runtime_state, agent_dir, event, op_name, error,
                                 clock(), error_lines)
                continue
            result = _log_reject(result, cfg, agent_dir, event, op_name, payload,
                                 session_id, pilot_executor, clock())
            if pilot_executor:
                result = _suppress_blocking(result)  # merge-level Pilot belt
            outcomes.append((index, result))
            if is_gate and _is_blocking(result):
                gate_blocked = True  # short-circuit all rightward phases

        health_line = _surface_health(agent_dir) if event == "SessionStart" else None
        stdout, exit_code, op_stderr = _merge_outputs(event, outcomes, health_line)
        state.save(agent_dir, runtime_state, session_id=session_id, now=clock())

    stderr_lines = op_stderr + error_lines
    stderr = "\n".join(stderr_lines) if stderr_lines else None
    return DispatchResult(stdout, exit_code, stderr)
