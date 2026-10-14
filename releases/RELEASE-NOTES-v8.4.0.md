# Navigator v8.4.0 Release Notes

**Release Date**: 2026-10-14
**Type**: Minor — metrics from every concurrent session; the `/nav` card says when a session is not scraped (TASK-100: TASK-101, TASK-102)

## Why

On 2026-10-14 the `/nav` session card showed `$0.00` for the day in every project. Claude
Code's `prometheus` exporter serves one fixed port, 9464, from each process. Only the first
process binds it; every later session exports nothing, silently. With five or six sessions
open, Prometheus held one idle session whose counters never moved, and the card's "today"
formula correctly reported zero. The card could not tell that it was reading someone else's
session, and nothing warned at session start.

## Added

- **OpenTelemetry Collector in the Grafana stack** (`.agent/grafana/docker-compose.yml`,
  `otel-collector-config.yml`, TASK-101). Every Claude Code session pushes OTLP to
  `localhost:4318` (`4317` for grpc); Prometheus scrapes the collector on `:8889`. Any number
  of concurrent sessions, one endpoint. Metric names stay byte-identical to the direct
  exporter's (`claude_code_cost_usage_total`, `claude_code_token_usage_total`, ...) because
  the collector strips unit suffixes and restores `_total`, so the dashboard and the `/nav`
  queries did not change. Claude Code sends delta counters over OTLP; the collector
  accumulates them and keeps a quiet session's running total for 48 h, so an overnight pause
  does not reset a series. Resource attributes (`session_id`, `user_email`,
  `terminal_type`, ...) remain labels. The legacy `:9464` target stays as job
  `claude-code-direct`.
- **`/nav` session guard** (TASK-102). The pane now asks Prometheus for this session's own
  series. After two completed turns with none, the card shows `--` for today's cost and
  `this session not in prometheus · metrics SOP` instead of a confident `$0.00`. The fleet's
  token and cache numbers stay. `NavTrip.sessionSeen`.
- **Session-start notice**, both runtimes byte-identical: when `OTEL_METRICS_EXPORTER` is
  `prometheus`, the config section ends with
  `Metrics: prometheus exporter is single-session (port 9464); switch to otlp —
  .agent/sops/integrations/opentelemetry-setup.md`. Decided from the environment alone; an
  `lsof` probe would race the exporter's own bind.

## Changed

- **Telemetry setup is OTLP and lives in `~/.claude/settings.json`.** The Grafana README, the
  OpenTelemetry SOP and `nav-init` document one `env` block
  (`OTEL_METRICS_EXPORTER=otlp`, `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`,
  `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318`, `OTEL_METRIC_EXPORT_INTERVAL=10000`).
  Settings `env` applies to every project and overrides the shell; verified on 2.1.287.
  `scripts/post-install.sh` prints that block and no longer appends `console` exporter lines
  to the shell rc. `docs/GRAFANA-DASHBOARD.md` is a pointer to the one source,
  `.agent/grafana/README.md`. `otel_session_stats.py` reads the collector's `:8889` on OTLP.
- The pane's history (context trend) now updates before the Prometheus refresh at turn end,
  so the guard's grace counts the turn that just ended.

Tests: `trip.test.ts` (grace, verdict, selector escaping), `register.test.ts` (13 fetches per
refresh, `t11` render), `test_session_start.py` `SectionMetricsNoticeTest`, two new lifeops
fixture scenarios; `make test-all` green. Knowledge graph: mem-087 updated, mem-104 decision.
Task docs: `.agent/tasks/archive/TASK-100…103`.

## Upgrade

1. `cd .agent/grafana && docker compose up -d` (adds the collector; Prometheus reloads its
   scrape config on `docker kill -s HUP navigator-prometheus` or a restart).
2. Put the `env` block from `.agent/grafana/README.md` into `~/.claude/settings.json`; delete
   `export OTEL_METRICS_EXPORTER=prometheus` from your shell rc.
3. Restart running Claude Code sessions. `curl -s localhost:8889/metrics | grep -o
   'session_id="[^"]*"' | sort -u` lists one line per session.

## Breaking Changes

None. A machine that keeps the `prometheus` exporter still works for one session and now
hears about the limit at session start.
