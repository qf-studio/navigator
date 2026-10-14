// Trip dashboard for the /nav pane: Claude Code's OTel metrics from the Prometheus of
// `.agent/grafana/docker-compose.yml`, today and over 7 days. Pure: register.tsx fetches.

import type { NavTripSpan as TripSpan } from '../../../types'
import { compact } from './palette'

/**
 * `session` is this session's own counters (null when no session id was known); `today` and
 * `week` are machine-wide. `sessionSeen` is false once Prometheus should hold this session's
 * series and does not (TASK-102).
 */
export type Trip = {
  session: TripSpan | null; today: TripSpan; week: TripSpan
  perMinute: number[]; sessionSeen: boolean
}
export type TripResults = Record<string, Record<string, number> | null>

// Not increase(): each session's counters start at their first push, so the first turn's
// usage is never an observed rise, and a laptop asleep across the window edge leaves live
// series without a sample there, which `offset` then misses. Per series: the max in the window
// minus the last sample before it (looking back a day), or the whole max when there is none.
const windowed = (metric: string, range: string, by = '', selector = ''): string => {
  const m = `${metric}${selector}`
  return `sum${by} ((max_over_time(${m}[${range}]) - last_over_time(${m}[1d] offset ${range}))`
    + ` or max_over_time(${m}[${range}]))`
}
const METRICS: Record<string, (range: string, selector: string) => string> = {
  usd: (r, sel) => windowed('claude_code_cost_usage_total', r, '', sel),
  tokens: (r, sel) => windowed('claude_code_token_usage_total', r, ' by (type)', sel),
  commits: (r, sel) => windowed('claude_code_commit_count_total', r, '', sel),
  lines: (r, sel) => windowed('claude_code_lines_of_code_count_total', r, ' by (type)', sel),
  active: (r, sel) => windowed('claude_code_active_time_total', r, '', sel),
}

/** Session ids are UUIDs; anything else is dropped so the value cannot escape the selector. */
export const sessionSelector = (sessionId: string): string =>
  `{session_id="${sessionId.replace(/[^A-Za-z0-9-]/g, '')}"}`

/** The first turns' export lands ~10 s after the turn ends: no verdict before this many turns. */
export const SESSION_SEEN_AFTER_TURNS = 2

/** Tokens per minute over the last two hours, one point per 7.5 minutes. */
export const PER_MINUTE = 'sum(rate(claude_code_token_usage_total[5m])) * 60'
export const PER_MINUTE_SPAN_SEC = 2 * 3600
export const PER_MINUTE_STEP_SEC = 450

const LOOPBACK_RE = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?(\/.*)?$/i

/** The panel reads a Prometheus on this machine only: nothing it fetches leaves the host. */
export const isLoopback = (url: string): boolean => LOOPBACK_RE.test(url)

/**
 * `today.usd`, `week.tokens`, … → PromQL; today is a range back to local midnight. With a
 * session id, `session.*` adds this session's own counters: its series over the week (a
 * session's whole life, counters never reset), so "this session" is exact and the machine-wide
 * spans stay.
 */
export const tripQueries = (
  sinceMidnightSec: number, sessionId?: string,
): Record<string, string> => {
  const spans: [string, string, string][] = [
    ['today', `${Math.max(60, Math.round(sinceMidnightSec))}s`, ''],
    ['week', '7d', ''],
  ]
  if (sessionId !== undefined) spans.push(['session', '7d', sessionSelector(sessionId)])
  return Object.fromEntries(spans.flatMap(([span, range, sel]) =>
    Object.entries(METRICS).map(([name, q]) => [`${span}.${name}`, q(range, sel)])))
}

export const secondsSinceMidnight = (nowMs: number): number => {
  const midnight = new Date(nowMs)
  midnight.setHours(0, 0, 0, 0)
  return Math.floor((nowMs - midnight.getTime()) / 1000)
}

const resultOf = (text: string, kind: 'vector' | 'matrix'): unknown[] | null => {
  try {
    const body = JSON.parse(text) as { status?: string; data?: { resultType?: string; result?: unknown } }
    const result = body.data?.result
    return body.status === 'success' && body.data?.resultType === kind && Array.isArray(result) ? result : null
  } catch {
    return null
  }
}

/** An instant-query vector → value by its `type` label ('' when unlabelled). */
export const parseVector = (text: string): Record<string, number> | null => {
  const result = resultOf(text, 'vector')
  if (result === null) return null
  const out: Record<string, number> = {}
  for (const row of result as { metric?: { type?: string }; value?: [number, string] }[]) {
    const v = Number(row.value?.[1])
    if (Number.isFinite(v)) out[row.metric?.type ?? ''] = (out[row.metric?.type ?? ''] ?? 0) + v
  }
  return out
}

/** The first series of a range query, as numbers. */
export const parseMatrix = (text: string): number[] | null => {
  const series = resultOf(text, 'matrix')?.[0] as { values?: [number, string][] } | undefined
  return series?.values ? series.values.map(([, v]) => Number(v)).filter(Number.isFinite) : null
}

const sum = (r: Record<string, number> | null | undefined): number =>
  Object.values(r ?? {}).reduce((a, b) => a + b, 0)

const spanOf = (results: TripResults, span: string): TripSpan => {
  const tokens = results[`${span}.tokens`] ?? {}
  const read = tokens.cacheRead ?? 0
  const inputSide = (tokens.input ?? 0) + read + (tokens.cacheCreation ?? 0)
  const lineCounts = results[`${span}.lines`] ?? {}
  return {
    usd: sum(results[`${span}.usd`]),
    tokens: sum(tokens),
    cacheHit: inputSide > 0 ? read / inputSide : null,
    commits: Math.round(sum(results[`${span}.commits`])),
    added: Math.round(lineCounts.added ?? 0),
    removed: Math.round(lineCounts.removed ?? 0),
    activeSec: sum(results[`${span}.active`]),
  }
}

/**
 * The trip, or null when Prometheus had nothing to say (stack down, no metrics yet). With
 * `session.*` results, `session` is this session's span and `sessionSeen` is whether it has any
 * tokens, except during the first SESSION_SEEN_AFTER_TURNS turns (`turnsDone`), when the first
 * export may not have landed yet. Without them (no session id) both default to absent / true.
 */
export const buildTrip = (
  results: TripResults, perMinute: number[] | null, probe?: { turnsDone: number },
): Trip | null => {
  const week = spanOf(results, 'week')
  if (week.tokens <= 0 && week.usd <= 0) return null
  const asked = Object.keys(results).some(k => k.startsWith('session.'))
  const session = asked ? spanOf(results, 'session') : null
  const sessionSeen = session === null || (probe?.turnsDone ?? 0) < SESSION_SEEN_AFTER_TURNS
    || session.tokens > 0
  return { session, today: spanOf(results, 'today'), week, perMinute: perMinute ?? [], sessionSeen }
}

export const duration = (sec: number): string => {
  const minutes = Math.floor(sec / 60)
  return minutes < 60 ? `${minutes}m` : `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

export const lines = (added: number, removed: number): string => `+${compact(added)} −${compact(removed)}`

/** `[label, today, week, note]` rows of the panel. */
export const tripRows = (t: Trip): [string, string, string, string][] => {
  const hit = t.today.cacheHit ?? t.week.cacheHit
  return [
    ['cost', `$${t.today.usd.toFixed(2)}`, `$${t.week.usd.toFixed(2)}`, ''],
    ['tokens', compact(t.today.tokens), compact(t.week.tokens), hit === null ? '' : `cache ${Math.round(hit * 100)}%`],
    ['commits', String(t.today.commits), String(t.week.commits), ''],
    ['lines', lines(t.today.added, t.today.removed), lines(t.week.added, t.week.removed), ''],
    ['active', duration(t.today.activeSec), duration(t.week.activeSec), ''],
  ]
}
