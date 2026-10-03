import { describe, expect, test } from 'claude-code/testing'

import { NO_PACE, etaText, fanOutText, judgeEffect, judgeTally, recordPace } from '../ui/nav'

describe('pane model', () => {
  test('eta: legs only until a leg is done, then legs × turns per leg × ms per turn', () => {
    expect(etaText(5, NO_PACE)).toBe('5 legs')
    expect(etaText(1, NO_PACE)).toBe('1 leg')
    let p = recordPace(NO_PACE, 120_000, null)
    expect(etaText(5, p)).toBe('5 legs')
    p = recordPace(p, 180_000, 2) // the leg just left took 2 turns
    expect(etaText(5, p)).toBe('eta ~25m · 5 legs') // 5 × 2 × 150 s
    expect(etaText(0, p)).toBe('0 legs')
    p = recordPace(p, 0, null) // a zero-length turn is not a sample
    expect(p.turnMs).toEqual([120_000, 180_000])
    expect(etaText(30, p)).toBe('eta ~2h 30m · 30 legs')
  })
  test('effect reads the injected context', () => {
    expect(judgeEffect(null)).toBe('direct')
    expect(judgeEffect('WORKFLOW CHECK\n│ Loop trigger: YES │')).toBe('loop mode')
    expect(judgeEffect('🧭 NAV-BRIEF: ambiguous')).toBe('brief shown')
    expect(judgeEffect('│ Mode: TASK │')).toBe('task mode')
  })
  test('tally lines from the state section', () => {
    expect(judgeTally(null)).toEqual(['no judge calls recorded'])
    const lines = judgeTally({ calls: 10, failed: 1, latency_last_ms: 400, latency_max_ms: 900,
      axes: { ambiguity: { agreed: 2, overridden: 6, undecided: 1 }, loop: { agreed: 9 } } })
    expect(lines[0]).toBe('10 calls · 1 failed · latency 400 ms, max 900 ms')
    expect(lines).toContain('unclear     agreed 2 · overrode 6 · undecided 1 · jev over rule 75%')
    expect(lines).toContain('loop        agreed 9 · overrode 0 · undecided 0 · jev over rule 0%')
  })
  test('fan-out verdict follows the turn in progress, else the last one', () => {
    expect(fanOutText({ total: 9, docs: 9, turnTotal: 0, turnDocs: 0, lastTurnTotal: 3, lastTurnDocs: 0 })).toBe('use an Agent')
    expect(fanOutText({ total: 9, docs: 9, turnTotal: 1, turnDocs: 1, lastTurnTotal: 3, lastTurnDocs: 0 })).toBe('fan-out ok')
  })
})
