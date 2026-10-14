# Navigator v8.4.2 Release Notes

**Release Date**: 2026-10-14
**Type**: Patch — the `/nav` session card is this session, nothing else (TASK-104)

## Changed

- **The session card shows this session only.** The card is titled "session", so it shows the
  session: cost, tokens and cache hit rate on the first line; its commits, lines and active
  time on the second (`2 commits · +120 −38 · 1h 05m active`); its own tokens/min trend. The
  machine-wide "today" and "7d" numbers are gone from the card; Grafana has them. A resumed
  session keeps its id, so the numbers cover the whole session, not the current context window.
- Seven Prometheus fetches per refresh instead of seventeen: one probe for the stack, one range
  query and five instant queries, all filtered by `session_id`. Without a session id the card
  falls back to Claude Code's own numbers.
- The v8.4.0 guard is unchanged: no tokens for this session after two completed turns shows
  `--` and `this session not in prometheus · metrics SOP`.

Tests: `trip.test.ts` rewritten around the session model (queries, probe, per-minute selector,
grace, produced line); `register.test.ts` `(t)`, `(t5)`, `(t11)` on 7/14 fetches;
`make mod-test` 164/164, typecheck green.
