// Navigator pane data: pure parsing and formatting. The hooks module does the I/O.

import type {
  NavGraph, NavJudge, NavJudgeLabel, NavMemory, NavPace, NavRate, NavReads, NavRejects, NavTask,
} from '../../../types'
import type { Judgment } from '../lib/scoring'

const TASK_ID_RE = /(TASK-\d+)/
const MEMORY_RE = /^-\s*([A-Z]+):\s*"(.*)"\s*(?:\((\d+)%\))?/
const STAT_RE = /^(Total Nodes|Total Edges|Memories):\s*(\d+)/

/** `path|# TASK-80: Title` lines → in-progress tasks with titles, in file order. */
export const parseTasks = (stdout: string): NavTask[] =>
  stdout.split('\n').flatMap(line => {
    const [path = '', heading = ''] = line.split('|')
    const m = TASK_ID_RE.exec(path)
    if (!m?.[1]) return []
    const title = heading.replace(/^#+\s*/, '').replace(new RegExp(`^${m[1]}:?\\s*`), '').trim()
    return [{ id: m[1], title, path: path.trim() }]
  })

/** `memory_recall.py --format compact` lines → kind, text, confidence. */
export const parseMemories = (stdout: string): NavMemory[] =>
  stdout.split('\n').flatMap(line => {
    const m = MEMORY_RE.exec(line.trim())
    if (!m?.[1] || m[2] === undefined) return []
    return [{ kind: m[1], text: m[2], percent: m[3] === undefined ? null : Number(m[3]) }]
  })

/** `graph_manager.py --action stats` text → counts; null when nothing parsed. */
export const parseGraphStats = (stdout: string): NavGraph | null => {
  const found: Record<string, number> = {}
  for (const line of stdout.split('\n')) {
    const m = STAT_RE.exec(line.trim())
    if (m?.[1] && m[2] !== undefined) found[m[1]] = Number(m[2])
  }
  const nodes = found['Total Nodes']
  const edges = found['Total Edges']
  const memories = found.Memories
  return nodes === undefined || edges === undefined || memories === undefined
    ? null
    : { nodes, edges, memories }
}

type Entry = { name: string; mtimeMs: number }

/** Newest marker name by modification time. */
export const latestMarker = (entries: readonly Entry[]): string | null => {
  const files = entries.filter(e => e.name.endsWith('.md'))
  const newest = files.reduce<Entry | null>(
    (best, e) => (best === null || e.mtimeMs > best.mtimeMs ? e : best), null,
  )
  return newest === null ? null : newest.name.replace(/\.md$/, '')
}

/** `▓▓▓▓░░░░` of `width` cells for a percent; all empty when unknown. */
export const bar = (percent: number | null, width: number): string => {
  if (percent === null) return '░'.repeat(width)
  const filled = Math.round((Math.min(100, Math.max(0, percent)) / 100) * width)
  return '▓'.repeat(filled) + '░'.repeat(width - filled)
}

/** `5h 23% · 7d 41% · $0.42`; empty when nothing is known. */
export const usageLine = (rates: readonly NavRate[], usd: number | null): string => {
  const parts = rates.map(r => `${r.kind} ${Math.round(r.percentUsed)}%`)
  if (usd !== null) parts.push(`$${usd.toFixed(2)}`)
  return parts.join(' · ')
}

export const cut = (text: string, width: number): string =>
  text.length > width ? `${text.slice(0, Math.max(0, width - 1))}…` : text

/** Turns until context reaches `limit`%, projected from the recent per-turn slope. */
export const turnsTo = (series: readonly number[], limit: number): number | null => {
  const tail = series.slice(-6)
  const last = tail[tail.length - 1]
  const first = tail[0]
  if (tail.length < 2 || last === undefined || first === undefined) return null
  const slope = (last - first) / (tail.length - 1)
  if (slope <= 0 || last >= limit) return null
  return Math.ceil((limit - last) / slope)
}

/** `five_hour` → `5h`, `seven_day_opus` → `7d opus`. */
export const rateKind = (kind: string): string =>
  kind.replace(/^five_hour/, '5h').replace(/^seven_day/, '7d').replace(/_/g, ' ').trim()

/** `HH:MM` of an ISO time, or null. */
export const clockOf = (iso: string | null): string | null => {
  if (iso === null) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** Estimated tokens for a byte count (~4 bytes per token). */
export const tokensOf = (bytes: number): number => Math.round(bytes / 4)

// Files a read-only Bash command reads (TASK-87): the reads card counted the Read tool only,
// so a session that reads with `cat` / `sed -n` / `head` showed 0 docs. A token is a file when
// it has a known extension; the command must already be read-only (stop-bash.ts), so `cat > f`
// never counts. `.agent/` paths are docs, like the Read tool's rule.
const READ_HEADS = new Set(['cat', 'sed', 'head', 'tail', 'grep', 'rg', 'wc', 'diff'])
const FILE_TOKEN = /^['"]?(\/?(?:[\w.~@-]+\/)*[\w.@-]+\.(?:md|markdown|txt|ts|tsx|js|jsx|mjs|py|sh|json|jsonl|ya?ml|toml|css|html|go|rs|sql))['"]?$/u

export const bashReadFiles = (command: string): string[] => {
  const files = new Set<string>()
  for (const segment of command.split(/\|\||&&|;|\||\n/)) {
    const tokens = segment.trim().split(/\s+/)
    const head = tokens.find(tok => tok.length > 0 && !/^[A-Za-z_][A-Za-z0-9_]*=/.test(tok))
    if (head === undefined || !READ_HEADS.has(head.replace(/^.*\//, ''))) continue
    for (const tok of tokens.slice(1)) {
      const m = FILE_TOKEN.exec(tok)
      if (m?.[1] && !tok.startsWith('-')) files.add(m[1])
    }
  }
  return [...files]
}

export const isDocPath = (path: string): boolean => path.includes('/.agent/') || path.startsWith('.agent/')

export const NO_READS: NavReads = {
  total: 0, docs: 0, turnTotal: 0, turnDocs: 0, lastTurnTotal: 0, lastTurnDocs: 0,
}
/** Code-file Reads in one turn from which the reads card says "use an Agent" (read_guard warns at 3). */
export const FAN_OUT_AT = 3

export const countRead = (r: NavReads, isDoc: boolean): NavReads => ({
  ...r,
  total: r.total + 1,
  docs: r.docs + (isDoc ? 1 : 0),
  turnTotal: r.turnTotal + 1,
  turnDocs: r.turnDocs + (isDoc ? 1 : 0),
})

/** A turn ended: its counts become the last turn's, the running ones restart. */
export const endTurnReads = (r: NavReads): NavReads => ({
  ...r, turnTotal: 0, turnDocs: 0, lastTurnTotal: r.turnTotal, lastTurnDocs: r.turnDocs,
})

/** The reads card's verdict, from the turn in progress when it has reads, else the last one. */
export const fanOutText = (r: NavReads): string => {
  const code = r.turnTotal > 0 ? r.turnTotal - r.turnDocs : r.lastTurnTotal - r.lastTurnDocs
  return code >= FAN_OUT_AT ? 'use an Agent' : 'fan-out ok'
}

const AXIS_WORD: Record<string, string> = {
  loop: 'loop', complexity: 'complexity', task: 'task', ambiguity: 'unclear',
}

/** What Navigator did with the prompt, read off the context it injected. */
export const judgeEffect = (context: string | null): string => {
  if (context === null) return 'direct'
  if (/Loop trigger: YES/.test(context)) return 'loop mode'
  if (/NAV-BRIEF/.test(context)) return 'brief shown'
  if (/Mode: TASK/.test(context)) return 'task mode'
  return 'direct'
}

/**
 * The judge card's line: the verdict in words (`task · medium · unclear`), the effect, and the
 * axes where the judge overrode the keyword rule. Null when the prompt was not judged.
 */
export const judgeView = (
  j: Judgment | null | undefined, axes: Record<string, string> | undefined, context: string | null,
  prompt: { text: string; at: number }, unclearAt = 0.5,
): NavJudge | null => {
  if (j == null) return null
  const task = j.taskVerdict()
  const words: string[] = [task === false ? 'chat' : task === true ? 'task' : 'task?']
  if (j.loopVerdict() === true) words.push('loop')
  const level = j.complexityLevel()
  if (level !== null && task !== false) words.push(level)
  const ambiguity = j.ambiguityIfConfident()
  if (ambiguity !== null && task !== false) words.push(ambiguity >= unclearAt ? 'unclear' : 'clear')
  const overrode = Object.entries(axes ?? {})
    .filter(([, outcome]) => outcome === 'overridden')
    .map(([axis]) => AXIS_WORD[axis] ?? axis)
  return {
    verdict: words.join(' · '),
    effect: judgeEffect(context),
    override: overrode.length === 0 ? null : `↑ ${overrode.join(', ')}: jev over rule`,
    model: j.model,
    latencyMs: j.latencyMs,
    text: prompt.text,
    at: prompt.at,
  }
}

export const JUDGE_TRAIL_MAX = 20
export const JUDGE_LABELS_FILE = 'judge-labels.json'
const LABEL_DOC = 'Prompts labeled from the /nav pane (TASK-86). tier DIRECT|TASK|LOOP, task bool, '
  + 'ambiguous bool; a disputed verdict has tier null for judge_label.py to label. Private, never commit.'

/** The label a confirmed verdict stands for, in the shape scripts/judge_label.py writes. */
export const labelFromVerdict = (verdict: string): { tier: 'DIRECT' | 'TASK' | 'LOOP'; task: boolean; ambiguous: boolean } => {
  const words = new Set(verdict.split(' · '))
  if (words.has('loop')) return { tier: 'LOOP', task: true, ambiguous: words.has('unclear') }
  if (words.has('chat')) return { tier: 'DIRECT', task: false, ambiguous: false }
  const substantial = words.has('substantial') || words.has('large')
  return { tier: substantial ? 'TASK' : 'DIRECT', task: true, ambiguous: words.has('unclear') }
}

export const labelEntry = (j: NavJudge, label: 'confirmed' | 'disputed', project: string): NavJudgeLabel => {
  const base = { text: j.text, project, source: 'pane' as const, at: new Date(j.at).toISOString(), judged: j.verdict }
  if (label === 'disputed') return { ...base, tier: null, task: null, ambiguous: null, disputed: true }
  return { ...base, ...labelFromVerdict(j.verdict) }
}

/** The label file with `entry` added, replacing an earlier entry for the same prompt text. */
export const withLabel = (raw: string | null, entry: NavJudgeLabel): string => {
  let doc: { _doc: string; prompts: NavJudgeLabel[] } = { _doc: LABEL_DOC, prompts: [] }
  if (raw !== null) {
    try {
      const parsed = JSON.parse(raw) as { prompts?: unknown }
      if (Array.isArray(parsed.prompts)) doc = { _doc: LABEL_DOC, prompts: parsed.prompts as NavJudgeLabel[] }
    } catch {
      doc = { _doc: LABEL_DOC, prompts: [] }
    }
  }
  doc.prompts = [...doc.prompts.filter(p => p.text !== entry.text), entry]
  return `${JSON.stringify(doc, null, 1)}\n`
}

/** `12:03 ✓ task · substantial · unclear  "make the onboarding better"`, cut to the width. */
export const trailLine = (j: NavJudge, width: number): string => {
  const mark = j.label === 'confirmed' ? '✓' : j.label === 'disputed' ? '✗' : '·'
  const head = j.text.split('\n')[0]?.trim() ?? ''
  return cut(`${clockOf(new Date(j.at).toISOString()) ?? '--:--'} ${mark} ${j.verdict}  "${head}"`, width)
}

type AxisRow = { agreed?: unknown; overridden?: unknown; undecided?: unknown }

/** `judge` section of the runtime state → the detail lines behind `j`. */
export const judgeTally = (section: unknown): string[] => {
  if (section === null || typeof section !== 'object') return ['no judge calls recorded']
  const b = section as Record<string, unknown>
  const n = (v: unknown): number => (typeof v === 'number' ? Math.trunc(v) : 0)
  const head = `${n(b.calls)} calls · ${n(b.failed)} failed · latency ${n(b.latency_last_ms)} ms, max ${n(b.latency_max_ms)} ms`
  const axes = (b.axes !== null && typeof b.axes === 'object' ? b.axes : {}) as Record<string, AxisRow>
  const rows = ['task', 'complexity', 'ambiguity', 'loop'].flatMap(axis => {
    const row = axes[axis]
    if (row === undefined) return []
    const agreed = n(row.agreed)
    const overridden = n(row.overridden)
    const decided = agreed + overridden
    const share = decided === 0 ? '' : ` · jev over rule ${Math.round((overridden / decided) * 100)}%`
    return [`${(AXIS_WORD[axis] ?? axis).padEnd(11)} agreed ${agreed} · overrode ${overridden} · undecided ${n(row.undecided)}${share}`]
  })
  return [head, ...rows]
}

export const NO_PACE: NavPace = { legTurns: [], turnMs: [] }
const PACE_WINDOW = 32

const mean = (xs: readonly number[]): number | null =>
  xs.length === 0 ? null : xs.reduce((a, b) => a + b, 0) / xs.length

/** A turn ran `ms`; if the leg changed, the one just left took `turnsOnLeg` turns. */
export const recordPace = (p: NavPace, ms: number, turnsOnLeg: number | null): NavPace => ({
  legTurns: turnsOnLeg === null ? p.legTurns : [...p.legTurns, turnsOnLeg].slice(-PACE_WINDOW),
  turnMs: ms > 0 ? [...p.turnMs, ms].slice(-PACE_WINDOW) : p.turnMs,
})

const minutes = (ms: number): string => {
  const m = Math.max(1, Math.round(ms / 60_000))
  return m < 60 ? `${m}m` : `${Math.floor(m / 60)}h ${m % 60}m`
}

/** `eta ~25m · 5 legs left` at the pace so far; `5 legs left` before any leg is done. */
export const etaText = (legsLeft: number, pace: NavPace): string => {
  const legs = legsLeft === 1 ? 'last leg' : `${legsLeft} legs left`
  const turnsPerLeg = mean(pace.legTurns)
  const msPerTurn = mean(pace.turnMs)
  if (legsLeft <= 0 || turnsPerLeg === null || msPerTurn === null) return legs
  return `eta ~${minutes(legsLeft * turnsPerLeg * msPerTurn)} · ${legs}`
}

/**
 * A mutating Bash command that can change what the pane shows: it names `.agent/`, or it is a
 * git command that moves, commits or rewrites files (a task doc archived with `git mv`, a
 * checkout that swaps the task list). Read-only commands never reach here.
 */
export const bashTouchesDocs = (command: string): boolean =>
  /\.agent\b/.test(command)
  || /\bgit\s+(?:mv|commit|checkout|switch|stash|pull|merge|rebase|reset|restore|cherry-pick)\b/.test(command)

// TASK-88: the reject log behind `l`. One JSON line per refusal (lib/rejects.ts); the pane shows
// today's count, the newest line, and the last REJECTS_TAIL lines when opened.
export const REJECTS_TAIL = 8

const sameLocalDay = (a: Date, b: Date): boolean =>
  a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()

/** `.nav-rejects.jsonl` text → pane model; malformed lines are skipped, never thrown on. */
export const parseRejects = (text: string, nowMs: number): NavRejects => {
  const now = new Date(nowMs)
  const rows: { ts: Date; op: string; reason: string }[] = []
  for (const line of text.split('\n')) {
    if (!line.trim()) continue
    try {
      const doc = JSON.parse(line) as Record<string, unknown>
      const ts = new Date(String(doc.ts ?? ''))
      if (Number.isNaN(ts.getTime())) continue
      rows.push({ ts, op: String(doc.op ?? '?'), reason: String(doc.reason ?? '') })
    } catch {
      continue
    }
  }
  const clock = (d: Date): string => clockOf(d.toISOString()) ?? '--:--'
  const last = rows[rows.length - 1]
  return {
    today: rows.filter(r => sameLocalDay(r.ts, now)).length,
    last: last === undefined ? null : { clock: clock(last.ts), op: last.op, reason: last.reason },
    tail: rows.slice(-REJECTS_TAIL).map(r => `${clock(r.ts)} ${r.op} · ${r.reason}`),
  }
}

/** The one-line summary under the reads card: `rejects today 3 · last 14:03 stop_completion`. */
export const rejectsLine = (r: NavRejects | null): string => {
  if (r === null || r.last === null) return 'rejects none'
  return `rejects today ${r.today} · last ${r.last.clock} ${r.last.op}`
}
