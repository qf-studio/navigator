# Navigator v8.4.1 Release Notes

**Release Date**: 2026-10-14
**Type**: Patch — the `/nav` session card reads as this session (TASK-104)

## Changed

- **The session card's first line is this session.** It sits next to the context card, so
  "session" reads as the session you are in. The pane now asks Prometheus for this session's
  own counters (`claude_code_*_total{session_id="<id>"}` over its life; counters never reset)
  and shows its cost, tokens and cache hit rate first. The machine-wide numbers move to the
  second line: `today $x · 7d $y · N commits`. The tokens/min trend is unchanged.
- The session guard from v8.4.0 now derives from the same queries: no tokens for this session
  after two completed turns shows `--` and `this session not in prometheus · metrics SOP`.
  Five more instant queries per refresh (17 in total), all loopback.

Tests: `trip.test.ts` (15 queries with a session id, the session span, the grace),
`register.test.ts` (`(t)` first and second line, `(t11)` guard, fetch counts 17/34);
`make mod-test` 166/166, typecheck green.
