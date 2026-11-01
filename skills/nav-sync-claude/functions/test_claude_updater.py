#!/usr/bin/env python3
"""Tests for the claude_updater hook-liveness sequencing guard (TASK-63 Phase 5).

TASK-45 subprocess pattern: each test builds a throwaway project dir and
drives the REAL CLI (`python3 claude_updater.py generate ...`), asserting on
exit code / stderr / on-disk effects. Both branches are covered:

  - refuse: no liveness proof (absent or stale files) -> exit 3, existing
    CLAUDE.md untouched, refusal names the guard, the files checked, and the
    remedy (mem-036 class: never strip prose while hooks are silently dead).
  - proceed: fresh .nav-runtime-state.json (meta.schema == 2, meta.updated
    within 7 days) OR fresh .nav-dispatch-health.json (last_error.ts within
    7 days) -> regeneration happens.

Env discipline (mem-036): the same behavior is asserted with hook-style env
vars set AND unset — the guard reads files, never env.

The --template argument is always a direct FILE path so the CLI takes the
no-network branch (GitHub fetch only fires for directory arguments). The
guard resolves the project root from --project-root, else the `source_dir`
that `extract` recorded, else the current directory — never from --output —
so the generate runs below use the project as cwd.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import claude_updater  # noqa: E402

SCRIPT = str(Path(__file__).resolve().parent / "claude_updater.py")

EMPTY_CUSTOMIZATIONS = {
    "project_name": "",
    "description": "",
    "tech_stack": [],
    "code_standards": [],
    "forbidden_actions": [],
    "pm_tool": "none",
    "custom_sections": {},
}

TEMPLATE_BODY = "# [Project Name] - Claude Code Configuration\n\nTemplate body.\n"


def _env_with_hook_vars(project: Path) -> dict:
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project)
    env["CLAUDE_PLUGIN_ROOT"] = str(project)
    return env


def _env_without_hook_vars() -> dict:
    return {
        k: v for k, v in os.environ.items()
        if not k.startswith("CLAUDE_") and k != "PILOT_EXECUTOR"
    }


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _write_state_file(project: Path, updated: datetime, schema: int = 2) -> None:
    agent = project / ".agent"
    agent.mkdir(parents=True, exist_ok=True)
    doc = {"meta": {"schema": schema, "updated": _iso(updated), "sections": {}}}
    (agent / ".nav-runtime-state.json").write_text(json.dumps(doc))


def _write_health_file(project: Path, ts: datetime) -> None:
    agent = project / ".agent"
    agent.mkdir(parents=True, exist_ok=True)
    doc = {
        "last_error": {
            "ts": _iso(ts), "event": "Stop", "op": "stop_state", "error": "OSError",
        },
        "surfaced": True,
    }
    (agent / ".nav-dispatch-health.json").write_text(json.dumps(doc))


def _run_generate(project: Path, env: dict) -> subprocess.CompletedProcess:
    customizations = project / "customizations.json"
    customizations.write_text(json.dumps(EMPTY_CUSTOMIZATIONS))
    template = project / "template.md"
    template.write_text(TEMPLATE_BODY)
    return subprocess.run(
        [
            sys.executable, SCRIPT, "generate",
            "--customizations", str(customizations),
            "--template", str(template),
            "--output", str(project / "CLAUDE.md"),
        ],
        capture_output=True, text=True, env=env, cwd=str(project),
    )


class GuardRefusalTests(unittest.TestCase):
    def test_refuses_when_no_liveness_files_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            result = _run_generate(project, _env_with_hook_vars(project))

            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertFalse((project / "CLAUDE.md").exists())
            # Refusal names the guard, both files checked, and the remedy.
            self.assertIn("sequencing guard", result.stderr)
            self.assertIn(".nav-runtime-state.json", result.stderr)
            self.assertIn(".nav-dispatch-health.json", result.stderr)
            self.assertIn("re-run the sync", result.stderr)

    def test_refuses_identically_with_hook_env_unset(self):
        # mem-036 discipline: env state must not change guard behavior.
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            result = _run_generate(project, _env_without_hook_vars())

            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertIn("sequencing guard", result.stderr)
            self.assertFalse((project / "CLAUDE.md").exists())

    def test_refuses_on_stale_state_and_preserves_existing_claude_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            stale = datetime.now(tz=timezone.utc) - timedelta(days=8)
            _write_state_file(project, stale)
            existing = "# Existing prose mandates\n"
            (project / "CLAUDE.md").write_text(existing)

            result = _run_generate(project, _env_with_hook_vars(project))

            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertEqual((project / "CLAUDE.md").read_text(), existing)

    def test_refuses_on_fresh_state_with_wrong_schema(self):
        # Schema gate: only meta.schema == 2 documents prove the v7 runtime.
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write_state_file(project, datetime.now(tz=timezone.utc), schema=1)

            result = _run_generate(project, _env_with_hook_vars(project))

            self.assertEqual(result.returncode, 3, result.stderr)

    def test_refuses_on_stale_health_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            stale = datetime.now(tz=timezone.utc) - timedelta(days=8)
            _write_health_file(project, stale)

            result = _run_generate(project, _env_with_hook_vars(project))

            self.assertEqual(result.returncode, 3, result.stderr)


class GuardProceedTests(unittest.TestCase):
    def test_proceeds_with_fresh_state_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write_state_file(project, datetime.now(tz=timezone.utc))

            result = _run_generate(project, _env_with_hook_vars(project))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Template body.", (project / "CLAUDE.md").read_text())

    def test_proceeds_with_fresh_state_file_env_unset(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write_state_file(project, datetime.now(tz=timezone.utc))

            result = _run_generate(project, _env_without_hook_vars())

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((project / "CLAUDE.md").exists())

    def test_proceeds_with_fresh_health_file_only(self):
        # Health is written on error only, but a fresh error record still
        # proves the dispatcher ran — liveness, not health, is the question.
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write_health_file(project, datetime.now(tz=timezone.utc))

            result = _run_generate(project, _env_with_hook_vars(project))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((project / "CLAUDE.md").exists())

    def test_proceeds_with_stale_state_but_fresh_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write_state_file(project, datetime.now(tz=timezone.utc) - timedelta(days=8))
            _write_health_file(project, datetime.now(tz=timezone.utc))

            result = _run_generate(project, _env_with_hook_vars(project))

            self.assertEqual(result.returncode, 0, result.stderr)


class CheckHookLivenessUnitTests(unittest.TestCase):
    """Direct unit coverage of the boundary math (injectable `now`)."""

    def test_exactly_seven_days_old_is_still_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            now = datetime.now(tz=timezone.utc)
            _write_state_file(project, now - timedelta(days=7))

            alive, message = claude_updater.check_hook_liveness(
                project, now=now.timestamp()
            )
            self.assertTrue(alive, message)

    def test_corrupt_json_counts_as_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            agent = project / ".agent"
            agent.mkdir()
            (agent / ".nav-runtime-state.json").write_text("{not json")
            (agent / ".nav-dispatch-health.json").write_text("[]")

            alive, message = claude_updater.check_hook_liveness(project)
            self.assertFalse(alive)
            self.assertIn("sequencing guard", message)


# ---------------------------------------------------------------------------
# Faithful extract + generate (defects seen 2026-10-15 on a Navigator 8.4.2
# project CLAUDE.md). The fixture mirrors that file's shape: a multi-line
# description and core principle, custom `##` sections between standard ones,
# a multi-line bullet, a dropped template default, an extra forbidden action,
# no violations marker.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_PATH = REPO_ROOT / "templates" / "CLAUDE.md"

# The Navigator section is template-owned, so an "already-current" file
# carries the installed template's paragraph verbatim.
NAVIGATOR_SECTION = claude_updater.extract_section(
    TEMPLATE_PATH.read_text(encoding="utf-8"), "Navigator")

CURRENT_CLAUDE_MD = """# acme-site - Claude Code Configuration

## Context

Marketing landing for acme.dev. Two ways to run Acme: Terminal (free, own key)
and Acme Console (hosted, USD 499/month per org). Private repo.

**Tech Stack**: Next.js 15 (static export), React 19, TypeScript, Tailwind CSS 4, Vitest, bun

**Core Principle**: The founder's Figma layout is the source of truth for layout and colour
(Acme — LP, frame 902:111). See `.agent/system/design-system.md`.

**Last Updated**: 2026-01-01
**Navigator Version**: 8.0.0

---

## Navigator

{navigator_section}

## Commands

- Dev: `bun run dev -- -p 4173` → http://127.0.0.1:4173/
- Checks: `make build` · `make test` · `make lint`

## Project-Specific Code Standards

- **Architecture**: KISS, DRY, SOLID principles
- **TypeScript**: Strict mode, no `any` without justification
- **Line Length**: Max 100 characters
- **Theme**: Tokens live in `app/globals.css` and come from the Figma frame. Do not invent new
  colours; add a token only when the Figma frame adds one.
- **Price**: The console price comes from the plan constant in `lib/site`. Never hardcode it.

## Founder Rules (binding)

- Ticket cards show REAL shipped issues in plain PM wording. No vendor names on cards.
- Hosting is CloudFront + S3, not Vercel.

## Forbidden Actions

- ❌ No Claude Code mentions in commits/code
- ❌ No package.json modifications without approval
- ❌ Never commit secrets/API keys/.env files
- ❌ Don't delete tests without replacement
- ❌ No client material in this repo or in the public repo
""".format(navigator_section=NAVIGATOR_SECTION)

THEME_BULLET = (
    "**Theme**: Tokens live in `app/globals.css` and come from the Figma frame. "
    "Do not invent new\n  colours; add a token only when the Figma frame adds one."
)
CORE_PRINCIPLE = (
    "The founder's Figma layout is the source of truth for layout and colour\n"
    "(Acme — LP, frame 902:111). See `.agent/system/design-system.md`."
)


def _repo_plugin_version() -> str:
    manifest = REPO_ROOT / ".claude-plugin" / "plugin.json"
    return json.loads(manifest.read_text(encoding="utf-8"))["version"]


class FaithfulRoundTripTests(unittest.TestCase):
    """extract + generate on an up-to-date project file keeps its content."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name)
        self.source = self.project / "CLAUDE.md"
        self.source.write_text(CURRENT_CLAUDE_MD, encoding="utf-8")
        self.customizations = claude_updater.extract_customizations(str(self.source))

    def generate(self, **kwargs) -> str:
        out = self.project / "out.md"
        kwargs.setdefault("version", "9.9.9")
        kwargs.setdefault("today", "2026-10-15")
        claude_updater.generate_updated_claude_md(
            self.customizations, str(TEMPLATE_PATH), str(out), **kwargs)
        return out.read_text(encoding="utf-8")

    def test_core_principle_kept_multiline(self):
        # Defect 3: the value used to become the template placeholder.
        self.assertEqual(self.customizations["core_principle"], CORE_PRINCIPLE)
        generated = self.generate()
        self.assertIn(f"**Core Principle**: {CORE_PRINCIPLE}", generated)
        self.assertNotIn("[Key architectural principle", generated)

    def test_description_keeps_its_line_breaks(self):
        self.assertEqual(
            self.customizations["description"],
            "Marketing landing for acme.dev. Two ways to run Acme: Terminal (free, own key)\n"
            "and Acme Console (hosted, USD 499/month per org). Private repo.")

    def test_multiline_bullet_kept(self):
        # Defect 4: the continuation line of a bullet was cut.
        self.assertIn(THEME_BULLET, self.customizations["code_standards"])
        self.assertIn(f"- {THEME_BULLET}\n", self.generate())

    def test_custom_sections_appear_once_in_place(self):
        # Defect 5: custom sections were listed under "Additional Project
        # Standards" and again under "Custom Project Sections".
        self.assertEqual(
            list(self.customizations["custom_sections"]),
            ["Commands", "Founder Rules (binding)"])
        self.assertEqual(self.customizations["custom_section_anchors"], {
            "Commands": "Project-Specific Code Standards",
            "Founder Rules (binding)": "Forbidden Actions",
        })
        generated = self.generate()
        self.assertEqual(generated.count("## Commands"), 1)
        self.assertEqual(generated.count("## Founder Rules (binding)"), 1)
        self.assertEqual(generated.count("Hosting is CloudFront + S3, not Vercel."), 1)
        for stale in ("### Commands", "Additional Project Standards",
                      "Custom Project Sections"):
            self.assertNotIn(stale, generated)
        order = [generated.index(h) for h in (
            "## Navigator", "## Commands", "## Project-Specific Code Standards",
            "## Founder Rules (binding)", "## Forbidden Actions")]
        self.assertEqual(order, sorted(order), "custom sections must keep their place")

    def test_dropped_template_default_stays_dropped_and_placeholder_goes(self):
        # Defect 6: the project has no **Testing** bullet; generate must not
        # add it, and the "[Customize ...]" placeholder must not survive.
        self.assertNotIn(
            "**Testing**", json.dumps(self.customizations["code_standards"]))
        generated = self.generate()
        self.assertNotIn("**Testing**", generated)
        self.assertNotIn(claude_updater.STANDARDS_PLACEHOLDER, generated)
        self.assertNotIn(claude_updater.VIOLATIONS_MARKER, generated)
        self.assertIn("- ❌ No client material in this repo or in the public repo\n", generated)

    def test_hyphenated_project_name_survives(self):
        self.assertEqual(self.customizations["project_name"], "acme-site")
        self.assertIn("# acme-site - Claude Code Configuration", self.generate())

    def test_round_trip_changes_only_the_stamp_lines(self):
        import difflib
        generated = self.generate(version="9.9.9", today="2026-10-15")
        changed = [
            line for line in difflib.unified_diff(
                CURRENT_CLAUDE_MD.splitlines(), generated.splitlines(), lineterm="", n=0)
            if line[:1] in "+-" and not line.startswith(("+++", "---"))
        ]
        self.assertEqual(changed, [
            "-**Last Updated**: 2026-01-01",
            "-**Navigator Version**: 8.0.0",
            "+**Last Updated**: 2026-10-15",
            "+**Navigator Version**: 9.9.9",
        ])

    def test_extract_is_stable_across_a_second_sync(self):
        # Same stamps as the fixture, so the recorded layout is byte-identical.
        generated = self.generate(version="8.0.0", today="2026-01-01")
        again = self.project / "again.md"
        again.write_text(generated, encoding="utf-8")
        second = claude_updater.extract_customizations(str(again))
        first = dict(self.customizations, source_dir=None)
        self.assertEqual(dict(second, source_dir=None), first)


# ---------------------------------------------------------------------------
# Layout round trip (defects seen 2026-11-01 on a Navigator 8.4.11 project
# CLAUDE.md that never had the template's shape): no "## Context", a title
# without " - Claude Code Configuration", a preamble, custom sections with
# fenced bash blocks whose `# comment` lines look like headers, a `###`
# after such a block, a section whose body is only a fence, template-owned
# names the template no longer has ("Quick Start", "Code Standards"), the
# runtime paragraph and the stamps inside a custom-named section, and
# sections in an order the template does not use.
# ---------------------------------------------------------------------------

RUNTIME_PARAGRAPH = NAVIGATOR_SECTION.split("\n\n")[0]

WORKFLOW_BODY = """**Navigator plans. Pilot executes.** Interactive sessions follow this pipeline.

### Quick Commands

```bash
# Plan a feature (Navigator)
/nav-task "feature"
# Hand off to Pilot
#   "dispatch TASK-XX to Pilot"        # uses H1 as title
gh issue create --label pilot
```

### Rules (interactive sessions)

1. Never run `pilot` locally.
2. Review Pilot's PR before merge.

---"""

QUICK_START_BODY = """```bash
# Build
go build ./...
# Run
./pilot
```"""

LAYOUT_CLAUDE_MD = """# Pilot: AI That Ships Your Tickets

**Navigator plans. Pilot executes.**

## Who is reading this file?

- Interactive sessions: a human is present. Ask before destructive actions.
- Pilot executor sessions: `PILOT_EXECUTOR` is set. Never ask; never push.

## ⚠️ WORKFLOW: Navigator + Pilot Pipeline (interactive sessions only)

{workflow}

## Quick Start

{quick_start}

## Code Standards

- Go 1.22, `gofmt`, no `interface{{}}` without justification
- Line length: 100

## Navigator Integration

This project uses Navigator for planning, Pilot for execution:

```bash
/nav-start              # Start session, load context
```

{runtime}

**Last Updated**: 2026-10-17
**Navigator Version**: 8.4.4

## Forbidden Actions

- ❌ No Claude Code mentions in commits/code
- ❌ Never commit secrets/API keys/.env files

## Current Status

See `.agent/tasks/` for open work.
""".format(workflow=WORKFLOW_BODY, quick_start=QUICK_START_BODY, runtime=RUNTIME_PARAGRAPH)

OLD_RUNTIME_PARAGRAPH = (
    "**Navigator runtime (v7+)**: workflow enforcement lives in the plugin's hook\n"
    "runtime, not in prose in this file. Load docs on demand (Pilot-executor sessions).")


def _changed_lines(before: str, after: str):
    import difflib
    return [
        line for line in difflib.unified_diff(
            before.splitlines(), after.splitlines(), lineterm="", n=0)
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    ]


class LayoutRoundTripTests(unittest.TestCase):
    """extract + generate on a file that never had the template's shape."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name)

    def extract(self, text: str) -> dict:
        source = self.project / "CLAUDE.md"
        source.write_text(text, encoding="utf-8")
        return claude_updater.extract_customizations(str(source))

    def generate(self, customizations: dict, **kwargs) -> str:
        out = self.project / "out.md"
        kwargs.setdefault("version", "8.4.12")
        kwargs.setdefault("today", "2026-11-01")
        claude_updater.generate_updated_claude_md(
            customizations, str(TEMPLATE_PATH), str(out), **kwargs)
        return out.read_text(encoding="utf-8")

    def test_title_without_the_template_suffix_is_the_project_name(self):
        # Defect 1: the title became "[Project Name] - Claude Code Configuration".
        got = self.extract(LAYOUT_CLAUDE_MD)
        self.assertEqual(got["title"], "Pilot: AI That Ships Your Tickets")
        self.assertEqual(got["project_name"], "Pilot: AI That Ships Your Tickets")
        self.assertFalse(got["has_context"])
        self.assertEqual(got["preamble"], "**Navigator plans. Pilot executes.**")
        generated = self.generate(got)
        self.assertTrue(generated.startswith("# Pilot: AI That Ships Your Tickets\n"))
        for placeholder in ("[Project Name]", claude_updater.DESCRIPTION_PLACEHOLDER,
                            claude_updater.TECH_STACK_PLACEHOLDER,
                            "[Key architectural principle", "## Context"):
            self.assertNotIn(placeholder, generated)

    def test_fenced_blocks_and_subsections_stay_in_their_section(self):
        # Defects 2 and 3: a `# comment` inside a bash fence ended the section.
        got = self.extract(LAYOUT_CLAUDE_MD)
        bodies = {s["header"]: s["body"] for s in got["sections"]}
        self.assertEqual(
            bodies["⚠️ WORKFLOW: Navigator + Pilot Pipeline (interactive sessions only)"],
            WORKFLOW_BODY)
        self.assertEqual(bodies["Quick Start"], QUICK_START_BODY)
        self.assertEqual(
            got["custom_sections"]["Quick Start"], QUICK_START_BODY)
        generated = self.generate(got)
        self.assertIn(WORKFLOW_BODY, generated)
        self.assertIn("## Quick Start\n\n" + QUICK_START_BODY + "\n", generated)
        self.assertIn("## Code Standards\n\n- Go 1.22", generated)

    def test_runtime_paragraph_in_a_custom_named_section_is_recognized(self):
        # Defect 4: the template's "## Navigator" was added beside the
        # project's "## Navigator Integration", runtime text twice.
        got = self.extract(LAYOUT_CLAUDE_MD)
        self.assertEqual(got["navigator_section"], "Navigator Integration")
        self.assertNotIn("Navigator Integration", got["custom_sections"])
        generated = self.generate(got)
        self.assertEqual(generated.count("**Navigator runtime**:"), 1)
        self.assertEqual(generated.count("## Navigator"), 1)
        self.assertNotIn("\n## Navigator\n", generated)
        self.assertNotIn("## Project-Specific Code Standards", generated)

    def test_sections_keep_their_source_order(self):
        # Defect 5: custom sections were re-anchored to the template's order.
        got = self.extract(LAYOUT_CLAUDE_MD)
        generated = self.generate(got)
        headers = [h.strip() for h in re.findall(r"^## (.+?)\s*$", generated, re.MULTILINE)]
        self.assertEqual(headers, [
            "Who is reading this file?",
            "⚠️ WORKFLOW: Navigator + Pilot Pipeline (interactive sessions only)",
            "Quick Start", "Code Standards", "Navigator Integration",
            "Forbidden Actions", "Current Status",
        ])

    def test_round_trip_changes_only_the_stamp_lines(self):
        got = self.extract(LAYOUT_CLAUDE_MD)
        generated = self.generate(got)
        self.assertEqual(_changed_lines(LAYOUT_CLAUDE_MD, generated), [
            "-**Last Updated**: 2026-10-17",
            "-**Navigator Version**: 8.4.4",
            "+**Last Updated**: 2026-11-01",
            "+**Navigator Version**: 8.4.12",
        ])

    def test_cli_round_trip_matches_the_function(self):
        source = self.project / "CLAUDE.md"
        source.write_text(LAYOUT_CLAUDE_MD, encoding="utf-8")
        _write_state_file(self.project, datetime.now(tz=timezone.utc))
        extracted = subprocess.run(
            [sys.executable, SCRIPT, "extract", "CLAUDE.md"],
            capture_output=True, text=True, env=_env_without_hook_vars(),
            cwd=str(self.project))
        self.assertEqual(extracted.returncode, 0, extracted.stderr)
        customizations = self.project / "c.json"
        customizations.write_text(extracted.stdout)
        out = self.project / "preview.md"
        result = subprocess.run(
            [sys.executable, SCRIPT, "generate",
             "--customizations", str(customizations), "--template", str(TEMPLATE_PATH),
             "--output", str(out), "--stamp-version", "8.4.12",
             "--stamp-date", "2026-11-01"],
            capture_output=True, text=True, env=_env_without_hook_vars(),
            cwd=str(self.project))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(_changed_lines(LAYOUT_CLAUDE_MD, out.read_text())), 4)

    def test_outdated_runtime_paragraph_is_replaced_in_place(self):
        # The paragraph is the one piece of prose Navigator owns: an older
        # wording is replaced with the installed template's, the section's
        # header and every other line stay.
        outdated = LAYOUT_CLAUDE_MD.replace(RUNTIME_PARAGRAPH, OLD_RUNTIME_PARAGRAPH)
        got = self.extract(outdated)
        self.assertEqual(got["navigator_section"], "Navigator Integration")
        generated = self.generate(got)
        self.assertIn("## Navigator Integration\n\n", generated)
        self.assertIn(RUNTIME_PARAGRAPH + "\n\n**Last Updated**: 2026-11-01\n", generated)
        self.assertNotIn("(v7+)", generated)
        self.assertEqual(
            sorted(_changed_lines(outdated, generated)),
            sorted(["-" + line for line in OLD_RUNTIME_PARAGRAPH.splitlines()]
                   + ["-**Last Updated**: 2026-10-17", "-**Navigator Version**: 8.4.4"]
                   + ["+" + line for line in RUNTIME_PARAGRAPH.splitlines()]
                   + ["+**Last Updated**: 2026-11-01", "+**Navigator Version**: 8.4.12"]))

    def test_exact_navigator_section_takes_the_template_body(self):
        text = LAYOUT_CLAUDE_MD.replace("## Navigator Integration", "## Navigator")
        got = self.extract(text)
        self.assertEqual(got["navigator_section"], "Navigator")
        generated = self.generate(got)
        self.assertIn("## Navigator\n\n" + NAVIGATOR_SECTION + "\n", generated)
        self.assertNotIn("/nav-start              # Start session", generated)
        self.assertEqual(generated.count("## Navigator"), 1)

    def test_file_without_runtime_paragraph_or_stamps_gets_them_without_placeholders(self):
        text = "\n".join([
            "# Widgets", "", "## Build", "", "```bash", "# make it", "make", "```", "",
            "## Forbidden Actions", "", "- ❌ Never push to main", "",
        ])
        got = self.extract(text)
        self.assertEqual(got["navigator_section"], "")
        generated = self.generate(got)
        self.assertTrue(generated.startswith(
            "# Widgets\n\n## Context\n\n**Last Updated**: 2026-11-01\n"
            "**Navigator Version**: 8.4.12\n\n## Navigator\n\n"))
        self.assertIn("## Build\n\n```bash\n# make it\nmake\n```\n", generated)
        self.assertIn("## Forbidden Actions\n\n- ❌ Never push to main\n", generated)
        self.assertNotIn("[", generated.split("## Navigator")[0])
        headers = re.findall(r"^## (.+?)\s*$", generated, re.MULTILINE)
        self.assertEqual(headers, [
            "Context", "Navigator", "Project-Specific Code Standards",
            "Build", "Forbidden Actions"])

    def test_extract_is_stable_across_a_second_sync(self):
        got = self.extract(LAYOUT_CLAUDE_MD)
        generated = self.generate(got, version="8.4.4", today="2026-10-17")
        self.assertEqual(generated, LAYOUT_CLAUDE_MD)
        again = self.project / "again.md"
        again.write_text(generated, encoding="utf-8")
        second = claude_updater.extract_customizations(str(again))
        self.assertEqual(dict(second, source_dir=None), dict(got, source_dir=None))


class FenceAwareHeaderTests(unittest.TestCase):
    def test_comment_lines_inside_fences_are_not_headers(self):
        text = "# T\n\n## A\n\n```bash\n# not a header\n## nor this\n```\n\n## B\n\nb\n"
        titles = [t for _l, t, _s, _e in claude_updater._scan_headers(text)]
        self.assertEqual(titles, ["T", "A", "B"])
        self.assertEqual(claude_updater.extract_section(text, "A"),
                         "```bash\n# not a header\n## nor this\n```")

    def test_tilde_fences_and_unclosed_fence(self):
        text = "# T\n\n## A\n\n~~~\n# x\n~~~\n\n## B\n\n```\n# y\n"
        titles = [t for _l, t, _s, _e in claude_updater._scan_headers(text)]
        self.assertEqual(titles, ["T", "A", "B"])
        self.assertEqual(claude_updater.extract_section(text, "B"), "```\n# y")


class StampTests(unittest.TestCase):
    """Defect 2: the generated file carried the template's own version/date."""

    def test_cli_stamps_installed_plugin_version_and_today(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write_state_file(project, datetime.now(tz=timezone.utc))
            (project / "CLAUDE.md").write_text(CURRENT_CLAUDE_MD, encoding="utf-8")
            customizations = project / "customizations.json"
            customizations.write_text(json.dumps(
                claude_updater.extract_customizations(str(project / "CLAUDE.md"))))
            out = project / "out.md"

            result = subprocess.run(
                [sys.executable, SCRIPT, "generate",
                 "--customizations", str(customizations),
                 "--template", str(TEMPLATE_PATH), "--output", str(out)],
                capture_output=True, text=True, env=_env_without_hook_vars(),
                cwd=str(project),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            generated = out.read_text(encoding="utf-8")
            self.assertIn(f"**Navigator Version**: {_repo_plugin_version()}\n", generated)
            self.assertIn(f"**Last Updated**: {datetime.now().date().isoformat()}\n", generated)
            template = TEMPLATE_PATH.read_text(encoding="utf-8")
            for stale in ("7.0.0-alpha", "2026-07-10"):
                if stale in template:
                    self.assertNotIn(stale, generated)

    def test_installed_plugin_version_is_this_checkout(self):
        self.assertEqual(claude_updater.installed_plugin_version(), _repo_plugin_version())

    def test_stamp_flags_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write_state_file(project, datetime.now(tz=timezone.utc))
            customizations = project / "customizations.json"
            customizations.write_text(json.dumps(EMPTY_CUSTOMIZATIONS))
            out = project / "out.md"
            result = subprocess.run(
                [sys.executable, SCRIPT, "generate",
                 "--customizations", str(customizations),
                 "--template", str(TEMPLATE_PATH), "--output", str(out),
                 "--stamp-version", "1.2.3", "--stamp-date", "2030-01-02"],
                capture_output=True, text=True, env=_env_without_hook_vars(),
                cwd=str(project),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            generated = out.read_text(encoding="utf-8")
            self.assertIn("**Navigator Version**: 1.2.3\n", generated)
            self.assertIn("**Last Updated**: 2030-01-02\n", generated)


class ProjectRootTests(unittest.TestCase):
    """Defect 1: the guard looked beside --output, so a dry run to /tmp failed."""

    def _generate(self, customizations_path: Path, output: Path, cwd: Path,
                  extra=()) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, SCRIPT, "generate",
             "--customizations", str(customizations_path),
             "--template", str(TEMPLATE_PATH), "--output", str(output), *extra],
            capture_output=True, text=True, env=_env_without_hook_vars(), cwd=str(cwd),
        )

    def test_dry_run_to_another_directory_uses_the_source_dir(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as other:
            project, elsewhere = Path(tmp), Path(other)
            _write_state_file(project, datetime.now(tz=timezone.utc))
            (project / "CLAUDE.md").write_text(CURRENT_CLAUDE_MD, encoding="utf-8")
            extracted = subprocess.run(
                [sys.executable, SCRIPT, "extract", "CLAUDE.md"],
                capture_output=True, text=True, env=_env_without_hook_vars(),
                cwd=str(project),
            )
            self.assertEqual(extracted.returncode, 0, extracted.stderr)
            customizations = elsewhere / "customizations.json"
            customizations.write_text(extracted.stdout)
            self.assertEqual(json.loads(extracted.stdout)["source_dir"],
                             str(project.resolve()))

            # cwd and --output are both outside the project: only the
            # recorded source_dir can prove liveness.
            result = self._generate(customizations, elsewhere / "dry-run.md", cwd=elsewhere)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((elsewhere / "dry-run.md").exists())
            self.assertFalse((elsewhere / ".agent").exists())

    def test_project_root_flag_wins(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as other:
            project, elsewhere = Path(tmp), Path(other)
            _write_state_file(project, datetime.now(tz=timezone.utc))
            customizations = elsewhere / "customizations.json"
            customizations.write_text(json.dumps(EMPTY_CUSTOMIZATIONS))  # no source_dir

            result = self._generate(customizations, elsewhere / "x.md", cwd=elsewhere,
                                    extra=("--project-root", str(project)))

            self.assertEqual(result.returncode, 0, result.stderr)

    def test_cwd_is_the_root_without_flag_or_source_dir(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as other:
            project, elsewhere = Path(tmp), Path(other)
            _write_state_file(project, datetime.now(tz=timezone.utc))
            customizations = elsewhere / "customizations.json"
            customizations.write_text(json.dumps(EMPTY_CUSTOMIZATIONS))

            # Output goes INTO the live project, cwd is elsewhere: the old
            # output-relative lookup would pass; the root is cwd, so it refuses.
            result = self._generate(customizations, project / "CLAUDE.md", cwd=elsewhere)

            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertIn(str(elsewhere.resolve() / ".agent"), result.stderr)
            self.assertFalse((project / "CLAUDE.md").exists())


if __name__ == "__main__":
    unittest.main()
