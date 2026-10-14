# TASK-101: OTel collector in the Grafana stack — every session exports

**Status**: ✅ Implemented — 2026-10-14 (spike passed on this machine: two concurrent headless sessions on the collector, names byte-identical, settings.json env overrides the shell; `claude_code.active_time.total` needed a second rename rule; Claude Code sends delta counters → `metric_expiration: 48h`)
**Parent**: TASK-100 (part A)
**Effort**: S–M
**Depends on**: Docker Desktop; the `.agent/grafana/` stack running on this machine

## Problem

`OTEL_METRICS_EXPORTER=prometheus` serves `:9464` from each `claude` process. The first
process binds, the rest export nothing (mem-087). Route every session through one OTLP
collector that Prometheus scrapes.

## Acceptance Criteria

- [x] Spike first, on this machine: collector up, env on OTLP, two concurrent sessions, both
      `session_id`s on `localhost:8889/metrics`, metric names identical to today's `:9464`
      names, the pane's today query rises from the new job.
- [x] `docker-compose.yml`: service `otel-collector` (`otel/opentelemetry-collector-contrib`,
      pinned), ports `4317`/`4318`, config from `otel-collector-config.yml`, same network.
- [x] `otel-collector-config.yml`: otlp receivers → prometheus exporter `0.0.0.0:8889`,
      `resource_to_telemetry_conversion` on, `metric_expiration` ≥ 1h, names unchanged
      (`add_metric_suffixes: false` + rename to `_total`, or whatever the spike proves).
- [x] `prometheus.yml`: job `claude-code` → `otel-collector:8889`; job `claude-code-direct`
      keeps `host.docker.internal:9464`.
- [x] Env documented once (OTLP block, `~/.claude/settings.json` `env` recommended) in
      `.agent/sops/integrations/opentelemetry-setup.md`; `.agent/grafana/README.md` is the
      source and `docs/GRAFANA-DASHBOARD.md` points to it; `skills/nav-init/SKILL.md` lists the
      new config file and says 13 panels; `scripts/post-install.sh` prints the OTLP block and
      no longer appends `console` lines to the shell rc.
- [x] mem-087 updated with cause and fix; one decision memory (collector over per-session ports).

## Won't do
- Per-session exporter ports. `lsof` probes. Dashboard query changes (names stay).

## Verify
- Spike checklist. Grafana panels non-empty after the switch. `make test` unaffected.
