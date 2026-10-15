#!/usr/bin/env python3
"""Template-shape tests: claude_updater vs the demoted v7 templates/CLAUDE.md.

TASK-63 Phase 3: templates/CLAUDE.md is demoted to context-only (<=65 lines).
claude_updater.py must still round-trip customizations through the new shape:
the generation placeholders stay present, the preserved customization region
("[Add project-specific violations here]") stays parseable, and the Navigator
runtime section never leaks into extracted custom_sections (sync drift).

Also guards the v6.18.1 regression class: table separator rows, if any, must
use exactly `|---|` per cell.

These tests call extract/generate as functions (the CLI's hook-liveness
sequencing guard is covered separately in test_claude_updater.py).
"""

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

FUNCTIONS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(FUNCTIONS_DIR))

import claude_updater  # noqa: E402

REPO_ROOT = FUNCTIONS_DIR.parents[2]
TEMPLATE_PATH = REPO_ROOT / "templates" / "CLAUDE.md"

VIOLATIONS_MARKER = "[Add project-specific violations here]"
DESCRIPTION_PLACEHOLDER = "[Brief project description - explain what this project does]"
TECH_STACK_PLACEHOLDER = "[List your technologies, e.g., Next.js, TypeScript, PostgreSQL]"

SAMPLE_CUSTOMIZATIONS = {
    "project_name": "Acme Shop",
    "description": "E-commerce storefront for Acme.",
    "tech_stack": ["Next.js", "PostgreSQL"],
    "code_standards": ["Use feature flags for risky rollouts"],
    "forbidden_actions": ["Never bypass the payment sandbox"],
    "pm_tool": "none",
    "custom_sections": {"Deployment Notes": "Deploy via blue/green only."},
}


class TemplateShapeTest(unittest.TestCase):
    """The demoted template keeps every marker claude_updater depends on."""

    @classmethod
    def setUpClass(cls):
        cls.text = TEMPLATE_PATH.read_text(encoding="utf-8")
        cls.lines = cls.text.splitlines()

    def test_template_within_demotion_budget(self):
        self.assertLessEqual(len(self.lines), 65,
                             "templates/CLAUDE.md must stay <=65 lines (TASK-63)")

    def test_no_workflow_check_mandate(self):
        self.assertNotIn("WORKFLOW CHECK", self.text)

    def test_generation_placeholders_present(self):
        self.assertIn("# [Project Name] - Claude Code Configuration", self.text)
        self.assertIn(DESCRIPTION_PLACEHOLDER, self.text)
        self.assertIn(TECH_STACK_PLACEHOLDER, self.text)
        self.assertEqual(self.text.count(VIOLATIONS_MARKER), 1,
                         "customization region marker must appear exactly once")

    def test_runtime_paragraph_names_off_switches(self):
        self.assertIn("Navigator runtime", self.text)
        for switch in ("enabled", "strict_block", "tier1.rules",
                       "stop_completion.continue_enabled", "PILOT_EXECUTOR"):
            self.assertIn(switch, self.text, f"runtime paragraph must name {switch}")

    def test_table_separator_rows_are_exact(self):
        # v6.18.1 regression class: separator cells must be exactly `---`.
        for line in self.lines:
            stripped = line.strip()
            if re.fullmatch(r"\|[\s:|-]+\|", stripped) and "-" in stripped:
                self.assertRegex(stripped, r"^\|(?:---\|)+$",
                                 f"wide table separator row: {stripped!r}")

    def test_pristine_template_extracts_only_its_own_defaults(self):
        # extract records the lists verbatim (a project may drop a default),
        # so the pristine template yields exactly its own bullets and nothing
        # custom: no description, no core principle, no custom sections.
        got = claude_updater.extract_customizations(str(TEMPLATE_PATH))
        self.assertEqual(got["project_name"], "[Project Name]")
        self.assertEqual(got["description"], "")
        self.assertEqual(got["core_principle"], "")
        self.assertEqual(got["code_standards"], [
            "**Architecture**: KISS, DRY, SOLID principles",
            "**TypeScript**: Strict mode, no `any` without justification",
            "**Line Length**: Max 100 characters",
            "**Testing**: High coverage (backend 90%+, frontend 85%+)",
        ])
        self.assertEqual(got["forbidden_actions"], [
            "No Claude Code mentions in commits/code",
            "No package.json modifications without approval",
            "Never commit secrets/API keys/.env files",
            "Don't delete tests without replacement",
        ])
        self.assertTrue(got["violations_marker"])
        self.assertEqual(got["custom_sections"], {})
        self.assertEqual(got["pm_tool"], "none")


class RoundTripTest(unittest.TestCase):
    """generate -> extract on the new template shape preserves customizations."""

    def generate(self, customizations):
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False, encoding="utf-8") as out:
            output_path = out.name
        self.addCleanup(Path(output_path).unlink)
        claude_updater.generate_updated_claude_md(
            customizations, str(TEMPLATE_PATH), output_path)
        return output_path, Path(output_path).read_text(encoding="utf-8")

    def test_round_trip_preserves_customizations(self):
        output_path, generated = self.generate(dict(SAMPLE_CUSTOMIZATIONS))

        # Everything the user customized is present in the generated document.
        self.assertIn("# Acme Shop - Claude Code Configuration", generated)
        self.assertIn("Use feature flags for risky rollouts", generated)
        self.assertIn("Never bypass the payment sandbox", generated)
        self.assertIn("Deploy via blue/green only.", generated)
        self.assertNotIn(DESCRIPTION_PLACEHOLDER, generated)
        self.assertNotIn(TECH_STACK_PLACEHOLDER, generated)

        # And a second extraction (the next sync) recovers it.
        got = claude_updater.extract_customizations(output_path)
        self.assertEqual(got["project_name"], "Acme Shop")
        self.assertEqual(got["description"], "E-commerce storefront for Acme.")
        self.assertEqual(got["tech_stack"], ["Next.js", "PostgreSQL"])
        self.assertIn("Never bypass the payment sandbox", got["forbidden_actions"])

        custom_flat = json.dumps(got["custom_sections"])
        self.assertIn("Deploy via blue/green only.", custom_flat)

    def test_navigator_runtime_section_never_drifts_into_custom_sections(self):
        # The "## Navigator" runtime section must be recognized as standard;
        # otherwise every sync would re-append it under Custom Project Sections.
        output_path, _ = self.generate(dict(SAMPLE_CUSTOMIZATIONS))
        got = claude_updater.extract_customizations(output_path)
        self.assertNotIn("Navigator", got["custom_sections"])
        self.assertNotIn("Navigator runtime", json.dumps(got["custom_sections"]))

    def test_marker_survives_generation_without_custom_violations(self):
        plain = dict(SAMPLE_CUSTOMIZATIONS,
                     code_standards=[], forbidden_actions=[], custom_sections={})
        _, generated = self.generate(plain)
        self.assertIn(VIOLATIONS_MARKER, generated,
                      "customization region must survive a no-customization sync")


if __name__ == "__main__":
    unittest.main()
