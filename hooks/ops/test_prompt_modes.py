#!/usr/bin/env python3
"""Tests for ops/prompt_modes.py — reply-mode toggles + injection (TASK-82, TASK-93).

Op-level: toggle phrases answer via decision:block and write that mode's
personal switch; injection only while resolved on; repo pin wins; a disabled
mode answers but never writes; Pilot silent; a prompt merely mentioning a
mode is neither a toggle nor an answer.
Subprocess: the full dispatcher path with NAVIGATOR_CONFIG_HOME isolated —
"adhd mode on" blocks at zero model turn, the next prompt carries the block,
"use ste" stacks the second block below it, "adhd mode off" removes the first.
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

import prompt_modes  # noqa: E402
from nav_hook_lib import config as nav_config, personal, reply_modes as rm  # noqa: E402

HOOKS_DIR = Path(__file__).resolve().parent.parent
DISPATCH = str(HOOKS_DIR / "nav_dispatch.py")
ENV_VARS = ("PILOT_EXECUTOR", "CLAUDE_USER_MESSAGE", "CLAUDE_PROJECT_DIR",
            "CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DIR", personal.ENV_OVERRIDE,
            nav_config.MOD_OWNS_ENV)
ADHD, STE = rm.by_key("adhd"), rm.by_key("ste")


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

    def cfg(self, adhd=None, ste=None, **blocks):
        c = copy.deepcopy(nav_config.DEFAULTS)
        c["adhd_mode"]["on"] = adhd
        c["ste_mode"]["on"] = ste
        for key, value in blocks.items():
            c[key].update(value)
        return c

    def ctx(self, prompt, cfg=None, pilot=False):
        return types.SimpleNamespace(
            event="UserPromptSubmit", payload={"prompt": prompt, "cwd": str(self.root)},
            config=cfg if cfg is not None else self.cfg(), state={},
            pilot_executor=pilot, now=1_700_000_000.0)


class ToggleTest(_Base):
    def test_on_writes_personal_switch_and_blocks(self):
        out = prompt_modes.run(self.ctx("adhd mode on"))
        self.assertEqual(out["decision"], "block")
        self.assertIn("ADHD mode: on (personal", out["reason"])
        self.assertIn('Say "adhd mode off" to stop.', out["reason"])
        self.assertNotIn("<!--", out["reason"])
        self.assertIs(rm.personal_on(ADHD), True)
        self.assertIsNone(rm.personal_on(STE))

    def test_ste_toggle_touches_only_its_own_file(self):
        out = prompt_modes.run(self.ctx("use STE"))
        self.assertEqual(out["decision"], "block")
        self.assertIn("STE mode: on (personal, ", out["reason"])
        self.assertIn("ste-mode.json", out["reason"])
        self.assertIn('Say "ste mode off" to stop.', out["reason"])
        self.assertIs(rm.personal_on(STE), True)
        self.assertFalse((self.home / "adhd-mode.json").exists())

    def test_off_then_status(self):
        prompt_modes.run(self.ctx("adhd mode on"))
        out = prompt_modes.run(self.ctx("stop adhd mode"))
        self.assertEqual(out["decision"], "block")
        self.assertIn("ADHD mode: off", out["reason"])
        self.assertIs(rm.personal_on(ADHD), False)
        status = prompt_modes.run(self.ctx("adhd mode?"))
        self.assertIn("ADHD mode: off (personal switch", status["reason"])

    def test_status_when_never_set(self):
        out = prompt_modes.run(self.ctx("ste mode"))
        self.assertIn("STE mode: off (never switched on).", out["reason"])
        self.assertIn('Say "ste mode on" or "ste mode off".', out["reason"])
        self.assertFalse((self.home / "ste-mode.json").exists())

    def test_repo_pin_is_reported_on_toggle(self):
        out = prompt_modes.run(self.ctx("adhd mode on", cfg=self.cfg(adhd=False)))
        self.assertIn("pins it off via adhd_mode.on", out["reason"])
        self.assertIs(rm.personal_on(ADHD), True, "personal switch still written")

    def test_disabled_mode_answers_without_writing(self):
        out = prompt_modes.run(self.ctx("ste mode on", cfg=self.cfg(ste_mode={"enabled": False})))
        self.assertEqual(out["decision"], "block")
        self.assertIn("STE mode: disabled in this repo (ste_mode.enabled", out["reason"])
        self.assertIsNone(rm.personal_on(STE))

    def test_pilot_is_silent(self):
        self.assertIsNone(prompt_modes.run(self.ctx("adhd mode on", pilot=True)))
        self.assertIsNone(rm.personal_on(ADHD))

    def test_mention_is_not_a_toggle(self):
        self.assertIsNone(prompt_modes.run(self.ctx("I have ADHD, keep replies short")))
        self.assertIsNone(prompt_modes.run(self.ctx("what is ASD-STE100?")))
        self.assertIsNone(rm.personal_on(ADHD))
        self.assertIsNone(rm.personal_on(STE))


class HandoffTest(_Base):
    """v8 (TASK-84): ownership is checked once in runtime._dispatch, not in the op.

    The op itself no longer reads NAVIGATOR_MOD_OWNS; the full dispatcher path proves the
    handoff: with prompt_modes owned, the subprocess emits no rule block.
    """

    def test_op_ignores_ownership_env(self):
        rm.set_personal(ADHD, True)
        os.environ[nav_config.MOD_OWNS_ENV] = "prompt_modes"
        out = prompt_modes.run(self.ctx("fix the login bug"))
        self.assertEqual(out, {"additional_context": ADHD.rule_block})

    def test_dispatcher_skips_owned_prompt_modes(self):
        rm.set_personal(ADHD, True)
        (self.root / ".agent").mkdir(exist_ok=True)
        payload = json.dumps({"prompt": "fix the login bug", "cwd": str(self.root),
                              "session_id": "s"})
        env = dict(os.environ, NAVIGATOR_MOD_OWNS="prompt_modes")
        owned = subprocess.run([sys.executable, DISPATCH, "UserPromptSubmit"], input=payload,
                               capture_output=True, text=True, env=env, cwd=self.root)
        env.pop("NAVIGATOR_MOD_OWNS")
        python = subprocess.run([sys.executable, DISPATCH, "UserPromptSubmit"], input=payload,
                                capture_output=True, text=True, env=env, cwd=self.root)
        self.assertNotIn("ADHD MODE: on (", owned.stdout)
        self.assertIn("ADHD MODE: on (", python.stdout)


class InjectionTest(_Base):
    def test_off_by_default_injects_nothing(self):
        self.assertIsNone(prompt_modes.run(self.ctx("fix the login bug")))

    def test_on_injects_block_on_any_prompt(self):
        rm.set_personal(ADHD, True)
        out = prompt_modes.run(self.ctx("fix the login bug"))
        self.assertEqual(out, {"additional_context": ADHD.rule_block})
        self.assertNotIn("decision", out)

    def test_two_modes_stack_in_table_order(self):
        rm.set_personal(STE, True)
        rm.set_personal(ADHD, True)
        out = prompt_modes.run(self.ctx("fix the login bug"))
        self.assertEqual(out["additional_context"],
                         ADHD.rule_block + "\n\n" + STE.rule_block)

    def test_repo_pin_off_beats_personal_on(self):
        rm.set_personal(ADHD, True)
        self.assertIsNone(prompt_modes.run(self.ctx("fix it", cfg=self.cfg(adhd=False))))

    def test_repo_pin_on_without_personal_file(self):
        out = prompt_modes.run(self.ctx("fix it", cfg=self.cfg(ste=True)))
        self.assertEqual(out["additional_context"], STE.rule_block)

    def test_disabled_mode_never_injects(self):
        rm.set_personal(STE, True)
        self.assertIsNone(prompt_modes.run(self.ctx("fix it", cfg=self.cfg(ste_mode={"enabled": False}))))

    def test_pilot_never_injects(self):
        rm.set_personal(ADHD, True)
        self.assertIsNone(prompt_modes.run(self.ctx("fix it", pilot=True)))


class DispatchSubprocessTest(_Base):
    """End to end through hooks/nav_dispatch.py against a throwaway project."""

    def setUp(self):
        super().setUp()
        agent = self.root / ".agent"
        agent.mkdir()
        (agent / ".nav-config.json").write_text(
            json.dumps({"version": "8.3.0", "judge": {"enabled": False}}), encoding="utf-8")

    def dispatch(self, prompt):
        payload = {"prompt": prompt, "cwd": str(self.root), "session_id": "modes-test",
                   "hook_event_name": "UserPromptSubmit"}
        proc = subprocess.run([sys.executable, DISPATCH, "UserPromptSubmit"],
                              input=json.dumps(payload), capture_output=True, text=True,
                              cwd=self.root, env=os.environ.copy(), timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_toggle_then_inject_then_stack_then_off(self):
        self.assertNotIn("MODE: on", self.dispatch("what time is it"))
        on = json.loads(self.dispatch("adhd mode on"))
        self.assertEqual(on.get("decision"), "block")
        self.assertIn("ADHD mode: on", on["reason"])
        self.assertIn("ADHD MODE: on", self.dispatch("what time is it"))
        ste = json.loads(self.dispatch("use ste"))
        self.assertIn("STE mode: on", ste["reason"])
        both = self.dispatch("what time is it")
        self.assertLess(both.index("ADHD MODE: on"), both.index("STE MODE: on"))
        off = json.loads(self.dispatch("adhd mode off"))
        self.assertEqual(off.get("decision"), "block")
        after = self.dispatch("what time is it")
        self.assertNotIn("ADHD MODE", after)
        self.assertIn("STE MODE: on", after)


if __name__ == "__main__":
    unittest.main()
