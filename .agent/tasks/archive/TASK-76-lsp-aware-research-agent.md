# TASK-76: LSP-aware research — navigator-research uses the LSP tool when present

**Status**: ✅ Released v7.5.0 — 2026-09-13 (spike P1–P4 passed, A/B measured on this repo)

## Context

**Problem**: `navigator-research` answers every codebase question with Grep and sampled
Reads. For symbol questions (who calls X, where is Y defined, file outline, signature)
that means whole-file Reads and text matches that include strings, comments and
same-named symbols. Claude Code has exposed an `LSP` tool since v2.0.74 whenever a
language-server plugin from the official marketplace is enabled (pyright-lsp,
typescript-lsp, gopls-lsp, rust-analyzer-lsp and eight more); Navigator never used it.

**Contradiction resolved**: precise symbol navigation (a language server) worsens
Navigator's zero-dependency promise. Separation by condition: the plugin's presence is
the toggle. The agent lists `LSP` in its tools and uses it only when the harness
actually provides it; without a plugin the tool is absent and the agent runs exactly
as before. Nothing is bundled, no config key, no hook or matcher change.

## Spike (Claude Code 2.1.258, pyright 1.1.414, 2026-09-13)

Driven headlessly through the production path: `claude -p … --agents <json>` with the
agent JSON generated from the working-tree `agents/navigator-research.md` (the installed
plugin is a cache copy, so the file itself is not live), the main session launching it
via the Task tool with `--allowedTools Task,Agent,LSP,Bash,Read,Grep,Glob`, counts taken
from the subagent transcript by `scripts/agent_tool_counts.py`, never from the model's
own report.

- **P1 grant — pass**: with `tools: Read, Grep, Glob, Bash, LSP` the subagent made one
  `LSP` call: `{"operation": "findReferences", "filePath": …, "line": 418, "character": 5}`.
  Transcript `7cd03832-…/subagents/agent-af6a7fa4a596a9b78.jsonl`.
- **P2 correctness — pass, with the finding below**: the answer cited
  `hooks/nav_dispatch.py:21`, the `test_runtime.py` sites, `hooks/ops/test_read_guard.py:323`
  and the driver-string calls in `hooks/test_nav_dispatch.py`; no fabricated path.
- **P3 negative control — pass**: plugin disabled, same definition with `LSP` still
  listed: agent loaded, 4 Reads + 2 Greps, zero LSP calls, no unknown-tool error.
  Transcript `27906176-…/subagents/agent-ae808b30ec9fbda5a.jsonl`.
- **P4 diagnostics noise — quiet**: one `diagnostics` attachment reached the main session
  without any edit (attached when the file was opened): 5 pre-existing pyright errors in
  `hooks/nav_hook_lib/runtime.py` (`object | float` passed to `_record_health(ts: float)`,
  from line 443), no missing-import noise. Below the 10-line threshold, so no
  `pyrightconfig.json` was added.

**Finding — first-request indexing race.** Through Claude Code's client, `findReferences`
on `dispatch` returned only the definition (1 hit) in every cold run, while a minimal LSP
client driving `pyright-langserver` directly returned all 61 references across 4 files in
0.3 s, with or without a `pyrightconfig.json`. The debug log (`--debug-file`) shows the
client sending `textDocument/references` ~0.5 s after `initialize`, before pyright has
enumerated the workspace; `goToDefinition` and `workspaceSymbol` in the same session work
across files. A second identical call returns the full set (probe: 4 → 61 → 61 → 61).
Phase 1.5 therefore carries a one-retry rule; the A/B confirmation run applied it
(1 hit, retry, 61 hits across 4 files).

Side finding: `scripts/session-stats.sh` sums `message.usage` per JSONL line, but one API
response spans several lines (same `requestId`, `apiBlockIndex` 0..n) that repeat
input/cache tokens; on a real subagent transcript the per-line input sum is 2.5x the
per-request sum. Out of scope here; the new script dedupes by `requestId`.

## Implementation

- `agents/navigator-research.md` — `LSP` added to `tools:`; description sentence; new
  `### Phase 1.5: Symbol Navigation (LSP, when available)` (28 lines): availability
  check, question→operation table (outline only for files over ~500 lines, references,
  hover, definition), the one-retry rule for the indexing race, ranged Reads after LSP
  located the body, the static-imports-only rule with this repo's dynamic-wiring examples,
  never for conventions; Phase 2's Grep rule and the Constraints point at Phase 1.5; the
  Sampling Report gains an `LSP calls:` line. The `research_findings` JSON contract is
  unchanged.
- `scripts/agent_tool_counts.py` (new, stdlib) — per-tool `tool_use` counts, LSP calls by
  operation, distinct Read paths, usage deduplicated per `requestId`, `--latest-subagent`
  resolver using Claude Code's project-path encoding (newest by mtime — do not use it
  while two sessions run concurrently; resolve by session id instead).
  `scripts/test_agent_tool_counts.py` (6 tests); `scripts` added to `TEST_DIRS`.

## Measurement

A = pyright-lsp disabled, B = enabled, same launcher, cwd = this repo, one run per cell
plus re-runs where noted (`*`). `ctx` = input + cache-creation + cache-read tokens summed
over the run's requests (total context processed); `fresh_input` was dropped as a
criterion because it tracks prompt-cache state between consecutive runs, not work.
All 47 `path:line` citations across the 10 first-round answers exist (0 fabricated).

| Q | Type | Cond | LSP | Read | Grep | Bash | req | ctx | out | Correct |
|---|---|---|---|---|---|---|---|---|---|---|
| Q1 who calls `dispatch` | symbol | A | 0 | 5 | 6 | 1 | 9 | 284k | 4.9k | yes |
| | | B | 1 (refs → 1 hit) | 3 | 3 | 0 | 5 | 146k | 3.4k | yes |
| | | B* final prompt | 2 (refs 1 → retry 61) | 4 | 1 | 0 | 5 | 142k | 3.5k | yes, 61 static + 3 driver-string sites |
| Q2 outline of `runtime.py` | symbol | A | 0 | 1 | 0 | 0 | 2 | 51k | 1.6k | yes |
| | | B | 1 (documentSymbol) | 2 | 2 | 0 | 5 | 121k | 2.2k | yes |
| | | B* outline rule | 1 (documentSymbol) | 1 | 1 | 0 | 4 | 103k | 2.0k | yes |
| Q3 `evaluate_exit` incl. dynamic import | symbol, fallback | A | 0 | 3 | 4 | 1 | 5 | 136k | 3.0k | yes |
| | | B | 0 | 2 | 2 | 0 | 4 | 99k | 2.1k | yes (`stop_completion.py:165` via Grep) |
| | | B* | 0 | 1 | 5 | 1 | 5 | 133k | 3.0k | yes |
| Q4 stderr emitter rule | convention | A | 0 | 2 | 2 | 0 | 3 | 71k | 1.9k | yes |
| | | A* | 0 | 2 | 1 | 1 | 3 | 75k | 1.5k | yes |
| | | B | 0 | 2 | 4 | 0 | 5 | 137k | 1.7k | yes |
| | | B* | 0 | 2 | 2 | 0 | 3 | 75k | 1.4k | yes |
| Q5 TASK doc convention | convention | A | 0 | 4 | 0 | 7 | 6 | 178k | 4.0k | yes |
| | | B | 0 | 4 | 1 | 3 | 4 | 118k | 4.0k | yes |

Verdict against the plan's criterion:
- References (Q1): LSP used; context halved, fewer Reads and Greps, complete answer.
- Outline (Q2): `documentSymbol` returns names and lines without signatures, so the
  agent read and grepped anyway and spent 2x the context of one whole-file Read of this
  470-line module. Phase 1.5 now reserves the outline route for files over ~500 lines.
- Fallback (Q3): the agent skipped LSP in both runs because the question named dynamic
  imports, and found `stop_completion.py:165` by Grep both times. The "≥1 LSP call"
  condition is not met on Q3; that is the fallback rule working, not a defect.
- Conventions (Q4, Q5): zero LSP calls in every B run; Read counts identical; Grep and
  context differences are within the run-to-run spread seen inside each condition
  (Q4-A 71k/75k, Q4-B 137k/75k). No regression attributable to the change.

## Verification

- `make test` green (15 directories incl. `--- scripts ---`, 6 new tests).
- Spike P1–P4 as above; direct-client probe and Claude Code debug log for the race.
- A/B table above; every cited `path:line` checked for existence and line range.
- Negative control re-run implicitly by condition A of the A/B (plugin disabled, `LSP`
  listed): no errors in any of the 7 A runs.
- Release validator: five version files at 7.5.0.

## Accepted limitations

- The retry rule costs one extra LSP call per cold server; the server stays warm for the
  rest of the session.
- `documentSymbol` output carries no signatures; `hover` per symbol or a ranged Read
  fills them in. For files under ~500 lines one Read is cheaper.
- Passive diagnostics have no documented off-switch and reach the main session when a
  file is opened, not only after edits. The research agent is read-only and returns a
  summary, so its opened files do not leak diagnostics into the caller's context.
- Cloud sessions have no LSP; the availability check makes Phase 1.5 a no-op.
- pyright indexes the workspace (1,119 `.py` files here); memory is the plugin's cost.
- LSP calls never reach `read_guard` (PreToolUse matcher is `Read`); the guard counts
  `.agent/` doc reads, LSP targets code.
- The Sampling Report's `LSP calls` line is model-reported; the script is the truth.
- String- and config-wired code (`registry.py` op names, `spec_from_file_location`,
  `plugin.json` hook commands, driver strings in tests) is invisible to a language
  server; Phase 1.5 requires a Grep confirmation and Q1/Q3 exercised it.
- One or two runs per cell; the numbers are indicative, not statistics. Only pyright
  measured; the prompt text is language-agnostic.
- No test validates agent frontmatter; the P3 run is the load check.
- `make conformance-check` has no `cc-2.1.258.json` result file and fails locally; it is
  not part of the release validator (v7.4.0 shipped the same way).
