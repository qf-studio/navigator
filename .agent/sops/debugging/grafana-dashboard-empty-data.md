# Grafana Dashboard Shows Empty Data

**Issue**: Navigator Grafana dashboard displays empty panels despite Prometheus scraping metrics successfully
**Severity**: Medium
**Affected Version**: v3.1.0 - v4.5.0
**Created**: 2025-11-02
**Status**: ✅ Resolved

---

## Problem Description

Dashboard panels show no data (all zeros or empty):
- Cache Hit Rate: Empty gauge
- Token Usage: Flat line at zero
- Commits, Lines Added/Deleted: All showing zero
- All time series panels: No data

However:
- ✅ Prometheus target is UP (`http://localhost:9092/targets`)
- ✅ Metrics exist in Prometheus (`curl localhost:9092/api/v1/query`)
- ✅ Claude Code exporting metrics (`curl localhost:9464/metrics`)
- ✅ Containers running (grafana, prometheus)

---

## Root Cause

**Datasource configuration mismatch between Grafana versions**

1. **Dashboard used deprecated string format**:
   ```json
   "datasource": "Prometheus"
   ```

2. **Grafana 12.x requires object format with UID**:
   ```json
   "datasource": {
     "type": "prometheus",
     "uid": "PBFA97CFB590B2093"
   }
   ```

3. **Grafana ignores provisioned UID**: Even with `uid: prometheus` in `grafana-datasource.yml`, Grafana auto-generates UID on first startup

---

## Solution

### Quick Fix (Recommended)

The simplest solution is to reset Grafana data volume and let it provision correctly:

```bash
cd .agent/grafana

# Stop containers and remove Grafana data
docker compose down
docker volume rm grafana_grafana-data

# Update dashboard to use object-based datasource format
sed -i '' 's/"datasource": "Prometheus"/"datasource": {"type": "prometheus", "uid": "prometheus"}/g' navigator-dashboard.json

# Start fresh
docker compose up -d
```

This ensures:
1. Grafana respects the provisioned UID (`prometheus`)
2. Dashboard uses correct object-based format
3. All panels connect to datasource properly

### Verify Fix

1. Wait 10 seconds for containers to start
2. Open http://localhost:3333
3. Login (admin/admin)
4. Navigate to **Dashboards** → **Navigator - Claude Code Metrics**
5. Panels should display data within 15 seconds

### Alternative: Update Existing Installation

If you can't reset data (preserving other dashboards):

**Step 1: Find Actual Datasource UID**

```bash
curl -s -u admin:admin http://localhost:3333/api/datasources | python3 -m json.tool | grep '"uid"'
```

**Step 2: Update Dashboard**

```bash
cd .agent/grafana

# Replace string format with object format
sed -i '' 's/"datasource": "Prometheus"/"datasource": {"type": "prometheus", "uid": "YOUR-ACTUAL-UID"}/g' navigator-dashboard.json
```

Replace `YOUR-ACTUAL-UID` with the UID from Step 1.

**Step 3: Reload Dashboard**

```bash
# Force Grafana to reload provisioned dashboard
docker compose restart grafana
```

**Note**: Grafana may cache the old dashboard. If restart doesn't work, use the Quick Fix method.

---

## Prevention

### For New Installations

**Option A: Use Auto-Generated UID** (Recommended)

1. Start Grafana once to let it generate datasource UID
2. Query API to get UID: `curl -s -u admin:admin http://localhost:3333/api/datasources`
3. Update `navigator-dashboard.json` with actual UID
4. Restart Grafana

**Option B: Pre-configure UID** (Advanced)

1. Set UID in `grafana-datasource.yml`:
   ```yaml
   datasources:
     - name: Prometheus
       type: prometheus
       uid: navigator-prometheus  # Custom UID
   ```

2. Delete Grafana data volume:
   ```bash
   docker compose down -v
   ```

3. Update dashboard JSON to use `navigator-prometheus` UID

4. Start fresh:
   ```bash
   docker compose up -d
   ```

**Note**: Option B only works on fresh installations. Existing installations ignore provisioned UIDs.

---

## Verification Commands

### Check Prometheus Target Status
```bash
curl -s http://localhost:9092/api/v1/targets | python3 -m json.tool | grep -A5 '"health"'
```

Expected: `"health": "up"`

### Check Claude Code Metrics Endpoint
```bash
curl -s http://localhost:9464/metrics | grep claude_code_token_usage_total | head -5
```

Expected: Counter values (not all zeros)

### Check Prometheus Data
```bash
curl -s 'http://localhost:9092/api/v1/query?query=claude_code_token_usage_total' | python3 -m json.tool | grep -A3 '"result"'
```

Expected: Non-empty result array

### Check Grafana Datasource
```bash
curl -s -u admin:admin http://localhost:3333/api/datasources | python3 -m json.tool
```

Expected: Datasource with `uid` field

---

## Second cause: the scrape target is down (2026-10-02)

**Symptom**: Grafana and the `/nav` trip panel are empty; `localhost:9464/metrics` serves
`claude_code_*` series, but Prometheus shows the target down with
`lookup host.docker.internal on 127.0.0.11:53: no such host`.

**Cause**: on a custom Docker network some runtimes do not resolve `host.docker.internal`.

**Fix**: `extra_hosts: ["host.docker.internal:host-gateway"]` on the prometheus service (now in
`.agent/grafana/docker-compose.yml`), then `docker compose -f .agent/grafana/docker-compose.yml up -d prometheus`.

**Also check the stack**: Navigator's Prometheus is `navigator-prometheus` on **9092**. Pilot's
stack (`pilot-prometheus`, 9093) scrapes Pilot only and has no Claude Code metrics.

**Expect zeros at first**: `increase()` needs two scrapes with activity between them; history
starts when this Prometheus first scrapes, so "7 days" fills over time.

## Files Modified

1. **`.agent/grafana/grafana-datasource.yml`**:
   - Added `uid: prometheus` (line 7)
   - UID is respected on fresh installations only

2. **`.agent/grafana/navigator-dashboard.json`**:
   - Changed all 13 datasource references from string to object format
   - Updated UIDs to `prometheus` (matches provisioned datasource)

3. **`.agent/grafana/docker-compose.yml`**:
   - No changes required

---

## Related Issues

- **Grafana Breaking Changes**: v10.0+ deprecated string datasource format
- **UID Provisioning**: Grafana only respects provisioned UIDs on fresh installs
- **Dashboard Migration**: All panels must use consistent datasource format

---

## Additional Notes

### Why Grafana Ignores Provisioned UID

Grafana assigns UIDs on datasource creation. Once created, the UID cannot be changed via provisioning. To use a custom UID:

1. Delete datasource: `docker compose down -v`
2. Provision with desired UID
3. Start Grafana: `docker compose up -d`

### Dashboard Provisioning Best Practice

Always use object format with explicit UID:

```json
{
  "datasource": {
    "type": "prometheus",
    "uid": "${DS_PROMETHEUS}"  // Use variable for portability
  }
}
```

Or discover UID programmatically in provisioning script.

---

## Testing

Tested on:
- **macOS**: 25.0.0 (Darwin)
- **Docker Desktop**: 27.x
- **Grafana**: 12.1.1
- **Prometheus**: latest
- **Claude Code**: 2.0.31

---

**SOP Created**: 2025-11-02
**Version**: 1.0.0
**Maintained By**: Navigator Plugin
