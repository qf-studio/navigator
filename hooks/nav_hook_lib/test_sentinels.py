#!/usr/bin/env python3
"""Unit tests for nav_hook_lib/sentinels.py (tag registry, strip, stderr emitter).

stdlib unittest only (pytest not installed). Covers:

  - TAGS registry completeness against the frozen fixture list enumerated
    from the v6 sources (adding/removing a tag must update the fixture).
  - wrap()/strip_all() for block tags (span excised), marker tags (marker
    only), orphaned tags (truncated echo), and idempotence.
  - mem-053 harness echo: 'Original prompt: <trigger>' lines appended by
    Claude Code outside the sentinel wrap are removed IFF a sentinel was
    stripped — PERMANENT test.
  - emit_stderr() redaction — the mem-034 echo case (a LOOP_TRIGGERS phrase
    like 'run until done' inside stderr) is a PERMANENT test.
  - lint: no 'sys.stderr' anywhere under hooks/ outside sentinels.py, minus
    the nine unported v6 hooks (allowlist empties in TASK-61 Phase 7).
"""

import contextlib
import io
import unittest
from pathlib import Path

import sentinels

# Frozen fixture: every sentinel tag enumerated from the v6 sources
# (hooks/*.py + skills/*/functions/*.py sweep + git-history pickaxe over
# retired hooks, 2026-07-10). No legacy tags existed at extraction time; when
# one appears it MUST be added here and to TAGS simultaneously.
FIXTURE_TAGS = {
    "nav-workflow-block": "<nav-workflow-block>",
    "nav-read-guard-block": "<nav-read-guard-block>",
    "nav-task-doc-guard-block": "<nav-task-doc-guard-block>",
    "nav-session-start-injected:v1": "<!-- nav-session-start-injected:v1 -->",
    # Tier-1 answers (ops/prompt_tier1.py) are intentionally UNWRAPPED — a block
    # reason renders as plain text, so a marker would show literally; Tier-1 is
    # self-safe via its exact-match + 48-char rail (S4/mem-053). No tag here.
}

# mem-034: the live-observed recursive-block trigger phrase.
LOOP_TRIGGER_PHRASE = "run until done"


class TagsRegistryTest(unittest.TestCase):
    def test_registry_matches_fixture_exactly(self):
        self.assertEqual(set(sentinels.TAGS), set(FIXTURE_TAGS))
        for name, open_tag in FIXTURE_TAGS.items():
            self.assertEqual(sentinels.TAGS[name]["open"], open_tag)

    def test_block_tags_have_close_markers_do_not(self):
        for name, spec in sentinels.TAGS.items():
            if spec["kind"] == "block":
                self.assertTrue(spec["close"], name)
            else:
                self.assertEqual(spec["kind"], "marker", name)
                self.assertIsNone(spec["close"], name)

    def test_every_tag_declares_status(self):
        for name, spec in sentinels.TAGS.items():
            self.assertIn(spec["status"], ("current", "legacy"), name)


class WrapTest(unittest.TestCase):
    def test_wrap_block_tag(self):
        wrapped = sentinels.wrap("nav-workflow-block", "blocked: reason here")
        self.assertTrue(wrapped.startswith("<nav-workflow-block>\n"))
        self.assertTrue(wrapped.endswith("\n</nav-workflow-block>"))
        self.assertIn("blocked: reason here", wrapped)

    def test_wrap_marker_tag_prepends_marker_line(self):
        wrapped = sentinels.wrap("nav-session-start-injected:v1", "# Navigator Session Start")
        lines = wrapped.split("\n")
        self.assertEqual(lines[0], "<!-- nav-session-start-injected:v1 -->")
        self.assertEqual(lines[1], "# Navigator Session Start")

    def test_wrap_unknown_tag_raises(self):
        with self.assertRaises(KeyError):
            sentinels.wrap("nav-not-a-tag", "text")


class StripAllTest(unittest.TestCase):
    def test_strips_every_fixture_tag(self):
        # One document embedding EVERY registered tag; nothing may survive.
        parts = ["user asked: please summarize the readme"]
        for name, spec in sentinels.TAGS.items():
            if spec["kind"] == "block":
                parts.append(sentinels.wrap(name, f"notice for {name}: {LOOP_TRIGGER_PHRASE}"))
            else:
                parts.append(spec["open"])
        doc = "\n".join(parts)
        stripped = sentinels.strip_all(doc)
        for open_tag in FIXTURE_TAGS.values():
            self.assertNotIn(open_tag, stripped)
        self.assertNotIn("</nav-workflow-block>", stripped)
        self.assertNotIn("</nav-read-guard-block>", stripped)
        # Block CONTENT is excised too — the echoed trigger phrase is gone.
        self.assertNotIn(LOOP_TRIGGER_PHRASE, stripped)
        # Non-sentinel text survives.
        self.assertIn("please summarize the readme", stripped)

    # PERMANENT (mem-053 / FIX 3): Claude Code appends 'Original prompt:
    # <trigger>' to UserPromptSubmit block messages OUTSIDE the sentinel wrap.
    # Stripping only tagged spans would leave the trigger phrase behind and
    # re-trigger the gate recursively — strip_all must remove that echo line
    # whenever a sentinel was present.
    def test_mem053_original_prompt_echo_removed_with_block_notice(self):
        block_notice = sentinels.wrap(
            "nav-workflow-block",
            "Navigator blocked this prompt: workflow check required first",
        )
        doc = block_notice + f"\nOriginal prompt: {LOOP_TRIGGER_PHRASE}\n"
        stripped = sentinels.strip_all(doc)
        self.assertNotIn(LOOP_TRIGGER_PHRASE, stripped)
        self.assertNotIn("Original prompt:", stripped)

    def test_mem053_indented_original_prompt_echo_removed(self):
        doc = (
            sentinels.wrap("nav-read-guard-block", "blocked at 7 reads")
            + f"\n   Original prompt: {LOOP_TRIGGER_PHRASE} please\n"
        )
        stripped = sentinels.strip_all(doc)
        self.assertNotIn(LOOP_TRIGGER_PHRASE, stripped)

    def test_original_prompt_line_untouched_without_sentinels(self):
        # Targeted removal: ordinary user text mentioning 'Original prompt:'
        # must never be altered when no sentinel is present.
        plain = "Original prompt: please summarize the readme\nsecond line"
        self.assertEqual(sentinels.strip_all(plain), plain)

    def test_block_span_content_removed(self):
        doc = "before\n" + sentinels.wrap("nav-read-guard-block", "blocked at 7 reads") + "\nafter"
        stripped = sentinels.strip_all(doc)
        self.assertNotIn("blocked at 7 reads", stripped)
        self.assertIn("before", stripped)
        self.assertIn("after", stripped)

    def test_marker_strip_preserves_surrounding_content(self):
        doc = sentinels.wrap("nav-session-start-injected:v1", "# Navigator Session Start\nbody")
        stripped = sentinels.strip_all(doc)
        self.assertNotIn("nav-session-start-injected", stripped)
        self.assertIn("# Navigator Session Start", stripped)
        self.assertIn("body", stripped)

    def test_orphan_open_tag_removed(self):
        # Truncated echo: open tag without its close (mem-034 defensive case).
        doc = "text <nav-workflow-block>\ntruncated notice with no close tag"
        stripped = sentinels.strip_all(doc)
        self.assertNotIn("<nav-workflow-block>", stripped)

    def test_orphan_close_tag_removed(self):
        doc = "tail of an echo</nav-read-guard-block> plus text"
        stripped = sentinels.strip_all(doc)
        self.assertNotIn("</nav-read-guard-block>", stripped)
        self.assertIn("plus text", stripped)

    def test_idempotent_and_plain_text_untouched(self):
        plain = "no sentinels anywhere in this prompt"
        self.assertEqual(sentinels.strip_all(plain), plain)
        once = sentinels.strip_all(sentinels.wrap("nav-workflow-block", "x"))
        self.assertEqual(sentinels.strip_all(once), once)

    def test_empty_input(self):
        self.assertEqual(sentinels.strip_all(""), "")


class EmitStderrTest(unittest.TestCase):
    def _emit(self, text, redact=None):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            sentinels.emit_stderr(text, redact=redact)
        return buf.getvalue()

    # PERMANENT (mem-034): stderr echoing a LOOP_TRIGGERS phrase re-triggers
    # the UserPromptSubmit block recursively. The emitter must redact it.
    def test_mem034_loop_trigger_phrase_redacted(self):
        out = self._emit(
            f"Navigator blocked: loop trigger '{LOOP_TRIGGER_PHRASE}' detected",
            redact=[LOOP_TRIGGER_PHRASE],
        )
        self.assertNotIn(LOOP_TRIGGER_PHRASE, out)
        self.assertIn(sentinels.REDACTION_PLACEHOLDER, out)
        self.assertIn("Navigator blocked", out)

    def test_redaction_is_case_insensitive(self):
        out = self._emit("prompt requests: Run Until Done", redact=[LOOP_TRIGGER_PHRASE])
        self.assertNotIn("Run Until Done", out)
        self.assertIn(sentinels.REDACTION_PLACEHOLDER, out)

    def test_redacts_every_phrase_in_list(self):
        out = self._emit(
            "matched 'run until done' and 'keep going' and 'do all'",
            redact=["run until done", "keep going", "do all"],
        )
        for phrase in ("run until done", "keep going", "do all"):
            self.assertNotIn(phrase, out)
        self.assertEqual(out.count(sentinels.REDACTION_PLACEHOLDER), 3)

    def test_no_redact_list_passes_through(self):
        out = self._emit("nav_read_guard: counter write failed")
        self.assertEqual(out, "nav_read_guard: counter write failed\n")

    def test_output_ends_with_single_newline(self):
        self.assertEqual(self._emit("already terminated\n"), "already terminated\n")
        self.assertEqual(self._emit("bare"), "bare\n")


class StderrLintTest(unittest.TestCase):
    """Nothing under hooks/ other than sentinels.py may touch sys.stderr (mem-034).

    Widened from lib-only to ALL of hooks/**/*.py (TASK-59 audit gap): a new
    hook or op writing stderr directly would bypass the redaction gate that
    keeps trigger phrases out of echoed block notices.
    """

    # TASK-61 Phase 7: the v6 hooks are deleted; nothing under hooks/ may
    # write stderr except sentinels.py. Keep empty.
    V6_HOOK_ALLOWLIST = frozenset()

    def test_no_stderr_writes_outside_sentinels(self):
        lib_dir = Path(__file__).resolve().parent
        hooks_dir = lib_dir.parent
        emitter = lib_dir / "sentinels.py"
        offenders = []
        for source in sorted(hooks_dir.rglob("*.py")):
            rel = source.relative_to(hooks_dir).as_posix()
            if source == emitter or source.name.startswith("test_"):
                continue
            if rel in self.V6_HOOK_ALLOWLIST:
                continue
            text = source.read_text(encoding="utf-8", errors="replace")
            for lineno, line in enumerate(text.splitlines(), 1):
                if "sys.stderr" in line:
                    offenders.append(f"{rel}:{lineno}: {line.strip()}")
        self.assertEqual(
            offenders, [],
            "stderr writes outside sentinels.py (route through "
            "sentinels.emit_stderr):\n" + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
