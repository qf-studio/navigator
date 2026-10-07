---
name: frontend-component
description: Create React/Vue component with TypeScript, tests, and styles. Auto-invoke when user says "create component", "add component", "new component", or "build component".
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
version: 2.0.0
---

# Frontend Component Generator

Generate production-ready React/Vue components with TypeScript, tests, and styles following modern best practices.

## When to Invoke

Auto-invoke when user mentions:
- "Create a component"
- "Add a component"
- "New component"
- "Build a component"
- "Generate component for [feature]"

## What This Does

1. Generates component file with TypeScript and props interface
2. Creates test file with React Testing Library
3. Generates CSS module for styling
4. Creates barrel export (index.ts)
5. Validates naming conventions
6. Follows project patterns

## Execution Steps

### Step 0: Check Existing Patterns (Phase 0)

Before gathering requirements, query the knowledge graph for what we already know about frontend/component work in this project. This mirrors `navigator-research`'s Phase 0 and prevents re-deriving patterns we've already decided on.

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_manager.py" \
  --action query --concept frontend \
  --graph-path .agent/knowledge/graph.json 2>/dev/null | head -40
```

If memories surface (look for `PATTERN`, `PITFALL`, `DECISION` entries), read the full memory files for any directly relevant ones:
```bash
ls .agent/knowledge/memories/{patterns,pitfalls,decisions}/ 2>/dev/null
```

**What to do with what you find**:
- **Patterns**: apply them (don't re-derive — e.g. "we use CSS Modules, not styled-components")
- **Pitfalls**: avoid them (record in `pitfalls_avoided` in Step 8)
- **Decisions**: respect them (e.g. "we chose React.memo for list items")

If the graph returns nothing useful, proceed without it. Skip this step only if the knowledge graph is disabled in `.agent/.nav-config.json`.

### Step 1: Gather Component Requirements

**First, detect the framework**: read `package.json`. If `"next"` is in `dependencies`, this is a Next.js App Router project — use the Next.js variants in Step 3 and **default styling to Tailwind** (no CSS module file). See `.agent/philosophy/NEXTJS-PATTERNS.md` for the patterns these templates encode.

**Ask user for component details**:
```
Component name: [PascalCase name, e.g., UserProfile]
Component type:
  Generic React:
    - simple            (basic functional component)
    - with-hooks        (useState, useEffect, etc.)
    - container         (data fetching component)
  Next.js App Router:
    - nextjs-page       (app/<route>/page.tsx — Server Component, async)
    - nextjs-layout     (app/<route>/layout.tsx — Server Component, metadata + viewport)
    - nextjs-server     (Server Component with fetch, async)
    - nextjs-client     ('use client' component with state/effects)

Styling approach:
  - tailwind            (default for nextjs-* types)
  - css-modules         (default for generic React types)
  - styled-components

Props needed: [Optional: describe expected props]
```

**Picking the right Next.js variant**:
- User says "create a Schedule page" → `nextjs-page`
- User says "wrap the app" / "root layout" → `nextjs-layout`
- User says "needs `useState`" / "click handler" / "interactive" → `nextjs-client`
- User says "fetches data" / "list of X" → `nextjs-server`

**Validate component name**:
- Use predefined function: `functions/name_validator.py`
- Ensure PascalCase format
- No reserved words
- Descriptive and specific

### Step 1.5: Confirm Component Design (ToM Checkpoint) [EXECUTE]

**IMPORTANT**: This step MUST be executed for complex components.

**Before generating files, confirm interpretation with user**.

**Display verification**:
```
I understood you want:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Component: {NAME}
Type: {TYPE} (inferred because: {REASON})
Location: src/components/{NAME}/
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Detected patterns from your codebase:
- Styling: {CSS_APPROACH} (found {EVIDENCE})
- Testing: {TEST_LIBRARY} (found in package.json)
- Similar component: {EXISTING_COMPONENT} at {PATH}

Props I'll generate:
{PROPS_PREVIEW}

Proceed with generation? [Y/n]
```

**Skip verification if** (HIGH-STAKES ONLY mode):
- Simple presentational component (no hooks, no data fetching)
- User explicitly said "quick", "just do it", or "skip confirmation"
- Component name and type are unambiguous
- No complex props structure

**Always verify if**:
- Container component with data fetching
- Complex props interface (5+ props)
- Hooks component with side effects
- Component name similar to existing component
- User is new to codebase (no profile history)

### Step 2: Generate Props Interface

**Based on component type and requirements**:

Use predefined function: `functions/props_interface_generator.py`

```python
# Generates TypeScript interface based on component requirements
python3 functions/props_interface_generator.py \
  --name "UserProfile" \
  --props "userId:string,onUpdate:function,isActive:boolean"
```

**Output**:
```typescript
interface UserProfileProps {
  userId: string;
  onUpdate?: () => void;
  isActive?: boolean;
  children?: React.ReactNode;
  className?: string;
}
```

### Step 3: Generate Component File

**Use appropriate template based on type**:

**Simple component**:
```
Use template: templates/component-simple-template.tsx
```

**Component with hooks** / **Container component**:
```
Start from templates/component-simple-template.tsx and add the hook
declarations (useState/useEffect) or data-fetching logic inline — there is
no separate with-hooks/container template file; the simple template is the base.
```

**Next.js App Router variants** (use when `"next"` is in `package.json`):
| --type           | Template                                                | Output path example                    |
|------------------|---------------------------------------------------------|----------------------------------------|
| `nextjs-page`    | `templates/nextjs-page-template.tsx`                    | `app/schedule/page.tsx`                |
| `nextjs-layout`  | `templates/nextjs-layout-template.tsx`                  | `app/schedule/layout.tsx`              |
| `nextjs-server`  | `templates/nextjs-server-component-template.tsx`        | `app/components/speaker-list.tsx`      |
| `nextjs-client`  | `templates/nextjs-client-component-template.tsx`        | `app/components/favourite-button.tsx`  |

The Next.js templates already encode Next.js 15+/16 conventions:
- `params`/`searchParams` are `Promise`s — `await` them
- `'use client'` directive on line 1 of client components, above all imports
- Mobile-first Tailwind classes
- Metadata + viewport exports on layouts

**Skip Step 5 (Style File) for `nextjs-*` types** — Tailwind classes are baked into the templates, no CSS module needed.

**Use predefined function**: `functions/component_generator.py`

```bash
python3 functions/component_generator.py \
  --name "UserProfile" \
  --type "simple" \
  --props-interface "UserProfileProps" \
  --template "templates/component-simple-template.tsx" \
  --output "src/components/UserProfile/UserProfile.tsx"
```

**Template substitutions**:
- `${COMPONENT_NAME}` → Component name (PascalCase)
- `${PROPS_INTERFACE}` → Generated props interface
- `${STYLE_IMPORT}` → CSS module import
- `${DESCRIPTION}` → Brief component description

### Step 4: Generate Test File

**Use predefined function**: `functions/file_generator.py`

```bash
python3 functions/file_generator.py \
  --component-name "UserProfile" \
  --component-path "src/components/UserProfile/UserProfile.tsx" \
  --template "templates/test-template.tsx" \
  --output "src/components/UserProfile/UserProfile.test.tsx"
```

**Test template includes**:
- Basic rendering test
- Props validation test
- Event handler tests (if applicable)
- Accessibility tests

**Template substitutions**:
- `${COMPONENT_NAME}` → Component name
- `${IMPORT_PATH}` → Relative import path
- `${TEST_CASES}` → Generated test cases based on props

### Step 5: Generate Style File

**Use predefined function**: `functions/style_generator.py`

```bash
python3 functions/style_generator.py \
  --name "UserProfile" \
  --approach "css-modules" \
  --template "templates/style-template.module.css" \
  --output "src/components/UserProfile/UserProfile.module.css"
```

**CSS Modules template**:
```css
.container {
  /* Component wrapper styles */
}

.title {
  /* Title styles */
}

/* Add more classes as needed */
```

**Styled Components alternative**:
```typescript
// Generated if --approach "styled-components"
import styled from 'styled-components';

export const Container = styled.div`
  /* Component wrapper styles */
`;

export const Title = styled.h2`
  /* Title styles */
`;
```

### Step 6: Generate Barrel Export

**Create index.ts for clean imports**:

```bash
Write(
  file_path: "src/components/UserProfile/index.ts",
  content: "export { UserProfile } from './UserProfile';\nexport type { UserProfileProps } from './UserProfile';\n"
)
```

**Allows usage**:
```typescript
import { UserProfile } from '@/components/UserProfile';
```

### Step 7: Show Component Summary

**Display generated files and usage**:

```
✅ Component Created: UserProfile

Structure:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 src/components/UserProfile/
   ├── UserProfile.tsx         (Component)
   ├── UserProfile.test.tsx    (Tests)
   ├── UserProfile.module.css  (Styles)
   └── index.ts                (Exports)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Props Interface:
interface UserProfileProps {
  userId: string;
  onUpdate?: () => void;
  isActive?: boolean;
}

Usage:
import { UserProfile } from '@/components/UserProfile';

<UserProfile
  userId="123"
  onUpdate={() => console.log('Updated')}
  isActive={true}
/>

Next Steps:
1. Customize component implementation
2. Run tests: npm test UserProfile
3. Import and use in your feature
```

### Step 8: Emit Execution Summary (Graph Ingestion)

After Step 7, emit an `execution_summary` JSON block that captures patterns/decisions/pitfalls from this run. This block is the parity equivalent of the `research_findings` block emitted by `navigator-research`, and it gets ingested into the knowledge graph so future component work can surface what we learned.

**Output the block verbatim** (replace placeholders with actual values from this run):

```json
{
  "execution_summary": {
    "skill": "frontend-component",
    "task": "{COMPONENT_NAME} component",
    "files_created": ["{paths of files written}"],
    "files_modified": ["{paths of files edited}"],
    "tests_added": ["{test file path}"],
    "stack_detected": "{e.g. react+typescript+vitest}",
    "patterns_followed": [
      {"summary": "{convention applied — e.g. functional component with Props interface}", "concepts": ["frontend"], "confidence": 0.8}
    ],
    "decisions_made": [
      {"summary": "{non-obvious choice — e.g. React.memo because props are stable}", "concepts": ["frontend"], "confidence": 0.75, "evidence": "{path:line}"}
    ],
    "pitfalls_avoided": [],
    "assumptions_made": ["{e.g. project uses CSS Modules (detected via existing components)}"]
  }
}
```

**Ingestion** (run from project root):

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
echo '<execution_summary JSON>' | python3 "$PLUGIN_DIR/skills/nav-graph/functions/execution_to_graph.py" -
```

**Rules**:
- Only include `decisions_made` and `pitfalls_avoided` entries that are non-obvious and would help future runs.
- Skip the block entirely if no patterns/decisions/pitfalls were notable — empty blocks pollute the graph.
- Confidence ≥ 0.7 for first-hand execution; 0.75 is a reasonable default.

---

## Predefined Functions

### 1. name_validator.py

Validates component naming conventions.

**Usage**:
```bash
python3 functions/name_validator.py --name "UserProfile"
```

**Checks**:
- PascalCase format
- Not a reserved word (e.g., Component, Element, etc.)
- Descriptive (length > 2 chars)
- No special characters

**Returns**: Valid name or error message

---

### 2. props_interface_generator.py

Generates TypeScript props interface from user input.

**Usage**:
```bash
python3 functions/props_interface_generator.py \
  --name "UserProfile" \
  --props "userId:string,onUpdate:function,isActive:boolean"
```

**Supported types**:
- `string`, `number`, `boolean`
- `function` (becomes `() => void`)
- `array` (becomes `any[]`)
- `object` (becomes `Record<string, any>`)
- `react-node` (becomes `React.ReactNode`)

**Returns**: TypeScript interface string

---

### 3. component_generator.py

Generates component file from template with substitutions.

**Usage**:
```bash
python3 functions/component_generator.py \
  --name "UserProfile" \
  --type "simple" \
  --props-interface "UserProfileProps" \
  --template "templates/component-simple-template.tsx" \
  --output "src/components/UserProfile/UserProfile.tsx"
```

**Parameters**:
- `--name`: Component name (PascalCase)
- `--type`: Component type (simple/with-hooks/container)
- `--props-interface`: Props interface name
- `--template`: Template file path
- `--output`: Output file path

**Returns**: Generated component code

---

### 4. file_generator.py

Generates test file with React Testing Library.

**Usage**:
```bash
python3 functions/file_generator.py \
  --component-name "UserProfile" \
  --component-path "src/components/UserProfile/UserProfile.tsx" \
  --template "templates/test-template.tsx" \
  --output "src/components/UserProfile/UserProfile.test.tsx"
```

**Generates tests for**:
- Component rendering
- Props validation
- Event handlers
- Accessibility attributes

**Returns**: Generated test code

---

### 5. style_generator.py

Generates style file (CSS Modules or Styled Components).

**Usage**:
```bash
python3 functions/style_generator.py \
  --name "UserProfile" \
  --approach "css-modules" \
  --template "templates/style-template.module.css" \
  --output "src/components/UserProfile/UserProfile.module.css"
```

**Supported approaches**:
- `css-modules` (default)
- `styled-components`
- `tailwind` (generates className utilities)

**Returns**: Generated style code

---

## Templates

### component-simple-template.tsx

Basic functional component template.

**Placeholders**:
- `${COMPONENT_NAME}` - Component name
- `${PROPS_INTERFACE}` - Props interface definition
- `${STYLE_IMPORT}` - CSS import statement
- `${DESCRIPTION}` - Component description

> Components needing hooks or data fetching start from
> `component-simple-template.tsx` (above) and the model adds the
> `useState`/`useEffect` declarations or fetch logic inline — no dedicated
> with-hooks/container template ships.

### test-template.tsx

React Testing Library test template.

**Placeholders**:
- `${COMPONENT_NAME}` - Component name
- `${IMPORT_PATH}` - Import path
- `${TEST_CASES}` - Generated test cases

### style-template.module.css

CSS Modules template.

**Placeholders**:
- `${COMPONENT_NAME_KEBAB}` - Component name in kebab-case
- `${BASE_STYLES}` - Base container styles

---

## Examples

See `examples/` directory for reference implementations:

1. **Button.tsx** - Simple component with variants
2. **SearchBar.tsx** - Component with hooks (useState, useEffect)

Each example includes:
- Component implementation
- Test file
- Style file
- Usage documentation

---

## Best Practices

### Component Design
- Keep components **small and focused** (single responsibility)
- **Compose** complex UIs from simple components
- **Lift state up** only when necessary
- Use **descriptive names** (UserProfile, not UP)

### TypeScript
- **Define prop interfaces** explicitly
- **Avoid `any`** type (use `unknown` if needed)
- **Export types** for consumers
- **Use strict mode**

### Testing
- **Test user behavior**, not implementation
- **Query by role/text**, not test IDs
- **Test accessible attributes**
- **Mock external dependencies**

### Styling
- **CSS Modules** for scoped styles
- **BEM or descriptive class names**
- **Mobile-first** responsive design
- **Use CSS custom properties** for theming

### Accessibility
- **Semantic HTML** (button, nav, main, etc.)
- **ARIA labels** when needed
- **Keyboard navigation** support
- **Focus management** in modals/dropdowns

---

## Troubleshooting

### Component Not Rendering

**Problem**: Generated component throws errors

**Solutions**:
1. Check TypeScript compilation errors
2. Verify all imports are correct
3. Check props interface matches usage
4. Validate JSX syntax

### Tests Failing

**Problem**: Generated tests don't pass

**Solutions**:
1. Ensure React Testing Library is installed
2. Check test queries match component output
3. Verify mocks are set up correctly
4. Run tests with `--verbose` flag

### Styles Not Applying

**Problem**: CSS modules not loading

**Solutions**:
1. Check CSS module import syntax
2. Verify webpack/vite config supports CSS modules
3. Check className is applied to element
4. Inspect browser devtools for loaded styles

---

## Success Criteria

**This skill succeeds when**:
- [ ] Component file generated with valid TypeScript
- [ ] Test file created with passing tests
- [ ] Style file generated with scoped styles
- [ ] Barrel export allows clean imports
- [ ] Props interface matches requirements
- [ ] Code follows React best practices
- [ ] Accessibility attributes included

---

**Auto-invoke this skill when creating React components to ensure consistency and save time** ⚛️
