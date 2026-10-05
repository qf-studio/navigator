# Navigator Grafana Dashboard

**Visual monitoring for Claude Code with OpenTelemetry metrics**

This directory contains everything needed to run Grafana dashboards for Navigator's OpenTelemetry integration.

---

## Quick Start

### Prerequisites

1. **Docker and Docker Compose** installed
2. **Enable Claude Code Prometheus exporter**:
   ```bash
   # Add to ~/.zshrc or ~/.bashrc
   export CLAUDE_CODE_ENABLE_TELEMETRY=1
   export OTEL_METRICS_EXPORTER=prometheus

   # Reload shell
   source ~/.zshrc  # or source ~/.bashrc
   ```
3. **Start Claude Code** - metrics will be available at `http://localhost:9464/metrics`

### Start Monitoring Stack

```bash
# From .agent/grafana directory:
docker compose up -d
```

This starts:
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
├── docker-compose.yml             # Container orchestration (ports: 9092, 3001)
├── prometheus.yml                 # Prometheus config (scrapes localhost:9464)
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
1. Check Claude Code is running with Prometheus exporter:
   ```bash
   curl http://localhost:9464/metrics
   ```

2. Check Prometheus can scrape Claude Code:
   - Open http://localhost:9090/targets
   - Look for `claude-code` target
   - Should be "UP" (not "DOWN")

3. Check Prometheus data:
   - Open http://localhost:9090
   - Query: `claude_code_token_usage_total`
   - Should return data

### Prometheus Can't Connect

**Problem**: Target shows "DOWN" in Prometheus (check at http://localhost:9092/targets)

**Solution**:
- **macOS/Windows Docker Desktop**: Already configured as `host.docker.internal:9464` ✓
- **Linux**: Change to `172.17.0.1:9464` (Docker bridge IP)

Edit `prometheus.yml` for Linux:

```yaml
scrape_configs:
  - job_name: 'claude-code'
    static_configs:
      - targets: ['172.17.0.1:9464']  # For Linux
```

Then restart: `docker compose restart prometheus`

### Port Already in Use

**Problem**: "Port 3333 is already allocated" or "Port 9092 is already allocated"

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
docker rmi prom/prometheus:latest grafana/grafana:latest
```

---

**Dashboard Version**: 1.0.0
**Navigator Version**: 3.1.0
**Last Updated**: 2025-10-20
