// Navigator pane data: pure parsing and formatting. The hooks module does the I/O.

import type { NavGraph, NavMemory, NavRate, NavTask } from '../types'

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
    return [{ id: m[1], title }]
  })

/** Lines of `memory_recall.py --format compact`: `- KIND: "text" (NN%) …`. */
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
