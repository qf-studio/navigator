// Trip dashboard for the /nav pane: Claude Code's OTel metrics from the Prometheus of
// `.agent/grafana/docker-compose.yml`, today and over 7 days. Pure: register.tsx fetches.

import type { NavTripSpan as TripSpan } from '../../../types'
import { compact } from './palette'

export type Trip = { today: TripSpan; week: TripSpan; perMinute: number[] }
export type TripResults = Record<string, Record<string, number> | null>

const METRICS = {
  usd: 'sum(increase(claude_code_cost_usage_total[R]))',
  tokens: 'sum by (type) (increase(claude_code_token_usage_total[R]))',
  commits: 'sum(increase(claude_code_commit_count_total[R]))',
  lines: 'sum by (type) (increase(claude_code_lines_of_code_count_total[R]))',
  active: 'sum(increase(claude_code_active_time_total[R]))',
} as const

/** Tokens per minute over the last two hours, one point per 7.5 minutes. */
export const PER_MINUTE = 'sum(rate(claude_code_token_usage_total[5m])) * 60'
export const PER_MINUTE_SPAN_SEC = 2 * 3600
export const PER_MINUTE_STEP_SEC = 450

/** `today.usd`, `week.tokens`, … → PromQL; today is a range back to local midnight. */
export const tripQueries = (sinceMidnightSec: number): Record<string, string> => {
  const spans = { today: `${Math.max(60, Math.round(sinceMidnightSec))}s`, week: '7d' }
  return Object.fromEntries(Object.entries(spans).flatMap(([span, range]) =>
    Object.entries(METRICS).map(([name, q]) => [`${span}.${name}`, q.replace('R', range)])))
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

/** The trip, or null when Prometheus had nothing to say (stack down, no metrics yet). */
export const buildTrip = (results: TripResults, perMinute: number[] | null): Trip | null => {
  const week = spanOf(results, 'week')
  if (week.tokens <= 0 && week.usd <= 0) return null
  return { today: spanOf(results, 'today'), week, perMinute: perMinute ?? [] }
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
