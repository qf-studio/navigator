# TASK-51: Misc Python correctness fixes

**Status**: ✅ Implemented — 2026-06-03
**Created**: 2026-06-02
**Work-package**: `wp11-python-misc`
**Phase**: 4 — Independent tracks (parallel)
**Priority**: Medium
**Effort**: M — Five of six fixes are 1-5 line edits (regex, lstrip helper, add_goal guard, progress_tracker try/except, feature_manager shutil.which). The only one needing care is correction_to_memory: it requires reading graph_manager.add_memory to choose where the 'source' marker lives, and the count fix should ship with a test since the heuristic was structurally wrong. With three focused test files, this is ~half a day; without tests it would be S. Grouping all six in one work-package keeps it M.
**Risk**: low — No published manifest (.claude-plugin/) is touched. No blocking hook code is modified — nav_profile_sync.py is unaffected because it self-tracks last_synced_count and calls --action sync, never the broken --action check. The correction_to_memory change does mutate knowledge-graph memory node shape (adds a 'source' field); this is additive and backward-compatible since existing memories simply lack the field and count as non-correction, but it warrants the included test. release_validator and feature_manager changes are no-ops on current data (lstrip works for ./skills paths today; the one check_command is a static literal).
**Depends on**: none
**Recommendation**: `fix+test`
**Source**: audit `wf_0dc1b9ce-7d8` → plan `wf_187896bb-5af`; roadmap in TASK-42

---

## Summary

Fix six independent small correctness defects in skill helper Python scripts (loop-variable count bug, brittle regex, unguarded JSON, shell=True under bare except, char-stripping lstrip, and missing-key assumption) and add focused unit tests for the non-trivial ones.

## Findings Addressed

- check_for_new_corrections counts synced memories with a condition that ignores the loop variable (correction_to_memory.py:178-181)
- task_id_generator regex requires a description suffix, skipping plain TASK-XX.md files (task_id_generator.py:27)
- progress_tracker reads JSON and indexes required keys without guards, crashes on corrupt/partial file (progress_tracker.py:135,180,210,213-215)
- feature_manager runs subprocess with shell=True under a bare except that swallows interrupts (feature_manager.py:205-217)
- release_validator uses lstrip('./') which strips characters, not the './' prefix (release_validator.py:61,111,195)
- profile_manager.add_goal assumes every goal dict has a 'name' key (profile_manager.py:104)

## Implementation

All six are independent, single-file edits in skills/*/functions/*.py; none touch the published .claude-plugin manifests or any blocking hook's own code, so they can land together in one commit with tests. Concrete fixes grounded in the read code:

1) correction_to_memory.py check_for_new_corrections (lines 178-181): the generator condition `'learned-from' not in str(graph.get('edges', []))` never references loop var `m`, so synced_count is uniformly len(all memories) or 0 — structurally wrong. The live sync path is NOT affected: hooks/nav_profile_sync.py tracks its own last_synced_count state file and calls `--action sync`; only the manual `--action check` CLI reaches this function. Fix per audit rec: tag correction-derived memories at creation. In _correction_to_memory_in_graph, add a source marker (add_memory currently passes source_task=None — confirm add_memory accepts/persists a source/origin field in graph_manager.add_memory before relying on it; if not, set a `source: 'correction'` field on the returned memory node). Then count `sum(1 for m in memories.values() if m.get('source') == 'correction')`. Must read skills/nav-graph/functions/graph_manager.py add_memory signature first — if it has no spare field, store the marker via the existing memory dict.

2) task_id_generator.py line 27: change `rf"{prefix}-(\d+)-.*\.md"` to `rf"{prefix}-(\d+)(?:-.*)?\.md"` so both TASK-09.md and TASK-09-name.md match, aligning with graph_builder.py:146 which uses `r'TASK-(\d+)'`. Trivial one-line regex change.

3) progress_tracker.py: update_progress (135), get_progress (180), get_next_task (210) call `json.loads(data_file.read_text())` then index required keys (data["progress"], data["essential_skills"], data["development_skills"], data["total"]). Wrap loads in try/except json.JSONDecodeError returning {"error": "Progress data corrupt"} (consistent with the existing missing-file {"error": ...} / {"initialized": False} returns), and use .get() with defaults for the indexed keys. get_next_task returns None on missing file — keep that contract for corrupt too.

4) feature_manager.py check_installed (205-217): the only call site passes the static literal `"command -v navigator-multi-claude.sh"` (FEATURES['multi_claude_scripts'].check_command), so this is not user-tainted. Per rec, switch to shell=False with `shlex.split(check_command)` and narrow `except:` to `except (subprocess.SubprocessError, OSError, FileNotFoundError):` so KeyboardInterrupt/SystemExit propagate. Move the local `import subprocess` to module top (and add `import shlex`). Note: `command -v` is a shell builtin — with shell=False it won't resolve; switch the check to `shutil.which("navigator-multi-claude.sh") is not None` (simpler, no subprocess) OR keep check_command but invoke via `["bash","-c",cmd]`. Recommend shutil.which approach for the one installed-type feature; verify no other check_command exists (grep confirms only one).

5) release_validator.py lines 61, 111, 195: replace all three `skill_path.lstrip("./")` with a helper `_strip_dot_slash(p) -> p[2:] if p.startswith("./") else p`. Current plugin.json paths are all `./skills/...` so lstrip happens to work today (latent bug), but it would corrupt any path with a leading-dot segment. Add the helper once, use in check_skills_exist, check_skills_committed, verify_tag_contents.

6) profile_manager.py add_goal line 104: `next((g for g in profile["goals"] if g["name"] == goal["name"]), None)` raises KeyError/TypeError if goal lacks 'name' or a legacy stored goal lacks 'name'. Per rec: guard at top `if not goal.get("name"): return {"error": "goal requires a 'name'"}` (or raise ValueError caught by caller) and use `g.get("name")` in the comparison. Note caller at line 256 ignores return value and main prints goal.get('name','Unknown'); decide on raise-vs-error-dict to match how main consumes it (main currently treats add_goal as returning the profile, then saves — so prefer guarding and returning profile unchanged plus stderr, or raise before save). Keep return type as dict (profile) to not break the save_profile(...) call.

Tests: there is no pytest run in CI (release.yml has no test step) but sibling skills follow a test_*.py convention (e.g. nav-loop/functions/test_*.py, nav-workflow/functions/test_*.py run via plain python3). Add test_*.py next to each non-trivial fix (correction_to_memory, progress_tracker, release_validator) following that convention.

### Files

| File | Change |
| --- | --- |
| `skills/nav-graph/functions/correction_to_memory.py` | Tag correction-derived memories with a source marker and fix check_for_new_corrections to count m.get('source')=='correction' (lines 178-181) |
| `skills/nav-graph/functions/graph_manager.py` | Verify/extend add_memory so a 'source' marker can be persisted on the memory node (read first; extend only if no existing field works) |
| `skills/nav-task/functions/task_id_generator.py` | Loosen regex line 27 to TASK-(\d+)(?:-.*)?\.md so plain TASK-XX.md is counted |
| `skills/nav-onboard/functions/progress_tracker.py` | Guard json.loads with try/except JSONDecodeError and use .get() defaults in update_progress/get_progress/get_next_task (135,180,210,213-215) |
| `skills/nav-features/functions/feature_manager.py` | Replace shell=True check_installed with shutil.which (or shell=False + shlex.split) and narrow bare except to (SubprocessError, OSError); hoist imports |
| `skills/nav-release/functions/release_validator.py` | Add _strip_dot_slash helper and replace the three lstrip('./') calls (lines 61,111,195) |
| `skills/nav-profile/functions/profile_manager.py` | Guard add_goal for missing 'name' and use g.get('name') in the dedup comparison (line 104) |
| `skills/nav-graph/functions/test_correction_to_memory.py` | New: unit test for synced-count after sync and for empty/no-correction graph |
| `skills/nav-onboard/functions/test_progress_tracker.py` | New: unit test that corrupt/partial .progress-data.json returns an error dict, not a crash |
| `skills/nav-release/functions/test_release_validator.py` | New: unit test that _strip_dot_slash handles './skills/x', 'skills/x', and a leading-dot segment correctly |

## Acceptance Criteria

- [x] correction_to_memory.py: after sync_corrections_to_graph adds N memories, check_for_new_corrections reports synced_memories == N and pending == 0 (test asserts this on a temp profile+graph)
- [x] Existing non-correction memories (no source field) are NOT counted as synced
- [x] task_id_generator: get_next_task_id counts both TASK-09.md and TASK-09-name.md (verified: a dir with only TASK-09.md returns TASK-10)
- [x] progress_tracker: update_progress/get_progress/get_next_task on a corrupt or partial .progress-data.json return an {"error":...} dict (or None for get_next_task) instead of raising JSONDecodeError/KeyError
- [x] feature_manager: check_installed uses no shell=True; KeyboardInterrupt is no longer swallowed; multi_claude_scripts feature still reports installed/not-installed correctly (shutil.which)
- [x] release_validator: _strip_dot_slash('./skills/x')=='skills/x', ('skills/x')=='skills/x', ('./a/.b')=='a/.b'; --check-all passes on a clean tree
- [x] profile_manager: add_goal with a goal dict lacking 'name' returns the profile unchanged with a clear stderr error and does not crash; legacy goals without 'name' do not break dedup
- [x] All new test_*.py files pass via `make test`

## Implementation Notes (2026-06-03)

- `add_memory` gained an optional `source` param (persisted on the node only
  when provided → backward-compatible); `correction_to_memory` tags its memories
  `source='correction'` and counts those.
- `feature_manager.check_installed` rewritten to `shutil.which` (no subprocess,
  no `shell=True`, no bare `except:`) — resolves the final token of the probe.
- **Stale-assumption catch**: the plan said to create
  `test_release_validator.py`, but wp1/wp2 already created it — appended a
  `StripDotSlashTest` class instead of overwriting.
- Added `skills/nav-onboard/functions` to the Makefile `TEST_DIRS` (it was
  absent, so the new progress_tracker test would not have run in CI).
- Verified out of scope and left untouched: `release_validator.py` main()'s
  `args.check_version.lstrip("v")` (display-only, guarded) is a separate
  latent bug not in this work-package's findings.

## Technical Decisions

- **Recommendation**: `fix+test`. No published manifest (.claude-plugin/) is touched. No blocking hook code is modified — nav_profile_sync.py is unaffected because it self-tracks last_synced_count and calls --action sync, never the broken --action check. The correction_to_memory change does mutate knowledge-graph memory node shape (adds a 'source' field); this is additive and backward-compatible since existing memories simply lack the field and count as non-correction, but it warrants the included test. release_validator and feature_manager changes are no-ops on current data (lstrip works for ./skills paths today; the one check_command is a static literal).

## Out of Scope

- Findings outside this work-package's listed scope (see TASK-42 roadmap for the full map).

## Refs

- TASK-42 — Audit Remediation Roadmap (umbrella)

## Verify

```bash
# See Acceptance Criteria; run the relevant tests/validators before marking done.
```

## Done

- [x] All acceptance criteria checked
- [x] Tests pass in CI (TASK-43 gate runs `make test`)
- [x] Committed + roadmap (TASK-42) status updated
