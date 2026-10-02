#!/usr/bin/env python3
"""Tests for nav_hook_lib/runtime.py (TASK-60 dispatch pipeline).

stdlib unittest only, in-process. Synthetic op modules are injected into
sys.modules under "ops.<name>" (importlib.import_module returns the
sys.modules entry directly) and paired with SimpleNamespace OpSpecs passed
via the ``registry`` override, so no hooks/ops/ package is required on disk.

Contract under test (TASK-60 dispatch contract):
  - phase ordering gates -> responders -> injectors -> recorders (stable
    registry order within a phase);
  - a gate block/deny/nonzero-exit short-circuits rightward phases while
    sibling gates still run;
  - merge rules: budgeted context concat in registry order, first
    decision:'block' wins, deny beats ask, exit_code max, `continue` is
    false-wins (emitted as false only when an op set continue_ False; true
    is the harness default and is never emitted), stderr lines joined, one
    output doc;
  - per-op crash isolation: op_errors note + ONE sentinel line (exception
    class only, never payload text) + health write, siblings still run;
    catches BaseException — SystemExit is crash-class (exit code recorded,
    never propagated), KeyboardInterrupt re-raised;
  - class-only redaction: exception MESSAGES never persist to op_errors,
    the health file, or the SessionStart surfacing line;
  - soft deadline drops non-gates, never gates; each deadline-skipped op
    leaves an op_errors "deadline-skipped" note (no sentinel, no health);
  - pilot merge belt: pilot_executor strips blocking keys from every op
    result before merging (non-blocking output flows normally);
  - health surfacing line is prepended before op contexts pre-clamp, so a
    full SessionStart budget cannot eat it;
  - state loaded once / saved once inside state.lock();
  - pilot_executor evaluated once and visible to every op;
  - health file round-trip surfaces at the next SessionStart exactly once;
  - missing op module -> op_errors note only (no sentinel, no health);
  - matcher and config_key filtering; no-.agent silent degrade.
"""

import contextlib
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import budget
import config
import runtime
import state

SESSION_ID = "sess-runtime-tests"


class RuntimeTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.agent_dir = self.root / ".agent"
        self.agent_dir.mkdir()
        self._fake_modules = []
        # Isolate from the surrounding environment/repo: fallback cwd and
        # env-derived roots must never point at the real project .agent/.
        self._saved_env = {
            key: os.environ.pop(key, None)
            for key in ("PILOT_EXECUTOR", "CLAUDE_PROJECT_DIR", "NAVIGATOR_MOD_OWNS")
        }
        self._saved_cwd = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(self._restore_environment)

    def _restore_environment(self):
        os.chdir(self._saved_cwd)
        for key, value in self._saved_env.items():
            if value is not None:
                os.environ[key] = value
        for name in self._fake_modules:
            sys.modules.pop(name, None)

    # -- helpers ----------------------------------------------------------

    def payload(self, **extra):
        data = {"cwd": str(self.root), "session_id": SESSION_ID}
        data.update(extra)
        return data

    def register_op(self, name, run):
        module = types.ModuleType(f"ops.{name}")
        module.run = run
        sys.modules[f"ops.{name}"] = module
        self._fake_modules.append(f"ops.{name}")
        return module

    def spec(self, name, phase="injectors", matcher=None, config_key=None,
             budget_ms=None):
        return types.SimpleNamespace(name=name, phase=phase, matcher=matcher,
                                     config_key=config_key, budget_ms=budget_ms)

    def make_op(self, name, phase="injectors", result=None, calls=None,
                matcher=None, config_key=None, run=None):
        """Register a fake op and return its OpSpec."""
        def default_run(ctx):
            if calls is not None:
                calls.append(name)
            return result

        self.register_op(name, run or default_run)
        return self.spec(name, phase=phase, matcher=matcher, config_key=config_key)

    def write_config(self, cfg_dict):
        path = self.agent_dir / ".nav-config.json"
        path.write_text(json.dumps(cfg_dict), encoding="utf-8")

    def read_state_file(self):
        raw = (self.agent_dir / ".nav-runtime-state.json").read_text(encoding="utf-8")
        return json.loads(raw)

    def read_health_file(self):
        path = self.agent_dir / runtime.HEALTH_FILE_NAME
        return json.loads(path.read_text(encoding="utf-8"))

    def op_errors(self):
        return self.read_state_file()["meta"]["op_errors"]


class ModOwnershipTest(RuntimeTestBase):
    """v8 handoff (TASK-84): ops a loaded mod owns are skipped in one place."""

    def test_owned_op_is_skipped_others_run(self):
        calls = []
        registry = {"SessionStart": [
            self.make_op("owned_op", calls=calls, result={"additional_context": "A"}),
            self.make_op("python_op", calls=calls, result={"additional_context": "B"}),
        ]}
        os.environ["NAVIGATOR_MOD_OWNS"] = "owned_op"
        result = runtime.dispatch("SessionStart", self.payload(), registry=registry)
        self.assertEqual(calls, ["python_op"])
        self.assertIn("B", result.stdout or "")
        self.assertNotIn("A", result.stdout or "")

    def test_all_owned_fast_exits_without_state_write(self):
        calls = []
        registry = {"Stop": [self.make_op("a", calls=calls), self.make_op("b", calls=calls)]}
        os.environ["NAVIGATOR_MOD_OWNS"] = "a,b"
        result = runtime.dispatch("Stop", self.payload(), registry=registry)
        self.assertEqual(calls, [])
        self.assertIsNone(result.stdout)
        self.assertEqual(result.exit_code, 0)
        self.assertFalse((self.agent_dir / ".nav-runtime-state.json").exists())

    def test_unset_env_runs_everything(self):
        calls = []
        registry = {"Stop": [self.make_op("a", calls=calls), self.make_op("b", calls=calls)]}
        runtime.dispatch("Stop", self.payload(), registry=registry)
        self.assertEqual(calls, ["a", "b"])


class PhaseOrderingTest(RuntimeTestBase):
    def test_phases_run_in_order_regardless_of_registry_order(self):
        calls = []
        registry = {"Stop": [
            self.make_op("po_rec", phase="recorders", calls=calls),
            self.make_op("po_inj", phase="injectors", calls=calls),
            self.make_op("po_resp", phase="responders", calls=calls),
            self.make_op("po_gate_a", phase="gates", calls=calls),
            self.make_op("po_gate_b", phase="gates", calls=calls),
        ]}
        runtime.dispatch("Stop", self.payload(), registry=registry)
        self.assertEqual(
            calls, ["po_gate_a", "po_gate_b", "po_resp", "po_inj", "po_rec"]
        )

    def test_registry_order_stable_within_phase(self):
        calls = []
        registry = {"Stop": [
            self.make_op("st_b", phase="recorders", calls=calls),
            self.make_op("st_a", phase="recorders", calls=calls),
        ]}
        runtime.dispatch("Stop", self.payload(), registry=registry)
        self.assertEqual(calls, ["st_b", "st_a"])


class GateShortCircuitTest(RuntimeTestBase):
    def test_gate_block_skips_rightward_phases_but_not_sibling_gates(self):
        calls = []
        registry = {"UserPromptSubmit": [
            self.make_op("gs_gate1", phase="gates", calls=calls,
                         result={"decision": "block", "reason": "gate says no"}),
            self.make_op("gs_gate2", phase="gates", calls=calls),
            self.make_op("gs_resp", phase="responders", calls=calls),
            self.make_op("gs_inj", phase="injectors", calls=calls),
            self.make_op("gs_rec", phase="recorders", calls=calls),
        ]}
        result = runtime.dispatch("UserPromptSubmit", self.payload(),
                                  registry=registry)
        self.assertEqual(calls, ["gs_gate1", "gs_gate2"])
        self.assertEqual(json.loads(result.stdout),
                         {"decision": "block", "reason": "gate says no"})
        self.assertEqual(result.exit_code, 0)

    def test_gate_nonzero_exit_short_circuits_and_survives(self):
        calls = []
        registry = {"UserPromptSubmit": [
            self.make_op("ge_gate", phase="gates", calls=calls,
                         result={"exit_code": 2, "stderr": "<nav-block>reason</nav-block>"}),
            self.make_op("ge_inj", phase="injectors", calls=calls),
        ]}
        result = runtime.dispatch("UserPromptSubmit", self.payload(),
                                  registry=registry)
        self.assertEqual(calls, ["ge_gate"])
        self.assertEqual(result.exit_code, 2)
        self.assertIn("<nav-block>reason</nav-block>", result.stderr)

    def test_gate_permission_deny_short_circuits(self):
        calls = []
        registry = {"PreToolUse": [
            self.make_op("gp_gate", phase="gates", matcher="Read", calls=calls,
                         result={"permission_decision": "deny",
                                 "permission_reason": "bulk read"}),
            self.make_op("gp_rec", phase="recorders", matcher="Read", calls=calls),
        ]}
        result = runtime.dispatch("PreToolUse", self.payload(tool_name="Read"),
                                  registry=registry)
        self.assertEqual(calls, ["gp_gate"])
        doc = json.loads(result.stdout)
        self.assertEqual(doc["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(doc["hookSpecificOutput"]["permissionDecisionReason"],
                         "bulk read")
        self.assertEqual(doc["hookSpecificOutput"]["hookEventName"], "PreToolUse")

    def test_non_gate_block_does_not_short_circuit(self):
        calls = []
        registry = {"UserPromptSubmit": [
            self.make_op("ng_resp", phase="responders", calls=calls,
                         result={"decision": "block", "reason": "tier1 answer"}),
            self.make_op("ng_inj", phase="injectors", calls=calls),
        ]}
        runtime.dispatch("UserPromptSubmit", self.payload(), registry=registry)
        self.assertEqual(calls, ["ng_resp", "ng_inj"])


class MergeRulesTest(RuntimeTestBase):
    def test_context_concatenated_in_registry_order(self):
        registry = {"SessionStart": [
            self.make_op("mc_a", result={"additional_context": "alpha"}),
            self.make_op("mc_b", result={"additional_context": "beta"}),
        ]}
        result = runtime.dispatch("SessionStart", self.payload(), registry=registry)
        doc = json.loads(result.stdout)
        self.assertEqual(doc["hookSpecificOutput"]["additionalContext"],
                         "alpha\nbeta")
        self.assertEqual(doc["hookSpecificOutput"]["hookEventName"], "SessionStart")

    def test_context_order_is_registry_order_not_execution_order(self):
        # The gate executes first but is listed second in the registry.
        registry = {"SessionStart": [
            self.make_op("mo_inj", phase="injectors",
                         result={"additional_context": "from-injector"}),
            self.make_op("mo_gate", phase="gates",
                         result={"additional_context": "from-gate"}),
        ]}
        result = runtime.dispatch("SessionStart", self.payload(), registry=registry)
        doc = json.loads(result.stdout)
        self.assertEqual(doc["hookSpecificOutput"]["additionalContext"],
                         "from-injector\nfrom-gate")

    def test_context_clamped_to_event_budget(self):
        big = "\n".join("line %04d" % i for i in range(2000))
        self.assertGreater(len(big), budget.BUDGETS["SessionStart"])
        registry = {"SessionStart": [
            self.make_op("mb_big", result={"additional_context": big}),
        ]}
        result = runtime.dispatch("SessionStart", self.payload(), registry=registry)
        text = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertLessEqual(len(text), budget.BUDGETS["SessionStart"])
        self.assertTrue(text.endswith(budget.TRUNCATION_MARKER))

    def test_first_block_wins(self):
        registry = {"UserPromptSubmit": [
            self.make_op("fb_one", phase="responders",
                         result={"decision": "block", "reason": "first"}),
            self.make_op("fb_two", phase="responders",
                         result={"decision": "block", "reason": "second"}),
        ]}
        result = runtime.dispatch("UserPromptSubmit", self.payload(),
                                  registry=registry)
        self.assertEqual(json.loads(result.stdout),
                         {"decision": "block", "reason": "first"})

    def test_permission_deny_beats_ask(self):
        registry = {"PreToolUse": [
            self.make_op("pd_ask", phase="gates",
                         result={"permission_decision": "ask",
                                 "permission_reason": "ask first"}),
            self.make_op("pd_deny", phase="gates",
                         result={"permission_decision": "deny",
                                 "permission_reason": "deny wins"}),
        ]}
        result = runtime.dispatch("PreToolUse", self.payload(tool_name="Read"),
                                  registry=registry)
        hso = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(hso["permissionDecision"], "deny")
        self.assertEqual(hso["permissionDecisionReason"], "deny wins")

    def test_exit_code_is_max_of_op_exit_codes(self):
        registry = {"Stop": [
            self.make_op("xc_one", phase="recorders", result={"exit_code": 1}),
            self.make_op("xc_two", phase="recorders", result={"exit_code": 2}),
            self.make_op("xc_zero", phase="recorders", result={"exit_code": 0}),
        ]}
        result = runtime.dispatch("Stop", self.payload(), registry=registry)
        self.assertEqual(result.exit_code, 2)

    def test_continue_omitted_unless_explicitly_set(self):
        registry = {"SessionStart": [
            self.make_op("co_inj", result={"additional_context": "hello"}),
        ]}
        result = runtime.dispatch("SessionStart", self.payload(), registry=registry)
        self.assertNotIn("continue", json.loads(result.stdout))

    def test_continue_false_emitted_when_set(self):
        registry = {"Stop": [
            self.make_op("cf_op", phase="recorders", result={"continue_": False}),
        ]}
        result = runtime.dispatch("Stop", self.payload(), registry=registry)
        self.assertEqual(json.loads(result.stdout), {"continue": False})

    def test_continue_false_wins_over_true(self):
        # false-wins (AND): continue:false is the ONLY meaningful emission
        # (mem-051) — one op setting True must never mask another's False.
        registry = {"Stop": [
            self.make_op("cv_no", phase="recorders", result={"continue_": False}),
            self.make_op("cv_yes", phase="recorders", result={"continue_": True}),
        ]}
        result = runtime.dispatch("Stop", self.payload(), registry=registry)
        self.assertEqual(json.loads(result.stdout), {"continue": False})

    def test_continue_true_only_is_omitted(self):
        # true is the harness default: emitting it is noise, so the key is
        # omitted entirely when ops only ever set continue_ True.
        registry = {"Stop": [
            self.make_op("ct_yes", phase="recorders",
                         result={"continue_": True, "system_message": "note"}),
        ]}
        result = runtime.dispatch("Stop", self.payload(), registry=registry)
        self.assertEqual(json.loads(result.stdout), {"systemMessage": "note"})

    def test_user_prompt_context_only_is_plain_stdout(self):
        registry = {"UserPromptSubmit": [
            self.make_op("up_brief",
                         result={"additional_context": "NAV-BRIEF: confirm scope"}),
        ]}
        result = runtime.dispatch("UserPromptSubmit", self.payload(),
                                  registry=registry)
        self.assertEqual(result.stdout, "NAV-BRIEF: confirm scope")

    def test_user_prompt_context_folds_into_json_when_mixed(self):
        registry = {"UserPromptSubmit": [
            self.make_op("um_ctx", result={"additional_context": "guidance"}),
            self.make_op("um_msg", phase="recorders",
                         result={"system_message": "recorded"}),
        ]}
        result = runtime.dispatch("UserPromptSubmit", self.payload(),
                                  registry=registry)
        doc = json.loads(result.stdout)
        self.assertEqual(doc["hookSpecificOutput"]["additionalContext"], "guidance")
        self.assertEqual(doc["systemMessage"], "recorded")

    def test_context_dropped_for_events_without_proven_channel(self):
        registry = {"Stop": [
            self.make_op("dp_ctx", result={"additional_context": "lost"}),
        ]}
        result = runtime.dispatch("Stop", self.payload(), registry=registry)
        self.assertIsNone(result.stdout)

    def test_exactly_one_json_doc_with_all_channels(self):
        registry = {"SessionStart": [
            self.make_op("od_ctx", result={"additional_context": "ctx"}),
            self.make_op("od_more", phase="recorders",
                         result={"system_message": "note", "continue_": True}),
        ]}
        result = runtime.dispatch("SessionStart", self.payload(), registry=registry)
        doc = json.loads(result.stdout)  # parses as ONE document
        self.assertEqual(doc["hookSpecificOutput"]["additionalContext"], "ctx")
        self.assertEqual(doc["systemMessage"], "note")
        self.assertNotIn("continue", doc)  # true = harness default, never emitted

    def test_op_stderr_passthrough_joined(self):
        registry = {"Stop": [
            self.make_op("se_a", phase="recorders", result={"stderr": "line-a"}),
            self.make_op("se_b", phase="recorders", result={"stderr": "line-b"}),
        ]}
        result = runtime.dispatch("Stop", self.payload(), registry=registry)
        self.assertEqual(result.stderr, "line-a\nline-b")

    def test_silent_ops_produce_no_output(self):
        registry = {"Stop": [
            self.make_op("sn_none", phase="recorders", result=None),
            self.make_op("sn_empty", phase="recorders", result={}),
        ]}
        result = runtime.dispatch("Stop", self.payload(), registry=registry)
        self.assertIsNone(result.stdout)
        self.assertEqual(result.exit_code, 0)
        self.assertIsNone(result.stderr)

    def test_ack_alone_emits_bare_empty_doc(self):
        # TASK-61 parity: v6 side-effect hooks print `{}` as a pure
        # acknowledgment; {"ack": True} reproduces that byte shape.
        registry = {"Stop": [
            self.make_op("ak_rec", phase="recorders", result={"ack": True}),
        ]}
        result = runtime.dispatch("Stop", self.payload(), registry=registry)
        self.assertEqual(result.stdout, "{}")
        self.assertEqual(result.exit_code, 0)
        self.assertIsNone(result.stderr)

    def test_ack_subsumed_by_real_output_keys(self):
        registry = {"Stop": [
            self.make_op("as_rec", phase="recorders",
                         result={"ack": True, "system_message": "note"}),
        ]}
        result = runtime.dispatch("Stop", self.payload(), registry=registry)
        self.assertEqual(json.loads(result.stdout), {"systemMessage": "note"})


class CrashIsolationTest(RuntimeTestBase):
    SECRET = "run until done: the user prompt text"

    def _crash_registry(self):
        calls = []
        secret = self.SECRET

        def crash(ctx):
            raise ValueError(secret)

        registry = {"PostCompact": [
            self.spec("cr_boom", phase="recorders"),
            self.make_op("cr_sibling", phase="recorders", calls=calls),
        ]}
        self.register_op("cr_boom", crash)
        return registry, calls

    def test_siblings_still_run_after_crash(self):
        registry, calls = self._crash_registry()
        runtime.dispatch("PostCompact", self.payload(), registry=registry)
        self.assertEqual(calls, ["cr_sibling"])

    def test_crash_emits_one_sentinel_line_without_payload_text(self):
        registry, _ = self._crash_registry()
        result = runtime.dispatch("PostCompact", self.payload(prompt=self.SECRET),
                                  registry=registry)
        self.assertEqual(result.stderr.count(runtime.ERROR_SENTINEL), 1)
        self.assertIn("op=cr_boom", result.stderr)
        self.assertIn("error=ValueError", result.stderr)
        self.assertNotIn(self.SECRET, result.stderr)
        self.assertEqual(result.exit_code, 0)  # crashes never set exit codes

    def test_crash_recorded_in_op_errors_and_health(self):
        registry, _ = self._crash_registry()
        runtime.dispatch("PostCompact", self.payload(), registry=registry)
        errors = self.op_errors()
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["op"], "cr_boom")
        self.assertIn("ValueError", errors[0]["error"])
        self.assertIn("ts", errors[0])
        health = self.read_health_file()
        self.assertIs(health["surfaced"], False)
        self.assertEqual(health["last_error"]["op"], "cr_boom")
        self.assertEqual(health["last_error"]["event"], "PostCompact")

    def test_invalid_result_type_is_crash_class(self):
        calls = []
        registry = {"Stop": [
            self.make_op("iv_bad", phase="recorders", result="not-a-dict"),
            self.make_op("iv_ok", phase="recorders", calls=calls),
        ]}
        result = runtime.dispatch("Stop", self.payload(), registry=registry)
        self.assertEqual(calls, ["iv_ok"])
        self.assertIn(runtime.ERROR_SENTINEL, result.stderr)
        self.assertEqual(self.op_errors()[0]["op"], "iv_bad")
        self.assertTrue((self.agent_dir / runtime.HEALTH_FILE_NAME).is_file())

    def test_sys_exit_from_op_is_crash_class_never_propagated(self):
        # v6 hooks use sys.exit as control flow; SystemExit must not escape
        # the per-op isolation (exit 3 would reach the harness; exit 2 would
        # block). Crash-class treatment: op_errors + sentinel + health, exit
        # code recorded in the note but the dispatch exit code stays 0.
        calls = []

        def bail(ctx):
            sys.exit(3)

        self.register_op("sx_exit", bail)
        registry = {"Stop": [
            self.spec("sx_exit", phase="recorders"),
            self.make_op("sx_sibling", phase="recorders", calls=calls),
        ]}
        result = runtime.dispatch("Stop", self.payload(), registry=registry)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(calls, ["sx_sibling"])  # sibling still ran
        self.assertIn("error=SystemExit", result.stderr)
        errors = self.op_errors()
        self.assertEqual(errors[0]["op"], "sx_exit")
        self.assertEqual(errors[0]["error"], "SystemExit code=3")
        health = self.read_health_file()
        self.assertEqual(health["last_error"]["op"], "sx_exit")
        self.assertIn("SystemExit", health["last_error"]["error"])

    def test_keyboard_interrupt_is_reraised(self):
        def interrupt(ctx):
            raise KeyboardInterrupt()

        self.register_op("ki_op", interrupt)
        registry = {"Stop": [self.spec("ki_op", phase="recorders")]}
        with self.assertRaises(KeyboardInterrupt):
            runtime.dispatch("Stop", self.payload(), registry=registry)

    def test_exception_message_never_persists_to_any_sink(self):
        # Class-only redaction everywhere the error is stored or surfaced:
        # the message can embed payload/prompt text (loop triggers included)
        # and health lines re-enter model context at SessionStart.
        def crash(ctx):
            raise ValueError("SECRET run until done")

        self.register_op("rx_boom", crash)
        registry = {"Stop": [self.spec("rx_boom", phase="recorders")]}
        result = runtime.dispatch("Stop", self.payload(), registry=registry)
        self.assertNotIn("SECRET", result.stderr)

        state_raw = (self.agent_dir / ".nav-runtime-state.json").read_text()
        self.assertIn("ValueError", json.dumps(self.op_errors()))
        self.assertNotIn("SECRET", state_raw)

        health_raw = (self.agent_dir / runtime.HEALTH_FILE_NAME).read_text()
        self.assertIn("ValueError", health_raw)
        self.assertNotIn("SECRET", health_raw)

        surfaced = runtime.dispatch("SessionStart", self.payload(),
                                    registry={"SessionStart": []})
        text = json.loads(surfaced.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("ValueError", text)
        self.assertNotIn("SECRET", text)


class SoftDeadlineTest(RuntimeTestBase):
    def test_deadline_drops_non_gates_but_never_gates(self):
        calls = []

        class Clock:
            t = 1000.0

            def __call__(self):
                return self.t

        clock = Clock()

        def gate_slow(ctx):
            calls.append("dl_gate_slow")
            clock.t = 1000.0 + 3600  # blow way past every deadline
            return None

        self.register_op("dl_gate_slow", gate_slow)
        registry = {"Stop": [
            self.spec("dl_gate_slow", phase="gates"),
            self.make_op("dl_gate_late", phase="gates", calls=calls),
            self.make_op("dl_resp", phase="responders", calls=calls),
            self.make_op("dl_inj", phase="injectors", calls=calls),
            self.make_op("dl_rec", phase="recorders", calls=calls),
        ]}
        result = runtime.dispatch("Stop", self.payload(), registry=registry,
                                  now=clock)
        self.assertEqual(calls, ["dl_gate_slow", "dl_gate_late"])
        self.assertEqual(result.exit_code, 0)
        # Deadline skips are observability notes, not crashes: one op_errors
        # entry per skipped op, but no stderr sentinel and no health write.
        notes = self.op_errors()
        self.assertEqual([n["op"] for n in notes], ["dl_resp", "dl_inj", "dl_rec"])
        self.assertEqual({n["error"] for n in notes}, {"deadline-skipped"})
        for note in notes:
            self.assertIn("ts", note)
        self.assertIsNone(result.stderr)
        self.assertFalse((self.agent_dir / runtime.HEALTH_FILE_NAME).exists())

    def test_event_timeouts_match_v6_allowances(self):
        # FIX: v6 gave PostToolUse hooks 10s each and PostCompact 10s — the
        # shared dispatcher must not silently regress them to the 5s default.
        self.assertEqual(runtime.EVENT_TIMEOUTS, {
            "SessionStart": 10, "PostToolUse": 10,
            "PreCompact": 30, "PostCompact": 10,
        })
        self.assertEqual(runtime.DEFAULT_TIMEOUT_SECONDS, 5)

    def test_within_deadline_everything_runs(self):
        calls = []
        registry = {"Stop": [
            self.make_op("wd_gate", phase="gates", calls=calls),
            self.make_op("wd_rec", phase="recorders", calls=calls),
        ]}
        runtime.dispatch("Stop", self.payload(), registry=registry, now=1000.0)
        self.assertEqual(calls, ["wd_gate", "wd_rec"])


class StateLifecycleTest(RuntimeTestBase):
    def test_state_loaded_once_saved_once_inside_lock(self):
        events = []
        real_load, real_save, real_lock = state.load, state.save, state.lock

        def load_spy(*args, **kwargs):
            events.append("load")
            return real_load(*args, **kwargs)

        def save_spy(*args, **kwargs):
            events.append("save")
            return real_save(*args, **kwargs)

        @contextlib.contextmanager
        def lock_spy(agent_dir):
            events.append("lock-enter")
            with real_lock(agent_dir):
                yield
            events.append("lock-exit")

        state.load, state.save, state.lock = load_spy, save_spy, lock_spy
        self.addCleanup(lambda: setattr(state, "load", real_load))
        self.addCleanup(lambda: setattr(state, "save", real_save))
        self.addCleanup(lambda: setattr(state, "lock", real_lock))

        def op(ctx):
            events.append("op")
            return None

        self.register_op("sl_probe", op)
        registry = {"Stop": [self.spec("sl_probe", phase="recorders")]}
        runtime.dispatch("Stop", self.payload(), registry=registry)
        self.assertEqual(events, ["lock-enter", "load", "op", "save", "lock-exit"])

    def test_op_state_mutations_persist_with_session_stamp(self):
        def op(ctx):
            ctx.state["turn"] = {"marker": 41}
            ctx.state["turn"]["marker"] += 1
            return None

        self.register_op("sm_writer", op)
        registry = {"Stop": [self.spec("sm_writer", phase="recorders")]}
        runtime.dispatch("Stop", self.payload(), registry=registry)
        raw = self.read_state_file()
        self.assertEqual(raw["turn"], {"marker": 42})
        self.assertEqual(raw["session"]["id"], SESSION_ID)
        self.assertEqual(raw["meta"]["schema"], 2)


class PilotExecutorTest(RuntimeTestBase):
    def test_evaluated_once_and_visible_to_every_op(self):
        calls = []
        seen = []
        real = config.is_pilot_executor

        def fake_pilot():
            calls.append(1)
            return True

        config.is_pilot_executor = fake_pilot
        self.addCleanup(lambda: setattr(config, "is_pilot_executor", real))

        def observer(name):
            def run(ctx):
                seen.append((name, ctx.pilot_executor))
                return None
            return run

        self.register_op("pe_one", observer("pe_one"))
        self.register_op("pe_two", observer("pe_two"))
        registry = {"Stop": [
            self.spec("pe_one", phase="gates"),
            self.spec("pe_two", phase="recorders"),
        ]}
        runtime.dispatch("Stop", self.payload(), registry=registry)
        self.assertEqual(len(calls), 1)
        self.assertEqual(seen, [("pe_one", True), ("pe_two", True)])

    def test_merge_belt_strips_blocking_output_under_pilot(self):
        # Structural belt: even an op that never checks ctx.pilot_executor
        # cannot block under Pilot — the merge strips decision/reason, deny/
        # ask, nonzero exit_code, and continue_ False from every result.
        # Non-blocking output (the injector's context) still flows.
        os.environ["PILOT_EXECUTOR"] = "1"
        self.addCleanup(lambda: os.environ.pop("PILOT_EXECUTOR", None))
        registry = {"UserPromptSubmit": [
            self.make_op("pb_gate", phase="gates", result={
                "decision": "block", "reason": "would block interactively",
                "permission_decision": "deny", "permission_reason": "nope",
                "exit_code": 2, "continue_": False,
            }),
            self.make_op("pb_inj", phase="injectors",
                         result={"additional_context": "PILOT-CTX-4f1a"}),
        ]}
        result = runtime.dispatch("UserPromptSubmit", self.payload(),
                                  registry=registry)
        self.assertEqual(result.exit_code, 0)
        # Context-only output -> plain stdout channel; the gate neither
        # blocked nor short-circuited the injector.
        self.assertEqual(result.stdout, "PILOT-CTX-4f1a")
        for leaked in ("block", "deny", "continue"):
            self.assertNotIn(leaked, result.stdout)

    def test_merge_belt_keeps_system_message_under_pilot(self):
        os.environ["PILOT_EXECUTOR"] = "1"
        self.addCleanup(lambda: os.environ.pop("PILOT_EXECUTOR", None))
        registry = {"Stop": [
            self.make_op("pm_rec", phase="recorders", result={
                "continue_": False, "system_message": "state recorded",
            }),
        ]}
        result = runtime.dispatch("Stop", self.payload(), registry=registry)
        self.assertEqual(json.loads(result.stdout),
                         {"systemMessage": "state recorded"})


class HealthSurfacingTest(RuntimeTestBase):
    def test_error_surfaces_at_next_session_start_exactly_once(self):
        def crash(ctx):
            raise RuntimeError("op exploded")

        self.register_op("hs_boom", crash)
        crash_registry = {"Stop": [self.spec("hs_boom", phase="recorders")]}
        runtime.dispatch("Stop", self.payload(), registry=crash_registry)
        self.assertIs(self.read_health_file()["surfaced"], False)

        quiet_registry = {"SessionStart": []}
        first = runtime.dispatch("SessionStart", self.payload(),
                                 registry=quiet_registry)
        text = json.loads(first.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("nav-dispatch: last dispatch error:", text)
        self.assertIn("Stop/hs_boom", text)
        self.assertIn("RuntimeError", text)
        self.assertIs(self.read_health_file()["surfaced"], True)

        second = runtime.dispatch("SessionStart", self.payload(),
                                  registry=quiet_registry)
        self.assertIsNone(second.stdout)  # surfaced exactly once

    def test_no_health_file_means_no_surfacing(self):
        result = runtime.dispatch("SessionStart", self.payload(),
                                  registry={"SessionStart": []})
        self.assertIsNone(result.stdout)

    def test_health_line_prepended_and_survives_a_full_budget(self):
        # The surfacing line goes BEFORE op contexts pre-clamp: budget.clamp
        # cuts from the tail, so a SessionStart injector that fills the whole
        # budget must not silently eat the line while surfaced flips true.
        def crash(ctx):
            raise RuntimeError("boom")

        self.register_op("hp_boom", crash)
        runtime.dispatch("Stop", self.payload(),
                         registry={"Stop": [self.spec("hp_boom", phase="recorders")]})
        self.assertIs(self.read_health_file()["surfaced"], False)

        big = "\n".join("navigator line %05d" % i for i in range(2000))
        self.assertGreater(len(big), budget.BUDGETS["SessionStart"])
        registry = {"SessionStart": [
            self.make_op("hp_big", result={"additional_context": big}),
        ]}
        result = runtime.dispatch("SessionStart", self.payload(), registry=registry)
        text = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(text.startswith("nav-dispatch: last dispatch error:"),
                        text[:120])
        self.assertIn("Stop/hp_boom", text)
        self.assertLessEqual(len(text), budget.BUDGETS["SessionStart"])
        self.assertIs(self.read_health_file()["surfaced"], True)


class MissingModuleTest(RuntimeTestBase):
    def test_missing_op_module_notes_without_sentinel_or_health(self):
        registry = {"SessionStart": [
            self.spec("mm_never_registered", phase="injectors"),
        ]}
        result = runtime.dispatch("SessionStart", self.payload(), registry=registry)
        self.assertEqual(result.exit_code, 0)
        self.assertIsNone(result.stderr)
        errors = self.op_errors()
        self.assertEqual(errors[0]["op"], "mm_never_registered")
        self.assertEqual(errors[0]["error"], "op module not found")
        self.assertFalse((self.agent_dir / runtime.HEALTH_FILE_NAME).exists())


class MatcherTest(RuntimeTestBase):
    def _run(self, matcher, tool_name, event="PreToolUse"):
        calls = []
        registry = {event: [
            self.make_op(f"mt_{event}_{tool_name or 'none'}", phase="gates",
                         matcher=matcher, calls=calls),
        ]}
        payload = self.payload()
        if tool_name is not None:
            payload["tool_name"] = tool_name
        runtime.dispatch(event, payload, registry=registry)
        return calls

    def test_matcher_hit_runs_op(self):
        self.assertEqual(len(self._run("Read", "Read")), 1)

    def test_matcher_miss_skips_op(self):
        self.assertEqual(self._run("Read", "Write"), [])

    def test_matcher_is_full_match_not_prefix(self):
        self.assertEqual(self._run("Read", "ReadMcpResource"), [])

    def test_alternation_matcher(self):
        self.assertEqual(len(self._run("Edit|Write|MultiEdit|NotebookEdit",
                                       "Write", event="PostToolUse")), 1)

    def test_matcher_with_missing_tool_name_skips(self):
        self.assertEqual(self._run("Read", None), [])

    def test_none_matcher_always_runs(self):
        self.assertEqual(len(self._run(None, "Anything")), 1)

    def test_matcher_ignored_on_non_tool_events(self):
        self.assertEqual(len(self._run("Read", "irrelevant", event="Stop")), 1)


class ConfigGateTest(RuntimeTestBase):
    def test_disabled_config_key_skips_silently(self):
        self.write_config({"read_guard_hook": {"enabled": False}})
        calls = []
        registry = {"PreToolUse": [
            self.make_op("cg_guard", phase="gates", matcher="Read",
                         config_key="read_guard_hook", calls=calls),
        ]}
        result = runtime.dispatch("PreToolUse", self.payload(tool_name="Read"),
                                  registry=registry)
        self.assertEqual(calls, [])
        self.assertIsNone(result.stderr)
        self.assertEqual(self.op_errors(), [])

    def test_enabled_config_key_runs(self):
        self.write_config({"read_guard_hook": {"enabled": True}})
        calls = []
        registry = {"PreToolUse": [
            self.make_op("cg_on", phase="gates", matcher="Read",
                         config_key="read_guard_hook", calls=calls),
        ]}
        runtime.dispatch("PreToolUse", self.payload(tool_name="Read"),
                         registry=registry)
        self.assertEqual(calls, ["cg_on"])

    def test_missing_config_key_defaults_to_enabled(self):
        calls = []
        registry = {"Stop": [
            self.make_op("cg_unknown", phase="recorders",
                         config_key="block_that_does_not_exist", calls=calls),
        ]}
        runtime.dispatch("Stop", self.payload(), registry=registry)
        self.assertEqual(calls, ["cg_unknown"])

    def test_dispatcher_kill_switch(self):
        self.write_config({"dispatcher": {"enabled": False}})
        calls = []
        registry = {"Stop": [self.make_op("cg_dead", phase="gates", calls=calls)]}
        result = runtime.dispatch("Stop", self.payload(), registry=registry)
        self.assertEqual(calls, [])
        self.assertEqual((result.stdout, result.exit_code, result.stderr),
                         (None, 0, None))


class FailOpenTest(RuntimeTestBase):
    def test_no_agent_dir_degrades_silently(self):
        with tempfile.TemporaryDirectory() as bare:
            bare_root = Path(bare).resolve()
            calls = []
            registry = {"Stop": [self.make_op("fo_op", phase="gates", calls=calls)]}
            result = runtime.dispatch(
                "Stop", {"cwd": str(bare_root), "session_id": SESSION_ID},
                registry=registry)
            self.assertEqual((result.stdout, result.exit_code, result.stderr),
                             (None, 0, None))
            self.assertEqual(calls, [])
            self.assertFalse((bare_root / ".agent").exists())

    def test_default_registry_missing_module_is_safe(self):
        result = runtime.dispatch("UserPromptSubmit", self.payload(), registry=None)
        self.assertEqual(result.exit_code, 0)

    def test_non_dict_payload_never_raises(self):
        result = runtime.dispatch("Stop", None, registry={"Stop": []})
        self.assertEqual(result.exit_code, 0)

    def test_blank_or_non_string_event_is_silent(self):
        for event in ("", None, 42):
            result = runtime.dispatch(event, self.payload(), registry={})
            self.assertEqual((result.stdout, result.exit_code, result.stderr),
                             (None, 0, None))

    def test_broken_registry_object_fails_open_with_sentinel(self):
        result = runtime.dispatch("Stop", self.payload(), registry=42)
        self.assertEqual(result.exit_code, 0)
        self.assertIsNone(result.stdout)
        self.assertIn(runtime.ERROR_SENTINEL, result.stderr)
        self.assertIn("op=dispatch", result.stderr)

    def test_unknown_event_with_empty_registry(self):
        result = runtime.dispatch("NoSuchEvent", self.payload(), registry={})
        self.assertEqual((result.stdout, result.exit_code, result.stderr),
                         (None, 0, None))


class ContextObjectTest(RuntimeTestBase):
    def test_ctx_carries_contract_fields(self):
        seen = {}

        def probe(ctx):
            seen["event"] = ctx.event
            seen["payload"] = ctx.payload
            seen["config_is_dict"] = isinstance(ctx.config, dict)
            seen["state_is_dict"] = isinstance(ctx.state, dict)
            seen["pilot"] = ctx.pilot_executor
            seen["now"] = ctx.now
            return None

        self.register_op("cx_probe", probe)
        registry = {"Stop": [self.spec("cx_probe", phase="recorders")]}
        payload = self.payload(prompt="hello")
        runtime.dispatch("Stop", payload, registry=registry, now=1234.5)
        self.assertEqual(seen["event"], "Stop")
        self.assertEqual(seen["payload"], payload)
        self.assertTrue(seen["config_is_dict"])
        self.assertTrue(seen["state_is_dict"])
        self.assertIs(seen["pilot"], False)
        self.assertEqual(seen["now"], 1234.5)


if __name__ == "__main__":
    unittest.main()
