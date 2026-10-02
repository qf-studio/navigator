// Python-semantics helpers for the Stop ops port (TASK-84 step 5c). The Stop ops scan
// transcript text and shell commands with Python's Unicode-aware classes; these helpers
// reproduce them exactly so the ports stay byte-identical with hooks/ops/stop_*.py.

/** Python str.isspace() / re `\s` for str patterns (has \x1c-\x1f and \x85, not ﻿). */
const WS_CLASS = '\\t\\n\\x0b\\x0c\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000'
export const WS = `[${WS_CLASS}]`
/** Python re `\S`. */
export const NWS = `[^${WS_CLASS}]`
/** Python word class `\w` (str patterns) and an exact `\b` emulation (JS `\b` is ASCII-only). */
export const W = '[\\p{L}\\p{N}_]'
export const B = `(?:(?<=${W})(?!${W})|(?<!${W})(?=${W}))`

const STRIP_RE = new RegExp(`^${WS}+|${WS}+$`, 'gu')
const SPLIT_RE = new RegExp(`${WS}+`, 'u')
/** Python str.splitlines() line boundaries. */
const LINES_SOURCE = '\\r\\n|[\\n\\r\\x0b\\x0c\\x1c\\x1d\\x1e\\x85\\u2028\\u2029]'
const LINES_RE = new RegExp(LINES_SOURCE, 'u')
const TRAILING_BREAK_RE = new RegExp(`(?:${LINES_SOURCE})$`, 'u')

export const pyStrip = (s: string): string => s.replace(STRIP_RE, '')
export const pySplit = (s: string): string[] => s.split(SPLIT_RE).filter(t => t.length > 0)

export const pySplitlines = (s: string): string[] => {
  if (s === '') return []
  const parts = s.split(LINES_RE)
  // splitlines() yields no empty final element for a trailing line break.
  if (TRAILING_BREAK_RE.test(s)) parts.pop()
  return parts
}

/** Python truthiness for JSON-shaped values. */
export const pyTruthy = (v: unknown): boolean => {
  if (v === null || v === undefined || v === false) return false
  if (typeof v === 'number') return v !== 0 && !Number.isNaN(v)
  if (typeof v === 'string') return v.length > 0
  if (Array.isArray(v)) return v.length > 0
  if (typeof v === 'object') return Object.keys(v as object).length > 0
  return true
}

export const isDict = (v: unknown): v is Record<string, unknown> =>
  v !== null && typeof v === 'object' && !Array.isArray(v)

/** Python len() on str: code points, not UTF-16 units. */
export const pyLen = (s: string): number => {
  let n = 0
  for (const _ of s) n += 1
  return n
}

/** Python int(value) for config values; null where Python raises TypeError/ValueError. */
export const pyInt = (v: unknown): number | null => {
  if (typeof v === 'boolean') return v ? 1 : 0
  if (typeof v === 'number') return Number.isFinite(v) ? Math.trunc(v) : null
  if (typeof v === 'string') {
    const t = pyStrip(v)
    return /^[+-]?\d+(?:_\d+)*$/.test(t) ? Number.parseInt(t.replace(/_/g, ''), 10) : null
  }
  return null
}
