#!/usr/bin/env python3
"""Unit tests for nav_hook_lib/config.py (TASK-59 Phase 1) + lib-wide guard tests.

stdlib unittest only. Covers:

  - Layered defaults: a PRISTINE v6.18.1 config (fixtures/nav-config-v6.18.1.json,
    verbatim copy — no v7 blocks) loads with every DEFAULTS path present; the
    test iterates every block/leaf and proves zero KeyError.
  - v7 blocking features seeded OFF over the pristine fixture; dispatcher ON.
  - Deep merge: user leaves override, sibling defaults survive, unknown user
    keys preserved, missing/corrupt file -> DEFAULTS copy.
  - is_pilot_executor(): the single PILOT_EXECUTOR policy point.

Guard tests (lib-wide, glob-based so modules added by other task groups are
picked up automatically):

  - Stdlib purity: every hooks/nav_hook_lib/*.py imports only Python stdlib
    or sibling lib modules.
  - PILOT_EXECUTOR appears nowhere under hooks/** outside config.py, minus
    the two unported v6 hooks (allowlist empties in TASK-61 Phase 7).
"""

import ast
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402  (sibling import; path pinned above for package-mode discovery)

LIB_DIR = Path(__file__).resolve().parent
FIXTURE = LIB_DIR / "fixtures" / "nav-config-v6.18.1.json"

V6_BLOCKS = [
    "task_mode", "tom_features", "loop_mode", "simplification", "auto_update",
    "pilot", "session_start_hook", "compact_hook", "task_graph_sync_hook",
    "workflow_state_hook", "profile_sync_hook", "workflow_enforcer_hook",
    "brief_hook", "read_guard_hook", "knowledge_graph",
]
V7_BLOCKS = ["dispatcher", "tier1", "stop_completion", "jit_memory", "subagent_context",
             "adhd_mode"]


def _leaf_paths(node, prefix=()):
    """Yield every dotted leaf path in a nested dict (empty dicts count as leaves)."""
    for key, value in node.items():
        path = prefix + (key,)
        if isinstance(value, dict) and value:
            yield from _leaf_paths(value, path)
        else:
            yield path


class _ProjectDirMixin(unittest.TestCase):
    """Throwaway project root with an .agent/ dir per test."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(os.path.realpath(self._tmp.name))
        self.agent = self.root / ".agent"
        self.agent.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def write_config(self, obj_or_text):
        path = self.agent / ".nav-config.json"
        if isinstance(obj_or_text, str):
            path.write_text(obj_or_text, encoding="utf-8")
        else:
            path.write_text(json.dumps(obj_or_text, indent=2), encoding="utf-8")
        return path


class DefaultsShapeTest(unittest.TestCase):
    def test_every_v6_block_present_in_defaults(self):
        for block in V6_BLOCKS:
            self.assertIn(block, config.DEFAULTS)
            self.assertIsInstance(config.DEFAULTS[block], dict)

    def test_every_v7_block_present_in_defaults(self):
        for block in V7_BLOCKS:
            self.assertIn(block, config.DEFAULTS)
            self.assertIsInstance(config.DEFAULTS[block], dict)

    def test_v7_seed_values_match_contract(self):
        d = config.DEFAULTS
        self.assertTrue(d["dispatcher"]["enabled"])
        self.assertFalse(d["tier1"]["enabled"])
        self.assertEqual(d["tier1"]["rules"], {})
        self.assertFalse(d["stop_completion"]["enabled"])
        self.assertFalse(d["stop_completion"]["continue_enabled"])
        self.assertEqual(d["stop_completion"]["max_continues"], 2)
        self.assertFalse(d["jit_memory"]["enabled"])
        self.assertFalse(d["subagent_context"]["enabled"])
        self.assertEqual(d["subagent_context"]["budget_chars"], 2000)
        # TASK-82: available by default, but the switch itself defers (null).
        self.assertTrue(d["adhd_mode"]["enabled"])
        self.assertIsNone(d["adhd_mode"]["on"])


class LoadPristineFixtureTest(_ProjectDirMixin):
    """The old-consumer-config risk row: pristine v6.18.1 file, v7 consumers."""

    def setUp(self):
        super().setUp()
        self.assertTrue(FIXTURE.is_file(), f"missing fixture: {FIXTURE}")
        shutil.copy(FIXTURE, self.agent / ".nav-config.json")
        self.cfg = config.load(self.root)

    def test_fixture_is_pristine_v6(self):
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(raw["version"], "6.18.1")
        for block in V7_BLOCKS:
            self.assertNotIn(block, raw, f"fixture is not pristine: has v7 block {block}")

    def test_every_defaults_path_indexable_zero_keyerror(self):
        # Iterate EVERY block and leaf in DEFAULTS; direct dict indexing into
        # the loaded config must never raise KeyError.
        checked = 0
        for path in _leaf_paths(config.DEFAULTS):
            node = self.cfg
            try:
                for part in path:
                    node = node[part]
            except KeyError:
                self.fail(f"KeyError on defaults path: {'.'.join(path)}")
            checked += 1
        self.assertGreater(checked, 50, "leaf sweep unexpectedly small — walker broken?")

    def test_v7_blocks_seeded_off_over_pristine_fixture(self):
        self.assertIs(config.get(self.cfg, "dispatcher.enabled"), True)
        self.assertIs(config.get(self.cfg, "tier1.enabled"), False)
        self.assertEqual(config.get(self.cfg, "tier1.rules"), {})
        self.assertIs(config.get(self.cfg, "stop_completion.enabled"), False)
        self.assertIs(config.get(self.cfg, "stop_completion.continue_enabled"), False)
        self.assertEqual(config.get(self.cfg, "stop_completion.max_continues"), 2)
        self.assertIs(config.get(self.cfg, "jit_memory.enabled"), False)
        self.assertIs(config.get(self.cfg, "subagent_context.enabled"), False)
        self.assertEqual(config.get(self.cfg, "subagent_context.budget_chars"), 2000)

    def test_user_values_win_over_defaults(self):
        self.assertEqual(self.cfg["version"], "6.18.1")
        self.assertIs(config.get(self.cfg, "loop_mode.enabled"), False)
        self.assertIs(config.get(self.cfg, "workflow_enforcer_hook.strict_block"), True)

    def test_unknown_user_keys_preserved(self):
        # auto_update.last_check is runtime state stamped into the live file;
        # it is absent from DEFAULTS and must survive the merge untouched.
        self.assertIn("last_check", self.cfg["auto_update"])


class LoadMergeSemanticsTest(_ProjectDirMixin):
    def test_partial_block_keeps_sibling_defaults(self):
        self.write_config({"brief_hook": {"ambiguity_threshold": 0.7}})
        cfg = config.load(self.root)
        self.assertEqual(config.get(cfg, "brief_hook.ambiguity_threshold"), 0.7)
        self.assertEqual(config.get(cfg, "brief_hook.memory_budget_chars"), 1200)
        self.assertIs(config.get(cfg, "brief_hook.enabled"), True)

    def test_list_values_replace_not_merge(self):
        self.write_config({"read_guard_hook": {"allowlist": ["only-this.md"]}})
        cfg = config.load(self.root)
        self.assertEqual(config.get(cfg, "read_guard_hook.allowlist"), ["only-this.md"])

    def test_missing_file_returns_defaults(self):
        cfg = config.load(self.root)
        self.assertEqual(cfg, config.DEFAULTS)

    def test_corrupt_file_returns_defaults(self):
        self.write_config("{definitely not json")
        cfg = config.load(self.root)
        self.assertEqual(cfg, config.DEFAULTS)

    def test_non_object_json_returns_defaults(self):
        self.write_config("[1, 2, 3]")
        cfg = config.load(self.root)
        self.assertEqual(cfg, config.DEFAULTS)

    def test_load_returns_private_copy(self):
        cfg = config.load(self.root)
        cfg["task_mode"]["enabled"] = "MUTATED"
        cfg["new_key"] = True
        self.assertIs(config.DEFAULTS["task_mode"]["enabled"], True)
        self.assertNotIn("new_key", config.DEFAULTS)
        fresh = config.load(self.root)
        self.assertIs(config.get(fresh, "task_mode.enabled"), True)

    def test_defaults_never_mutated_by_merge(self):
        snapshot = copy.deepcopy(config.DEFAULTS)
        self.write_config({"tier1": {"enabled": True, "rules": {"greet": "hi"}}})
        cfg = config.load(self.root)
        self.assertIs(config.get(cfg, "tier1.enabled"), True)
        self.assertEqual(config.DEFAULTS, snapshot)


class LocalOverrideTest(_ProjectDirMixin):
    """GH-30: .agent/.nav-config.local.json merges last, over the shared file."""

    def write_local(self, obj_or_text):
        path = self.agent / ".nav-config.local.json"
        if isinstance(obj_or_text, str):
            path.write_text(obj_or_text, encoding="utf-8")
        else:
            path.write_text(json.dumps(obj_or_text, indent=2), encoding="utf-8")
        return path

    def test_local_key_overrides_shared(self):
        self.write_config({"judge": {"enabled": True, "model": "jev-latest"}})
        self.write_local({"judge": {"enabled": False}})
        cfg = config.load(self.root)
        self.assertIs(config.get(cfg, "judge.enabled"), False)
        self.assertEqual(config.get(cfg, "judge.model"), "jev-latest")  # sibling kept

    def test_absent_local_file_changes_nothing(self):
        self.write_config({"judge": {"enabled": True}})
        with_local_absent = config.load(self.root)
        self.assertIs(config.get(with_local_absent, "judge.enabled"), True)
        self.assertEqual(with_local_absent, config.load(self.root))

    def test_corrupt_local_file_is_ignored(self):
        self.write_config({"judge": {"enabled": True}})
        self.write_local("{nope")
        self.assertIs(config.get(config.load(self.root), "judge.enabled"), True)

    def test_local_only_over_defaults_when_shared_missing(self):
        self.write_local({"loop_mode": {"enabled": True}})
        self.assertIs(config.get(config.load(self.root), "loop_mode.enabled"), True)

    def test_local_relpath_constant(self):
        self.assertEqual(config.LOCAL_CONFIG_RELPATH, ".agent/.nav-config.local.json")


class GetDottedPathTest(unittest.TestCase):
    def setUp(self):
        self.cfg = {"a": {"b": {"c": 7, "n": None}}, "flat": "x"}

    def test_hit(self):
        self.assertEqual(config.get(self.cfg, "a.b.c"), 7)
        self.assertEqual(config.get(self.cfg, "flat"), "x")

    def test_none_leaf_is_returned_not_defaulted(self):
        self.assertIsNone(config.get(self.cfg, "a.b.n", default="fallback"))

    def test_missing_returns_default(self):
        self.assertEqual(config.get(self.cfg, "a.b.zzz", default=9), 9)
        self.assertIsNone(config.get(self.cfg, "nope.nope"))

    def test_traversal_through_scalar_returns_default(self):
        self.assertEqual(config.get(self.cfg, "flat.deeper", default="d"), "d")


class IsPilotExecutorTest(unittest.TestCase):
    def test_unset_is_false(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PILOT_EXECUTOR", None)
            self.assertFalse(config.is_pilot_executor())

    def test_empty_string_is_false(self):
        with mock.patch.dict(os.environ, {"PILOT_EXECUTOR": ""}):
            self.assertFalse(config.is_pilot_executor())

    def test_any_nonempty_value_is_true(self):
        for value in ("1", "true", "0"):  # v6 semantics: truthiness of the raw string
            with mock.patch.dict(os.environ, {"PILOT_EXECUTOR": value}):
                self.assertTrue(config.is_pilot_executor())


class StdlibPurityGuardTest(unittest.TestCase):
    """hooks/nav_hook_lib must be importable on any user Python: stdlib only.

    Globs the lib dir so modules added by other TASK-59 groups are swept
    automatically. Sibling lib modules (bare or relative imports) are allowed;
    anything else must be in sys.stdlib_module_names.
    """

    def test_lib_sources_import_stdlib_or_siblings_only(self):
        stdlib = set(getattr(sys, "stdlib_module_names", ()))
        self.assertTrue(stdlib, "needs Python 3.10+ (sys.stdlib_module_names)")
        siblings = {p.stem for p in LIB_DIR.glob("*.py")}
        allowed = stdlib | siblings | {"nav_hook_lib"}
        offenders = []
        for src in sorted(LIB_DIR.glob("*.py")):
            tree = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:  # relative import — sibling by construction
                        continue
                    names = [(node.module or "").split(".")[0]]
                else:
                    continue
                offenders.extend(
                    f"{src.name}:{node.lineno} imports non-stdlib '{name}'"
                    for name in names
                    if name and name not in allowed
                )
        self.assertEqual(offenders, [], "\n".join(offenders))


class PilotExecutorSinglePolicyPointTest(unittest.TestCase):
    """config.is_pilot_executor() is THE only PILOT_EXECUTOR read under hooks/.

    Widened from lib-only to ALL of hooks/**/*.py (TASK-59 audit gap): a new
    hook or op reading the env var directly would fork Pilot-executor policy.
    Test files are excluded: setting the env var in test setup is not a
    policy read.
    """

    # TASK-61 Phase 7: the v6 hooks are deleted; config.is_pilot_executor()
    # is the only PILOT_EXECUTOR read under hooks/. Keep empty.
    V6_HOOK_ALLOWLIST = frozenset()

    def test_no_pilot_executor_mentions_outside_config(self):
        hooks_dir = LIB_DIR.parent
        policy_point = LIB_DIR / "config.py"
        offenders = []
        for src in sorted(hooks_dir.rglob("*.py")):
            rel = src.relative_to(hooks_dir).as_posix()
            if src == policy_point or src.name.startswith("test_"):
                continue
            if rel in self.V6_HOOK_ALLOWLIST:
                continue
            for lineno, line in enumerate(
                src.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
            ):
                if "PILOT_EXECUTOR" in line:
                    offenders.append(f"{rel}:{lineno}: {line.strip()}")
        self.assertEqual(
            offenders, [],
            "PILOT_EXECUTOR must only be read via config.is_pilot_executor():\n"
            + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
