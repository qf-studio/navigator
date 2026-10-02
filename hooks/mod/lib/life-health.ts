// runtime._surface_health port (TASK-84 step 5d). Not an op: the v7 dispatcher prepends this
// line to the SessionStart contexts before the budget clamp, once per recorded dispatch error.
// The mod runner must do the same for SessionStart (see the step 5d integration notes).
import { cpSlice, dumps, get, isDict, pyStr, safeJson } from './life-py'
import type { Io } from './types'

export const HEALTH_FILE_NAME = '.nav-dispatch-health.json'
const SURFACE_LINE_LIMIT = 160

/** The one-line notice when an unsurfaced error exists; flips `surfaced` so it shows once. */
export const surfaceHealth = async (io: Io, agentDir: string): Promise<string | null> => {
  const path = `${agentDir}/${HEALTH_FILE_NAME}`
  const doc = await safeJson(io, path)
  if (doc === null || doc.size === 0 || get(doc, 'surfaced', true) !== false) return null
  const last = get(doc, 'last_error')
  if (!isDict(last)) return null
  const line = cpSlice(`nav-dispatch: last dispatch error: ${pyStr(get(last, 'event', '?'))}/`
    + `${pyStr(get(last, 'op', '?'))}: ${pyStr(get(last, 'error', ''))}`, 0, SURFACE_LINE_LIMIT)
  doc.set('surfaced', true)
  try {
    await io.write(path, `${dumps(doc, 2)}\n`)
  } catch {
    // atomic_write_json returns False on failure; the line is still returned
  }
  return line
}
