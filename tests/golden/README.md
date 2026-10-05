# tests/golden — TASK-61 golden corpus + parity harness (Phase 0)

Recorded v6 hook behavior is the gate for the v7 op ports: for every corpus case,
`python3 hooks/nav_dispatch.py <event>` stdout + exit code must BYTE-MATCH the recorded
v6 golden. The only sanctioned difference is internal state-file paths (v6 per-hook files
→ `.agent/.nav-runtime-state.json` schema 2, legacy archived). If v6 emitted nothing, the
op emits nothing.

## Layout

| Path | What |
|---|---|
| `goldens/<surface>.json` | One case per surface: `{payload, stdout, exit_code, env_notes}` |
| `fixtures/agent/` | Pristine v6.18.1 scratch `.agent/` (config, minimal README, task doc) |
| `fixtures/notes.md` | Pre-edit scratch file the capture session appended to |
| `fixtures/transcript.jsonl` | Real transcript of the capture session (see deviations) |
| `corpus.py` | Shared plumbing: surface table, fresh-project builder, env discipline, runners |
| `record_goldens.py` | Recorder (initial `--capture-log` mode + frozen-payload re-record mode) |
| `test_parity.py` | The parity suite (`make test` runs it via `TEST_DIRS`) |

## The nine surfaces

| Golden | Event | v6 script | Recorded branch |
|---|---|---|---|
| `session_start` | SessionStart | `nav_session_start.py` | injection doc (config/tasks/navigator) |
| `prompt_gate` | UserPromptSubmit | `workflow_enforcer.py` | silent (no loop/task trigger) |
| `prompt_brief` | UserPromptSubmit | `nav_brief.py` | silent (not ambiguous/task-shaped) |
| `read_guard` | PreToolUse(Read) | `nav_read_guard.py` | silent (1st counted read; warn=3) |
| `graph_sync` | PostToolUse(Edit) | `nav_task_graph_sync.py` | `{}` doc (non-task file edited) |
| `profile_sync` | PostToolUse(Edit) | `nav_profile_sync.py` | `{}` doc (non-profile file edited) |
| `stop_state` | Stop | `nav_workflow_state.py` | `{}` doc (state write is internal) |
| `pre_compact` | PreCompact | `nav_pre_compact.py` | `{}` doc (marker write is internal) |
| `post_compact` | PostCompact | `nav_post_compact.py` | `{}` doc (no `.active` → no-op branch) |

Goldens lock the COMMON path: fresh project, no pre-existing state files (the default
no-state branch). Interesting branches (read_guard warn/block, prompt_gate hard block,
post_compact append) are covered by op-colocated tests in later phases, not here.

## How the payloads were captured (2026-07-10, CC 2.1.205)

1. A temporary catch-all logging plugin (`golden-logger`, all seven events, appends raw
   stdin JSON to a log, cwd-gated under `/tmp/nav-v7-golden`) was installed from a scratch
   marketplace at `/tmp/nav-v7-golden/marketplace`.
2. ONE live headless session ran in a scratch project carrying exactly the `fixtures/`
   content, with the prompt:
   > Read the file .agent/tasks/TASK-01-sample.md, then use the Edit tool to append the
   > line 'golden capture complete' to notes.md. Reply DONE.
   This fired SessionStart, UserPromptSubmit, PreToolUse(Read on the `.agent/` task doc),
   PostToolUse(Edit on notes.md), and Stop; their payloads are stored VERBATIM.
3. The logging plugin was uninstalled and its marketplace removed afterwards.

The prompt was pre-checked against `workflow_detector.detect_workflow` and
`ambiguity_scorer.score_ambiguity` to keep BOTH UserPromptSubmit surfaces silent: the two
goldens share one payload, and the dispatcher emits ONE document per event, so same-event
same-payload goldens must agree (enforced by `CorpusCoherenceTest`).

## Documented deviations

- **Pre/PostCompact payloads are SYNTHESIZED** — those events cannot be driven headlessly.
  Fields mirror exactly what `nav_pre_compact.py` / `nav_post_compact.py` read (`cwd`,
  `session_id`, `transcript_path`, plus `trigger`/`custom_instructions` and
  `compact_summary`), with session identity taken from the live-captured Stop payload.
- **Runtime payload rewrites** (the only edits replays apply, in `corpus.rewrite_payload`):
  `cwd` → the fresh tmp project (the capture-time scratch dir no longer exists) and
  `transcript_path` → `fixtures/transcript.jsonl`, so every machine replays the same
  branch. Stored payload bytes are never modified.
- **Transcript fixture** is the real capture-session transcript minus `attachment`
  records (environment-specific injected content — skills inventory etc.); hooks read
  message records only for the branches this corpus locks.
- **Env discipline** (`corpus.build_env`): `HOME` → empty tmp dir (blocks installed-plugin
  version-drift leakage into the session_start golden); `CLAUDE_PROJECT_DIR`,
  `CLAUDE_USER_MESSAGE`, `CLAUDE_PLUGIN_DIR`, `PILOT_EXECUTOR` stripped (PILOT_EXECUTOR
  would silence the UserPromptSubmit surfaces).

## Env variants (mem-036)

Every dispatcher case runs twice: `CLAUDE_PLUGIN_ROOT` set to the repo root AND unset.
Both must byte-match the same golden. Under the sh-guard manifest (see
`.claude-plugin/plugin.json`):

```sh
f="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/marketplaces/navigator-marketplace}\
/hooks/nav_dispatch.py"; if [ -f "$f" ]; then exec python3 "$f" <Event>; fi
```

an unset var only changes WHICH dispatcher file is executed — the installed-marketplace
fallback — and a missing file no-ops at the sh level before python starts. Once
`nav_dispatch.py` runs, its behavior must not depend on the variable; the suite proves
the unset path is not a silent no-op of a DIFFERENT kind (mem-036's failure class).

## expectedFailure protocol

Six dispatcher cases are decorated `@unittest.expectedFailure` because their ops are not
ported yet. They flip to real assertions as each port lands — port agents remove the
decorator for their surfaces in the same commit as the op. Three cases (`prompt_gate`,
`prompt_brief`, `read_guard`) have silent goldens and are already-green REAL assertions:
do not decorate them (an expectedFailure that passes fails the suite), do not let them
regress.

Note for the five `{}` goldens: v6 side-effect hooks print a bare `{}` JSON doc, while
the TASK-60 runtime prints nothing for silent ops. The ports must reproduce the `{}` doc
or get that delta explicitly sanctioned (task-doc decision + re-record) — never silently
accept the difference.

- **`auto_update` section excluded from the fixture config (TASK-81, 2026-10-05).** The
  golden was recorded with the section silent by accident: `--check-drift` read the plugin
  version from `claude plugin list`, which saw the isolated HOME and found nothing. Since
  TASK-81 the drift check reads the plugin's own manifest, so in this repo it reports
  `6.18.1 behind plugin (v<current>)` — a line that changes on every release and cannot be
  golden-pinned. `session_start_hook.include_sections` in `fixtures/agent/.nav-config.json`
  drops `auto_update`; the recorded stdout is unchanged (the config summary does not render
  that key).

## Re-recording

`python3 record_goldens.py` re-runs the v6 scripts against the frozen stored payloads and
refreshes stdout/exit_code. Only legitimate use: an explicitly sanctioned corpus change.
It refuses to run once the v6 scripts are deleted (Phase 7) — from then on the goldens
are frozen v6 truth.
