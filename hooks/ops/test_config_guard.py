#!/usr/bin/env python3
"""Tests for ops/config_guard.py — TASK-62 Phase 5 (ConfigChange).

Covers: invalid-JSON warning with parse position, non-object top level,
missing/empty/valid config silence, no payload echo (mem-034), and the
dispatch-level contract for the ConfigChange event (validate-or-drop KEPT
the registration on CC 2.1.205): systemMessage doc, off-switch honored,
Pilot passthrough (non-blocking output flows).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))          # this dir
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # hooks/ (nav_hook_lib)

import config_guard
from nav_hook_lib import config

HOOKS_DIR = Path(__file__).resolve().parent.parent
DISPATCH = str(HOOKS_DIR / "nav_dispatch.py")
SESSION_ID = "sess-config-guard-tests"
NOW = 1_700_000_000.0


class ConfigGuardBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(os.path.realpath(self._tmp.name)) / "project"
        self.agent = self.root / ".agent"
        self.agent.mkdir(parents=True)
        self.config_path = self.agent / ".nav-config.json"

    def ctx(self, payload_extra=None):
        payload = {"cwd": str(self.root), "session_id": SESSION_ID}
        if payload_extra:
            payload.update(payload_extra)
        return types.SimpleNamespace(
            event="ConfigChange",
            payload=payload,
            config=config.load(self.root),
            state={},
            pilot_executor=False,
            now=NOW,
        )


class ValidationTest(ConfigGuardBase):
    def test_invalid_json_warns_with_parse_position(self):
        self.config_path.write_text('{\n  "version": 6.18.1,\n}\n', encoding="utf-8")
        result = config_guard.run(self.ctx())
        message = result["system_message"]
        self.assertIn(".agent/.nav-config.json", message)
        self.assertIn("line 2", message)
        self.assertIn("built-in defaults", message)

    def test_non_object_top_level_warns(self):
        self.config_path.write_text('["not", "an", "object"]\n', encoding="utf-8")
        result = config_guard.run(self.ctx())
        self.assertIn("top level is list", result["system_message"])

    def test_valid_config_is_silent(self):
        self.config_path.write_text('{"version": "6.18.1"}\n', encoding="utf-8")
        self.assertIsNone(config_guard.run(self.ctx()))

    def test_missing_config_is_silent(self):
        self.assertIsNone(config_guard.run(self.ctx()))

    def test_empty_config_file_is_silent(self):
        self.config_path.write_text("  \n", encoding="utf-8")
        self.assertIsNone(config_guard.run(self.ctx()))

    def test_invalid_local_override_warns_and_names_the_file(self):
        """GH-30: a broken personal override is caught like the shared file."""
        self.config_path.write_text('{"version": "7.7.1"}', encoding="utf-8")
        (self.agent / ".nav-config.local.json").write_text("{nope", encoding="utf-8")
        result = config_guard.run(self.ctx())
        self.assertIsNotNone(result)
        self.assertIn(".nav-config.local.json", result["system_message"])
        self.assertIn("personal overrides", result["system_message"])

    def test_valid_local_override_is_silent(self):
        self.config_path.write_text('{"version": "7.7.1"}', encoding="utf-8")
        (self.agent / ".nav-config.local.json").write_text('{"judge": {"enabled": false}}',
                                                          encoding="utf-8")
        self.assertIsNone(config_guard.run(self.ctx()))

    def test_warning_never_echoes_payload_text(self):
        self.config_path.write_text("{broken", encoding="utf-8")
        result = config_guard.run(self.ctx(
            {"prompt": "SECRET-TRIGGER-2ac8 run until done"}))
        self.assertNotIn("SECRET-TRIGGER-2ac8", result["system_message"])


class DispatchContractTest(ConfigGuardBase):
    """TASK-45 subprocess pattern against the live ConfigChange route."""

    def dispatch(self, env_extra=None):
        env = os.environ.copy()
        for key in ("PILOT_EXECUTOR", "CLAUDE_PROJECT_DIR", "CLAUDE_USER_MESSAGE"):
            env.pop(key, None)
        if env_extra:
            env.update(env_extra)
        payload = {"cwd": str(self.root), "session_id": SESSION_ID}
        return subprocess.run(
            [sys.executable, DISPATCH, "ConfigChange"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=str(self.root),
            env=env,
            timeout=30,
        )

    def test_invalid_config_emits_system_message_doc(self):
        self.config_path.write_text("{broken json", encoding="utf-8")
        proc = self.dispatch()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        doc = json.loads(proc.stdout)
        self.assertIn("built-in defaults", doc["systemMessage"])

    def test_valid_config_is_silent_through_dispatch(self):
        self.config_path.write_text('{"version": "6.18.1"}\n', encoding="utf-8")
        proc = self.dispatch()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("systemMessage", proc.stdout)

    def test_off_switch_silences_the_warning(self):
        # A BROKEN config cannot carry its own toggle (it does not parse), so
        # the off-switch case uses a VALID config whose guard block is off and
        # asserts overall silence — the gate must skip the op cleanly.
        self.config_path.write_text(
            json.dumps({"config_guard": {"enabled": False}}), encoding="utf-8")
        proc = self.dispatch()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("systemMessage", proc.stdout)

    def test_pilot_executor_still_surfaces_the_warning(self):
        # Non-blocking output flows under Pilot (runtime belt strips only
        # blocking keys) — a broken config is MORE dangerous unattended.
        self.config_path.write_text("{broken json", encoding="utf-8")
        proc = self.dispatch(env_extra={"PILOT_EXECUTOR": "1"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        doc = json.loads(proc.stdout)
        self.assertIn("built-in defaults", doc["systemMessage"])


if __name__ == "__main__":
    unittest.main()
