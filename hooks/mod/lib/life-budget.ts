// budget.clamp in code points (Python len/slicing). lib/budget.ts counts UTF-16 units, which
// differs from Python only on astral characters; the lifecycle ops use this exact version.
import { BUDGETS, TRUNCATION_MARKER } from './gen/sentinels.gen'
import { cpLen, cpSlice } from './life-py'

export const clampCp = (text: string | null, event: string): string => {
  if (text === null) return ''
  const budget = (BUDGETS as Record<string, number>)[event]
  if (budget === undefined || cpLen(text) <= budget) return text
  const room = budget - cpLen(TRUNCATION_MARKER)
  if (room <= 0) return cpSlice(text, 0, budget)
  let head = cpSlice(text, 0, room)
  const cut = head.lastIndexOf('\n')
  if (cut > 0) head = head.slice(0, cut)
  return head + TRUNCATION_MARKER
}

/** Python int(x) for config values (numbers truncate, numeric strings parse, bools 0/1). */
export const pyInt = (v: unknown, dflt: number): number => {
  if (typeof v === 'boolean') return v ? 1 : 0
  if (typeof v === 'number' && Number.isFinite(v)) return Math.trunc(v)
  if (typeof v === 'string' && /^\s*[-+]?\d+\s*$/.test(v)) return Number.parseInt(v, 10)
  if (v === undefined) return dflt
  throw new TypeError('int() argument')
}
