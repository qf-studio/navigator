"""Parity fixtures for the reject log (TASK-88).

Runs ``nav_hook_lib.rejects.line`` over a corpus of refusals and records the exact bytes;
``hooks/mod/tests/rejects.test.ts`` asserts ``rejectLine`` produces the same string for each.
"""
from __future__ import annotations

import sys

import gen_mod_data as g

sys.path.insert(0, str(g.ROOT / "hooks"))
from nav_hook_lib import rejects  # noqa: E402

FIXTURES = g.ROOT / "hooks/mod/tests/fixtures"

CORPUS = [
    {"ts": "2026-10-05T09:06:06.895917+00:00", "session": "s1", "event": "Stop",
     "op": "stop_completion", "tool": None, "suppressed": False,
     "reject": {"reason": "mutating turn, 1/6 indicators met, no exit signal",
                "evidence": {"met": 1, "unmet": ["code_committed", "tests_passing"],
                             "mutating_tools": ["Bash"]}}},
    {"ts": "2026-10-05T09:06:06+00:00", "session": "s1", "event": "PreToolUse",
     "op": "read_guard", "tool": "Read", "suppressed": False,
     "reject": {"reason": "5 .agent/ reads this turn (escalate_threshold=5)",
                "evidence": {"path": "tasks/TASK-88-reject-log.md", "count": 5, "threshold": 5}}},
    {"ts": "2026-10-05T09:06:06+00:00", "session": None, "event": "UserPromptSubmit",
     "op": "prompt_gate", "tool": None, "suppressed": True,
     "reject": {"reason": "loop trigger after a skipped WORKFLOW CHECK (strict_block)",
                "evidence": {"trigger": "run until done"}}},
    {"ts": "T", "session": "s", "event": "Stop", "op": "x", "tool": "", "suppressed": False,
     "reject": {}},
    {"ts": "T", "session": "s", "event": "Stop", "op": "x", "tool": None, "suppressed": False,
     "reject": {"reason": "quotes \" and \\ and unicode — café", "evidence": {"nested": {"a": [1, 2, {"b": None}]}, "flag": True}}},
    {"ts": "T", "session": "s", "event": "Stop", "op": "x", "tool": None, "suppressed": False,
     "reject": {"reason": "control chars \t\n\u0001", "evidence": "not-a-dict"}},
]


def _build() -> str:
    cases = []
    for case in CORPUS:
        cases.append({**case, "line": rejects.line(
            case["ts"], case["session"], case["event"], case["op"], case["tool"],
            case["reject"], suppressed=case["suppressed"])})
    return g.HEADER + "\n" + g.ts_const("REJECT_LINES", cases)


TARGETS = {FIXTURES / "rejects.gen.ts": _build}
