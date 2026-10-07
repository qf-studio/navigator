#!/usr/bin/env python3
"""Every skill resolves the plugin root with the same two lines (TASK-97).

Two fallbacks for ``CLAUDE_PLUGIN_ROOT`` once coexisted in the skills: a flat cache path that
the versioned cache layout broke on every install, and the marketplace clone that exists only
on GitHub installs. The session_start op now publishes the real root to
``<config home>/plugin-root`` and every skill reads it through one snippet; this test keeps
the snippet identical everywhere so the two forms cannot drift apart again.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = sorted((ROOT / "skills").glob("*/SKILL.md"))

RESOLVER = (
    'PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-'
    '$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"'
)
GUARD = '[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"'
# The versioned cache (`.../navigator/<version>/`) is never a plugin root.
RETIRED_CACHE_FALLBACK = "plugins/cache/navigator-marketplace/navigator"


class SkillPluginRootTest(unittest.TestCase):
    def test_skill_corpus_present(self):
        self.assertGreater(len(SKILLS), 10)

    def test_every_resolver_line_is_the_snippet_and_guarded(self):
        seen = 0
        for path in SKILLS:
            lines = path.read_text(encoding="utf-8").split("\n")
            for i, line in enumerate(lines):
                body = line.strip()
                if "CLAUDE_PLUGIN_ROOT:-$" in body or body.startswith("PLUGIN_DIR="):
                    with self.subTest(file=path.name, line=i + 1):
                        self.assertEqual(body, RESOLVER)
                        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
                        self.assertEqual(nxt, GUARD)
                        self.assertEqual(line[: len(line) - len(body)],
                                         lines[i + 1][: len(lines[i + 1]) - len(nxt)],
                                         "resolver and guard share one indent")
                    seen += 1
        self.assertGreaterEqual(seen, 60)

    def test_no_skill_names_the_flat_cache_path(self):
        for path in SKILLS:
            with self.subTest(file=path.name):
                self.assertNotIn(RETIRED_CACHE_FALLBACK, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
