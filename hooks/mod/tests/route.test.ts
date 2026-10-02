import { describe, expect, test } from 'claude-code/testing'

import {
  bandText, buildRoute, captureGoal, contentWords, isOffRoute, nextTaskNumber, parseChecklist, routeLine,
} from '../ui/route'

describe('route model', () => {
  test('goal capture: table row, bold, plain; separators ignored', () => {
    expect(captureGoal('| Goal | Ship the route view |\n| Scope | x |')).toBe('Ship the route view')
    expect(captureGoal('**Goal**: Fix the flaky test')).toBe('Fix the flaky test')
    expect(captureGoal('Goal: tighten the band')).toBe('tighten the band')
    expect(captureGoal('|---|---|')).toBeNull()
    expect(captureGoal('no goal here')).toBeNull()
  })
  test('route from checklist, else phases; complete counts as arrived', () => {
    expect(buildRoute(parseChecklist('- [x] a\n- [ ] b\n- [ ] c'), 'IMPL').map(w => w.state))
      .toEqual(['done', 'current', 'todo'])
    expect(buildRoute([], 'VERIFY').map(w => w.state)).toEqual(['done', 'done', 'current', 'todo'])
    expect(buildRoute([], 'COMPLETE').every(w => w.state === 'done')).toBe(true)
    expect(buildRoute([], null).every(w => w.state === 'todo')).toBe(true)
  })
  test('route line shortens labels before dropping them', () => {
    const route = buildRoute(parseChecklist('- [x] collect the evidence\n- [ ] add one more surface\n- [ ] ship'), null)
    expect(routeLine(route, 80)).toBe('✓ collect the evidence ── ● add one more surface ── ○ ship')
    expect(routeLine(route, 30).length).toBeLessThanOrEqual(30)
    expect(routeLine(route, 5)).toBe('✓ ● ○')
  })
  test('off route needs substance and zero shared vocabulary; word stems count as shared', () => {
    const dest = contentWords('Ship the route view TASK-85 research impl')
    expect(isOffRoute('draft a threads reply for the marketing audience', dest)).toBe(true)
    expect(isOffRoute('yes go ahead', dest)).toBe(false)
    expect(isOffRoute('fix the routing bug in the pane rendering code', dest)).toBe(false)
    expect(isOffRoute('anything at all here goes', new Set())).toBe(false)
  })
  test('band stays one quiet line', () => {
    expect(bandText({ destination: null, waypoint: null, offRoute: false, lowFuel: false }, 80)).toBe('')
    expect(bandText({ destination: 'Ship v8', waypoint: 'verify', offRoute: false, lowFuel: true }, 80))
      .toBe('→ Ship v8 · verify · compact soon')
    expect(bandText({ destination: 'Ship v8', waypoint: 'verify', offRoute: true, lowFuel: true }, 80))
      .toBe('⚠ off route · /nav')
  })
  test('next task number', () => {
    expect(nextTaskNumber(['TASK-84-x.md', 'TASK-9.md', 'README.md'])).toBe(85)
    expect(nextTaskNumber([])).toBe(1)
  })
})
