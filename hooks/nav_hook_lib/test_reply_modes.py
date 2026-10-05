#!/usr/bin/env python3
"""Tests for nav_hook_lib/reply_modes.py — the mode table, phrases, resolution, state.

Covers both rows (ADHD TASK-82, STE TASK-93) through the shared functions so a
new row only needs its own phrase/block assertions.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # hooks/

from nav_hook_lib import config, personal, reply_modes as rm  # noqa: E402

ADHD, STE = rm.by_key("adhd"), rm.by_key("ste")


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

    def cfg(self, adhd=None, ste=None, **blocks):
        c = copy.deepcopy(config.DEFAULTS)
        c["adhd_mode"]["on"] = adhd
        c["ste_mode"]["on"] = ste
        for key, value in blocks.items():
            c[key].update(value)
        return c


class TableTest(unittest.TestCase):
    def test_rows_are_unique_and_ordered_shape_before_sentence(self):
        self.assertEqual([m.key for m in rm.MODES], ["adhd", "ste"])
        for attr in ("key", "label", "config_key", "state_name", "rule_block"):
            values = [getattr(m, attr) for m in rm.MODES]
            self.assertEqual(len(values), len(set(values)), attr)
        self.assertIs(rm.by_config_key("ste_mode"), STE)
        self.assertIsNone(rm.by_key("terse"))

    def test_phrases_never_collide_across_modes(self):
        seen = set()
        for mode in rm.MODES:
            for phrases in (mode.on_phrases, mode.off_phrases, mode.status_phrases):
                self.assertFalse(seen & phrases, mode.key)
                seen |= phrases

    def test_every_block_is_compact_declarative_and_capped_in_total(self):
        total = 0
        for mode in rm.MODES:
            block = mode.rule_block
            total += len(block)
            self.assertTrue(block.startswith(f"{mode.label.upper()} MODE: on ("), mode.key)
            self.assertIn(f'"{mode.key} mode off" ends it', block)
            self.assertIn("replies only", block)
            self.assertNotIn("<!--", block)
            self.assertLess(len(block), 900, mode.key)
        self.assertLess(total, rm.MAX_TOTAL_BLOCK_CHARS)

    def test_adhd_block_keeps_its_v7_9_rules(self):
        for must in ("ONE next action", "deadline in bold", "at most 5", "step k of n",
                     "No preamble", "replies only"):
            self.assertIn(must, ADHD.rule_block)

    def test_ste_block_holds_the_part_1_subset_without_the_dictionary(self):
        for must in ("ASD-STE100", "20 words", "imperative", "active voice", "gerunds",
                     "noun clusters", "verbatim", "inside\nany reply-shape rules above"):
            self.assertIn(must, STE.rule_block)
        self.assertNotIn("dictionary", STE.rule_block)


class ClassifyTest(unittest.TestCase):
    def test_adhd_on_off_status_phrases(self):
        for text in ("adhd mode on", "ADHD Mode ON", "  enable adhd mode. ", "adhd on!",
                     "turn on ADHD mode", "adhd mode: on"):
            self.assertEqual(rm.classify(text), (ADHD, "on"), text)
        for text in ("adhd mode off", "stop adhd mode", "Disable ADHD mode", "adhd off"):
            self.assertEqual(rm.classify(text), (ADHD, "off"), text)
        for text in ("adhd mode", "adhd mode?", "ADHD status"):
            self.assertEqual(rm.classify(text), (ADHD, "status"), text)

    def test_ste_on_off_status_phrases(self):
        for text in ("ste mode on", "STE Mode ON", "use STE", "enable ste mode", "ste on"):
            self.assertEqual(rm.classify(text), (STE, "on"), text)
        for text in ("ste mode off", "stop STE", "stop ste mode", "ste off"):
            self.assertEqual(rm.classify(text), (STE, "off"), text)
        for text in ("ste mode", "ste mode?", "STE status"):
            self.assertEqual(rm.classify(text), (STE, "status"), text)

    def test_no_fuzzy_match(self):
        for text in ("please turn adhd mode on for me", "adhd mode on and fix the bug",
                     "I have ADHD", "mode on", "", None, "x" * 40 + " adhd mode on",
                     "use STE for the docs", "what is ASD-STE100", "ste"):
            self.assertIsNone(rm.classify(text), repr(text))


class ResolveTest(_Isolated):
    def test_default_off_for_every_mode(self):
        for mode in rm.MODES:
            self.assertEqual(rm.resolve(mode, self.cfg()), (False, "default"))
            self.assertEqual(rm.status_line(mode, self.cfg()), "")
        self.assertEqual(rm.status_lines(self.cfg()), [])
        self.assertEqual(rm.active_blocks(self.cfg()), [])
        self.assertIsNone(rm.injection(self.cfg()))

    def test_personal_switch_is_per_mode(self):
        self.assertTrue(rm.set_personal(STE, True, now=1_700_000_000.0))
        self.assertEqual(rm.resolve(STE, self.cfg()), (True, "personal"))
        self.assertEqual(rm.resolve(ADHD, self.cfg()), (False, "default"))
        data = json.loads((self.home / "ste-mode.json").read_text())
        self.assertEqual(data, {"on": True, "updated": "2023-11-14T22:13:20+00:00"})
        self.assertFalse((self.home / "adhd-mode.json").exists())
        self.assertIn("STE mode: on (personal switch", rm.status_line(STE, self.cfg()))
        rm.set_personal(STE, False)
        self.assertEqual(rm.resolve(STE, self.cfg()), (False, "personal"))

    def test_repo_pin_beats_personal(self):
        rm.set_personal(ADHD, True)
        self.assertEqual(rm.resolve(ADHD, self.cfg(adhd=False)), (False, "repo"))
        rm.set_personal(ADHD, False)
        self.assertEqual(rm.resolve(ADHD, self.cfg(adhd=True)), (True, "repo"))
        self.assertIn("pinned by repo config adhd_mode.on",
                      rm.status_line(ADHD, self.cfg(adhd=True)))
        self.assertIn("pinned by repo config ste_mode.on",
                      rm.status_line(STE, self.cfg(ste=False)))

    def test_corrupt_personal_file_reads_as_unset(self):
        (self.home / "adhd-mode.json").write_text('{"on": "yes"}', encoding="utf-8")
        self.assertIsNone(rm.personal_on(ADHD))
        self.assertEqual(rm.resolve(ADHD, self.cfg()), (False, "default"))

    def test_injection_is_table_order_with_a_blank_line_between(self):
        rm.set_personal(STE, True)
        self.assertEqual(rm.injection(self.cfg()), STE.rule_block)
        rm.set_personal(ADHD, True)
        self.assertEqual(rm.injection(self.cfg()),
                         ADHD.rule_block + "\n\n" + STE.rule_block)
        self.assertEqual(rm.injection(self.cfg(ste=False)), ADHD.rule_block)

    def test_status_lines_list_every_explicit_switch(self):
        rm.set_personal(ADHD, True)
        lines = rm.status_lines(self.cfg(ste=False))
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("ADHD mode: on (personal switch"))
        self.assertTrue(lines[1].startswith("STE mode: off (pinned by repo config"))

    def test_disabled_mode_is_invisible(self):
        rm.set_personal(STE, True)
        cfg = self.cfg(ste_mode={"enabled": False})
        self.assertFalse(rm.mode_enabled(STE, cfg))
        self.assertIsNone(rm.injection(cfg))
        self.assertEqual(rm.status_lines(cfg), [])


if __name__ == "__main__":
    unittest.main()
