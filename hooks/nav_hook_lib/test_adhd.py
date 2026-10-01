#!/usr/bin/env python3
"""Tests for nav_hook_lib/adhd.py — phrases, resolution order, state (TASK-82)."""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # hooks/

from nav_hook_lib import adhd, config, personal  # noqa: E402


class _Isolated(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self._saved = os.environ.pop(personal.ENV_OVERRIDE, None)
        os.environ[personal.ENV_OVERRIDE] = str(self.home)
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop(personal.ENV_OVERRIDE, None)
        else:
            os.environ[personal.ENV_OVERRIDE] = self._saved

    def cfg(self, on=None):
        c = copy.deepcopy(config.DEFAULTS)
        c["adhd_mode"]["on"] = on
        return c


class ClassifyTest(unittest.TestCase):
    def test_on_off_status_phrases(self):
        for text in ("adhd mode on", "ADHD Mode ON", "  enable adhd mode. ", "adhd on!",
                     "turn on ADHD mode", "adhd mode: on"):
            self.assertEqual(adhd.classify(text), "on", text)
        for text in ("adhd mode off", "stop adhd mode", "Disable ADHD mode", "adhd off"):
            self.assertEqual(adhd.classify(text), "off", text)
        for text in ("adhd mode", "adhd mode?", "ADHD status"):
            self.assertEqual(adhd.classify(text), "status", text)

    def test_no_fuzzy_match(self):
        for text in ("please turn adhd mode on for me", "adhd mode on and fix the bug",
                     "I have ADHD", "mode on", "", None, "x" * 40 + " adhd mode on"):
            self.assertIsNone(adhd.classify(text), repr(text))


class ResolveTest(_Isolated):
    def test_default_off(self):
        self.assertEqual(adhd.resolve(self.cfg()), (False, "default"))
        self.assertEqual(adhd.status_line(self.cfg()), "")

    def test_personal_switch(self):
        self.assertTrue(adhd.set_personal(True, now=1_700_000_000.0))
        self.assertEqual(adhd.resolve(self.cfg()), (True, "personal"))
        data = json.loads((self.home / "adhd-mode.json").read_text())
        self.assertEqual(data, {"on": True, "updated": "2023-11-14T22:13:20+00:00"})
        self.assertIn("ADHD mode: on (personal switch", adhd.status_line(self.cfg()))
        adhd.set_personal(False)
        self.assertEqual(adhd.resolve(self.cfg()), (False, "personal"))

    def test_repo_pin_beats_personal(self):
        adhd.set_personal(True)
        self.assertEqual(adhd.resolve(self.cfg(on=False)), (False, "repo"))
        adhd.set_personal(False)
        self.assertEqual(adhd.resolve(self.cfg(on=True)), (True, "repo"))
        self.assertIn("pinned by repo config", adhd.status_line(self.cfg(on=True)))

    def test_corrupt_personal_file_reads_as_unset(self):
        (self.home / "adhd-mode.json").write_text('{"on": "yes"}', encoding="utf-8")
        self.assertIsNone(adhd.personal_on())
        self.assertEqual(adhd.resolve(self.cfg()), (False, "default"))


class RuleBlockTest(unittest.TestCase):
    def test_block_is_compact_and_declarative(self):
        self.assertLess(len(adhd.RULE_BLOCK), 900)
        self.assertTrue(adhd.RULE_BLOCK.startswith("ADHD MODE: on"))
        for must in ("ONE next action", "deadline in bold", "at most 5", "step k of n",
                     "No preamble", "replies only"):
            self.assertIn(must, adhd.RULE_BLOCK)
        self.assertNotIn("<!--", adhd.RULE_BLOCK)


if __name__ == "__main__":
    unittest.main()
