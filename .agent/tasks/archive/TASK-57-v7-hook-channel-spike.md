# TASK-57: v7 Spike — Empirically Verify Unproven Hook Channels

**Status**: ✅ Implemented — 2026-07-10 (six memories mem-050..055 recorded, CC 2.1.205)
**Created**: 2026-07-10
**Parent plan**: v7.0.0 hooks-runtime concept (approved 2026-07-10)
**Execution**: interactive — NOT dispatched to Pilot (user decision 2026-07-10)
**Effort**: M
**Depends on**: —

## Context

**Problem**: v7 makes hooks the primary deterministic runtime, and its headline capabilities sit
on channels Navigator has never used: PostToolUse/SubagentStart `additionalContext`, Stop
`continue:true`, UserPromptSubmit block-as-answer. mem-035 proves current docs can be wrong about
exactly this class of behavior. Per the plan, nothing is load-bearing until empirically proven.

**Goal**: run six probes (S1–S6) against a live Claude Code session via the ship path, record one
graph memory per channel with dual evidence, thereby confirming — or closing via named fallback —
each spike-gated routing-matrix row. **Hard gate**: no dispatcher code before the memories exist.

## Known Pitfalls & Patterns

- **mem-034** (pitfall, 100): UserPromptSubmit exit 2 bypasses the model; echoing the trigger
  phrase in stderr caused recursive blocks. → S4 carries a mandatory echo-hygiene subtest;
  sentinels are UUID-suffixed and never repeat prompt trigger text.
- **mem-035** (pitfall, 100): PreToolUse/PostToolUse stdout + additionalContext silently dropped
  (live-verified v6.12.0) — CONFLICTS with current docs. → S1 tests PostToolUse fresh on today's
  CC; S5 re-tests PreToolUse; no probe may cite docs as evidence, only observed behavior.
- **mem-036** (pitfall, 95): unset plugin env var made every hook a silent no-op for two releases;
  a project-local `.claude/settings.json` masked it. → whole spike runs from a scratch local
  marketplace (real `${CLAUDE_PLUGIN_ROOT}` binding) in a scratch project with no settings.json,
  no `.agent/`; S6 re-checks binding with env set AND unset.
- **mem-037** (pitfall, 100): Stop hook stamping state on conversational turns deadlocked the
  enforcer. → S2 requires a single-shot flag-file fuse plus a run-twice subtest before
  `continue:true` is trusted anywhere.
- **TASK-45 pattern**: subprocess-against-tmp-project contract tests. → probes are standalone
  re-runnable scripts so TASK-58 can package them into `tests/harness-conformance/` unchanged.
- **v6.18.1 regression**: wide table separator rows corrupt decision extraction → recorded memory
  bodies are prose-only, no wide separator rows.

## Acceptance Criteria

- [ ] Scratch marketplace plugin installs from a local path; a hook logs a non-empty resolved
      `CLAUDE_PLUGIN_ROOT` pointing into the install.
- [ ] Scratch project verifiably has no `.claude/settings.json` and no `.agent/` during probes.
- [ ] All six probes executed; each verdict records CC version, date, transcript path, and BOTH
      observables (behavioral quote-check + transcript grep proving sentinel POSITION).
- [ ] S2: continuation contains the injected sentinel; fuse flag consumed; a second run in the
      same session produces zero further continuations.
- [ ] S4: transcript shows no model invocation on the blocked turn; rendering judged for both
      `decision:block` and exit-2 variants with a winner named; echo-hygiene subtest shows block
      text absent from the next prompt's context and no hook re-trigger.
- [ ] S3: sentinel present in subagent output and absent from main thread; a main-thread-only
      sentinel absent from subagent context (both-way isolation).
- [ ] Six graph memories via `add_memory`, auto-assigned IDs (none from mem-044..049), conf 1.0.
- [ ] S5 memory contains an explicit "supersedes mem-035" or "reconfirms mem-035" statement.
- [ ] `git diff` for this task contains no dispatcher, registry, or `nav_hook_lib` code.

## Implementation

### Phase 1 — Ship-path harness (mem-036, TASK-45)
**Goal**: probes run exactly as consumers run Navigator — no backstop masking.
**Tasks**: build a scratch marketplace (`marketplace.json` + one spike plugin whose manifest
registers all probe hooks); scratch project with NO `.claude/settings.json`, NO `.agent/`;
`claude plugin marketplace add <local-path>` + install; record `claude --version`; per-run UUID
sentinels (`NAV-S<n>-<uuid8>`); dual-observable checker (answer quote-check + transcript JSONL
grep asserting position, not mere presence).
**Files**: `/tmp/nav-v7-spike/marketplace/`, `/tmp/nav-v7-spike/project/`, probe scripts in
`/tmp/nav-v7-spike/probes/` (re-runnable; TASK-58 lifts them verbatim).

### Phase 2 — Injection probes: S1, S3
**S1 — PostToolUse additionalContext**
- Shape: PostToolUse (matcher `Read`) returns `hookSpecificOutput.additionalContext` carrying the
  sentinel plus "quote this token in your answer".
- Drive: ask the model to read a scratch file and summarize it.
- Pass: sentinel quoted in the visible answer AND transcript grep finds it adjacent to the
  tool_result block (not echoed elsewhere).
- Fail → fallback (routing matrix): PostToolUse advisory tier dies — queue in state, surface at
  next UserPromptSubmit. PostToolUseFailure (S1-analog) inherits the same verdict.

**S3 — SubagentStart additionalContext**
- Shape: SubagentStart returns additionalContext with sentinel A; main thread separately carries
  sentinel B via the driving prompt.
- Drive: prompt the main thread to spawn a Task agent for a trivial question.
- Pass: A in subagent output, absent from main-thread turns; B absent from subagent transcript
  (both-way isolation check).
- Fail → fallback: drop the subagent_context feature entirely (plan names no degraded variant).

### Phase 3 — Control-flow probes: S2, S4 (mem-037, mem-034)
**S2 — Stop continue:true with single-shot fuse**
- Shape: Stop hook emits `{"continue": true}` + injected instruction containing the sentinel;
  before emitting it checks a flag file — present → silent exit 0; absent → write flag, emit.
- Drive: one trivial turn, observe forced continuation. Run-twice subtest: a second prompt in the
  same session must end with no continuation (fuse consumed).
- Pass: continuation contains the sentinel; flag consumed; second run does not continue. If
  continuation loops despite the fuse, record it as circuit-breaker evidence for TASK-62.
- Fail → fallback: stop_completion uses Stop `decision:block`; `continue:true` stays OFF.

**S4 — UserPromptSubmit block-as-answer (Tier-1 candidate)**
- Shape: on the exact prompt `nav spike ping`, variant A returns `{"decision": "block", "reason":
  <answer with sentinel>}`; variant B exits 2 with the answer on stderr.
- Drive: send the trigger prompt once per variant; then send an unrelated follow-up prompt.
- Pass: transcript shows zero model invocation on the blocked turn; rendering quality judged per
  variant (markdown honored? error chrome?) and a winner picked; echo-hygiene (mem-034): block
  text absent from the follow-up's context, and the follow-up does not re-trigger the hook.
- Fail → fallback: Tier-1 demotes to advisory injection ("answer verbatim from this data").

### Phase 4 — Re-checks: S5, S6 (mem-035, mem-036)
**S5 — PreToolUse injection re-test (mem-035 conflict)**
- Shape: PreToolUse (matcher `Read`) emits both plain stdout and additionalContext with the
  sentinel while allowing the tool call.
- Drive: trigger a Read; check whether either channel reaches the model.
- Pass: either outcome is a result. Injection works → memory supersedes mem-035. Still dropped →
  memory reconfirms mem-035, docs remain untrustworthy, every other pass is version-fragile →
  conformance-suite (TASK-58) priority rises. read_guard stays deny-only either way.

**S6 — CLAUDE_PLUGIN_ROOT env-binding re-check**
- Shape: manifest hook command appends the resolved `${CLAUDE_PLUGIN_ROOT}` to a log file.
- Drive: live session (harness binds the var) + mem-036 three-variant shell test of the manifest
  command: env unset, empty string, explicitly bound.
- Pass: live log shows a non-empty path into the marketplace install.
- Fail → fallback: shell parameter-expansion fallback path (mem-036 recipe) becomes mandatory in
  the v7 dispatcher manifest. Plan budget: 15 minutes of insurance.

### Phase 5 — Record memories (the deliverable; v6.18.1 caution)
**Goal**: six channel verdicts queryable from the graph; v7 design cites memories, never docs.
**Tasks**: one `add_memory` per channel with AUTO-ASSIGNED IDs — do NOT hand-pick mem-044..049;
those IDs are burned by archived `resolved/` files. Each body: verdict, "empirically observed in
CC vX.Y.Z", date, transcript path, probe script path; confidence 1.0; prose only (no wide
separator rows — v6.18.1 regression). S5 memory must state explicitly whether it supersedes or
reconfirms mem-035. The TASK-60 design doc will cite these IDs, never harness docs.
**Files**: `.agent/knowledge/memories/` (auto-placed), `.agent/knowledge/graph.json` (via tool).

## Out of Scope

- Dispatcher, registry, or `nav_hook_lib` code — hard-gated behind this task (TASK-59/60).
- Packaging probes + checked-in `results/cc-<version>.json` (TASK-58).
- Any change to shipping hooks, `.claude-plugin/plugin.json`, config, or CLAUDE.md.
- Probing the plan's deliberate exclusions (PermissionRequest, MessageDisplay, StopFailure, etc.)
  or the `updatedInput`/`updatedToolOutput` rewrite channels — no v7 op depends on them.
- Acting on verdicts — feature builds and demotions land in TASK-59..63 per the routing matrix.

## Technical Decisions

| Decision | Options Considered | Chosen | Reasoning |
|---|---|---|---|
| Probe env | settings.json vs marketplace | marketplace | mem-036: settings.json masks failures |
| Evidence | single; dual observable | dual, position grep | mem-034: echoes false-pass presence |
| Memory IDs | hand-pick 044..049; auto | auto-assign | IDs burned by archived resolved/ files |
| Sequencing | parallel dispatcher work; gate | hard gate | plan: no dispatcher code pre-memories |
| S2 ship default | on if pass; off until proven | OFF until proven | mem-037 successor risk |

Deferred decisions (resolved BY this spike and recorded in the memories, not decided here):
- `decision:block` vs exit-2 as the Tier-1 mechanism — S4 picks the winner on rendering + hygiene.
- Whether Stop `continue:true` ships (S2), subagent_context exists (S3), PreToolUse reopens (S5).

## Verify

```bash
claude --version                                  # recorded into every memory body
cd /tmp/nav-v7-spike/project && test ! -e .claude/settings.json && test ! -d .agent
grep -n "NAV-S" <transcript>.jsonl                # per-sentinel position check, each probe
ls /tmp/nav-v7-spike/probes/                      # six re-runnable probe scripts
python3 skills/nav-graph/functions/memory_recall.py --concepts hooks harness-behavior
git diff --stat                                   # no hooks/nav_dispatch.py, no nav_hook_lib/
```

## Done

- Six graph memories exist (auto-assigned IDs, confidence 1.0), one per channel, each carrying CC
  version, date, transcript path, and a pass/fail verdict against the falsifiable criteria above.
- S5 memory explicitly supersedes or reconfirms mem-035.
- Every spike-gated routing-matrix row points at a proven channel or its named fallback;
  TASK-59/60 unblocked. Probe scripts re-runnable, handed to TASK-58 for packaging.

## Results (2026-07-10, CC 2.1.205)

Six memories recorded, confidence 1.0, auto-assigned IDs mem-050..055 (mem-044..049 correctly
skipped as burned). Channel verdicts, one line each:

- **S1 (mem-050)**: PostToolUse `additionalContext` DELIVERS — supersedes mem-035 for this
  sub-channel; declarative content only (imperatives flagged as prompt injection and refused).
- **S2 (mem-051)**: Stop `continue:true` NO-OP; `decision:block`+reason is the forced-continuation
  mechanism; `stop_hook_active` belt + flag-file fuse both verified. continue:true ships OFF.
- **S3 (mem-052)**: SubagentStart `additionalContext` WORKS; subagent complied (start-context is
  trusted, unlike tool-adjacent); both-way isolation holds; subagent transcripts are separate
  `<session>/subagents/agent-<id>.jsonl` files.
- **S4 (mem-053)**: block-as-answer WORKS both variants, zero model tokens (num_turns=0, usage=0);
  WINNER `decision:block` (exit-2 leaks hook command chrome); no re-trigger; CC appends
  "Original prompt: <trigger>" to block messages — transcript-scanning hooks must tolerate it.
- **S5 (mem-054)**: PreToolUse split — stdout DEAD (reconfirms mem-035 for stdout);
  `additionalContext` DELIVERS (supersedes mem-035 for that sub-channel). read_guard stays
  deny-only per plan.
- **S6 (mem-055)**: `${CLAUDE_PLUGIN_ROOT}` binds (to marketplace SOURCE path for dir-source
  installs); unset = LOUD exit-2 failure, not silent no-op; SessionStart fires in headless `-p`;
  silent hooks leave no transcript attachment (conformance needs side-channel logs).

**Method lesson (feeds TASK-58)**: never use "quote this token verbatim" as the injection
observable on tool-adjacent channels — the model's injection defense refuses compliance while
delivery succeeds. Use a declarative fact + a question only answerable from it. Also: hook payload
`cwd` arrives realpath'd on macOS (`/tmp` → `/private/tmp`) — never string-prefix-gate on cwd.
`memory_recall.py` takes comma-separated concepts: `--concepts "hooks,harness-behavior"`.

Probe scripts (re-runnable, for TASK-58): `/tmp/nav-v7-spike/probes/` — `common.py` +
`probe_s{1..6}.py`; harness at `/tmp/nav-v7-spike/marketplace/` (plugin installed at user scope,
uninstall after TASK-58 packaging). Verdicts: `/tmp/nav-v7-spike/state/verdict-s*.json`.

## Refs

- Plan: `~/.claude/plans/the-cocept-of-the-delightful-dongarra.md` (spike table, routing matrix)
- `.agent/knowledge/memories/pitfalls/mem-034.md`, `mem-035.md`, `mem-036.md`, `mem-037.md`
- `hooks/test_workflow_enforcer.py` — subprocess-vs-tmp-project template (TASK-45); TASK-58/59/60

**Last Updated**: 2026-07-10
