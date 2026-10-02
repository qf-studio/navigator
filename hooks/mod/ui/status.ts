// Band content, mirrored from hooks/ops/stop_state.py (phase regex) and the
// NAVIGATOR_STATUS layout in skills/nav-loop/SKILL.md. Pure.

import type { NavPhase, NavStatus } from '../../../types'

const PHASE_RE = /\bPhase:\s*(INIT|RESEARCH|IMPL|VERIFY|COMPLETE)\b/
const NEXT_ACTION_RE = /^(?:\*\*)?Next(?: action)?:(?:\*\*)?\s*(.+)$/im
const LEAD_MARKUP_RE = /^(?:[#>*\-]+\s*|\d+\.\s*)+/
const BOLD_RE = /\*\*/g
const STATUS_LINE_RE = /^(NAVIGATOR_STATUS|Phase:|Iteration:|Progress:|Stagnation:|State Hash|Previous Hash|Exit Conditions|Completion Indicators|```)/

export const parsePhase = (answer: string): NavPhase | null => {
  const m = PHASE_RE.exec(answer)
  return m ? (m[1] as NavPhase) : null
}

/** The first non-empty line, stripped of list/heading markup and bold markers. */
export const firstLine = (answer: string): string | null => {
  const line = answer.split('\n').map(l => l.trim())
    .find(l => l.length > 0 && !STATUS_LINE_RE.test(l))
  if (!line) return null
  const bare = line.replace(LEAD_MARKUP_RE, '').replace(BOLD_RE, '').trim()
  return bare.length > 0 ? bare : null
}

/** `Next Action:` (NAVIGATOR_STATUS) or a `Next:` line, else the reply's first line. */
export const parseNextAction = (answer: string): string | null => {
  const m = NEXT_ACTION_RE.exec(answer)
  return m?.[1] ? m[1].trim() : firstLine(answer)
}

export const statusOf = (answer: string, ctxPercent: number | null): NavStatus => ({
  phase: parsePhase(answer),
  next: parseNextAction(answer),
  ctxPercent,
})

export const isQuiet = (s: NavStatus | null): boolean =>
  s === null || (s.phase === null && s.next === null)

/** `[nav] phase IMPL · ctx 42% · next: run tests`, null segments omitted, cut to width. */
export const bandLine = (s: NavStatus, columns: number): string => {
  const parts = [
    s.phase === null ? null : `phase ${s.phase}`,
    s.ctxPercent === null ? null : `ctx ${Math.round(s.ctxPercent)}%`,
    s.next === null ? null : `next: ${s.next}`,
  ].filter((p): p is string => p !== null)
  const line = `[nav] ${parts.join(' · ')}`
  return line.length > columns ? `${line.slice(0, Math.max(0, columns - 1))}…` : line
}
