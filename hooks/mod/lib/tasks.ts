// Task-doc status predicate shared by the /nav pane and the compact marker (TASK-91).
// Mirrors the Python in hooks/ops/compact_marker.py (`is_in_progress`); the lifeops
// fixtures assert parity for the marker hint.

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
