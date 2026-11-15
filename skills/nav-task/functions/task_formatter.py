#!/usr/bin/env python3
"""
Format task markdown with proper structure and metadata.
"""

import sys
import argparse
from datetime import datetime

def format_task(title, task_id, priority="Medium", complexity="Medium", status="Planning"):
    """
    Generate formatted task markdown.

    Args:
        title: Task title
        task_id: Task ID (e.g., TASK-10)
        priority: Priority level (Low, Medium, High, Critical)
        complexity: Complexity level (Low, Medium, High)
        status: Task status (Planning, In Progress, Completed)

    Returns:
        str: Formatted markdown content
    """
    today = datetime.now().strftime("%Y-%m-%d")

    template = f"""# {task_id}: {title}

**Created**: {today}
**Status**: {status}
**Priority**: {priority}
**Complexity**: {complexity}

---

## Context

[Describe the problem, feature request, or improvement needed]

**Problem**: [What needs to be solved?]

**Goal**: [What should be achieved?]

---

## Acceptance Criteria

Concrete, checkable outcomes — written so anyone (human or AI) can verify them.

- [ ] [Specific, observable outcome]
- [ ] [Another outcome]
- [ ] [Edge case handled]

---

## Route

<!-- The route in plain words: one line per step, no internal codes, no state words (the
     state comes from GitHub and the checkboxes). A trailing parenthesis holds the ticket
     (#12), "operator" for a step a person does, and "needs 1, 2". Read by nav-route and
     the /nav pane. Phases below hold the technical detail. -->

### Phase 1: [Phase Name]
- [ ] 1. [What this step does, in plain words]
- [ ] 2. [What the next step does] (needs 1)

### Side tracks
- [ ] [Work outside the main route]

### Waits for you
- [ ] [A decision or an action for the user]

---

## Implementation

### Phase 1: [Phase Name]

**Tasks**:
- [ ] Task 1
- [ ] Task 2
- [ ] Task 3

**Expected Outcome**: [What this phase delivers]

---

## Out of Scope

Explicit non-goals — what this task deliberately does not address.

- [What's deferred to a future task]
- [Adjacent change being avoided]

---

## Verify

Run these commands to validate the implementation:

```bash
# Run tests
[test command for this feature]

# Type check
[type check command]

# Build
[build command]
```

---

## Done

Observable outcomes that prove completion:

- [ ] [Specific file/API exists and exports expected interface]
- [ ] [Tests pass - specify count or coverage target]
- [ ] [Build succeeds without errors]
- [ ] [User-observable behavior works as specified]

---

## Refs

- [Source plan / design doc / parent issue]
- [Related ticket]

---

## Related Tasks

- [Link to related tasks]

---

## Notes

- [Additional context, decisions, or considerations]

---

**Task created**: {today}
**Priority**: {priority}
**Effort**: {complexity}
"""
    return template

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Format Navigator task markdown")
    parser.add_argument("--title", required=True, help="Task title")
    parser.add_argument("--id", required=True, help="Task ID (e.g., TASK-10)")
    parser.add_argument("--priority", default="Medium", choices=["Low", "Medium", "High", "Critical"])
    parser.add_argument("--complexity", default="Medium", choices=["Low", "Medium", "High"])
    parser.add_argument("--status", default="Planning", choices=["Planning", "In Progress", "Completed"])

    args = parser.parse_args()

    output = format_task(
        title=args.title,
        task_id=args.id,
        priority=args.priority,
        complexity=args.complexity,
        status=args.status
    )

    print(output)
