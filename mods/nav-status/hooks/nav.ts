// Navigator pane data: pure parsing and formatting. The hooks module does the I/O.

export type Memory = { kind: string; text: string; percent: number | null }

export type NavData = {
  task: string | null
  marker: string | null
  memories: Memory[]
}

export const EMPTY_NAV: NavData = { task: null, marker: null, memories: [] }

const TASK_ID_RE = /(TASK-\d+)/
const MEMORY_RE = /^-\s*([A-Z]+):\s*"(.*)"\s*(?:\((\d+)%\))?/

/** Last in-progress task id from a `grep -l` listing of task files. */
export const parseTaskList = (stdout: string): string | null => {
  const names = stdout.split('\n').map(l => l.trim()).filter(l => l.length > 0)
  const last = names[names.length - 1]
  const m = last === undefined ? null : TASK_ID_RE.exec(last)
  return m?.[1] ?? null
}

/** Lines of `memory_recall.py --format compact`: `- KIND: "text" (NN%) …`. */
export const parseMemories = (stdout: string): Memory[] =>
  stdout.split('\n').flatMap(line => {
    const m = MEMORY_RE.exec(line.trim())
    if (!m?.[1] || m[2] === undefined) return []
    return [{ kind: m[1], text: m[2], percent: m[3] === undefined ? null : Number(m[3]) }]
  })

/** Newest marker name from a directory listing, by name order (dated names sort). */
export const latestMarker = (names: readonly string[]): string | null => {
  const files = names.filter(n => n.endsWith('.md')).sort()
  const last = files[files.length - 1]
  return last === undefined ? null : last.replace(/\.md$/, '')
}

/** `▓▓▓▓░░░░` of `width` cells for a percent; empty when unknown. */
export const bar = (percent: number | null, width: number): string => {
  if (percent === null) return '░'.repeat(width)
  const filled = Math.round((Math.min(100, Math.max(0, percent)) / 100) * width)
  return '▓'.repeat(filled) + '░'.repeat(width - filled)
}

export const cut = (text: string, width: number): string =>
  text.length > width ? `${text.slice(0, Math.max(0, width - 1))}…` : text
