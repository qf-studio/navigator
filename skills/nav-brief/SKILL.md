---
name: nav-brief
description: Render a one-screen intent brief (Goal/Scope/Approach/Limits/Verify/Won't-do/Contradiction) before implementing ambiguous task-shaped prompts, triggered by the prompt_brief op (UserPromptSubmit via hooks/nav_dispatch.py). Confirms scope with max 2 open questions before touching files; detects brief drift mid-task.
version: 1.0.0
---

# Navigator Intent Brief Skill

Front-load the scope negotiation. When a prompt is task-shaped but ambiguous,
render a one-screen INTENT BRIEF and get confirmation **before** writing code —
turning 2-4 correction exchanges into 1 confirmation exchange.

## Why This Exists

Ambiguity is not complexity. A small task can be highly ambiguous ("fix the
bug" — which bug?) while a large one can be fully specified. The expensive
failure mode is implementing on guessed scope: rework burns tokens on
undo/redo, pollutes context with dead ends, and forces mid-feature compacts.

## When This Fires

**Hook contract**: render a brief ONLY when this turn's injected context
contains a `NAV-BRIEF` reminder block (emitted by the `prompt_brief` op —
`hooks/ops/prompt_brief.py`, dispatched by `nav_dispatch.py` — on
UserPromptSubmit when ambiguity score >= threshold). Never self-trigger from
your own judgment alone — the hook is the single trigger source, so behavior
stays predictable and tunable via config.

Config (`.agent/.nav-config.json`):
```json
"brief_hook": {
  "enabled": true,
  "ambiguity_threshold": 0.5,
  "memory_budget_chars": 1200
}
```

## Rendering the Brief

Use the template below. Pre-fill every field you can from the injected
`## Relevant Memories` section and current session context; mark assumptions
explicitly.

```
┌─ BRIEF: <short title> ──────────────────────────────┐
│ Goal      <outcome, one line>                       │
│ Scope     <files/dirs/endpoints — concrete>         │
│           NOT <adjacent things left untouched>      │
│ Approach  <how — cite memory if pre-filled>         │
│ Limits    <numbers, constraints — mark ASSUMED>     │
│ Verify    <how completion will be proven>           │
│ Won't do  <explicit non-goals>                      │
│ Contradict <improving X worsens Y — or "none">      │
└─────────────────────────────────────────────────────┘
Confirm / edit? (open questions: <0-2>)
```

Rules:
- **Max 2 open questions.** Ask only what you cannot infer or safely assume;
  everything else is a pre-filled default the user can veto.
- **Stop and wait** for user confirmation before any Edit/Write/Bash that
  modifies the project.
- After confirmation, capture corrections: changed defaults are candidate
  knowledge-graph memories (`"Remember we decided..."` flow via nav-graph),
  so future briefs pre-fill better.

## When a Contradiction Is Declared (TRIZ, TASK-72)

`Contradict` is the TRIZ row: the task is inventive only when improving one
thing worsens another ("faster session start vs enough context"). Most tasks
are routine — `none` is the expected common case. Never invent a tension to
fill the row.

When the row is not `none`, query prior resolutions BEFORE filling
`Approach`:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_manager.py" \
  --action contradictions --filter "<2-3 key terms>"
```

Cite matching `mem-NNN` ids in `Approach` ("resolved by separation in time
before: mem-063"). If nothing matches, say so in one line. On a substantial
task (Task Mode complexity ≥ 0.5 or more than one subsystem), hand off to
**nav-triz** before filling `Approach`: it produces three candidates from
different separation modes and recommends one. After the task,
if the resolution was non-obvious, capture it as a decision with
`--contradiction / --separation / --principle` (see nav-graph Step 3B) so the
next brief can find it. Drift detection does not cover this row.

## Passthrough Rules (do NOT render a brief)

- No `NAV-BRIEF` reminder in this turn's context.
- The prompt is plainly an **answer to a pending brief's open questions**
  (model-side judgment — the hook is stateless in v1 and may re-fire on
  answers that contain task verbs; known limitation).
- User signals urgency/override: "just do it", "quick fix", "skip the brief".
  Respect it silently.

## Brief Drift Detection

Mid-implementation, if the work is about to exceed the confirmed brief's
Scope or Limits (touching files outside scope, changing an untouched-by-
agreement area), STOP and surface:

```
⚠ BRIEF DRIFT: <what exceeds the brief, one line>
Options: extend brief / skip this change
```

One question, then continue per the answer.

## Interaction with workflow_enforcer / Task Mode

Both UserPromptSubmit hooks may fire on the same prompt. Show both blocks —
they are complementary: WORKFLOW CHECK decides *how* to execute (mode),
the brief decides *what* is in scope. In Task Mode, the confirmed brief
replaces ad-hoc scope derivation in the PLAN phase.

## Examples

**Brief rendered** — `"add rate limiting to the API"` (score 0.7): brief with
Scope pre-filled to public routes (graph memory), Limits marked ASSUMED,
1 open question about limit numbers. User answers; implementation starts.

**Passthrough** — `"fix the typo in README.md"` (score 0.1): file reference
gives full scope; no brief, direct execution.

**Drift** — brief confirmed scope `/api/public/*`; implementation later needs
a shared middleware file used by internal routes → BRIEF DRIFT raised, user
extends the brief.

## Future Work (explicitly deferred from v1)

- Statefulness: persist pending-brief state across turns (removes the
  answer-re-fire limitation).
- `strict_block`: hard-gate implementation until a brief is confirmed.
- Measurement: briefs-shown/passthrough counters + corrections-per-task
  metrics (pairs with nav-stats; deferred until there is a consumer).
- Prompt rewriting.
