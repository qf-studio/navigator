#!/usr/bin/env python3
"""Manifest + shim contract tests for nav_dispatch (TASK-60, shim-manifest group).

stdlib unittest only, subprocess-driven per the test_workflow_enforcer.py
template. Three concerns:

1. Manifest shape — .claude-plugin/plugin.json references ONLY
   hooks/nav_dispatch.py, registers exactly the seven v6 event surfaces
   plus the six TASK-62 events that survived the validate-or-drop gate
   (SubagentStart, PostToolUseFailure, TaskCreated, TaskCompleted,
   ConfigChange, Setup — all accepted by `claude plugin validate` on CC
   2.1.205), with the contract matchers (PreToolUse: Read; PostToolUse:
   Edit|Write|MultiEdit|NotebookEdit; no matcher on any TASK-62 event) and
   timeouts (SessionStart 10, PostToolUse 10, PreCompact 30, PostCompact 10
   — the v6 allowances — all others 5, including every TASK-62 event).
   Each command is the fail-OPEN shell guard: the dispatcher
   file is [ -f ]-checked before exec, so a resolution miss exits 0
   silently instead of python3's loud exit 2 (which the harness treats as
   a block on every event).

2. mem-036 env variants — every event's LITERAL manifest command runs as a
   subprocess (sh -c, so ${VAR:-fallback} expands exactly as the harness
   would) under three CLAUDE_PLUGIN_ROOT variants:
     * set-to-repo: resolves to this checkout; the dispatcher must exit 0 on
       an empty payload (fail-open), and a seeded health file proves the
       guard actually DISPATCHES (not silently skips) when the file exists.
     * unset: sh substitutes the $HOME fallback. HOME is pointed at a temp
       dir carrying a STALE marketplace clone (pre-v7: no nav_dispatch.py) —
       the realistic fallback state. The guard must exit 0 silently: the old
       loud-exit-2 behavior fails CLOSED and blocks every event.
     * empty string: the :- operator treats empty like unset, so behavior
       must match the unset variant (same fallback resolution).

3. Shim contract — hooks/nav_dispatch.py stays under 40 lines and exits 0
   with no output on: empty JSON stdin, garbage stdin, missing event arg,
   unknown event (fail-open; must hold with or without nav_hook_lib.runtime).
"""

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
REPO_ROOT = HOOKS_DIR.parent
SHIM = HOOKS_DIR / "nav_dispatch.py"
PLUGIN_JSON = REPO_ROOT / ".claude-plugin" / "plugin.json"

EVENTS = (
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "PreCompact",
    "PostCompact",
    # TASK-62 event surfaces (validate-or-drop survivors, CC 2.1.205):
    "SubagentStart",
    "PostToolUseFailure",
    "TaskCreated",
    "TaskCompleted",
    "ConfigChange",
    "Setup",
)
# v6 allowances: PostToolUse hooks had 10s EACH, PostCompact 10s — the shared
# dispatcher must not regress them to the 5s default.
EXPECTED_TIMEOUTS = {
    "SessionStart": 10, "PostToolUse": 10, "PreCompact": 30, "PostCompact": 10,
}
DEFAULT_TIMEOUT = 5
EXPECTED_MATCHERS = {
    "PreToolUse": "Read",
    "PostToolUse": "Edit|Write|MultiEdit|NotebookEdit",
}
# Fail-OPEN shell guard: missing dispatcher file -> exit 0 silently (stdin
# passes through the exec). %s is the event name.
COMMAND_GUARD = (
    "sh -c 'f=\"${CLAUDE_PLUGIN_ROOT:-"
    "$HOME/.claude/plugins/marketplaces/navigator-marketplace}"
    "/hooks/nav_dispatch.py\"; "
    "if [ -f \"$f\" ]; then exec python3 \"$f\" %s; fi'"
)
FALLBACK_RELPATH = ".claude/plugins/marketplaces/navigator-marketplace"
# Wedge guard: generous vs the 5-30s manifest timeouts; TimeoutExpired = fail.
SUBPROCESS_TIMEOUT = 20


def load_manifest():
    return json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))


def single_hook_entry(testcase, manifest, event):
    """Assert the event has exactly one matcher group with one hook; return both."""
    groups = manifest["hooks"][event]
    testcase.assertEqual(len(groups), 1, f"{event}: expected exactly one matcher group")
    hooks = groups[0]["hooks"]
    testcase.assertEqual(len(hooks), 1, f"{event}: expected exactly one hook entry")
    return groups[0], hooks[0]


_ISOLATED_CONFIG_HOME = tempfile.TemporaryDirectory()


def clean_env(extra=None, drop=()):
    env = os.environ.copy()
    for key in ("PILOT_EXECUTOR", "CLAUDE_PROJECT_DIR", "CLAUDE_USER_MESSAGE"):
        env.pop(key, None)
    env["NAVIGATOR_CONFIG_HOME"] = _ISOLATED_CONFIG_HOME.name  # TASK-82
    for key in drop:
        env.pop(key, None)
    if extra:
        env.update(extra)
    return env


def run_shim(args, stdin="", env=None, cwd=None):
    return subprocess.run(
        ["python3", str(SHIM), *args],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=cwd or REPO_ROOT,
        env=env or clean_env(),
        timeout=SUBPROCESS_TIMEOUT,
    )


def run_manifest_command(command, env, cwd, stdin="{}"):
    """Run the literal manifest command through sh -c, as the harness does."""
    return subprocess.run(
        ["/bin/sh", "-c", command],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=SUBPROCESS_TIMEOUT,
    )


class ManifestShapeTest(unittest.TestCase):
    """plugin.json routes every event through nav_dispatch.py, nothing else."""

    def setUp(self):
        self.manifest = load_manifest()

    def test_only_nav_dispatch_referenced(self):
        raw = PLUGIN_JSON.read_text(encoding="utf-8")
        scripts = set(re.findall(r"hooks/[A-Za-z0-9_]+\.py", raw))
        self.assertEqual(scripts, {"hooks/nav_dispatch.py"})

    def test_exactly_the_registered_event_surfaces(self):
        # Seven v6 surfaces + six TASK-62 validate-or-drop survivors; every
        # registration maps to a committed dispatcher (v5.1.0 lesson) and to
        # a registry EVENT_OPS row (asserted in nav_hook_lib/test_registry).
        self.assertEqual(set(self.manifest["hooks"].keys()), set(EVENTS))

    def test_command_shape_per_event(self):
        for event in EVENTS:
            _, hook = single_hook_entry(self, self.manifest, event)
            self.assertEqual(hook["type"], "command", event)
            self.assertEqual(hook["command"], COMMAND_GUARD % event, event)

    def test_timeouts(self):
        for event in EVENTS:
            _, hook = single_hook_entry(self, self.manifest, event)
            expected = EXPECTED_TIMEOUTS.get(event, DEFAULT_TIMEOUT)
            self.assertEqual(hook["timeout"], expected, event)

    def test_matchers(self):
        for event in EVENTS:
            group, _ = single_hook_entry(self, self.manifest, event)
            if event in EXPECTED_MATCHERS:
                self.assertEqual(group.get("matcher"), EXPECTED_MATCHERS[event], event)
            else:
                self.assertNotIn("matcher", group, event)

    def test_shim_file_exists_in_same_commit(self):
        # v5.1.0 lesson: never reference a file the manifest commit does not carry.
        self.assertTrue(SHIM.is_file())


class ManifestEnvVariantTest(unittest.TestCase):
    """mem-036: run each event's literal manifest command under 3 env variants.

    The fallback marketplace clone realistically predates v7 (no
    nav_dispatch.py), so ``stale_home`` ships one. The guard must fail OPEN:
    with the old bare ``python3 <path>`` command, python3 exits 2 ("can't
    open file") and the harness blocks EVERY event — the guard turns that
    into a silent exit 0. ``empty_home`` (no clone at all) must behave the
    same.
    """

    def setUp(self):
        self.manifest = load_manifest()
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name) / "project"
        self.project.mkdir()
        # Stale fallback: marketplace clone exists but predates v7 — the
        # hooks/ dir carries v6 scripts, never nav_dispatch.py.
        self.stale_home = Path(self.tmp.name) / "home-stale"
        stale_hooks = self.stale_home / FALLBACK_RELPATH / "hooks"
        stale_hooks.mkdir(parents=True)
        (stale_hooks / "nav_session_start.py").write_text("# stale v6 hook\n")
        # Empty fallback: no marketplace clone at all.
        self.empty_home = Path(self.tmp.name) / "home-empty"
        self.empty_home.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def commands(self):
        for event in EVENTS:
            yield event, self.manifest["hooks"][event][0]["hooks"][0]["command"]

    def test_variant_set_to_repo(self):
        """CLAUDE_PLUGIN_ROOT=<repo>: expansion hits this checkout; exit 0, fail-open."""
        env = clean_env(extra={"CLAUDE_PLUGIN_ROOT": str(REPO_ROOT)})
        for event, command in self.commands():
            proc = run_manifest_command(command, env, self.project)
            self.assertEqual(proc.returncode, 0, f"{event}: {proc.stderr!r}")

    def test_variant_set_to_repo_actually_dispatches(self):
        """The guard must exec the dispatcher when the file exists, not skip it.

        Proof: a seeded unsurfaced health error in the project makes the
        SessionStart dispatch emit the surfacing line — a silent guard skip
        would print nothing.
        """
        agent = self.project / ".agent"
        agent.mkdir()
        (agent / ".nav-dispatch-health.json").write_text(json.dumps({
            "last_error": {"ts": "2026-07-10T00:00:00+00:00", "event": "Stop",
                           "op": "probe", "error": "RuntimeError"},
            "surfaced": False,
        }))
        env = clean_env(extra={"CLAUDE_PLUGIN_ROOT": str(REPO_ROOT)})
        command = self.manifest["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        payload = json.dumps({"cwd": str(self.project), "session_id": "mv1"})
        proc = run_manifest_command(command, env, self.project, stdin=payload)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("last dispatch error", proc.stdout)

    def assert_silent_fail_open(self, event, proc):
        """Fallback dispatcher missing: the guard must exit 0 with NO output.

        A loud python3 exit 2 here fails CLOSED — the harness would block
        every event on any machine whose marketplace clone predates v7.
        A hang is caught by run_manifest_command's subprocess timeout.
        """
        self.assertEqual(proc.returncode, 0, f"{event}: {proc.stderr!r}")
        self.assertEqual(proc.stdout, "", f"{event}: fail-open must be silent")
        self.assertEqual(proc.stderr, "", f"{event}: fail-open must be silent")

    def test_variant_unset_with_stale_fallback(self):
        """CLAUDE_PLUGIN_ROOT unset + stale (pre-v7) fallback clone: silent 0."""
        env = clean_env(extra={"HOME": str(self.stale_home)}, drop=("CLAUDE_PLUGIN_ROOT",))
        for event, command in self.commands():
            self.assert_silent_fail_open(
                event, run_manifest_command(command, env, self.project))

    def test_variant_unset_with_absent_fallback(self):
        """CLAUDE_PLUGIN_ROOT unset + no fallback clone at all: silent 0."""
        env = clean_env(extra={"HOME": str(self.empty_home)}, drop=("CLAUDE_PLUGIN_ROOT",))
        for event, command in self.commands():
            self.assert_silent_fail_open(
                event, run_manifest_command(command, env, self.project))

    def test_variant_empty_with_stale_fallback(self):
        """CLAUDE_PLUGIN_ROOT="": the :- operator falls back exactly like unset."""
        env = clean_env(extra={"HOME": str(self.stale_home), "CLAUDE_PLUGIN_ROOT": ""})
        for event, command in self.commands():
            self.assert_silent_fail_open(
                event, run_manifest_command(command, env, self.project))


class ShimContractTest(unittest.TestCase):
    """nav_dispatch.py: <40 lines, fail-open exit 0 on every degenerate input.

    Runs are pinned to a tmp project carrying its own .agent/ so the full
    dispatch pipeline executes without leaking runtime state into the real
    repo .agent/ (integration fix: cwd previously defaulted to REPO_ROOT).
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name) / "project"
        (self.project / ".agent").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def run_pinned(self, args, stdin=""):
        return run_shim(args, stdin=stdin, cwd=self.project)

    def test_line_count_under_40(self):
        line_count = SHIM.read_text(encoding="utf-8").count("\n")  # wc -l semantics
        self.assertLess(line_count, 40)

    def test_empty_json_stdin_exits_0(self):
        for event in EVENTS:
            proc = self.run_pinned([event], stdin="{}")
            self.assertEqual(proc.returncode, 0, f"{event}: {proc.stderr!r}")

    def test_garbage_stdin_exits_0(self):
        proc = self.run_pinned(["Stop"], stdin="not json {{{")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_no_event_arg_exits_0_no_output(self):
        proc = self.run_pinned([], stdin="{}")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "")

    def test_unknown_event_exits_0_no_output(self):
        proc = self.run_pinned(["NoSuchEvent"], stdin="{}")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "")

    def test_shim_never_touches_real_repo_state(self):
        """Regression: a full-event sweep must not write into the repo .agent/."""
        leak_targets = [
            REPO_ROOT / ".agent" / ".nav-runtime-state.json",
            REPO_ROOT / ".agent" / ".nav-runtime-state.lock",
            REPO_ROOT / ".agent" / ".nav-dispatch-health.json",
        ]
        before = {p: p.stat().st_mtime_ns for p in leak_targets if p.exists()}
        for event in EVENTS:
            self.run_pinned([event], stdin="{}")
        for path in leak_targets:
            if path.exists():
                self.assertIn(path, before, f"leaked into repo .agent/: {path.name}")
                self.assertEqual(path.stat().st_mtime_ns, before[path],
                                 f"modified repo .agent/ file: {path.name}")


if __name__ == "__main__":
    unittest.main()
