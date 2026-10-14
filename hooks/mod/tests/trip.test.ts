import { describe, expect, test } from 'claude-code/testing'

import {
  SESSION_SEEN_AFTER_TURNS, buildTrip, duration, isLoopback, lines, parseMatrix, parseVector, secondsSinceMidnight,
  sessionSelector, tripQueries, tripRows,
} from '../ui/trip'

const vector = (rows: [Record<string, string>, number][]) => JSON.stringify({
  status: 'success',
  data: { resultType: 'vector', result: rows.map(([metric, v]) => ({ metric, value: [1, String(v)] })) },
})
const matrix = (values: number[]) => JSON.stringify({
  status: 'success',
  data: { resultType: 'matrix', result: [{ metric: {}, values: values.map((v, i) => [i, String(v)]) }] },
})

describe('trip dashboard model', () => {
  test('queries: one per metric and span, max in the window minus the last sample before it, by type where split', () => {
    const q = tripQueries(3600)
    const w = (m: string, r: string) =>
      `(max_over_time(${m}[${r}]) - last_over_time(${m}[1d] offset ${r})) or max_over_time(${m}[${r}])`
    expect(q['today.usd']).toBe(`sum (${w('claude_code_cost_usage_total', '3600s')})`)
    expect(q['week.tokens']).toBe(`sum by (type) (${w('claude_code_token_usage_total', '7d')})`)
    expect(q['week.lines']).toBe(`sum by (type) (${w('claude_code_lines_of_code_count_total', '7d')})`)
    expect(Object.keys(q)).toHaveLength(10)
    expect(tripQueries(0)['today.usd']).toContain('[60s]') // just after midnight: a 1-minute floor
    // With a session id: the same five metrics for this session alone, over its whole life.
    const mine = tripQueries(3600, '596354cb-02ae-48a9-944b-3624ce22aeaa')
    expect(Object.keys(mine)).toHaveLength(15)
    expect(mine['session.usd']).toBe(`sum (${w('claude_code_cost_usage_total{session_id="596354cb-02ae-48a9-944b-3624ce22aeaa"}', '7d')})`)
    expect(mine['today.usd']).toBe(q['today.usd'])
    expect(sessionSelector('x"} or up{a="')).toBe('{session_id="xorupa"}')
  })
  test('only loopback Prometheus URLs are read', () => {
    for (const url of ['http://localhost:9092', 'http://127.0.0.1:9090/', 'https://[::1]:9443', 'http://localhost']) {
      expect(isLoopback(url)).toBe(true)
    }
    for (const url of ['http://prom.internal:9090', 'http://localhost.evil.com', 'http://127.0.0.1.nip.io', 'file:///etc/passwd', 'localhost:9092']) {
      expect(isLoopback(url)).toBe(false)
    }
  })
  test('local midnight', () => {
    const at = new Date(2026, 9, 2, 14, 30, 15).getTime()
    expect(secondsSinceMidnight(at)).toBe(14 * 3600 + 30 * 60 + 15)
  })
  test('vector and matrix parsing; anything else is null', () => {
    expect(parseVector(vector([[{ type: 'input' }, 10], [{ type: 'output' }, 2.5]]))).toEqual({ input: 10, output: 2.5 })
    expect(parseVector(vector([[{}, 4.12]]))).toEqual({ '': 4.12 })
    expect(parseVector('not json')).toBeNull()
    expect(parseVector(JSON.stringify({ status: 'error' }))).toBeNull()
    expect(parseMatrix(matrix([1, 2, 3]))).toEqual([1, 2, 3])
    expect(parseMatrix('{}')).toBeNull()
  })
  test('a trip needs data: no week tokens and no cost → null', () => {
    const empty = buildTrip({}, null)
    expect(empty).toBeNull()
    const trip = buildTrip({
      'today.usd': { '': 4.12 }, 'week.usd': { '': 31.8 },
      'today.tokens': { input: 100_000, output: 50_000, cacheRead: 1_800_000, cacheCreation: 150_000 },
      'week.tokens': { input: 1_000_000, cacheRead: 13_600_000 },
      'today.commits': { '': 6 }, 'week.commits': { '': 41 },
      'today.lines': { added: 820, removed: 214 }, 'week.lines': { added: 5100, removed: 1900 },
      'today.active': { '': 7800 }, 'week.active': { '': 42000 },
    }, [1, 2])
    expect(trip?.today).toEqual({ usd: 4.12, tokens: 2_100_000, cacheHit: 1_800_000 / 2_050_000, commits: 6, added: 820, removed: 214, activeSec: 7800 })
    expect(trip?.perMinute).toEqual([1, 2])
    expect(trip?.session).toBeNull() // no session queries ran
    expect(trip?.sessionSeen).toBe(true)
  })
  test('this session (TASK-102): its own span, seen when it has tokens, after a grace of two turns', () => {
    const base = { 'week.tokens': { input: 10 }, 'session.usd': { '': 0.73 } }
    const at = (tokens: Record<string, number> | null, turnsDone: number) =>
      buildTrip({ ...base, 'session.tokens': tokens }, null, { turnsDone })
    const seen = at({ input: 2, cacheRead: 50_010 }, 5)
    expect(seen?.session).toEqual({ usd: 0.73, tokens: 50_012, cacheHit: 50_010 / 50_012, commits: 0, added: 0, removed: 0, activeSec: 0 })
    expect(seen?.sessionSeen).toBe(true)
    expect(at({}, 5)?.sessionSeen).toBe(false) // Prometheus answered: no series for this session
    expect(at(null, 5)?.sessionSeen).toBe(false) // the query failed: not seen either
    expect(at({}, SESSION_SEEN_AFTER_TURNS - 1)?.sessionSeen).toBe(true) // too early to tell
    expect(at({}, SESSION_SEEN_AFTER_TURNS)?.sessionSeen).toBe(false)
  })
  test('rows render the draft: cost, tokens + cache, commits, lines, active', () => {
    const span = { usd: 4.12, tokens: 2_100_000, cacheHit: 0.91, commits: 6, added: 820, removed: 214, activeSec: 7800 }
    const rows = tripRows({ session: null, today: span, week: { ...span, usd: 31.8, cacheHit: null }, perMinute: [], sessionSeen: true })
    expect(rows).toEqual([
      ['cost', '$4.12', '$31.80', ''],
      ['tokens', '2.1M', '2.1M', 'cache 91%'], // today's cache hit, else the week's
      ['commits', '6', '6', ''],
      ['lines', '+820 −214', '+820 −214', ''],
      ['active', '2h 10m', '2h 10m', ''],
    ])
    expect(tripRows({ session: null, today: { ...span, cacheHit: null }, week: span, perMinute: [], sessionSeen: true })[1]?.[3]).toBe('cache 91%')
    expect(duration(59)).toBe('0m')
    expect(duration(3 * 3600)).toBe('3h 0m')
    expect(lines(5100, 1900)).toBe('+5.1K −1.9K')
  })
})
