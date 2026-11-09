# TASK-47: Knowledge-graph data integrity + dormant maintenance wiring

**Status**: ✅ Implemented — 2026-06-03 (PR #16; Track B decay = idempotent + manual-only/experimental, not hook-wired)
**Created**: 2026-06-02
**Work-package**: `wp6-kg-integrity`
**Phase**: 3 — Behavioral fixes (guarded)
**Priority**: Medium
**Effort**: L — Each code fix is small and localized, but there are ~7 distinct fixes across 4 Python files plus a data migration of a 179k JSON file plus new unit tests for code that currently has zero Python test coverage (only shell scripts in scripts/). The decay-wiring decision (track B) carries design judgment about where mutation may happen safely. Realistically 1-2 days including tests and a repeatable repair script. Splitting is reasonable (see recommendation).
**Risk**: med — Mutates committed, git-tracked graph data (.agent/knowledge/graph.json) — a bad dedup/dangling pass could silently drop legitimate edges, so the repair must be a reviewable script with before/after counts (852->682 edges, 6 dangling removed, 1 confidence fixed) rather than hand edits. No published manifest is touched. The only blocking-hook exposure is the OPTIONAL nav_session_start.py decay wiring: that hook injects session context and must remain read-only on the hot path; writing graph.json on every session start would create noisy git churn and a per-start failure surface, so decay must be throttled and exit-0-safe or wired elsewhere. query_by_concept change is additive (new buckets) so existing callers are unaffected.
**Depends on**: TASK-45 (wp4-hook-tests)
**Recommendation**: `split`
**Source**: audit `wf_0dc1b9ce-7d8` → plan `wf_187896bb-5af`; roadmap in TASK-42

---

## Summary

Repair the corrupt graph.json data (bad confidence, duplicate + dangling edges), close the query/health/confidence code gaps that produced it, and either wire the configured decay/staleness maintenance into a real trigger or stop the config from promising it.

## Findings Addressed

- apply_decay does not update last_validated -> repeated runs double-decay (graph_maintenance.py:124-145)
- Graph timestamps use naive local time labeled UTC 'Z' (graph_manager.py:32,47; graph_builder.py:394)
- update_confidence boost math assumes fixed 0.8 base, mishandling decayed/elevated memories (graph_manager.py:407-413)
- prune_memories leaves empty concept_index entries behind, inconsistent with remove_node (graph_maintenance.py:165-168)
- Invalid confidence 90.0 in mem-026 renders as 9000% (graph.json + graph_manager.py:435) — confirmed: only mem-026 is out of [0,1]
- query_by_concept silently drops marker and concept nodes despite being indexed (graph_manager.py:219-250) — confirmed: e.g. concept 'database' indexes marker 'v4.0.0-release-complete' which never appears in output
- 170 duplicate edge rows in graph.json (852 stored vs 682 unique) — confirmed via dedup count
- 6 dangling edge rows referencing non-existent nodes (graph.json + graph_builder.py:359-366) — confirmed: implements->'tom' (concept never normalized to canonical 'theory of mind'), learned-from->'RELEASE-v6.15.3', learned-from->'TASK-39'
- Confidence decay and staleness pruning configured but never invoked (graph_maintenance.py:124-176; .nav-config.json knowledge_graph.confidence_decay_rate/staleness_threshold_days) — confirmed: only referenced as manual commands in nav-graph/SKILL.md, no hook/session-start caller
- Conflict detector false-positive 'opposing guidance' via naive substring matching (graph_maintenance.py:44-65)
- health_check has no edge-integrity coverage; reports clean score over a graph with 176 edge defects (graph_maintenance.py:179-232)

**Already resolved in v6.15.6** (excluded from this work):
- ~~The single CRITICAL audit finding (deleted nav_commit_reminder.py still registered in plugin.json) was fixed and shipped in v6.15.6 — not part of this work-package and confirmed unrelated to any nav-graph finding here. plugin.json version reads 6.15.6.~~

## Implementation

Two coherent tracks: (A) data repair + code guards, (B) decay/staleness wiring.

(A1) Data fix in .agent/knowledge/graph.json: set mem-026 confidence 90.0 -> 0.9; dedup the edges array to the 682 unique (from,to,type) rows; drop the 6 dangling edges (implements->'tom', learned-from->'RELEASE-v6.15.3', learned-from->'TASK-39'). Do this with a one-shot repair script (committed under scripts/ or run via graph_maintenance --action repair) rather than hand-editing 179k of JSON.

(A2) graph_builder.infer_edges (line 360-366): normalize each task concept through the same map build_concept_nodes uses before emitting the 'implements' edge — the concept node store uses canonical 'theory of mind' but infer_edges emits raw 'tom'. Simplest fix: emit edges to the canonical concept (the concepts already come from extract_concepts_from_text which normalizes, but raw legacy 'tom' slipped in) and add a referential-integrity filter that drops any edge whose from/to is not a known node id before returning the graph. Route build_graph's edge list through add_edge (graph_manager.py:127, already has dedup at 138-143) instead of the raw infer_edges append so dedup is enforced at build time, killing the 170-dup root cause.

(A3) graph_manager.query_by_concept (line 219-250): add 'markers' and 'concepts' to type_to_category, add matching buckets to the results dict (228-236), and add render sections in format_query_results (450-487) with _format_marker/_format_concept helpers. Markers are genuinely indexed (verified) so this surfaces real data.

(A4) graph_manager.add_memory (322) and update_confidence (393): clamp/validate confidence to [0,1] on input (reject or normalize >1.0); fix the boost math at 407-413 — drop the hardcoded `current_boost = confidence - 0.8` anchor and instead clamp boost at min(confidence+0.05, 1.0) or track an original_confidence field, so decayed/elevated memories boost correctly. Fix the 'Z' timestamp bug at graph_manager.py:32,47 and graph_builder.py:394 using datetime.now(timezone.utc).isoformat().

(A5) graph_maintenance.health_check (179-232): add duplicate-edge count, dangling-edge count (from/to not in union of node ids — note concepts node-keys must be included), and confidence-range validation (flag any memory outside [0,1]); factor each into health_score and the issues list. Fix prune_memories (165-168) to delete now-empty concept_index keys mirroring remove_node (114-116), or route through remove_node.

(B) Decay/staleness wiring: apply_decay (124-145) currently re-decays every run because it never records when it last ran. Fix idempotency first: read knowledge_graph.confidence_decay_rate from .nav-config.json, decay against a persisted per-memory last_decayed (or graph-level last_decayed date) so a given calendar day decays at most once. Then add a 'maintenance' action that runs decay+stale read-only-safe and gate it behind a once-per-day throttle. Wire it via the existing nav_task_graph_sync.py pattern OR a small addition to nav_session_start.py — but session-start MUST stay read-only for context injection; if decay mutates graph.json on every start it fights git_tracked:true. Recommended: throttled (>=24h since last_decayed) decay invoked from a PostCompact path or an explicit nav-graph maintenance command, NOT on every session start. If wiring is deemed too risky for this pass, the fallback is to mark decay/staleness experimental in SKILL.md and the config keys, and update the stale SKILL.md health-output example (shows 'Memories: 2', real graph has 37).

(C) Conflict detector (44-65): downgrade to advisory — keep detection but stop letting it subtract from health_score, and add a SKILL.md note that it is heuristic / high-false-positive. Word-boundary matching is a nice-to-have, not required this pass.

### Files

| File | Change |
| --- | --- |
| `.agent/knowledge/graph.json` | mem-026 confidence 90.0->0.9; dedup 852->682 edges; drop 6 dangling edges (implements->tom, learned-from->RELEASE-v6.15.3, learned-from->TASK-39) |
| `skills/nav-graph/functions/graph_builder.py` | infer_edges: normalize concept before 'implements' edge + referential-integrity filter; route build_graph edges through add_edge for dedup; fix 'Z' timestamp at line 394 |
| `skills/nav-graph/functions/graph_manager.py` | query_by_concept + format_query_results: add markers/concepts buckets & render; add_memory/update_confidence: clamp confidence to [0,1] and fix 0.8-anchored boost; fix naive-UTC 'Z' at lines 32,47 |
| `skills/nav-graph/functions/graph_maintenance.py` | apply_decay: idempotent via persisted last_decayed + config rate; prune_memories: delete empty concept_index keys; health_check: add duplicate-edge/dangling-edge/confidence-range checks into score+issues; conflicts advisory (no score penalty) |
| `skills/nav-graph/SKILL.md` | refresh stale health-output example (2->37 memories); document conflict detection as heuristic; document decay/staleness trigger (or mark experimental) |
| `.agent/.nav-config.json` | only if decay is NOT wired: annotate/remove confidence_decay_rate & staleness_threshold_days so config does not promise unrun behavior |
| `hooks/nav_session_start.py` | OPTIONAL, only if throttled decay is wired here: add >=24h-throttled decay call kept strictly side-effect-safe; do not mutate graph on every start |

## Acceptance Criteria

- [ ] After repair, `graph_maintenance.py --action health` reports 0 duplicate edges, 0 dangling edges, and 0 memories with confidence outside [0,1]; health_score reflects these as zero defects
- [ ] `python3 -c` dedup check on graph.json returns 682 stored == 682 unique edges (currently 852 stored / 682 unique)
- [ ] No edge in graph.json references a from/to id absent from the union of all node-type keys (currently 6 dangling: tom, RELEASE-v6.15.3, TASK-39)
- [ ] mem-026 confidence == 0.9 and _format_memory renders it as 90% (not 9000%)
- [ ] Querying a concept that indexes a marker (e.g. 'database' -> 'v4.0.0-release-complete') now lists that marker in query output instead of dropping it
- [ ] Running `--action decay` twice on the same calendar day produces identical confidence values (idempotent); decay reads confidence_decay_rate from .nav-config.json
- [ ] After prune_memories with --execute, no concept_index key maps to an empty list
- [ ] add_memory/update_confidence reject or normalize a confidence > 1.0
- [ ] All new behavior covered by Python unit tests under a tests/ path (build dedup, dangling filter, query markers bucket, decay idempotency, health-check defect counts, confidence clamp) — first Python tests for nav-graph
- [ ] If decay is not wired to a trigger, .nav-config.json + SKILL.md no longer present decay/staleness as active automatic behavior; if wired, nav_session_start.py stays read-only on its context-injection path and decay is throttled to <=1/day

## Technical Decisions

- **Recommendation**: `split`. Mutates committed, git-tracked graph data (.agent/knowledge/graph.json) — a bad dedup/dangling pass could silently drop legitimate edges, so the repair must be a reviewable script with before/after counts (852->682 edges, 6 dangling removed, 1 confidence fixed) rather than hand edits. No published manifest is touched. The only blocking-hook exposure is the OPTIONAL nav_session_start.py decay wiring: that hook injects session context and must remain read-only on the hot path; writing graph.json on every session start would create noisy git churn and a per-start failure surface, so decay must be throttled and exit-0-safe or wired elsewhere. query_by_concept change is additive (new buckets) so existing callers are unaffected.
- **Split**: Track A = data repair (dedup, mem-026 0.90, dangling edges) is low-risk and ships first. Track B = decay/staleness wiring mutates on session start; defer or mark experimental in config + SKILL.md if risk judged too high this pass.

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
