#!/usr/bin/env python3
"""
Code Analyzer for Navigator Simplification Skill

Analyzes code files for simplification opportunities based on Anthropic's
code-simplifier patterns.

Usage:
    python3 code_analyzer.py --file src/utils/auth.ts
    python3 code_analyzer.py --file src/utils/auth.ts --output json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

try:
    from cost_analyzer import compute_cost_score
except ImportError:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent))
    from cost_analyzer import compute_cost_score

# Per-issue-type benefit weights — bigger number = simplifying this type
# of issue yields more readability gain.
TYPE_WEIGHTS: dict[str, float] = {
    "deep_nesting": 3.0,
    "nested_ternary": 2.5,
    "long_function": 2.0,
    "unclear_naming": 1.0,
    "redundant_comparison": 0.5,
}

DEFAULT_BENEFIT_WEIGHTS: dict[str, float] = {
    "density": 0.4,
    "severity_impact": 0.4,
    "in_active_diff": 0.2,
}

DEFAULT_SCORING_THRESHOLDS: dict[str, float] = {
    "skip_below": 0.5,
    "suggest_below": 1.5,
    "auto_apply_at": 1.5,
}

SEVERITY_WEIGHTS: dict[str, float] = {"high": 3.0, "medium": 2.0, "low": 1.0}


def detect_indent_unit(content: str, default: int = 2) -> int:
    """Auto-detect indent unit (spaces per level) from file content.

    Strategy:
        1. If any line starts with a tab, use 1 (each tab = one level).
        2. Otherwise, take the smallest non-zero leading-space count seen
           on a non-blank line. That's the file's indent unit.
        3. Clamp to {2, 4, 8} — anything else is almost certainly noise.
        4. Fall back to `default` if no indented lines were observed.
    """
    min_indent = None
    for line in content.split('\n'):
        if not line.strip():
            continue
        if line.startswith('\t'):
            return 1
        stripped = line.lstrip(' ')
        leading = len(line) - len(stripped)
        if leading == 0:
            continue
        if min_indent is None or leading < min_indent:
            min_indent = leading

    if min_indent is None:
        return default
    # Snap to common indent widths
    if min_indent in (2, 4, 8):
        return min_indent
    if min_indent == 1 or min_indent == 3:
        return 2  # likely a continuation line, not the true indent
    return min_indent


def analyze_nesting_depth(content: str) -> list[dict[str, Any]]:
    """Detect deeply nested code blocks.

    Indent unit is auto-detected from the file rather than hardcoded — 2/4-space
    files (Python, Go, Java, TypeScript variants) and tab-indented files all
    measure correctly.
    """
    issues = []
    lines = content.split('\n')
    indent_unit = detect_indent_unit(content)

    for i, line in enumerate(lines, 1):
        stripped = line.lstrip()
        if not stripped:
            continue

        # Tabs: depth = leading-tab count; spaces: depth = leading-spaces / unit
        if line.startswith('\t'):
            depth = len(line) - len(line.lstrip('\t'))
        else:
            indent = len(line) - len(stripped)
            depth = indent // indent_unit if indent_unit > 0 else 0

        if depth > 3:
            issues.append({
                "line": i,
                "type": "deep_nesting",
                "severity": "high" if depth > 4 else "medium",
                "depth": depth,
                "indent_unit": indent_unit,
                "suggestion": "Extract to helper function or use early returns"
            })

    return issues


def analyze_nested_ternaries(content: str) -> list[dict[str, Any]]:
    """Detect nested ternary operators."""
    issues = []
    lines = content.split('\n')

    # Pattern: condition ? (another_condition ? x : y) : z
    nested_ternary_pattern = r'\?[^?:]*\?'

    for i, line in enumerate(lines, 1):
        if re.search(nested_ternary_pattern, line):
            issues.append({
                "line": i,
                "type": "nested_ternary",
                "severity": "medium",
                "suggestion": "Convert to switch statement or if-else chain"
            })

    return issues


def analyze_function_length(content: str) -> list[dict[str, Any]]:
    """Detect overly long functions."""
    issues = []

    # Simple pattern for function detection
    function_patterns = [
        r'function\s+(\w+)\s*\([^)]*\)\s*{',
        r'(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*{',
        r'(\w+)\s*:\s*(?:async\s*)?\([^)]*\)\s*=>\s*{',
    ]

    lines = content.split('\n')

    for pattern in function_patterns:
        for match in re.finditer(pattern, content):
            start_pos = match.start()
            start_line = content[:start_pos].count('\n') + 1

            # Find matching closing brace (simplified)
            brace_count = 0
            end_line = start_line
            in_function = False

            for i, line in enumerate(lines[start_line - 1:], start_line):
                brace_count += line.count('{') - line.count('}')
                if '{' in line:
                    in_function = True
                if in_function and brace_count == 0:
                    end_line = i
                    break

            length = end_line - start_line + 1
            if length > 50:
                issues.append({
                    "line": start_line,
                    "type": "long_function",
                    "severity": "medium",
                    "length": length,
                    "function_name": match.group(1) if match.lastindex else "anonymous",
                    "suggestion": f"Function is {length} lines. Consider breaking into smaller functions."
                })

    return issues


def analyze_unclear_names(content: str) -> list[dict[str, Any]]:
    """Detect single-letter or unclear variable names."""
    issues = []
    lines = content.split('\n')

    # Match any single-letter declaration, then skip the conventional loop
    # counters explicitly. The old char class [a-hln-z] silently dropped 'm'
    # alongside i/j/k, so single-letter 'm' names were never flagged.
    single_letter_pattern = r'\b(const|let|var)\s+([a-z])\s*='
    loop_counter_names = {"i", "j", "k"}

    for i, line in enumerate(lines, 1):
        matches = re.findall(single_letter_pattern, line)
        for match in matches:
            var_name = match[1]
            if var_name in loop_counter_names:
                continue
            issues.append({
                "line": i,
                "type": "unclear_naming",
                "severity": "low",
                "variable": var_name,
                "suggestion": f"Rename '{var_name}' to a descriptive name"
            })

    return issues


def analyze_redundant_code(content: str) -> list[dict[str, Any]]:
    """Detect potentially redundant patterns."""
    issues = []
    lines = content.split('\n')

    # Detect redundant boolean comparisons
    redundant_bool_pattern = r'===?\s*(true|false)\b'

    for i, line in enumerate(lines, 1):
        if re.search(redundant_bool_pattern, line):
            issues.append({
                "line": i,
                "type": "redundant_comparison",
                "severity": "low",
                "suggestion": "Remove explicit boolean comparison (use truthy/falsy)"
            })

    return issues


def calculate_complexity_score(issues: list[dict[str, Any]]) -> float:
    """Calculate overall complexity score (0-10). Legacy metric, kept for backward compat."""
    if not issues:
        return 0.0
    total_weight = sum(SEVERITY_WEIGHTS.get(issue.get("severity", "low"), 1.0) for issue in issues)
    return round(min(total_weight / 2, 10.0), 1)


def _file_in_active_diff(path: str | Path) -> bool:
    """True if file appears in uncommitted, cached, or last-commit diff."""
    p = str(path)
    for args in (
        ["git", "diff", "--name-only", "--", p],
        ["git", "diff", "--name-only", "--cached", "--", p],
        ["git", "diff", "--name-only", "HEAD~1", "--", p],
    ):
        try:
            result = subprocess.run(
                args, capture_output=True, text=True, timeout=2, check=False
            )
            if result.stdout.strip():
                return True
        except (subprocess.SubprocessError, OSError):
            continue
    return False


def compute_benefit_score(
    issues: list[dict[str, Any]],
    loc: int,
    in_diff: bool,
    weights: dict[str, float] | None = None,
) -> tuple[float, dict[str, Any]]:
    """Compute the benefit side of the ROI ratio."""
    if not issues:
        return 0.0, {"issue_density": 0.0, "severity_impact": 0.0, "in_active_diff": in_diff}

    w = weights or DEFAULT_BENEFIT_WEIGHTS

    # Density: issues per 100 lines, capped at 10
    density = min(10.0, (len(issues) / max(loc, 1)) * 100)

    # Severity × type impact, normalized
    raw_impact = sum(
        SEVERITY_WEIGHTS.get(issue.get("severity", "low"), 1.0)
        * TYPE_WEIGHTS.get(issue.get("type", ""), 1.0)
        for issue in issues
    )
    severity_impact = min(10.0, raw_impact / 3.0)

    diff_signal = 10.0 if in_diff else 0.0

    score = (
        density * w["density"]
        + severity_impact * w["severity_impact"]
        + diff_signal * w["in_active_diff"]
    )

    explanation = {
        "issue_density": round(density, 2),
        "severity_impact": round(severity_impact, 2),
        "in_active_diff": in_diff,
    }
    return round(score, 2), explanation


def compute_roi_score(benefit: float, cost: float, cost_floor: float = 0.5) -> float:
    """ROI = B / max(C, floor). Floor prevents divide-by-zero churn on cheap files."""
    return round(benefit / max(cost, cost_floor), 2)


def load_scoring_config(repo_root: Path | None = None) -> dict[str, Any]:
    """Load ``simplification.scoring`` from ``.agent/.nav-config.json`` if present."""
    root = repo_root or Path.cwd()
    config_path = root / ".agent" / ".nav-config.json"
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text())
        return data.get("simplification", {}).get("scoring", {}) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def roi_gate_action(roi: float, thresholds: dict[str, float]) -> str:
    """Map ROI → gate action: ``skip``, ``suggest``, or ``apply``."""
    skip_below = thresholds.get("skip_below", DEFAULT_SCORING_THRESHOLDS["skip_below"])
    auto_apply_at = thresholds.get("auto_apply_at", DEFAULT_SCORING_THRESHOLDS["auto_apply_at"])
    if roi < skip_below:
        return "skip"
    if roi < auto_apply_at:
        return "suggest"
    return "apply"


def analyze_file(file_path: str, scoring_mode: str | None = None) -> dict[str, Any]:
    """Analyze a single file for simplification opportunities.

    ``scoring_mode``:
        - ``"complexity"`` (default): legacy behavior, no ROI fields
        - ``"roi"``: adds ``benefit_score`` / ``cost_score`` / ``roi_score`` /
          ``scoring_explanation`` / ``gate_action`` to the output
        - ``None``: read from ``.agent/.nav-config.json`` if present, else ``"complexity"``
    """
    path = Path(file_path)

    if not path.exists():
        return {
            "file": file_path,
            "error": "File not found",
            "issues": [],
            "complexity_score": 0,
            "recommended_actions": 0
        }

    content = path.read_text()

    issues = []
    issues.extend(analyze_nesting_depth(content))
    issues.extend(analyze_nested_ternaries(content))
    issues.extend(analyze_function_length(content))
    issues.extend(analyze_unclear_names(content))
    issues.extend(analyze_redundant_code(content))

    issues.sort(key=lambda x: x.get("line", 0))

    complexity_score = calculate_complexity_score(issues)
    recommended_actions = sum(
        1 for issue in issues if issue.get("severity") in ("high", "medium")
    )

    result: dict[str, Any] = {
        "file": file_path,
        "issues": issues,
        "complexity_score": complexity_score,
        "recommended_actions": recommended_actions,
        "total_issues": len(issues),
    }

    config = load_scoring_config()
    mode = scoring_mode or config.get("mode", "complexity")
    if mode != "roi":
        return result

    loc = max(1, len([line for line in content.split("\n") if line.strip()]))
    in_diff = _file_in_active_diff(path)

    benefit, benefit_explain = compute_benefit_score(
        issues, loc, in_diff, weights=config.get("benefit_weights")
    )
    cost, cost_explain = compute_cost_score(
        issues, loc, path, weights=config.get("cost_weights")
    )
    cost_floor = config.get("cost_floor", 0.5)
    roi = compute_roi_score(benefit, cost, cost_floor=cost_floor)

    thresholds = {**DEFAULT_SCORING_THRESHOLDS, **{
        k: v for k, v in config.items() if k in DEFAULT_SCORING_THRESHOLDS
    }}
    gate = roi_gate_action(roi, thresholds)

    result.update({
        "benefit_score": benefit,
        "cost_score": cost,
        "roi_score": roi,
        "gate_action": gate,
        "scoring_explanation": {
            "benefit": benefit_explain,
            "cost": cost_explain,
            "thresholds": thresholds,
            "cost_floor": cost_floor,
        },
    })
    return result


def format_text_output(result: dict[str, Any]) -> str:
    """Format analysis result as human-readable text."""
    output = []
    output.append(f"\n📊 Analysis: {result['file']}")
    output.append("=" * 50)

    if result.get("error"):
        output.append(f"❌ Error: {result['error']}")
        return "\n".join(output)

    output.append(f"Complexity Score: {result['complexity_score']}/10")
    output.append(f"Total Issues: {result['total_issues']}")
    output.append(f"Recommended Actions: {result['recommended_actions']}")
    if "roi_score" in result:
        output.append(
            f"Benefit: {result['benefit_score']}/10  "
            f"Cost: {result['cost_score']}/10  "
            f"ROI: {result['roi_score']}  "
            f"Gate: {result['gate_action']}"
        )
    output.append("")

    if not result['issues']:
        output.append("✅ No simplification opportunities found")
        return "\n".join(output)

    output.append("Issues Found:")
    output.append("-" * 40)

    for issue in result['issues']:
        severity_icon = {
            "high": "🔴",
            "medium": "🟡",
            "low": "🟢"
        }.get(issue.get("severity", "low"), "⚪")

        output.append(f"  {severity_icon} Line {issue.get('line', '?')}: {issue.get('type', 'unknown')}")
        output.append(f"     └─ {issue.get('suggestion', 'No suggestion')}")

    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description="Analyze code for simplification opportunities")
    parser.add_argument("--file", required=True, help="Path to file to analyze")
    parser.add_argument("--output", choices=["json", "text"], default="text", help="Output format")
    parser.add_argument("--standards", help="Path to CLAUDE.md for project standards (optional)")
    parser.add_argument(
        "--scoring",
        choices=["complexity", "roi"],
        default=None,
        help="Scoring mode override (defaults to .nav-config.json setting)",
    )

    args = parser.parse_args()

    result = analyze_file(args.file, scoring_mode=args.scoring)

    if args.output == "json":
        print(json.dumps(result, indent=2))
    else:
        print(format_text_output(result))


if __name__ == "__main__":
    main()
