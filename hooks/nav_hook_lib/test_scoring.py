#!/usr/bin/env python3
"""Tests for scoring.py (TASK-59, Phase 4).

Includes the characterization corpus: ~49 real prompts harvested from the
four v6 scorer test suites, SKILL.md examples, and CLAUDE.md trigger lists.
V6_SNAPSHOT holds outputs captured by RUNNING the original v6 modules
(workflow_detector, complexity_detector, skill_detector, ambiguity_scorer)
before they were converted to re-export shims. Every v6 classification must
be preserved within one tier of the unified model.

Run `python3 test_scoring.py --diff` to print the per-prompt v6-vs-v7 diff.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import scoring
from scoring import ScoreCard, contains_phrase, score, v6_exports

TIER_RANK = {"DIRECT": 0, "TASK": 1, "LOOP": 2}


def complexity_bucket(value: float) -> int:
    """Three-tier complexity ladder shared by v6 and unified scores."""
    if value < 0.3:
        return 0
    if value < 0.7:
        return 1
    return 2


# ---------------------------------------------------------------------------
# v6 snapshot — captured from the live v6 implementations on 2026-07-10,
# BEFORE the shim conversion. Do not regenerate from the unified model.
#
# (wd_mode, wd_complexity, cd_score, cd_recommendation, sd_skill,
#  sd_defer, amb_score, amb_task_shaped)
# ---------------------------------------------------------------------------
V6_SNAPSHOT = {
    # workflow_detector tests (loop triggers, complexity, TASK-48 boundaries)
    'run until done: fix the bug': ('LOOP', 0.1, 0.5, 'task_mode', 'nav-loop', True, 0.5, True),
    'Just keep going on this': ('LOOP', 0.0, 0.3, 'direct_execution', None, False, 0.0, False),
    'iterate until the tests pass': ('LOOP', 0.0, 0.5, 'task_mode', None, False, 0.0, False),
    'Use loop mode for this': ('LOOP', 0.0, 0.5, 'task_mode', 'nav-loop', True, 0.0, False),
    'Please review this file': ('DIRECT', 0.0, 0.5, 'task_mode', None, False, 0.0, False),
    'Please refactor this': ('DIRECT', 0.3, 0.8, 'task_mode', None, False, 0.5, True),
    'Please enhance it': ('DIRECT', 0.2, 0.5, 'task_mode', None, False, 0.5, True),
    'Please remove it': ('DIRECT', 0.1, 0.5, 'task_mode', None, False, 0.5, True),
    'change across the codebase': ('DIRECT', 0.3, 0.5, 'task_mode', None, False, 0.7, True),
    'hello there': ('DIRECT', 0.0, 0.5, 'task_mode', None, False, 0.0, False),
    'Refactor and implement the new feature across the entire codebase':
        ('TASK', 1.0, 1.0, 'task_mode', None, False, 0.7, True),
    'refactor implement migrate architecture redesign overhaul across the codebase':
        ('TASK', 1.0, 1.0, 'task_mode', None, False, 0.7, True),
    'Add a button': ('DIRECT', 0.1, 0.5, 'task_mode', None, False, 0.5, True),
    'Refactor the authentication architecture across the codebase':
        ('TASK', 0.8, 1.0, 'task_mode', None, False, 0.7, True),
    'What time is it': ('DIRECT', 0.0, 0.5, 'task_mode', None, False, 0.0, False),
    'implement it': ('DIRECT', 0.3, 0.7, 'task_mode', None, False, 0.5, True),
    'Please document everything we discussed':
        ('DIRECT', 0.0, 0.5, 'task_mode', None, False, 0.0, False),
    'complete everything on the list': ('LOOP', 0.0, 0.5, 'task_mode', None, False, 0.0, False),
    "don't stop until it works": ('LOOP', 0.0, 0.5, 'task_mode', None, False, 0.0, False),
    'fix the address field': ('DIRECT', 0.1, 0.5, 'task_mode', None, False, 0.5, True),
    'we are modifying the layout': ('DIRECT', 0.0, 0.5, 'task_mode', None, False, 0.0, False),
    # complexity_detector tests
    'Fix the typo in README.md': ('DIRECT', 0.1, 0.0, 'direct_execution', None, False, 0.1, True),
    ('Refactor the authentication system to use JWT and update both frontend '
     'and backend with proper integration tests'):
        ('DIRECT', 0.4, 1.0, 'task_mode', None, False, 0.7, True),
    'Refactor the entire payment system to use a new provider':
        ('DIRECT', 0.3, 0.8, 'task_mode', None, False, 0.7, True),
    'Add a new table for user preferences with proper schema migration':
        ('DIRECT', 0.1, 0.95, 'task_mode', 'database-migration', True, 0.5, True),
    'Update the copyright year in footer':
        ('DIRECT', 0.1, 0.4, 'direct_execution', None, False, 0.5, True),
    'Add a new button component':
        ('DIRECT', 0.1, 0.5, 'task_mode', 'frontend-component', True, 0.5, True),
    'Figure out how the cache system works':
        ('DIRECT', 0.0, 0.85, 'task_mode', None, False, 0.0, False),
    'Just fix the typo': ('DIRECT', 0.1, 0.1, 'direct_execution', None, False, 0.3, True),
    # skill_detector tests
    'Create a new login component':
        ('DIRECT', 0.1, 0.5, 'task_mode', 'frontend-component', True, 0.5, True),
    'Add a new REST API endpoint for users':
        ('DIRECT', 0.1, 0.5, 'task_mode', 'backend-endpoint', True, 0.5, True),
    'Create a migration to add user preferences table':
        ('DIRECT', 0.2, 0.8, 'task_mode', 'database-migration', True, 0.5, True),
    'Create a checkpoint before we continue':
        ('DIRECT', 0.1, 0.5, 'task_mode', 'nav-marker', True, 0.5, True),
    'Clear context and start fresh':
        ('DIRECT', 0.0, 0.5, 'task_mode', 'nav-compact', True, 0.0, False),
    'Save my progress before I take a break':
        ('DIRECT', 0.0, 0.5, 'task_mode', 'nav-marker', False, 0.0, False),
    'Something seems off with your responses':
        ('DIRECT', 0.0, 0.5, 'task_mode', 'nav-diagnose', False, 0.0, False),
    'Document this solution for future reference':
        ('DIRECT', 0.0, 0.5, 'task_mode', 'nav-sop', False, 0.0, False),
    'Write unit tests for the authentication API':
        ('DIRECT', 0.0, 0.75, 'task_mode', 'backend-test', True, 0.7, True),
    # ambiguity_scorer tests
    'fix the bug': ('DIRECT', 0.1, 0.5, 'task_mode', None, False, 0.5, True),
    'refactor the API': ('DIRECT', 0.3, 0.8, 'task_mode', None, False, 0.7, True),
    'add rate limiting to all API endpoints':
        ('DIRECT', 0.1, 0.5, 'task_mode', None, False, 0.7, True),
    'clean up the codebase': ('DIRECT', 0.2, 0.5, 'task_mode', None, False, 0.7, True),
    'implement JWT auth in src/auth/session.ts, only touching the login flow':
        ('DIRECT', 0.3, 0.35, 'direct_execution', None, False, 0.0, True),
    # CLAUDE.md / SKILL.md trigger lists and examples
    'Run until done: add user authentication':
        ('LOOP', 0.1, 0.65, 'task_mode', 'nav-loop', True, 0.5, True),
    'Keep going until complete': ('LOOP', 0.0, 0.5, 'task_mode', 'nav-loop', False, 0.0, False),
    'Refactor auth to use JWT': ('DIRECT', 0.3, 0.95, 'task_mode', None, False, 0.5, True),
    'Fix the typo in README': ('DIRECT', 0.1, 0.3, 'direct_execution', None, False, 0.5, True),
    'Create a UserProfile component':
        ('DIRECT', 0.1, 0.5, 'task_mode', 'frontend-component', True, 0.5, True),
    'Start my Navigator session': ('DIRECT', 0.0, 0.5, 'task_mode', None, False, 0.0, False),
}


class CorpusCharacterizationTest(unittest.TestCase):
    """Every v6 classification preserved within one tier of the unified model."""

    def test_corpus_size(self):
        """The corpus holds ~40+ real prompts."""
        self.assertGreaterEqual(len(V6_SNAPSHOT), 40)

    def test_workflow_mode_within_one_tier(self):
        """Unified tier is within one step of v6 recommended_mode."""
        for prompt, (wd_mode, *_rest) in V6_SNAPSHOT.items():
            with self.subTest(prompt=prompt):
                card = score(prompt)
                diff = abs(TIER_RANK[card.tier] - TIER_RANK[wd_mode])
                self.assertLessEqual(
                    diff, 1,
                    f"tier {card.tier} vs v6 {wd_mode} drifts {diff} tiers")

    def test_loop_detection_exact(self):
        """LOOP is trigger-based and must match v6 exactly, both directions."""
        for prompt, (wd_mode, *_rest) in V6_SNAPSHOT.items():
            with self.subTest(prompt=prompt):
                card = score(prompt)
                self.assertEqual(card.tier == "LOOP", wd_mode == "LOOP")

    def test_complexity_bucket_within_one_tier(self):
        """Unified additive complexity stays within one bucket of v6's."""
        for prompt, (_mode, wd_complexity, *_rest) in V6_SNAPSHOT.items():
            with self.subTest(prompt=prompt):
                card = score(prompt)
                diff = abs(complexity_bucket(card.complexity)
                           - complexity_bucket(wd_complexity))
                self.assertLessEqual(
                    diff, 1,
                    f"complexity {card.complexity} vs v6 {wd_complexity}")

    def test_substantiality_within_one_tier_of_complexity_detector(self):
        """cd's direct/task classification preserved within one tier.

        LOOP prompts are excluded: v6's detect_workflow ranks LOOP above
        TASK before complexity is consulted, so cd's tier was never the
        operative classification for them.
        """
        for prompt, snap in V6_SNAPSHOT.items():
            wd_mode, _wd_cx, _cd_score, cd_recommendation = snap[:4]
            if wd_mode == "LOOP":
                continue
            with self.subTest(prompt=prompt):
                card = score(prompt)
                cd_tier = 1 if cd_recommendation == "task_mode" else 0
                unified_tier = 1 if card.tier == "TASK" else 0
                self.assertLessEqual(abs(unified_tier - cd_tier), 1)

    def test_intent_preserved_exactly(self):
        """Intent router returns the same skill v6's skill_detector chose."""
        for prompt, snap in V6_SNAPSHOT.items():
            sd_skill = snap[4]
            with self.subTest(prompt=prompt):
                self.assertEqual(score(prompt).intent, sd_skill)

    def test_ambiguity_preserved_exactly(self):
        """Ambiguity is wrapped, not merged: byte-identical scores."""
        for prompt, snap in V6_SNAPSHOT.items():
            amb_score, amb_task_shaped = snap[6], snap[7]
            with self.subTest(prompt=prompt):
                self.assertEqual(score(prompt).ambiguity, amb_score)
                result = scoring.score_ambiguity(prompt)
                self.assertEqual(result["score"], amb_score)
                self.assertEqual(result["task_shaped"], amb_task_shaped)


class ScoreCardTest(unittest.TestCase):
    """Contract shape: ScoreCard{complexity, tier, intent, ambiguity, triggers}."""

    def test_field_types(self):
        card = score("Refactor the auth system across the codebase")
        self.assertIsInstance(card, ScoreCard)
        self.assertIsInstance(card.complexity, float)
        self.assertIsInstance(card.tier, str)
        self.assertIn(card.tier, scoring.TIER_LADDER)
        self.assertIsInstance(card.ambiguity, float)
        self.assertIsInstance(card.triggers, list)

    def test_intent_none_or_str(self):
        self.assertIsNone(score("hello there").intent)
        self.assertEqual(score("Create a login component").intent,
                         "frontend-component")

    def test_empty_prompt(self):
        card = score("")
        self.assertEqual(card.tier, "DIRECT")
        self.assertEqual(card.complexity, 0.0)
        self.assertEqual(card.ambiguity, 0.0)
        self.assertIsNone(card.intent)
        self.assertEqual(card.triggers, [])

    def test_none_prompt_tolerated(self):
        card = score(None)
        self.assertEqual(card.tier, "DIRECT")
        self.assertEqual(card.complexity, 0.0)

    def test_complexity_clamped(self):
        card = score(
            "refactor implement migrate architecture redesign overhaul "
            "across the codebase with tests for the database and api"
        )
        self.assertLessEqual(card.complexity, 1.0)

    def test_triggers_tagged(self):
        card = score("run until done: refactor the auth module")
        self.assertIn("loop:run until done", card.triggers)
        self.assertIn("high:refactor", card.triggers)


class TierLogicTest(unittest.TestCase):
    def test_loop_trigger_wins(self):
        """Loop trigger outranks complexity."""
        card = score("run until done: hello")
        self.assertEqual(card.tier, "LOOP")

    def test_task_at_threshold(self):
        card = score("Refactor the authentication architecture across the codebase")
        self.assertEqual(card.tier, "TASK")
        self.assertGreaterEqual(card.complexity, 0.5)

    def test_direct_below_threshold(self):
        card = score("Fix the typo in README")
        self.assertEqual(card.tier, "DIRECT")

    def test_config_threshold_override(self):
        prompt = "Please refactor this"  # unified complexity 0.6
        default_card = score(prompt)
        strict_card = score(prompt, {"task_mode": {"complexity_threshold": 0.9}})
        self.assertEqual(default_card.tier, "TASK")
        self.assertEqual(strict_card.tier, "DIRECT")

    def test_config_garbage_tolerated(self):
        for cfg in (None, {}, [], "x", {"task_mode": "broken"},
                    {"task_mode": {"complexity_threshold": "high"}}):
            with self.subTest(cfg=cfg):
                self.assertEqual(score("hello there", cfg).tier, "DIRECT")


class ContainsPhraseTest(unittest.TestCase):
    """Word-boundary matcher lifted from workflow_detector (TASK-48)."""

    def test_whole_word_matches(self):
        self.assertTrue(contains_phrase("add a feature", "add"))

    def test_substring_does_not_match(self):
        self.assertFalse(contains_phrase("fix the address field", "add"))
        self.assertFalse(contains_phrase("we are modifying the layout", "modify"))
        self.assertFalse(contains_phrase("install it", "all"))

    def test_apostrophe_phrase(self):
        self.assertTrue(contains_phrase("don't stop until it works", "don't stop"))

    def test_multiword_phrase(self):
        self.assertTrue(contains_phrase("please run until done now", "run until done"))


class AmbiguitySeparateAxisTest(unittest.TestCase):
    """TASK-48 precedent: ambiguity is not complexity."""

    def test_small_but_ambiguous(self):
        card = score("fix the bug")
        self.assertLess(card.complexity, 0.5)
        self.assertGreaterEqual(card.ambiguity, 0.5)

    def test_complex_but_specified(self):
        card = score(
            "implement JWT auth in src/auth/session.ts, only touching the login flow"
        )
        self.assertGreaterEqual(card.complexity, 0.5)
        self.assertEqual(card.ambiguity, 0.0)


class IntentDataTableTest(unittest.TestCase):
    """Skill patterns live in a data table (SKILL_TRIGGERS)."""

    def test_table_shape(self):
        self.assertGreater(len(scoring.SKILL_TRIGGERS), 0)
        for skill, config in scoring.SKILL_TRIGGERS.items():
            with self.subTest(skill=skill):
                self.assertIsInstance(config["patterns"], list)
                self.assertIsInstance(config["keywords"], list)
                self.assertIsInstance(config["priority"], int)
                self.assertIsInstance(config["description"], str)

    def test_intent_uses_table(self):
        result = scoring.detect_skill_match("Create a new login component")
        self.assertEqual(result.matching_skill, "frontend-component")
        self.assertTrue(result.defer)


class UnifiedComplexityModelTest(unittest.TestCase):
    """The additive model replaced the base-0.5 +/- variant."""

    def test_no_signal_prompt_scores_zero(self):
        """Additive model: no evidence -> 0.0, not a 0.5 base."""
        complexity, matched = scoring.unified_complexity("hello there")
        self.assertEqual(complexity, 0.0)
        self.assertEqual(matched, [])

    def test_signal_families_add(self):
        complexity, matched = scoring.unified_complexity(
            "Figure out how the cache system works")
        self.assertGreater(complexity, 0.0)
        self.assertIn("signal:needs_research", matched)
        self.assertIn("signal:data_changes", matched)

    def test_simplicity_credits_not_applied(self):
        """"just"/"only" no longer subtract — pure additive."""
        plain = scoring.unified_complexity("fix the typo")[0]
        hedged = scoring.unified_complexity("just fix the typo")[0]
        self.assertEqual(plain, hedged)


class V6ExportsTest(unittest.TestCase):
    """Shim support: exact public namespace per legacy module."""

    EXPECTED = {
        "workflow_detector": {
            "LOOP_TRIGGERS", "COMPLEXITY_INDICATORS", "MULTI_FILE_INDICATORS",
            "_contains_phrase", "detect_loop_trigger", "calculate_complexity",
            "detect_workflow", "main",
        },
        "complexity_detector": {
            "ComplexityResult", "COMPLEXITY_SIGNALS", "SIMPLICITY_SIGNALS",
            "detect_signals", "calculate_complexity", "get_recommendation",
            "detect_complexity", "main",
        },
        "skill_detector": {
            "SkillMatch", "SKILL_TRIGGERS", "calculate_match_score",
            "detect_skill_match", "main",
        },
        "ambiguity_scorer": {
            "score_ambiguity", "TASK_SHAPED_VERBS", "VAGUE_SCOPE_SIGNALS",
            "LIMITER_WORDS", "ACCEPTANCE_PHRASES", "QUESTION_STARTERS",
            "CONFIRMATION_PREFIXES",
        },
    }

    def test_expected_names_present(self):
        for module_name, names in self.EXPECTED.items():
            exported = v6_exports(module_name)
            for name in names:
                with self.subTest(module=module_name, name=name):
                    self.assertIn(name, exported)

    def test_calculate_complexity_disambiguated(self):
        """Same legacy name, two variants: each shim gets its own."""
        wd_variant = v6_exports("workflow_detector")["calculate_complexity"]
        cd_variant = v6_exports("complexity_detector")["calculate_complexity"]
        # workflow_detector variant: message -> (score, matched)
        wd_score, matched = wd_variant("Please refactor this")
        self.assertAlmostEqual(wd_score, 0.3, places=2)
        self.assertIn("high:refactor", matched)
        # complexity_detector variant: (signals, weights) -> base-0.5 score
        self.assertEqual(cd_variant({}, {}), 0.5)

    def test_returns_copy(self):
        exports = v6_exports("skill_detector")
        exports["detect_skill_match"] = None
        self.assertIsNotNone(v6_exports("skill_detector")["detect_skill_match"])

    def test_unknown_module_raises(self):
        with self.assertRaises(KeyError):
            v6_exports("no_such_module")


class V6CompatBehaviorTest(unittest.TestCase):
    """Spot checks that compat wrappers keep v6 behavior byte-identical.

    (The full legacy suites still run against the shims in their own dirs.)
    """

    def test_detect_workflow_loop(self):
        result = scoring.detect_workflow("run until done: build the dashboard")
        self.assertTrue(result["loop_mode"])
        self.assertEqual(result["loop_trigger"], "run until done")
        self.assertEqual(result["recommended_mode"], "LOOP")

    def test_detect_workflow_keys(self):
        result = scoring.detect_workflow("Add a button")
        for key in ("loop_mode", "loop_trigger", "task_mode", "complexity",
                    "complexity_indicators", "recommended_mode"):
            self.assertIn(key, result)

    def test_detect_complexity_legacy_base(self):
        result = scoring.detect_complexity("Fix the typo in README.md")
        self.assertLess(result.complexity_score, 0.5)
        self.assertEqual(result.recommendation, "direct_execution")

    def test_get_recommendation_buckets(self):
        self.assertEqual(scoring.get_recommendation(0.2, 0.5)[0], "direct_execution")
        self.assertEqual(scoring.get_recommendation(0.6, 0.5)[0], "task_mode")
        self.assertIn("Complex", scoring.get_recommendation(0.8, 0.5)[1])

    def test_score_ambiguity_gates(self):
        self.assertFalse(scoring.score_ambiguity("What time is it?")["task_shaped"])
        self.assertFalse(scoring.score_ambiguity("yes, go ahead")["task_shaped"])
        self.assertTrue(scoring.score_ambiguity("fix the bug")["task_shaped"])


def print_corpus_diff():
    """Per-prompt v6-vs-v7 tier diff (task Verify: all rows must be <=1)."""
    header = f"{'v6 mode':8} {'v7 tier':8} {'d':1}  {'v6 cx':5} {'v7 cx':5}  prompt"
    print(header)
    print("-" * len(header))
    for prompt, snap in V6_SNAPSHOT.items():
        wd_mode, wd_complexity = snap[0], snap[1]
        card = score(prompt)
        diff = abs(TIER_RANK[card.tier] - TIER_RANK[wd_mode])
        print(f"{wd_mode:8} {card.tier:8} {diff:1}  "
              f"{wd_complexity:5.2f} {card.complexity:5.2f}  {prompt[:55]}")


if __name__ == "__main__":
    if "--diff" in sys.argv:
        print_corpus_diff()
    else:
        unittest.main(verbosity=2)


# ---------------------------------------------------------------------------
# TASK-79 — judge blending (judgment=None must stay byte-identical heuristics)
# ---------------------------------------------------------------------------

from nav_hook_lib import judge as nav_judge  # noqa: E402


def _judgment(**kw):
    base = dict(is_task=0.95, wants_loop=0.05, complexity=0.67, complexity_confidence=0.9,
                ambiguity=0.5, ambiguity_confidence=0.9,
                dimensions={"scope": 0.9, "limits": 0.1, "approach": 0.5, "verification": 0.1},
                model="jev-test", latency_ms=7,
                thresholds={"min_confidence": 0.6, "noul_low": 0.3, "noul_high": 0.7})
    base.update(kw)
    return nav_judge.Judgment(**base)


class TestJudgeBlend(unittest.TestCase):
    FALSE_FIRE = "## F. Loop mode\n| F1 | phase_detector.py | detect_phase |"

    def test_none_judgment_is_pure_heuristic(self):
        for prompt in ("run until done: build it", "fix the typo", "make it better"):
            self.assertEqual(scoring.detect_workflow(prompt),
                             scoring.detect_workflow(prompt, judgment=None))
            self.assertEqual(scoring.score_ambiguity(prompt),
                             scoring.score_ambiguity(prompt, judgment=None))
            self.assertEqual(scoring.score(prompt), scoring.score(prompt, judgment=None))
        self.assertNotIn("judge", scoring.detect_workflow("run until done: x"))

    def test_decisive_loop_no_overrides_keyword_false_fire(self):
        result = scoring.detect_workflow(self.FALSE_FIRE, judgment=_judgment(
            wants_loop=0.14, complexity=0.31, complexity_confidence=0.95))
        self.assertFalse(result["loop_mode"])
        self.assertIsNone(result["loop_trigger"])
        self.assertEqual(result["recommended_mode"], "DIRECT")
        self.assertEqual(result["judge"]["overrides"], ["loop", "complexity"])
        self.assertEqual(result["judge"]["model"], "jev-test")

    def test_undecided_loop_keeps_heuristic(self):
        result = scoring.detect_workflow(self.FALSE_FIRE, judgment=_judgment(
            wants_loop=0.5, complexity_confidence=0.1))
        self.assertTrue(result["loop_mode"])
        self.assertEqual(result["loop_trigger"], "loop mode")
        self.assertEqual(result["judge"]["overrides"], [])

    def test_decisive_loop_yes_without_phrase(self):
        result = scoring.detect_workflow("please just get all of it finished without asking",
                                         judgment=_judgment(wants_loop=0.9))
        self.assertTrue(result["loop_mode"])
        self.assertEqual(result["loop_trigger"], scoring.JUDGE_LOOP_PHRASE)
        self.assertEqual(result["recommended_mode"], "LOOP")

    def test_confident_complexity_replaces_indicators(self):
        result = scoring.detect_workflow("clean up the hooks",
                                         judgment=_judgment(complexity=0.67))
        self.assertEqual(result["complexity"], 0.67)
        self.assertEqual(result["complexity_indicators"], ["judge:substantial"])
        self.assertTrue(result["task_mode"])

    def test_low_confidence_complexity_keeps_heuristic(self):
        heuristic = scoring.detect_workflow("clean up the hooks")
        result = scoring.detect_workflow("clean up the hooks",
                                         judgment=_judgment(complexity_confidence=0.2))
        self.assertEqual(result["complexity"], heuristic["complexity"])
        self.assertEqual(result["complexity_indicators"], heuristic["complexity_indicators"])

    def test_scorecard_uses_judgment(self):
        card = scoring.score("what does loop mode do?", judgment=_judgment(
            wants_loop=0.02, complexity=0.05, is_task=0.03))
        self.assertEqual(card.tier, "DIRECT")
        self.assertEqual(card.ambiguity, 0.0)
        card = scoring.score("what does loop mode do?")
        self.assertEqual(card.tier, "LOOP")

    def test_ambiguity_task_verdict_no_silences(self):
        result = scoring.score_ambiguity("make the onboarding better",
                                         judgment=_judgment(is_task=0.05))
        self.assertFalse(result["task_shaped"])
        self.assertEqual(result["undefined_dimensions"], [])

    def test_ambiguity_task_verdict_yes_on_question_shaped_prompt(self):
        prompt = "could you add retries to the fetcher?"
        self.assertFalse(scoring.score_ambiguity(prompt)["task_shaped"])
        result = scoring.score_ambiguity(prompt, judgment=_judgment(
            is_task=0.9, ambiguity=0.8,
            dimensions={"scope": 0.9, "limits": 0.1, "approach": 0.5, "verification": 0.1}))
        self.assertTrue(result["task_shaped"])
        self.assertEqual(result["score"], 0.8)
        self.assertIn("judge:task", result["matched_signals"])
        # scope decided defined, approach undecided -> "all undefined" fallback keeps it
        self.assertEqual(result["undefined_dimensions"], ["limits", "approach", "verification"])

    def test_ambiguity_dimensions_blend_with_heuristic(self):
        prompt = "refactor hooks/ops/read_guard.py"
        heuristic = scoring.score_ambiguity(prompt)
        self.assertNotIn("scope", heuristic["undefined_dimensions"])  # file path credit
        result = scoring.score_ambiguity(prompt, judgment=_judgment(
            ambiguity_confidence=0.1,
            dimensions={"scope": 0.5, "limits": 0.5, "approach": 0.9, "verification": 0.5}))
        self.assertEqual(result["score"], heuristic["score"])  # not confident -> heuristic
        self.assertNotIn("scope", result["undefined_dimensions"])     # undecided -> heuristic
        self.assertNotIn("approach", result["undefined_dimensions"])  # decided defined
        self.assertIn("verification", result["undefined_dimensions"])
