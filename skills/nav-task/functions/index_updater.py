#!/usr/bin/env python3
"""
Update DEVELOPMENT-README.md task index with new task entry.
"""

import os
import sys
import re
from datetime import datetime

def update_task_index(task_file, status="Planning", description=""):
    """
    Add task entry to DEVELOPMENT-README.md index.

    Args:
        task_file: Task filename (e.g., TASK-10-feature-name.md or GH-57-feature.md)
        status: Task status (Planning, In Progress, Completed)
        description: Short task description

    Returns:
        bool: True if updated successfully
    """
    readme_path = ".agent/DEVELOPMENT-README.md"

    if not os.path.exists(readme_path):
        print(f"Error: {readme_path} not found", file=sys.stderr)
        return False

    # Extract task ID and title from filename
    match = re.match(r'([A-Z][A-Z0-9]*-\d+)-(.*?)\.md', task_file)  # TASK-12-x, GH-57-x
    if not match:
        print(f"Error: Invalid task filename format: {task_file}", file=sys.stderr)
        return False

    task_id = match.group(1)
    task_slug = match.group(2).replace('-', ' ').title()

    # Read current README
    with open(readme_path, 'r') as f:
        content = f.read()

    # Find the task index section
    task_section_pattern = r'(### Implementation Plans \(`tasks/`\).*?)(###|\Z)'
    task_section_match = re.search(task_section_pattern, content, re.DOTALL)

    if not task_section_match:
        print("Error: Could not find task index section", file=sys.stderr)
        return False

    # Create new task entry
    status_emoji = {
        "Planning": "📋",
        "In Progress": "🚧",
        "Completed": "✅"
    }.get(status, "📋")

    today = datetime.now().strftime("%Y-%m-%d")

    new_entry = f"""
#### [{task_id}: {task_slug}](./tasks/{task_file})
**Status**: {status_emoji} {status}
**Created**: {today}

**What**: {description or "Description pending"}

---
"""

    # Insert before the next section marker
    task_section = task_section_match.group(1)
    rest_of_doc = content[task_section_match.end(1):]

    # Add new entry at the end of task section
    updated_section = task_section.rstrip() + "\n" + new_entry
    updated_content = content[:task_section_match.start(1)] + updated_section + rest_of_doc

    # Write back
    with open(readme_path, 'w') as f:
        f.write(updated_content)

    print(f"✅ Added {task_id} to DEVELOPMENT-README.md index")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: index_updater.py <task-file> [status] [description]", file=sys.stderr)
        sys.exit(1)

    task_file = sys.argv[1]
    status = sys.argv[2] if len(sys.argv) > 2 else "Planning"
    description = sys.argv[3] if len(sys.argv) > 3 else ""

    success = update_task_index(task_file, status, description)
    sys.exit(0 if success else 1)
