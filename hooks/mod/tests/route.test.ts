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
  test('band follows "<state>: <what>" in every state', () => {
    const base = { destination: 'Ship v8', waypoint: 'verify', position: 3, total: 5, next: 'run headless matrix', offRoute: null, lowFuel: false }
    expect(bandText(base, 120)).toBe('on route: Ship v8 · ● verify 3/5 · next: run headless matrix')
    expect(bandText({ ...base, lowFuel: true }, 120)).toBe('low fuel: Ship v8 · ● verify 3/5 · compact after this waypoint')
    expect(bandText({ ...base, offRoute: 'threads feedback' }, 120)).toBe('off route: threads feedback · /nav to park or go back')
    expect(bandText({ ...base, destination: null, waypoint: null, next: null }, 120)).toBe('')
    expect(bandText(base, 20)).toBe('on route: Ship v8 ·…')
  })
  test('next task number', () => {
    expect(nextTaskNumber(['TASK-84-x.md', 'TASK-9.md', 'README.md'])).toBe(85)
    expect(nextTaskNumber([])).toBe(1)
  })
})
