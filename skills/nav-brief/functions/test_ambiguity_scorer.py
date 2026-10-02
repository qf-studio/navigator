#!/usr/bin/env python3
"""Unit tests for ambiguity_scorer.py (TASK-56).

stdlib unittest only (pytest not installed). Assertions are bucket-based
(score >= / < threshold), never exact floats, so weights can be retuned
without rewriting fixtures.
"""

import unittest

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

# v8: the ambiguity_scorer shim is gone; tested on scoring directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks" / "nav_hook_lib"))
from scoring import score_ambiguity  # noqa: E402

THRESHOLD = 0.5  # default brief_hook.ambiguity_threshold


class ZeroOutGatesTest(unittest.TestCase):
    def test_question_scores_zero(self):
        result = score_ambiguity("What time is it?")
        self.assertEqual(result["score"], 0.0)
        self.assertFalse(result["task_shaped"])

    def test_question_gate_wins_over_verb(self):
        # "refactor" is a task verb, but the question gate short-circuits.
        result = score_ambiguity("Should I refactor this file?")
        self.assertEqual(result["score"], 0.0)
        self.assertFalse(result["task_shaped"])

    def test_interrogative_first_word_without_question_mark(self):
        result = score_ambiguity("why does the build fail")
        self.assertEqual(result["score"], 0.0)
        self.assertFalse(result["task_shaped"])

    def test_confirmation_scores_zero(self):
        result = score_ambiguity("yes, go ahead")
        self.assertEqual(result["score"], 0.0)
        self.assertFalse(result["task_shaped"])

    def test_confirmation_with_verb_scores_zero(self):
        # "ship" is not a task verb, but "do it" family must not fire either.
        result = score_ambiguity("looks good, ship it")
        self.assertEqual(result["score"], 0.0)
        self.assertFalse(result["task_shaped"])

    def test_long_prompt_starting_with_no_is_not_confirmation(self):
        # >6 words: the confirmation gate must not swallow real corrections.
        result = score_ambiguity("no, remove the retry logic from the client entirely")
        self.assertTrue(result["task_shaped"])

    def test_non_task_prompt_scores_zero(self):
        result = score_ambiguity("the deploy finished ten minutes ago")
        self.assertEqual(result["score"], 0.0)
        self.assertFalse(result["task_shaped"])

    def test_empty_prompt(self):
        result = score_ambiguity("")
        self.assertEqual(result["score"], 0.0)
        self.assertFalse(result["task_shaped"])


class ScoreBucketsTest(unittest.TestCase):
    def test_file_scoped_fix_is_low(self):
        result = score_ambiguity("fix the typo in README.md")
        self.assertTrue(result["task_shaped"])
        self.assertLess(result["score"], THRESHOLD)

    def test_bare_fix_the_bug_is_high(self):
        result = score_ambiguity("fix the bug")
        self.assertTrue(result["task_shaped"])
        self.assertGreaterEqual(result["score"], THRESHOLD)

    def test_refactor_the_api_is_high(self):
        result = score_ambiguity("refactor the API")
        self.assertTrue(result["task_shaped"])
        self.assertGreaterEqual(result["score"], THRESHOLD)

    def test_rate_limiting_all_endpoints_is_high(self):
        result = score_ambiguity("add rate limiting to all API endpoints")
        self.assertTrue(result["task_shaped"])
        self.assertGreaterEqual(result["score"], THRESHOLD)

    def test_clean_up_codebase_is_high(self):
        result = score_ambiguity("clean up the codebase")
        self.assertTrue(result["task_shaped"])
        self.assertGreaterEqual(result["score"], THRESHOLD)

    def test_path_plus_limiter_is_low(self):
        result = score_ambiguity(
            "implement JWT auth in src/auth/session.ts, only touching the login flow"
        )
        self.assertTrue(result["task_shaped"])
        self.assertLess(result["score"], THRESHOLD)

    def test_number_plus_limiter_is_low(self):
        result = score_ambiguity(
            "update the changelog for v6.18.0, only add the 3 new entries"
        )
        self.assertTrue(result["task_shaped"])
        self.assertLess(result["score"], THRESHOLD)

    def test_acceptance_criteria_lowers_score(self):
        result = score_ambiguity(
            "acceptance criteria: users can log in with email; "
            "implement login flow, verify with unit tests when done"
        )
        self.assertTrue(result["task_shaped"])
        self.assertLess(result["score"], THRESHOLD)


class WordBoundaryTest(unittest.TestCase):
    """TASK-48 discipline: token-boundary matching, no substring hits."""

    def test_addressing_does_not_match_add(self):
        result = score_ambiguity("addressing this issue in the retro doc")
        self.assertFalse(result["task_shaped"])

    def test_created_does_not_match_create(self):
        result = score_ambiguity("it created a mess yesterday")
        self.assertFalse(result["task_shaped"])

    def test_multiword_verb_matches_across_whitespace(self):
        result = score_ambiguity("clean  up the codebase")
        self.assertTrue(result["task_shaped"])


class DimensionsAndSignalsTest(unittest.TestCase):
    def test_undefined_dimensions_for_vague_prompt(self):
        result = score_ambiguity("refactor the API")
        for dim in ("scope", "limits", "approach", "verification"):
            self.assertIn(dim, result["undefined_dimensions"])

    def test_defined_dimensions_are_omitted(self):
        result = score_ambiguity(
            "implement JWT auth in src/auth/session.ts, only touching the login flow"
        )
        self.assertNotIn("scope", result["undefined_dimensions"])
        self.assertNotIn("limits", result["undefined_dimensions"])

    def test_non_task_prompt_has_no_dimensions(self):
        result = score_ambiguity("What time is it?")
        self.assertEqual(result["undefined_dimensions"], [])

    def test_matched_signals_present(self):
        result = score_ambiguity("refactor the API")
        self.assertTrue(any(s.startswith("verb:") for s in result["matched_signals"]))
        self.assertTrue(any(s.startswith("vague:") for s in result["matched_signals"]))

    def test_pure_function_deterministic(self):
        prompt = "add rate limiting to all API endpoints"
        self.assertEqual(score_ambiguity(prompt), score_ambiguity(prompt))

    def test_score_clamped_to_zero(self):
        result = score_ambiguity(
            "fix the typo in docs/README.md line 12, only that one, done when it reads correctly"
        )
        self.assertGreaterEqual(result["score"], 0.0)


if __name__ == "__main__":
    unittest.main()
