# TASK-100: Metrics from every session — OTel collector in the stack, pane guard when a session is not scraped

**Status**: ✅ Released — v8.4.0, 2026-10-14; sliced into TASK-101 (stack), TASK-102 (guard + notice), TASK-103 (release), all shipped
**Origin**: 2026-10-14 dogfood: the /nav session card showed `$0.00` "today" in every project.
Cause: Claude Code's `prometheus` exporter binds a fixed port, 9464. Only the first-started
process gets it. With five or six concurrent sessions on this machine, the other sessions
export nothing, silently (mem-087). Prometheus then holds one idle session whose counters do
not move, and the windowed "today" formula (mem-085) correctly reports 0.
**Effort**: M (compose + collector config + docs: S; pane guard + session-start notice in both
runtimes + tests: S–M; live verification on this machine: S)
**Depends on**: nothing open. Docker Desktop with the `.agent/grafana/` stack running.

## Problem

1. **One exporter port for N processes.** `OTEL_METRICS_EXPORTER=prometheus` makes each
   `claude` process serve `:9464`. The bind failure is silent (docs: export errors are
   silent unless `CLAUDE_CODE_OTEL_DIAG_STDERR=1`). The repo documents only this exporter
   (`.agent/grafana/README.md:17-23`, `docs/GRAFANA-DASHBOARD.md`, `scripts/post-install.sh:116-137`
   writes the shell rc), so every user who runs two sessions hits this.
2. **The pane cannot tell.** `refreshTrip` (`hooks/mod/register.tsx:294-332`) runs fleet-wide
   queries only. `buildTrip` (`hooks/mod/ui/trip.ts:104-108`) returns a trip whenever the 7-day
   token sum is positive, so a stale session renders as a confident `$0.00` instead of a warning.
   The mod already has the session id (`io.sessionId`, `register.tsx:119`) and never uses it here.
3. **Nothing warns at session start.** `session_start` probes the judge key and the reply modes
   (`hooks/mod/ops/session_start.ts:62-125`, `hooks/ops/session_start.py:110-150`) but not the
   metrics path.

Verified on 2026-10-14: `lsof -iTCP:9464` showed pid 69880 (a Friday session in another repo);
the exporter on `:9464` listed one `session_id`; the pane's exact today query returned `0` while
the 7-day query returned `$87.15`. Killing 69880 and restarting fixed one session only.

## Acceptance Criteria

### A. Collector in the stack (root cause)
- [ ] `.agent/grafana/docker-compose.yml` gains service `otel-collector`
      (`otel/opentelemetry-collector-contrib`, pinned tag), host ports `4318` (OTLP http) and
      `4317` (OTLP grpc), config mounted from new `.agent/grafana/otel-collector-config.yml`,
      on `navigator-monitoring`, `restart: unless-stopped`.
- [ ] Collector config: `receivers.otlp` (grpc + http) → `exporters.prometheus` on
      `0.0.0.0:8889` with `resource_to_telemetry_conversion.enabled: true` (so `session_id`,
      `user_email`, `terminal_type`, `otel_scope_version` stay labels as today) and
      `metric_expiration` ≥ `1h` (series must outlive a quiet session long enough for the
      15 s scrape; TSDB keeps history for `max_over_time`/`last_over_time`).
- [ ] **Metric names unchanged.** Today the names are `claude_code_cost_usage_total`,
      `claude_code_token_usage_total`, `claude_code_commit_count_total`,
      `claude_code_lines_of_code_count_total`, `claude_code_active_time_total`,
      `claude_code_session_count_total`, labels `type`, `model`, `query_source`, `effort`,
      `skill_name`, `plugin_name`, `session_id`. The collector's exporter appends unit suffixes by
      default (`_USD_total`, `_tokens_total`, `_seconds_total`) — set `add_metric_suffixes: false`
      and restore `_total` with a `metricstransform` regex rename, or whichever combination the
      spike (Verify step 1) proves keeps the names byte-identical. Dashboard JSON and `trip.ts`
      query only names and `type` (research: 0 hits for other labels in the dashboard), so the
      names are the whole compatibility surface.
- [ ] `prometheus.yml`: job `claude-code` targets `otel-collector:8889`; the direct `:9464`
      target stays as job `claude-code-direct` for users who keep the old exporter (one exporter
      per process, never both, so no double count). Both carry `app=claude-code`.
- [ ] Documented env for OTLP, in one place and referenced from the others:
      `CLAUDE_CODE_ENABLE_TELEMETRY=1`, `OTEL_METRICS_EXPORTER=otlp`,
      `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318`,
      `OTEL_METRIC_EXPORT_INTERVAL=10000`; optional `CLAUDE_CODE_OTEL_DIAG_STDERR=1` for debugging.
      Recommend `~/.claude/settings.json` `env` (applies to every project, overrides the shell)
      over the shell rc. `scripts/post-install.sh` stops appending the `console` exporter lines
      and prints the OTLP block instead (or nothing — decide in Approach).
- [ ] `.agent/grafana/README.md` and `docs/GRAFANA-DASHBOARD.md` reconciled: one is the source,
      the other a pointer. Fix the stale "3001" port comment and "10-panel" in
      `skills/nav-init/SKILL.md:44-49,141-145` (13 panels). `nav-init` copies the directory, so
      new projects get the collector for free; verify the copy list includes the new config file.
- [ ] `.agent/sops/integrations/opentelemetry-setup.md`: OTLP-through-collector is the
      recommended path; `prometheus` exporter marked single-session with the mem-087 symptom.

### B. Pane guard + session-start notice (the symptom never hides again)
- [ ] `refreshTrip` adds one instant query
      `max(claude_code_token_usage_total{session_id="<io.sessionId()>"})`. Result → new field
      `NavTrip.sessionSeen: boolean` (`types/index.d.ts:103`). Grace: `false` only after the
      session has completed ≥ 2 turns (the first export lands 10 s after the first turn), so a
      fresh session never flashes the warning.
- [ ] Session card (`register.tsx:755-790`): when `sessionSeen === false`, the today cost
      renders `--` and the line under it reads `this session not in prometheus · see metrics SOP`
      (exact copy decided in IMPL; ≤ 48 cols so the narrow layout holds). `tripRows` and
      `TripSpan.usd` stay numeric; the guard is a boolean, not a nullable cost.
- [ ] `session_start` notice in **both** runtimes, byte-identical: when
      `OTEL_METRICS_EXPORTER=prometheus` is set, append
      `Metrics: prometheus exporter is single-session (port 9464); switch to otlp — .agent/sops/integrations/opentelemetry-setup.md`
      after the judge/modes notices (`session_start.ts:106-125`, `session_start.py:110-131`).
      Deterministic from env only — no `lsof`, no race with the exporter's own bind.
      `scripts/mod_fixtures/lifeops.py` + regenerated `hooks/mod/tests/fixtures/lifeops-session_start.gen.ts`
      (`make mod-gen-check` green).
- [ ] Tests: `hooks/mod/tests/trip.test.ts` (`buildTrip` with `sessionSeen` true/false),
      `hooks/mod/tests/register.test.ts` fetch counts 12 → 13 (`:541,549-554`) and a
      `sessionSeen=false` render case; Python `test_session_start` for the notice; `make test-all`.
- [ ] mem-087 updated: cause + the two fixes + "check `/nav` says session not in prometheus";
      one new decision memory (collector over per-session ports, contradiction: one scrape target
      vs N processes).

### C. Release
- [ ] CHANGELOG + `releases/RELEASE-NOTES-v8.4.0.md`; version bump across the six files;
      `make release-check`; docs site sync (dashboard page + plugin-ops page mention the notice).

## Approach

1. **Spike (30 min, no commit)**: add the collector service and config locally, point this
   machine's env at `http://localhost:4318` in `~/.claude/settings.json`, start two `claude`
   sessions in two repos, scrape `localhost:8889/metrics` and confirm (a) both `session_id`s
   present, (b) metric names identical to the `:9464` output captured today, (c) the pane's
   `today.usd` query returns a rising number from the new job. This settles the
   `add_metric_suffixes` / rename question before any doc is written.
2. Commit A (stack + docs). 3. Commit B (guard + notice + tests). 4. Release 8.4.0.

Decision for `post-install.sh`: it currently appends `OTEL_METRICS_EXPORTER=console` to the
user's rc — a third, unrelated exporter. Replace the append with a printed OTLP block and a link
to the SOP; never edit the rc silently again.

## Won't do
- No `OTEL_EXPORTER_PROMETHEUS_PORT` per-session trick (one port per terminal is not a product).
- No `lsof` probe in session_start (racy: the exporter binds after the hook runs).
- No nullable `TripSpan.usd` — the agent's suggested `--` for an empty cost series is covered by
  `sessionSeen`; an empty cost series with tokens present has not been observed.
- No Pilot changes: Pilot's own `:9091` job is untouched.
- No change to the windowed formula (mem-085); it is correct once every session exports.

## Verify
- Spike checklist above, on this machine, with ≥ 2 concurrent sessions.
- `make test-all` with `NAVIGATOR_MOD_OWNS` unset; `make mod-gen-check`.
- `/nav` in a session that is not exported (set `OTEL_METRICS_EXPORTER=prometheus` while another
  session holds 9464) shows `--` and the guard line; session start shows the notice.
- Grafana dashboard panels non-empty after the switch (names unchanged).

## Refs
- Research 2026-10-14: `navigator-research` map of `.agent/grafana/`, `trip.ts`, `register.tsx`,
  `session_start.*`, tests and docs; `claude-code-guide` on OTLP env vars and defaults
  (`OTEL_METRICS_INCLUDE_SESSION_ID=true` default; export errors silent without
  `CLAUDE_CODE_OTEL_DIAG_STDERR=1`; settings.json `env` overrides the shell).
- Docs: https://code.claude.com/docs/en/monitoring-usage, https://code.claude.com/docs/en/env-vars
- Memories: mem-085 (`increase()` undercounts; windowed formula), mem-087 (port 9464 single-bind).
- Live evidence 2026-10-14: `~/.zshrc:232-234` sets the prometheus exporter; pid 69880 held
  `:9464` since 2026-10-09; Prometheus `today.usd` = 0, `week.usd` = 87.15.
