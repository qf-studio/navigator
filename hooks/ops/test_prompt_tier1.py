#!/usr/bin/env python3
"""Tests for ops/prompt_tier1.py — the Tier-1 deterministic responder (TASK-62).

Two layers (TASK-45 pattern):
  - Op-level contract: exact-match table on strip_all()'d prompts (<=48 chars,
    no fuzzy matching), sentinel-wrapped answers + escape line via
    signals.prompt_block (mem-053 winner — never exit-2), per-rule toggles,
    telemetry (turn.tier1_hit, tier1.false_positives), Pilot bypass, and the
    mem-034 echo-hygiene probe.
  - Subprocess contract via hooks/nav_dispatch.py against a throwaway
    project: hit/passthrough/off-by-default/Pilot, with CLAUDE_PLUGIN_ROOT
    set AND unset (mem-036).
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

import prompt_tier1  # noqa: E402
from nav_hook_lib import config as nav_config  # noqa: E402
from nav_hook_lib import sentinels  # noqa: E402

HOOKS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = HOOKS_DIR.parent
DISPATCH = str(HOOKS_DIR / "nav_dispatch.py")

ENV_VARS = ("PILOT_EXECUTOR", "CLAUDE_USER_MESSAGE", "CLAUDE_PROJECT_DIR",
            "CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DIR")


def enabled_cfg(**tier1_overrides):
    cfg = copy.deepcopy(nav_config.DEFAULTS)
    cfg["tier1"]["enabled"] = True
    for key, value in tier1_overrides.items():
        cfg["tier1"][key] = value
    return cfg


def make_ctx(prompt=None, cfg=None, state=None, pilot=False, cwd=None):
    payload = {} if prompt is None else {"prompt": prompt}
    if cwd is not None:
        payload["cwd"] = str(cwd)
    return types.SimpleNamespace(
        event="UserPromptSubmit",
        payload=payload,
        config=cfg if cfg is not None else enabled_cfg(),
        state=state if state is not None else {},
        pilot_executor=pilot,
        now=0.0,
    )


class Tier1TestBase(unittest.TestCase):
    def setUp(self):
        self._saved = {key: os.environ.pop(key, None) for key in ENV_VARS}
        self.addCleanup(self._restore)

    def _restore(self):
        for key, value in self._saved.items():
            if value is not None:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)

    def make_project(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        project = Path(os.path.realpath(tmp.name))
        (project / ".agent").mkdir(parents=True)
        return project


class ExactMatchTest(Tier1TestBase):
    def assert_hit(self, result, ctx, rule):
        self.assertIsNotNone(result)
        self.assertEqual(result["decision"], "block")
        self.assertNotIn("exit_code", result)   # mem-053: never exit-2
        self.assertNotIn("stderr", result)
        reason = result["reason"]
        # Renders as a plain-text grot card: framed, no sentinel litter.
        self.assertTrue(reason.startswith("╭─"), reason)
        self.assertTrue(reason.rstrip().endswith("╯"), reason)
        self.assertNotIn("<!--", reason)   # no marker shows to the user
        self.assertIn(prompt_tier1.ESCAPE_LINE, reason)
        self.assertEqual(ctx.state["turn"]["tier1_hit"], rule)
        self.assertIs(ctx.state["completion"]["tier1_fuse"], True)
        self.assertEqual(ctx.state["tier1"]["hits"], 1)

    def test_every_seed_command_answers(self):
        project = self.make_project()
        for command, rule in prompt_tier1.COMMANDS.items():
            with self.subTest(command=command):
                ctx = make_ctx(command, cwd=project)
                self.assert_hit(prompt_tier1.run(ctx), ctx, rule)

    def test_exact_match_is_case_insensitive_and_trimmed(self):
        project = self.make_project()
        ctx = make_ctx("  NAV Stats  ", cwd=project)
        self.assert_hit(prompt_tier1.run(ctx), ctx, "nav_stats")

    def test_escape_line_text_is_the_contract_string(self):
        self.assertEqual(prompt_tier1.ESCAPE_LINE,
                         "reply 'ask claude' to run the model")


class PassthroughTest(Tier1TestBase):
    """No fuzzy matching: non-exact variants must reach the model."""

    def assert_passthrough(self, ctx):
        self.assertIsNone(prompt_tier1.run(ctx))
        turn = ctx.state.get("turn") or {}
        self.assertNotIn("tier1_hit", turn)

    def test_trailing_words_pass_through(self):
        self.assert_passthrough(make_ctx("nav stats please"))

    def test_leading_words_pass_through(self):
        self.assert_passthrough(make_ctx("please nav stats"))

    def test_internal_whitespace_is_not_collapsed(self):
        self.assert_passthrough(make_ctx("nav  stats"))

    def test_trailing_punctuation_passes_through(self):
        self.assert_passthrough(make_ctx("nav stats?"))

    def test_prompt_over_48_chars_never_matches(self):
        long_prompt = "nav stats" + " " + "x" * 48
        self.assertGreater(len(long_prompt), prompt_tier1.MAX_PROMPT_CHARS)
        self.assert_passthrough(make_ctx(long_prompt))

    def test_empty_prompt_is_silent(self):
        self.assert_passthrough(make_ctx())

    def test_disabled_by_default_config(self):
        # config.DEFAULTS seeds tier1.enabled=false — exact match passes through.
        ctx = make_ctx("nav stats", cfg=copy.deepcopy(nav_config.DEFAULTS))
        self.assert_passthrough(ctx)

    def test_per_rule_toggle_disables_only_that_rule(self):
        project = self.make_project()
        cfg = enabled_cfg(rules={"nav_stats": False})
        self.assert_passthrough(make_ctx("nav stats", cfg=cfg, cwd=project))
        ctx = make_ctx("graph health", cfg=cfg, cwd=project)
        result = prompt_tier1.run(ctx)
        self.assertEqual(result["decision"], "block")

    def test_pilot_executor_bypasses_entirely(self):
        ctx = make_ctx("nav stats", pilot=True)
        self.assertIsNone(prompt_tier1.run(ctx))
        self.assertEqual(ctx.state, {})  # no answer, no telemetry


class EchoHygieneTest(Tier1TestBase):
    """mem-034 class: an echoed Tier-1 answer can never re-trigger anything."""

    def test_answer_is_a_clean_unwrapped_card(self):
        # A block reason renders as plain text, so the answer carries NO
        # sentinel marker (it would show literally). Safety comes from the
        # exact-match rail, not from strip-on-echo (see the pass-through test).
        project = self.make_project()
        ctx = make_ctx("nav stats", cwd=project)
        reason = prompt_tier1.run(ctx)["reason"]
        self.assertNotIn("<!--", reason)
        self.assertNotIn("nav-t1-response", reason)
        self.assertTrue(reason.startswith("╭─"), reason)

    def test_refed_echo_passes_through_without_matching(self):
        project = self.make_project()
        first = make_ctx("nav stats", cwd=project)
        reason = prompt_tier1.run(first)["reason"]
        refed = make_ctx(reason + "\nOriginal prompt: nav stats", cwd=project)
        self.assertIsNone(prompt_tier1.run(refed))


class FalsePositiveTelemetryTest(Tier1TestBase):
    def test_near_identical_reprompt_after_hit_increments_counter(self):
        state = {"turn": {"tier1_hit": "nav_stats"}}
        ctx = make_ctx("nav stats please", state=state)
        self.assertIsNone(prompt_tier1.run(ctx))  # telemetry only, passthrough
        self.assertEqual(ctx.state["tier1"]["false_positives"], 1)
        self.assertNotIn("tier1_hit", ctx.state["turn"])  # one-shot window

    def test_unrelated_prompt_after_hit_does_not_count(self):
        state = {"turn": {"tier1_hit": "nav_stats"}}
        ctx = make_ctx("refactor the parser", state=state)
        self.assertIsNone(prompt_tier1.run(ctx))
        self.assertNotIn("tier1", ctx.state)

    def test_single_shared_word_after_hit_does_not_count(self):
        # "stats" is the only token shared with the "nav stats" command:
        # containment fails and Jaccard (1/5) is well below the threshold.
        state = {"turn": {"tier1_hit": "nav_stats"}}
        ctx = make_ctx("stats overview report now", state=state)
        self.assertIsNone(prompt_tier1.run(ctx))
        self.assertNotIn("tier1", ctx.state)
        self.assertEqual(ctx.state["turn"]["tier1_hit"], "nav_stats")  # window kept

    def test_reordered_rephrase_after_hit_counts_via_jaccard(self):
        # "features show" contains no verbatim command but its token set is
        # identical (Jaccard 1.0) — a genuine rephrase of "show features".
        state = {"turn": {"tier1_hit": "show_features"}}
        ctx = make_ctx("features show", state=state)
        self.assertIsNone(prompt_tier1.run(ctx))
        self.assertEqual(ctx.state["tier1"]["false_positives"], 1)
        self.assertNotIn("tier1_hit", ctx.state["turn"])  # one-shot window

    def test_verbatim_whitespace_miss_is_not_a_false_positive(self):
        # "nav  stats" misses the exact matcher only on whitespace; normalized
        # it IS the command (not a rephrase), so it is not counted.
        state = {"turn": {"tier1_hit": "nav_stats"}}
        ctx = make_ctx("nav  stats", state=state)
        self.assertIsNone(prompt_tier1.run(ctx))
        self.assertNotIn("tier1", ctx.state)

    def test_similarity_helper_constants_are_named(self):
        self.assertEqual(prompt_tier1.SIMILARITY_MAX_EXTRA_TOKENS, 3)
        self.assertEqual(prompt_tier1.SIMILARITY_MIN_JACCARD, 0.6)
        self.assertTrue(prompt_tier1._is_near_identical("nav stats please", "nav stats"))
        self.assertFalse(prompt_tier1._is_near_identical("nav stats", "nav stats"))
        # containment but too much padding (>3 extra tokens) fails rule 1, and
        # Jaccard (2/6) fails rule 2.
        self.assertFalse(prompt_tier1._is_near_identical(
            "nav stats a b c d", "nav stats"))

    def test_near_identical_without_prior_hit_does_not_count(self):
        ctx = make_ctx("nav stats please")
        self.assertIsNone(prompt_tier1.run(ctx))
        self.assertNotIn("tier1", ctx.state)

    def test_exact_reprompt_is_a_fresh_hit_not_a_false_positive(self):
        project = self.make_project()
        state = {"turn": {"tier1_hit": "nav_stats"}}
        ctx = make_ctx("nav stats", state=state, cwd=project)
        result = prompt_tier1.run(ctx)
        self.assertEqual(result["decision"], "block")
        self.assertNotIn("false_positives", ctx.state["tier1"])


class AnswerContentTest(Tier1TestBase):
    def _reason(self, prompt, project, cfg=None, state=None):
        ctx = make_ctx(prompt, cfg=cfg, state=state, cwd=project)
        result = prompt_tier1.run(ctx)
        self.assertIsNotNone(result)
        return result["reason"]

    def test_list_markers_lists_files(self):
        project = self.make_project()
        markers = project / ".agent" / ".context-markers"
        markers.mkdir()
        (markers / "2026-01-01-alpha.md").write_text("a")
        (markers / "2026-01-02-beta.md").write_text("b")
        reason = self._reason("list markers", project)
        self.assertIn("2 total", reason)
        self.assertIn("2026-01-01-alpha.md", reason)
        self.assertIn("2026-01-02-beta.md", reason)

    def test_list_markers_empty(self):
        project = self.make_project()
        self.assertIn("No context markers", self._reason("list markers", project))

    def test_graph_health_reports_stats(self):
        project = self.make_project()
        knowledge = project / ".agent" / "knowledge"
        knowledge.mkdir()
        (knowledge / "graph.json").write_text(json.dumps({
            "version": 5,
            "last_updated": "2026-07-10T00:00:00Z",
            "stats": {"total_nodes": 7, "total_edges": 3, "memory_count": 2},
            "concept_index": {"auth": [], "hooks": []},
        }))
        reason = self._reason("graph health", project)
        self.assertIn("nodes: 7 | edges: 3 | memories: 2", reason)
        self.assertIn("indexed concepts: 2", reason)
        self.assertIn("2026-07-10T00:00:00Z", reason)

    def test_graph_health_missing_graph(self):
        project = self.make_project()
        self.assertIn("No knowledge graph", self._reason("graph health", project))

    def test_nav_stats_reads_state_and_graph(self):
        project = self.make_project()
        state = {"reads": {"turn_count": 3},
                 "tier1": {"hits": 4, "false_positives": 1}}
        reason = self._reason("nav stats", project, state=state)
        self.assertIn("reads this turn: 3", reason)
        # hits incremented by THIS hit: 4 -> 5.
        self.assertIn("tier1: 5 hits / 1 suspected false positives", reason)
        self.assertIn("graph: 0 nodes / 0 edges / 0 memories", reason)

    def test_show_features_reflects_config(self):
        project = self.make_project()
        reason = self._reason("show features", project)
        self.assertIn("tier1: on", reason)            # enabled for this test
        self.assertIn("stop_completion: off", reason)  # seeded OFF
        self.assertIn("task_mode: on", reason)

    def test_nav_version_reports_drift(self):
        project = self.make_project()
        os.environ["CLAUDE_PLUGIN_ROOT"] = str(REPO_ROOT)
        plugin_version = json.loads(
            (REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
        cfg = enabled_cfg()
        cfg["version"] = "0.0.1"
        reason = self._reason("nav version", project, cfg=cfg)
        self.assertIn(f"Navigator plugin: {plugin_version}", reason)
        self.assertIn(f"config 0.0.1 != plugin {plugin_version}", reason)

    def test_nav_version_resolves_without_plugin_env(self):
        # mem-036 flavor: with the env var UNSET the resolver falls back to
        # the checkout containing the lib — the answer must still resolve.
        project = self.make_project()
        plugin_version = json.loads(
            (REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
        cfg = enabled_cfg()
        cfg["version"] = plugin_version
        reason = self._reason("nav version", project, cfg=cfg)
        self.assertIn(f"Navigator plugin: {plugin_version}", reason)
        self.assertIn("version drift: none", reason)


class DispatchContractTest(Tier1TestBase):
    """Subprocess contract via nav_dispatch.py (TASK-45 template)."""

    TIER1_ON = json.dumps({"tier1": {"enabled": True}})

    def dispatch(self, project, payload, env_extra=None, config_body=None):
        agent = project / ".agent"
        if config_body is not None:
            (agent / ".nav-config.json").write_text(config_body)
        env = os.environ.copy()
        for var in ENV_VARS:
            env.pop(var, None)
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            [sys.executable, DISPATCH, "UserPromptSubmit"],
            input=json.dumps(payload), capture_output=True, text=True,
            cwd=project, env=env, timeout=60,
        )

    def payload(self, project, prompt):
        return {"cwd": str(project), "session_id": "s1", "prompt": prompt}

    def read_state(self, project):
        path = project / ".agent" / ".nav-runtime-state.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def assert_hit_doc(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        doc = json.loads(result.stdout)
        self.assertEqual(doc["decision"], "block")
        self.assertIn("nav stats · zero model tokens", doc["reason"])
        self.assertIn(prompt_tier1.ESCAPE_LINE, doc["reason"])
        return doc

    def test_hit_emits_block_doc_env_unset_and_set(self):
        # mem-036: the same behavior with CLAUDE_PLUGIN_ROOT set AND unset.
        for env_extra in (None, {"CLAUDE_PLUGIN_ROOT": str(REPO_ROOT)}):
            with self.subTest(env=env_extra):
                project = self.make_project()
                result = self.dispatch(project, self.payload(project, "nav stats"),
                                       env_extra=env_extra,
                                       config_body=self.TIER1_ON)
                self.assert_hit_doc(result)
                state = self.read_state(project)
                self.assertEqual(state["turn"]["tier1_hit"], "nav_stats")

    def test_non_exact_variant_passes_through(self):
        project = self.make_project()
        result = self.dispatch(project, self.payload(project, "nav stats please"),
                               config_body=self.TIER1_ON)
        self.assertEqual(result.returncode, 0, result.stderr)
        if result.stdout.strip():
            doc = json.loads(result.stdout)
            self.assertNotEqual(doc.get("decision"), "block", doc)

    def test_seeded_off_pristine_config_passes_through(self):
        # No tier1 block at all: the feature must be OFF (config.DEFAULTS).
        project = self.make_project()
        result = self.dispatch(project, self.payload(project, "nav stats"),
                               config_body="{}")
        self.assertEqual(result.returncode, 0, result.stderr)
        if result.stdout.strip():
            doc = json.loads(result.stdout)
            self.assertNotEqual(doc.get("decision"), "block", doc)

    def test_pilot_executor_bypasses(self):
        project = self.make_project()
        result = self.dispatch(project, self.payload(project, "nav stats"),
                               env_extra={"PILOT_EXECUTOR": "1"},
                               config_body=self.TIER1_ON)
        self.assertEqual(result.returncode, 0, result.stderr)
        if result.stdout.strip():
            doc = json.loads(result.stdout)
            self.assertNotEqual(doc.get("decision"), "block", doc)
        turn = self.read_state(project).get("turn") or {}
        self.assertNotIn("tier1_hit", turn)


if __name__ == "__main__":
    unittest.main()


class TestNavStatsJudgeLine(unittest.TestCase):
    """TASK-80 B: the nav stats card carries a judge line only after a call."""

    def _ctx(self, state):
        import copy as _copy
        from nav_hook_lib import config as _cfg
        cfg = _copy.deepcopy(_cfg.DEFAULTS)
        cfg["tier1"]["enabled"] = True
        return types.SimpleNamespace(event="UserPromptSubmit", payload={"prompt": "nav stats"},
                                     config=cfg, state=state, pilot_executor=False, now=0.0)

    def test_absent_without_calls(self):
        text = prompt_tier1._answer_nav_stats(self._ctx({}))
        self.assertNotIn("judge:", text)

    def test_present_after_calls(self):
        state = {"judge": {"calls": 3, "failed": 0, "model": "jev-1.13.0",
                           "latency_last_ms": 650, "latency_max_ms": 720,
                           "axes": {"loop": {"overridden": 1, "agreed": 2}}}}
        text = prompt_tier1._answer_nav_stats(self._ctx(state))
        self.assertIn("judge: 3 calls / 0 failed · 650 ms last, 720 ms max", text)
        self.assertIn("judge axes: 1 overridden / 2 agreed / 0 undecided", text)
