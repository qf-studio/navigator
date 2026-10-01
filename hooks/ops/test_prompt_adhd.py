#!/usr/bin/env python3
"""Tests for ops/prompt_adhd.py — ADHD mode toggle + injection (TASK-82).

Op-level: toggle phrases answer via decision:block and write the personal
switch; injection only while resolved on; repo pin wins; Pilot silent; a
prompt merely mentioning ADHD is neither a toggle nor an answer.
Subprocess: the full dispatcher path with NAVIGATOR_CONFIG_HOME isolated —
"adhd mode on" blocks at zero model turn, the next prompt carries the block,
"adhd mode off" removes it.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))          # this dir
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # hooks/

import prompt_adhd  # noqa: E402
from nav_hook_lib import adhd, config as nav_config, personal  # noqa: E402

HOOKS_DIR = Path(__file__).resolve().parent.parent
DISPATCH = str(HOOKS_DIR / "nav_dispatch.py")
ENV_VARS = ("PILOT_EXECUTOR", "CLAUDE_USER_MESSAGE", "CLAUDE_PROJECT_DIR",
            "CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DIR", personal.ENV_OVERRIDE)


class _Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.home = self.root / "cfg-home"
        self._saved = {k: os.environ.pop(k, None) for k in ENV_VARS}
        self.addCleanup(self._restore)
        os.environ[personal.ENV_OVERRIDE] = str(self.home)

    def _restore(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def cfg(self, on=None):
        c = copy.deepcopy(nav_config.DEFAULTS)
        c["adhd_mode"]["on"] = on
        return c

    def ctx(self, prompt, cfg=None, pilot=False):
        return types.SimpleNamespace(
            event="UserPromptSubmit", payload={"prompt": prompt, "cwd": str(self.root)},
            config=cfg if cfg is not None else self.cfg(), state={},
            pilot_executor=pilot, now=1_700_000_000.0)


class ToggleTest(_Base):
    def test_on_writes_personal_switch_and_blocks(self):
        out = prompt_adhd.run(self.ctx("adhd mode on"))
        self.assertEqual(out["decision"], "block")
        self.assertIn("ADHD mode: on (personal", out["reason"])
        self.assertIn("adhd mode off", out["reason"])
        self.assertNotIn("<!--", out["reason"])
        self.assertIs(adhd.personal_on(), True)

    def test_off_then_status(self):
        prompt_adhd.run(self.ctx("adhd mode on"))
        out = prompt_adhd.run(self.ctx("stop adhd mode"))
        self.assertEqual(out["decision"], "block")
        self.assertIn("ADHD mode: off", out["reason"])
        self.assertIs(adhd.personal_on(), False)
        status = prompt_adhd.run(self.ctx("adhd mode?"))
        self.assertIn("ADHD mode: off (personal switch", status["reason"])

    def test_status_when_never_set(self):
        out = prompt_adhd.run(self.ctx("adhd mode"))
        self.assertIn("never switched on", out["reason"])
        self.assertFalse((self.home / "adhd-mode.json").exists())

    def test_repo_pin_is_reported_on_toggle(self):
        out = prompt_adhd.run(self.ctx("adhd mode on", cfg=self.cfg(on=False)))
        self.assertIn("pins it off", out["reason"])
        self.assertIs(adhd.personal_on(), True, "personal switch still written")

    def test_pilot_is_silent(self):
        self.assertIsNone(prompt_adhd.run(self.ctx("adhd mode on", pilot=True)))
        self.assertIsNone(adhd.personal_on())

    def test_mention_is_not_a_toggle(self):
        self.assertIsNone(prompt_adhd.run(self.ctx("I have ADHD, keep replies short")))
        self.assertIsNone(adhd.personal_on())


class InjectionTest(_Base):
    def test_off_by_default_injects_nothing(self):
        self.assertIsNone(prompt_adhd.run(self.ctx("fix the login bug")))

    def test_on_injects_block_on_any_prompt(self):
        adhd.set_personal(True)
        out = prompt_adhd.run(self.ctx("fix the login bug"))
        self.assertEqual(out, {"additional_context": adhd.RULE_BLOCK})
        self.assertNotIn("decision", out)

    def test_repo_pin_off_beats_personal_on(self):
        adhd.set_personal(True)
        self.assertIsNone(prompt_adhd.run(self.ctx("fix it", cfg=self.cfg(on=False))))

    def test_repo_pin_on_without_personal_file(self):
        out = prompt_adhd.run(self.ctx("fix it", cfg=self.cfg(on=True)))
        self.assertEqual(out["additional_context"], adhd.RULE_BLOCK)

    def test_pilot_never_injects(self):
        adhd.set_personal(True)
        self.assertIsNone(prompt_adhd.run(self.ctx("fix it", pilot=True)))


class DispatchSubprocessTest(_Base):
    """End to end through hooks/nav_dispatch.py against a throwaway project."""

    def setUp(self):
        super().setUp()
        agent = self.root / ".agent"
        agent.mkdir()
        (agent / ".nav-config.json").write_text(
            json.dumps({"version": "7.9.0", "judge": {"enabled": False}}), encoding="utf-8")

    def dispatch(self, prompt):
        payload = {"prompt": prompt, "cwd": str(self.root), "session_id": "adhd-test",
                   "hook_event_name": "UserPromptSubmit"}
        proc = subprocess.run([sys.executable, DISPATCH, "UserPromptSubmit"],
                              input=json.dumps(payload), capture_output=True, text=True,
                              cwd=self.root, env=os.environ.copy(), timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_toggle_then_inject_then_off(self):
        self.assertNotIn("ADHD MODE", self.dispatch("what time is it"))
        on = self.dispatch("adhd mode on")
        doc = json.loads(on)
        self.assertEqual(doc.get("decision"), "block")
        self.assertIn("ADHD mode: on", doc["reason"])
        self.assertIn("ADHD MODE: on", self.dispatch("what time is it"))
        off = json.loads(self.dispatch("adhd mode off"))
        self.assertEqual(off.get("decision"), "block")
        self.assertNotIn("ADHD MODE", self.dispatch("what time is it"))


if __name__ == "__main__":
    unittest.main()
