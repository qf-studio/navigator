import { describe, expect, test } from 'claude-code/testing'

import type { NavRouteReport, NavRouteStep } from '../../../types'
import { bandText, parseRouteSection } from '../ui/route'
import {
  bandCounts, bandLeg, bashTouchesTickets, cardLines, currentStep, hasTicket, legPromptOf, parseRouteOutput,
  phaseHint, phaseTitle, progressText, routesHint, rowCount, shortState, sideText, sourceText, stepMark,
  wantTickets,
} from '../ui/roadmap'

const step = (number: string, kind: string, over: Partial<NavRouteStep> = {}): NavRouteStep => ({
  key: number, number, text: `Do thing ${number}.`, ticket: 'Not filed', state: kind, kind, changed: '', ...over,
})
const report = (over: Partial<NavRouteReport> = {}): NavRouteReport => ({
  doc: { path: '.agent/roadmaps/r.md', id: '', title: 'The roadmap', kind: 'roadmap' },
  goal: 'A goal.', source: 's', github: true,
  phases: [
    { title: 'Phase 1: Start', done: 2, total: 2, steps: [step('1', 'done'), step('2', 'done')] },
    { title: 'Phase 2: Middle', done: 1, total: 4, steps: [
      step('3', 'done'), step('4', 'queue', { ticket: 'PR #9' }), step('5', 'next', { ticket: 'TASK-7 · #8' }), step('6', 'blocked'),
    ] },
    { title: 'End', done: 0, total: 1, steps: [step('7', 'later')] },
  ],
  side: [step('', 'queue', { key: 'side:1' }), step('', 'done', { key: 'side:2' })],
  queue: [{ ticket: 'PR #9', text: 'Do thing 4.' }], waits: ['Review PR #9: Do thing 4.'],
  done: 3, total: 7, at: Date.UTC(2026, 10, 15, 14, 3), ...over,
})

describe('route card model', () => {
  test('script output: a report with its list; an error keeps the list; junk is nothing', () => {
    const raw = {
      doc: { path: 'a.md', id: 'TASK-1', title: 'T', kind: 'task' }, goal: 'g', source: 's', github: true,
      phases: [{ title: 'P', done: 0, total: 1, steps: [{ key: '1', number: '1', text: 'x y', ticket: '#1', state: 'Next', kind: 'next', changed: '' }, { nope: 1 }] }],
      side: [], queue: [{ ticket: '#1', text: 'x y' }], waits: ['w', 3], done: 0, total: 1,
      routes: [{ path: 'a.md', id: 'TASK-1', title: 'T', kind: 'task', has_route: true, done: 0, total: 1, active: true }, { title: 'no path' }],
    }
    const out = parseRouteOutput(JSON.stringify(raw), 5)
    expect(out.error).toBeNull()
    expect(out.report?.phases[0]?.steps).toHaveLength(1)
    expect(out.report?.waits).toEqual(['w'])
    expect(out.report?.at).toBe(5)
    expect(out.routes).toEqual([{ path: 'a.md', id: 'TASK-1', title: 'T', kind: 'task', hasRoute: true, done: 0, total: 1, active: true }])
    const failed = parseRouteOutput(JSON.stringify({ error: 'step 4 has no plain line', routes: raw.routes }), 5)
    expect([failed.report, failed.error, failed.routes.length]).toEqual([null, 'step 4 has no plain line', 1])
    expect(parseRouteOutput('Traceback', 5)).toEqual({ report: null, routes: [], error: null })
    expect(parseRouteOutput('[1]', 5)).toEqual({ report: null, routes: [], error: null })
  })
  test('lines: each phase one line, the open phase with its steps', () => {
    const lines = cardLines(report(), 6)
    expect(lines.map(l => (l.type === 'phase' ? `${l.mark} ${l.title} ${l.count}` : l.type === 'step' ? l.step.number : l.type)))
      .toEqual(['✓ Start 2/2', '● Middle 1/4', '3', '4', '5', '6', '○ End 0/1'])
  })
  test('lines: a long open phase keeps the last done step and folds the tail', () => {
    const lines = cardLines(report(), 2)
    expect(lines.map(l => (l.type === 'step' ? l.step.number : l.type === 'more' ? `+${l.count}` : l.type)))
      .toEqual(['phase', 'phase', '3', '4', '+2', 'phase'])
  })
  test('lines, compact: the open phase only, with its open steps; a hint says where it sits', () => {
    const lines = cardLines(report(), 3, true)
    expect(lines.map(l => (l.type === 'fold' ? `${l.mark} ${l.text}` : l.type === 'step' ? l.step.number : l.type)))
      .toEqual(['phase', '4', '5', '6'])
    expect(phaseHint(report())).toBe('phase 2 of 3')
    expect(phaseHint(report({ phases: [report().phases[1]!] }))).toBe('')
    expect(['queue', 'work', 'next', 'blocked', 'later', 'done'].map(shortState))
      .toEqual(['queue', 'work', 'next', 'blocked', '', ''])
    const done = report({ phases: [{ title: 'A', done: 1, total: 1, steps: [step('1', 'done')] }, { title: 'B', done: 1, total: 1, steps: [step('2', 'done')] }] })
    expect(cardLines(done, 3, true)).toEqual([{ type: 'fold', mark: '✓', text: '2 phases done' }])
    expect(cardLines(done, 3).every(l => l.type === 'phase' && l.mark === '✓')).toBe(true)
  })
  test('the press is the step marked next, else the first open one', () => {
    expect(currentStep(report())?.number).toBe('5')
    const none = report({ phases: [{ title: 'P', done: 0, total: 2, steps: [step('1', 'queue'), step('2', 'blocked')] }] })
    expect(currentStep(none)?.number).toBe('1')
    expect(legPromptOf(report().doc, currentStep(report())!)).toBe('Do the next leg of "The roadmap": Do thing 5. (TASK-7 · #8)')
    expect(legPromptOf({ ...report().doc, id: 'TASK-3' }, step('2', 'next'))).toBe('Do the next leg of TASK-3: Do thing 2.')
    expect(bandLeg(report())).toEqual({ waypoint: 'Do thing 5.', position: 4, total: 7 })
  })
  test('small texts', () => {
    expect(phaseTitle('Phase 12b — The gate')).toBe('The gate')
    expect(phaseTitle('')).toBe('Steps')
    expect([stepMark('done'), stepMark('work'), stepMark('queue'), stepMark('blocked')]).toEqual(['✓', '●', '●', '○'])
    expect([hasTicket(step('1', 'next')), hasTicket(step('1', 'next', { ticket: 'Operator step' })), hasTicket(step('1', 'next', { ticket: 'TASK-7' }))])
      .toEqual([false, false, true])
    expect(progressText(report())).toBe('3/7 · 4 legs left')
    expect(progressText(report({ done: 6 }))).toBe('6/7 · last leg')
    expect(progressText(report({ done: 7 }))).toBe('7/7 · arrived')
    expect(sideText(report())).toBe('1 open · 1 in the queue')
    expect(sideText(report({ side: [] }))).toBe('')
    expect(sideText(report({ side: [step('', 'done')] }))).toBe('1 done')
    expect(sourceText(report(), 60)).toBe('state from GitHub 15:03')
    expect(sourceText(report({ github: false }), 0)).toBe('state from the checkboxes 14:03')
    expect(bandCounts(report())).toBe('1 in queue · 1 waits')
    expect(bandCounts(report({ queue: [], waits: ['a', 'b'] }))).toBe('2 wait')
    expect(bandCounts(report({ queue: [], waits: [] }))).toBe('')
    expect(bandCounts(null)).toBe('')
    const row = { path: 'a', id: '', title: 't', kind: 'task', hasRoute: true, done: 1, total: 4, active: false }
    expect([rowCount(row), rowCount({ ...row, hasRoute: false })]).toEqual(['1/4', 'no route section'])
    expect(routesHint([row, { ...row, active: true }, row])).toBe('2 of 3')
    expect(routesHint([{ ...row, active: true }])).toBe('')
  })
  test('ticket refresh: never at start, always forced, on open when stale, after a doc edit only to stay GitHub-backed', () => {
    const r = report()
    const path = r.doc.path
    expect(wantTickets('start', null, path, r.at)).toBe(false)
    expect(wantTickets('force', r, path, r.at)).toBe(true)
    expect(wantTickets('open', null, path, r.at)).toBe(true)
    expect(wantTickets('open', r, path, r.at + 59_000)).toBe(false)
    expect(wantTickets('open', r, path, r.at + 61_000)).toBe(true)
    expect(wantTickets('open', r, 'other.md', r.at)).toBe(true) // the selection moved
    expect(wantTickets('open', { ...r, github: false }, path, r.at)).toBe(true)
    expect(wantTickets('docs', r, path, r.at + 999_000)).toBe(true)
    expect(wantTickets('docs', { ...r, github: false }, path, r.at)).toBe(false)
    expect(wantTickets('docs', null, path, r.at)).toBe(false)
  })
  test('a Bash command that can move ticket state', () => {
    for (const cmd of ['gh pr merge 5', 'cd x && gh issue close 3', 'git push origin main', 'git merge feat', 'git pull']) {
      expect(bashTouchesTickets(cmd)).toBe(true)
    }
    for (const cmd of ['git status', 'echo gh', 'ls ghost', 'git commit -m "x"']) expect(bashTouchesTickets(cmd)).toBe(false)
  })
  test('the route section accepts a task document as a step attribute', () => {
    expect(parseRouteSection('## Route\n- [ ] 1. Show the pane. (TASK-111, PR #53, needs 2)\n- [x] 2. Print it. (GH-50)'))
      .toEqual([{ id: '1', label: 'Show the pane.', done: false }, { id: '2', label: 'Print it.', done: true }])
  })
  test('the band keeps the counts: the leg text gives way, then the legs-left count', () => {
    const base = { label: 'TASK-84', waypoint: 'Install the plugin on the build machine.', position: 3, total: 6, offRoute: null, lowFuel: false, ctxPercent: 42, counts: '2 in queue · 1 waits' }
    expect(bandText(base, 120)).toBe('nav · TASK-84 · ● 3/6 Install the plugin on the build machine. · 4 legs left · 2 in queue · 1 waits')
    expect(bandText(base, 80)).toBe('nav · TASK-84 · ● 3/6 Install the plugin o… · 4 legs left · 2 in queue · 1 waits')
    expect(bandText(base, 60)).toBe('nav · TASK-84 · ● 3/6 Install the… · 2 in queue · 1 waits')
    expect(bandText({ ...base, counts: '' }, 40)).toBe('nav · TASK-84 · ● 3/6 Install the plugi…')
  })
})
