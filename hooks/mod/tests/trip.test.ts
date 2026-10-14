import { describe, expect, test } from 'claude-code/testing'

import {
  PROBE, SESSION_SEEN_AFTER_TURNS, buildTrip, duration, isLoopback, lines, parseMatrix, parseVector,
  perMinuteQuery, producedLine, sessionSelector, tripQueries,
} from '../ui/trip'

const vector = (rows: [Record<string, string>, number][]) => JSON.stringify({
  status: 'success',
  data: { resultType: 'vector', result: rows.map(([metric, v]) => ({ metric, value: [1, String(v)] })) },
})
const matrix = (values: number[]) => JSON.stringify({
  status: 'success',
  data: { resultType: 'matrix', result: [{ metric: {}, values: values.map((v, i) => [i, String(v)]) }] },
})
const ID = '596354cb-02ae-48a9-944b-3624ce22aeaa'

describe('session card model', () => {
  test('queries: one per metric for this session alone, max over its life minus the last sample before', () => {
    const q = tripQueries(ID)
    const w = (m: string) =>
      `(max_over_time(${m}[7d]) - last_over_time(${m}[1d] offset 7d)) or max_over_time(${m}[7d])`
    expect(Object.keys(q)).toEqual(['usd', 'tokens', 'commits', 'lines', 'active'])
    expect(q.usd).toBe(`sum (${w(`claude_code_cost_usage_total{session_id="${ID}"}`)})`)
    expect(q.tokens).toBe(`sum by (type) (${w(`claude_code_token_usage_total{session_id="${ID}"}`)})`)
    expect(PROBE).toBe(`sum (${w('claude_code_token_usage_total')})`) // the stack, not the session
    expect(perMinuteQuery(ID)).toBe(`sum(rate(claude_code_token_usage_total{session_id="${ID}"}[5m])) * 60`)
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
  test('vector and matrix parsing; anything else is null', () => {
    expect(parseVector(vector([[{ type: 'input' }, 10], [{ type: 'output' }, 2.5]]))).toEqual({ input: 10, output: 2.5 })
    expect(parseVector(vector([[{}, 4.12]]))).toEqual({ '': 4.12 })
    expect(parseVector('not json')).toBeNull()
    expect(parseVector(JSON.stringify({ status: 'error' }))).toBeNull()
    expect(parseMatrix(matrix([1, 2, 3]))).toEqual([1, 2, 3])
    expect(parseMatrix('{}')).toBeNull()
  })
  test('the trip is this session: its span, seen when it has tokens, after a grace of two turns', () => {
    const trip = buildTrip({
      usd: { '': 4.12 },
      tokens: { input: 100_000, output: 50_000, cacheRead: 1_800_000, cacheCreation: 150_000 },
      commits: { '': 6 }, lines: { added: 820, removed: 214 }, active: { '': 7800 },
    }, [1, 2], 5)
    expect(trip.session).toEqual({ usd: 4.12, tokens: 2_100_000, cacheHit: 1_800_000 / 2_050_000, commits: 6, added: 820, removed: 214, activeSec: 7800 })
    expect(trip.perMinute).toEqual([1, 2])
    expect(trip.sessionSeen).toBe(true)
    const at = (tokens: Record<string, number> | null, turnsDone: number) => buildTrip({ tokens }, null, turnsDone)
    expect(at({}, 5).sessionSeen).toBe(false) // Prometheus answered: no series for this session
    expect(at(null, 5).sessionSeen).toBe(false) // the query failed: not seen either
    expect(at({}, SESSION_SEEN_AFTER_TURNS - 1).sessionSeen).toBe(true) // too early to tell
    expect(at({}, SESSION_SEEN_AFTER_TURNS).sessionSeen).toBe(false)
    expect(at({}, 5).session.tokens).toBe(0)
  })
  test('the second line is what the session produced', () => {
    const span = { usd: 4.12, tokens: 2_100_000, cacheHit: 0.91, commits: 6, added: 820, removed: 214, activeSec: 7800 }
    expect(producedLine(span)).toBe('6 commits · +820 −214 · 2h 10m active')
    expect(producedLine({ ...span, commits: 1, added: 5100, removed: 1900, activeSec: 59 })).toBe('1 commit · +5.1K −1.9K · 0m active')
    expect(duration(3 * 3600)).toBe('3h 0m')
    expect(lines(5100, 1900)).toBe('+5.1K −1.9K')
  })
})
