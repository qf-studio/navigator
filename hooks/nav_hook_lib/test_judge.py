#!/usr/bin/env python3
"""Tests for nav_hook_lib.judge — the typed prompt judge client (TASK-79).

Contract under test:
  - disabled by default: no request is built, no network touched;
  - decisive bands: nouls count only outside [noul_low, noul_high], scores
    only at/above min_confidence;
  - fail-open: missing key, timeout, HTTP error, malformed body -> None;
  - secrets never leave: redact_secrets strips key-shaped tokens before the
    prompt becomes request state; state is head-capped;
  - one call per dispatch: for_ctx caches the result (and a None) on ctx.
"""
from __future__ import annotations

import copy
import io
import json
import os
import sys
import tempfile
import types
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # hooks/

from nav_hook_lib import config as nav_config  # noqa: E402
from nav_hook_lib import judge  # noqa: E402


def api_doc(**overrides):
    """A well-formed API response; overrides patch individual answers."""
    answers = {
        "is_task": {"type": "noul", "noul": 0.96},
        "wants_loop": {"type": "noul", "noul": 0.05},
        "complexity": {"type": "score", "score": 2.1, "confidence": 0.8,
                       "probabilities": {"0": 0, "1": 0.1, "2": 0.7, "3": 0.2}},
        "ambiguity": {"type": "score", "score": 1.0, "confidence": 0.9,
                      "probabilities": {"0": 0.05, "1": 0.9, "2": 0.05}},
        "scope_defined": {"type": "noul", "noul": 0.9},
        "limits_defined": {"type": "noul", "noul": 0.1},
        "approach_defined": {"type": "noul", "noul": 0.5},
        "verification_defined": {"type": "noul", "noul": 0.2},
    }
    for name, value in overrides.items():
        answers[name].update(value)
    return {"model": "jev-1.13.0", "answers": answers,
            "usage": {"input_tokens": 520, "output_tokens": 40}}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_opener(doc, calls=None):
    def opener(request, timeout):
        if calls is not None:
            calls.append((request, timeout))
        return FakeResponse(json.dumps(doc).encode("utf-8"))
    return opener


def enabled_settings(**extra):
    s = dict(judge.DEFAULTS)
    s["enabled"] = True
    s["api_key_env"] = "NAV_TEST_JUDGE_KEY"
    s["api_key_file"] = "/nonexistent/judge-key"
    s.update(extra)
    return s


class JudgeTestBase(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.pop(k, None)
                       for k in ("NAV_TEST_JUDGE_KEY", "PILOT_EXECUTOR")}
        os.environ["NAV_TEST_JUDGE_KEY"] = "test-key"

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestDecide(unittest.TestCase):
    def test_bands(self):
        t = {"noul_low": 0.3, "noul_high": 0.7}
        self.assertTrue(judge.decide(0.9, t))
        self.assertTrue(judge.decide(0.7, t))
        self.assertFalse(judge.decide(0.1, t))
        self.assertFalse(judge.decide(0.3, t))
        self.assertIsNone(judge.decide(0.5, t))
        self.assertIsNone(judge.decide("nan-ish", t))

    def test_defaults_when_no_thresholds(self):
        self.assertTrue(judge.decide(0.95))
        self.assertIsNone(judge.decide(0.5))


class TestParse(unittest.TestCase):
    def test_normalizes_scores_and_reads_dimensions(self):
        j = judge.parse_response(api_doc(), {"min_confidence": 0.6})
        self.assertAlmostEqual(j.complexity, 2.1 / 3, places=4)
        self.assertAlmostEqual(j.ambiguity, 0.9 * 0.35 + 0.05, places=4)  # weighted
        self.assertEqual(j.model, "jev-1.13.0")
        self.assertEqual(j.input_tokens, 520)
        self.assertEqual(set(j.dimensions), set(judge.DIMENSIONS))
        self.assertEqual(j.complexity_level(), "substantial")

    def test_verdicts_follow_thresholds(self):
        j = judge.parse_response(api_doc(), {"min_confidence": 0.85,
                                              "noul_low": 0.3, "noul_high": 0.7})
        self.assertTrue(j.task_verdict())
        self.assertFalse(j.loop_verdict())
        self.assertIsNone(j.complexity_if_confident())   # 0.8 < 0.85
        self.assertAlmostEqual(j.ambiguity_if_confident(), 0.365)  # 0.9 >= 0.85
        self.assertTrue(j.dimension_verdict("scope"))
        self.assertFalse(j.dimension_verdict("limits"))
        self.assertIsNone(j.dimension_verdict("approach"))  # 0.5 in band
        self.assertIsNone(j.dimension_verdict("nonexistent"))

    def test_ambiguity_falls_back_to_linear_without_probabilities(self):
        doc = api_doc()
        del doc["answers"]["ambiguity"]["probabilities"]
        j = judge.parse_response(doc)
        self.assertAlmostEqual(j.ambiguity, 0.5)

    def test_malformed_raises(self):
        with self.assertRaises((KeyError, TypeError, ValueError)):
            judge.parse_response({"answers": {"is_task": {}}})
        with self.assertRaises((KeyError, TypeError, ValueError)):
            judge.parse_response({})


class TestRedaction(unittest.TestCase):
    def test_key_shapes_are_redacted(self):
        samples = [
            "apikey_0000feedfacecafe1234567890abcdef00_ffffffffffffffffffffffff",
            "sk-abcdefghijklmnopqrstuvwxyz0123",
            "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123",
            "AKIAABCDEFGHIJKLMNOP",
            "xoxb-1234567890-abcdefghij",
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV",
            "api_key = 'abc123def456'",
            "Bearer: xyz.secret.value",
            "0123456789abcdef0123456789abcdef01234567",
        ]
        for sample in samples:
            out = judge.redact_secrets(f"please use {sample} for the call")
            self.assertNotIn(sample, out, sample)
            self.assertIn(judge.REDACTED, out, sample)

    def test_ordinary_text_untouched(self):
        text = "refactor hooks/ops/read_guard.py and keep the tests green"
        self.assertEqual(judge.redact_secrets(text), text)

    def test_request_state_is_redacted_and_capped(self):
        s = enabled_settings(max_state_chars=40)
        req = judge.build_request("x" * 30 + " sk-abcdefghijklmnopqrstuvwxyz " + "y" * 100, s)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz", req["state"])
        self.assertLessEqual(len(req["state"]), 40)
        self.assertEqual(req["model"], judge.DEFAULTS["model"])
        self.assertEqual(set(req["questions"]), set(judge.QUESTIONS))


class TestApiKey(JudgeTestBase):
    def test_env_wins(self):
        self.assertEqual(judge.api_key(enabled_settings()), "test-key")

    def test_file_fallback_first_line(self):
        os.environ.pop("NAV_TEST_JUDGE_KEY")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "key"
            path.write_text("  file-key  \nsecond line\n")
            self.assertEqual(judge.api_key(enabled_settings(api_key_file=str(path))),
                             "file-key")

    def test_none_when_absent(self):
        os.environ.pop("NAV_TEST_JUDGE_KEY")
        self.assertIsNone(judge.api_key(enabled_settings()))


class TestCall(JudgeTestBase):
    def test_happy_path_builds_bearer_request(self):
        calls = []
        j = judge.call("fix the typo", enabled_settings(timeout_ms=1234),
                       opener=fake_opener(api_doc(), calls))
        self.assertIsNotNone(j)
        request, timeout = calls[0]
        self.assertAlmostEqual(timeout, 1.234)
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(request.get_method(), "POST")
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["state"], "fix the typo")
        self.assertGreaterEqual(j.latency_ms, 0)

    def test_thresholds_from_settings_travel_on_judgment(self):
        j = judge.call("x", enabled_settings(min_confidence=0.95, noul_high=0.99),
                       opener=fake_opener(api_doc()))
        self.assertIsNone(j.complexity_if_confident())
        self.assertIsNone(j.task_verdict())  # 0.96 < 0.99

    def test_fail_open_on_missing_key(self):
        os.environ.pop("NAV_TEST_JUDGE_KEY")
        calls = []
        self.assertIsNone(judge.call("x", enabled_settings(), opener=fake_opener(api_doc(), calls)))
        self.assertEqual(calls, [])

    def test_fail_open_on_empty_prompt(self):
        calls = []
        self.assertIsNone(judge.call("   ", enabled_settings(), opener=fake_opener(api_doc(), calls)))
        self.assertEqual(calls, [])

    def test_fail_open_on_errors(self):
        def timeout_opener(request, timeout):
            raise TimeoutError("slow")

        def http_opener(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 429, "rate", {}, None)

        def garbage_opener(request, timeout):
            return FakeResponse(b"not json")

        def partial_opener(request, timeout):
            return FakeResponse(json.dumps({"answers": {}}).encode())

        for opener in (timeout_opener, http_opener, garbage_opener, partial_opener):
            self.assertIsNone(judge.call("x", enabled_settings(), opener=opener))


class TestGating(JudgeTestBase):
    def test_disabled_by_default_makes_no_call(self):
        calls = []
        cfg = copy.deepcopy(nav_config.DEFAULTS)
        self.assertFalse(judge.settings(cfg)["enabled"])
        self.assertIsNone(judge.judge_prompt("refactor everything", cfg,
                                             opener=fake_opener(api_doc(), calls)))
        self.assertEqual(calls, [])

    def test_enabled_calls(self):
        calls = []
        cfg = {"judge": enabled_settings()}
        self.assertIsNotNone(judge.judge_prompt("refactor everything", cfg,
                                                opener=fake_opener(api_doc(), calls)))
        self.assertEqual(len(calls), 1)

    def test_pilot_executor_short_circuits(self):
        os.environ["PILOT_EXECUTOR"] = "1"
        calls = []
        cfg = {"judge": enabled_settings()}
        self.assertIsNone(judge.judge_prompt("refactor everything", cfg,
                                             opener=fake_opener(api_doc(), calls)))
        self.assertEqual(calls, [])

    def test_settings_tolerate_missing_or_odd_block(self):
        self.assertEqual(judge.settings({})["timeout_ms"], judge.DEFAULTS["timeout_ms"])
        self.assertEqual(judge.settings(None)["enabled"], False)
        self.assertEqual(judge.settings({"judge": "nope"})["enabled"], False)


class TestForCtx(JudgeTestBase):
    def _ctx(self, cfg):
        return types.SimpleNamespace(event="UserPromptSubmit", payload={"prompt": "x"},
                                     config=cfg, state={}, pilot_executor=False, now=0.0)

    def test_one_call_per_dispatch(self):
        calls = []
        ctx = self._ctx({"judge": enabled_settings()})
        opener = fake_opener(api_doc(), calls)
        first = judge.for_ctx(ctx, "refactor everything", opener=opener)
        second = judge.for_ctx(ctx, "refactor everything", opener=opener)
        self.assertIs(first, second)
        self.assertEqual(len(calls), 1)

    def test_none_is_cached_too(self):
        calls = []
        ctx = self._ctx(copy.deepcopy(nav_config.DEFAULTS))  # disabled
        opener = fake_opener(api_doc(), calls)
        self.assertIsNone(judge.for_ctx(ctx, "x", opener=opener))
        self.assertIsNone(judge.for_ctx(ctx, "x", opener=opener))
        self.assertEqual(calls, [])
        self.assertTrue(hasattr(ctx, "_judgment"))


if __name__ == "__main__":
    unittest.main()


class TestSetupPath(JudgeTestBase):
    """key_source / setup_hint / --check: the user-facing setup surface."""

    def test_key_source_names_env_then_file_never_the_key(self):
        s = enabled_settings()
        self.assertEqual(judge.key_source(s), "env:NAV_TEST_JUDGE_KEY")
        os.environ.pop("NAV_TEST_JUDGE_KEY")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "key"
            path.write_text("file-key\n")
            source = judge.key_source(enabled_settings(api_key_file=str(path)))
            self.assertEqual(source, f"file:{path}")
            self.assertNotIn("file-key", source)
        self.assertIsNone(judge.key_source(enabled_settings()))

    def test_setup_hint_names_env_and_file_and_check_command(self):
        hint = judge.setup_hint(enabled_settings(api_key_file="~/x/key"))
        for needle in ("NAV_TEST_JUDGE_KEY", "~/x/key", "--check", "console.typesafe.ai"):
            self.assertIn(needle, hint)

    def test_check_ready(self):
        lines = []
        rc = judge.check({"judge": enabled_settings()}, opener=fake_opener(api_doc()),
                         out=lines.append)
        self.assertEqual(rc, 0)
        text = "\n".join(lines)
        self.assertIn("judge.enabled: true", text)
        self.assertIn("api key: env:NAV_TEST_JUDGE_KEY", text)
        self.assertIn("round trip: ok — jev-1.13.0", text)
        self.assertNotIn("test-key", text)

    def test_check_no_key_exits_1_with_hint_and_no_call(self):
        os.environ.pop("NAV_TEST_JUDGE_KEY")
        calls, lines = [], []
        rc = judge.check({"judge": enabled_settings()}, opener=fake_opener(api_doc(), calls),
                         out=lines.append)
        self.assertEqual(rc, 1)
        self.assertEqual(calls, [])
        self.assertIn("api key: NOT FOUND", "\n".join(lines))
        self.assertIn("console.typesafe.ai", "\n".join(lines))

    def test_check_disabled_still_round_trips_and_says_how_to_enable(self):
        lines = []
        s = enabled_settings(); s["enabled"] = False
        rc = judge.check({"judge": s}, opener=fake_opener(api_doc()), out=lines.append)
        self.assertEqual(rc, 0)
        self.assertIn("judge.enabled: false", lines[0])
        self.assertIn("enable judge", lines[0])

    def test_check_round_trip_failure_exits_2(self):
        def broken(request, timeout):
            raise TimeoutError()
        lines = []
        rc = judge.check({"judge": enabled_settings()}, opener=broken, out=lines.append)
        self.assertEqual(rc, 2)
        self.assertIn("round trip: FAILED", "\n".join(lines))

    def test_main_check_flag(self):
        lines = []
        rc = judge.main(["--check"], opener=fake_opener(api_doc()), out=lines.append)
        self.assertIn(rc, (0, 1))  # 0 with this env's key, 1 without — never a crash
        self.assertTrue(lines)


class TestTelemetry(JudgeTestBase):
    """TASK-80 B: counters only, never prompt text; nav stats line."""

    def test_record_call_counts_calls_failures_latency(self):
        state = {}
        judge.record_call(state, None, enabled=False)
        self.assertEqual(state, {})  # judge off -> nothing recorded
        judge.record_call(state, None, enabled=True)
        j = judge.parse_response(api_doc()); j.latency_ms = 640
        judge.record_call(state, j, enabled=True)
        j2 = judge.parse_response(api_doc()); j2.latency_ms = 710
        judge.record_call(state, j2, enabled=True)
        block = state["judge"]
        self.assertEqual((block["calls"], block["failed"]), (3, 1))
        self.assertEqual((block["latency_last_ms"], block["latency_max_ms"]), (710, 710))
        self.assertEqual(block["model"], "jev-1.13.0")

    def test_record_axes_accumulates_known_axes_only(self):
        state = {}
        judge.record_axes(state, {"loop": "overridden", "complexity": "undecided", "bogus": "agreed",
                                  "task": "nonsense"})
        judge.record_axes(state, {"loop": "agreed", "complexity": "undecided"})
        judge.record_axes(state, None)
        table = state["judge"]["axes"]
        self.assertEqual(table["loop"], {"overridden": 1, "agreed": 1})
        self.assertEqual(table["complexity"], {"undecided": 2})
        self.assertNotIn("bogus", table)
        self.assertNotIn("task", table)

    def test_summary_lines_empty_until_a_call(self):
        self.assertEqual(judge.summary_lines({}), [])
        self.assertEqual(judge.summary_lines({"judge": {"axes": {"loop": {"agreed": 1}}}}), [])

    def test_summary_line_totals(self):
        state = {}
        j = judge.parse_response(api_doc()); j.latency_ms = 662
        judge.record_call(state, j, enabled=True)
        judge.record_call(state, None, enabled=True)
        judge.record_axes(state, {"loop": "overridden", "complexity": "agreed",
                                  "task": "undecided", "ambiguity": "agreed"})
        lines = judge.summary_lines(state)
        self.assertEqual(lines, ["judge: 2 calls / 1 failed · 662 ms last, 662 ms max",
                                 "judge axes: 1 overridden / 2 agreed / 1 undecided"])
        self.assertTrue(all(len(line) <= 56 for line in lines))

    def test_for_ctx_records_call_when_enabled(self):
        ctx = types.SimpleNamespace(event="UserPromptSubmit", payload={"prompt": "x"},
                                    config={"judge": enabled_settings()}, state={},
                                    pilot_executor=False, now=0.0)
        judge.for_ctx(ctx, "refactor everything", opener=fake_opener(api_doc()))
        judge.for_ctx(ctx, "refactor everything", opener=fake_opener(api_doc()))  # cached
        self.assertEqual(ctx.state["judge"]["calls"], 1)

    def test_for_ctx_records_nothing_when_disabled(self):
        ctx = types.SimpleNamespace(event="UserPromptSubmit", payload={"prompt": "x"},
                                    config=copy.deepcopy(nav_config.DEFAULTS), state={},
                                    pilot_executor=False, now=0.0)
        judge.for_ctx(ctx, "refactor everything", opener=fake_opener(api_doc()))
        self.assertNotIn("judge", ctx.state)
