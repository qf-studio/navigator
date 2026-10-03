# TASK-85: stop_completion over-fires when two sessions share a repo

**Status**: ✅ Released — v8.0.1, 2026-10-03
**Origin**: TASK-84 8.1 candidate 1 (mem-077). On 2026-10-03 the gate forced a continuation on
~6 read-only turns (lsof, curl, ps, python3 -c) of a session that shared `.agent/` with the
dogfood terminal.

## Root cause

`completion` is a session-scoped state section (`state.py SESSION_SCOPED_SECTIONS`,
`lib/state.ts SESSION_SCOPED`). Every event from another session in the same repo flips
`session.id`; on the next Stop here `completion` loads empty, `prev_digest` is `None`, and the
TASK-71 tree-evidence rule (unchanged `git status --porcelain` digest → not mutating) cannot
fire. The Bash allowlist alone decides, and anything not on it reads as mutating.

Secondary: the allowlist lacks ordinary inspection commands (`lsof`, `pgrep`, a `curl` that
writes no file), and the mod ignores Claude Code's own `isReadOnly` verdict on each tool call.

## Changes

1. **Digest per session, outside the scoped section** (both runtimes, parity): `tree.digests`
   `{ <session_id>: sha }`, bounded to the 8 most recent sessions, no session scoping, no TTL.
   `prev_digest = tree.digests[sid]`, falling back to `completion.tree_digest` (old files).
   `completion.tree_digest` is still written. Python ctx gains `session_id` (runtime, fixture
   generator, tests).
2. **Allowlist** (both runtimes): `lsof`, `pgrep`, `nproc`, `sw_vers`; `curl` is read-only
   unless it names an output (`-o`, `-O`, `--output`, `--remote-name`, `--output-dir`).
3. **Mod only**: a Bash-only turn whose every Bash call returned `isReadOnly: true` from Claude
   Code is not mutating, whatever the allowlist says. `activity.bashCalls` / `bashMutating`
   track the turn; the Stop handler passes `bashAllReadOnly` into the op context. Python keeps
   the allowlist (it has no such signal); the fixture replay passes no flag, so parity holds.

## Verify

- `env -u NAVIGATOR_MOD_OWNS make test`, `make mod-gen-check mod-validate mod-test` green;
  fixtures regenerated.
- New tests: two sessions alternating Stops over one state file — the second session's
  read-only turn does not block; `curl -o` mutating, `curl -s URL` not; mod `isReadOnly` path.
- Live: this session (shares the repo with the dogfood terminal) runs a read-only turn without
  the "forced continuation" notice.

## Not in scope

`code_committed` is unmet while `.agent/marketing/` sits untracked (git never clean) — that is
the repo's state, not the gate's. `NAVIGATOR_MOD_OWNS` appearing in this session's Bash env
without a mod loaded is logged, not chased.

## Done (2026-10-03)

- Python: `runtime.py` ctx carries `session_id`; `stop_completion.py` `_prev_digest` /
  `_record_digest` with `tree.digests` (bounded 8), `completion.tree_digest` kept; `lsof`,
  `pgrep`, `nproc`, `sw_vers` and the `curl` rule in `_bash_readonly`. 65 op tests.
- Mod: `stop-bash.ts` mirror; `stop_completion.ts` `prevDigestOf` / `recordDigest`;
  `turnMutating(…, bashAllReadOnly)`; `register.tsx` counts Bash calls and `isReadOnly` per turn
  (`activity.bashCalls` / `bashMutating`, reset on `turn.complete`), the Stop handler passes
  `bashAllReadOnly` through `runFor`'s new `extra` context. Fixtures regenerated
  (`scripts/mod_fixtures/stopops.py` ctx has `session_id="s"`); 124 kit tests incl. the
  end-to-end pair (w)/(w2).
- Not changed: `SESSION_SCOPED_SECTIONS` — `completion` stays scoped (fuse and held_count are
  per session by design); only the digest moved out.
