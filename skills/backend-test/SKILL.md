---
name: backend-test
description: Generate backend tests (unit, integration, mocks) for existing code. Auto-invoke when user says "write test for", "add test", "test this", or "create test".
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
version: 2.0.0
---

# Backend Test Generator

Generate backend tests for **existing code** — typically code that was written without tests, or where additional coverage is needed beyond what a code-writing skill (`backend-endpoint`) already produced.

> **When to use this vs. `backend-endpoint`**: `backend-endpoint` generates tests as part of creating a new endpoint. Use `backend-test` when the code already exists and you need to add or expand its tests.

## When to Invoke

Auto-invoke when user says:
- "Write test for [file/function]"
- "Add test" / "Add tests"
- "Test this"
- "Create test for [thing]"
- "Test the [api/service/function]"

## Execution Steps

### Step 0: Check Existing Patterns (Phase 0)

Query the knowledge graph for what we know about testing in this project:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_manager.py" \
  --action query --concept testing \
  --graph-path .agent/knowledge/graph.json 2>/dev/null | head -40
```

Surface patterns (preferred frameworks, mocking conventions) and pitfalls (flaky-test gotchas). If the graph returns nothing, proceed without it.

### Step 1: Locate Code Under Test

If the user named a specific file, use it. Otherwise, ask:
```
What should I test?
  - File path (e.g., src/services/userService.ts)
  - Function name (e.g., authenticateUser)
  - API endpoint (e.g., POST /api/login)
```

Read the target file in full so the generated tests cover its actual behavior, not assumed behavior.

### Step 2: Detect Test Framework

```bash
# Jest
grep -q '"jest"' package.json 2>/dev/null && echo "Jest detected"
# Vitest
grep -q '"vitest"' package.json 2>/dev/null && echo "Vitest detected"
# Mocha
grep -q '"mocha"' package.json 2>/dev/null && echo "Mocha detected"
# Node test runner (built-in)
[ -f "package.json" ] && grep -q '"test":\s*"node --test' package.json && echo "node:test detected"
```

Detect existing test patterns by reading a peer test file under `__tests__/`, `tests/`, or `*.test.ts` alongside the target.

### Step 3: Generate Test File

**File location**: place tests where existing tests live (mirror the project's convention — colocated `*.test.ts` next to source, or under a `tests/` directory).

**Structure (Jest/Vitest)**:
```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest';  // or 'jest'
import { {FUNCTION_NAME} } from '{TARGET_PATH}';

describe('{FUNCTION_NAME}', () => {
  describe('happy path', () => {
    it('returns expected result for valid input', () => {
      const result = {FUNCTION_NAME}({VALID_INPUT});
      expect(result).toEqual({EXPECTED});
    });
  });

  describe('error cases', () => {
    it('throws on invalid input', () => {
      expect(() => {FUNCTION_NAME}({INVALID_INPUT})).toThrow();
    });
  });

  describe('edge cases', () => {
    it('handles empty input', () => { /* ... */ });
    it('handles boundary values', () => { /* ... */ });
  });
});
```

**For API/integration tests** (supertest pattern):
```typescript
import request from 'supertest';
import { app } from '{APP_PATH}';

describe('{METHOD} {PATH}', () => {
  it('returns 200 for valid request', async () => {
    const response = await request(app).{method}('{PATH}').send({BODY});
    expect(response.status).toBe(200);
    expect(response.body).toMatchObject({EXPECTED_SHAPE});
  });

  it('returns 4xx for invalid request', async () => {
    const response = await request(app).{method}('{PATH}').send({BAD_BODY});
    expect(response.status).toBe(400);
  });
});
```

### Step 4: Verify

Run the generated tests:
```bash
{TEST_COMMAND} {TEST_FILE_PATH}
```

If any fail because tests assume incorrect behavior, **fix the tests, not the source** — unless the source has an actual bug. If the source is buggy, surface that to the user; don't silently change it.

### Step 5: Emit Execution Summary (Graph Ingestion)

```json
{
  "execution_summary": {
    "skill": "backend-test",
    "task": "tests for {TARGET}",
    "files_created": ["{test file path}"],
    "files_modified": [],
    "tests_added": ["{test file path}"],
    "stack_detected": "{e.g. vitest+supertest}",
    "patterns_followed": [
      {"summary": "{e.g. supertest pattern for HTTP integration tests}", "concepts": ["testing", "api"], "confidence": 0.8}
    ],
    "decisions_made": [
      {"summary": "{e.g. mocked the DB client because tests must run offline}", "concepts": ["testing"], "confidence": 0.75}
    ],
    "pitfalls_avoided": [],
    "assumptions_made": ["{e.g. project uses Vitest globals — no explicit import needed}"]
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

- [ ] Test file located where the project keeps tests (mirrors convention)
- [ ] Happy path, error cases, and at least one edge case covered
- [ ] Mocks isolate the unit under test
- [ ] All generated tests pass on first run (or surface real bugs in the source)
- [ ] Execution summary emitted

## When NOT to Use This Skill

- You're creating a new endpoint from scratch — use `backend-endpoint` (it generates tests as part of its workflow)
- You want to test a UI component — use `frontend-test`
