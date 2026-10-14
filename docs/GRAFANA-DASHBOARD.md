# Grafana Dashboard

The dashboard, the Prometheus and the OpenTelemetry Collector that feed it live in
[`.agent/grafana/`](../.agent/grafana/README.md). That README is the single source: setup
(`~/.claude/settings.json` env block, `docker compose up -d`), the 13 panels, ports
(4317/4318/8889 collector, 9092 Prometheus, 3333 Grafana), troubleshooting and useful queries.

Why a collector (TASK-101): Claude Code's `prometheus` exporter serves one fixed port per
process, so only the first of several concurrent sessions ever exports. Every session pushes
OTLP to the collector instead; Prometheus scrapes the collector; metric names are unchanged.

Telemetry environment reference: [`.agent/sops/integrations/opentelemetry-setup.md`](../.agent/sops/integrations/opentelemetry-setup.md).
