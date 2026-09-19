#!/usr/bin/env python3
"""Tests for hooks/ops/session_start.py (TASK-61 Phase 1).

Covers the op-level contract on top of the golden parity suite
(tests/golden/test_parity.py owns byte-parity with the recorded v6 doc):

  - injection body: sentinel + header + v6 section set/order;
  - resume branch: banner line + marker section hoisted to the top;
  - legacy state archival: the three v6 state files are COPIED to
    .agent/.nav-v6-state.bak/, sources never deleted, idempotent
    (first snapshot wins — a changed source never overwrites the archive);
  - .agent/.context-markers/ is read-only for this op (TASK-61 acceptance:
    user save-points are untouched);
  - char-budget truncation with the v6 footer;
  - non-Navigator root -> None (no output, no writes).

stdlib unittest only; run(ctx) is called in-process with a synthetic ctx.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))          # this dir
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # hooks/ (nav_hook_lib)

import session_start
from nav_hook_lib import config as nav_config

FIXED_NOW = 1_767_000_000.0

# Hermetic section set: no graph/auto_update/memories -> no subprocess spawns
# and no dependence on machine-local plugin installs.
HERMETIC_CONFIG = {
    "version": "6.18.1",
    "session_start_hook": {
        "enabled": True,
        "include_sections": ["navigator", "marker", "config", "profile", "tasks"],
        "char_budget": 9500,
    },
    "knowledge_graph": {"auto_surface_relevant": False},
}

LEGACY_BODIES = {
    ".nav-workflow-state.json": '{"check_shown": null}\n',
    ".nav-read-counter.json": '{"count": 4}\n',
    ".nav-profile-sync-state.json": '{"last_synced_count": 2}\n',
}

# Stub updater: records the argv it was called with under <plugin_dir>/argv.txt
# and emits a drift payload. parents[3] of the stub file == the plugin dir
# (plugin/skills/nav-start/functions/auto_updater.py). Ported from the v6
# suite (test_nav_session_start.py) — the read-only --check-drift contract.
STUB_DRIFT = (
    "import sys, json, pathlib\n"
    "pathlib.Path(__file__).resolve().parents[3].joinpath('argv.txt')"
    ".write_text(' '.join(sys.argv))\n"
    "print(json.dumps({'has_drift': True, 'plugin_version': '9.9.9',\n"
    "  'project_version': '1.0.0',\n"
    "  'message': 'Project config (v1.0.0) behind plugin (v9.9.9). Run nav-upgrade.'}))\n"
)

STUB_NO_DRIFT = "import json; print(json.dumps({'has_drift': False}))\n"

# Stub recall: records argv under <plugin_dir>/recall_argv.txt and emits two
# compact lines (plugin/skills/nav-graph/functions/memory_recall.py).
STUB_RECALL = (
    "import sys, pathlib\n"
    "pathlib.Path(__file__).resolve().parents[3].joinpath('recall_argv.txt')"
    ".write_text(' '.join(sys.argv))\n"
    "print('- PITFALL: \"Auth breaks session tests\" (90%)')\n"
    "print('- PATTERN: \"Unit before integration\" (85%)')\n"
)

STUB_RECALL_EMPTY = "pass\n"


class SessionStartOpTestBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.agent = self.root / ".agent"
        self.agent.mkdir()
        self._saved_env = {
            key: os.environ.pop(key, None)
            for key in ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DIR")
        }
        self.addCleanup(self._restore_env)
        self.write_config(HERMETIC_CONFIG)
        (self.agent / "DEVELOPMENT-README.md").write_text(
            "# Test Navigator Index\n\nDocs table here.\n", encoding="utf-8")
        tasks = self.agent / "tasks"
        tasks.mkdir()
        (tasks / "TASK-01-sample.md").write_text(
            "# TASK-01: Sample\n\n**Status**: In Progress\n", encoding="utf-8")

    def _restore_env(self):
        for key, value in self._saved_env.items():
            if value is not None:
                os.environ[key] = value

    def write_config(self, cfg_dict):
        path = self.agent / ".nav-config.json"
        path.write_text(json.dumps(cfg_dict, indent=2), encoding="utf-8")

    def make_ctx(self, source="startup", root=None):
        root = self.root if root is None else root
        payload = {
            "cwd": str(root),
            "session_id": "sess-op-tests",
            "hook_event_name": "SessionStart",
            "source": source,
        }
        return types.SimpleNamespace(
            event="SessionStart",
            payload=payload,
            config=nav_config.load(root),
            state={},
            pilot_executor=False,
            now=FIXED_NOW,
        )

    def run_op(self, **kwargs):
        return session_start.run(self.make_ctx(**kwargs))

    def write_legacy_files(self):
        for name, body in LEGACY_BODIES.items():
            (self.agent / name).write_text(body, encoding="utf-8")

    def snapshot_dir(self, path: Path) -> dict:
        return {
            child.name: child.read_bytes()
            for child in sorted(path.iterdir())
            if child.is_file()
        }


class InjectionBodyTest(SessionStartOpTestBase):
    def test_returns_additional_context_with_sentinel_and_sections(self):
        result = self.run_op()
        self.assertEqual(set(result), {"additional_context"})
        body = result["additional_context"]
        self.assertTrue(body.startswith(session_start.SENTINEL))
        self.assertIn("# Navigator Session Start", body)
        self.assertIn("_source: startup_", body)
        self.assertIn("## Navigator Config (.agent/.nav-config.json)", body)
        self.assertIn("## Open Tasks", body)
        self.assertIn("- `TASK-01-sample.md` — TASK-01: Sample [In Progress]", body)
        self.assertIn("## Navigator Index (.agent/DEVELOPMENT-README.md)", body)
        # v6 order: navigator (biggest) is last so truncation eats its tail.
        self.assertLess(body.index("## Open Tasks"), body.index("## Navigator Index"))

    def test_resume_adds_banner_and_hoists_marker_before_config(self):
        markers = self.agent / ".context-markers"
        markers.mkdir()
        (markers / ".active").write_text("m1.md\n", encoding="utf-8")
        (markers / "m1.md").write_text("marker body", encoding="utf-8")
        body = self.run_op(source="resume")["additional_context"]
        self.assertIn("**RESUMED FROM PREVIOUS SESSION** — prioritize active marker.", body)
        self.assertIn("_source: resume_", body)
        self.assertLess(body.index("## Active Marker: `m1.md`"),
                        body.index("## Navigator Config"))

    def test_startup_renders_marker_after_tasks(self):
        markers = self.agent / ".context-markers"
        markers.mkdir()
        (markers / ".active").write_text("m1.md\n", encoding="utf-8")
        (markers / "m1.md").write_text("marker body", encoding="utf-8")
        body = self.run_op()["additional_context"]
        self.assertLess(body.index("## Open Tasks"),
                        body.index("## Active Marker: `m1.md`"))

    def test_char_budget_truncates_with_v6_footer(self):
        cfg = json.loads(json.dumps(HERMETIC_CONFIG))
        cfg["session_start_hook"]["char_budget"] = 400
        self.write_config(cfg)
        body = self.run_op()["additional_context"]
        self.assertEqual(len(body), 400)
        self.assertTrue(body.endswith(session_start.TRUNCATION_FOOTER))

    def test_non_navigator_root_returns_none_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as other:
            other_root = Path(other).resolve()
            ctx = self.make_ctx(root=other_root)
            self.assertIsNone(session_start.run(ctx))
            self.assertEqual(list(other_root.iterdir()), [])


class LegacyStateArchivalTest(SessionStartOpTestBase):
    def test_archives_copies_and_never_deletes_sources(self):
        self.write_legacy_files()
        self.run_op()
        bak = self.agent / session_start.ARCHIVE_DIR_NAME
        for name, original_body in LEGACY_BODIES.items():
            source = self.agent / name
            self.assertTrue(source.is_file(), f"{name} source was deleted")
            self.assertEqual(source.read_text(encoding="utf-8"), original_body)
            self.assertEqual((bak / name).read_text(encoding="utf-8"), original_body)

    def test_archive_is_idempotent_first_snapshot_wins(self):
        self.write_legacy_files()
        self.run_op()
        changed = self.agent / ".nav-workflow-state.json"
        changed.write_text('{"check_shown": true}\n', encoding="utf-8")
        self.run_op()
        bak_copy = self.agent / session_start.ARCHIVE_DIR_NAME / ".nav-workflow-state.json"
        self.assertEqual(bak_copy.read_text(encoding="utf-8"),
                         LEGACY_BODIES[".nav-workflow-state.json"])

    def test_no_legacy_files_no_archive_dir(self):
        self.run_op()
        self.assertFalse((self.agent / session_start.ARCHIVE_DIR_NAME).exists())

    def test_context_markers_are_untouched(self):
        """TASK-61 acceptance: user save-points are never modified by archival."""
        markers = self.agent / ".context-markers"
        markers.mkdir()
        (markers / ".active").write_text("keep.md\n", encoding="utf-8")
        (markers / "keep.md").write_text("precious user save-point", encoding="utf-8")
        self.write_legacy_files()
        before = self.snapshot_dir(markers)
        self.run_op()
        self.assertEqual(self.snapshot_dir(markers), before)
        bak = self.agent / session_start.ARCHIVE_DIR_NAME
        self.assertEqual(
            sorted(child.name for child in bak.iterdir()),
            sorted(LEGACY_BODIES),
            "archive must hold exactly the three legacy state files",
        )


class SectionAutoUpdateTest(SessionStartOpTestBase):
    """Ported from v6 test_nav_session_start.py (wp5 / TASK-46).

    The auto-update section must run auto_updater READ-ONLY: `--check-drift`
    (version comparison only), never the mutating `claude plugin update` path.
    """

    def setUp(self):
        super().setUp()
        self.plugin_dir = self.root / "plugin"

    def _stub_updater(self, body: str) -> None:
        fn_dir = self.plugin_dir / "skills" / "nav-start" / "functions"
        fn_dir.mkdir(parents=True, exist_ok=True)
        (fn_dir / "auto_updater.py").write_text(body, encoding="utf-8")

    def test_drift_renders_section_in_read_only_mode(self):
        self._stub_updater(STUB_DRIFT)
        section = session_start._section_auto_update(self.root, self.plugin_dir)
        self.assertIsNotNone(section)
        self.assertIn("Auto-Update", section)
        self.assertIn("9.9.9", section)
        # Proves it ran read-only: --check-drift was passed (mutating mode
        # takes no args), along with the project --config-path.
        argv = (self.plugin_dir / "argv.txt").read_text()
        self.assertIn("--check-drift", argv)
        self.assertIn("--config-path", argv)

    def test_no_drift_returns_none(self):
        self._stub_updater(STUB_NO_DRIFT)
        self.assertIsNone(
            session_start._section_auto_update(self.root, self.plugin_dir))

    def test_missing_updater_returns_none(self):
        # plugin_dir exists but has no auto_updater.py.
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        self.assertIsNone(
            session_start._section_auto_update(self.root, self.plugin_dir))

    def test_plugin_dir_none_returns_none(self):
        self.assertIsNone(session_start._section_auto_update(self.root, None))

    def test_malformed_updater_output_returns_none(self):
        self._stub_updater("print('not json')\n")
        self.assertIsNone(
            session_start._section_auto_update(self.root, self.plugin_dir))


class SectionRelevantMemoriesTest(SessionStartOpTestBase):
    """Ported from v6 test_nav_session_start.py (v6.17.0 auto_surface_relevant)."""

    def setUp(self):
        super().setUp()
        self.plugin_dir = self.root / "plugin"
        knowledge = self.agent / "knowledge"
        knowledge.mkdir()
        (knowledge / "graph.json").write_text("{}", encoding="utf-8")

    def _stub_recall(self, body: str) -> None:
        fn_dir = self.plugin_dir / "skills" / "nav-graph" / "functions"
        fn_dir.mkdir(parents=True, exist_ok=True)
        (fn_dir / "memory_recall.py").write_text(body, encoding="utf-8")

    def test_section_renders_from_recall_output(self):
        self._stub_recall(STUB_RECALL)
        section = session_start._section_relevant_memories(
            self.root, self.plugin_dir, 5)
        self.assertIsNotNone(section)
        self.assertIn("## Relevant Memories", section)
        self.assertIn("Auth breaks session tests", section)
        # --auto mode with the configured limit and compact format.
        argv = (self.plugin_dir / "recall_argv.txt").read_text()
        self.assertIn("--auto", argv)
        self.assertIn("--limit 5", argv)
        self.assertIn("--format compact", argv)

    def test_limit_passthrough(self):
        self._stub_recall(STUB_RECALL)
        session_start._section_relevant_memories(self.root, self.plugin_dir, 3)
        argv = (self.plugin_dir / "recall_argv.txt").read_text()
        self.assertIn("--limit 3", argv)

    def test_empty_recall_output_returns_none(self):
        self._stub_recall(STUB_RECALL_EMPTY)
        self.assertIsNone(session_start._section_relevant_memories(
            self.root, self.plugin_dir, 5))

    def test_missing_graph_returns_none(self):
        (self.agent / "knowledge" / "graph.json").unlink()
        self._stub_recall(STUB_RECALL)
        self.assertIsNone(session_start._section_relevant_memories(
            self.root, self.plugin_dir, 5))

    def test_plugin_dir_none_or_missing_recall_returns_none(self):
        self.assertIsNone(
            session_start._section_relevant_memories(self.root, None, 5))
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        self.assertIsNone(session_start._section_relevant_memories(
            self.root, self.plugin_dir, 5))


class MemoriesGateAndOrderingTest(SessionStartOpTestBase):
    """Ported from v6 HookConfigMemoriesGateTest + PayloadOrderingTest.

    knowledge_graph.auto_surface_relevant gates the memories section (defaults
    on, limit 5); the section must precede navigator so truncation can't eat
    it; flag off never invokes recall.
    """

    def setUp(self):
        super().setUp()
        knowledge = self.agent / "knowledge"
        knowledge.mkdir()
        (knowledge / "graph.json").write_text("{}", encoding="utf-8")
        plugin = self.root / "plugin"
        fn_dir = plugin / "skills" / "nav-graph" / "functions"
        fn_dir.mkdir(parents=True)
        (fn_dir / "memory_recall.py").write_text(STUB_RECALL, encoding="utf-8")
        (plugin / "skills" / "nav-start").mkdir(parents=True)
        self.plugin_dir = plugin
        os.environ["CLAUDE_PLUGIN_ROOT"] = str(plugin)
        self.addCleanup(os.environ.pop, "CLAUDE_PLUGIN_ROOT", None)

    def _memories_config(self, knowledge_graph=None):
        cfg = {
            "version": "6.18.1",
            "session_start_hook": {
                "enabled": True,
                "include_sections": ["navigator", "config", "tasks"],
                "char_budget": 9500,
            },
        }
        if knowledge_graph is not None:
            cfg["knowledge_graph"] = knowledge_graph
        self.write_config(cfg)

    def test_defaults_surface_memories_with_limit_five(self):
        self._memories_config()  # no knowledge_graph block at all
        body = self.run_op()["additional_context"]
        self.assertIn("## Relevant Memories", body)
        argv = (self.plugin_dir / "recall_argv.txt").read_text()
        self.assertIn("--limit 5", argv)

    def test_max_memories_honored(self):
        self._memories_config({"max_session_memories": 2})
        self.run_op()
        argv = (self.plugin_dir / "recall_argv.txt").read_text()
        self.assertIn("--limit 2", argv)

    def test_memories_before_navigator(self):
        self._memories_config({"auto_surface_relevant": True})
        body = self.run_op()["additional_context"]
        self.assertIn("## Relevant Memories", body)
        self.assertLess(body.index("## Relevant Memories"),
                        body.index("## Navigator Index"))

    def test_flag_off_omits_section_and_never_invokes_recall(self):
        self._memories_config({"auto_surface_relevant": False})
        body = self.run_op()["additional_context"]
        self.assertNotIn("## Relevant Memories", body)
        self.assertFalse((self.plugin_dir / "recall_argv.txt").exists())


if __name__ == "__main__":
    unittest.main()


class SectionJudgeNoticeTest(SessionStartOpTestBase):
    """TASK-79: the config section names the judge key source, or warns (no secrets)."""

    def _config_with_judge(self, **judge_block):
        cfg = json.loads((self.agent / ".nav-config.json").read_text(encoding="utf-8"))
        cfg["judge"] = judge_block
        self.write_config(cfg)

    def test_no_judge_block_no_notice(self):
        body = self.run_op()["additional_context"]
        self.assertNotIn("Typed judge", body)

    def test_disabled_judge_no_notice(self):
        self._config_with_judge(enabled=False)
        body = self.run_op()["additional_context"]
        self.assertNotIn("Typed judge", body)

    def test_enabled_with_key_file_names_source_not_key(self):
        key_file = self.root / "judge.key"
        key_file.write_text("super-secret-key\n", encoding="utf-8")
        self._config_with_judge(enabled=True, api_key_env="NAV_TEST_NO_SUCH_ENV",
                                api_key_file=str(key_file))
        body = self.run_op()["additional_context"]
        self.assertIn(f"Typed judge: on (jev-latest, key from file:{key_file})", body)
        self.assertNotIn("super-secret-key", body)

    def test_enabled_without_key_warns_with_hint(self):
        self._config_with_judge(enabled=True, api_key_env="NAV_TEST_NO_SUCH_ENV",
                                api_key_file=str(self.root / "missing.key"))
        body = self.run_op()["additional_context"]
        self.assertIn("Typed judge is enabled but no API key was found", body)
        self.assertIn("console.typesafe.ai/keys", body)
        self.assertIn("--check", body)
