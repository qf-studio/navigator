// The /nav route card (TASK-111): the report of skills/nav-route/functions/route_render.py
// (`--format json --with-list`) as the pane shows it. Pure: the hooks module runs the script
// and holds the state; these functions validate its output and decide what to draw. The
// script is the one source of ticket state, so nothing here derives a state.

import type {
  NavRouteDoc, NavRoutePhase, NavRouteReport, NavRouteRow, NavRouteStep,
} from '../../../types'

const isObject = (v: unknown): v is Record<string, unknown> =>
  v !== null && typeof v === 'object' && !Array.isArray(v)
const text = (v: unknown): string => (typeof v === 'string' ? v : '')
const count = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0)
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : [])

const stepOf = (v: unknown): NavRouteStep[] => (!isObject(v) || text(v.text) === '' ? [] : [{
  key: text(v.key), number: text(v.number), text: text(v.text), ticket: text(v.ticket),
  state: text(v.state), kind: text(v.kind), changed: text(v.changed),
}])

const docOf = (v: unknown): NavRouteDoc | null => (!isObject(v) || text(v.path) === '' ? null : {
  path: text(v.path), id: text(v.id), title: text(v.title), kind: text(v.kind) || 'task',
})

const rowOf = (v: unknown): NavRouteRow[] => {
  const doc = docOf(v)
  if (doc === null || !isObject(v)) return []
  return [{
    ...doc, hasRoute: v.has_route === true, done: count(v.done), total: count(v.total),
    active: v.active === true,
  }]
}

export type RouteOutput = { report: NavRouteReport | null; routes: NavRouteRow[]; error: string | null }

/** The script's stdout → a report (null on an error or junk) and the route list. */
export const parseRouteOutput = (stdout: string, atMs: number): RouteOutput => {
  let data: unknown
  try {
    data = JSON.parse(stdout)
  } catch {
    return { report: null, routes: [], error: null }
  }
  if (!isObject(data)) return { report: null, routes: [], error: null }
  const routes = list(data.routes).flatMap(rowOf)
  const doc = docOf(data.doc)
  if (doc === null || typeof data.error === 'string') {
    return { report: null, routes, error: text(data.error) || null }
  }
  const phases: NavRoutePhase[] = list(data.phases).flatMap(p => (!isObject(p) ? [] : [{
    title: text(p.title), done: count(p.done), total: count(p.total),
    steps: list(p.steps).flatMap(stepOf),
  }]))
  return {
    routes,
    error: null,
    report: {
      doc, goal: text(data.goal), source: text(data.source), github: data.github === true,
      phases, side: list(data.side).flatMap(stepOf),
      queue: list(data.queue).flatMap(q => (!isObject(q) ? [] : [{ ticket: text(q.ticket), text: text(q.text) }])),
      waits: list(data.waits).filter((w): w is string => typeof w === 'string'),
      done: count(data.done), total: count(data.total), at: atMs,
    },
  }
}

/** `Phase 2: Release` → `Release`: the card numbers nothing itself. */
export const phaseTitle = (title: string): string =>
  title.replace(/^phase\s+\d+[a-z]?\s*[:.—–-]\s*/i, '').trim() || 'Steps'

const isOpen = (s: NavRouteStep): boolean => s.kind !== 'done'

/** The step the `n` press does: the one marked next, else the first that is not done. */
export const currentStep = (report: NavRouteReport): NavRouteStep | null => {
  const steps = report.phases.flatMap(p => p.steps)
  return steps.find(s => s.kind === 'next') ?? steps.find(isOpen) ?? null
}

export type CardLine =
  | { type: 'phase'; mark: '✓' | '●' | '○'; title: string; count: string }
  | { type: 'fold'; mark: '✓' | '○'; text: string }
  | { type: 'step'; step: NavRouteStep }
  | { type: 'more'; count: number }

const plural = (n: number, word: string): string => `${n} ${word}${n === 1 ? '' : 's'}`

/**
 * The route card's lines: every phase is one line; the first phase with open work also lists
 * its steps. With more steps than `maxSteps` the list keeps the last done step for context,
 * starts there, and folds the tail into "n more". `compact` is the narrow side panel: only
 * the open phase, and only its open steps.
 */
export const cardLines = (report: NavRouteReport, maxSteps: number, compact = false): CardLine[] => {
  const open = report.phases.findIndex(p => p.steps.some(isOpen))
  const perPhase = report.phases.map((phase, i): CardLine[] => {
    const head: CardLine = {
      type: 'phase', mark: phase.done >= phase.total ? '✓' : i === open ? '●' : '○',
      title: phaseTitle(phase.title), count: `${phase.done}/${phase.total}`,
    }
    if (i !== open) return [head]
    const steps = compact ? phase.steps.filter(isOpen) : phase.steps
    const first = steps.findIndex(isOpen)
    const start = steps.length <= maxSteps ? 0
      : Math.min(Math.max(0, first - 1), steps.length - maxSteps)
    const shown = steps.slice(start, start + maxSteps)
    const more = steps.length - start - shown.length
    return [head, ...shown.map((step): CardLine => ({ type: 'step', step })),
      ...(more > 0 ? [{ type: 'more', count: more } as CardLine] : [])]
  })
  if (!compact) return perPhase.flat()
  // The side panel shows the open phase only; `phaseHint` says where it sits among the others.
  if (open < 0) {
    return [{ type: 'fold', mark: '✓', text: `${plural(report.phases.length, 'phase')} done` }]
  }
  return perPhase[open] ?? []
}

/** `phase 2 of 3` for the side panel, where the other phases are not listed; '' for one phase. */
export const phaseHint = (report: NavRouteReport): string => {
  const open = report.phases.findIndex(p => p.steps.some(isOpen))
  return report.phases.length > 1 && open >= 0 ? `phase ${open + 1} of ${report.phases.length}` : ''
}

/** One word for a step's state in the side panel, where a step is one line; '' says nothing. */
export const shortState = (kind: string): string =>
  ({ queue: 'queue', work: 'work', next: 'next', blocked: 'blocked' } as Record<string, string>)[kind] ?? ''

export const stepMark = (kind: string): string =>
  kind === 'done' ? '✓' : kind === 'queue' || kind === 'work' ? '●' : '○'

/** A ticket worth showing: `#50`, `TASK-12 · PR #7`; not the "Not filed" / "Operator step" words. */
export const hasTicket = (step: NavRouteStep): boolean => /[#\d]/.test(step.ticket)

/** The prompt the `n` press submits: the step in plain words with its ticket. */
export const legPromptOf = (doc: NavRouteDoc, step: NavRouteStep): string => {
  const name = doc.id || `"${doc.title}"`
  return `Do the next leg of ${name}: ${step.text}${hasTicket(step) ? ` (${step.ticket})` : ''}`
}

/** `8/9 · last leg`, `2/4 · 2 legs left`, `4/4 · arrived`. */
export const progressText = (report: NavRouteReport): string => {
  const left = report.total - report.done
  const tail = left <= 0 ? 'arrived' : left === 1 ? 'last leg' : `${left} legs left`
  return `${report.done}/${report.total} · ${tail}`
}

/** `1 open · 1 in the queue` for the side tracks; '' when there are none. */
export const sideText = (report: NavRouteReport): string => {
  if (report.side.length === 0) return ''
  const open = report.side.filter(isOpen)
  const queued = open.filter(s => s.kind === 'queue' || s.kind === 'work').length
  if (open.length === 0) return `${report.side.length} done`
  return `${open.length} open${queued > 0 ? ` · ${queued} in the queue` : ''}`
}

/** `state from GitHub 14:03` / `state from the checkboxes 14:03` (local wall clock). */
export const sourceText = (report: NavRouteReport, offsetMinutes: number): string => {
  const local = new Date(report.at + offsetMinutes * 60_000).toISOString().slice(11, 16)
  return `state from ${report.github ? 'GitHub' : 'the checkboxes'} ${local}`
}

/** `2 in queue · 1 waits` for the band; '' when both are zero. */
export const bandCounts = (report: NavRouteReport | null): string => {
  if (report === null) return ''
  return [
    report.queue.length > 0 ? `${report.queue.length} in queue` : null,
    report.waits.length > 0 ? `${report.waits.length} ${report.waits.length === 1 ? 'waits' : 'wait'}` : null,
  ].filter(Boolean).join(' · ')
}

/** The band's leg from the report: the step the press does, as the leg after the done ones. */
export const bandLeg = (report: NavRouteReport): { waypoint: string | null; position: number; total: number } => {
  const step = currentStep(report)
  return { waypoint: step?.text ?? null, position: step === null ? 0 : report.done + 1, total: report.total }
}

/** `1 of 3` when the project has more than one route document; '' otherwise. */
export const routesHint = (routes: readonly NavRouteRow[]): string => {
  const at = routes.findIndex(r => r.active)
  return routes.length > 1 && at >= 0 ? `${at + 1} of ${routes.length}` : ''
}

/** A row of the roadmaps list: `8/9`, or why the document has no count. */
export const rowCount = (row: NavRouteRow): string =>
  row.hasRoute ? `${row.done}/${row.total}` : 'no route section'

/** A Bash command that can change ticket state: any `gh` call, or a push / merge / pull. */
export const bashTouchesTickets = (command: string): boolean =>
  /(^|[\s;&|(])gh\s+\S/.test(command) || /\bgit\s+(push|merge|pull)\b/.test(command)

export type RouteTrigger = 'start' | 'open' | 'force' | 'docs'
export const TICKETS_FRESH_MS = 60_000

/**
 * Whether a refresh asks GitHub: never at session start; always on `r` and after a turn that
 * ran `gh` or a push; on `/nav` open when there is no GitHub-backed report for this route or it
 * is older than a minute; after a doc edit only when the card already shows GitHub state, so
 * the card never falls back to checkbox state mid-session.
 */
export const wantTickets = (
  trigger: RouteTrigger, prev: NavRouteReport | null, activePath: string | null, nowMs: number,
): boolean => {
  if (trigger === 'start') return false
  if (trigger === 'force') return true
  const same = prev !== null && prev.github && (activePath === null || prev.doc.path === activePath)
  return trigger === 'docs' ? same : !same || nowMs - prev.at > TICKETS_FRESH_MS
}
