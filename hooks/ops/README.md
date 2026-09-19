# hooks/ops — Navigator v7 op modules

One file per op. The dispatcher (`hooks/nav_dispatch.py` → `nav_hook_lib.runtime.dispatch`)
routes each hook event through the ordered `OpSpec` list in `nav_hook_lib/registry.py` and
merges every op's result into exactly ONE JSON output document per event.

This README is the contract for TASK-61 (ports of the nine v6 hooks) and TASK-62 (new
capabilities on spike-proven channels) op authors.

## Op module protocol

```python
# hooks/ops/<name>.py
def run(ctx) -> dict | None:
    ...
```

`<name>` must match `OpSpec.name` in the registry. `run(ctx)` is the only required export.
Modules are imported lazily — only when their event fires and their matcher hits — so keep
imports cheap (UserPromptSubmit dispatch must stay ≤200ms p95).

### ctx (types.SimpleNamespace)

Ops may cache per-dispatch derived values on ``ctx`` under a leading-underscore
attribute; ``nav_hook_lib.judge.for_ctx`` stores ``ctx._judgment`` so prompt_gate and
prompt_brief share one judge call (TASK-79).

| Field | Meaning |
|---|---|
| `ctx.event` | Hook event name, e.g. `"UserPromptSubmit"` |
| `ctx.payload` | Parsed stdin payload dict from the harness |
| `ctx.config` | Layered config from `nav_hook_lib.config.load()` (loaded once per dispatch) |
| `ctx.state` | Runtime state dict (`nav_hook_lib.state`) — mutate IN PLACE; runtime saves once |
| `ctx.pilot_executor` | `config.is_pilot_executor()` evaluated ONCE at dispatch entry |
| `ctx.now` | Timestamp injected by the runtime (use it, not `time.time()`, for testability) |

Never read the Pilot-executor env var yourself — `ctx.pilot_executor` is the single policy
point (a guard test sweeps `hooks/**` for strays). Gate every interactive/blocking behavior
on it.

### Result keys (all optional; `None` or `{}` = silent op)

| Key | Type | Merge rule in runtime |
|---|---|---|
| `additional_context` | str | Concatenated in registry order, then `budget.clamp(text, event)` |
| `decision` | `'block'` | First `'block'` wins; its `reason` is used |
| `reason` | str | Reason for `decision: 'block'` |
| `permission_decision` | `'deny'`\|`'ask'` | For PreToolUse gates; deny beats allow |
| `permission_reason` | str | Reason for the permission decision |
| `continue_` | bool | OR'd; only `continue: false` is ever emitted (omit unless explicitly set) |
| `exit_code` | int | `max()` across ops — a deliberate gate exit-2 survives the merge |
| `stderr` | str | Joined; runtime emits it — see sentinel discipline below |
| `system_message` | str | Surfaced as `systemMessage` |
| `ack` | bool | v6 parity: emit the bare `{}` doc when the merge is otherwise empty |

## Phase semantics (`OpSpec.phase`, executed in this order)

1. **`gates`** — may block/deny (workflow enforcement, read guard). A gate result carrying
   `decision`/`permission_decision: 'deny'`/nonzero `exit_code` SHORT-CIRCUITS all rightward
   phases. Gates are EXEMPT from the soft deadline — they always run, even past it.
2. **`responders`** — deterministic answers that cut the request (Tier-1, TASK-62).
3. **`injectors`** — add `additional_context` for the model (session start, intent brief).
4. **`recorders`** — write state/graph/profile side effects; emit nothing user-visible.

Soft deadline: `manifest timeout − 500ms`, checked BEFORE each op. Past it, responders,
injectors and recorders are dropped for the rest of the dispatch; gates still run.

## Per-op isolation and failure posture

- Each op runs in its own try/except. A crash appends `{op, error, ts}` to
  `state['meta']['op_errors']`, emits ONE sentinel-wrapped stderr line (tag
  `nav-dispatch-error`), and records `.agent/.nav-dispatch-health.json`; sibling ops still
  run. The dispatcher itself never exits non-zero on its own behalf (fail-open).
- NEVER write to stderr/stdout directly from an op (mem-034: unwrapped stderr echoes recycle
  as trigger phrases). Return `stderr` in the result dict; `nav_hook_lib.sentinels` owns the
  only emitter. A lint test greps op files for raw writes.
- NEVER echo payload/prompt text into errors or stderr (mem-034). Scan only text that has
  passed `sentinels.strip_all()`.

## Config gating and matchers

- `OpSpec.config_key` names the v6 toggle block in `.agent/.nav-config.json`; the runtime
  checks `config.get(cfg, config_key + '.enabled', True)` — `false` skips the op silently.
  Missing blocks default safe via `config.DEFAULTS` (pristine v6.18.1 configs must work).
- `OpSpec.matcher` is a regex tested against `payload['tool_name']` for
  PreToolUse/PostToolUse (`'Read'`, `'Edit|Write|MultiEdit|NotebookEdit'`); `None` = always.
  Manifest matchers stay coarse; do fine filtering inside the op.

## Channel constraints (TASK-57 spike verdicts — cite memories, not docs)

- Tool-adjacent `additional_context` (PostToolUse mem-050, PreToolUse mem-054) must be
  DECLARATIVE (facts, data, memories). Imperative instructions are flagged by the model as
  prompt injection and refused.
- Stop `continue: true` is a NO-OP (mem-051); forced continuation uses `decision: 'block'`
  + reason, fused single-shot. Ships OFF by default and always OFF under the Pilot executor.
- UserPromptSubmit block-as-answer uses `decision: 'block'` JSON, never exit-2 (mem-053).
- SubagentStart injection is viable at the 2k-char budget (mem-052; `budget.BUDGETS`).

## Testing

Colocate `test_<name>.py` next to the op (stdlib `unittest`). Pin the import path like the
existing suites so discovery works both from `hooks/` and from inside this directory:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))          # this dir
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # hooks/ (nav_hook_lib)
```

Build ops on `nav_hook_lib` (`hio`, `config`, `state`, `sentinels`, `signals`, `scoring`,
`budget`, `memory`) — never reimplement it.
