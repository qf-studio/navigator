#!/usr/bin/env python3
"""Navigator RuntimeState schema v2 (TASK-59 Phase 2).

Single state file `.agent/.nav-runtime-state.json` replacing v6's scattered
per-hook files. Section mapping (every v6 state file is representable):

    v6 artifact                       -> v2 section
    .nav-workflow-state.json          -> turn   (signals.check_shown TRISTATE,
                                                 signals.nav_status_shown,
                                                 signals.loop_phase,
                                                 tools_used, assistant_text_chars)
    .nav-read-counter.json            -> reads  (count / turn_count)
    .nav-profile-sync-state.json      -> profile (last_synced_count)
    nav_brief.py (stateless in v6)    -> brief  (v7 pending-brief state)
    session identity                  -> session {id, ...}
    loop / stop-completion bookkeeping -> completion
    jit_memory injection dedupe       -> jit
    Tier-1 telemetry (hits/false pos) -> tier1  (TASK-62; cumulative, so it
                                                 survives session boundaries
                                                 like profile — /nav:stats
                                                 surfaces the counters)
    pre/post-compact marker handoff   -> compact
    bookkeeping                       -> meta {schema, writer, op_errors,
                                               updated, sections}

Guarantees:
  - Schema gate: only documents with ``meta.schema == 2`` are read.
    Schema-less files (v6 leftovers such as a stray .nav-workflow-state.json
    body) and any other schema version are ignored entirely by ``load()``.
  - Per-section TTLs (``SECTION_TTLS_SECONDS`` — module-level so ops can
    tune) expire independently. Timestamps live in ``meta.sections`` and are
    refreshed by ``save()`` only when a section's content actually changed;
    an untouched section keeps aging even if the file is rewritten every
    turn. ``load()`` prunes the timestamp of a dropped section, so re-writing
    identical content after expiry restarts that section's clock.
  - Session scoping is FAIL-CLOSED: ``load(session_id=X)`` drops
    ``SESSION_SCOPED_SECTIONS`` when the stored ``session.id`` is absent OR
    differs from X — an unstamped file must not leak another session's turn
    state. ``save(session_id=X)`` stamps ``session.id`` so the next scoped
    load succeeds. ``profile`` and ``compact`` survive session boundaries:
    profile.last_synced_count must not reset (a reset would re-sync old
    corrections as duplicates) and compact markers must survive the session
    boundary a compact can create.
  - Concurrency: ``lock(agent_dir)`` is the read-modify-write guard between
    concurrent hook processes (flock on ``.agent/.nav-runtime-state.lock``).
    The TASK-60 dispatcher MUST hold ``state.lock()`` across its whole
    load -> ops -> save span; individual ``load()``/``save()`` calls do NOT
    self-lock (one lock per dispatch, no nesting). On lock timeout (~2s) the
    context manager proceeds WITHOUT the lock — fail-open, a hook is never
    bricked by a stuck peer. On platforms without fcntl (Windows) it degrades
    to a no-op.
  - Tristate fidelity (mem-037): section content is passed through verbatim —
    ``turn.signals.check_shown`` True/False/None is never coerced on read or
    write, in JSON (true/false/null) or in Python.
  - Atomic writes via ``hio.atomic_write_json`` (tmp + os.replace).

Missing section timestamps are treated as fresh, never expired — same
discipline as v6 nav_read_guard's unparseable-timestamp handling.
"""
from __future__ import annotations

import contextlib
import time
from datetime import datetime, timezone
from pathlib import Path

try:  # POSIX stdlib; absent on Windows — lock() degrades to a no-op there
    import fcntl
except ImportError:
    fcntl = None

try:  # package context (v7 ops import nav_hook_lib.state)
    from . import hio
except ImportError:  # bare sibling context (unittest discover from the lib dir)
    import hio


SCHEMA_VERSION = 2

# Project-root-relative location of the runtime state file. load()/save()
# take the .agent directory itself, so they join only the file name.
STATE_PATH = ".agent/.nav-runtime-state.json"
_STATE_FILE_NAME = ".nav-runtime-state.json"

# Cross-process mutex for the read-modify-write span (see lock()).
LOCK_PATH = ".agent/.nav-runtime-state.lock"
_LOCK_FILE_NAME = ".nav-runtime-state.lock"
LOCK_TIMEOUT_SECONDS = 2.0
_LOCK_RETRY_INTERVAL = 0.05

KNOWN_SECTIONS = (
    "session",
    "turn",
    "reads",
    "completion",
    "brief",
    "jit",
    "tier1",
    "profile",
    "compact",
    "judge",
)

_HOUR = 3600.0
_DAY = 24 * _HOUR

# Staleness windows per section, in seconds. Module-level so ops can tune.
# turn/reads are per-turn state (short TTL); session/jit are per-session;
# profile/compact persist across sessions.
SECTION_TTLS_SECONDS = {
    "session": 1 * _DAY,
    "turn": 2 * _HOUR,
    "reads": 2 * _HOUR,
    "completion": 2 * _HOUR,
    "brief": 2 * _HOUR,
    "jit": 1 * _DAY,
    "tier1": 30 * _DAY,
    "profile": 30 * _DAY,
    "compact": 30 * _DAY,
    "judge": 30 * _DAY,  # cumulative override telemetry (TASK-80 B), like tier1
}

# Sections dropped on load when the stored session.id differs from the
# session_id passed by the caller. profile/compact/tier1 deliberately
# excluded — see module docstring (tier1 carries cumulative telemetry).
SESSION_SCOPED_SECTIONS = frozenset(
    {"session", "turn", "reads", "completion", "brief", "jit"}
)

# meta.op_errors is bounded so a chronically failing op cannot grow the
# state file without limit; save() keeps the most recent entries.
MAX_OP_ERRORS = 20


def _state_file(agent_dir) -> Path:
    return Path(agent_dir) / _STATE_FILE_NAME


@contextlib.contextmanager
def lock(agent_dir):
    """Exclusive cross-process lock over the runtime state read-modify-write.

    flock (LOCK_EX) on ``.agent/.nav-runtime-state.lock``, acquired via a
    LOCK_NB retry loop bounded by ``LOCK_TIMEOUT_SECONDS`` (~2s). On timeout
    the body runs WITHOUT the lock — fail-open by contract: a hook must never
    hang or crash because a peer process wedged with the lock held.

    Discipline (TASK-60): the dispatcher MUST hold state.lock() across its
    entire load -> ops -> save span. load()/save() do NOT self-lock —
    exactly one lock per dispatch, never nested (flock does not count
    recursively across file objects; nesting would self-deadlock until the
    timeout fires).

    Degrades to a no-op when fcntl is unavailable (Windows) or the lockfile
    cannot be opened.
    """
    if fcntl is None:
        yield
        return
    handle = None
    try:
        lock_path = Path(agent_dir) / _LOCK_FILE_NAME
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(lock_path, "a")
    except Exception:
        yield  # fail-open: no lockfile, proceed unguarded
        return
    acquired = False
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
            break
        except OSError:
            if time.monotonic() >= deadline:
                break  # fail-open: proceed without the lock
            time.sleep(_LOCK_RETRY_INTERVAL)
    try:
        yield
    finally:
        try:
            if acquired:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            handle.close()
        except Exception:
            pass


def _now_ts(now) -> float:
    return time.time() if now is None else float(now)


def _read_v2(path: Path) -> dict | None:
    """Raw v2 document from disk, or None.

    None covers: missing file, corrupt JSON, non-object top level, and any
    document whose meta.schema is not exactly SCHEMA_VERSION — including
    schema-less v6 leftovers (their `schema` key is top-level, not in meta)
    and v1 documents. Readers ignore those entirely.
    """
    data = hio.safe_json(path)
    if not isinstance(data, dict):
        return None
    meta = data.get("meta")
    if not isinstance(meta, dict) or meta.get("schema") != SCHEMA_VERSION:
        return None
    return data


def _ensure_meta_fields(meta: dict) -> dict:
    meta.setdefault("writer", "")
    if not isinstance(meta.get("op_errors"), list):
        meta["op_errors"] = []
    return meta


def load(agent_dir, session_id=None, now=None) -> dict:
    """Load runtime state; expired or session-mismatched sections are absent.

    agent_dir: the .agent directory (str or Path).
    session_id: when given, session scoping is FAIL-CLOSED — every section in
        SESSION_SCOPED_SECTIONS comes back absent unless the stored
        session.id is present AND equal to session_id. A file that never got
        stamped (absent session.id) is treated as another session's state,
        not passed through.
    now: injectable epoch seconds (float) for TTL math; defaults to
        time.time().

    Always returns a dict with a `meta` section carrying schema, writer,
    op_errors, and the per-section timestamp map (`sections`) for the
    sections that survived.
    """
    data = _read_v2(_state_file(agent_dir))
    if data is None:
        return {
            "meta": _ensure_meta_fields({"schema": SCHEMA_VERSION, "sections": {}}),
        }

    now_ts = _now_ts(now)
    meta_in = data["meta"]
    ts_map = meta_in.get("sections")
    if not isinstance(ts_map, dict):
        ts_map = {}

    stored = data.get("session")
    stored_session = stored.get("id") if isinstance(stored, dict) else None
    # Fail-closed: an absent stored id is a mismatch, same as a differing one.
    mismatch = bool(session_id) and stored_session != session_id

    out: dict = {}
    surviving_ts: dict = {}
    for name, content in data.items():
        if name == "meta":
            continue
        if not isinstance(content, dict):
            continue  # sections are JSON objects; drop anything else defensively
        if mismatch and name in SESSION_SCOPED_SECTIONS:
            continue
        ts = ts_map.get(name)
        ttl = SECTION_TTLS_SECONDS.get(name)
        has_ts = isinstance(ts, (int, float)) and not isinstance(ts, bool)
        if has_ts and ttl is not None and (now_ts - float(ts)) > ttl:
            continue
        out[name] = content
        if has_ts:
            surviving_ts[name] = float(ts)

    meta_out = dict(meta_in)
    meta_out["schema"] = SCHEMA_VERSION
    meta_out["sections"] = surviving_ts
    out["meta"] = _ensure_meta_fields(meta_out)
    return out


def save(agent_dir, state, session_id=None, now=None) -> bool:
    """Atomically persist `state` to the runtime state file.

    Stamps meta in place on the passed dict: meta.schema = 2, meta.updated
    (ISO 8601 UTC), meta.sections (per-section TTL timestamps), and defaults
    for meta.writer / meta.op_errors when the caller did not set them.

    session_id: when provided, stamps ``state['session']['id'] = session_id``
    before writing (creating the section if needed) so a subsequent
    ``load(session_id=...)`` passes the fail-closed scoping gate.

    A section's timestamp is refreshed only when its content differs from
    what is on disk; unchanged sections keep their carried timestamp so TTLs
    make progress across frequent saves. Sections whose timestamp was pruned
    by load() (expired / mismatched) are stamped fresh even when the written
    content matches the stale bytes on disk.

    Returns hio.atomic_write_json's result (False on any write failure).
    now: injectable epoch seconds (float) for tests; defaults to time.time().
    """
    if not isinstance(state, dict):
        return False

    if session_id:
        session = state.get("session")
        if not isinstance(session, dict):
            session = {}
            state["session"] = session
        session["id"] = session_id

    path = _state_file(agent_dir)
    now_ts = _now_ts(now)
    prev = _read_v2(path) or {}

    meta = state.get("meta")
    if not isinstance(meta, dict):
        meta = {}
        state["meta"] = meta

    carried_ts = meta.get("sections")
    if not isinstance(carried_ts, dict):
        carried_ts = {}

    new_ts: dict = {}
    for name, content in state.items():
        if name == "meta":
            continue
        carried = carried_ts.get(name)
        has_carried = isinstance(carried, (int, float)) and not isinstance(carried, bool)
        if has_carried and prev.get(name) == content:
            new_ts[name] = float(carried)
        else:
            new_ts[name] = now_ts

    meta["schema"] = SCHEMA_VERSION
    meta["updated"] = datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()
    meta["sections"] = new_ts
    _ensure_meta_fields(meta)
    meta["op_errors"] = meta["op_errors"][-MAX_OP_ERRORS:]

    return bool(hio.atomic_write_json(path, state))
