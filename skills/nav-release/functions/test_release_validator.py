#!/usr/bin/env python3
"""Unit tests for release_validator's static gates (verify_hook_paths, check_version_match,
verify_mod, verify_dispatcher, verify_conformance) and the verify_hooks env builder.

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
    verify_dispatcher,
    verify_conformance,
    _hook_envs,
    _strip_dot_slash,
    MARKETPLACE_FALLBACK,
    CONFORMANCE_RESULTS,
)
import os  # noqa: E402
import subprocess  # noqa: E402


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

    def test_real_repo_mod_owns_every_registry_op(self):
        """v8.0 parity contract: every Python op has a mod twin and is owned by it."""
        import re
        root = Path(__file__).resolve().parents[3]
        owns = (root / "hooks" / "mod" / "owns.ts").read_text()
        block = re.search(r"export const OWNED[^=]*=\s*\[([^\]]*)\]", owns).group(1)
        owned = set(re.findall(r"'([a-z0-9_]+)'", block))
        registry = set(re.findall(r'OpSpec\(\s*"([a-z0-9_]+)"',
                                  (root / "hooks" / "nav_hook_lib" / "registry.py").read_text()))
        self.assertEqual(owned, registry)


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

# --- TASK-99: dispatcher gate --------------------------------------------------

_DISPATCH_CMD = {"type": "command",
                 "command": 'sh -c \'exec python3 "${CLAUDE_PLUGIN_ROOT:-x}/hooks/nav_dispatch.py" Stop\''}


def _git(tmp: Path, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          cwd=tmp, capture_output=True, text=True, check=True)


def _make_dispatcher_root(tmp: Path, registry_ops, op_bodies, manifest_hooks=None, commit=True):
    """Plugin root with registry.py, hooks/ops/<name>.py (body per op) and a git history."""
    (tmp / "hooks" / "ops").mkdir(parents=True)
    (tmp / "hooks" / "nav_hook_lib").mkdir(parents=True)
    (tmp / ".claude-plugin").mkdir()
    rows = ",\n".join(f'        OpSpec("{n}", "injectors", None, None, 100)' for n in registry_ops)
    (tmp / "hooks" / "nav_hook_lib" / "registry.py").write_text(
        f'EVENT_OPS = {{\n    "X": [\n{rows}\n    ],\n}}\n')
    (tmp / "hooks" / "ops" / "__init__.py").write_text("")
    for name, body in op_bodies.items():
        (tmp / "hooks" / "ops" / f"{name}.py").write_text(body)
    hooks = manifest_hooks if manifest_hooks is not None else {"Stop": [{"hooks": [_DISPATCH_CMD]}]}
    (tmp / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "navigator", "hooks": hooks}))
    _git(tmp, "init", "-q")
    if commit:
        _git(tmp, "add", "-A")
        _git(tmp, "commit", "-q", "-m", "init")
    return json.loads((tmp / ".claude-plugin" / "plugin.json").read_text())


class VerifyDispatcherTest(unittest.TestCase):
    def test_green_path(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d).resolve()
            plugin = _make_dispatcher_root(tmp, ["a", "b"], {"a": "X = 1\n", "b": "Y = 2\n"})
            resolved, problems = verify_dispatcher(tmp, plugin)
            self.assertEqual(problems, [])
            self.assertEqual(len(resolved), 3)  # one manifest line + two ops

    def test_registry_op_without_file(self):
        # The v5.1.0 incident generalized: registered, never written.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d).resolve()
            plugin = _make_dispatcher_root(tmp, ["a", "ghost"], {"a": "X = 1\n"})
            _, problems = verify_dispatcher(tmp, plugin)
            self.assertEqual(len(problems), 1)
            self.assertIn("ghost", problems[0])
            self.assertIn("does not exist", problems[0])

    def test_untracked_op_file(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d).resolve()
            plugin = _make_dispatcher_root(tmp, ["a"], {"a": "X = 1\n"})
            (tmp / "hooks" / "ops" / "late.py").write_text("Z = 3\n")
            reg = tmp / "hooks" / "nav_hook_lib" / "registry.py"
            reg.write_text(reg.read_text().replace('OpSpec("a"', 'OpSpec("late", "i", None, None, 1),\n        OpSpec("a"'))
            _, problems = verify_dispatcher(tmp, plugin)
            self.assertEqual(len(problems), 1)
            self.assertIn("late", problems[0])
            self.assertIn("not tracked", problems[0])

    def test_broken_import(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d).resolve()
            plugin = _make_dispatcher_root(tmp, ["a"], {"a": "import no_such_module_xyz\n"})
            _, problems = verify_dispatcher(tmp, plugin)
            self.assertEqual(len(problems), 1)
            self.assertIn("import failed", problems[0])
            self.assertIn("no_such_module_xyz", problems[0])

    def test_manifest_command_bypassing_dispatcher(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d).resolve()
            hooks = {"Stop": [{"hooks": [_DISPATCH_CMD]}],
                     "PostToolUse": [{"hooks": [{"type": "command",
                                                 "command": "python3 hooks/nav_commit_reminder.py"}]}]}
            plugin = _make_dispatcher_root(tmp, ["a"], {"a": "X = 1\n"}, manifest_hooks=hooks)
            _, problems = verify_dispatcher(tmp, plugin)
            self.assertEqual(len(problems), 1)
            self.assertTrue(problems[0].startswith("PostToolUse: hook command bypasses"))

    def test_repo_itself_is_green(self):
        root = Path(__file__).resolve().parents[3]
        plugin = json.loads((root / ".claude-plugin" / "plugin.json").read_text())
        _, problems = verify_dispatcher(root, plugin)
        self.assertEqual(problems, [])


# --- TASK-99: conformance gate --------------------------------------------------

class VerifyConformanceTest(unittest.TestCase):
    def _root(self, tmp: Path, files):
        (tmp / CONFORMANCE_RESULTS).mkdir(parents=True)
        for name, body in files.items():
            (tmp / CONFORMANCE_RESULTS / name).write_text(body)

    def test_results_file_present(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d); self._root(tmp, {"cc-2.1.287.json": "{}"})
            ok, problems = verify_conformance(tmp, "2.1.287")
            self.assertTrue(ok); self.assertEqual(problems, [])

    def test_v_prefix_is_tolerated(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d); self._root(tmp, {"cc-2.1.287.json": "{}"})
            self.assertTrue(verify_conformance(tmp, "v2.1.287")[0])

    def test_results_file_missing(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d); self._root(tmp, {"cc-2.1.241.json": "{}"})
            ok, problems = verify_conformance(tmp, "2.1.287")
            self.assertFalse(ok)
            self.assertIn("MISSING conformance results for Claude Code 2.1.287", problems[0])
            self.assertIn("cc-2.1.287.json", problems[1])

    def test_invalid_json_fails(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d); self._root(tmp, {"cc-2.1.287.json": "{not json"})
            ok, problems = verify_conformance(tmp, "2.1.287")
            self.assertFalse(ok); self.assertIn("not valid JSON", problems[0])


# --- TASK-99: verify_hooks environments -----------------------------------------

class HookEnvsTest(unittest.TestCase):
    def test_envs_are_hermetic(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d).resolve(); root = tmp / "repo"; home = tmp / "home"
            root.mkdir(); home.mkdir()
            saved = {k: os.environ.get(k) for k in ("NAVIGATOR_MOD_OWNS", "PILOT_EXECUTOR", "CLAUDE_PLUGIN_ROOT")}
            os.environ["NAVIGATOR_MOD_OWNS"] = "session_start"
            os.environ["PILOT_EXECUTOR"] = "1"
            os.environ["CLAUDE_PLUGIN_ROOT"] = "/elsewhere"
            try:
                envs = _hook_envs(root, home)
            finally:
                for k, v in saved.items():
                    if v is None: os.environ.pop(k, None)
                    else: os.environ[k] = v
            self.assertEqual(set(envs), {"set", "unset"})
            for env in envs.values():
                self.assertNotIn("NAVIGATOR_MOD_OWNS", env)
                self.assertNotIn("PILOT_EXECUTOR", env)
            self.assertEqual(envs["set"]["CLAUDE_PLUGIN_ROOT"], str(root))
            self.assertNotIn("CLAUDE_PLUGIN_ROOT", envs["unset"])
            self.assertEqual(envs["unset"]["HOME"], str(home))
            link = home / MARKETPLACE_FALLBACK
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), root)



if __name__ == "__main__":
    unittest.main()
