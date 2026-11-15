#!/usr/bin/env python3
"""Unit tests for route_render.py — the route section, GitHub state, the two report forms."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import route_render as rr

DOC = """# TASK-7: Open Tasks shows the real status

**Status**: 🚧 In Progress

## Context

**Problem**:
Done documents show as open.

**Goal**:
The session start lists only open work. Done documents are one count line.

## Acceptance Criteria

- [ ] An acceptance box is not a step.

## Route

### Phase 1: The gate reads the status line
- [x] 1. Read the status from one shared function. (#48)
- [ ] 2. Show done documents as one count line. (PR #49, needs 1)
- [ ] 3. Install the plugin on the build machine (the founder box). (operator, needs 2)

### Phase 2: Release
- [ ] 4. Write the release notes.
- [ ] 5. Announce the release. (acme/site#7, needs 3, 4)

### Side tracks
- [ ] Repair the test target on macOS. (#52)

### Waits for you
- [ ] Decide the release number.
- [x] Approve the plan.

## Refs

- [ ] Not a step either.
"""

GITHUB = {
    "#48": {"state": "closed", "state_reason": "completed", "closed_at": "2026-11-08T10:00:00Z"},
    "#49": {"state": "open", "pull_request": {"merged_at": None}},
    "#52": {"state": "open", "labels": [{"name": "Pilot"}], "assignees": []},
}


def build(doc=DOC, github=None):
    route = rr.parse_route(doc)
    rr.resolve(route, GITHUB if github is None else github)
    return route


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = rr.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class ParseTest(unittest.TestCase):
    def test_phases_steps_side_tracks_and_waits(self):
        route = rr.parse_route(DOC)
        self.assertEqual((route.task_id, route.title),
                         ("TASK-7", "Open Tasks shows the real status"))
        self.assertEqual([p.title for p in route.phases],
                         ["Phase 1: The gate reads the status line", "Phase 2: Release"])
        self.assertEqual([s.number for s in route.steps], ["1", "2", "3", "4", "5"])
        self.assertEqual([s.text for s in route.side], ["Repair the test target on macOS."])
        self.assertEqual(route.waits, ["Decide the release number."])

    def test_goal_is_the_context_paragraph(self):
        self.assertEqual(rr.parse_route(DOC).goal,
                         "The session start lists only open work. "
                         "Done documents are one count line.")

    def test_goal_on_the_same_line(self):
        doc = DOC.replace("**Goal**:\nThe session", "**Goal**: The session")
        self.assertTrue(rr.parse_route(doc).goal.startswith("The session start"))

    def test_attributes(self):
        one, two, three, four, five = rr.parse_route(DOC).steps
        self.assertEqual((one.ref, one.checked, one.needs), ("#48", True, ()))
        self.assertEqual((two.ref, two.needs), ("#49", ("1",)))
        self.assertEqual((three.operator, three.needs, three.ref), (True, ("2",), ""))
        self.assertEqual((four.ref, four.operator, four.needs), ("", False, ()))
        self.assertEqual((five.ref, five.needs), ("acme/site#7", ("3", "4")))

    def test_an_ordinary_parenthesis_stays_in_the_plain_line(self):
        doc = DOC.replace("4. Write the release notes.", "4. Write the notes (short ones).")
        self.assertEqual(rr.parse_route(doc).steps[3].text, "Write the notes (short ones).")
        three = rr.parse_route(DOC).steps[2]
        self.assertEqual(three.text, "Install the plugin on the build machine (the founder box).")

    def test_only_the_route_section_gives_steps(self):
        texts = [s.text for s in rr.parse_route(DOC).steps]
        self.assertNotIn("An acceptance box is not a step.", texts)
        self.assertNotIn("Not a step either.", texts)

    def test_steps_with_no_phase_heading(self):
        doc = DOC.replace("### Phase 1: The gate reads the status line\n", "")
        self.assertEqual(rr.parse_route(doc).phases[0].title, "")


class ErrorTest(unittest.TestCase):
    def assert_error(self, doc, needle):
        with self.assertRaises(rr.RouteError) as caught:
            rr.parse_route(doc)
        self.assertIn(needle, str(caught.exception))

    def test_step_with_no_plain_line_names_the_step(self):
        self.assert_error(DOC.replace("4. Write the release notes.", "4. `notes` (#9)"),
                          "step 4 has no plain line")

    def test_internal_code_names_the_step_and_the_code(self):
        self.assert_error(DOC.replace("4. Write the release notes.", "4. U2: release notes"),
                          "step 4 starts with an internal code 'U2'")

    def test_step_with_no_number(self):
        self.assert_error(DOC.replace("- [ ] 4. Write", "- [ ] Write"), "no order number")

    def test_unknown_need(self):
        self.assert_error(DOC.replace("needs 3, 4", "needs 3, 9"), "needs step 9")

    def test_duplicate_number(self):
        self.assert_error(DOC.replace("- [ ] 4. Write", "- [ ] 3. Write"), "step 3 appears")

    def test_no_route_section(self):
        self.assert_error(DOC.replace("## Route", "## Plan"), "no '## Route' section")

    def test_no_goal(self):
        self.assert_error(DOC.replace("**Goal**:", "**Aim**:"), "no '**Goal**:' text")

    def test_template_placeholder_goal_is_no_goal(self):
        doc = DOC.replace("The session start lists only open work. "
                          "Done documents are one count line.", "[What are we building?]")
        self.assert_error(doc, "no '**Goal**:' text")


class ResolveTest(unittest.TestCase):
    def states(self, route):
        return {s.key: s.state for s in route.steps + route.side}

    def test_github_state(self):
        self.assertEqual(self.states(build()), {
            "1": "Done 2026-11-08",
            "2": "In the queue now",
            "3": "Blocked: needs step 2",
            "4": "Next",
            "5": "Blocked: needs steps 3 and 4",
            "side:1": "In the queue now",
        })

    def test_merged_pull_request_unblocks_the_next_step(self):
        github = dict(GITHUB, **{"#49": {"state": "closed", "pull_request":
                                         {"merged_at": "2026-11-09T08:00:00Z"}}})
        states = self.states(build(github=github))
        self.assertEqual(states["2"], "Merged 2026-11-09")
        self.assertEqual(states["3"], "Next")
        self.assertEqual(states["4"], "Later")

    def test_no_github_falls_back_to_the_checkboxes(self):
        self.assertEqual(self.states(build(github={})), {
            "1": "Done", "2": "Next", "3": "Blocked: needs step 2", "4": "Later",
            "5": "Blocked: needs steps 3 and 4", "side:1": "Open",
        })

    def test_checked_box_is_done_when_the_issue_is_still_open(self):
        github = {"#48": {"state": "open", "labels": [], "assignees": []}}
        self.assertEqual(self.states(build(github=github))["1"], "Done")

    def test_closed_states(self):
        github = {"#49": {"state": "closed", "pull_request": {"merged_at": None}},
                  "#52": {"state": "closed", "state_reason": "not_planned",
                          "closed_at": "2026-11-10T00:00:00Z"}}
        states = self.states(build(github=github))
        self.assertEqual(states["2"], "Closed, not merged; Next")
        self.assertEqual(states["side:1"], "Closed, not planned 2026-11-10")

    def test_assignee_or_queue_label_means_in_the_queue(self):
        doc = DOC.replace("4. Write the release notes.", "4. Write the release notes. (#60)")
        idle = {"#60": {"state": "open", "labels": [{"name": "docs"}], "assignees": []}}
        busy = {"#60": {"state": "open", "labels": [], "assignees": [{"login": "a"}]}}
        self.assertEqual(self.states(build(doc, idle))["4"], "Later")
        self.assertEqual(self.states(build(doc, busy))["4"], "In the queue now")


class RenderTest(unittest.TestCase):
    def test_full_form_has_the_five_sections_in_order(self):
        text = rr.render_full(build(), "State from GitHub.")
        heads = [line for line in text.split("\n") if line.startswith("## ")]
        self.assertEqual(heads, ["## 1. The goal", "## 2. The roadmap", "## 3. Side tracks",
                                 "## 4. The queue now", "## 5. What waits for you"])
        self.assertIn("# Route report: TASK-7 — Open Tasks shows the real status", text)

    def test_roadmap_lines(self):
        text = rr.render_full(build(), "State from GitHub.")
        self.assertIn("**Phase 1: The gate reads the status line (1 of 3 done)**", text)
        self.assertIn("- ✓ 1. Read the status from one shared function. — #48 · "
                      "Done 2026-11-08", text)
        self.assertIn("- ● 2. Show done documents as one count line. — PR #49 · "
                      "In the queue now", text)
        self.assertIn("— Operator step · Blocked: needs step 2", text)
        self.assertIn("- ○ 4. Write the release notes. — Not filed · Next", text)

    def test_queue_and_waits(self):
        text = rr.render_full(build(), "State from GitHub.")
        queue = text.split("## 4. The queue now")[1].split("## 5.")[0]
        self.assertIn("- PR #49: Show done documents as one count line.", queue)
        self.assertIn("- #52: Repair the test target on macOS.", queue)
        waits = text.split("## 5. What waits for you")[1]
        self.assertIn("1. Review PR #49: Show done documents as one count line.", waits)
        self.assertIn("2. Decide the release number.", waits)
        self.assertNotIn("Approve the plan", waits)

    def test_operator_step_waits_for_the_user_when_it_is_next(self):
        github = dict(GITHUB, **{"#49": {"state": "closed", "pull_request":
                                         {"merged_at": "2026-11-09T08:00:00Z"}}})
        waits = rr.render_full(build(github=github), "s").split("## 5.")[1]
        self.assertIn("1. Do the operator step 3: Install the plugin", waits)

    def test_empty_sections_say_so(self):
        doc = DOC.split("### Side tracks")[0] + "## Refs\n"
        text = rr.render_full(build(doc, {}), "s")
        self.assertIn("## 3. Side tracks\n\nNone.", text)
        self.assertIn("## 4. The queue now\n\nNothing is in the queue.", text)
        self.assertIn("## 5. What waits for you\n\nNothing.", text)

    def test_changes_since_a_state_are_marked(self):
        before = rr.state_of(build(github={}), "2026-11-07")["steps"]
        text = rr.render_full(build(), "s", before)
        self.assertIn("· Done 2026-11-08  ← changed (was: Done)", text)
        self.assertIn("· In the queue now  ← changed (was: Next)", text)
        self.assertNotIn("Blocked: needs step 2  ←", text)

    def test_short_form_shows_changed_rows_and_the_unchanged_count(self):
        before = rr.state_of(build(github={}), "2026-11-07")["steps"]
        text = rr.render_short(build(), before)
        rows = [line for line in text.split("\n") if line.startswith("- ")]
        self.assertEqual(len(rows), 4)          # steps 1, 2, 4 and the side track
        self.assertTrue(text.rstrip().endswith("unchanged: 2"))
        self.assertNotIn("## ", text)

    def test_short_form_reports_new_and_removed_steps(self):
        before = dict(rr.state_of(build(), "d")["steps"], **{"9": "Next"})
        del before["4"]
        text = rr.render_short(build(), before)
        self.assertIn("4. Write the release notes. — Not filed · Next  ← changed (new)", text)
        self.assertIn("- Removed from the route: 9.", text)
        self.assertIn("unchanged: 5", text)


class TemplateTest(unittest.TestCase):
    """The three task templates carry one route section, in the format the script reads."""

    ROOT = Path(__file__).resolve().parents[3]
    TEMPLATES = ("skills/nav-task/SKILL.md", "skills/nav-task/functions/task_formatter.py",
                 "templates/task-template.md")

    def test_every_template_has_a_route_section_that_parses(self):
        for name in self.TEMPLATES:
            text = (self.ROOT / name).read_text(encoding="utf-8")
            start = text.index("## Route\n")
            section = text[start:text.index("## Implementation", start)]
            route = rr.parse_route("# TASK-1: Template\n\n**Goal**: A goal is here.\n\n" + section)
            self.assertEqual([s.number for s in route.steps], ["1", "2"], name)
            self.assertEqual(route.steps[1].needs, ("1",), name)
            self.assertEqual((len(route.side), len(route.waits)), (1, 1), name)

    def test_the_marker_skill_stores_the_route_state(self):
        text = (self.ROOT / "skills/nav-marker/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("## Route State", text)
        self.assertIn("route_render.py\" --state", text)


class CliTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.task = self.dir / "TASK-7-open-tasks.md"
        self.task.write_text(DOC, encoding="utf-8")

    def test_no_gh_renders_from_the_checkboxes(self):
        code, out, err = run_cli("--task", str(self.task), "--no-gh", "--today", "2026-11-15")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("_State from the checkboxes, 2026-11-15. GitHub state is not available._",
                      out)
        self.assertIn("## 5. What waits for you", out)

    def test_missing_gh_binary_renders_from_the_checkboxes(self):
        with mock.patch.object(rr.shutil, "which", return_value=None):
            code, out, _ = run_cli("--task", str(self.task))
        self.assertEqual(code, 0)
        self.assertIn("GitHub state is not available", out)

    def test_gh_answers_are_used(self):
        with mock.patch.object(rr, "fetch_github", return_value=GITHUB):
            code, out, _ = run_cli("--task", str(self.task), "--today", "2026-11-15")
        self.assertEqual(code, 0)
        self.assertIn("State from GitHub and the checkboxes, 2026-11-15. "
                      "GitHub did not answer for 1 ticket(s).", out)

    def test_error_goes_to_stderr_with_exit_2(self):
        self.task.write_text(DOC.replace("4. Write the release notes.", "4. x"), "utf-8")
        code, out, err = run_cli("--task", str(self.task), "--no-gh")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("error: step 4 has no plain line", err)

    def test_state_round_trip_through_a_marker(self):
        code, state, _ = run_cli("--task", str(self.task), "--no-gh", "--state",
                                 "--today", "2026-11-07")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(state)["task"], "TASK-7")
        marker = self.dir / "marker.md"
        marker.write_text(f"# Marker\n\n## Route State\n\n```json\n{state.strip()}\n```\n", "utf-8")
        self.task.write_text(DOC.replace("- [ ] 2.", "- [x] 2."), "utf-8")
        code, out, _ = run_cli("--task", str(self.task), "--no-gh", "--short",
                               "--since", str(marker))
        self.assertEqual(code, 0)
        self.assertIn("2. Show done documents as one count line. — #49 · Done  "
                      "← changed (was: Next)", out)
        self.assertIn("3. Install the plugin on the build machine (the founder box). — "
                      "Operator step · Next  ← changed (was: Blocked: needs step 2)", out)
        self.assertIn("unchanged: 4", out)

    def test_short_needs_since(self):
        code, _, err = run_cli("--task", str(self.task), "--no-gh", "--short")
        self.assertEqual(code, 2)
        self.assertIn("the short form needs --since", err)

    def test_since_file_without_a_state(self):
        other = self.dir / "note.md"
        other.write_text("# nothing here\n", "utf-8")
        code, _, err = run_cli("--task", str(self.task), "--no-gh", "--since", str(other))
        self.assertEqual(code, 2)
        self.assertIn("holds no route state", err)

    def test_default_task_is_the_last_open_document_with_a_route(self):
        (self.dir / "TASK-8-done.md").write_text(
            DOC.replace("🚧 In Progress", "✅ Completed").replace("TASK-7", "TASK-8"), "utf-8")
        (self.dir / "TASK-9-no-route.md").write_text("# TASK-9: x\n\n**Status**: 🚧\n", "utf-8")
        code, out, _ = run_cli("--tasks-dir", str(self.dir), "--no-gh")
        self.assertEqual(code, 0)
        self.assertIn("# Route report: TASK-7", out)

    def test_no_document_with_a_route(self):
        self.task.unlink()
        code, _, err = run_cli("--tasks-dir", str(self.dir), "--no-gh")
        self.assertEqual(code, 2)
        self.assertIn("no open task document with a '## Route' section", err)


if __name__ == "__main__":
    unittest.main()
