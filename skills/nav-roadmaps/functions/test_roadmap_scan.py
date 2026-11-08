#!/usr/bin/env python3
"""Unit tests for roadmap_scan.py — discovery, kind, dates, ticket counts, rendering."""
from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

import roadmap_scan as rs

TODAY = dt.date(2026, 11, 8)

TICKETS = """---
name: tickets
---

# Cloud roadmap — tickets per project (2026-10-21)

## Status Legend
| ✅ | merged |
| 📋 | not filed |

## console — 3
| ID | Title | Status |
|---|---|---|
| C1 | thing | ✅ merged (PR#1) |
| C2 | thing | 🎫 #40 |
| C3 | thing | 📋 |

## daemon — 2
| ID | Title | Status |
|---|---|---|
| P1 | thing | 🚧 running |
| P2 | thing | ✅ |
"""

EXEC_TASK = """# TASK-584: Cloud — complete execution roadmap (phases A–H)

**Status**: 🚀 **11-04: PADDLE ON.** Nelya said so.
**Created**: 2026-10-22
"""

FALSE_POSITIVE_TASK = """# TASK-647: Research page events (pilot#5810, roadmap P17 / U9)

**Status**: 🚀 A1 dispatched 2026-11-08
"""

HISTORICAL = """# Roadmap: SaaS Build (TASK-405 Program)

> **2026-11-02 note — historical doc (S0–S4 era).** See TASK-584.

**Source plan**: `.agent/tasks/TASK-405-platform.md` + `arch.md`
**As of**: 2026-07-23 night — S0 ✅
"""

PROGRAM = """# TASK-405: Platform

**Created**: 2026-07-13 · **Status**: ✅ **S3 EXIT MET** passed 2026-08-18
"""

STUB = """# Roadmap: SaaS Build (TASK-405 Program)

**Moved 2026-11-08** to the private repo.
"""

ARCHIVED = """# Roadmap: old thing

**Status**: done 2026-01-01
"""


class RoadmapScanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name) / ".agent"
        (root / "system" / "project").mkdir(parents=True)
        (root / "tasks" / "archive").mkdir(parents=True)
        (root / ".context-markers").mkdir()
        (root / "system" / "project" / "project_roadmap_tickets.md").write_text(TICKETS)
        (root / "tasks" / "TASK-584-execution-roadmap.md").write_text(EXEC_TASK)
        (root / "tasks" / "TASK-647-events.md").write_text(FALSE_POSITIVE_TASK)
        (root / "system" / "saas-roadmap.md").write_text(HISTORICAL)
        (root / "tasks" / "TASK-405-platform.md").write_text(PROGRAM)
        (root / "tasks" / "archive" / "old-roadmap.md").write_text(ARCHIVED)
        (root / ".context-markers" / "2026-11-08-roadmap-marker.md").write_text("# marker roadmap")
        self.root = root
        self.docs = rs.scan_root(root, TODAY, 30, 110)
        self.by_path = {d["path"]: d for d in self.docs}

    def tearDown(self):
        self.tmp.cleanup()

    def test_discovery_skips_archive_markers_and_parenthesised_mentions(self):
        paths = set(self.by_path)
        self.assertEqual(
            paths,
            {
                "system/project/project_roadmap_tickets.md",
                "tasks/TASK-584-execution-roadmap.md",
                "system/saas-roadmap.md",
                "tasks/TASK-405-platform.md",
            },
        )

    def test_kinds(self):
        self.assertEqual(self.by_path["system/saas-roadmap.md"]["kind"], "historical")
        self.assertEqual(self.by_path["tasks/TASK-405-platform.md"]["kind"], "program")
        self.assertEqual(self.by_path["tasks/TASK-584-execution-roadmap.md"]["kind"], "live")
        self.assertEqual(self.by_path["system/project/project_roadmap_tickets.md"]["kind"], "live")

    def test_stub_kind(self):
        stub_root = Path(self.tmp.name) / "other" / ".agent" / "system"
        stub_root.mkdir(parents=True)
        (stub_root / "saas-roadmap.md").write_text(STUB)
        docs = rs.scan_root(stub_root.parent, TODAY, 30, 110)
        self.assertEqual(docs[0]["kind"], "stub")
        self.assertEqual(docs[0]["tickets"], [])

    def test_short_date_in_status_line_wins_over_created(self):
        d = self.by_path["tasks/TASK-584-execution-roadmap.md"]
        self.assertEqual(d["last_date"], "2026-11-04")
        self.assertFalse(d["stale"])

    def test_short_date_in_the_future_rolls_back_a_year(self):
        self.assertEqual(rs._last_date(["**Status**: 12-25 party"], TODAY), "2025-12-25")

    def test_status_excerpt_is_plain_and_bounded(self):
        d = self.by_path["tasks/TASK-584-execution-roadmap.md"]
        self.assertTrue(d["status"].startswith("🚀 11-04: PADDLE ON."))
        self.assertNotIn("**", d["status"])
        long = rs._status(["**Status**: " + "x" * 500], 40)
        self.assertEqual(len(long), 40)
        self.assertTrue(long.endswith("…"))

    def test_as_of_counts_as_status(self):
        self.assertTrue(self.by_path["system/saas-roadmap.md"]["status"].startswith("2026-07-23 night"))

    def test_ticket_counts_per_section_skip_legend(self):
        t = self.by_path["system/project/project_roadmap_tickets.md"]["tickets"]
        self.assertEqual([s["section"] for s in t], ["console — 3", "daemon — 2"])
        console, daemon = t
        self.assertEqual((console["rows"], console["merged"], console["filed"], console["not_filed"]), (3, 1, 1, 1))
        self.assertEqual((daemon["rows"], daemon["in_flight"], daemon["merged"]), (2, 1, 1))

    def test_stale_is_only_for_live_docs(self):
        program = self.by_path["tasks/TASK-405-platform.md"]
        self.assertEqual(program["last_date"], "2026-08-18")
        self.assertFalse(program["stale"])
        old = rs.scan_root(self.root, dt.date(2027, 6, 1), 30, 110)
        live_stale = [d for d in old if d["stale"]]
        self.assertTrue(live_stale)
        self.assertTrue(all(d["kind"] == "live" for d in live_stale))

    def test_render_md_has_both_tables_and_sorted_kinds(self):
        md = rs.render_md([self.root], self.docs, TODAY)
        self.assertIn("| # | Roadmap | Path | Kind | Last date | Status |", md)
        self.assertIn("### Tickets — Cloud roadmap — tickets per project (2026-10-21)", md)
        self.assertIn("| **Total** | 5 | 2 | 1 | 1 | 1 |", md)
        kinds = [d["kind"] for d in self.docs]
        self.assertEqual(kinds, sorted(kinds, key=lambda k: {"live": 0, "program": 1, "historical": 2, "stub": 3}[k]))

    def test_render_multi_root_prefixes_repo_label(self):
        other = Path(self.tmp.name) / "repo-b" / ".agent" / "system"
        other.mkdir(parents=True)
        (other / "x-roadmap.md").write_text("# X roadmap\n\n**Status**: open 2026-11-01\n")
        docs = self.docs + rs.scan_root(other.parent, TODAY, 30, 110)
        md = rs.render_md([self.root, other.parent], docs, TODAY)
        self.assertIn("`repo-b: system/x-roadmap.md`", md)

    def test_empty_root(self):
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        self.assertEqual(rs.scan_root(empty, TODAY, 30, 110), [])
        self.assertIn("No roadmap documents found.", rs.render_md([empty], [], TODAY))


if __name__ == "__main__":
    unittest.main()
