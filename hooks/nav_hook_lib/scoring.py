#!/usr/bin/env python3
"""nav_hook_lib.scoring — unified prompt scorer (TASK-59, Phase 4).

Unifies the four v6 scorers into one module:

  - skills/nav-start/functions/workflow_detector.py   (loop triggers + additive complexity)
  - skills/nav-workflow/functions/complexity_detector.py (base-0.5 +/- signal model)
  - skills/nav-workflow/functions/skill_detector.py   (intent router, skill data table)
  - skills/nav-brief/functions/ambiguity_scorer.py    (ambiguity — separate axis, TASK-48)

Unified model (``score()`` -> ``ScoreCard``):
  - complexity is ADDITIVE: workflow_detector's indicator weights plus
    complexity_detector's positive signal families, summed from 0.0 and capped
    at 1.0. This replaces complexity_detector's contradictory base-0.5 +/-
    model (plan section 4). Simplicity credits and the 0.5 base are dropped.
  - tier: LOOP (loop trigger present) > TASK (complexity >= threshold) > DIRECT.
  - intent: best skill match from the SKILL_TRIGGERS data table (or None).
  - ambiguity: wrapped ambiguity_scorer output — a SEPARATE axis, never merged
    into complexity (TASK-48 precedent: a small task can be highly ambiguous).
  - triggers: matched loop/indicator/signal tags for observability.

v6 compatibility: every public name of the four legacy modules is re-exported
here with byte-identical behavior; ``v6_exports(module_name)`` returns the
exact public namespace so the old files can be <=5-line re-export shims
(deleted in v8). The two legacy ``calculate_complexity`` variants have
different signatures, hence the per-module export maps instead of ``__all__``.

Pure stdlib. No sibling imports — importable standalone and as a library part.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Shared matching primitive (lifted from workflow_detector._contains_phrase)
# ---------------------------------------------------------------------------

def contains_phrase(text: str, phrase: str) -> bool:
    """True if ``phrase`` occurs in ``text`` on word boundaries.

    Substring matching wrongly fired on word fragments — "add" inside
    "address", "modify" inside "modifying", "all" inside "install". A
    \\b...\\b anchor matches whole words/phrases only. re.escape keeps
    internal spaces and apostrophes literal (e.g. "don't stop").
    Case-sensitive: callers lower-case ``text`` first (v6 convention).
    """
    return re.search(r"\b" + re.escape(phrase) + r"\b", text) is not None


# ---------------------------------------------------------------------------
# Data tables — loop triggers + additive complexity (from workflow_detector)
# ---------------------------------------------------------------------------

# Loop Mode trigger phrases (case-insensitive, matched on word boundaries).
# Bare "everything" and "all of it" were removed in TASK-48: they fired Loop
# Mode on innocuous prompts like "document everything we discussed".
LOOP_TRIGGERS = [
    "run until done",
    "do all",
    "do it all",
    "keep going",
    "iterate until",
    "finish this",
    "complete everything",
    "don't stop",
    "dont stop",
    "until complete",
    "until finished",
    "until done",
    "loop mode",
    "autonomous mode",
]

# Task Mode complexity indicators (case-insensitive)
COMPLEXITY_INDICATORS = {
    # High complexity (0.3 each)
    "high": [
        "refactor",
        "implement",
        "add feature",
        "new feature",
        "architecture",
        "redesign",
        "migrate",
        "overhaul",
    ],
    # Medium complexity (0.2 each)
    "medium": [
        "fix all",
        "update all",
        "change all",
        "modify",
        "enhance",
        "improve",
        "extend",
        "integrate",
    ],
    # Low complexity (0.1 each)
    "low": [
        "add",
        "create",
        "update",
        "fix",
        "change",
        "remove",
        "delete",
    ],
}

# Multi-file indicators (adds 0.2, once)
MULTI_FILE_INDICATORS = [
    "multiple files",
    "several files",
    "across",
    "all files",
    "everywhere",
    "throughout",
    "project-wide",
    "codebase",
]


# ---------------------------------------------------------------------------
# Data tables — signal families (from complexity_detector)
# ---------------------------------------------------------------------------

# Complexity-increasing signals (positive weight). In the unified model these
# are ADDED to the indicator sum; in the legacy compat layer they adjust the
# 0.5 base exactly as v6 did.
COMPLEXITY_SIGNALS = {
    "multi_file": {
        "patterns": [
            r'\b(multiple|several|all|across|throughout)\s+(file|module|component)s?\b',
            r'\brefactor(ing)?\b',
            r'\bmigrat(e|ion)\b',
            r'\bupgrade\b',
            r'\boverhaul\b',
        ],
        "weight": 0.3,
        "description": "Multi-file changes expected"
    },
    "planning_language": {
        "patterns": [
            r'\bimplement(ation)?\b',
            r'\b(add|create|build)\s+(new\s+)?(feature|system|module)\b',
            r'\bdesign\b',
            r'\barchitect(ure)?\b',
            r'\bintegrat(e|ion)\b',
        ],
        "weight": 0.2,
        "description": "Feature implementation language"
    },
    "cross_system": {
        "patterns": [
            r'\b(frontend|backend|database|api)\s+and\s+(frontend|backend|database|api)\b',
            r'\bfull.?stack\b',
            r'\bend.?to.?end\b',
            r'\bclient\s+and\s+server\b',
        ],
        "weight": 0.3,
        "description": "Cross-system changes"
    },
    "needs_research": {
        "patterns": [
            r'\bhow\s+(do|does|should|would)\b',
            r'\bunderstand\b',
            r'\bexplore\b',
            r'\binvestigate\b',
            r'\bfigure\s+out\b',
            r'\bbest\s+(way|approach|practice)\b',
        ],
        "weight": 0.2,
        "description": "Research/exploration required"
    },
    "testing_mentioned": {
        "patterns": [
            r'\bwith\s+tests?\b',
            r'\btest(ing)?\s+(coverage|suite)\b',
            r'\bunit\s+tests?\b',
            r'\bintegration\s+tests?\b',
        ],
        "weight": 0.1,
        "description": "Testing requirements mentioned"
    },
    "security_work": {
        "patterns": [
            r'\bauth(entication|orization)?\b',
            r'\bsecur(e|ity)\b',
            r'\bpermission(s)?\b',
            r'\baccess\s+control\b',
            r'\bencrypt(ion)?\b',
        ],
        "weight": 0.15,
        "description": "Security-sensitive changes"
    },
    "data_changes": {
        "patterns": [
            r'\bdatabase\b',
            r'\bschema\b',
            r'\bdata\s+(model|structure)\b',
            r'\bstate\s+management\b',
            r'\bcache\b',
        ],
        "weight": 0.15,
        "description": "Data/state management changes"
    },
}

# Simplicity-indicating signals (negative weight). Legacy compat only: the
# unified additive model has no base to subtract from, so these are unused
# by score() — kept because complexity_detector's public API exposes them.
SIMPLICITY_SIGNALS = {
    "single_file": {
        "patterns": [
            r'\bin\s+(the\s+)?[a-zA-Z0-9_./]+\.(ts|js|py|tsx|jsx|css|md)\b',
            r'\bjust\s+(this|that|the)\s+(file|function|line)\b',
            r'\bonly\s+(in|the)\b',
        ],
        "weight": -0.3,
        "description": "Single file scope"
    },
    "fix_language": {
        "patterns": [
            r'\b(fix|correct)\s+(a\s+)?(typo|bug|error|issue)\b',
            r'\btypo\b',
            r'\bsmall\s+(fix|change|update)\b',
            r'\bminor\b',
        ],
        "weight": -0.2,
        "description": "Bug fix language"
    },
    "quick_modifier": {
        "patterns": [
            r'\bquick(ly)?\b',
            r'\bsimple\b',
            r'\bjust\b',
            r'\bonly\b',
            r'\bsmall\b',
        ],
        "weight": -0.2,
        "description": "Simplicity modifier"
    },
    "specific_location": {
        "patterns": [
            r'\b(line|row)\s+\d+\b',
            r'\bfunction\s+[a-zA-Z_][a-zA-Z0-9_]*\b',
            r'\bclass\s+[A-Z][a-zA-Z0-9_]*\b',
            r'at\s+[a-zA-Z0-9_./]+:\d+',
        ],
        "weight": -0.15,
        "description": "Specific location provided"
    },
    "update_existing": {
        "patterns": [
            r'\bupdate\s+(the\s+)?\w+\b',
            r'\bchange\s+(the\s+)?\w+\s+to\b',
            r'\brename\b',
            r'\breplace\b',
        ],
        "weight": -0.1,
        "description": "Simple update/change"
    },
}


# ---------------------------------------------------------------------------
# Data table — intent router (skill patterns, from skill_detector)
# ---------------------------------------------------------------------------

SKILL_TRIGGERS = {
    "frontend-component": {
        "patterns": [
            r'\b(create|add|build|make|new)\s+(an?\s+)?(\w+\s+)?component\b',
            r'\bcomponent\s+(for|called|named)\b',
            r'\b(ui|user\s+interface)\s+component\b',
            r'\b(button|modal|form|card|list|table)\s+component\b',
            r'\b\w+component\b',  # PascalCase component names
        ],
        "keywords": ["component", "react", "vue", "ui"],
        "priority": 1,
        "description": "React/Vue component generation"
    },
    "backend-endpoint": {
        "patterns": [
            r'\b(create|add|build|make|new)\s+(an?\s+)?(api\s+)?endpoint\b',
            r'\b(rest|graphql)\s+(api|endpoint)\b',
            r'\b(add|create)\s+(an?\s+)?route\b',
            r'\bapi\s+(for|called|named)\b',
            r'\bendpoint\s+for\b',
        ],
        "keywords": ["endpoint", "api", "route", "rest"],
        "priority": 1,
        "description": "API endpoint generation"
    },
    "database-migration": {
        "patterns": [
            r'\b(create|add|write)\s+(an?\s+)?(database\s+)?migration\b',
            r'\bmigration\s+(for|to)\b',
            r'\b(add|modify|change)\s+(an?\s+)?(database\s+)?(table|column|schema)\b',
            r'\bschema\s+(change|update|migration)\b',
        ],
        "keywords": ["migration", "schema", "table", "column"],
        "priority": 1,
        "description": "Database migration generation"
    },
    "backend-test": {
        "patterns": [
            r'\b(write|create|add)\s+(an?\s+)?(unit\s+)?test(s)?\s+for\s+'
            r'.*(api|endpoint|service|function)\b',
            r'\bbackend\s+test(s)?\b',
            r'\btest\s+(the\s+)?(api|endpoint|service)\b',
            r'\b(write|add|create)\s+test(s)?\b',
            r'\btest\s+this\b',
        ],
        "keywords": ["test", "backend", "unit test", "api test"],
        "priority": 2,
        "description": "Backend test generation"
    },
    "frontend-test": {
        "patterns": [
            r'\b(write|create|add)\s+(an?\s+)?(unit\s+)?test(s)?\s+for\s+.*(component|ui)\b',
            r'\bcomponent\s+test(s)?\b',
            r'\btest\s+(the\s+)?component\b',
            r'\bsnapshot\s+test\b',
            r'\btest\s+this\s+component\b',
            r'\bwrite\s+component\s+test(s)?\b',
        ],
        "keywords": ["test", "component", "snapshot", "jest"],
        "priority": 2,
        "description": "Frontend component test generation"
    },
    "nav-task": {
        "patterns": [
            r'\b(create|document|archive)\s+(an?\s+)?task\b',
            r'\btask\s+doc(umentation)?\b',
            r'\bimplementation\s+plan\b',
            r'\bdocument\s+(this|the)\s+feature\b',
        ],
        "keywords": ["task", "documentation", "implementation plan"],
        "priority": 2,
        "description": "Task documentation management"
    },
    "nav-sop": {
        "patterns": [
            r'\b(create|document|write)\s+(an?\s+)?(sop|standard\s+operating\s+procedure)\b',
            r'\bprocedure\s+for\b',
            r'\bdocument\s+(this\s+)?solution\b',
            r'\bsave\s+(this\s+)?for\s+next\s+time\b',
        ],
        "keywords": ["sop", "procedure", "document solution"],
        "priority": 2,
        "description": "Standard Operating Procedure creation"
    },
    "nav-marker": {
        "patterns": [
            r'\b(create|save)\s+(an?\s+)?(context\s+)?marker\b',
            r'\bsave\s+(my\s+)?progress\b',
            r'\b(create|make)\s+(an?\s+)?checkpoint\b',
            r'\bmark\s+this\s+point\b',
        ],
        "keywords": ["marker", "checkpoint", "save progress"],
        "priority": 3,
        "description": "Context marker creation"
    },
    "nav-compact": {
        "patterns": [
            r'\b(clear|compact)\s+(the\s+)?context\b',
            r'\bstart\s+fresh\b',
            r'\bdone\s+with\s+this\s+task\b',
        ],
        "keywords": ["compact", "clear context", "fresh"],
        "priority": 3,
        "description": "Context compaction"
    },
    "nav-simplify": {
        "patterns": [
            r'\bsimplify\s+(this\s+)?code\b',
            r'\breview\s+for\s+clarity\b',
            r'\bcleanup\s+code\b',
            r'\bcode\s+clarity\b',
        ],
        "keywords": ["simplify", "clarity", "cleanup"],
        "priority": 2,
        "description": "Code simplification"
    },
    "nav-diagnose": {
        "patterns": [
            r'\bsomething\s+(seems|is)\s+(off|wrong)\b',
            r'\byou\'?re\s+not\s+getting\s+(this|it)\b',
            r'\bdiagnose\b',
            r'\bre-?anchor\b',
        ],
        "keywords": ["diagnose", "something off", "re-anchor"],
        "priority": 2,
        "description": "Quality diagnosis"
    },
    "nav-loop": {
        "patterns": [
            r'\brun\s+until\s+done\b',
            r'\bkeep\s+going\s+until\s+complete\b',
            r'\biterate\s+until\s+finished\b',
            r'\bloop\s+mode\b',
            r'\bautonomous\s+mode\b',
        ],
        "keywords": ["loop", "until done", "autonomous"],
        "priority": 1,
        "description": "Loop mode activation"
    },
    "product-design": {
        "patterns": [
            r'\bdesign\s+review\b',
            r'\bfigma\s+(mockup|design|file)\b',
            r'\bdesign\s+handoff\b',
            r'\b(review|analyze)\s+design\b',
        ],
        "keywords": ["design", "figma", "mockup"],
        "priority": 1,
        "description": "Design review automation"
    },
    "visual-regression": {
        "patterns": [
            r'\bvisual\s+regression\b',
            r'\bscreenshot\s+test(ing)?\b',
            r'\b(add|set\s+up)\s+(chromatic|percy|backstop)\b',
            r'\bvisual\s+test(ing)?\b',
        ],
        "keywords": ["visual regression", "chromatic", "percy"],
        "priority": 1,
        "description": "Visual regression testing setup"
    },
}


# ---------------------------------------------------------------------------
# Data tables — ambiguity axis (from ambiguity_scorer, TASK-56/TASK-48)
# ---------------------------------------------------------------------------

QUESTION_STARTERS = {
    "what", "why", "how", "when", "where", "who", "which",
    "can", "could", "should", "is", "are", "do", "does", "did",
    "will", "would",
}

CONFIRMATION_PREFIXES = [
    "yes", "ok", "okay", "sure", "sounds good", "go ahead", "proceed",
    "continue", "looks good", "lgtm", "do it", "correct", "confirmed",
    "approved", "agreed", "that's right", "that's correct",
    "no", "nope", "cancel", "stop",
]
CONFIRMATION_MAX_WORDS = 6

TASK_SHAPED_VERBS = [
    "add", "create", "build", "implement", "refactor", "fix", "update",
    "change", "improve", "enhance", "redesign", "migrate", "integrate",
    "optimize", "rewrite", "replace", "remove", "delete", "write",
    "design", "develop", "extend", "generate", "configure",
    "set up", "clean up",
]

VAGUE_SCOPE_SIGNALS = [
    "the app", "the system", "the api", "the codebase", "the platform",
    "the backend", "the frontend", "the ui", "the project", "the entire",
    "everything", "all of it", "the whole thing",
    "endpoints", "components", "tests", "files", "bugs", "issues", "features",
]

LIMITER_WORDS = [
    "only", "just", "specifically", "excluding", "except",
    "up to", "no more than", "limit to", "solely",
]

ACCEPTANCE_PHRASES = [
    "acceptance criteria", "when done", "success looks like",
    "verify with", "verify that", "done when", "definition of done",
]

APPROACH_CONNECTORS = ["using", "via", "with", "through", "by using", "based on"]

PATH_RE = re.compile(r"[\w.\-]+/[\w.\-/]+")
FILE_RE = re.compile(
    r"\b[\w\-]+\.(?:py|ts|tsx|js|jsx|md|json|yaml|yml|go|rb|java|rs|css|html)\b",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
WORD_RE = re.compile(r"[a-z']+")

BASE_SCORE = 0.5
VAGUE_BONUS = 0.2
CREDIT_FILE_PATH = 0.4
CREDIT_NUMBER = 0.2
CREDIT_LIMITER = 0.2
CREDIT_ACCEPTANCE = 0.3


# ---------------------------------------------------------------------------
# workflow_detector compat — loop triggers + additive message complexity
# ---------------------------------------------------------------------------

def detect_loop_trigger(message: str) -> Tuple[bool, Optional[str]]:
    """Check if message contains Loop Mode trigger phrases.

    Returns:
        (is_triggered, matched_phrase)
    """
    message_lower = message.lower()

    for trigger in LOOP_TRIGGERS:
        if contains_phrase(message_lower, trigger):
            return True, trigger

    return False, None


def calculate_message_complexity(message: str) -> Tuple[float, List[str]]:
    """Additive complexity from indicator phrases (workflow_detector variant).

    Legacy name: workflow_detector.calculate_complexity.

    Returns:
        (score 0.0-1.0, list of matched indicators)
    """
    message_lower = message.lower()
    score = 0.0
    matched = []

    for indicator in COMPLEXITY_INDICATORS["high"]:
        if contains_phrase(message_lower, indicator):
            score += 0.3
            matched.append(f"high:{indicator}")

    for indicator in COMPLEXITY_INDICATORS["medium"]:
        if contains_phrase(message_lower, indicator):
            score += 0.2
            matched.append(f"medium:{indicator}")

    for indicator in COMPLEXITY_INDICATORS["low"]:
        if contains_phrase(message_lower, indicator):
            score += 0.1
            matched.append(f"low:{indicator}")

    for indicator in MULTI_FILE_INDICATORS:
        if contains_phrase(message_lower, indicator):
            score += 0.2
            matched.append(f"multi-file:{indicator}")
            break  # Only count once

    score = min(score, 1.0)

    return score, matched


def detect_workflow(message: str, judgment=None) -> Dict:
    """Full v6 workflow detection - Loop Mode and Task Mode.

    Returns:
        Complete detection result as dict
    """
    loop_triggered, loop_phrase = detect_loop_trigger(message)
    complexity, indicators = calculate_message_complexity(message)

    judged = _apply_judgment(judgment, loop_triggered, loop_phrase, complexity, indicators)
    loop_triggered, loop_phrase, complexity, indicators, judge_info = judged
    task_mode = complexity >= 0.5

    if loop_triggered:
        mode = "LOOP"
    elif task_mode:
        mode = "TASK"
    else:
        mode = "DIRECT"

    result = {
        "loop_mode": loop_triggered,
        "loop_trigger": loop_phrase,
        "task_mode": task_mode,
        "complexity": round(complexity, 2),
        "complexity_indicators": indicators,
        "recommended_mode": mode,
    }
    if judge_info is not None:
        result["judge"] = judge_info
    return result


JUDGE_LOOP_PHRASE = "judged: autonomous iteration requested"


def _apply_judgment(judgment, loop_triggered, loop_phrase, complexity, indicators):
    """Overlay decisive judge axes on the heuristic answers (TASK-79).

    Returns (loop_triggered, loop_phrase, complexity, indicators, judge_info);
    ``judge_info`` is None when no judgment was supplied, so callers can tell
    "heuristic only" from "judged, nothing overridden".
    """
    if judgment is None:
        return loop_triggered, loop_phrase, complexity, indicators, None
    overrides = []
    verdict = judgment.loop_verdict()
    if verdict is not None and verdict != loop_triggered:
        loop_triggered = verdict
        loop_phrase = JUDGE_LOOP_PHRASE if verdict else None
        overrides.append("loop")
    judged_complexity = judgment.complexity_if_confident()
    if judged_complexity is not None:
        complexity = judged_complexity
        indicators = [f"judge:{judgment.complexity_level()}"]
        overrides.append("complexity")
    judge_info = {
        "model": judgment.model,
        "latency_ms": judgment.latency_ms,
        "overrides": overrides,
    }
    return loop_triggered, loop_phrase, complexity, indicators, judge_info


def workflow_detector_main():
    """CLI entry point preserved from workflow_detector.py."""
    parser = argparse.ArgumentParser(description="Navigator Workflow Detector")
    parser.add_argument("message", nargs="?", help="User message to analyze")
    parser.add_argument("--check-loop", action="store_true", help="Only check Loop Mode")
    parser.add_argument("--check-complexity", action="store_true", help="Only check complexity")

    args = parser.parse_args()

    if args.message:
        message = args.message
    else:
        message = sys.stdin.read().strip()

    if not message:
        print(json.dumps({"error": "No message provided"}))
        sys.exit(1)

    if args.check_loop:
        triggered, phrase = detect_loop_trigger(message)
        result = {"loop_mode": triggered, "loop_trigger": phrase}
    elif args.check_complexity:
        score_value, indicators = calculate_message_complexity(message)
        result = {
            "task_mode": score_value >= 0.5,
            "complexity": round(score_value, 2),
            "complexity_indicators": indicators,
        }
    else:
        result = detect_workflow(message)

    print(json.dumps(result, indent=2))

    # Exit code: 0 if workflow mode detected, 1 if direct
    if result.get("recommended_mode") == "DIRECT" and not result.get("loop_mode"):
        sys.exit(1)
    sys.exit(0)


# ---------------------------------------------------------------------------
# complexity_detector compat — legacy base-0.5 +/- signal model
# ---------------------------------------------------------------------------

@dataclass
class ComplexityResult:
    complexity_score: float
    signals: Dict[str, bool]
    signal_weights: Dict[str, float]
    recommendation: str
    reason: str
    is_substantial: bool


def detect_signals(text: str) -> Tuple[Dict[str, bool], Dict[str, float]]:
    """Detect complexity and simplicity signals in text."""
    text_lower = text.lower()

    signals = {}
    weights = {}

    for signal_name, signal_config in COMPLEXITY_SIGNALS.items():
        matched = any(
            re.search(pattern, text_lower)
            for pattern in signal_config["patterns"]
        )
        signals[signal_name] = matched
        if matched:
            weights[signal_name] = signal_config["weight"]

    for signal_name, signal_config in SIMPLICITY_SIGNALS.items():
        matched = any(
            re.search(pattern, text_lower)
            for pattern in signal_config["patterns"]
        )
        signals[signal_name] = matched
        if matched:
            weights[signal_name] = signal_config["weight"]

    return signals, weights


def calculate_signal_complexity(signals: Dict[str, bool], weights: Dict[str, float]) -> float:
    """Legacy base-0.5 +/- score (complexity_detector variant, compat only).

    Legacy name: complexity_detector.calculate_complexity. The unified
    score() does NOT use this — kept solely so the v6 shim's tests and any
    old callers keep byte-identical behavior until v8 deletion.
    """
    base_score = 0.5

    total_adjustment = sum(weights.values())

    final_score = max(0.0, min(1.0, base_score + total_adjustment))

    return round(final_score, 2)


def get_recommendation(score_value: float, threshold: float) -> Tuple[str, str]:
    """Get recommendation based on score."""
    if score_value < 0.3:
        return "direct_execution", "Simple task - direct execution without overhead"
    elif score_value < threshold:
        return "direct_execution", f"Below threshold ({score_value:.2f} < {threshold:.2f})"
    elif score_value < 0.7:
        return "task_mode", "Substantial task - Task Mode recommended"
    else:
        return "task_mode", "Complex task - Task Mode with full phase tracking"


def detect_complexity(
    request: str,
    context: str = "",
    threshold: float = 0.5
) -> ComplexityResult:
    """v6 complexity analysis (legacy base-0.5 +/- model, compat only).

    Args:
        request: User's request/task description
        context: Additional context (recent conversation, etc.)
        threshold: Complexity threshold for Task Mode activation

    Returns:
        ComplexityResult with score, signals, and recommendation
    """
    full_text = f"{request} {context}".strip()

    signals, weights = detect_signals(full_text)

    score_value = calculate_signal_complexity(signals, weights)

    recommendation, reason = get_recommendation(score_value, threshold)

    return ComplexityResult(
        complexity_score=score_value,
        signals=signals,
        signal_weights=weights,
        recommendation=recommendation,
        reason=reason,
        is_substantial=score_value >= threshold
    )


def complexity_detector_main():
    """CLI entry point preserved from complexity_detector.py."""
    parser = argparse.ArgumentParser(
        description="Analyze task complexity"
    )
    parser.add_argument(
        "--request",
        required=True,
        help="User's request/task description"
    )
    parser.add_argument(
        "--context",
        default="",
        help="Additional context"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Complexity threshold (0-1)"
    )
    parser.add_argument(
        "--output",
        choices=["json", "text"],
        default="json",
        help="Output format"
    )

    args = parser.parse_args()

    result = detect_complexity(
        request=args.request,
        context=args.context,
        threshold=args.threshold
    )

    if args.output == "json":
        print(json.dumps(asdict(result), indent=2))
    else:
        print(f"Complexity Score: {result.complexity_score:.2f}")
        print(f"Threshold: {args.threshold:.2f}")
        print(f"Substantial: {'Yes' if result.is_substantial else 'No'}")
        print(f"Recommendation: {result.recommendation}")
        print(f"Reason: {result.reason}")
        print()
        print("Signals detected:")
        for signal, active in result.signals.items():
            if active:
                weight = result.signal_weights.get(signal, 0)
                sign = "+" if weight > 0 else ""
                print(f"  {signal}: {sign}{weight}")

    return 0


# ---------------------------------------------------------------------------
# skill_detector compat — intent router over the SKILL_TRIGGERS data table
# ---------------------------------------------------------------------------

@dataclass
class SkillMatch:
    matching_skill: Optional[str]
    confidence: float
    triggers: List[str]
    defer: bool
    reason: str
    alternative_skills: List[str]


def calculate_match_score(
    text: str,
    patterns: List[str],
    keywords: List[str]
) -> Tuple[float, List[str]]:
    """Calculate how well text matches skill patterns."""
    text_lower = text.lower()
    matched_triggers = []

    # Pattern matches (stronger signal)
    pattern_score = 0
    for pattern in patterns:
        if re.search(pattern, text_lower):
            pattern_score += 0.4
            matched_triggers.append(pattern)

    # Keyword matches (weaker signal)
    keyword_score = 0
    for keyword in keywords:
        if keyword.lower() in text_lower:
            keyword_score += 0.15

    # Cap scores
    pattern_score = min(pattern_score, 0.8)
    keyword_score = min(keyword_score, 0.3)

    total_score = min(pattern_score + keyword_score, 1.0)

    return total_score, matched_triggers


def detect_skill_match(
    request: str,
    available_skills: List[str] = None
) -> SkillMatch:
    """Check if a skill should handle this request.

    Args:
        request: User's request text
        available_skills: List of available skill names (filters results)

    Returns:
        SkillMatch with best matching skill or None
    """
    if available_skills is None:
        available_skills = list(SKILL_TRIGGERS.keys())

    best_match = None
    best_score = 0
    best_triggers = []
    alternatives = []

    for skill_name, skill_config in SKILL_TRIGGERS.items():
        if skill_name not in available_skills:
            continue

        match_score, triggers = calculate_match_score(
            request,
            skill_config["patterns"],
            skill_config["keywords"]
        )

        if match_score > 0.3:  # Minimum threshold for consideration
            if match_score > best_score:
                # Move previous best to alternatives
                if best_match:
                    alternatives.append(best_match)
                best_match = skill_name
                best_score = match_score
                best_triggers = triggers
            else:
                alternatives.append(skill_name)

    defer = best_score >= 0.5

    if best_match:
        skill_desc = SKILL_TRIGGERS[best_match]["description"]
        reason = f"Request matches {best_match} skill ({skill_desc})"
    else:
        reason = "No skill match found - Task Mode should handle"

    return SkillMatch(
        matching_skill=best_match,
        confidence=round(best_score, 2),
        triggers=best_triggers[:3],  # Limit to top 3 triggers
        defer=defer,
        reason=reason,
        alternative_skills=alternatives[:2]  # Limit to top 2 alternatives
    )


def skill_detector_main():
    """CLI entry point preserved from skill_detector.py."""
    parser = argparse.ArgumentParser(
        description="Detect if a skill should handle a request"
    )
    parser.add_argument(
        "--request",
        required=True,
        help="User's request text"
    )
    parser.add_argument(
        "--available-skills",
        default=None,
        help="JSON array of available skill names"
    )
    parser.add_argument(
        "--output",
        choices=["json", "text"],
        default="json",
        help="Output format"
    )

    args = parser.parse_args()

    available_skills = None
    if args.available_skills:
        try:
            available_skills = json.loads(args.available_skills)
        except json.JSONDecodeError:
            # Lazy sibling import: sentinels owns the ONLY stderr writer
            # (mem-034); kept out of module scope so scoring stays
            # importable standalone. Dual-form per lib convention so it
            # resolves both as package member and top-level module.
            try:
                from .sentinels import emit_stderr
            except ImportError:
                from sentinels import emit_stderr
            emit_stderr("Error: --available-skills must be valid JSON array")
            return 1

    result = detect_skill_match(args.request, available_skills)

    if args.output == "json":
        print(json.dumps(asdict(result), indent=2))
    else:
        if result.matching_skill:
            print(f"Matching Skill: {result.matching_skill}")
            print(f"Confidence: {result.confidence:.0%}")
            print(f"Defer: {'Yes' if result.defer else 'No'}")
            print(f"Reason: {result.reason}")
            if result.triggers:
                print(f"Triggers: {', '.join(result.triggers[:2])}")
            if result.alternative_skills:
                print(f"Alternatives: {', '.join(result.alternative_skills)}")
        else:
            print("No skill match found")
            print("Recommendation: Task Mode should orchestrate")

    return 0


# ---------------------------------------------------------------------------
# ambiguity_scorer compat — separate axis, wrapped verbatim (TASK-48)
# ---------------------------------------------------------------------------

def _amb_contains_phrase(text: str, phrase: str) -> bool:
    """Word-boundary match; multiword phrases tolerate any whitespace run."""
    pattern = r"\b" + re.escape(phrase).replace(r"\ ", r"\s+") + r"\b"
    return re.search(pattern, text) is not None


def _first_match(text: str, phrases: list) -> str:
    for phrase in phrases:
        if _amb_contains_phrase(text, phrase):
            return phrase
    return ""


def _is_question(text: str) -> bool:
    if text.rstrip().endswith("?"):
        return True
    words = WORD_RE.findall(text)
    return bool(words) and words[0] in QUESTION_STARTERS


def _is_confirmation(text: str) -> bool:
    words = WORD_RE.findall(text)
    if not words or len(words) > CONFIRMATION_MAX_WORDS:
        return False
    normalized = " ".join(words)
    for phrase in CONFIRMATION_PREFIXES:
        bare = " ".join(WORD_RE.findall(phrase))
        if normalized == bare or normalized.startswith(bare + " "):
            return True
    return False


def _has_file_reference(text: str) -> bool:
    return bool(PATH_RE.search(text) or FILE_RE.search(text))


def _score_ambiguity_heuristic(prompt: str) -> dict:
    """Score a prompt's ambiguity (keyword heuristic).

    Returns {"score": float, "task_shaped": bool,
             "undefined_dimensions": [str], "matched_signals": [str]}.
    Deterministic: same input always produces the same output.
    """
    empty = {
        "score": 0.0,
        "task_shaped": False,
        "undefined_dimensions": [],
        "matched_signals": [],
    }
    text = (prompt or "").lower().strip()
    if not text:
        return empty

    if _is_question(text):
        return {**empty, "matched_signals": ["gate:question"]}
    if _is_confirmation(text):
        return {**empty, "matched_signals": ["gate:confirmation"]}

    verb = _first_match(text, TASK_SHAPED_VERBS)
    if not verb:
        return empty

    signals = [f"verb:{verb}"]
    score_value = BASE_SCORE

    vague = _first_match(text, VAGUE_SCOPE_SIGNALS)
    if vague:
        score_value += VAGUE_BONUS
        signals.append(f"vague:{vague}")

    has_file = _has_file_reference(prompt)  # original case: paths matter
    has_number = bool(NUMBER_RE.search(text))
    limiter = _first_match(text, LIMITER_WORDS)
    acceptance = _first_match(text, ACCEPTANCE_PHRASES)
    approach = _first_match(text, APPROACH_CONNECTORS)

    if has_file:
        score_value -= CREDIT_FILE_PATH
        signals.append("credit:file_path")
    if has_number:
        score_value -= CREDIT_NUMBER
        signals.append("credit:number")
    if limiter:
        score_value -= CREDIT_LIMITER
        signals.append(f"credit:limiter:{limiter}")
    if acceptance:
        score_value -= CREDIT_ACCEPTANCE
        signals.append(f"credit:acceptance:{acceptance}")

    undefined = []
    if not has_file:
        undefined.append("scope")
    if not limiter and not acceptance:
        undefined.append("limits")
    if not approach:
        undefined.append("approach")
    if not acceptance:
        undefined.append("verification")

    return {
        "score": round(max(0.0, min(1.0, score_value)), 2),
        "task_shaped": True,
        "undefined_dimensions": undefined,
        "matched_signals": signals,
    }


AMBIGUITY_DIMENSIONS = ("scope", "limits", "approach", "verification")


def score_ambiguity(prompt: str, judgment=None) -> dict:
    """Ambiguity result, judge-blended when a decisive judgment is supplied.

    With ``judgment=None`` this is exactly the heuristic (deterministic). With
    a judgment (TASK-79): ``is_task`` decides task-shapedness when decisive;
    the ambiguity score replaces the heuristic's when confident; each
    undefined dimension follows its noul when decisive. Undecided axes keep
    the heuristic answer.
    """
    heuristic = _score_ambiguity_heuristic(prompt)
    if judgment is None:
        return heuristic

    task_verdict = judgment.task_verdict()
    task_shaped = heuristic["task_shaped"] if task_verdict is None else task_verdict
    if not task_shaped:
        return {"score": 0.0, "task_shaped": False,
                "undefined_dimensions": [], "matched_signals": []}

    signals = list(heuristic["matched_signals"])
    if heuristic["task_shaped"]:
        score_value = heuristic["score"]
        heuristic_undefined = set(heuristic["undefined_dimensions"])
    else:
        # Heuristic saw no task; the judge did. Start from the base and let
        # the dimension nouls (or, undecided, "all undefined") fill the rows.
        signals.append("judge:task")
        score_value = BASE_SCORE
        heuristic_undefined = set(AMBIGUITY_DIMENSIONS)

    judged_ambiguity = judgment.ambiguity_if_confident()
    if judged_ambiguity is not None:
        score_value = judged_ambiguity
        signals.append("judge:ambiguity")

    undefined = []
    for name in AMBIGUITY_DIMENSIONS:
        verdict = judgment.dimension_verdict(name)
        is_undefined = (name in heuristic_undefined) if verdict is None else (not verdict)
        if is_undefined:
            undefined.append(name)

    return {
        "score": round(max(0.0, min(1.0, score_value)), 2),
        "task_shaped": True,
        "undefined_dimensions": undefined,
        "matched_signals": signals,
    }


# ---------------------------------------------------------------------------
# Unified model — ScoreCard + score()
# ---------------------------------------------------------------------------

@dataclass
class ScoreCard:
    complexity: float
    tier: str
    intent: Optional[str]
    ambiguity: float
    triggers: List[str]


DEFAULT_COMPLEXITY_THRESHOLD = 0.5

# Tier ladder (ordered): DIRECT < TASK < LOOP
TIER_LADDER = ["DIRECT", "TASK", "LOOP"]


def _threshold_from_config(config) -> float:
    """Tolerant read of task_mode.complexity_threshold from a config dict."""
    if not isinstance(config, dict):
        return DEFAULT_COMPLEXITY_THRESHOLD
    task_mode = config.get("task_mode")
    if not isinstance(task_mode, dict):
        return DEFAULT_COMPLEXITY_THRESHOLD
    value = task_mode.get("complexity_threshold", DEFAULT_COMPLEXITY_THRESHOLD)
    try:
        return float(value)
    except (TypeError, ValueError):
        return DEFAULT_COMPLEXITY_THRESHOLD


def unified_complexity(message: str) -> Tuple[float, List[str]]:
    """Pure-additive complexity: indicator weights + positive signal families.

    Replaces the legacy base-0.5 +/- model: starts at 0.0, only adds. The
    workflow_detector indicators and complexity_detector's positive signal
    families both contribute (overlap, e.g. "refactor", intentionally stacks
    — v6 fired both detectors on such prompts too). Simplicity credits are
    dropped: absence of complexity evidence IS the low score.
    """
    score_value, matched = calculate_message_complexity(message)
    text_lower = message.lower()

    for family, family_config in COMPLEXITY_SIGNALS.items():
        hit = any(re.search(p, text_lower) for p in family_config["patterns"])
        if hit:
            score_value += family_config["weight"]
            matched.append(f"signal:{family}")

    return min(round(score_value, 2), 1.0), matched


def score(prompt: str, config: dict = None, judgment=None) -> ScoreCard:
    """Unified prompt scorer: one call, four v6 axes.

    Args:
        prompt: raw user prompt (None tolerated -> empty).
        config: optional loaded nav-config dict; only
            task_mode.complexity_threshold is consulted (default 0.5).
        judgment: optional nav_hook_lib.judge.Judgment; decisive axes
            override the heuristics (TASK-79), None keeps pure heuristics.

    Returns:
        ScoreCard(complexity, tier, intent, ambiguity, triggers)
    """
    text = prompt or ""
    threshold = _threshold_from_config(config)

    loop_triggered, loop_phrase = detect_loop_trigger(text)
    complexity, indicator_tags = unified_complexity(text)
    loop_triggered, loop_phrase, complexity, indicator_tags, _info = _apply_judgment(
        judgment, loop_triggered, loop_phrase, complexity, indicator_tags)
    intent_match = detect_skill_match(text)
    ambiguity = score_ambiguity(text, judgment=judgment)["score"]

    if loop_triggered:
        tier = "LOOP"
    elif complexity >= threshold:
        tier = "TASK"
    else:
        tier = "DIRECT"

    triggers = []
    if loop_phrase:
        triggers.append(f"loop:{loop_phrase}")
    triggers.extend(indicator_tags)
    if intent_match.matching_skill:
        triggers.append(f"intent:{intent_match.matching_skill}")

    return ScoreCard(
        complexity=complexity,
        tier=tier,
        intent=intent_match.matching_skill,
        ambiguity=ambiguity,
        triggers=triggers,
    )


# ---------------------------------------------------------------------------
# v6 shim support — exact public namespaces of the four legacy modules
# ---------------------------------------------------------------------------

_V6_EXPORTS = {
    "workflow_detector": {
        "LOOP_TRIGGERS": LOOP_TRIGGERS,
        "COMPLEXITY_INDICATORS": COMPLEXITY_INDICATORS,
        "MULTI_FILE_INDICATORS": MULTI_FILE_INDICATORS,
        "_contains_phrase": contains_phrase,
        "detect_loop_trigger": detect_loop_trigger,
        "calculate_complexity": calculate_message_complexity,
        "detect_workflow": detect_workflow,
        "main": workflow_detector_main,
    },
    "complexity_detector": {
        "ComplexityResult": ComplexityResult,
        "COMPLEXITY_SIGNALS": COMPLEXITY_SIGNALS,
        "SIMPLICITY_SIGNALS": SIMPLICITY_SIGNALS,
        "detect_signals": detect_signals,
        "calculate_complexity": calculate_signal_complexity,
        "get_recommendation": get_recommendation,
        "detect_complexity": detect_complexity,
        "main": complexity_detector_main,
    },
    "skill_detector": {
        "SkillMatch": SkillMatch,
        "SKILL_TRIGGERS": SKILL_TRIGGERS,
        "calculate_match_score": calculate_match_score,
        "detect_skill_match": detect_skill_match,
        "main": skill_detector_main,
    },
    "ambiguity_scorer": {
        "QUESTION_STARTERS": QUESTION_STARTERS,
        "CONFIRMATION_PREFIXES": CONFIRMATION_PREFIXES,
        "CONFIRMATION_MAX_WORDS": CONFIRMATION_MAX_WORDS,
        "TASK_SHAPED_VERBS": TASK_SHAPED_VERBS,
        "VAGUE_SCOPE_SIGNALS": VAGUE_SCOPE_SIGNALS,
        "LIMITER_WORDS": LIMITER_WORDS,
        "ACCEPTANCE_PHRASES": ACCEPTANCE_PHRASES,
        "APPROACH_CONNECTORS": APPROACH_CONNECTORS,
        "PATH_RE": PATH_RE,
        "FILE_RE": FILE_RE,
        "NUMBER_RE": NUMBER_RE,
        "WORD_RE": WORD_RE,
        "BASE_SCORE": BASE_SCORE,
        "VAGUE_BONUS": VAGUE_BONUS,
        "CREDIT_FILE_PATH": CREDIT_FILE_PATH,
        "CREDIT_NUMBER": CREDIT_NUMBER,
        "CREDIT_LIMITER": CREDIT_LIMITER,
        "CREDIT_ACCEPTANCE": CREDIT_ACCEPTANCE,
        "_contains_phrase": _amb_contains_phrase,
        "_first_match": _first_match,
        "_is_question": _is_question,
        "_is_confirmation": _is_confirmation,
        "_has_file_reference": _has_file_reference,
        "score_ambiguity": score_ambiguity,
    },
}


def v6_exports(module_name: str) -> dict:
    """Exact public namespace of a legacy v6 scorer module.

    Shim support only (skills/*/functions/*.py are <=5-line re-export shims
    over this map). Scheduled for deletion in v8 along with the shims.
    """
    return dict(_V6_EXPORTS[module_name])
