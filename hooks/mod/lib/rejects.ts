// Reject log, mirror of nav_hook_lib/rejects.py (TASK-88): one JSONL line per refusal the
// runtime makes. Ops attach `reject: {reason, evidence}` to a blocking result; runOps strips
// the key and appends the line here. Byte-identical to the Python line (compact separators,
// fixed key order), asserted by the generated rejects fixture.
import type { Io, Json } from './types'

export const REJECTS_PATH = '.agent/.nav-rejects.jsonl'
export const KEEP_LINES = 500
export const REWRITE_AT = 600

export type Reject = { reason: string; evidence: Json }

export const rejectLine = (
  ts: string, session: string | null, event: string, op: string, tool: string | null,
  reject: Partial<Reject> | Json, suppressed = false,
): string => {
  const doc: Json = { ts, session, event, op }
  if (typeof tool === 'string' && tool) doc.tool = tool
  doc.reason = String(reject.reason ?? '')
  const evidence = reject.evidence
  doc.evidence = evidence !== null && typeof evidence === 'object' && !Array.isArray(evidence) ? evidence : {}
  if (suppressed) doc.suppressed = true
  return JSON.stringify(doc)
}

/** rejects.append: one line; rewrite with the newest KEEP_LINES once past REWRITE_AT. */
export const appendReject = async (io: Io, root: string, text: string): Promise<boolean> => {
  const path = `${root}/${REJECTS_PATH}`
  const existing = await io.read(path).catch(() => '')
  let lines = existing.split('\n').filter(Boolean)
  lines.push(text)
  if (lines.length > REWRITE_AT) lines = lines.slice(-KEEP_LINES)
  try {
    await io.write(path, `${lines.join('\n')}\n`)
    return true
  } catch {
    return false
  }
}
