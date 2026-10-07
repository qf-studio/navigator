---
name: frontend-test
description: Generate frontend component tests (React Testing Library, Vue Test Utils, snapshot) for existing components. Auto-invoke when user says "test this component", "write component test", or "add component test".
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
version: 2.0.0
---

# Frontend Component Test Generator

Generate component tests for **existing components** — typically components written without tests, or where additional coverage is needed beyond what `frontend-component` already produced.

> **When to use this vs. `frontend-component`**: `frontend-component` generates tests as part of creating a new component. Use `frontend-test` when the component already exists and you need to add or expand its tests.

## When to Invoke

Auto-invoke when user says:
- "Test this component"
- "Write component test"
- "Add component test"
- "Test component [name]"
- "Component tests for [name]"

## Execution Steps

### Step 0: Check Existing Patterns (Phase 0)

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_manager.py" \
  --action query --concept frontend \
  --graph-path .agent/knowledge/graph.json 2>/dev/null | head -40

python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_manager.py" \
  --action query --concept testing \
  --graph-path .agent/knowledge/graph.json 2>/dev/null | head -40
```

Look for patterns about test utilities used (RTL vs Enzyme), snapshot policy, accessibility-test conventions.

### Step 1: Locate Component Under Test

Ask if not specified:
```
Which component should I test?
  - File path (e.g., src/components/UserProfile.tsx)
  - Component name (e.g., UserProfile)
```

Read the component in full so generated tests cover actual behavior (props handled, events emitted, conditional rendering, etc.).

### Step 2: Detect Test Framework + Library

```bash
# React Testing Library
grep -q '"@testing-library/react"' package.json 2>/dev/null && echo "RTL detected"
# Vue Test Utils
grep -q '"@vue/test-utils"' package.json 2>/dev/null && echo "Vue Test Utils detected"
# Test runner
grep -q '"vitest"' package.json 2>/dev/null && echo "Vitest"
grep -q '"jest"' package.json 2>/dev/null && echo "Jest"
```

Check for `setupTests.ts` / `vitest.setup.ts` to understand global utilities and matchers.

### Step 3: Generate Test File

**File location**: colocate with the component (`UserProfile.test.tsx` next to `UserProfile.tsx`) unless the project convention is otherwise.

**Structure (RTL + Vitest/Jest)**:
```tsx
import { describe, it, expect, vi } from 'vitest';  // or '@jest/globals'
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { {COMPONENT_NAME} } from './{COMPONENT_NAME}';

describe('{COMPONENT_NAME}', () => {
  describe('rendering', () => {
    it('renders with required props', () => {
      render(<{COMPONENT_NAME} {...{REQUIRED_PROPS}} />);
      expect(screen.getByRole('{ROLE}')).toBeInTheDocument();
    });

    it('renders conditional content when prop is set', () => {
      render(<{COMPONENT_NAME} {...{REQUIRED_PROPS}} {OPTIONAL_PROP} />);
      expect(screen.getByText('{EXPECTED_TEXT}')).toBeInTheDocument();
    });
  });

  describe('interactions', () => {
    it('calls onClick handler when clicked', async () => {
      const user = userEvent.setup();
      const onClick = vi.fn();
      render(<{COMPONENT_NAME} {...{REQUIRED_PROPS}} onClick={onClick} />);
      await user.click(screen.getByRole('button'));
      expect(onClick).toHaveBeenCalledOnce();
    });
  });

  describe('accessibility', () => {
    it('has accessible name', () => {
      render(<{COMPONENT_NAME} {...{REQUIRED_PROPS}} />);
      expect(screen.getByRole('{ROLE}')).toHaveAccessibleName();
    });
  });
});
```

**Snapshot tests**: only generate if the project's existing tests use them (check peer test files first). They're easy to over-rely on; prefer assertion-based tests for behavior, snapshots only for stable visual structure.

### Step 4: Verify

```bash
{TEST_COMMAND} {COMPONENT_NAME}
```

If tests fail because they assume incorrect behavior, fix the tests. Only fix the component if it's actually buggy — surface that to the user.

### Step 5: Emit Execution Summary (Graph Ingestion)

```json
{
  "execution_summary": {
    "skill": "frontend-test",
    "task": "tests for {COMPONENT_NAME}",
    "files_created": ["{test file path}"],
    "files_modified": [],
    "tests_added": ["{test file path}"],
    "stack_detected": "{e.g. react+rtl+vitest}",
    "patterns_followed": [
      {"summary": "{e.g. queries via getByRole, not getByTestId}", "concepts": ["frontend", "testing"], "confidence": 0.85}
    ],
    "decisions_made": [
      {"summary": "{e.g. asserted accessible name instead of snapshot to avoid brittleness}", "concepts": ["testing"], "confidence": 0.8}
    ],
    "pitfalls_avoided": [
      {"summary": "{e.g. used userEvent.setup() not fireEvent — RTL recommendation}", "concepts": ["testing"], "confidence": 0.85}
    ],
    "assumptions_made": ["{e.g. project uses Vitest globals from setup file}"]
  }
}
```

Ingest:
```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
echo '<execution_summary JSON>' | python3 "$PLUGIN_DIR/skills/nav-graph/functions/execution_to_graph.py" -
```

## Success Criteria

- [ ] Test file colocated with component (or per project convention)
- [ ] Rendering, interactions, and at least one accessibility check covered
- [ ] Queries use `getByRole` / `getByLabelText` over `getByTestId` where possible
- [ ] All generated tests pass on first run
- [ ] Execution summary emitted

## When NOT to Use This Skill

- You're creating a new component from scratch — use `frontend-component` (it generates tests as part of its workflow)
- You want to test a backend endpoint or service — use `backend-test`
- You want visual regression testing — use `visual-regression`
