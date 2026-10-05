# Navigator v8.2.0 Release Notes

**Release Date**: 2026-10-05
**Type**: Minor — the reject log: every refusal the runtime makes, one line, greppable (TASK-88)

## Added

- **Reject log.** Navigator already refused deterministically at three points — the read guard
  denies the fifth repeated `.agent/` Read, the prompt gate drops a loop prompt that follows a
  skipped WORKFLOW CHECK, the stop gate forces one continuation on an unfinished mutating turn —
  but kept only tallies: no reason, no time. The 2026-10-03 stop-gate over-fire (six blocks on
  read-only turns) was diagnosed from the transcript. Each refusing op now attaches
  `reject: {reason, evidence}` to its blocking result; the runtime strips the key before the
  merge and appends one compact JSON line to `.agent/.nav-rejects.jsonl` from a single point
  per runtime (`runtime._log_reject`, `runner.ts logReject`). The line:
  `{ts, session, event, op, tool?, reason, evidence, suppressed?}`. Evidence per op: read guard
  `{path, count, threshold}`; stop gate `{met, unmet, mutating_tools}`, so a Bash-only
  over-fire reads `"mutating_tools":["Bash"]` in one `grep`; prompt gate `{trigger}`.
- **Pilot writes it too.** Under `PILOT_EXECUTOR` the merge belt strips every block; the log
  line survives with `suppressed: true` — the refusal was computed, not applied. The autonomous
  case is the one that needs the record most.
- **Bounded, on by default.** The file keeps its newest 500 lines (rewritten past 600). It
  observes and never blocks, so `reject_log.enabled` ships on; `nav-features disable reject_log`
  turns it off. Gitignored here and by `nav-init`.
- **In the pane.** With `d`, the reads card ends with `rejects today N · last HH:MM <op>`
  (warning color when today is non-zero); `l` opens the last eight lines. The log never enters
  the model's context — the pane renders it, stderr stays sentinel-redacted.

## Parity

Python and the mod emit byte-identical lines: a generated corpus
(`scripts/mod_fixtures/rejects.py` → `hooks/mod/tests/fixtures/rejects.gen.ts`) is asserted in
`rejects.test.ts`; the op fixtures carry the new `reject` key on both sides.

Tests: 146 kit tests (+7: line parity, one line per refusal, strip, off switch, Pilot
suppression, bounded append, pane model); Python runtime tests (+7) and the three op suites
assert the summaries. Config: `reject_log.enabled` (default `true`).
Design: `.agent/tasks/archive/TASK-88-reject-log.md`.
