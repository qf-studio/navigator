#!/usr/bin/env python3
"""Tests for task_to_graph.add_task_to_graph referential integrity (wp6 follow-up).

The PostToolUse task-sync hook must not re-introduce dangling 'implements'
edges. Before the fix, keyword_map produced concept 'tom' (no canonical node)
and an unconditional edge, so every task edit poisoned the graph with a
dangling edge that --action repair then had to clean.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from graph_manager import create_empty_graph, save_graph, load_graph, add_node
from graph_maintenance import find_dangling_edges
from task_to_graph import add_task_to_graph, extract_decisions, extract_status


class TaskSyncIntegrityTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.graph_path = self.root / "graph.json"
        graph = create_empty_graph()
        # Only the canonical 'theory of mind' concept exists as a node.
        graph = add_node(
            graph, "concepts", "theory of mind",
            {"name": "Theory of Mind", "aliases": ["tom", "profile"]},
        )
        save_graph(str(self.graph_path), graph)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_task(self, name: str, body: str) -> Path:
        path = self.root / name
        path.write_text(body)
        return path

    def test_sync_creates_no_dangling_edges(self):
        # 'profile' -> 'theory of mind' (node exists -> edge ok);
        # 'deploy' -> 'deployment' (no node -> edge filtered, not dangling).
        task = self._write_task(
            "TASK-77.md",
            "# TASK-77: x\n\nWork on the user profile and deployment pipeline.\n",
        )
        add_task_to_graph(str(task), str(self.graph_path))
        graph = load_graph(str(self.graph_path))
        self.assertEqual(find_dangling_edges(graph), [])

    def test_gh_prefixed_doc_gets_gh_task_id_and_title(self):
        """GH-32: task_id_source github → GH-<n>-slug.md, '# GH-<n>: title'."""
        task = self._write_task(
            "GH-57-oauth.md",
            "# GH-57: OAuth login\n\nImprove the profile flow.\n",
        )
        add_task_to_graph(str(task), str(self.graph_path))
        graph = load_graph(str(self.graph_path))
        node = graph["nodes"]["tasks"]["GH-57"]
        self.assertEqual(node["title"], "OAuth login")
        self.assertNotIn("GH-57-oauth", graph["nodes"]["tasks"])

    def test_canonical_concept_edge_is_added(self):
        # 'profile'/'tom' both normalize to the canonical 'theory of mind' node.
        task = self._write_task(
            "TASK-78.md",
            "# TASK-78: x\n\nImprove the profile / tom modeling.\n",
        )
        add_task_to_graph(str(task), str(self.graph_path))
        graph = load_graph(str(self.graph_path))
        edges = [(e["from"], e["to"]) for e in graph["edges"]]
        self.assertIn(("TASK-78", "theory of mind"), edges)


COMPLETED_TASK_WITH_DECISIONS = """# TASK-99: Demo

**Status**: ✅ Completed

## Technical Decisions

| Decision | Options | Chosen | Reasoning |
|----------|---------|--------|-----------|
| Issue interface | gh, API | `gh` | GitHub-only access |
"""


class DecisionExtractionTest(unittest.TestCase):
    """Separator rows must never be ingested as decisions (mem-038/mem-044)."""

    def test_wide_separator_row_not_ingested(self):
        decisions = extract_decisions(COMPLETED_TASK_WITH_DECISIONS)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["decision"], "Issue interface")

    def test_narrow_separator_row_still_skipped(self):
        content = (
            "## Technical Decisions\n\n"
            "| Decision | Options | Chosen | Reasoning |\n"
            "|---|---|---|---|\n"
            "| X | a, b | a | short reason here |\n"
        )
        decisions = extract_decisions(content)
        self.assertEqual([d["decision"] for d in decisions], ["X"])

    def test_colon_aligned_separator_skipped(self):
        content = (
            "## Technical Decisions\n\n"
            "| Decision | Options | Chosen | Reasoning |\n"
            "|:---------|:-------:|-------:|-----------|\n"
            "| Y | a, b | b | another reason here |\n"
        )
        decisions = extract_decisions(content)
        self.assertEqual([d["decision"] for d in decisions], ["Y"])


class DecisionDedupeTest(unittest.TestCase):
    """Re-syncing a completed task must not duplicate its decision memories
    (the TASK-54 double-sync produced mem-044..049 as copies of mem-038..043).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.graph_path = self.root / "graph.json"
        save_graph(str(self.graph_path), create_empty_graph())
        # add_memory writes backing files under CWD-relative .agent/knowledge;
        # run inside the tmp root so tests never touch the real project graph.
        self._old_cwd = Path.cwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self._old_cwd)
        self._tmp.cleanup()

    def test_resync_does_not_duplicate_decision_memories(self):
        task = self.root / "TASK-99.md"
        task.write_text(COMPLETED_TASK_WITH_DECISIONS)

        first = add_task_to_graph(str(task), str(self.graph_path))
        self.assertEqual(len(first["memories_created"]), 1)

        second = add_task_to_graph(str(task), str(self.graph_path))
        self.assertEqual(second["memories_created"], [])

        graph = load_graph(str(self.graph_path))
        summaries = [m["summary"] for m in graph["nodes"]["memories"].values()]
        self.assertEqual(len(summaries), len(set(summaries)))
        self.assertEqual(len(summaries), 1)


class StatusVocabularyTest(unittest.TestCase):
    """TASK-67: plain-text Status lines must map to a known canonical status,
    not 'unknown' — the graph was recording most in-repo task docs (which use
    '**Status**: Implemented') as 'unknown'.
    """

    def _status(self, status_line: str) -> str:
        return extract_status(f"# TASK-1: x\n\n{status_line}\n\nbody\n")

    def test_emoji_prefixed_implemented_maps_to_completed(self):
        line = "**Status**: ✅ Implemented — 2026-07-10"
        self.assertEqual(self._status(line), "completed")

    def test_plain_implemented_maps_to_completed(self):
        self.assertEqual(self._status("**Status**: Implemented"), "completed")

    def test_plain_in_progress_maps_to_in_progress(self):
        self.assertEqual(self._status("**Status**: In Progress"), "in-progress")

    def test_emoji_research_and_planning_maps_to_research(self):
        line = "**Status**: 🔬 Research & Planning"
        self.assertEqual(self._status(line), "research")

    def test_plain_deprecated_maps_to_deprecated(self):
        self.assertEqual(self._status("**Status**: Deprecated"), "deprecated")

    def test_case_insensitive_and_punctuation(self):
        self.assertEqual(self._status("**Status**: completed."), "completed")
        self.assertEqual(self._status("**Status**: - PLANNED"), "backlog")

    def test_new_states_recognized(self):
        self.assertEqual(self._status("**Status**: Design"), "design")
        self.assertEqual(self._status("**Status**: Dispatched"), "dispatched")
        self.assertEqual(self._status("**Status**: Blocked"), "blocked")

    def test_unrecognized_status_line_is_unknown(self):
        self.assertEqual(self._status("**Status**: Flibbertigibbet"), "unknown")

    def test_emoji_only_status_still_resolves(self):
        self.assertEqual(self._status("**Status**: ✅"), "completed")

    def test_prose_mention_does_not_misclassify(self):
        # No Status line; body talks about design/research but must not leak in.
        content = (
            "# TASK-2: x\n\n"
            "This task is about the design of the research pipeline.\n"
        )
        self.assertEqual(extract_status(content), "unknown")

    def test_legacy_no_status_line_fallback(self):
        content = "# TASK-3: x\n\nProgress note: ✅ Completed the rollout.\n"
        self.assertEqual(extract_status(content), "completed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
