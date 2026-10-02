#!/usr/bin/env python3
"""Unit tests for release_validator's static gates (verify_hook_paths, check_version_match).

These guard the v6.15.6 regression class: a deleted hook left registered in the
published manifest, and version drift across the bump files.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from release_validator import (  # noqa: E402
    verify_hook_paths,
    check_version_match,
    verify_mod,
    _strip_dot_slash,
)


def _make_mod_root(tmp: Path, modules, owned, op_files, registry_ops):
    """Minimal plugin root for verify_mod: hooks.json, owns.ts, op files, registry.py."""
    (tmp / "hooks" / "mod" / "ops").mkdir(parents=True)
    (tmp / "hooks" / "nav_hook_lib").mkdir(parents=True)
    (tmp / "hooks" / "hooks.json").write_text(json.dumps({"modules": modules}))
    if "./mod/register.tsx" in modules:
        (tmp / "hooks" / "mod" / "register.tsx").write_text("export const register = () => {}\n")
    names = ", ".join(f"'{n}'" for n in owned)
    (tmp / "hooks" / "mod" / "owns.ts").write_text(
        f"export const OWNED: readonly string[] = [{names}]\n")
    for name in op_files:
        (tmp / "hooks" / "mod" / "ops" / f"{name}.ts").write_text("export {}\n")
    rows = ",\n".join(f'        OpSpec("{n}", "injectors", None, None, 100)' for n in registry_ops)
    (tmp / "hooks" / "nav_hook_lib" / "registry.py").write_text(
        f'EVENT_OPS = {{\n    "X": [\n{rows}\n    ],\n}}\n')


class VerifyModTest(unittest.TestCase):
    """TASK-84: the v8 mod must be declared, and every op it owns must exist on both sides."""

    def test_consistent_mod_passes(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _make_mod_root(tmp, ["./mod/register.tsx"], ["a_op"], ["a_op"], ["a_op", "b_op"])
            ok, problems = verify_mod(tmp, run_generator=False)
            self.assertEqual(problems, [])
            self.assertTrue(ok)

    def test_owned_op_missing_ts_file_is_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _make_mod_root(tmp, ["./mod/register.tsx"], ["a_op"], [], ["a_op"])
            ok, problems = verify_mod(tmp, run_generator=False)
            self.assertFalse(ok)
            self.assertTrue(any("a_op" in p and ".ts" in p for p in problems))

    def test_owned_op_unknown_to_python_is_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _make_mod_root(tmp, ["./mod/register.tsx"], ["ghost"], ["ghost"], ["a_op"])
            ok, problems = verify_mod(tmp, run_generator=False)
            self.assertFalse(ok)
            self.assertTrue(any("ghost" in p and "registry" in p for p in problems))

    def test_missing_module_file_is_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _make_mod_root(tmp, ["./mod/gone.tsx"], [], [], ["a_op"])
            ok, problems = verify_mod(tmp, run_generator=False)
            self.assertFalse(ok)
            self.assertTrue(any("gone.tsx" in p for p in problems))

    def test_real_repo_mod_is_consistent(self):
        root = Path(__file__).resolve().parents[3]
        ok, problems = verify_mod(root, run_generator=False)
        self.assertEqual(problems, [])


def _make_root(tmp: Path, hook_names, manifest_hooks):
    """Build a minimal project root: hooks/ with the given files + a plugin.json."""
    (tmp / ".claude-plugin").mkdir(parents=True)
    (tmp / "hooks").mkdir()
    for name in hook_names:
        (tmp / "hooks" / name).write_text("# stub\n")
    (tmp / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "navigator", "version": "6.15.6", "hooks": manifest_hooks})
    )


def _cmd(name):
    return {
        "type": "command",
        "command": f'python3 "${{CLAUDE_PLUGIN_ROOT:-x}}/hooks/{name}"',
        "timeout": 5,
    }


class VerifyHookPathsTest(unittest.TestCase):
    def test_all_hooks_resolve(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _make_root(
                tmp,
                ["a.py", "b.py"],
                {"SessionStart": [{"hooks": [_cmd("a.py")]}],
                 "Stop": [{"hooks": [_cmd("b.py")]}]},
            )
            plugin = json.loads((tmp / ".claude-plugin" / "plugin.json").read_text())
            resolved, missing = verify_hook_paths(tmp, plugin)
            self.assertEqual(missing, [])
            self.assertEqual(len(resolved), 2)

    def test_deleted_hook_is_flagged(self):
        # The exact v6.15.6 regression: a registered hook file does not exist.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _make_root(
                tmp,
                ["a.py"],
                {"SessionStart": [{"hooks": [_cmd("a.py")]}],
                 "PostToolUse": [{"matcher": "Bash",
                                  "hooks": [_cmd("nav_commit_reminder.py")]}]},
            )
            plugin = json.loads((tmp / ".claude-plugin" / "plugin.json").read_text())
            resolved, missing = verify_hook_paths(tmp, plugin)
            self.assertEqual(len(missing), 1)
            self.assertIn("nav_commit_reminder.py", missing[0])

    def test_command_without_hook_path_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _make_root(
                tmp, ["a.py"],
                {"Stop": [{"hooks": [{"type": "command", "command": "echo hi"}]}]},
            )
            plugin = json.loads((tmp / ".claude-plugin" / "plugin.json").read_text())
            resolved, missing = verify_hook_paths(tmp, plugin)
            self.assertEqual(missing, [])
            self.assertEqual(resolved, [])


class CheckVersionMatchTest(unittest.TestCase):
    def _root_with_versions(self, tmp, version):
        (tmp / ".claude-plugin").mkdir(parents=True)
        (tmp / ".agent").mkdir()
        (tmp / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"version": version}))
        (tmp / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps({"metadata": {"version": version}}))
        (tmp / "CLAUDE.md").write_text(f"**Navigator Version**: {version}\n")
        (tmp / "README.md").write_text(
            f"[![Version](https://img.shields.io/badge/version-{version}-blue.svg)](x)\n")
        (tmp / ".agent" / ".nav-config.json").write_text(
            json.dumps({"version": version}))

    def test_all_match(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self._root_with_versions(tmp, "6.15.6")
            _, mismatches = check_version_match(tmp, "6.15.6")
            self.assertEqual(mismatches, [])

    def test_tag_prefix_stripped(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self._root_with_versions(tmp, "6.15.6")
            _, mismatches = check_version_match(tmp, "v6.15.6")
            self.assertEqual(mismatches, [])

    def test_drift_is_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self._root_with_versions(tmp, "6.15.6")
            # Simulate one file left behind (README badge stale).
            (tmp / "README.md").write_text(
                "[![Version](https://img.shields.io/badge/version-6.15.5-blue.svg)](x)\n")
            _, mismatches = check_version_match(tmp, "6.15.6")
            self.assertTrue(any("README.md" in m for m in mismatches))


class StripDotSlashTest(unittest.TestCase):
    """wp11/TASK-51: prefix-only strip, not lstrip('./') char-class strip."""

    def test_strips_leading_dot_slash(self):
        self.assertEqual(_strip_dot_slash("./skills/x"), "skills/x")

    def test_no_prefix_unchanged(self):
        self.assertEqual(_strip_dot_slash("skills/x"), "skills/x")

    def test_preserves_dot_segment_after_prefix(self):
        self.assertEqual(_strip_dot_slash("./a/.b"), "a/.b")

    def test_demonstrates_lstrip_bug_is_fixed(self):
        # lstrip('./') eats the leading dot of a dotfile; the helper does not.
        self.assertEqual("./.config".lstrip("./"), "config")
        self.assertEqual(_strip_dot_slash("./.config"), ".config")


if __name__ == "__main__":
    unittest.main()
