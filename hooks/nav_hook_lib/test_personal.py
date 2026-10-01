#!/usr/bin/env python3
"""Tests for nav_hook_lib/personal.py — per-person settings files (TASK-82)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # hooks/

from nav_hook_lib import personal  # noqa: E402


class PersonalTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self._saved = {k: os.environ.pop(k, None)
                       for k in (personal.ENV_OVERRIDE, "XDG_CONFIG_HOME")}
        self.addCleanup(self._restore)
        os.environ[personal.ENV_OVERRIDE] = str(self.home)

    def _restore(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_env_override_wins(self):
        self.assertEqual(personal.config_home(), self.home)
        self.assertEqual(personal.path("x"), self.home / "x.json")

    def test_xdg_then_home_fallback(self):
        os.environ.pop(personal.ENV_OVERRIDE)
        os.environ["XDG_CONFIG_HOME"] = str(self.home / "xdg")
        self.assertEqual(personal.config_home(), self.home / "xdg" / "navigator")
        os.environ.pop("XDG_CONFIG_HOME")
        self.assertEqual(personal.config_home(), Path.home() / ".config" / "navigator")

    def test_missing_corrupt_and_non_object_read_as_empty(self):
        self.assertEqual(personal.read("nothing"), {})
        (self.home / "bad.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(personal.read("bad"), {})
        (self.home / "list.json").write_text("[1, 2]", encoding="utf-8")
        self.assertEqual(personal.read("list"), {})

    def test_write_creates_dir_and_round_trips(self):
        target = self.home / "deeper"
        os.environ[personal.ENV_OVERRIDE] = str(target)
        self.assertTrue(personal.write("s", {"on": True, "n": 1}))
        self.assertEqual(json.loads((target / "s.json").read_text()), {"on": True, "n": 1})
        self.assertEqual(personal.read("s"), {"on": True, "n": 1})
        self.assertFalse(list(target.glob(".*.tmp")), "tmp file left behind")


if __name__ == "__main__":
    unittest.main()
