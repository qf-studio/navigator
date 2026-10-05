#!/usr/bin/env python3
"""Tests for hooks/ops/compact_marker.py (TASK-61 Phase 2).

Covers the op-level contract on top of the golden parity suite
(tests/golden/test_parity.py owns the `{}` byte-parity for both events):

  - PreCompact: marker file + .active pointer written, v6 header/section
    shape, trigger normalization, config toggles, char-budget truncation,
    ack result;
  - PostCompact: append branch, missing-.active no-op branch,
    append_post_compact_summary toggle, dict-summary serialization;
  - both branches return {"ack": True} (the runtime turns that into the
    bare `{}` doc v6 printed); unknown events return None.

stdlib unittest only; run(ctx) is called in-process with a synthetic ctx.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))          # this dir
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # hooks/ (nav_hook_lib)

import compact_marker
import session_start
from nav_hook_lib import config as nav_config

FIXED_NOW = 1_767_000_000.0
SESSION_ID = "sess-compact-tests"

FILES_HEADER = "**Files/paths mentioned**:\n"
SECTION_DIVIDER = "\n\n---\n\n"


class CompactMarkerTestBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.agent = self.root / ".agent"
        self.agent.mkdir()
        self.markers = self.agent / ".context-markers"
        self._saved_env = {
            key: os.environ.pop(key, None) for key in ("CLAUDE_PROJECT_DIR",)
        }
        self.addCleanup(self._restore_env)
        self.transcript = self.root / "transcript.jsonl"
        self.transcript.write_text(
            json.dumps({"message": {"role": "user", "content": "please fix hooks/foo.py"}})
            + "\n"
            + json.dumps({"message": {"role": "assistant",
                                      "content": [{"type": "text", "text": "done"}]}})
            + "\n",
            encoding="utf-8",
        )

    def _restore_env(self):
        for key, value in self._saved_env.items():
            if value is not None:
                os.environ[key] = value

    def write_config(self, cfg_dict):
        path = self.agent / ".nav-config.json"
        path.write_text(json.dumps(cfg_dict, indent=2), encoding="utf-8")

    def make_ctx(self, event, **payload_extra):
        payload = {
            "cwd": str(self.root),
            "session_id": SESSION_ID,
            "transcript_path": str(self.transcript),
            "hook_event_name": event,
        }
        payload.update(payload_extra)
        return types.SimpleNamespace(
            event=event,
            payload=payload,
            config=nav_config.load(self.root),
            state={},
            pilot_executor=False,
            now=FIXED_NOW,
        )

    def run_pre(self, **payload_extra):
        payload = {"trigger": "manual", "custom_instructions": ""}
        payload.update(payload_extra)
        return compact_marker.run(self.make_ctx("PreCompact", **payload))

    def run_post(self, **payload_extra):
        return compact_marker.run(self.make_ctx("PostCompact", **payload_extra))

    def marker_files(self):
        if not self.markers.is_dir():
            return []
        return sorted(p.name for p in self.markers.iterdir() if p.name != ".active")

    def expected_stamp(self):
        return datetime.fromtimestamp(FIXED_NOW).strftime("%Y-%m-%d-%H%M")


class PreCompactTest(CompactMarkerTestBase):
    def test_writes_marker_and_active_pointer_and_acks(self):
        result = self.run_pre()
        self.assertEqual(result, {"ack": True})
        expected_name = f"before-compact-manual-{self.expected_stamp()}.md"
        self.assertEqual(self.marker_files(), [expected_name])
        active = (self.markers / ".active").read_text(encoding="utf-8")
        self.assertEqual(active, expected_name + "\n")
        body = (self.markers / expected_name).read_text(encoding="utf-8")
        self.assertIn("# Before Compact (manual)", body)
        self.assertIn("**Trigger**: `manual` (user ran /compact)", body)
        self.assertIn(f"**Session**: `{SESSION_ID}`", body)
        self.assertIn("## Git State", body)
        self.assertIn("## Conversation Summary (heuristic)", body)
        self.assertIn("hooks/foo.py", body)  # path token survived compression

    def test_auto_trigger_named_and_described(self):
        self.run_pre(trigger="auto")
        expected_name = f"before-compact-auto-{self.expected_stamp()}.md"
        self.assertEqual(self.marker_files(), [expected_name])
        body = (self.markers / expected_name).read_text(encoding="utf-8")
        self.assertIn("**Trigger**: `auto` (Claude Code auto-compacted)", body)

    def test_unknown_trigger_normalized_to_manual(self):
        self.run_pre(trigger="weird")
        expected_name = f"before-compact-manual-{self.expected_stamp()}.md"
        self.assertEqual(self.marker_files(), [expected_name])

    def test_config_toggles_drop_git_and_transcript_sections(self):
        self.write_config({"compact_hook": {
            "include_git_state": False,
            "include_transcript_summary": False,
        }})
        self.run_pre()
        body = (self.markers / self.marker_files()[0]).read_text(encoding="utf-8")
        self.assertNotIn("## Git State", body)
        self.assertNotIn("## Conversation Summary (heuristic)", body)
        self.assertIn("# Before Compact (manual)", body)

    def test_missing_transcript_path_uses_v6_placeholder(self):
        ctx = self.make_ctx("PreCompact", trigger="manual")
        del ctx.payload["transcript_path"]
        self.assertEqual(compact_marker.run(ctx), {"ack": True})
        body = (self.markers / self.marker_files()[0]).read_text(encoding="utf-8")
        self.assertIn("_[transcript_path not provided]_", body)

    def test_char_budget_truncates_marker_body(self):
        # Header alone (~250 chars) overflows a 200-char budget once the
        # git/transcript sections are toggled off — v6 tail truncation kicks in.
        self.write_config({"compact_hook": {
            "char_budget": 200,
            "include_git_state": False,
            "include_transcript_summary": False,
        }})
        self.run_pre()
        body = (self.markers / self.marker_files()[0]).read_text(encoding="utf-8")
        self.assertLessEqual(len(body), 200)
        self.assertTrue(body.endswith("[... truncated to char budget ...]\n"))


class PostCompactTest(CompactMarkerTestBase):
    def seed_marker(self, name="before-compact-manual-2026-07-10-1200.md"):
        self.markers.mkdir(parents=True)
        (self.markers / name).write_text("# Before Compact (manual)\n", encoding="utf-8")
        (self.markers / ".active").write_text(name + "\n", encoding="utf-8")
        return self.markers / name

    def test_no_active_pointer_acks_without_writing(self):
        result = self.run_post(compact_summary="never used")
        self.assertEqual(result, {"ack": True})
        self.assertFalse(self.markers.exists())

    def test_appends_summary_section_to_active_marker(self):
        marker = self.seed_marker()
        result = self.run_post(compact_summary="Session summary text.")
        self.assertEqual(result, {"ack": True})
        body = marker.read_text(encoding="utf-8")
        self.assertIn("## Compact Summary (Claude Code)", body)
        self.assertIn("_Appended by PostCompact hook at ", body)
        self.assertTrue(body.endswith("Session summary text.\n"))

    def test_missing_summary_uses_v6_placeholder(self):
        marker = self.seed_marker()
        self.run_post()
        self.assertIn(compact_marker.NO_SUMMARY_PLACEHOLDER,
                      marker.read_text(encoding="utf-8"))

    def test_dict_summary_serialized_as_indented_json(self):
        marker = self.seed_marker()
        self.run_post(compact_summary={"files": ["a.py"]})
        body = marker.read_text(encoding="utf-8")
        self.assertIn('"files": [\n    "a.py"\n  ]', body)

    def test_append_flag_off_acks_without_writing(self):
        marker = self.seed_marker()
        before = marker.read_text(encoding="utf-8")
        self.write_config({"compact_hook": {"append_post_compact_summary": False}})
        result = self.run_post(compact_summary="ignored")
        self.assertEqual(result, {"ack": True})
        self.assertEqual(marker.read_text(encoding="utf-8"), before)

    def test_stale_active_pointer_acks_without_crash(self):
        self.markers.mkdir(parents=True)
        (self.markers / ".active").write_text("gone.md\n", encoding="utf-8")
        self.assertEqual(self.run_post(compact_summary="x"), {"ack": True})
        self.assertEqual(self.marker_files(), [])


class CompressContextTest(unittest.TestCase):
    """Ported from v6 test_nav_pre_compact.py (wp5 / TASK-46).

    Path detection must be path-SHAPED (a real path token, not prose that
    merely mentions an extension), and sampling must cover both the head and
    tail of a long transcript — not the tail alone.
    """

    def _files_listed(self, text: str) -> list:
        """Return the lines of the Files/paths section (empty if absent)."""
        out = compact_marker._compress_context(text)
        if FILES_HEADER not in out:
            return []
        section = out.split(FILES_HEADER, 1)[1].split(SECTION_DIVIDER, 1)[0]
        return [ln for ln in section.splitlines() if ln.strip()]

    def test_prose_extension_not_captured(self):
        # A bare ".py"/".md" preceded by whitespace is prose, not a path.
        files = self._files_listed("Let's see the .py docs and the .md guide.")
        self.assertEqual(files, [])

    def test_real_path_captured(self):
        files = self._files_listed("I edited hooks/token_monitor.py to fix it.")
        self.assertIn("hooks/token_monitor.py", files)

    def test_captured_token_is_clean(self):
        # Trailing ":140" / ":" must not glue onto the captured path token.
        files = self._files_listed("ran hooks/token_monitor.py:140 just now")
        self.assertIn("hooks/token_monitor.py", files)
        self.assertNotIn("hooks/token_monitor.py:140", files)

    def test_head_and_tail_both_sampled(self):
        # >200 lines: a path near the start AND one near the end must survive.
        head_path = "src/early_module.py"
        tail_path = "src/late_module.py"
        lines = ([f"touched {head_path}"] + ["filler"] * 300
                 + [f"touched {tail_path}"])
        files = self._files_listed("\n".join(lines))
        self.assertIn(head_path, files)
        self.assertIn(tail_path, files)

    def test_empty_transcript(self):
        self.assertEqual(compact_marker._compress_context(""),
                         "_[transcript unavailable]_")


class CompactRoundTripTest(CompactMarkerTestBase):
    """Ported from v6 test_compact_roundtrip.py: the PreCompact marker feeds
    PostCompact and the session_start active-marker section on one project."""

    def test_pre_post_session_start_chain(self):
        self.assertEqual(self.run_pre(), {"ack": True})
        name = (self.markers / ".active").read_text(encoding="utf-8").strip()
        marker = self.markers / name
        self.assertTrue(name.startswith("before-compact-manual-"))
        self.assertTrue(name.endswith(".md"))
        before = marker.read_text(encoding="utf-8")
        self.assertNotIn("## Compact Summary (Claude Code)", before)

        result = self.run_post(compact_summary="SUMMARY-SENTINEL-12345")
        self.assertEqual(result, {"ack": True})
        after = marker.read_text(encoding="utf-8")
        self.assertIn("## Compact Summary (Claude Code)", after)
        self.assertIn("SUMMARY-SENTINEL-12345", after)

        section = session_start._section_active_marker(self.root)
        self.assertIsNotNone(section, "active-marker section returned None")
        self.assertIn(name, section)
        self.assertIn("## Active Marker", section)


class EventBranchingTest(CompactMarkerTestBase):
    def test_unknown_event_returns_none(self):
        self.assertIsNone(compact_marker.run(self.make_ctx("Stop")))
        self.assertFalse(self.markers.exists())

    def test_non_navigator_root_returns_none(self):
        with tempfile.TemporaryDirectory() as other:
            ctx = self.make_ctx("PreCompact")
            ctx.payload["cwd"] = str(Path(other).resolve())
            self.assertIsNone(compact_marker.run(ctx))


class InProgressPredicateTests(unittest.TestCase):
    """TASK-91: the Status line decides; prose mentions elsewhere do not."""

    def test_status_line_forms(self):
        for text in (
            "# T\n\n**Status**: 🚧 In Progress\n",
            "# T\n\n**Status:** 🚧 Shipping\n",
            "# T\n\n**Status**: In Progress\n",
            "# T\n\n> Status: in-progress\n",
        ):
            self.assertTrue(compact_marker.is_in_progress(text), text)

    def test_finished_doc_quoting_the_phrase_is_not_in_progress(self):
        text = (
            "# TASK-67: Vocabulary\n\n**Status**: ✅ Implemented\n\n"
            "Plain `**Status**: In Progress` lines were recorded as 🚧 unknown.\n"
        )
        self.assertFalse(compact_marker.is_in_progress(text))

    def test_other_status_values(self):
        for text in ("**Status**: ✅ Implemented\n", "**Status**: Design\n", "**Status**: Blocked\n"):
            self.assertFalse(compact_marker.is_in_progress(text), text)

    def test_no_status_line_keeps_legacy_head_scan(self):
        self.assertTrue(compact_marker.is_in_progress("# Six in progress\n"))
        self.assertTrue(compact_marker.is_in_progress("no heading, in-progress soon\n"))
        self.assertFalse(compact_marker.is_in_progress("# Done\n"))

    def test_active_task_hint_skips_prose_only_doc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tasks = root / ".agent" / "tasks"
            tasks.mkdir(parents=True)
            (tasks / "TASK-01-done.md").write_text(
                "# TASK-01: Done\n\n**Status**: ✅ Implemented\n\nwas in progress once\n"
            )
            (tasks / "TASK-02-live.md").write_text("# TASK-02: Live\n\n**Status**: 🚧 In Progress\n")
            hint = compact_marker._active_task_hint(root)
            self.assertEqual(hint, "**In-progress tasks**:\n- `TASK-02-live.md` — TASK-02: Live")


if __name__ == "__main__":
    unittest.main()
