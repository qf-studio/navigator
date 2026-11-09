// Task-doc status predicates shared by the /nav pane, the compact marker (TASK-91) and the
// session-start Open Tasks block (GH-47). Mirrors the Python in hooks/ops/compact_marker.py
// (`is_in_progress`, `status_value`, `is_done`); the lifeops fixtures assert parity.

/** The `**Status**:` / `**Status:**` / `Status:` line, tolerant like task_to_graph.py. */
const STATUS_LINE = /^[>\s]*\*{0,2}\s*status\s*\*{0,2}\s*:\s*\*{0,2}\s*(.+?)\s*$/im

const IN_PROGRESS_WORDS = /\bin[ -]progress\b/i

/**
 * True when a task doc is in progress. With a Status line only that line decides
 * (🚧 or the phrase "in progress"), so prose that quotes the phrase elsewhere — TASK-67's own
 * doc does — no longer counts. Docs without a Status line keep the legacy whole-head scan.
 */
export const isInProgress = (text: string): boolean => {
  const m = STATUS_LINE.exec(text)
  if (m?.[1] !== undefined) {
    return m[1].includes('🚧') || IN_PROGRESS_WORDS.test(m[1])
  }
  const low = text.toLowerCase()
  return low.includes('in progress') || low.includes('in-progress') || text.includes('🚧')
}

/** Done vocabulary shared with session_start (GH-47); `\b` is ASCII-only, as in the Python. */
const DONE_MARKS = ['✅', '📦', '❌', '🗑']
const DONE_WORDS = new RegExp(
  "\\b(?:completed?|implemented|released|shipped|archived|archive pending|done|removed"
  + "|deprecated|won'?t do)\\b", 'i')
const LEADING_SYMBOLS = /^(?:[^\x00-\x7f]|[ \t])*/
const CLAUSE_END = /[—–,;:(]|[ \t]-[ \t]/

/** Python str.strip(chars) for the decoration around a Status value. */
const stripDecoration = (s: string): string => s.replace(/^[*` ]+/, '').replace(/[*` ]+$/, '')

/**
 * The value of the Status line with bold/code decoration stripped, or undefined when the doc
 * has no Status line; the H1 or prose never count.
 */
export const statusValue = (text: string): string | undefined => {
  const m = STATUS_LINE.exec(text)
  return m?.[1] === undefined ? undefined : stripDecoration(m[1])
}

/**
 * True when the Status line says the work is finished. A leading symbol decides when present
 * (✅ 📦 ❌ 🗑 done, any other open); without one the first clause of the value is matched
 * whole-word against the done vocabulary. Docs without a Status line are open.
 */
export const isDone = (text: string): boolean => {
  const value = statusValue(text)
  if (value === undefined) return false
  const marks = LEADING_SYMBOLS.exec(value)?.[0] ?? ''
  if (marks.trim() !== '') return DONE_MARKS.some((mark) => marks.includes(mark))
  const end = CLAUSE_END.exec(value)
  const clause = end === null ? value : value.slice(0, end.index)
  return DONE_WORDS.test(clause)
}
