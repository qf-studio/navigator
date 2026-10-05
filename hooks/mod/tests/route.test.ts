import { describe, expect, test } from 'claude-code/testing'

import { firstLine, parseNextAction } from '../ui/status'

import {
  bandText, buildRoute, captureGoal, contentWords, isOffRoute, nextTaskNumber, parseChecklist, parseSteps,
  routeView, waypointText,
} from '../ui/route'

// The shape TASK-84 uses: a numbered work-breakdown table, progress headings marking steps ✅.
const PLAN_DOC = [
  '# TASK-9: Ship it',
  '## Per-op mapping',
  '| 1 | not a step | x |',
  '## Work breakdown (branch `v8`; keep tests green)',
  '| # | Step | Size |',
  '|---|---|---|',
  '| 0 | Baseline: `validate --strict` on main; conformance probes | M |',
  '| 1 | Move mod into the plugin (per layout); rename state | M |',
  '| 5a | prompt.submit group: gate, tier1 | L |',
  '| 5b | tool.call group | M |',
  '| 9 | Docs: CLAUDE.md "Runtime (v8)" table | M |',
  '| 10 | Dogfood (below), bump, tag, CI release | M |',
  '## Progress log',
  '### Step 0 — baseline (2026-10-02) ✅',
  '### Steps 1 + 5a — moved and ported ✅ (parallel forks)',
  '### Step 10 (automated part) — verification matrix ✅',
].join('\n')

describe('next action from a reply', () => {
  test('the first sentence of the first line, not the whole line', () => {
    expect(firstLine('**Done.** Committed as `ad0c80b`, unreleased. Site is live.')).toBe('Done.')
    expect(firstLine('No files changed by me this turn. The working-tree change in x is not mine.'))
      .toBe('No files changed by me this turn.')
    expect(firstLine('v8.2.1 is out, e.g. the fix shipped')).toBe('v8.2.1 is out, e.g. the fix shipped')
    expect(firstLine('- open `/nav`, press `d` then `l`')).toBe('open `/nav`, press `d` then `l`')
    expect(parseNextAction('Phase: IMPL\nNext Action: run tests. then commit')).toBe('run tests. then commit')
  })
})

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
  test('steps: a checklist wins, else the plan table with ✅ progress headings', () => {
    expect(parseSteps('- [x] a\n- [ ] b\n## Work breakdown\n| 1 | c | S |')).toEqual([
      { label: 'a', done: true }, { label: 'b', done: false },
    ])
    expect(parseSteps(PLAN_DOC)).toEqual([
      { id: '0', label: 'Baseline: validate --strict on main', done: true },
      { id: '1', label: 'Move mod into the plugin', done: true },
      { id: '5a', label: 'prompt.submit group: gate, tier1', done: true },
      { id: '5b', label: 'tool.call group', done: false },
      { id: '9', label: 'Docs: CLAUDE.md "Runtime" table', done: false },
      { id: '10', label: 'Dogfood, bump, tag, CI release', done: false }, // "(automated part)" is partial
    ])
  })
  test('steps: a numbered list under a plan heading; ✅ or strike-through marks done', () => {
    const doc = '## Notes\n1. not a step\n## Implementation plan\n1. Write the parser ✅\n2. ~~Drop the panel~~\n3. Ship it\n## Risks\n4. none'
    expect(parseSteps(doc)).toEqual([
      { id: '1', label: 'Write the parser', done: true },
      { id: '2', label: 'Drop the panel', done: true },
      { id: '3', label: 'Ship it', done: false },
    ])
    expect(parseSteps('# Just prose\nNothing planned.')).toEqual([])
  })
  test('steps: long labels are capped for the band', () => {
    const [step] = parseSteps(`## Steps\n1. ${'word '.repeat(30)}`)
    expect(step?.label.length).toBeLessThanOrEqual(60)
    expect(step?.label.endsWith('…')).toBe(true)
  })
  test('route view shows the whole route when it fits, else folds early passed steps', () => {
    const route = buildRoute(parseSteps(PLAN_DOC), null)
    expect(routeView(route, 16)).toEqual({ earlier: 0, shown: route, more: 0 })
    const view = routeView(route, 3)
    expect(view.earlier).toBe(2)
    expect(view.shown.map(w => [w.id, w.state])).toEqual([['5a', 'done'], ['5b', 'current'], ['9', 'todo']])
    expect(view.more).toBe(1)
    const arrived = routeView(route.map(w => ({ ...w, state: 'done' as const })), 3)
    expect([arrived.earlier, arrived.shown.map(w => w.id), arrived.more]).toEqual([3, ['5b', '9', '10'], 0])
    expect(waypointText(view.shown[1]!)).toBe('● 5b  tool.call group')
    expect(waypointText(view.shown[2]!)).toBe('○ 9   Docs: CLAUDE.md "Runtime" table')
    expect(waypointText(buildRoute([], 'IMPL')[0]!)).toBe('✓ research')
  })
  test('off route needs substance and zero shared vocabulary; word stems count as shared', () => {
    const dest = contentWords('Ship the route view TASK-85 research impl')
    expect(isOffRoute('draft a threads reply for the marketing audience', dest)).toBe(true)
    expect(isOffRoute('yes go ahead', dest)).toBe(false)
    expect(isOffRoute('fix the routing bug in the pane rendering code', dest)).toBe(false)
    expect(isOffRoute('anything at all here goes', new Set())).toBe(false)
  })
  test('band follows "<state>: <what>" in every state', () => {
    const base = { label: 'TASK-84', waypoint: 'verify', position: 3, total: 5, offRoute: null, lowFuel: false, ctxPercent: 42 }
    expect(bandText(base, 120)).toBe('nav · TASK-84 · ● 3/5 verify · 3 legs left')
    expect(bandText({ ...base, position: 5 }, 120)).toBe('nav · TASK-84 · ● 5/5 verify · last leg')
    expect(bandText({ ...base, lowFuel: true, ctxPercent: 72 }, 120)).toBe('low fuel 72% · compact after this leg · TASK-84 · ● 3/5 verify · 3 legs left')
    expect(bandText({ ...base, offRoute: 'threads feedback' }, 120)).toBe('off route: threads feedback · /nav to park or go back')
    expect(bandText({ ...base, label: null, waypoint: null }, 120)).toBe('')
    expect(bandText({ ...base, label: null, waypoint: null, lowFuel: true, ctxPercent: null }, 120)).toBe('low fuel · compact soon')
    expect(bandText(base, 20)).toBe('nav · TASK-84 · ● 3…')
  })
  test('next task number', () => {
    expect(nextTaskNumber(['TASK-84-x.md', 'TASK-9.md', 'README.md'])).toBe(85)
    expect(nextTaskNumber([])).toBe(1)
  })
})
