// nav-signal v3 / pilot-signal v2 parser, port of nav_hook_lib/signals.parse. Python's
// MULTILINE `^`/`$` see only \n as a line break and its `.` matches \r; JS's `m` flag and
// `.` also break on \r, U+2028 and U+2029, so v3 lines are matched per \n-split line.
import { isDict } from './stop-py'
import type { Json } from './types'

export const V3_TYPES = ['exit', 'status', 'check', 'brief', 'defer']

const V3_LINE = /^[ \t]*(?:<!--[ \t]*)?nav-signal:v3:(\{[^\n]*\})[ \t]*(?:-->)?[ \t\r]*$/
const V2_BLOCK = /```pilot-signal\r?\n([\s\S]+?)\r?\n```/g

const normalize = (raw: string): Json | null => {
  let data: unknown
  try {
    data = JSON.parse(raw)
  } catch {
    return null
  }
  if (!isDict(data) || typeof data.type !== 'string' || !V3_TYPES.includes(data.type)) return null
  const signal: Json = { v: 3 }
  for (const [k, v] of Object.entries(data)) if (k !== 'v') signal[k] = v
  return signal
}

/** Every signal in `text`, normalized to v3 dicts, in document order. Never throws. */
export const parseSignals = (text: string): Json[] => {
  if (!text) return []
  const found: [number, Json][] = []
  let offset = 0
  for (const line of text.split('\n')) {
    const m = V3_LINE.exec(line)
    if (m?.[1] !== undefined) {
      const signal = normalize(m[1])
      if (signal !== null) found.push([offset, signal])
    }
    offset += line.length + 1
  }
  for (const m of text.matchAll(V2_BLOCK)) {
    const signal = normalize((m[1] ?? '').replace(/\r\n/g, '\n').replace(/\r/g, ''))
    if (signal !== null) found.push([m.index ?? 0, signal])
  }
  found.sort((a, b) => a[0] - b[0])
  return found.map(([, s]) => s)
}
