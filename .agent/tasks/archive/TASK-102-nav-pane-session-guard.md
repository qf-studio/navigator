# TASK-102: /nav guard — say when this session is not in Prometheus; session-start notice

**Status**: ✅ Implemented — 2026-10-14 (grace counts completed turns from the pane history, which now updates before the Prometheus refresh; Python fallback warns only when `OTEL_METRICS_EXPORTER` reaches the hook process)
**Parent**: TASK-100 (part B)
**Effort**: S–M
**Depends on**: TASK-101 (so the guard has a true "seen" path to test against)

## Problem

The trip card renders a confident `$0.00` when Prometheus holds only a stale session
(`buildTrip` needs week tokens > 0, nothing else). The mod has `io.sessionId` and never asks
whether this session's series exist. Session start probes the judge key but not the metrics path.

## Acceptance Criteria

- [x] `refreshTrip` adds `max(claude_code_token_usage_total{session_id="<id>"})` →
      `NavTrip.sessionSeen: boolean`; `false` only after ≥ 2 completed turns (export lands 10 s
      after the first turn).
- [x] Session card: `sessionSeen === false` → today cost `--` and one line
      `this session not in prometheus · metrics SOP` (≤ 48 cols). `TripSpan.usd` stays numeric.
- [x] `session_start` in both runtimes, byte-identical: when `OTEL_METRICS_EXPORTER=prometheus`
      append `Metrics: prometheus exporter is single-session (port 9464); switch to otlp — .agent/sops/integrations/opentelemetry-setup.md`
      after the judge/modes notices. Env-only, no `lsof`.
- [x] Tests: `trip.test.ts` (`sessionSeen` true/false), `register.test.ts` fetch counts
      12 → 13 and a `sessionSeen=false` render, Python `test_session_start` notice,
      `scripts/mod_fixtures/lifeops.py` + regenerated `lifeops-session_start.gen.ts`,
      `make test-all` green with `NAVIGATOR_MOD_OWNS` unset.

## Won't do
- Nullable cost. `lsof` at session start (races the exporter's own bind).

## Verify
- Set `OTEL_METRICS_EXPORTER=prometheus` in one session while another holds 9464: `/nav`
  shows `--` + the line; session start shows the notice. Normal OTLP session: no notice, cost rises.
