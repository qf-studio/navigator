// Port of nav_hook_lib/state.py load/save (TASK-84). The mod and the Python runtime share
// one schema-2 file, .agent/.nav-runtime-state.json, so an op handed between them (breaker,
// older Claude Code) sees the same state. No flock in the mod: events run sequentially
// (modules before settings hooks), and readers fail open on a torn file.
import type { Io, Json } from './types'

export const SCHEMA_VERSION = 2
export const STATE_PATH = '.agent/.nav-runtime-state.json'
const HOUR = 3600
const DAY = 24 * HOUR
export const SECTION_TTLS: Record<string, number> = {
  session: DAY, turn: 2 * HOUR, reads: 2 * HOUR, completion: 2 * HOUR, brief: 2 * HOUR,
  jit: DAY, tier1: 30 * DAY, profile: 30 * DAY, compact: 30 * DAY, judge: 30 * DAY,
}
const SESSION_SCOPED = new Set(['session', 'turn', 'reads', 'completion', 'brief', 'jit'])
const MAX_OP_ERRORS = 20

export type RuntimeState = Json & { meta: Json & { sections: Record<string, number> } }

const isObject = (v: unknown): v is Json => v !== null && typeof v === 'object' && !Array.isArray(v)

const readV2 = async (io: Io, path: string): Promise<Json | null> => {
  try {
    const data: unknown = JSON.parse(await io.read(path))
    if (!isObject(data) || !isObject(data.meta) || data.meta.schema !== SCHEMA_VERSION) return null
    return data
  } catch {
    return null
  }
}

const ensureMeta = (meta: Json): Json => {
  if (meta.writer === undefined) meta.writer = ''
  if (!Array.isArray(meta.op_errors)) meta.op_errors = []
  return meta
}

/** state.load: expired or session-mismatched sections are absent (fail-closed scoping). */
export const load = async (
  io: Io, root: string, sessionId: string | null, nowS: number,
): Promise<RuntimeState> => {
  const data = await readV2(io, `${root}/${STATE_PATH}`)
  if (data === null) {
    return { meta: ensureMeta({ schema: SCHEMA_VERSION, sections: {} }) } as RuntimeState
  }
  const metaIn = data.meta as Json
  const tsMap = isObject(metaIn.sections) ? (metaIn.sections as Record<string, unknown>) : {}
  const stored = isObject(data.session) ? data.session.id : undefined
  const mismatch = Boolean(sessionId) && stored !== sessionId
  const out: Json = {}
  const surviving: Record<string, number> = {}
  for (const [name, content] of Object.entries(data)) {
    if (name === 'meta' || !isObject(content)) continue
    if (mismatch && SESSION_SCOPED.has(name)) continue
    const ts = tsMap[name]
    const ttl = SECTION_TTLS[name]
    const hasTs = typeof ts === 'number'
    if (hasTs && ttl !== undefined && nowS - ts > ttl) continue
    out[name] = content
    if (hasTs) surviving[name] = ts
  }
  out.meta = ensureMeta({ ...metaIn, schema: SCHEMA_VERSION, sections: surviving })
  return out as RuntimeState
}

/** Python `datetime.fromtimestamp(ts, tz=utc).isoformat()` (microseconds, +00:00). */
const isoUtc = (nowS: number): string => {
  const ms = Math.floor(nowS * 1000)
  const micros = Math.round((nowS - Math.floor(nowS)) * 1e6)
  const base = new Date(ms).toISOString().slice(0, 19)
  return micros === 0 ? `${base}+00:00` : `${base}.${String(micros).padStart(6, '0')}+00:00`
}

const same = (a: unknown, b: unknown): boolean => JSON.stringify(a) === JSON.stringify(b)

/** state.save: refresh a section's timestamp only when its content changed. */
export const save = async (
  io: Io, root: string, state: RuntimeState, sessionId: string | null, nowS: number,
): Promise<boolean> => {
  if (sessionId) {
    const session = isObject(state.session) ? state.session : {}
    session.id = sessionId
    state.session = session
  }
  const path = `${root}/${STATE_PATH}`
  const prev = (await readV2(io, path)) ?? {}
  const meta = isObject(state.meta) ? state.meta : ({} as RuntimeState['meta'])
  const carried = isObject(meta.sections) ? meta.sections : {}
  const fresh: Record<string, number> = {}
  for (const [name, content] of Object.entries(state)) {
    if (name === 'meta') continue
    const c = carried[name]
    fresh[name] = typeof c === 'number' && same(prev[name], content) ? c : nowS
  }
  meta.schema = SCHEMA_VERSION
  meta.updated = isoUtc(nowS)
  meta.sections = fresh
  ensureMeta(meta)
  meta.op_errors = (meta.op_errors as unknown[]).slice(-MAX_OP_ERRORS)
  state.meta = meta
  try {
    await io.write(path, `${JSON.stringify(state, null, 2)}\n`)
    return true
  } catch {
    return false
  }
}
