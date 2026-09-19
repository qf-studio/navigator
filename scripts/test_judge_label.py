#!/usr/bin/env python3
"""Tests for scripts/judge_label.py extraction filters (TASK-80 A)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import judge_label  # noqa: E402


def entry(text, **extra):
    d = {"type": "user", "message": {"content": text}}
    d.update(extra)
    return d


class ExtractionTest(unittest.TestCase):
    def test_filters(self):
        self.assertTrue(judge_label.is_user_prompt(entry("fix the typo")))
        self.assertFalse(judge_label.is_user_prompt(entry("fix", isMeta=True)))
        self.assertFalse(judge_label.is_user_prompt(entry("fix", isSidechain=True)))
        self.assertFalse(judge_label.is_user_prompt({"type": "user", "message": {"content": [{"type": "tool_result"}]}}))
        self.assertFalse(judge_label.is_user_prompt({"type": "assistant", "message": {"content": "x"}}))
        for prefix in judge_label.SKIP_PREFIXES:
            self.assertFalse(judge_label.is_user_prompt(entry(prefix + " tail")))
        self.assertFalse(judge_label.is_user_prompt(entry("ok")))

    def test_extract_redacts_dedups_and_skips_agent_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "-Users-me-proj"
            proj.mkdir()
            lines = [entry("refactor the auth module"), entry("REFACTOR the auth module"),
                     entry("use sk-abcdefghijklmnopqrstuvwxyz for the call"),
                     entry("Stop hook feedback: nope")]
            (proj / "s1.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n")
            (proj / "agent-1.jsonl").write_text(json.dumps(entry("model-written prompt")) + "\n")
            items = judge_label.extract(Path(tmp), limit=10, per_project=10, seed=1)
        texts = sorted(i["text"] for i in items)
        self.assertEqual(len(texts), 2)
        self.assertNotIn("model-written prompt", texts)
        self.assertTrue(any("[redacted]" in t and "sk-abc" not in t for t in texts))
        self.assertTrue(all(i["tier"] is None for i in items))


if __name__ == "__main__":
    unittest.main()
