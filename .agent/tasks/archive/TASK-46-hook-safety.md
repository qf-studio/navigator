# TASK-46: Hook correctness & safety fixes (non-path)

**Status**: ✅ Implemented — 2026-06-03 (PR #14)
**Created**: 2026-06-02
**Work-package**: `wp5-hook-safety`
**Phase**: 3 — Behavioral fixes (guarded)
**Priority**: Medium
**Effort**: M — ~half-day. token_monitor retirement + plugin.json + README is ~30min and the highest-value piece. The auto-update decouple is the most involved (rewrite the parsing branch in _section_auto_update against the --check-drift JSON shape, ~1h incl. manual run). Staleness guard, pre-compact regex (mirrored to marker_compressor), and the enforcer one-liner are each <30min. Bulk of the time is writing the hook tests wp4 will house (subprocess-driven stdin JSON fixtures). All edits are small and localized; no cross-cutting refactor.
**Risk**: med — Touches the published .claude-plugin/plugin.json manifest that ships to every installed user (same surface as the v6.15.6 critical fix) — removing the token_monitor PostToolUse entry must keep the JSON valid and the remaining two PostToolUse Edit|Write entries intact. nav_session_start.py is a blocking-budget SessionStart hook: the auto-update change reduces risk (read-only vs mutating) but a parsing bug in the --check-drift branch could drop the drift notice (degraded UX, not a crash — _build_payload swallows section exceptions at line 301). The read-counter staleness guard only relaxes blocking, so worst case is a missed bulk-load warning, never a false block. No knowledge-graph data mutation. Requires Claude Code restart to re-register the changed manifest (standard for any plugin.json change).
**Depends on**: TASK-45 (wp4-hook-tests)
**Recommendation**: `fix+test`
**Source**: audit `wf_0dc1b9ce-7d8` → plan `wf_187896bb-5af`; roadmap in TASK-42

---

## Summary

Make Navigator's lifecycle hooks correct and safe by retiring the dead-channel/inaccurate token_monitor, decoupling the mutating plugin-update call from the SessionStart hook budget, and hardening the read-counter, pre-compact heuristics, and workflow_enforcer import fallback.

## Findings Addressed

- SessionStart hook runs a full mutating `claude plugin update` (30s+60s subprocess chain) under a 4s subprocess timeout inside a 10s hook budget (nav_session_start.py:162-195 + auto_updater.py:146-174)
- token_monitor.py prints user-facing warnings on PostToolUse stdout — a model-silent channel per mem-035, same dead-channel class as the retired nav_commit_reminder probe (token_monitor.py:113-122)
- token_monitor token estimate counts entire transcript bytes/4 (including pruned tool outputs) against a hardcoded non-configurable 180k TOKEN_LIMIT (token_monitor.py:29,45-57,94)
- token_monitor.py file mode is 0711 (rwx--x--x), not group/other readable, unlike all sibling hooks 0644/0755
- Read-counter reset is double-sourced (read_guard resets on session_id change; Stop hook resets to 0) with no staleness guard, so a skipped Stop event can bleed a stale count across turns (nav_read_guard.py:131-145, nav_workflow_state.py:84-108)
- nav_pre_compact._compress_context scans only the last 200 transcript lines and treats any line containing a file extension as a file path, yielding low-fidelity recovery markers (nav_pre_compact.py:125-153)
- workflow_enforcer falls back to a stub detect_workflow on ImportError with no diagnostic, silently disabling all workflow detection (workflow_enforcer.py:46-54)

**Already resolved in v6.15.6** (excluded from this work):
- ~~plugin.json registered the deleted nav_commit_reminder.py PostToolUse(Bash) hook — removed in v6.15.6; the PostToolUse block now lists only token_monitor (Edit|Write|Bash) + nav_task_graph_sync + nav_profile_sync (Edit|Write), verified at .claude-plugin/plugin.json:128-159~~
- ~~DEVELOPMENT-README.md corrected from ten to nine hooks with the nav_commit_reminder row removed and version refs synced to 6.15.6 (v6.15.6)~~

## Implementation

Five independent edits, sequenced low-risk first.

1) token_monitor retirement (primary). mem-035 (.agent/knowledge/memories/pitfalls/mem-035.md:37) proves PostToolUse has no model-visible channel — token_monitor.py:113-122 print() to stdout is dead, exactly like the retired nav_commit_reminder probe. The estimate (token_monitor.py:45-57,94) reads the whole transcript file (`len(content)//4`) including tool outputs already pruned from context, against hardcoded TOKEN_LIMIT=180000 (line 29). Recommend RETIRE: delete the PostToolUse(Edit|Write|Bash) entry at plugin.json:128-138, delete hooks/token_monitor.py, and update the DEVELOPMENT-README.md hook table (currently labels it "(legacy)" at the 9th row) to "eight hooks". Keep token_monitor's basename in skills/nav-upgrade/functions/migrate_hooks_out_of_settings.py:56 NAV_HOOK_BASENAMES so existing users' settings.json entries still get cleaned up. This single change also resolves the 0711-perms finding (file gone) and the inaccurate-estimate finding (hook gone). If product wants to keep a context-pressure signal, the fallback is: emit `{}` on stdout, move text to stderr, make TOKEN_LIMIT a config key, and subtract a fixed JSON-envelope factor — but mem-035 makes retirement the honest call.

2) Decouple SessionStart auto-update. nav_session_start.py:_section_auto_update (162-195) invokes auto_updater.py with NO args under timeout=4, which triggers auto_updater.auto_update() — chaining refresh_marketplace (30s, line 132) + update_plugin_via_claude (60s, line 162) + possible reinstall (line 177). Change the subprocess call (line 170) to `[sys.executable, str(updater), "--check-drift", "--config-path", str(root/".agent"/".nav-config.json")]` — read-only, no `claude plugin update`. auto_updater already implements --check-drift (auto_updater.py:531-534) returning {has_drift, plugin_version, project_version, message}. Rewrite the result-parsing branch (lines 178-192) to render a drift notice ("Update available: v{plugin} — run nav-upgrade") instead of update/failed status. Pass root into the function (currently takes only plugin_dir). The actual mutating update stays where nav-start/SKILL.md already runs it (SKILL.md:92) — the hook should only notify, not mutate. This removes the headline timeout-vs-budget hazard.

3) read-counter staleness guard. In nav_read_guard.py:_increment_counter (131-145), the only reset path is session_id mismatch (line 135); the Stop reset in nav_workflow_state.py:84-108 may not fire (mem-036: Stop is silent/skippable). Add a staleness check: before incrementing, parse state["updated_at"] (already written, line 142) and if it is older than a configurable window (default ~300s via read_guard_hook.stale_after_seconds) treat the prior count as 0. Low risk — only relaxes blocking.

4) nav_pre_compact path heuristic. In _compress_context (nav_pre_compact.py:125-153), replace the bare `any(ext in line for ext in (...))` substring test (line 135) with a path-shaped regex (token containing a slash plus a known extension at a word boundary), and sample head+tail of `lines` instead of only `lines[-200:]` (line 125). Mirror the same fix into skills/nav-marker/functions/marker_compressor.py (the docstring at line 111-112 says this duplicates it) to keep parity. Cosmetic-quality only — markers are advisory.

5) workflow_enforcer ImportError diagnostic. In workflow_enforcer.py:51-54, add `print("workflow_enforcer: workflow_detector import failed, enforcement disabled", file=sys.stderr)` in the except branch before defining the stub. Optionally harden the sys.path.insert at line 47 to also try CLAUDE_PLUGIN_DIR (the resolution other subprocess hooks use), but the relative path is correct for the plugin layout — diagnostic is the must-have.

NOTE (wp3 overlap, do NOT own here): nav_session_start.py:60 reads CLAUDE_PROJECT_ROOT while every other hook reads CLAUDE_PROJECT_DIR — Claude Code only sets CLAUDE_PROJECT_DIR, so that fallback is dead. Fix belongs to wp3-plugin-paths; coordinate the one-line change there to avoid a double edit on _project_root.

### Files

| File | Change |
| --- | --- |
| `/Users/aleks.petrov/Projects/startups/navigator/hooks/token_monitor.py` | Delete the file (retire the dead-channel, inaccurate-estimate PostToolUse hook; also resolves 0711 perms). |
| `/Users/aleks.petrov/Projects/startups/navigator/.claude-plugin/plugin.json` | Remove the PostToolUse Edit|Write|Bash token_monitor.py block (lines 128-138); keep nav_task_graph_sync + nav_profile_sync entries. |
| `/Users/aleks.petrov/Projects/startups/navigator/.agent/DEVELOPMENT-README.md` | Drop the token_monitor.py (legacy) row from the hook table; change 'nine hooks' to 'eight hooks'. |
| `/Users/aleks.petrov/Projects/startups/navigator/hooks/nav_session_start.py` | Change _section_auto_update (lines 162-195) to invoke auto_updater with --check-drift --config-path (read-only) and render a drift notice; pass root in. |
| `/Users/aleks.petrov/Projects/startups/navigator/hooks/nav_read_guard.py` | Add updated_at staleness guard in _increment_counter (treat count as 0 when older than read_guard_hook.stale_after_seconds). |
| `/Users/aleks.petrov/Projects/startups/navigator/hooks/nav_pre_compact.py` | Replace bare extension substring match with a path-shaped regex and sample head+tail instead of only last 200 lines in _compress_context. |
| `/Users/aleks.petrov/Projects/startups/navigator/skills/nav-marker/functions/marker_compressor.py` | Mirror the path-regex + head/tail sampling fix to keep parity with nav_pre_compact (the duplicated heuristic). |
| `/Users/aleks.petrov/Projects/startups/navigator/hooks/workflow_enforcer.py` | Emit a one-line stderr diagnostic in the ImportError branch (lines 51-54) before defining the stub detect_workflow. |

## Acceptance Criteria

- [ ] grep of .claude-plugin/plugin.json contains no token_monitor reference; the file parses as valid JSON and still registers nav_task_graph_sync + nav_profile_sync on PostToolUse Edit|Write.
- [ ] hooks/token_monitor.py no longer exists; skills/nav-upgrade migrate_hooks_out_of_settings.py still lists 'token_monitor' in its basename allowlist (existing-user cleanup preserved); its test suite stays green.
- [ ] DEVELOPMENT-README.md hook table no longer lists token_monitor and the count reads 'eight hooks'.
- [ ] A test feeds nav_session_start.py stdin with a Navigator project and asserts: the auto-update subprocess is invoked with --check-drift (no `claude plugin update`), and total hook wall-time stays well under the 10s budget even when the updater is slow (mock/stub claude).
- [ ] A test for nav_read_guard.py writes a counter with updated_at older than stale_after_seconds and asserts the next increment starts from 1 (stale count treated as 0), and a fresh updated_at preserves the running count.
- [ ] A test for nav_pre_compact._compress_context asserts a prose line like 'see the .py docs' is NOT captured as a file path while 'hooks/token_monitor.py' IS, and that paths from the transcript head are sampled (not only the tail).
- [ ] Running workflow_enforcer.py with workflow_detector unimportable prints the 'enforcement disabled' diagnostic to stderr and still exits 0.
- [ ] All existing hook smoke tests and wp4 hook tests pass; manual `python3 hooks/nav_session_start.py < fixture.json` returns valid JSON and does not hang.

## Technical Decisions

- **Recommendation**: `fix+test`. Touches the published .claude-plugin/plugin.json manifest that ships to every installed user (same surface as the v6.15.6 critical fix) — removing the token_monitor PostToolUse entry must keep the JSON valid and the remaining two PostToolUse Edit|Write entries intact. nav_session_start.py is a blocking-budget SessionStart hook: the auto-update change reduces risk (read-only vs mutating) but a parsing bug in the --check-drift branch could drop the drift notice (degraded UX, not a crash — _build_payload swallows section exceptions at line 301). The read-counter staleness guard only relaxes blocking, so worst case is a missed bulk-load warning, never a false block. No knowledge-graph data mutation. Requires Claude Code restart to re-register the changed manifest (standard for any plugin.json change).

## Out of Scope

- Findings outside this work-package's listed scope (see TASK-42 roadmap for the full map).

## Refs

- TASK-42 — Audit Remediation Roadmap (umbrella)
- TASK-45 — dependency (`wp4-hook-tests`)

## Verify

```bash
# See Acceptance Criteria; run the relevant tests/validators before marking done.
```

## Done

- [ ] All acceptance criteria checked
- [ ] Tests pass in CI (once TASK-43 gate exists)
- [ ] Committed + roadmap (TASK-42) status updated
