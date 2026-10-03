import { describe, expect, test } from 'claude-code/testing'

import {
  NO_PACE, etaText, fanOutText, judgeEffect, judgeTally, labelEntry, labelFromVerdict, recordPace, trailLine,
  withLabel,
} from '../ui/nav'
import type { NavJudge } from '../../../types'
import { PALETTE, areaColors, brailleArea, dimHex, gradient, lerpHex, sparkColor } from '../ui/palette'

describe('pane model', () => {
  test('eta: legs only until a leg is done, then legs × turns per leg × ms per turn', () => {
    expect(etaText(5, NO_PACE)).toBe('5 legs left')
    expect(etaText(1, NO_PACE)).toBe('last leg')
    let p = recordPace(NO_PACE, 120_000, null)
    expect(etaText(5, p)).toBe('5 legs left')
    p = recordPace(p, 180_000, 2) // the leg just left took 2 turns
    expect(etaText(5, p)).toBe('eta ~25m · 5 legs left') // 5 × 2 × 150 s
    expect(etaText(0, p)).toBe('0 legs left')
    p = recordPace(p, 0, null) // a zero-length turn is not a sample
    expect(p.turnMs).toEqual([120_000, 180_000])
    expect(etaText(30, p)).toBe('eta ~2h 30m · 30 legs left')
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
  test('a flat sparkline is dim; one with movement takes the accent', () => {
    expect(sparkColor([])).toBe(PALETTE.dim)
    expect(sparkColor([0, 0, 0])).toBe(PALETTE.dim)
    expect(sparkColor([5, 5, 6])).toBe(PALETTE.accent)
  })
  test('fan-out verdict follows the turn in progress, else the last one', () => {
    expect(fanOutText({ total: 9, docs: 9, turnTotal: 0, turnDocs: 0, lastTurnTotal: 3, lastTurnDocs: 0 })).toBe('use an Agent')
    expect(fanOutText({ total: 9, docs: 9, turnTotal: 1, turnDocs: 1, lastTurnTotal: 3, lastTurnDocs: 0 })).toBe('fan-out ok')
  })
})

describe('braille area (grom port)', () => {
  test('shape: rows × width cells, blank when empty, right-aligned when short', () => {
    expect(brailleArea([], 4, 2)).toEqual(['    ', '    '])
    const rows = brailleArea([1, 2, 3, 4, 5, 6, 7, 8], 4, 2)
    expect(rows).toHaveLength(2)
    expect(rows.every(r => [...r].length === 4)).toBe(true)
    expect(rows[1]!.trim().length).toBeGreaterThan(0) // the bottom row always has dots
    expect(rows[1]!.endsWith('⣿')).toBe(true) // the max on the right fills its cell
    expect(rows[0]!.startsWith(' ')).toBe(true) // the min on the left stays low
    expect(brailleArea([5, 5], 4, 1)[0]!.slice(0, 3)).toBe('   ') // two values → right edge only
  })
  test('gaps and flat series', () => {
    expect(brailleArea([NaN, NaN], 1, 1)).toEqual([' '])
    expect(brailleArea([3, 3, 3, 3], 2, 1)[0]!.trim().length).toBe(2) // flat positive → half height
  })
  test('gradient and dim', () => {
    expect(dimHex('#7eb8da', 0)).toBe('#000000')
    expect(dimHex('#7eb8da', 1)).toBe('#7eb8da')
    expect(lerpHex('#000000', '#ffffff', 0.5)).toBe('#7f7f7f')
    expect(gradient(['#7eb8da'], 1)).toEqual(['#7eb8da'])
    expect(gradient(['#000000', '#ffffff'], 3)).toEqual(['#000000', '#7f7f7f', '#ffffff'])
    const c = areaColors('#7eb8da', 2)
    expect(c).toHaveLength(2)
    expect(c[0]).toBe(dimHex('#7eb8da', 0.75)) // top brightest
    expect(c[1]).toBe(dimHex('#7eb8da', 0.35))
  })
})

describe('judge trail and labels (TASK-86)', () => {
  const decision: NavJudge = {
    verdict: 'task · substantial · unclear', effect: 'brief shown', override: null, model: 'jev-1.13.0',
    latencyMs: 400, text: 'make the onboarding better\nsecond line', at: Date.UTC(2026, 9, 3, 12, 3),
  }
  test('a confirmed verdict becomes a judge_label.py label', () => {
    expect(labelFromVerdict('task · substantial · unclear')).toEqual({ tier: 'TASK', task: true, ambiguous: true })
    expect(labelFromVerdict('task · large · clear')).toEqual({ tier: 'TASK', task: true, ambiguous: false })
    expect(labelFromVerdict('task · small · clear')).toEqual({ tier: 'DIRECT', task: true, ambiguous: false })
    expect(labelFromVerdict('task · loop · substantial')).toEqual({ tier: 'LOOP', task: true, ambiguous: false })
    expect(labelFromVerdict('chat')).toEqual({ tier: 'DIRECT', task: false, ambiguous: false })
    const e = labelEntry(decision, 'confirmed', 'navigator')
    expect(e).toMatchObject({ text: decision.text, tier: 'TASK', task: true, ambiguous: true, project: 'navigator', source: 'pane', judged: decision.verdict })
    expect(e.at).toBe('2026-10-03T12:03:00.000Z')
    expect(labelEntry(decision, 'disputed', 'navigator')).toMatchObject({ tier: null, task: null, ambiguous: null, disputed: true })
  })
  test('the label file is created, deduped by prompt text, and survives a malformed file', () => {
    const first = withLabel(null, labelEntry(decision, 'disputed', 'p'))
    const doc = JSON.parse(first) as { _doc: string; prompts: { tier: unknown }[] }
    expect(doc._doc).toContain('judge_label.py')
    expect(doc.prompts).toHaveLength(1)
    expect(doc.prompts[0]?.tier).toBeNull()
    const second = JSON.parse(withLabel(first, labelEntry(decision, 'confirmed', 'p'))) as { prompts: { tier: unknown }[] }
    expect(second.prompts).toHaveLength(1) // same text: replaced, not appended
    expect(second.prompts[0]?.tier).toBe('TASK')
    const other = JSON.parse(withLabel(first, labelEntry({ ...decision, text: 'another' }, 'confirmed', 'p'))) as { prompts: unknown[] }
    expect(other.prompts).toHaveLength(2)
    expect(JSON.parse(withLabel('{not json', labelEntry(decision, 'confirmed', 'p'))).prompts).toHaveLength(1)
  })
  test('a trail line: time, verdict, effect, the first line of the prompt, the label mark', () => {
    const line = trailLine(decision, 72)
    expect(line).toMatch(/^\d\d:\d\d · task · substantial · unclear  "make the onboarding better"$/)
    expect(trailLine({ ...decision, label: 'confirmed' }, 72)).toContain(' ✓ task')
    expect(trailLine({ ...decision, label: 'disputed' }, 72)).toContain(' ✗ task')
    expect([...trailLine({ ...decision, text: 'x'.repeat(200) }, 60)].length).toBeLessThanOrEqual(60)
  })
})
