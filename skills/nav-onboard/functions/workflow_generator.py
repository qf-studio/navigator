#!/usr/bin/env python3
"""
Personalized workflow generator for Navigator onboarding.

Generates MY-WORKFLOW.md in the per-person onboarding directory
(onboarding_paths.onboarding_dir, outside the repo) based on project analysis
and skill recommendations.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from onboarding_paths import onboarding_dir as _onboarding_dir  # noqa: E402


def generate_workflow(
    project_dir: str,
    project_analysis: Dict,
    skill_recommendations: Dict
) -> str:
    """
    Generate personalized workflow guide.

    Args:
        project_dir: Project directory path
        project_analysis: Output from project_analyzer.py
        skill_recommendations: Output from skill_recommender.py

    Returns:
        Path to generated workflow file
    """
    onboarding_dir = _onboarding_dir(project_dir)  # per person, outside the repo (GH-31)
    onboarding_dir.mkdir(parents=True, exist_ok=True)

    workflow_file = onboarding_dir / "MY-WORKFLOW.md"

    # Extract info
    project_name = project_analysis.get("project_name", "Unknown")
    project_type = project_analysis.get("project_type", "unknown")
    tech_stack = _format_tech_stack(project_analysis)

    essential = skill_recommendations.get("skill_details", {}).get("essential", [])
    recommended = skill_recommendations.get("skill_details", {}).get("recommended", [])
    optional = skill_recommendations.get("skill_details", {}).get("optional", [])
    workflow_order = skill_recommendations.get("workflow_order", [])

    # Generate sections
    workflow_diagram = _generate_workflow_diagram(project_type, workflow_order)
    daily_workflow = _generate_daily_workflow(project_type, recommended)
    skills_table = _generate_skills_table(essential, recommended, optional)
    quick_reference = _generate_quick_reference(essential, recommended)

    content = f"""# My Navigator Workflow

**Generated**: {datetime.now().strftime("%Y-%m-%d %H:%M")}
**Project**: {project_name}
**Type**: {project_type.title()}
**Stack**: {tech_stack}

---

## Workflow Diagram

{workflow_diagram}

---

## Daily Workflow

{daily_workflow}

---

## Skills Reference

{skills_table}

---

## Quick Reference

{quick_reference}

---

## Tips for {project_type.title()} Projects

{_generate_tips(project_type, project_analysis)}

---

## Next Steps

1. **Start every session** with: "Start my Navigator session"
2. **Create checkpoints** before breaks: "Create checkpoint [name]"
3. **Document features** when complete: "Archive TASK-XX"
4. **Capture solutions** after debugging: "Create SOP for [issue]"
5. **Clear context** when switching tasks: "Clear context and preserve"

---

*This workflow was personalized for your {project_type} project.*
*Update as your needs evolve.*

**Navigator Version**: 4.6.0
"""

    workflow_file.write_text(content)
    return str(workflow_file)


def _format_tech_stack(analysis: Dict) -> str:
    """Format tech stack from analysis."""
    parts = []

    if analysis.get("frontend_framework"):
        parts.append(analysis["frontend_framework"])
    if analysis.get("backend_framework"):
        parts.append(analysis["backend_framework"])
    if analysis.get("orm"):
        parts.append(analysis["orm"])
    elif analysis.get("database"):
        parts.append(analysis["database"])
    if analysis.get("testing_framework"):
        parts.append(analysis["testing_framework"])

    return ", ".join(parts) if parts else "Not detected"


def _generate_workflow_diagram(project_type: str, workflow_order: List[str]) -> str:
    """Generate ASCII workflow diagram."""
    if project_type == "frontend":
        return """```
SESSION START
     │
     ▼
┌─────────────┐
│  nav-start  │  "Start my Navigator session"
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│  Load task doc      │  (if continuing work)
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│ frontend-component  │  "Create component [name]"
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│   frontend-test     │  "Test this component"
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│     nav-task        │  "Archive TASK-XX"
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│     nav-sop         │  (if solved issue)
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│    nav-marker       │  "Create checkpoint [name]"
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│   nav-compact       │  (when switching tasks)
└─────────────────────┘
```"""

    elif project_type == "backend":
        return """```
SESSION START
     │
     ▼
┌─────────────┐
│  nav-start  │  "Start my Navigator session"
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│  Load task doc      │  (if continuing work)
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│ backend-endpoint    │  "Add endpoint [path]"
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│   backend-test      │  "Write test for [function]"
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│ database-migration  │  (if schema changes)
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│     nav-task        │  "Archive TASK-XX"
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│    nav-marker       │  "Create checkpoint [name]"
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│   nav-compact       │  (when switching tasks)
└─────────────────────┘
```"""

    else:  # fullstack or unknown
        return """```
SESSION START
     │
     ▼
┌─────────────┐
│  nav-start  │  "Start my Navigator session"
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│  Load task doc      │  (if continuing work)
└──────┬──────────────┘
       │
       ├────────────────────────┐
       ▼                        ▼
┌──────────────────┐   ┌──────────────────┐
│frontend-component│   │ backend-endpoint │
└───────┬──────────┘   └────────┬─────────┘
        │                       │
        ▼                       ▼
┌──────────────────┐   ┌──────────────────┐
│  frontend-test   │   │   backend-test   │
└───────┬──────────┘   └────────┬─────────┘
        │                       │
        └───────────┬───────────┘
                    │
                    ▼
          ┌─────────────────────┐
          │     nav-task        │  "Archive TASK-XX"
          └──────┬──────────────┘
                 │
                 ▼
          ┌─────────────────────┐
          │    nav-marker       │  "Create checkpoint"
          └──────┬──────────────┘
                 │
                 ▼
          ┌─────────────────────┐
          │   nav-compact       │  (when switching)
          └─────────────────────┘
```"""


def _generate_daily_workflow(project_type: str, recommended: List[Dict]) -> str:
    """Generate daily workflow checklist."""
    dev_skills = [s["name"] for s in recommended[:2]] if recommended else ["development skills"]
    dev_skills_str = ", ".join(dev_skills)

    return f"""### Morning Routine

1. **Start session**: "Start my Navigator session"
2. **Check tasks**: Review `.agent/tasks/` index for current work
3. **Load context**: Read relevant task documentation

### During Development

4. **Use dev skills**: {dev_skills_str}
5. **Create checkpoints**: Before breaks or risky changes
6. **Document decisions**: Update task doc with technical choices

### After Completing Work

7. **Archive task**: "Archive TASK-XX documentation"
8. **Capture solutions**: "Create SOP for [solved issue]"
9. **Final checkpoint**: "Create checkpoint [feature-name]-complete"

### End of Session

10. **Clear context**: "Clear context and preserve markers" (if switching tasks)
11. **Or keep context**: If continuing same work tomorrow"""


def _generate_skills_table(
    essential: List[Dict],
    recommended: List[Dict],
    optional: List[Dict]
) -> str:
    """Generate skills reference tables."""
    sections = []

    # Essential skills
    sections.append("### Essential Skills (Use Daily)\n")
    sections.append("| Skill | Description | Trigger |")
    sections.append("|-------|-------------|---------|")
    for skill in essential:
        trigger = skill.get("triggers", [""])[0]
        sections.append(f"| {skill['name']} | {skill['description']} | \"{trigger}\" |")

    # Recommended skills
    if recommended:
        sections.append("\n### Development Skills (Use When Building)\n")
        sections.append("| Skill | Description | Trigger |")
        sections.append("|-------|-------------|---------|")
        for skill in recommended:
            trigger = skill.get("triggers", [""])[0]
            sections.append(f"| {skill['name']} | {skill['description']} | \"{trigger}\" |")

    # Optional skills
    if optional:
        sections.append("\n### Optional Skills (Advanced)\n")
        sections.append("| Skill | Description | Trigger |")
        sections.append("|-------|-------------|---------|")
        for skill in optional:
            trigger = skill.get("triggers", [""])[0]
            sections.append(f"| {skill['name']} | {skill['description']} | \"{trigger}\" |")

    return "\n".join(sections)


def _generate_quick_reference(essential: List[Dict], recommended: List[Dict]) -> str:
    """Generate quick reference table."""
    lines = [
        "| Action | Say This |",
        "|--------|----------|",
        "| Start session | \"Start my Navigator session\" |",
        "| Save progress | \"Create checkpoint [name]\" |",
        "| Document feature | \"Create task doc for [feature]\" |",
        "| Archive feature | \"Archive TASK-XX documentation\" |",
        "| Capture solution | \"Create SOP for [issue]\" |",
        "| Clear context | \"Clear context and preserve markers\" |",
    ]

    # Add first recommended skill
    if recommended:
        skill = recommended[0]
        trigger = skill.get("triggers", [""])[0]
        lines.append(f"| {skill['description'][:30]} | \"{trigger}\" |")

    return "\n".join(lines)


def _generate_tips(project_type: str, analysis: Dict) -> str:
    """Generate project-type specific tips."""
    tips = []

    if project_type == "frontend":
        tips.extend([
            "- Use `frontend-component` to maintain consistent component structure",
            "- Create markers before CSS refactoring (easy to mess up)",
            "- SOPs are great for browser compatibility fixes",
        ])
        if analysis.get("has_storybook"):
            tips.append("- Consider `visual-regression` for UI consistency")
        if analysis.get("has_figma_mcp"):
            tips.append("- Use `product-design` for design handoff automation")

    elif project_type == "backend":
        tips.extend([
            "- Use `backend-endpoint` for consistent API structure",
            "- Create SOPs for auth flows and edge cases",
            "- Document database decisions in task docs",
        ])
        if analysis.get("database"):
            tips.append(f"- Use `database-migration` for {analysis['database']} schema changes")

    elif project_type == "fullstack":
        tips.extend([
            "- Balance frontend and backend work in single sessions",
            "- Create task docs that span both layers",
            "- SOPs for API contract changes are invaluable",
            "- Compact between frontend and backend focus switches",
        ])

    else:
        tips.extend([
            "- Use task docs to capture library/package decisions",
            "- SOPs for build and publish workflows",
            "- Markers before major refactors",
        ])

    return "\n".join(tips)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: workflow_generator.py <project_dir> <analysis_json> <recommendations_json>")
        sys.exit(1)

    project_dir = sys.argv[1]

    # Load analysis and recommendations
    with open(sys.argv[2]) as f:
        analysis = json.load(f)
    with open(sys.argv[3]) as f:
        recommendations = json.load(f)

    result = generate_workflow(project_dir, analysis, recommendations)
    print(result)
