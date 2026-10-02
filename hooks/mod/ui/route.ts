// Navigation model for the /nav pane and band: destination, route, off-route detection.
// Pure: the hooks module reads files and state, these functions decide what to show.

export type Waypoint = { label: string; state: 'done' | 'current' | 'todo' }
export type Destination = { title: string; taskId: string | null; source: 'brief' | 'task' }

const PHASES = ['research', 'impl', 'verify', 'complete'] as const
const CHECK_RE = /^\s*[-*]\s+\[([ xX])\]\s+(.+?)\s*$/
const GOAL_RE = /^\s*(?:\|\s*)?(?:\*\*)?goal(?:\*\*)?\s*(?:\||:)\s*(?:\*\*)?(.+?)(?:\s*\|)?\s*$/im
const STOP = new Set([
  'this', 'that', 'these', 'those', 'with', 'from', 'into', 'about', 'after', 'before', 'please',
  'then', 'them', 'they', 'their', 'have', 'been', 'will', 'would', 'should', 'could', 'make',
  'sure', 'need', 'want', 'like', 'some', 'more', 'when', 'what', 'where', 'which', 'there',
  'here', 'just', 'also', 'only', 'does', 'doing', 'done', 'dont', 'thing', 'things', 'okay',
  'yeah', 'show', 'tell', 'look', 'lets', 'your', 'mine', 'very', 'much', 'many', 'next',
])

/** `- [ ] item` / `- [x] item` lines of a task doc, in order. */
export const parseChecklist = (markdown: string): { label: string; done: boolean }[] =>
  markdown.split('\n').flatMap(line => {
    const m = CHECK_RE.exec(line)
    return m?.[2] ? [{ label: m[2].replace(/\*\*/g, ''), done: m[1] !== ' ' }] : []
  })

/** The route: the task's checklist when it has one, else Navigator's own phases. */
export const buildRoute = (
  checklist: readonly { label: string; done: boolean }[], phase: string | null,
): Waypoint[] => {
  if (checklist.length > 0) {
    const current = checklist.findIndex(c => !c.done)
    return checklist.map((c, i) => ({
      label: c.label,
      state: c.done ? 'done' : i === current ? 'current' : 'todo',
    }))
  }
  const at = phase === null ? -1 : PHASES.indexOf(phase.toLowerCase() as (typeof PHASES)[number])
  return PHASES.map((label, i) => ({
    label,
    state: at < 0 ? 'todo' : i < at ? 'done' : i === at ? (label === 'complete' ? 'done' : 'current') : 'todo',
  }))
}

export const currentWaypoint = (route: readonly Waypoint[]): Waypoint | null =>
  route.find(w => w.state === 'current') ?? null

export const arrived = (route: readonly Waypoint[]): boolean =>
  route.length > 0 && route.every(w => w.state === 'done')

const short = (label: string, max: number): string =>
  label.length > max ? `${label.slice(0, Math.max(1, max - 1))}…` : label

/** `✓ research ── ● verify ── ○ docs`, labels shortened until the line fits `width`. */
export const routeLine = (route: readonly Waypoint[], width: number): string => {
  const mark = (w: Waypoint) => (w.state === 'done' ? '✓' : w.state === 'current' ? '●' : '○')
  for (const max of [24, 16, 12, 9, 6, 3]) {
    const line = route.map(w => `${mark(w)} ${short(w.label, max)}`).join(' ── ')
    if (line.length <= width) return line
  }
  return route.map(mark).join(' ')
}

/** "Goal: …" from a brief Claude wrote (plain, bold, or a `| Goal | … |` table row). */
export const captureGoal = (answer: string): string | null => {
  const m = GOAL_RE.exec(answer)
  const goal = m?.[1]?.replace(/\*\*/g, '').trim()
  return goal && goal.length >= 4 && !/^[-|: ]+$/.test(goal) ? goal.slice(0, 80) : null
}

/** Lower-case content words (4+ letters, stopwords out). */
export const contentWords = (text: string): Set<string> =>
  new Set((text.toLowerCase().match(/[a-z][a-z0-9-]{3,}/g) ?? []).filter(w => !STOP.has(w)))

/**
 * A prompt is off route when it has enough substance to judge (4+ content words) and shares
 * none of them with the destination's vocabulary. Short replies ("yes", "go ahead") never count.
 */
/** Light suffix stemmer so route / routes / routing / routed share a stem. */
const stem = (w: string): string => {
  const m = /^(.{4,}?)(?:ations?|ings?|ions?|ers?|ed|es|e|s)$/.exec(w)
  return m?.[1] ?? w
}

/**
 * A prompt is off route when it has enough substance to judge (4+ content words) and shares
 * no word stem with the destination's vocabulary. Short replies ("yes", "go ahead") never count.
 */
export const isOffRoute = (prompt: string, destinationWords: ReadonlySet<string>): boolean => {
  if (destinationWords.size === 0) return false
  const words = contentWords(prompt)
  if (words.size < 4) return false
  const stems = new Set([...destinationWords].map(stem))
  for (const w of words) if (stems.has(stem(w))) return false
  return true
}

/** A 2–4 word topic for a detour, taken from the prompt itself. */
export const detourTopic = (prompt: string): string => {
  const words = [...contentWords(prompt)].slice(0, 3)
  return words.length > 0 ? words.join(' ') : 'a different topic'
}

/** Next free TASK number from task file names. */
export const nextTaskNumber = (names: readonly string[]): number =>
  1 + names.reduce((max, n) => Math.max(max, Number(/^TASK-(\d+)/.exec(n)?.[1] ?? 0)), 0)

export const slugOf = (text: string): string =>
  text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40) || 'parked'

/** A task stub for a parked detour. */
export const parkedTaskDoc = (
  id: string, topic: string, prompt: string, destination: string, date: string,
): string => [
  `# ${id}: ${topic}`,
  '',
  `**Status**: 📋 Parked — ${date}, from a detour while working on "${destination}".`,
  '',
  '## What came up',
  '',
  ...prompt.trim().split('\n').map(l => `> ${l}`),
  '',
  '## Next',
  '',
  '- [ ] Decide whether this is worth doing',
  '',
].join('\n')

export type BandState = {
  destination: string | null
  waypoint: string | null
  /** 1-based position of the current waypoint and the route length. */
  position: number
  total: number
  next: string | null
  offRoute: string | null
  lowFuel: boolean
}

/**
 * One quiet line, `<state>: <what>`, or '' when there is nothing worth showing:
 *   on route: Ship v8 · ● verify 3/5 · next: run headless matrix
 *   low fuel: Ship v8 · ● verify 3/5 · compact after this waypoint
 *   off route: Threads feedback · /nav to park or go back
 *   no route: say what you're building, or /nav → t to pick a task
 */
export const bandText = (s: BandState, width: number): string => {
  const at = s.waypoint === null ? null
    : `● ${s.waypoint}${s.total > 0 && s.position > 0 ? ` ${s.position}/${s.total}` : ''}`
  const head = [s.destination, at].filter((x): x is string => Boolean(x)).join(' · ')
  let line: string
  if (s.offRoute !== null) line = `off route: ${s.offRoute} · /nav to park or go back`
  else if (head && s.lowFuel) line = `low fuel: ${head} · compact after this waypoint`
  else if (head) line = `on route: ${head}${s.next ? ` · next: ${s.next}` : ''}`
  else if (s.lowFuel) line = 'low fuel: compact soon'
  else line = ''
  return line.length > width ? `${line.slice(0, Math.max(0, width - 1))}…` : line
}
