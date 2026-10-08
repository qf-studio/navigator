#!/usr/bin/env python3
"""
Release validator for Navigator plugin.

Validates plugin integrity before release:
- All skills in plugin.json exist
- All skills are committed (not untracked)
- Version consistency across files
- Tag contains all expected files

Usage:
    python3 release_validator.py --check-all
    python3 release_validator.py --check-version 5.1.0
    python3 release_validator.py --verify-tag v5.1.0

Created: 2025-01-13 (after v5.1.0 missing nav-profile incident)
"""

import argparse
import json
import os
import re
import subprocess
import tempfile
import sys
from pathlib import Path
from typing import List, Tuple, Dict


def _strip_dot_slash(path: str) -> str:
    """Strip a single leading './' from a path.

    `str.lstrip("./")` strips ANY leading '.' and '/' characters, so it would
    mangle a path whose first segment begins with a dot (e.g. './.config' →
    'config'). This removes only the literal './' prefix.
    """
    return path[2:] if path.startswith("./") else path


def get_project_root() -> Path:
    """Find project root (contains .claude-plugin/)."""
    current = Path.cwd()
    while current != current.parent:
        if (current / ".claude-plugin" / "plugin.json").exists():
            return current
        current = current.parent
    return Path.cwd()


def load_plugin_json(root: Path) -> dict:
    """Load plugin.json configuration."""
    plugin_path = root / ".claude-plugin" / "plugin.json"
    if not plugin_path.exists():
        return {}
    with open(plugin_path) as f:
        return json.load(f)


def check_skills_exist(root: Path, plugin: dict) -> Tuple[List[str], List[str]]:
    """
    Check all skills referenced in plugin.json exist.

    Returns:
        (existing_skills, missing_skills)
    """
    skills = plugin.get("skills", [])
    existing = []
    missing = []

    for skill_path in skills:
        # Normalize path (remove ./ prefix)
        clean_path = _strip_dot_slash(skill_path)
        skill_dir = root / clean_path
        skill_md = skill_dir / "SKILL.md"

        if skill_md.exists():
            existing.append(clean_path)
        else:
            missing.append(clean_path)

    return existing, missing


def check_skills_committed(root: Path, plugin: dict) -> Tuple[List[str], List[str], List[str]]:
    """
    Check git status of all skills.

    Returns:
        (committed, modified, untracked)
    """
    skills = plugin.get("skills", [])
    committed = []
    modified = []
    untracked = []

    # Get git status
    result = subprocess.run(
        ["git", "status", "--porcelain", "skills/"],
        capture_output=True,
        text=True,
        cwd=root
    )

    status_lines = result.stdout.strip().split("\n") if result.stdout.strip() else []

    # Parse status
    modified_paths = set()
    untracked_paths = set()

    for line in status_lines:
        if not line:
            continue
        status = line[:2]
        path = line[3:].strip()

        if status.startswith("?"):
            untracked_paths.add(path)
        elif status.strip():
            modified_paths.add(path)

    # Check each skill
    for skill_path in skills:
        clean_path = _strip_dot_slash(skill_path)

        # Check if any file in skill dir is modified/untracked
        is_modified = any(p.startswith(clean_path) for p in modified_paths)
        is_untracked = any(p.startswith(clean_path) for p in untracked_paths)

        if is_untracked:
            untracked.append(clean_path)
        elif is_modified:
            modified.append(clean_path)
        else:
            committed.append(clean_path)

    return committed, modified, untracked


def check_version_consistency(root: Path) -> Dict[str, str]:
    """
    Check version across all relevant files.

    Returns:
        dict mapping filename to version found
    """
    versions = {}

    # plugin.json
    plugin_path = root / ".claude-plugin" / "plugin.json"
    if plugin_path.exists():
        with open(plugin_path) as f:
            data = json.load(f)
            versions["plugin.json"] = data.get("version", "NOT_FOUND")

    # marketplace.json
    marketplace_path = root / ".claude-plugin" / "marketplace.json"
    if marketplace_path.exists():
        with open(marketplace_path) as f:
            data = json.load(f)
            versions["marketplace.json"] = data.get("metadata", {}).get("version", "NOT_FOUND")

    # CLAUDE.md (Navigator Version line)
    claude_md = root / "CLAUDE.md"
    if claude_md.exists():
        content = claude_md.read_text()
        match = re.search(r'\*\*Navigator Version\*\*:\s*(\d+\.\d+\.\d+)', content)
        if match:
            versions["CLAUDE.md"] = match.group(1)
        else:
            versions["CLAUDE.md"] = "NOT_FOUND"

    # README.md badge
    readme = root / "README.md"
    if readme.exists():
        content = readme.read_text()
        match = re.search(r'version-(\d+\.\d+\.\d+)-blue', content)
        if match:
            versions["README.md"] = match.group(1)
        else:
            versions["README.md"] = "NOT_FOUND"

    # .nav-config.json
    nav_config = root / ".agent" / ".nav-config.json"
    if nav_config.exists():
        with open(nav_config) as f:
            data = json.load(f)
            versions[".nav-config.json"] = data.get("version", "NOT_FOUND")

    return versions


def verify_tag_contents(root: Path, tag: str) -> Tuple[List[str], List[str]]:
    """
    Verify tag contains all expected skills.

    Returns:
        (found_in_tag, missing_from_tag)
    """
    plugin = load_plugin_json(root)
    skills = plugin.get("skills", [])

    found = []
    missing = []

    for skill_path in skills:
        clean_path = _strip_dot_slash(skill_path)
        skill_md_path = f"{clean_path}/SKILL.md"

        # Check if file exists in tag
        result = subprocess.run(
            ["git", "ls-tree", tag, skill_md_path],
            capture_output=True,
            text=True,
            cwd=root
        )

        if result.stdout.strip():
            found.append(clean_path)
        else:
            missing.append(clean_path)

    return found, missing


def print_validation_report(
    existing: List[str],
    missing: List[str],
    committed: List[str],
    modified: List[str],
    untracked: List[str],
    versions: Dict[str, str]
) -> bool:
    """Print validation report and return True if passed."""

    print("━" * 50)
    print("NAVIGATOR RELEASE VALIDATION")
    print("━" * 50)
    print()

    # Skills existence check
    print("Skills Check:")
    all_skills = existing + missing
    for skill in sorted(all_skills):
        if skill in existing:
            status = "exists"
            if skill in committed:
                status += ", committed"
            elif skill in modified:
                status += ", MODIFIED"
            elif skill in untracked:
                status += ", UNTRACKED"
            print(f"  [{'x' if skill in existing else ' '}] {skill:<20} {'✓' if skill in committed else '⚠'} {status}")
        else:
            print(f"  [ ] {skill:<20} ✗ MISSING")
    print()

    # Version check
    print("Version Check:")
    version_values = list(versions.values())
    expected_version = version_values[0] if version_values else "UNKNOWN"
    all_match = all(v == expected_version for v in version_values if v != "NOT_FOUND")

    for filename, version in versions.items():
        match_indicator = "✓" if version == expected_version else "← MISMATCH"
        print(f"  {filename:<20} {version} {match_indicator if version != expected_version else '✓'}")
    print()

    # Git status summary
    print("Git Status:")
    print(f"  Uncommitted skills: {len(modified)} {'✓' if len(modified) == 0 else '⚠'}")
    print(f"  Untracked skills:   {len(untracked)} {'✓' if len(untracked) == 0 else '⚠'}")
    print()

    # Final result
    print("━" * 50)
    passed = len(missing) == 0 and len(modified) == 0 and len(untracked) == 0 and all_match

    if passed:
        print("VALIDATION: PASSED ✓")
    else:
        print("VALIDATION: FAILED ✗")
        print()
        if missing:
            print(f"  Missing skills: {', '.join(missing)}")
        if modified:
            print(f"  Modified skills: {', '.join(modified)}")
        if untracked:
            print(f"  Untracked skills: {', '.join(untracked)}")
        if not all_match:
            print(f"  Version mismatch detected")

    print("━" * 50)

    return passed


HOOK_STDIN_FIXTURES = {
    "SessionStart": '{"cwd": "."}',
    "PreCompact": '{"cwd": ".", "trigger": "manual"}',
    "PostCompact": '{"cwd": ".", "compact_summary": ""}',
    "Stop": '{"cwd": "."}',
    "UserPromptSubmit": '{"prompt": "hello", "cwd": "."}',
    "PreToolUse": '{"tool_name": "Read", "tool_input": {"file_path": "/tmp/_release_validator_noop"}, "cwd": "."}',
    "PostToolUse": '{"tool_name": "Edit", "tool_input": {}, "tool_response": {}, "cwd": "."}',
}

# Events whose hooks are expected to emit visible payload on a normal invocation.
# Silent exit 0 on these is the v6.14.0 regression signature.
# Other events (Stop, UserPromptSubmit, PreToolUse, PostToolUse) are side-effect-only
# or blocking-only by design — silent exit 0 is correct behavior there.
HOOK_EMITS_PAYLOAD = {"SessionStart", "PreCompact", "PostCompact"}


# Env vars that change what a manifest hook does and must not leak from the caller's
# session into the smoke test: the mod's ownership list (inside a Claude Code session the
# Python dispatcher skips every owned op and exits silently, which looks like the mem-036
# signature) and the Pilot belt (disables blocking behaviour).
HOOK_ENV_SCRUB = ("CLAUDE_PLUGIN_ROOT", "NAVIGATOR_MOD_OWNS", "PILOT_EXECUTOR", "HOME")

# The manifest's fallback when CLAUDE_PLUGIN_ROOT is unset (see .claude-plugin/plugin.json).
MARKETPLACE_FALLBACK = Path(".claude") / "plugins" / "marketplaces" / "navigator-marketplace"


def _hook_envs(root: Path, tmp_home: Path) -> Dict[str, Dict[str, str]]:
    """
    Build the two environments verify_hooks runs every manifest command under.

    "set":   CLAUDE_PLUGIN_ROOT points at `root` — the code under release, not a cached
             install — with the real HOME so personal config is visible.
    "unset": no CLAUDE_PLUGIN_ROOT; HOME is `tmp_home`, inside which the marketplace
             fallback path is a symlink to `root`. The command must resolve through the
             fallback (mem-036); a runner or laptop without the real fallback dir would
             otherwise fail for a reason unrelated to the plugin.
    """
    base = {k: v for k, v in os.environ.items() if k not in HOOK_ENV_SCRUB}
    home = os.environ.get("HOME", str(Path.home()))
    link = tmp_home / MARKETPLACE_FALLBACK
    link.parent.mkdir(parents=True, exist_ok=True)
    if not link.exists():
        link.symlink_to(root, target_is_directory=True)
    return {
        "set": {**base, "HOME": home, "CLAUDE_PLUGIN_ROOT": str(root)},
        "unset": {**base, "HOME": str(tmp_home)},
    }


def verify_hooks(root: Path, plugin: dict) -> Tuple[List[Dict], List[Dict]]:
    """
    Smoke-test every plugin manifest hook command end-to-end under both
    set and unset $CLAUDE_PLUGIN_ROOT (environments from _hook_envs: the set path uses the
    repo under release, the unset path a tmp HOME whose marketplace fallback links to it).

    Detects the v6.14.0 class of bug where a manifest shell guard silently
    short-circuits (exit 0, no stdout, no stderr) when the variable is
    not bound by Claude Code in the hook spawn environment.

    Returns:
        (passed_checks, failed_checks) — each check is a dict with keys
        event, command_summary, env_state, exit_code, stdout_len,
        stderr_len, status, and (on failure) reason.
    """
    hooks = plugin.get("hooks", {})
    passed: List[Dict] = []
    failed: List[Dict] = []
    with tempfile.TemporaryDirectory(prefix="nav-verify-hooks-") as tmp_home:
        envs = _hook_envs(root, Path(tmp_home))
        _run_hook_matrix(root, hooks, envs, passed, failed)
    return passed, failed


def _run_hook_matrix(root: Path, hooks: dict, envs: Dict[str, Dict[str, str]],
                     passed: List[Dict], failed: List[Dict]) -> None:
    for event, entries in hooks.items():
        fixture = HOOK_STDIN_FIXTURES.get(event, '{"cwd": "."}')
        for entry in entries:
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                if not cmd:
                    continue
                summary = cmd[:80] + ("..." if len(cmd) > 80 else "")

                for env_state, env in envs.items():
                    try:
                        result = subprocess.run(
                            ["bash", "-c", cmd],
                            input=fixture,
                            capture_output=True,
                            text=True,
                            timeout=15,
                            env=env,
                            cwd=root,
                        )
                        stdout_len = len(result.stdout.strip())
                        stderr_len = len(result.stderr.strip())
                        exit_code = result.returncode
                        # v6.14.0 regression signature: a payload-emitting hook
                        # silently exits 0 with no output on either channel.
                        # Side-effect-only hooks (Stop, PreToolUse counter, PostToolUse
                        # sync) are silent by design — don't flag those.
                        is_silent_failure = (
                            event in HOOK_EMITS_PAYLOAD
                            and exit_code == 0
                            and stdout_len == 0
                            and stderr_len == 0
                        )
                        if is_silent_failure:
                            failed.append({
                                "event": event, "command_summary": summary,
                                "env_state": env_state, "exit_code": exit_code,
                                "stdout_len": stdout_len, "stderr_len": stderr_len,
                                "status": "fail",
                                "reason": "silent exit 0 — payload-emitting hook produced no output",
                            })
                        else:
                            passed.append({
                                "event": event, "command_summary": summary,
                                "env_state": env_state, "exit_code": exit_code,
                                "stdout_len": stdout_len, "stderr_len": stderr_len,
                                "status": "pass",
                            })
                    except subprocess.TimeoutExpired:
                        failed.append({
                            "event": event, "command_summary": summary,
                            "env_state": env_state, "exit_code": -1,
                            "stdout_len": 0, "stderr_len": 0,
                            "status": "fail", "reason": "timeout (>15s)",
                        })


def verify_hook_paths(root: Path, plugin: dict) -> Tuple[List[str], List[str]]:
    """
    Statically assert every hook command in plugin.json references a
    hooks/<name>.py file that exists on disk.

    Catches the v6.15.5/v6.15.6 regression class: a deleted hook left
    registered in the published manifest. verify_hooks() runs the command,
    but a missing-file PostToolUse hook exits 2 and is classified 'pass'
    (PostToolUse is silent-by-design), so a static existence check is a
    required separate gate.

    Returns:
        (resolved, missing) — resolved are "event: hooks/<name>" strings;
        missing are the offending full command strings.
    """
    hooks = plugin.get("hooks", {})
    resolved: List[str] = []
    missing: List[str] = []

    for event, entries in hooks.items():
        for entry in entries:
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                match = re.search(r"/hooks/(\w+\.py)", cmd)
                if not match:
                    continue
                name = match.group(1)
                if (root / "hooks" / name).exists():
                    resolved.append(f"{event}: hooks/{name}")
                else:
                    missing.append(f"{event}: {cmd}")

    return resolved, missing


_OWNED_RE = re.compile(r"export const OWNED[^=]*=\s*\[([^\]]*)\]")
_OPSPEC_RE = re.compile(r'OpSpec\(\s*"([a-z0-9_]+)"')


def verify_mod(root: Path, run_generator: bool = True) -> Tuple[bool, List[str]]:
    """
    Static gate for the v8 Navigator mod (TASK-84).

    - hooks/hooks.json names exactly one hooks module, and that file exists;
    - every op name in hooks/mod/owns.ts OWNED is a Python op in
      hooks/nav_hook_lib/registry.py (else NAVIGATOR_MOD_OWNS would silence nothing, or the
      Python fallback for it would not exist) and has hooks/mod/ops/<name>.ts
      (the mem-070 missing-artifact class);
    - generated TS data matches the Python runtime (scripts/gen_mod_data.py --check).

    Returns (ok, problems).
    """
    problems: List[str] = []
    hooks_json = root / "hooks" / "hooks.json"
    try:
        modules = json.loads(hooks_json.read_text(encoding="utf-8")).get("modules")
    except (OSError, ValueError):
        modules = None
    if not isinstance(modules, list) or len(modules) != 1:
        problems.append("hooks/hooks.json: expected exactly one entry in 'modules'")
    else:
        module_path = (hooks_json.parent / str(modules[0])).resolve()
        if not module_path.is_file():
            problems.append(f"hooks/hooks.json: module {modules[0]} does not exist")

    owns = root / "hooks" / "mod" / "owns.ts"
    try:
        match = _OWNED_RE.search(owns.read_text(encoding="utf-8"))
    except OSError:
        match = None
    if match is None:
        problems.append("hooks/mod/owns.ts: OWNED list not found")
        owned: List[str] = []
    else:
        owned = re.findall(r"'([a-z0-9_]+)'", match.group(1))

    try:
        registry_ops = set(_OPSPEC_RE.findall(
            (root / "hooks" / "nav_hook_lib" / "registry.py").read_text(encoding="utf-8")))
    except OSError:
        registry_ops = set()
        problems.append("hooks/nav_hook_lib/registry.py: not readable")
    for name in owned:
        if name not in registry_ops:
            problems.append(f"owned op '{name}' is not in the Python registry (no fallback)")
        if not (root / "hooks" / "mod" / "ops" / f"{name}.ts").is_file():
            problems.append(f"owned op '{name}' has no hooks/mod/ops/{name}.ts")

    if run_generator:
        gen = root / "scripts" / "gen_mod_data.py"
        if gen.is_file():
            out = subprocess.run([sys.executable, str(gen), "--check"], cwd=root,
                                 capture_output=True, text=True)
            if out.returncode != 0:
                problems.append("generated mod data is stale: " + (out.stdout or out.stderr).strip())
    return not problems, problems


CONFORMANCE_RESULTS = Path("tests") / "harness-conformance" / "results"


def _registry_op_names(root: Path) -> List[str]:
    text = (root / "hooks" / "nav_hook_lib" / "registry.py").read_text(encoding="utf-8")
    return sorted(set(_OPSPEC_RE.findall(text)))


def verify_dispatcher(root: Path, plugin: dict) -> Tuple[List[str], List[str]]:
    """
    Gate for the Python fallback runtime (TASK-99, carried from TASK-64 Phase 1).

    - every manifest hook command routes through hooks/nav_dispatch.py (no hook may bypass
      the dispatcher's fail-open belt);
    - every op named by an OpSpec in hooks/nav_hook_lib/registry.py has hooks/ops/<name>.py
      that exists, is tracked by git, and imports cleanly — the v5.1.0 missing-skill
      incident generalized to ops (mem-070 class). verify_mod covers the mod side; this
      covers the side that runs when the mod does not.

    Returns (resolved, problems); resolved lists what passed, one line each.
    """
    resolved: List[str] = []
    problems: List[str] = []
    for event, entries in plugin.get("hooks", {}).items():
        for entry in entries:
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                if not cmd:
                    continue
                if "nav_dispatch.py" in cmd:
                    resolved.append(f"{event}: routes through nav_dispatch.py")
                else:
                    problems.append(f"{event}: hook command bypasses nav_dispatch.py — {cmd[:80]}")
    try:
        names = _registry_op_names(root)
    except OSError:
        return resolved, problems + ["hooks/nav_hook_lib/registry.py: not readable"]
    env = {k: v for k, v in os.environ.items() if k not in ("NAVIGATOR_MOD_OWNS", "PILOT_EXECUTOR")}
    hooks_dir = root / "hooks"
    for name in names:
        rel = Path("hooks") / "ops" / f"{name}.py"
        if not (root / rel).is_file():
            problems.append(f"op '{name}': {rel} does not exist")
            continue
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(rel)],
                                 cwd=root, capture_output=True, text=True)
        if tracked.returncode != 0:
            problems.append(f"op '{name}': {rel} is not tracked by git")
            continue
        code = f"import sys; sys.path.insert(0, {str(hooks_dir)!r}); import ops.{name}"
        try:
            imported = subprocess.run([sys.executable, "-c", code], cwd=root, env=env,
                                      capture_output=True, text=True, timeout=15)
        except subprocess.TimeoutExpired:
            problems.append(f"op '{name}': import timed out (>15s)")
            continue
        if imported.returncode != 0:
            tail = (imported.stderr.strip().splitlines() or ["no stderr"])[-1]
            problems.append(f"op '{name}': import failed — {tail}")
            continue
        resolved.append(f"op '{name}': {rel} exists, tracked, imports")
    return resolved, problems


def _installed_claude_version() -> str:
    out = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=15)
    return out.stdout.split()[0] if out.returncode == 0 and out.stdout.split() else ""


def verify_conformance(root: Path, version: str = "") -> Tuple[bool, List[str]]:
    """
    Gate from TASK-58/TASK-64: a harness-conformance results file must exist for the
    Claude Code version we ship against. `version` empty → `claude --version` (the local
    form, same as `make conformance-check`); CI passes the pinned version explicitly so the
    runner never needs the binary. Probes are live-driven and cannot run here; this only
    asserts the evidence was recorded (tests/harness-conformance/run.md re-drives it).
    """
    if not version:
        try:
            version = _installed_claude_version()
        except (OSError, subprocess.TimeoutExpired):
            version = ""
        if not version:
            return False, ["claude --version unavailable; pass the version: --verify-conformance <x.y.z>"]
    version = version.lstrip("v")
    results = root / CONFORMANCE_RESULTS / f"cc-{version}.json"
    rel = results.relative_to(root)
    if not results.is_file():
        return False, [f"MISSING conformance results for Claude Code {version}",
                       f"expected file: {rel}",
                       "re-drive the suite: tests/harness-conformance/run.md"]
    try:
        json.loads(results.read_text(encoding="utf-8"))
    except ValueError as exc:
        return False, [f"{rel}: not valid JSON ({exc})"]
    return True, []


def check_version_match(root: Path, expected: str) -> Tuple[Dict[str, str], List[str]]:
    """
    Compare an expected version (e.g. a release tag) against every
    version-bearing file. Strips a single leading 'v' from the tag.

    Returns:
        (versions, mismatches) — mismatches are "file=found" strings for any
        file whose version != expected.
    """
    if expected.startswith("v"):
        expected = expected[1:]
    versions = check_version_consistency(root)
    mismatches = [
        f"{name}={ver}" for name, ver in versions.items() if ver != expected
    ]
    return versions, mismatches


def main():
    parser = argparse.ArgumentParser(description="Validate Navigator plugin for release")
    parser.add_argument("--check-all", action="store_true", help="Run all validation checks")
    parser.add_argument("--check-version", type=str, help="Verify specific version")
    parser.add_argument("--verify-tag", type=str, help="Verify tag contains all skills")
    parser.add_argument("--verify-hooks", action="store_true",
                        help="Smoke-test plugin manifest hook commands under set/unset CLAUDE_PLUGIN_ROOT")
    parser.add_argument("--verify-hook-paths", action="store_true",
                        help="Statically assert every plugin.json hook command resolves to an existing hooks/<name>.py file")
    parser.add_argument("--verify-mod", action="store_true",
                        help="Static gate for the v8 mod: hooks module, OWNED ops on both sides, fresh generated data")
    parser.add_argument("--verify-dispatcher", action="store_true",
                        help="Every manifest hook routes through nav_dispatch.py; every registry op has a committed, importable hooks/ops/<name>.py")
    parser.add_argument("--verify-conformance", nargs="?", const="", default=None, metavar="CC_VERSION",
                        help="A harness-conformance results file exists for this Claude Code version (default: `claude --version`)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    root = get_project_root()
    plugin = load_plugin_json(root)

    if not plugin:
        print("Error: plugin.json not found", file=sys.stderr)
        return 1

    if args.verify_hooks:
        passed, failed = verify_hooks(root, plugin)
        if args.json:
            print(json.dumps({"passed": passed, "failed": failed}, indent=2))
        else:
            total = len(passed) + len(failed)
            print(f"Hook smoke-test: {len(passed)}/{total} passed, {len(failed)} failed")
            print()
            for chk in failed:
                print(f"  ❌ {chk['event']:18} [{chk['env_state']:5}] {chk['reason']}")
                print(f"     {chk['command_summary']}")
            for chk in passed:
                print(f"  ✓  {chk['event']:18} [{chk['env_state']:5}] "
                      f"exit={chk['exit_code']} out={chk['stdout_len']}B err={chk['stderr_len']}B")
        return 0 if not failed else 1

    if args.verify_dispatcher:
        resolved, problems = verify_dispatcher(root, plugin)
        if args.json:
            print(json.dumps({"resolved": resolved, "problems": problems}, indent=2))
        else:
            print("Dispatcher check (TASK-99): " + ("PASSED ✓" if not problems else f"FAILED ✗ — {len(problems)} problem(s)"))
            for problem in problems:
                print(f"  ❌ {problem}")
            for line in resolved:
                print(f"  ✓  {line}")
        return 0 if not problems else 1

    if args.verify_conformance is not None:
        ok, problems = verify_conformance(root, args.verify_conformance)
        if args.json:
            print(json.dumps({"ok": ok, "problems": problems}, indent=2))
        else:
            print("Conformance check (TASK-58): " + ("OK ✓" if ok else "FAILED ✗"))
            for problem in problems:
                print(f"  ❌ {problem}")
        return 0 if ok else 1

    if args.verify_mod:
        ok, problems = verify_mod(root)
        if args.json:
            print(json.dumps({"ok": ok, "problems": problems}, indent=2))
        else:
            print("Mod check (TASK-84): " + ("PASSED ✓" if ok else f"FAILED ✗ — {len(problems)} problem(s)"))
            for problem in problems:
                print(f"  ❌ {problem}")
        return 0 if ok else 1

    if args.verify_hook_paths:
        resolved, missing = verify_hook_paths(root, plugin)
        if args.json:
            print(json.dumps({"resolved": resolved, "missing": missing}, indent=2))
        else:
            total = len(resolved) + len(missing)
            print(f"Hook-path check: {len(resolved)}/{total} resolve to an existing file")
            for r in resolved:
                print(f"  ✓  {r}")
            for m in missing:
                print(f"  ❌ MISSING FILE — {m}")
            if missing:
                print(f"\nVALIDATION: FAILED ✗ — {len(missing)} hook command(s) reference a deleted/missing script")
        return 0 if not missing else 1

    if args.check_version:
        versions, mismatches = check_version_match(root, args.check_version)
        expected = args.check_version.lstrip("v") if args.check_version.startswith("v") else args.check_version
        if args.json:
            print(json.dumps({"expected": expected, "versions": versions, "mismatches": mismatches}, indent=2))
        else:
            print(f"Version-match check (expected {expected}):")
            for name, ver in versions.items():
                indicator = "✓" if ver == expected else "← MISMATCH"
                print(f"  {name:<20} {ver} {indicator}")
            if mismatches:
                print(f"\nVALIDATION: FAILED ✗ — {len(mismatches)} file(s) disagree with {expected}: {', '.join(mismatches)}")
            else:
                print(f"\nVALIDATION: PASSED ✓ — all files at {expected}")
        return 0 if not mismatches else 1

    if args.verify_tag:
        found, missing = verify_tag_contents(root, args.verify_tag)

        if args.json:
            print(json.dumps({"found": found, "missing": missing}))
        else:
            print(f"Tag {args.verify_tag} verification:")
            print(f"  Found: {len(found)} skills")
            print(f"  Missing: {len(missing)} skills")
            if missing:
                print(f"\nMissing from tag:")
                for skill in missing:
                    print(f"  - {skill}")
                return 1
            else:
                print("\n✓ All skills present in tag")

        return 0 if not missing else 1

    # Run all checks
    existing, missing = check_skills_exist(root, plugin)
    committed, modified, untracked = check_skills_committed(root, plugin)
    versions = check_version_consistency(root)

    if args.json:
        result = {
            "existing": existing,
            "missing": missing,
            "committed": committed,
            "modified": modified,
            "untracked": untracked,
            "versions": versions,
            "passed": len(missing) == 0 and len(modified) == 0 and len(untracked) == 0
        }
        print(json.dumps(result, indent=2))
        return 0 if result["passed"] else 1

    passed = print_validation_report(
        existing, missing, committed, modified, untracked, versions
    )

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
