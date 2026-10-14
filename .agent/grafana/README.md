# Navigator Grafana Dashboard

**Visual monitoring for Claude Code with OpenTelemetry metrics**

This directory contains everything needed to run Grafana dashboards for Navigator's OpenTelemetry integration.

---

## Quick Start

### Prerequisites

1. **Docker and Docker Compose** installed
2. **Point Claude Code at the collector** (OTLP). Put this in `~/.claude/settings.json`;
   it applies to every project and overrides the same variables in your shell:
   ```json
   {
     "env": {
       "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
       "OTEL_METRICS_EXPORTER": "otlp",
       "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
       "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",
       "OTEL_METRIC_EXPORT_INTERVAL": "10000"
     }
   }
   ```
   Remove any `OTEL_METRICS_EXPORTER=prometheus` line from `~/.zshrc` / `~/.bashrc`.

   **Why OTLP and not the `prometheus` exporter**: the `prometheus` exporter makes each
   Claude Code process serve `http://localhost:9464/metrics`. Only the first process can bind
   that port; every later session exports nothing, silently, and the dashboard and the `/nav`
   session card show `$0.00` for the day. The collector accepts any number of sessions.
3. **Start Claude Code** (new sessions pick up the settings; restart running ones)

### Start Monitoring Stack

```bash
# From .agent/grafana directory:
docker compose up -d
```

This starts:
- **OpenTelemetry Collector** on http://localhost:4318 (OTLP http), 4317 (grpc); scrape
  endpoint http://localhost:8889/metrics
- **Prometheus** on http://localhost:9092
- **Grafana** on http://localhost:3333

### Access Dashboard

1. Open http://localhost:3333
2. Login:
   - Username: `admin`
   - Password: `admin`
3. Navigate to **Dashboards** → **"Navigator - Claude Code Metrics"**

**Dashboard auto-provisions** - no manual import needed!

---

## Dashboard Preview

![Navigator Grafana Dashboard](./dashboard-screenshot.jpg)

*Real-time productivity and token analytics for Navigator*

---

## What You'll See

### Dashboard Panels (13 Total)

**Row 1 - Performance KPIs**:
1. **Cache Hit Rate** - Navigator efficiency (green >80%)
2. **Cache Savings ($)** - Money saved by prompt caching vs full input cost
3. **Commits** - Total commits created
4. **Lines Added** - Productivity metric
5. **Lines Deleted** - Code cleanup metric

**Row 2 - Token Analytics**:
6. **Token Usage (Cumulative)** - Stacked area (cacheRead=green, input=blue, output=purple)
7. **Token Rate** - Instantaneous consumption rate (tokens/min, uses irate() to avoid counter reset spikes)

**Row 3 - Workflow Activity**:
8. **Code Activity** - Lines modified per 5min (bars: added=green, removed=red)
9. **Commits Over Time** - Trend line with points

**Row 4 - Session Stats**:
10. **Active Time** - Coding duration (excludes idle)
11. **Sessions** - Session count
12. **Cost** - Total USD (secondary metric)
13. **Model Usage** - Donut chart (Haiku vs Sonnet distribution)

**Auto-refresh**: Dashboard updates every 10 seconds

---

## Files Included

```
.agent/grafana/
├── README.md                      # This file
├── docker-compose.yml             # Container orchestration (ports: 4317/4318/8889, 9092, 3333)
├── otel-collector-config.yml      # OTLP in → Prometheus scrape endpoint out, names unchanged
├── prometheus.yml                 # Prometheus config (scrapes otel-collector:8889; :9464 legacy)
├── grafana-datasource.yml         # Grafana data source (auto-configured)
├── grafana-dashboards.yml         # Dashboard provisioning config
└── navigator-dashboard.json       # Pre-built 13-panel dashboard
```

---

## Configuration

### Port Conflicts

Default ports configured to avoid common conflicts:
- Grafana: `3333` (not 3000/3001 - often used by dev servers)
- Prometheus: `9092` (not 9090 - often used by other Prometheus instances)

**To change ports**, edit `docker-compose.yml`:

```yaml
# Grafana
ports:
  - "3334:3000"  # Change 3333 to 3334

# Prometheus
ports:
  - "9093:9090"  # Change 9092 to 9093
```

Then update `GF_SERVER_ROOT_URL` to match new Grafana port.

### Change Admin Password

Edit `docker-compose.yml`:

```yaml
environment:
  - GF_SECURITY_ADMIN_PASSWORD=your-secure-password
```

### Adjust Scrape Interval

Edit `prometheus.yml`:

```yaml
global:
  scrape_interval: 30s  # Change from 15s
```

### Data Retention

Edit `docker-compose.yml`:

```yaml
command:
  - '--storage.tsdb.retention.time=30d'  # Change from 7d
```

---

## Troubleshooting

### Dashboard is Empty

**Problem**: No data showing in Grafana

**Solutions**:
1. Check the collector sees your session (one `session_id` per running session):
   ```bash
   curl -s http://localhost:8889/metrics | grep -o 'session_id="[^"]*"' | sort -u
   ```
   Nothing after a full turn (+10 s)? Claude Code is not on OTLP. Check `~/.claude/settings.json`
   `env` (above) and restart the session. `CLAUDE_CODE_OTEL_DIAG_STDERR=1` prints export
   errors, which are silent by default.

2. Check Prometheus can scrape the collector:
   - Open http://localhost:9092/targets
   - Job `claude-code` (target `otel-collector:8889`) should be "UP"
   - Job `claude-code-direct` (`host.docker.internal:9464`) is the legacy `prometheus`
     exporter; "DOWN" is normal on OTLP

3. Check Prometheus data:
   - Open http://localhost:9092
   - Query: `claude_code_token_usage_total`
   - Should return data

### Only one session shows up

**Problem**: several Claude Code sessions run, Prometheus has series for one `session_id`,
the `/nav` session card says `$0.00` today.

**Cause**: `OTEL_METRICS_EXPORTER=prometheus` is still set somewhere (shell rc, project
`.claude/settings.json`). That exporter serves a fixed port, 9464, and only the first process
binds it. `lsof -nP -iTCP:9464 -sTCP:LISTEN` names the one that did.

**Fix**: switch to OTLP as in Prerequisites; restart the sessions.

### Prometheus Can't Connect

**Problem**: Target shows "DOWN" in Prometheus (check at http://localhost:9092/targets)

**Solution** (job `claude-code-direct`, legacy exporter only; the collector job needs no host
address):
- **macOS/Windows Docker Desktop**: Already configured as `host.docker.internal:9464` ✓
- **Linux**: Change to `172.17.0.1:9464` (Docker bridge IP)

Edit `prometheus.yml` for Linux:

```yaml
scrape_configs:
  - job_name: 'claude-code-direct'
    static_configs:
      - targets: ['172.17.0.1:9464']  # For Linux
```

Then reload: `docker kill -s HUP navigator-prometheus`

### Port Already in Use

**Problem**: "Port 3333 is already allocated", "Port 9092 ..." or "Port 4318 ..."

**Solutions**:
1. Stop conflicting service
2. Or change port in `docker-compose.yml` (see [Port Conflicts](#port-conflicts) above)
3. Restart: `docker compose down && docker compose up -d`

---

## Management Commands

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Stop and remove data
docker-compose down -v

# Restart services
docker-compose restart

# Update to latest images
docker-compose pull
docker-compose up -d
```

---

## Customizing the Dashboard

### Edit Existing Dashboard

1. Open Grafana → Dashboards → Navigator
2. Click "Edit" on any panel
3. Modify query, visualization, or settings
4. Click "Save dashboard"

### Export Modified Dashboard

1. Dashboard → Settings → JSON Model
2. Copy JSON
3. Save to `navigator-dashboard.json`
4. Restart Grafana: `docker-compose restart grafana`

### Add New Panel

1. Dashboard → Add Panel
2. Select Prometheus data source
3. Enter query (e.g., `claude_code_commit_count_total`)
4. Configure visualization
5. Save

---

## Useful Prometheus Queries

### Token Usage by Type
```promql
sum(rate(claude_code_token_usage_total[5m])) by (type)
```

### Cost per Hour
```promql
rate(claude_code_cost_usage_total[1h]) * 3600
```

### Cache Efficiency
```promql
sum(claude_code_token_usage_total{type="cacheRead"})
/
sum(claude_code_token_usage_total{type="input"}) * 100
```

### Sessions Started
```promql
sum(claude_code_session_count_total)
```

### Lines of Code Added
```promql
sum(claude_code_lines_of_code_count_total{type="added"})
```

### Model Distribution
```promql
sum(claude_code_token_usage_total) by (model)
```

---

## Advanced Setup

### Team Metrics

Tag your sessions with team info:

```bash
export OTEL_RESOURCE_ATTRIBUTES="team=engineering,user=$(whoami)"
```

Then filter in Grafana:
```promql
claude_code_token_usage_total{team="engineering"}
```

### Multi-User Dashboard

Create dashboard variable:
1. Dashboard → Settings → Variables
2. Add variable: `user`
3. Query: `label_values(claude_code_token_usage_total, user_email)`
4. Use in queries: `claude_code_token_usage_total{user_email="$user"}`

### Alerts

Configure alerting in Grafana:
1. Panel → Alert tab
2. Set condition (e.g., cost > $10/hour)
3. Configure notification channel
4. Save

---

## Related Documentation

- [OpenTelemetry Setup Guide](../sops/integrations/opentelemetry-setup.md)
- [Navigator Session Stats Script](../../skills/nav-start/scripts/otel_session_stats.py)
- [Claude Code Monitoring Docs](https://docs.claude.com/en/docs/claude-code/monitoring-usage)

---

## Cleanup

To remove everything:

```bash
# Stop containers and remove volumes
docker-compose down -v

# Remove images
docker rmi prom/prometheus:latest grafana/grafana:latest otel/opentelemetry-collector-contrib:0.144.0
```

---

**Dashboard Version**: 1.1.0 (collector stack, TASK-101)
**Navigator Version**: 8.4.0
**Last Updated**: 2026-10-14
