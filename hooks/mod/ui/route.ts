// Navigation model for the /nav pane and band: destination, route, off-route detection.
// Pure: the hooks module reads files and state, these functions decide what to show.

export type Waypoint = { id?: string; label: string; state: 'done' | 'current' | 'todo' }
export type Step = { id?: string; label: string; done: boolean }
export type Destination = { title: string; taskId: string | null; source: 'brief' | 'task' }

const PHASES = ['research', 'impl', 'verify', 'complete'] as const
const CHECK_RE = /^\s*[-*]\s+\[([ xX])\]\s+(.+?)\s*$/
const PLAN_RE = /^(#{2,3})\s+.*\b(work breakdown|implementation|plan|steps|phases)\b/i
const HEADING_RE = /^(#{1,6})\s/
const ROW_RE = /^\|\s*(\d+[a-z]?)\s*\|\s*([^|]+?)\s*\|/i
const ITEM_RE = /^\s*(\d+)[.)]\s+(.+?)\s*$/
// `### Step 0 — …✅`, `### Steps 5b + 5c — …✅`; `### Step 10 (automated part) — …✅` is partial.
const STEP_DONE_RE = /^#{2,4}\s+Steps?\s+([\da-z+,&\s]+?)\s*(\([^)]*\))?\s*[—–-]\s.*✅/i
const LABEL_MAX = 60
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

/** A plan cell as a waypoint label: no markup, parentheticals or `; details`, capped. */
const stepLabel = (raw: string): string => {
  const text = raw.replace(/`|\*\*|~~|✅/g, '').replace(/\s*\([^)]*\)/g, '')
    .split(';')[0]!.replace(/\s+/g, ' ').trim()
  return text.length > LABEL_MAX ? `${text.slice(0, LABEL_MAX - 1).trimEnd()}…` : text
}

/** Lines of the first plan section (`## Work breakdown`, `## Implementation plan`, …). */
const planSection = (lines: readonly string[]): string[] => {
  const start = lines.findIndex(l => PLAN_RE.test(l))
  if (start < 0) return []
  const level = PLAN_RE.exec(lines[start]!)![1]!.length
  const rest = lines.slice(start + 1)
  const end = rest.findIndex(l => (HEADING_RE.exec(l)?.[1]?.length ?? 99) <= level)
  return end < 0 ? rest : rest.slice(0, end)
}

/** Step ids a `### Step … ✅` progress heading marks done. */
const doneIds = (lines: readonly string[]): Set<string> =>
  new Set(lines.flatMap(line => {
    const m = STEP_DONE_RE.exec(line)
    return m?.[1] && !m[2] ? (m[1].match(/\d+[a-z]?/gi) ?? []).map(id => id.toLowerCase()) : []
  }))

/**
 * The steps to the destination, from the active task doc: its `- [ ]` checklist when it has one,
 * else the numbered table rows or list items of its plan section, done when the row says ✅ or
 * ~~struck~~, or a `### Step n — … ✅` progress heading names it.
 */
export const parseSteps = (markdown: string): Step[] => {
  const checklist = parseChecklist(markdown)
  if (checklist.length > 0) return checklist
  const lines = markdown.split('\n')
  const section = planSection(lines)
  const matches = (re: RegExp) => section.map(l => re.exec(l)).filter(m => m !== null)
  const table = matches(ROW_RE)
  const rows = table.length > 0 ? table : matches(ITEM_RE)
  const finished = doneIds(lines)
  return rows.map(([line, id, cell]) => ({
    id: id!,
    label: stepLabel(cell!),
    done: line.includes('✅') || /^~~.*~~$/.test(cell!.trim()) || finished.has(id!.toLowerCase()),
  }))
}

/** The route: the task's steps when it has some, else Navigator's own phases. */
export const buildRoute = (steps: readonly Step[], phase: string | null): Waypoint[] => {
  if (steps.length > 0) {
    const current = steps.findIndex(c => !c.done)
    return steps.map((c, i) => ({
      ...(c.id === undefined ? {} : { id: c.id }),
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

export type RouteView = { earlier: number; shown: Waypoint[]; more: number }

/**
 * What the pane lists: the whole route when it fits `max` lines; a longer one keeps the last
 * passed step for context, folds the steps before it into `earlier`, and cuts the tail.
 */
export const routeView = (route: readonly Waypoint[], max: number): RouteView => {
  if (route.length <= max) return { earlier: 0, shown: [...route], more: 0 }
  const open = route.findIndex(w => w.state !== 'done')
  const start = Math.min(Math.max(0, (open < 0 ? route.length : open) - 1), route.length - max)
  return { earlier: start, shown: route.slice(start, start + max), more: route.length - start - max }
}

/** `● 5b  tool.call group`, `○ verify`. */
export const waypointText = (w: Waypoint): string => {
  const mark = w.state === 'done' ? '✓' : w.state === 'current' ? '●' : '○'
  return w.id === undefined ? `${mark} ${w.label}` : `${mark} ${w.id.padEnd(3)} ${w.label}`
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
