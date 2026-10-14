# OpenTelemetry Setup for Navigator

**Purpose**: Enable real-time session statistics with official Claude Code metrics
**When to use**: Setting up Navigator for the first time, enabling ROI measurement
**Last Updated**: 2026-10-14 (TASK-101: OTLP through the collector is the default; the `prometheus` exporter is single-session)

---

## Quick Start

### 1. Start the local stack

```bash
cd .agent/grafana && docker compose up -d
```

This starts an OpenTelemetry Collector (OTLP in on `localhost:4318`, scrape endpoint on
`localhost:8889`), Prometheus (`:9092`) and Grafana (`:3333`). Details:
[`.agent/grafana/README.md`](../../grafana/README.md).

### 2. Point Claude Code at the collector (one-time)

Put the variables in `~/.claude/settings.json`. They apply to every project and override the
same variables exported by your shell:

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

Remove any `export OTEL_METRICS_EXPORTER=...` line from `~/.zshrc` / `~/.bashrc`; one place
only. Restart running Claude Code sessions.

**Do not use `OTEL_METRICS_EXPORTER=prometheus` with more than one session.** That exporter
serves a fixed port (`9464`) from each Claude Code process. Only the first process binds it;
every later session exports nothing, silently (`CLAUDE_CODE_OTEL_DIAG_STDERR=1` surfaces the
error). The dashboard and the `/nav` session card then show `$0.00` for the day, and session
start warns `Metrics: prometheus exporter is single-session`. The collector accepts any number
of sessions on one endpoint (mem-087).

### 3. Verify

After one full turn (plus the 10 s export interval):

```bash
curl -s http://localhost:8889/metrics | grep -o 'session_id="[^"]*"' | sort -u
```

One line per running session. `/nav` shows today's cost from the same data.

---

## What Navigator Tracks

### Metrics Used by Navigator

**claude_code.token.usage**
- Input tokens (with cache breakdown)
- Output tokens
- Cache read tokens (free)
- Cache creation tokens

**claude_code.cost.usage**
- Session costs in USD
- Cost per model

**claude_code.active_time.total**
- Actual active work time
- Not idle time

### Benefits for Navigator Users

1. **Real Token Usage** (not estimates)
   - See actual tokens consumed
   - Cache hit rates validate Navigator efficiency

2. **Cost Tracking**
   - Monitor session spend
   - Prove ROI with real savings data

3. **Cache Performance**
   - See CLAUDE.md caching in action
   - Validate context optimization

4. **Productivity Metrics**
   - Track active time vs output
   - Measure tokens per feature delivered

---

## Configuration Options

### Console Exporter (terminal only)

**No stack, metrics printed to stderr every interval**. Nothing stores them, so `/nav`, the
dashboard and `otel_session_stats.py` see nothing:

```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_METRICS_EXPORTER=console
export OTEL_METRIC_EXPORT_INTERVAL=10000  # 10 seconds (default: 60s)
```

### OTLP Exporter (default: the local collector, or any remote one)

The Quick Start above. `OTEL_EXPORTER_OTLP_PROTOCOL` may be `grpc` (`:4317`) or
`http/protobuf` (`:4318`); the local collector listens on both. For a remote collector set
`OTEL_EXPORTER_OTLP_ENDPOINT` and, if needed, `OTEL_EXPORTER_OTLP_HEADERS`.

Claude Code sends **delta** counters over OTLP. The local collector accumulates them per series
and keeps a quiet session's running total for 48 h (`metric_expiration` in
`.agent/grafana/otel-collector-config.yml`), so an overnight pause does not reset a counter.
Metric names on the scrape side are the same as the direct exporter's
(`claude_code_cost_usage_total`, `claude_code_token_usage_total`, ...); the collector config
strips unit suffixes and restores `_total` so dashboards and `/nav` queries never change.

### Prometheus Exporter (single session only)

```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_METRICS_EXPORTER=prometheus
```

Metrics at `http://localhost:9464/metrics`, served by the Claude Code process itself. One
process per port: a second concurrent session exports nothing. Prometheus still scrapes this
endpoint as job `claude-code-direct`, so a one-session machine keeps working, but the OTLP path
above is the one Navigator documents and tests. `lsof -nP -iTCP:9464 -sTCP:LISTEN` names the
process that holds the port.

---

## Advanced Configuration

### Multi-Team Organization Support

Add custom attributes to distinguish teams:

```bash
export OTEL_RESOURCE_ATTRIBUTES="team=engineering,department=platform,cost_center=eng-123"
```

Benefits:
- Filter metrics by team
- Track costs per department
- Team-specific dashboards
- Per-team alerts

### Authentication (Enterprise)

For authenticated OTLP endpoints:

```bash
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer your-token-here"
```

### Metrics Cardinality Control

Control which attributes are included:

```bash
# Include session IDs (default: true)
export OTEL_METRICS_INCLUDE_SESSION_ID=true

# Include app version (default: false)
export OTEL_METRICS_INCLUDE_VERSION=true

# Include account UUID (default: true)
export OTEL_METRICS_INCLUDE_ACCOUNT_UUID=true
```

Lower cardinality = better performance, less storage cost.

---

## Navigator-Specific Setup

### Recommended Configuration for Navigator Projects

The `~/.claude/settings.json` block from the Quick Start, plus optional resource tags:

```json
{
  "env": {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",
    "OTEL_METRIC_EXPORT_INTERVAL": "10000",
    "OTEL_RESOURCE_ATTRIBUTES": "workflow=navigator,context_optimization=enabled"
  }
}
```

### For ROI Measurement

If tracking Navigator savings across projects:

```bash
# Tag sessions with Navigator usage
export OTEL_RESOURCE_ATTRIBUTES="navigator_enabled=true,project=your-project-name"
```

Then compare metrics:
- Sessions with `navigator_enabled=true` (optimized)
- Sessions without Navigator (standard workflow)

Calculate token savings, cost reduction, productivity gains.

---

## Troubleshooting

### Issue: No Metrics Displayed

**Symptom**: Navigator says "No metrics yet"; `/nav` shows `--` for cost

**Solutions**:
1. Check telemetry is enabled in `~/.claude/settings.json` `env` (or `echo
   $CLAUDE_CODE_ENABLE_TELEMETRY` prints `1`).
2. Check the stack is up: `docker ps | grep navigator-` lists the collector, Prometheus and
   Grafana.
3. Wait for the first export (`OTEL_METRIC_EXPORT_INTERVAL`, default 60 s; Navigator
   recommends 10 s), then `curl -s http://localhost:8889/metrics | grep -c claude_code`.
4. Export errors are silent by default: start one session with
   `CLAUDE_CODE_OTEL_DIAG_STDERR=1` to see them.

### Issue: Only one session has metrics; `/nav` says `$0.00` today

**Symptom**: several Claude Code sessions run; Prometheus has one `session_id`; the session card
reads `this session not in prometheus`; session start prints
`Metrics: prometheus exporter is single-session (port 9464); switch to otlp`.

**Cause**: `OTEL_METRICS_EXPORTER=prometheus` is still set (shell rc, a project
`.claude/settings.json`, or a stale `~/.claude/settings.json`). One process holds port 9464;
the rest export nothing.

**Fix**: the Quick Start block in `~/.claude/settings.json`; delete the shell export; restart
the sessions. `lsof -nP -iTCP:9464 -sTCP:LISTEN` shows which process held the port.

### Issue: Setup Instructions Always Show

**Symptom**: Navigator keeps showing OTel setup instructions

**Solution**: Verify environment variable is set:
```bash
env | grep CLAUDE_CODE_ENABLE_TELEMETRY
# Should show: CLAUDE_CODE_ENABLE_TELEMETRY=1
```

If not, check:
- Did you reload shell? (`source ~/.zshrc`)
- Is export in correct config file? (`.zshrc` for Zsh, `.bashrc` for Bash)
- Are you using correct shell? (check with `echo $SHELL`)

### Issue: Metrics Look Wrong

**Symptom**: Token counts don't match expectations

**Explanation**:
- Metrics are cumulative for the session
- Shows total since session start
- Cache reads are separate from input tokens

**Validation**:
- Compare with Claude Console usage dashboard
- Check cache_read + fresh_input = total_input

---

## Enterprise Deployment

### Using OpenTelemetry Collector

**Setup collector for centralized monitoring**: the local stack in `.agent/grafana/` is the
same shape (collector → Prometheus → Grafana); host its `docker-compose.yml` and
`otel-collector-config.yml` on a shared machine and point every developer's
`OTEL_EXPORTER_OTLP_ENDPOINT` at it. Keep the collector's `metricstransform` and
`add_metric_suffixes: false` so metric names match the dashboard.

**Client configuration**:

```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_METRICS_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_ENDPOINT=http://collector.company.com:4317
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer company-token"
```

### Administrator Configuration

For organization-wide rollout, use managed settings:

**File**: `/Library/Application Support/ClaudeCode/managed-settings.json` (macOS)

```json
{
  "env": {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector.company.com:4317",
    "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Bearer company-token"
  }
}
```

Distributable via MDM (Mobile Device Management).

---

## ROI Measurement with Navigator

### Metrics to Track

**Token Efficiency**:
```sql
-- Sessions with Navigator
SELECT
  SUM(claude_code.token.usage) as navigator_tokens
WHERE
  OTEL_RESOURCE_ATTRIBUTES LIKE '%navigator_enabled=true%'

-- Sessions without Navigator
SELECT
  SUM(claude_code.token.usage) as standard_tokens
WHERE
  OTEL_RESOURCE_ATTRIBUTES NOT LIKE '%navigator_enabled=true%'

-- Calculate savings
token_reduction = (standard_tokens - navigator_tokens) / standard_tokens * 100
```

**Cost Savings**:
```sql
SELECT
  SUM(claude_code.cost.usage) as total_cost
WHERE
  OTEL_RESOURCE_ATTRIBUTES LIKE '%navigator_enabled=true%'
GROUP BY session.id

-- Compare to pre-Navigator baseline
```

**Productivity**:
```sql
SELECT
  SUM(claude_code.lines_of_code.count) / SUM(claude_code.token.usage) as loc_per_token
WHERE
  OTEL_RESOURCE_ATTRIBUTES LIKE '%navigator_enabled=true%'
```

### Grafana Dashboard (Quick Start)

Navigator includes a pre-configured Grafana stack in `.agent/grafana/`.

**Prerequisites**:
1. Enable Prometheus exporter:
   ```bash
   export CLAUDE_CODE_ENABLE_TELEMETRY=1
   export OTEL_METRICS_EXPORTER=prometheus
   source ~/.zshrc  # or ~/.bashrc
   ```

2. Docker and Docker Compose installed

**Start Dashboard Stack**:

```bash
cd .agent/grafana
docker compose up -d
```

**Access Dashboard**:
- **Grafana**: http://localhost:3333 (admin/admin)
- **Prometheus**: http://localhost:9092
- **Dashboard**: Dashboards → "Navigator - Claude Code Metrics"

**What's Included**:
- Prometheus scraping Claude Code metrics (port 9464)
- Grafana with pre-provisioned Navigator dashboard
- Auto-configured data source
- 10-panel dashboard with all key metrics

**Ports** (configurable in `docker-compose.yml`):
- Grafana: 3333 (avoid conflicts with dev servers on 3000/3001)
- Prometheus: 9092 (avoid conflicts with other Prometheus instances)

**Complete setup guide**: See `.agent/grafana/README.md`

### Dashboard Panels Explained

The pre-provisioned dashboard includes 10 panels:

**Row 1 - Overview**:
1. **Token Usage (Cumulative)** - All token types over time with legend
2. **Cache Hit Rate** - Gauge (0-100%, green >60%)
3. **Total Session Cost** - USD with color thresholds
4. **Active Time** - Duration formatted, excludes idle time

**Row 2 - Rates**:
5. **Cost Rate (USD/hour)** - Spending rate by model
6. **Token Rate (tokens/min)** - Usage rate by type

**Row 3 - Stats & Distribution**:
7. **Lines Added** - Total lines of code added
8. **Commits** - Total commits made
9. **Sessions** - Session count
10. **Token Distribution by Model** - Donut chart (Haiku vs Sonnet)

**Key Queries**:
- Cache hit rate: `(cacheRead / (input + cacheCreation)) * 100`
- Token usage: `claude_code_token_usage_total` (cumulative counter)
- Cost rate: `rate(claude_code_cost_usage_total[5m]) * 3600`
- Token rate: `rate(claude_code_token_usage_total[1m]) * 60`

**Dashboard auto-refreshes every 10 seconds** to show real-time metrics.

---

## Related Documentation

- **Official Claude Code Docs**: [Monitoring Usage](https://docs.claude.com/en/docs/claude-code/monitoring-usage)
- **OpenTelemetry Spec**: [OTLP Exporter](https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/protocol/exporter.md)
- **Navigator Session Stats**: `skills/nav-start/scripts/otel_session_stats.py`

---

## Summary

**Setup Time**: 2 minutes
**Benefit**: Real-time session metrics, ROI proof, cache validation
**Required**: Optional (Navigator works without OTel)
**Recommended For**: Teams measuring productivity, organizations tracking costs

**Quick Command**:
```bash
echo 'export CLAUDE_CODE_ENABLE_TELEMETRY=1' >> ~/.zshrc
echo 'export OTEL_METRICS_EXPORTER=console' >> ~/.zshrc
source ~/.zshrc
```

Start your next Claude Code session and Navigator will show real-time statistics.

---

**SOP Created**: 2025-10-20
**Version**: 1.0.0
**Maintained By**: Navigator Plugin
