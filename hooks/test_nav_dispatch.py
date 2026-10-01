#!/usr/bin/env python3
"""Subprocess contract harness for hooks/nav_dispatch.py (TASK-60 Phase 5).

Template: hooks/test_workflow_enforcer.py (TASK-45 precedent) — each test
builds a throwaway project dir and drives the dispatcher as a subprocess
(`python3 hooks/nav_dispatch.py <event>`) with a JSON payload on stdin,
asserting on stdout/exit code only. stdlib unittest (pytest not installed).

Mandatory cases from the TASK-60 acceptance list covered here:

  - Pristine v6.18.1 config fixture -> exit 0 on every v6 event surface,
    with at most ONE JSON document on stdout.
  - Project with NO .agent/ -> exit 0 AND empty stdout on every event, and
    the dispatcher never CREATES .agent/ (silent degradation).
  - PILOT_EXECUTOR=1 -> no blocking output on any event. NOTE: TASK-61 ops
    do not exist yet, so this is the dispatch-level synthetic check (clean
    exit, no block/deny/continue:false emissions); op-level bypass cases
    (e.g. read_guard deny suppressed under Pilot) land with the TASK-61
    ports that plug into this harness.
  - Per-behavior off-switch: a config with every v6 toggle block disabled
    (read_guard_hook.enabled=false etc.) -> exit 0 everywhere, and the
    config gate skips ops BEFORE import (no missing-module op_errors notes
    for gated-off ops).
  - Malformed stdin fails open (exit 0); missing/unknown event arg -> exit
    0, no output.
  - Crash-injection: NOT feasible at the subprocess level right now — the
    real op modules land in TASK-61, so there is nothing on the live
    registry to crash. Instead a tmp-dir driver script imports
    nav_hook_lib.runtime directly and dispatches a SYNTHETIC registry
    (contract: the `registry` param overrides EVENT_OPS for testability)
    with fake op modules: crash isolation, sentinel stderr hygiene
    (mem-034: no payload echo), meta.op_errors, health-file write +
    SessionStart surfacing, and gate short-circuit of rightward phases.
  - Timing: UserPromptSubmit dispatched 20x against
    nav_hook_lib/fixtures/timing_prompt.json; p95 <= 200ms * NAV_TIMING_MULT
    (env, default 1 — set >1 on slow CI runners).

Out of scope here (other TASK-60 groups): mem-036 three-env-variant manifest
command tests (need .claude-plugin/plugin.json — integrator), state
read-once/write-once unit verification (runtime builder's colocated tests).
"""

import json
import math
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
HOOK = str(HOOKS_DIR / "nav_dispatch.py")
FIXTURES = HOOKS_DIR / "nav_hook_lib" / "fixtures"
PRISTINE_CONFIG = (FIXTURES / "nav-config-v6.18.1.json").read_text()
TIMING_FIXTURE = FIXTURES / "timing_prompt.json"

# The seven v6 manifest event surfaces (registry.EVENT_OPS keys — TASK-60
# registers ONLY these; new routing-matrix events belong to TASK-62).
EVENTS = (
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "PreCompact",
    "PostCompact",
)

# Realistic per-event payload shapes (tool_name chosen to HIT the coarse
# registry matchers: 'Read' and 'Edit|Write|MultiEdit|NotebookEdit').
EVENT_PAYLOAD_EXTRAS = {
    "SessionStart": {"source": "startup"},
    "UserPromptSubmit": {"prompt": "hello there"},
    "PreToolUse": {"tool_name": "Read", "tool_input": {"file_path": "/tmp/x.md"}},
    "PostToolUse": {
        "tool_name": "Edit",
        "tool_input": {"file_path": "/tmp/x.py"},
        "tool_response": {},
    },
    "Stop": {"stop_hook_active": False},
    "PreCompact": {"trigger": "manual"},
    "PostCompact": {},
}

# v6 toggle block names (from fixtures/nav-config-v6.18.1.json) -> the op
# names the registry gates on them. Used by the off-switch tests.
TOGGLE_BLOCKS = (
    "session_start_hook",
    "workflow_enforcer_hook",
    "brief_hook",
    "read_guard_hook",
    "task_graph_sync_hook",
    "profile_sync_hook",
    "workflow_state_hook",
    "compact_hook",
)
GATED_OPS = (
    "session_start",
    "prompt_gate",
    "prompt_brief",
    "read_guard",
    "graph_sync",
    "profile_sync",
    "stop_state",
    "compact_marker",
)
ALL_TOGGLES_OFF = json.dumps({block: {"enabled": False} for block in TOGGLE_BLOCKS})


_ISOLATED_CONFIG_HOME = tempfile.TemporaryDirectory()


def clean_env(extra=None):
    """Subprocess env with the escape hatches / project redirects removed.

    CLAUDE_PROJECT_DIR must go: with malformed stdin the payload is {}, and
    an inherited value would redirect hio.resolve_cwd() at the REAL repo.
    """
    env = os.environ.copy()
    for var in ("PILOT_EXECUTOR", "CLAUDE_PROJECT_DIR", "CLAUDE_USER_MESSAGE"):
        env.pop(var, None)
    # TASK-82: per-person settings (ADHD switch) live outside the repo; point
    # them at an empty dir so the developer's own switch never shapes a test.
    env["NAVIGATOR_CONFIG_HOME"] = _ISOLATED_CONFIG_HOME.name
    if extra:
        env.update(extra)
    return env


def run_dispatch(project_dir, event=None, payload=None, raw_stdin=None, env_extra=None):
    """Invoke `python3 nav_dispatch.py [<event>]` rooted at project_dir.

    payload: sent as JSON on stdin ({} when None).
    raw_stdin: sent verbatim (overrides payload) — malformed-input cases.
    event: omitted from argv entirely when None (missing-arg case).
    """
    argv = [sys.executable, HOOK]
    if event is not None:
        argv.append(event)
    if raw_stdin is None:
        raw_stdin = json.dumps(payload if payload is not None else {})
    return subprocess.run(
        argv,
        input=raw_stdin,
        capture_output=True,
        text=True,
        cwd=project_dir,
        env=clean_env(env_extra),
    )


def event_payload(project, event, session_id="s1"):
    payload = {"cwd": project, "session_id": session_id}
    payload.update(EVENT_PAYLOAD_EXTRAS.get(event, {}))
    return payload


def parse_single_doc(testcase, stdout):
    """Contract: EXACTLY ONE JSON doc on stdout, or nothing. Returns doc/None.

    json.loads rejects concatenated documents, so a second doc fails here.
    """
    if not stdout.strip():
        return None
    try:
        doc = json.loads(stdout)
    except json.JSONDecodeError:
        testcase.fail(f"stdout is not a single JSON document: {stdout!r}")
    testcase.assertIsInstance(doc, dict, f"stdout doc is not an object: {stdout!r}")
    return doc


def assert_not_blocking(testcase, result, event):
    """No blocking emission: exit 0, no block/deny/ask/continue:false."""
    testcase.assertEqual(result.returncode, 0, f"{event}: {result.stderr}")
    doc = parse_single_doc(testcase, result.stdout)
    if doc is None:
        return
    testcase.assertNotEqual(doc.get("decision"), "block", f"{event}: {doc}")
    testcase.assertIsNot(doc.get("continue"), False, f"{event}: {doc}")
    hso = doc.get("hookSpecificOutput") or {}
    perm = hso.get("permissionDecision") or doc.get("permissionDecision")
    testcase.assertNotIn(perm, ("deny", "ask"), f"{event}: {doc}")


class _ProjectCase(unittest.TestCase):
    """Throwaway project per test (TASK-45 template shape)."""

    with_agent = True
    config_body = None  # written to .agent/.nav-config.json when set

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        # realpath so macOS /var -> /private/var resolution stays consistent
        # (mem-055: hook payload cwd arrives realpath'd).
        self.project = os.path.realpath(self._tmp.name)
        self.agent = Path(self.project) / ".agent"
        if self.with_agent:
            self.agent.mkdir(parents=True)
            if self.config_body is not None:
                (self.agent / ".nav-config.json").write_text(self.config_body)

    def tearDown(self):
        self._tmp.cleanup()

    def state_op_errors(self):
        """meta.op_errors from the runtime state file, JSON-serialized ('' if absent)."""
        state_path = self.agent / ".nav-runtime-state.json"
        if not state_path.exists():
            return None
        doc = json.loads(state_path.read_text())
        return json.dumps(doc.get("meta", {}).get("op_errors", []))


class PristineConfigTest(_ProjectCase):
    """Acceptance: pristine v6.18.1 config (no v7 blocks) -> exit 0 everywhere."""

    config_body = PRISTINE_CONFIG

    def test_every_event_exits_zero_with_single_doc(self):
        for event in EVENTS:
            with self.subTest(event=event):
                result = run_dispatch(self.project, event, event_payload(self.project, event))
                self.assertEqual(result.returncode, 0, f"{event}: {result.stderr}")
                parse_single_doc(self, result.stdout)


class NoAgentDirTest(_ProjectCase):
    """Acceptance: no .agent/ -> exit 0 AND empty stdout; never creates .agent/."""

    with_agent = False

    def test_every_event_degrades_silently(self):
        for event in EVENTS:
            with self.subTest(event=event):
                result = run_dispatch(self.project, event, event_payload(self.project, event))
                self.assertEqual(result.returncode, 0, f"{event}: {result.stderr}")
                self.assertEqual(result.stdout, "", f"{event} emitted output: {result.stdout!r}")
        self.assertFalse(
            self.agent.exists(),
            "dispatcher created .agent/ in a non-Navigator project (must degrade silently)",
        )


class PilotExecutorTest(_ProjectCase):
    """Acceptance: PILOT_EXECUTOR=1 -> no blocking output on any event.

    Synthetic-level check only: with TASK-61 ops absent this proves the
    dispatch pipeline itself never blocks under Pilot (pilot_executor is
    evaluated ONCE at entry per contract). Op-level bypass assertions (a
    would-block gate suppressed under Pilot) land with the TASK-61 op ports.
    """

    config_body = PRISTINE_CONFIG

    def test_no_blocking_output_on_any_event(self):
        for event in EVENTS:
            with self.subTest(event=event):
                result = run_dispatch(
                    self.project,
                    event,
                    event_payload(self.project, event),
                    env_extra={"PILOT_EXECUTOR": "1"},
                )
                assert_not_blocking(self, result, event)


class OffSwitchTest(_ProjectCase):
    """Acceptance: each v6 per-behavior toggle block honored (enabled=false).

    All eight toggle blocks off -> exit 0 everywhere AND no missing-module
    op_errors notes for the gated ops: the config gate must skip an op
    silently BEFORE its (currently nonexistent) module import is attempted.
    """

    config_body = ALL_TOGGLES_OFF

    def test_disabled_toggles_exit_zero_and_skip_before_import(self):
        for event in EVENTS:
            with self.subTest(event=event):
                result = run_dispatch(self.project, event, event_payload(self.project, event))
                assert_not_blocking(self, result, event)
        errs = self.state_op_errors()
        if errs is not None:  # existence itself is asserted in MissingOpModuleTest
            for op in GATED_OPS:
                self.assertNotIn(
                    op, errs, f"config-gated-off op {op} was still attempted: {errs}"
                )


class OpModuleImportTest(_ProjectCase):
    """Contract: registry op modules import and run cleanly (post-TASK-61).

    Differential partner of OffSwitchTest: with the pristine (all-enabled)
    config, the UserPromptSubmit ops ARE attempted. Pre-TASK-61 this class
    asserted "op module not found" notes (the sanctioned missing state);
    the ports landed, so the differential flips: the modules must import
    and leave NO missing-module or crash notes, while still exiting 0 and
    persisting state via the single atomic save. The missing-module
    contract itself stays covered in-process by nav_hook_lib/test_runtime
    (test_missing_op_module_notes_without_sentinel_or_health).
    """

    config_body = PRISTINE_CONFIG

    def test_registry_ops_import_and_run_without_error_notes(self):
        result = run_dispatch(
            self.project, "UserPromptSubmit", event_payload(self.project, "UserPromptSubmit")
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        errs = self.state_op_errors()
        self.assertIsNotNone(errs, "runtime state file not persisted after dispatch")
        self.assertNotIn("op module not found", errs,
                         f"a registry op module is missing post-TASK-61: {errs}")
        for op in ("prompt_gate", "prompt_brief"):
            self.assertNotIn(op, errs, f"op {op} left an error note: {errs}")


class MalformedInputTest(_ProjectCase):
    """Acceptance: malformed stdin / bad argv fail open (exit 0)."""

    def test_garbage_stdin_every_event(self):
        for event in EVENTS:
            with self.subTest(event=event):
                result = run_dispatch(self.project, event, raw_stdin="garbage {not json")
                self.assertEqual(result.returncode, 0, f"{event}: {result.stderr}")
                parse_single_doc(self, result.stdout)

    def test_empty_stdin(self):
        result = run_dispatch(self.project, "UserPromptSubmit", raw_stdin="")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_event_arg(self):
        result = run_dispatch(self.project, event=None)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "", f"missing-arg output: {result.stdout!r}")

    def test_unknown_event(self):
        result = run_dispatch(self.project, "NoSuchEventEver")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "", f"unknown-event output: {result.stdout!r}")


# --------------------------------------------------------------------------
# Crash injection — synthetic registry via an in-process driver script.
#
# WHY NOT A SUBPROCESS DISPATCH: nav_dispatch.py runs the LIVE registry, and
# the live op modules only land in TASK-61 — there is no real op to crash
# from the outside, and the shim's whole-body try/except would mask any
# injected failure anyway. The dispatch contract provides the seam instead:
# dispatch(..., registry=...) overrides EVENT_OPS. The driver below runs in
# its own interpreter (subprocess isolation for sys.path/sys.modules games)
# but calls runtime.dispatch directly with fake op modules.
#
# Module resolution assumption: ops resolve as importable modules named
# `ops.<name>` with hooks/ on sys.path (the shim bootstraps its own dir onto
# sys.path; ops live at hooks/ops/<name>.py). The driver puts a synthetic
# ops/ package first on sys.path AND aliases the modules into sys.modules
# under `hooks.ops.<name>` / `nav_hook_lib.ops.<name>` so any
# importlib.import_module-based resolution finds them.
# --------------------------------------------------------------------------

_OPS_FILES = {
    "__init__.py": "",
    "crashy.py": ("def run(ctx):\n    raise RuntimeError('synthetic crash for isolation test')\n"),
    "sibling.py": ("def run(ctx):\n    return {'additional_context': 'SIBLING-RAN-e7f2'}\n"),
    "gate_block.py": (
        "def run(ctx):\n    return {'decision': 'block', 'reason': 'synthetic gate block'}\n"
    ),
    "flag_writer.py": (
        "from pathlib import Path\n"
        "def run(ctx):\n"
        "    Path(r'@FLAG@').write_text('ran')\n"
        "    return {'additional_context': 'SHOULD-NOT-APPEAR-9d3b'}\n"
    ),
}

_DRIVER = '''\
"""TASK-60 synthetic-registry driver: crash isolation, health, gate cut."""
import json
import sys
from pathlib import Path

TMP = r"@TMP@"
HOOKS = r"@HOOKS@"
PROJECT = r"@PROJECT@"
FLAG = Path(r"@FLAG@")

sys.path.insert(0, HOOKS)
sys.path.insert(0, TMP)

from nav_hook_lib import runtime
from nav_hook_lib.registry import OpSpec

import ops.crashy, ops.sibling, ops.gate_block, ops.flag_writer  # noqa: E401
for _name in ("crashy", "sibling", "gate_block", "flag_writer"):
    _mod = sys.modules["ops." + _name]
    sys.modules.setdefault("hooks.ops." + _name, _mod)
    sys.modules.setdefault("nav_hook_lib.ops." + _name, _mod)


def spec(name, phase):
    return OpSpec(name=name, phase=phase, matcher=None, config_key=None, budget_ms=50)


STATE = Path(PROJECT) / ".agent" / ".nav-runtime-state.json"
HEALTH = Path(PROJECT) / ".agent" / ".nav-dispatch-health.json"

# Case A -- per-op isolation: crashing injector; sibling injector still runs;
# ONE sentinel stderr line, payload text never echoed (mem-034); crash entry
# in meta.op_errors; health file written with surfaced:false.
reg = {"UserPromptSubmit": [spec("crashy", "injectors"), spec("sibling", "injectors")]}
payload = {"prompt": "SECRET-PROMPT-c4a1 please fix", "cwd": PROJECT, "session_id": "t"}
res = runtime.dispatch("UserPromptSubmit", payload, registry=reg)
assert res.exit_code == 0, ("A: exit_code", res)
assert res.stdout and "SIBLING-RAN-e7f2" in res.stdout, ("A: sibling did not run", res)
assert res.stderr and "nav-dispatch-error" in res.stderr, ("A: sentinel stderr missing", res)
assert "SECRET-PROMPT-c4a1" not in (res.stderr or ""), ("A: payload echoed to stderr", res)
errs = json.dumps(json.loads(STATE.read_text()).get("meta", {}).get("op_errors", []))
assert "crashy" in errs, ("A: meta.op_errors missing crash entry", errs)
health = json.loads(HEALTH.read_text())
assert health.get("surfaced") is False, ("A: health surfaced flag", health)
assert health.get("last_error", {}).get("op") == "crashy", ("A: health last_error.op", health)

# Case B -- a gate block SHORT-CIRCUITS all rightward phases: the recorder
# never runs (no flag file, no leaked context); block doc wins stdout.
reg = {"UserPromptSubmit": [spec("gate_block", "gates"), spec("flag_writer", "recorders")]}
res = runtime.dispatch(
    "UserPromptSubmit", {"prompt": "x", "cwd": PROJECT, "session_id": "t"}, registry=reg
)
doc = json.loads(res.stdout)
assert doc.get("decision") == "block", ("B: decision", doc)
assert "synthetic gate block" in str(doc.get("reason", "")), ("B: reason", doc)
assert not FLAG.exists(), "B: recorder ran after a gate block"
assert "SHOULD-NOT-APPEAR-9d3b" not in (res.stdout or ""), ("B: recorder output leaked", res)
assert res.exit_code == 0, ("B: exit_code", res)

# Case C -- the next SessionStart dispatch surfaces the case-A health error
# once (additional_context line) and flips surfaced to true.
res = runtime.dispatch(
    "SessionStart",
    {"cwd": PROJECT, "session_id": "t", "source": "startup"},
    registry={"SessionStart": []},
)
assert res.stdout and "last dispatch error" in res.stdout, ("C: surface line missing", res)
health = json.loads(HEALTH.read_text())
assert health.get("surfaced") is True, ("C: surfaced not flipped", health)

print("DRIVER-OK")
'''


class CrashInjectionTest(unittest.TestCase):
    """Synthetic-registry contract cases (see block comment above for why
    this is an in-process driver rather than a subprocess dispatch)."""

    def test_synthetic_registry_driver(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = os.path.realpath(tmp)
            project = Path(tmp) / "project"
            (project / ".agent").mkdir(parents=True)
            ops_dir = Path(tmp) / "ops"
            ops_dir.mkdir()
            flag = str(Path(tmp) / "recorder-ran.flag")
            for name, body in _OPS_FILES.items():
                (ops_dir / name).write_text(body.replace("@FLAG@", flag))
            script = (
                _DRIVER.replace("@TMP@", tmp)
                .replace("@HOOKS@", str(HOOKS_DIR))
                .replace("@PROJECT@", str(project))
                .replace("@FLAG@", flag)
            )
            driver = Path(tmp) / "driver.py"
            driver.write_text(script)
            result = subprocess.run(
                [sys.executable, str(driver)],
                capture_output=True,
                text=True,
                cwd=tmp,
                env=clean_env(),
            )
            self.assertEqual(
                result.returncode,
                0,
                f"driver failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            self.assertIn("DRIVER-OK", result.stdout)


class TimingTest(_ProjectCase):
    """Acceptance: UserPromptSubmit dispatch <=200ms p95 (lazy op imports).

    20 measured subprocess runs against fixtures/timing_prompt.json (its
    placeholder cwd swapped for this test's project). One unmeasured warmup
    run absorbs first-run bytecode compilation. NAV_TIMING_MULT (default 1)
    relaxes the limit on slow CI runners without weakening the local gate.
    """

    config_body = PRISTINE_CONFIG
    RUNS = 20
    LIMIT_SECONDS = 0.200

    def test_user_prompt_submit_p95_under_200ms(self):
        payload = json.loads(TIMING_FIXTURE.read_text())
        payload["cwd"] = self.project  # fixture ships "." as a placeholder
        raw = json.dumps(payload)
        argv = [sys.executable, HOOK, "UserPromptSubmit"]
        env = clean_env()

        def run_once():
            return subprocess.run(
                argv, input=raw, capture_output=True, text=True, cwd=self.project, env=env
            )

        warmup = run_once()
        self.assertEqual(warmup.returncode, 0, warmup.stderr)

        samples = []
        for _ in range(self.RUNS):
            started = time.perf_counter()
            result = run_once()
            samples.append(time.perf_counter() - started)
            self.assertEqual(result.returncode, 0, result.stderr)

        samples.sort()
        p95 = samples[max(0, math.ceil(0.95 * len(samples)) - 1)]
        try:
            mult = float(os.environ.get("NAV_TIMING_MULT", "1") or "1")
        except ValueError:
            mult = 1.0
        limit = self.LIMIT_SECONDS * mult
        self.assertLessEqual(
            p95,
            limit,
            f"UserPromptSubmit p95 {p95 * 1000:.0f}ms > {limit * 1000:.0f}ms "
            f"(NAV_TIMING_MULT={mult}, samples ms: "
            f"{[int(s * 1000) for s in samples]})",
        )


if __name__ == "__main__":
    unittest.main()
