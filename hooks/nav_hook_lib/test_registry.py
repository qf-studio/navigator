#!/usr/bin/env python3
"""Unit tests for nav_hook_lib/registry.py (TASK-60 Phase 2).

stdlib unittest only. Covers:

  - EVENT_OPS keys are EXACTLY the seven v6 manifest event surfaces plus the
    six TASK-62 events that survived the validate-or-drop gate (SubagentStart,
    PostToolUseFailure, TaskCreated, TaskCompleted, ConfigChange, Setup).
  - OpSpec is a dataclass with exactly the five contract fields
    (name, phase, matcher, config_key, budget_ms), every field populated
    with the right type on every live row.
  - Phases are valid PHASE_ORDER values and each event's ops are listed in
    non-decreasing phase order (registry order IS merge order).
  - config_key per row resolves an 'enabled' toggle: v6-ported rows verify
    against the pristine fixture fixtures/nav-config-v6.18.1.json, with the
    exact block names quoted here (session_start_hook,
    workflow_enforcer_hook, brief_hook, read_guard_hook,
    task_graph_sync_hook, profile_sync_hook, workflow_state_hook,
    compact_hook); v7 rows (absent by design from pristine v6 configs)
    verify against config.DEFAULTS: blocking/injecting blocks (tier1,
    stop_completion, jit_memory, subagent_context, failure_diagnosis) must
    seed enabled=false so old configs default safe, while the
    systemMessage-only safety surfaces (config_guard, setup_hook) seed on.
  - Matcher regexes compile; the contract matchers behave ('Read',
    'Edit|Write|MultiEdit|NotebookEdit').
  - Every landed TASK-62 row is a live OpSpec citing its mem-05x verdict in
    an adjacent registry comment (config_guard has no spike dependency), and
    every registered op name maps to a committed hooks/ops/<name>.py file
    (v5.1.0 lesson: no registration without its file in the same commit).
  - registry.py stays pure data: no op imports, no I/O modules.
"""

import ast
import json
import re
import sys
import unittest
from dataclasses import fields, is_dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402  (sibling import; path pinned above)
import registry  # noqa: E402  (sibling import; path pinned above)

LIB_DIR = Path(__file__).resolve().parent
FIXTURE = LIB_DIR / "fixtures" / "nav-config-v6.18.1.json"
OPS_DIR = LIB_DIR.parent / "ops"

# The seven v6 manifest event surfaces.
V6_EVENTS = {
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "PreCompact",
    "PostCompact",
}

# TASK-62 event surfaces: all six candidates survived the validate-or-drop
# gate (`claude plugin validate`, CC 2.1.205 — a bogus-name control probe was
# rejected, proving the gate checks event names).
TASK62_EVENTS = {
    "SubagentStart",
    "PostToolUseFailure",
    "TaskCreated",
    "TaskCompleted",
    "ConfigChange",
    "Setup",
}

ALL_EVENTS = V6_EVENTS | TASK62_EVENTS

# The eight TASK-61 rows + every landed TASK-62 row, in order.
EXPECTED_ROWS = {
    "SessionStart": ["session_start"],
    "UserPromptSubmit": ["prompt_gate", "prompt_tier1", "prompt_modes", "prompt_brief"],
    "PreToolUse": ["read_guard"],
    "PostToolUse": ["jit_memory", "graph_sync", "profile_sync"],
    "Stop": ["stop_completion", "stop_state"],
    "PreCompact": ["compact_marker"],
    "PostCompact": ["compact_marker"],
    "SubagentStart": ["subagent_context"],
    "PostToolUseFailure": ["failure_diagnosis"],
    "TaskCreated": ["graph_sync"],
    "TaskCompleted": ["graph_sync"],
    "ConfigChange": ["config_guard"],
    "Setup": ["setup"],
}

# op name -> the EXACT toggle block name in .agent/.nav-config.json.
EXPECTED_CONFIG_KEYS = {
    "session_start": "session_start_hook",
    "prompt_gate": "workflow_enforcer_hook",
    "prompt_tier1": "tier1",
    "prompt_modes": "reply_modes",
    "prompt_brief": "brief_hook",
    "read_guard": "read_guard_hook",
    "graph_sync": "task_graph_sync_hook",
    "profile_sync": "profile_sync_hook",
    "stop_completion": "stop_completion",
    "stop_state": "workflow_state_hook",
    "compact_marker": "compact_hook",
    "jit_memory": "jit_memory",
    "subagent_context": "subagent_context",
    "failure_diagnosis": "failure_diagnosis",
    "config_guard": "config_guard",
    "setup": "setup_hook",
}

# v7 rows: their toggle blocks are deliberately ABSENT from the pristine
# v6.18.1 fixture; they resolve via config.DEFAULTS. Blocking/injecting
# features seed OFF; the systemMessage-only safety surfaces seed ON.
V7_OFF_CONFIG_KEYS = {
    "tier1", "stop_completion", "jit_memory", "subagent_context",
    "failure_diagnosis",
}
# adhd_mode (TASK-82) seeds enabled=True too: the block only makes the toggle
# available; injection waits for the person's own switch (seeded off).
V7_ON_CONFIG_KEYS = {"config_guard", "setup_hook", "reply_modes"}
V7_CONFIG_KEYS = V7_OFF_CONFIG_KEYS | V7_ON_CONFIG_KEYS

EXPECTED_PHASES = {
    "session_start": "injectors",
    "prompt_gate": "gates",
    "prompt_tier1": "responders",
    "prompt_modes": "responders",
    "prompt_brief": "injectors",
    "read_guard": "gates",
    "graph_sync": "recorders",
    "profile_sync": "recorders",
    "stop_completion": "gates",
    "stop_state": "recorders",
    "compact_marker": "recorders",
    "jit_memory": "injectors",
    "subagent_context": "injectors",
    "failure_diagnosis": "injectors",
    "config_guard": "injectors",
    "setup": "injectors",
}

MUTATING_MATCHER = "Edit|Write|MultiEdit|NotebookEdit"

# Manifest timeouts per TASK-60 (runtime.EVENT_TIMEOUTS mirrors these; hardcoded
# here rather than imported — runtime.py is owned by a parallel task group).
# PostToolUse/PostCompact carry the v6 10s allowances (no 5s regression).
EVENT_TIMEOUT_SECONDS = {
    "SessionStart": 10, "PostToolUse": 10, "PreCompact": 30, "PostCompact": 10,
}
DEFAULT_TIMEOUT_SECONDS = 5

# TASK-62 ops landed as live rows: each must still cite its verdict memory
# in an adjacent registry comment. config_guard has no spike dependency in
# the routing matrix — no mem required.
LIVE_TASK62_MEM = {
    "prompt_tier1": "mem-053",
    "stop_completion": "mem-051",
    "jit_memory": "mem-050",
    "failure_diagnosis": "mem-050",
    "subagent_context": "mem-052",
    "config_guard": None,
    "setup": "mem-055",
}

# Spike-gated TASK-62 ops NOT yet landed: comments only. Empty since Phases
# 3-5 landed; the structure (and its never-live assertion) stays for any
# future spike-gated row.
FUTURE_OPS_MEM = {}


def _all_specs():
    for event in registry.EVENT_OPS:
        for spec in registry.EVENT_OPS[event]:
            yield event, spec


class EventSurfaceTest(unittest.TestCase):
    def test_events_are_exactly_the_v6_plus_task62_surfaces(self):
        self.assertEqual(set(registry.EVENT_OPS), ALL_EVENTS)
        self.assertEqual(set(registry.EVENTS), ALL_EVENTS)

    def test_every_event_has_at_least_one_op(self):
        for event, ops in registry.EVENT_OPS.items():
            self.assertIsInstance(ops, list, event)
            self.assertGreater(len(ops), 0, f"{event} has no ops")

    def test_expected_rows_in_order(self):
        for event, expected in EXPECTED_ROWS.items():
            names = [spec.name for spec in registry.EVENT_OPS[event]]
            self.assertEqual(names, expected, f"row mismatch for {event}")


class OpSpecShapeTest(unittest.TestCase):
    def test_opspec_is_a_dataclass_with_exactly_the_five_contract_fields(self):
        self.assertTrue(is_dataclass(registry.OpSpec))
        names = [f.name for f in fields(registry.OpSpec)]
        self.assertEqual(names, ["name", "phase", "matcher", "config_key", "budget_ms"])

    def test_every_field_populated_with_correct_type(self):
        for event, spec in _all_specs():
            where = f"{event}/{spec.name}"
            self.assertIsInstance(spec.name, str, where)
            self.assertTrue(spec.name, where)
            self.assertTrue(spec.name.isidentifier(), f"{where}: name must be a module name")
            self.assertIsInstance(spec.phase, str, where)
            self.assertIn(spec.phase, registry.PHASE_ORDER, where)
            self.assertTrue(
                spec.matcher is None or isinstance(spec.matcher, str), where
            )
            if isinstance(spec.matcher, str):
                self.assertTrue(spec.matcher, f"{where}: matcher must be None or non-empty")
            self.assertIsInstance(spec.config_key, str, where)
            self.assertTrue(spec.config_key, where)
            self.assertIsInstance(spec.budget_ms, int, where)
            self.assertNotIsInstance(spec.budget_ms, bool, where)
            self.assertGreater(spec.budget_ms, 0, where)


class PhaseTest(unittest.TestCase):
    def test_phase_order_constant(self):
        self.assertEqual(
            registry.PHASE_ORDER, ("gates", "responders", "injectors", "recorders")
        )

    def test_expected_phase_per_op(self):
        for event, spec in _all_specs():
            self.assertEqual(
                spec.phase, EXPECTED_PHASES[spec.name], f"{event}/{spec.name}"
            )

    def test_ops_listed_in_phase_order_within_each_event(self):
        # Registry order is merge order; it must never contradict phase order.
        rank = {phase: i for i, phase in enumerate(registry.PHASE_ORDER)}
        for event, ops in registry.EVENT_OPS.items():
            ranks = [rank[spec.phase] for spec in ops]
            self.assertEqual(ranks, sorted(ranks), f"{event} ops out of phase order")


class ConfigKeyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert FIXTURE.is_file(), f"missing fixture: {FIXTURE}"
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_config_key_matches_expected_v6_block_per_op(self):
        for event, spec in _all_specs():
            self.assertEqual(
                spec.config_key,
                EXPECTED_CONFIG_KEYS[spec.name],
                f"{event}/{spec.name}",
            )

    def test_every_v6_config_key_is_a_block_in_the_v6_fixture(self):
        for event, spec in _all_specs():
            if spec.config_key in V7_CONFIG_KEYS:
                continue  # v7 blocks are absent from pristine v6 configs
            where = f"{event}/{spec.name}: {spec.config_key}"
            self.assertIn(spec.config_key, self.fixture, where)
            self.assertIsInstance(self.fixture[spec.config_key], dict, where)

    def test_every_v6_config_key_block_has_an_enabled_toggle(self):
        # The runtime gates ops on config.get(cfg, key + '.enabled', True);
        # every mapped block must actually carry the toggle in v6.18.1.
        for event, spec in _all_specs():
            if spec.config_key in V7_CONFIG_KEYS:
                continue
            block = self.fixture[spec.config_key]
            self.assertIn(
                "enabled", block, f"{event}/{spec.name}: {spec.config_key}.enabled"
            )
            self.assertIsInstance(block["enabled"], bool, spec.config_key)

    def test_v7_config_keys_seed_the_right_posture_in_defaults(self):
        # v7 rows must resolve via config.DEFAULTS so a pristine v6.18.1
        # config loads safely: blocking/responding/injecting features seed
        # enabled=False (migration policy); the systemMessage-only safety
        # surfaces (config_guard, setup_hook) seed enabled=True.
        live_v7 = {
            spec.config_key for _, spec in _all_specs()
            if spec.config_key in V7_CONFIG_KEYS
        }
        self.assertEqual(live_v7, V7_CONFIG_KEYS)
        for key in sorted(V7_OFF_CONFIG_KEYS):
            block = config.DEFAULTS.get(key)
            self.assertIsInstance(block, dict, key)
            self.assertIs(block.get("enabled"), False, f"{key}.enabled must seed False")
        for key in sorted(V7_ON_CONFIG_KEYS):
            block = config.DEFAULTS.get(key)
            self.assertIsInstance(block, dict, key)
            self.assertIs(block.get("enabled"), True, f"{key}.enabled must seed True")


class MatcherTest(unittest.TestCase):
    def test_all_matchers_compile(self):
        for event, spec in _all_specs():
            if spec.matcher is not None:
                try:
                    re.compile(spec.matcher)
                except re.error as exc:
                    self.fail(f"{event}/{spec.name}: matcher does not compile: {exc}")

    def test_matcher_values_match_the_contract(self):
        # Keyed by (event, op): graph_sync carries the mutating matcher on
        # PostToolUse but None on the TaskCreated/TaskCompleted lifecycle
        # events (matchers only apply to Pre/PostToolUse payloads).
        expected = {
            ("PreToolUse", "read_guard"): "Read",
            ("PostToolUse", "jit_memory"): MUTATING_MATCHER,
            ("PostToolUse", "graph_sync"): MUTATING_MATCHER,
            ("PostToolUse", "profile_sync"): MUTATING_MATCHER,
        }
        for event, spec in _all_specs():
            self.assertEqual(
                spec.matcher, expected.get((event, spec.name)),
                f"{event}/{spec.name}",
            )

    def test_mutating_matcher_hits_all_four_tools_and_not_bash(self):
        pattern = re.compile(MUTATING_MATCHER)
        for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            self.assertTrue(pattern.search(tool), tool)
        self.assertIsNone(pattern.search("Bash"))
        self.assertIsNone(pattern.search("Read"))

    def test_module_constant_matches_registry_rows(self):
        self.assertEqual(registry.MUTATING_TOOLS, MUTATING_MATCHER)


class BudgetSanityTest(unittest.TestCase):
    def test_per_event_budgets_fit_under_the_soft_deadline(self):
        # Soft deadline = manifest timeout - 500ms. The advisory op budgets
        # for one event must collectively fit under it, or they are lies.
        for event, ops in registry.EVENT_OPS.items():
            timeout_s = EVENT_TIMEOUT_SECONDS.get(event, DEFAULT_TIMEOUT_SECONDS)
            deadline_ms = timeout_s * 1000 - 500
            total = sum(spec.budget_ms for spec in ops)
            self.assertLessEqual(
                total, deadline_ms,
                f"{event}: op budgets {total}ms exceed soft deadline {deadline_ms}ms",
            )


class FutureRowsTest(unittest.TestCase):
    """TASK-62 row discipline: landed ops are live OpSpecs citing their
    verdict memories in adjacent comments; any spike-gated op NOT yet landed
    (FUTURE_OPS_MEM, empty since Phases 3-5 shipped) stays comment-only."""

    @classmethod
    def setUpClass(cls):
        cls.source = Path(registry.__file__).read_text(encoding="utf-8")

    def test_future_ops_are_not_live_opspecs(self):
        live = {spec.name for _, spec in _all_specs()}
        overlap = live & set(FUTURE_OPS_MEM)
        self.assertEqual(
            overlap, set(),
            f"unlanded TASK-62 ops registered as live OpSpecs: {sorted(overlap)}",
        )

    def test_landed_task62_ops_are_live_opspecs(self):
        live = {spec.name for _, spec in _all_specs()}
        missing = set(LIVE_TASK62_MEM) - live
        self.assertEqual(
            missing, set(),
            f"landed TASK-62 ops missing from the registry: {sorted(missing)}",
        )

    def _assert_mem_cited_near(self, op_name, mem_id):
        self.assertIn(op_name, self.source, f"missing TASK-62 row: {op_name}")
        # The verdict memory must be cited on the same comment block as the
        # op name (within a few lines of its first mention).
        idx = self.source.index(op_name)
        window = self.source[max(0, idx - 700): idx + 700]
        self.assertIn(
            mem_id, window,
            f"{op_name}: registry must cite its verdict memory {mem_id}",
        )

    def test_future_ops_documented_in_comments_with_mem_verdicts(self):
        for op_name, mem_id in FUTURE_OPS_MEM.items():
            if mem_id is None:
                self.assertIn(
                    op_name, self.source, f"missing TASK-62 comment row: {op_name}"
                )
                continue
            self._assert_mem_cited_near(op_name, mem_id)

    def test_live_task62_ops_cite_mem_verdicts(self):
        for op_name, mem_id in LIVE_TASK62_MEM.items():
            if mem_id is None:  # config_guard: no spike dependency
                self.assertIn(op_name, self.source, f"missing row: {op_name}")
                continue
            self._assert_mem_cited_near(op_name, mem_id)

    def test_every_registered_op_has_a_committed_module_file(self):
        # v5.1.0 incident class: a manifest/registry entry referencing a file
        # the commit does not carry. Every live op name must map to
        # hooks/ops/<name>.py in this checkout.
        for event, spec in _all_specs():
            module_path = OPS_DIR / f"{spec.name}.py"
            self.assertTrue(
                module_path.is_file(),
                f"{event}/{spec.name}: missing op module {module_path}",
            )


class PureDataModuleTest(unittest.TestCase):
    """registry.py imports nothing but dataclasses — no ops, no I/O, no lib."""

    def test_registry_imports_are_pure_data(self):
        source = Path(registry.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=registry.__file__)
        allowed = {"dataclasses", "__future__"}
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            offenders.extend(
                f"registry.py:{node.lineno} imports '{name}'"
                for name in names
                if name and name not in allowed
            )
        self.assertEqual(offenders, [], "\n".join(offenders))


class OpsPackageMarkerTest(unittest.TestCase):
    def test_ops_package_marker_exists(self):
        self.assertTrue((OPS_DIR / "__init__.py").is_file(), OPS_DIR / "__init__.py")

    def test_ops_readme_documents_the_protocol(self):
        readme = OPS_DIR / "README.md"
        self.assertTrue(readme.is_file(), readme)
        text = readme.read_text(encoding="utf-8")
        self.assertIn("run(ctx)", text)
        for phase in registry.PHASE_ORDER:
            self.assertIn(phase, text)


if __name__ == "__main__":
    unittest.main()
