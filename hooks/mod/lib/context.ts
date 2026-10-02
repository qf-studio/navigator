// Build the per-event context the ops see, mirror of the SimpleNamespace in runtime._dispatch.
import { getPath, isPilotExecutor, loadConfig } from './config'
import { projectRoot } from './project'
import { load } from './state'
import type { Io, Json, OpCtx } from './types'

/** null outside a Navigator project or with the dispatcher kill switch off (v7 parity). */
export const makeCtx = async (io: Io, event: string, payload: Json): Promise<OpCtx | null> => {
  const root = await projectRoot(io)
  if (root === null) return null
  const config = await loadConfig(io, root)
  if (getPath(config, 'dispatcher.enabled', true) === false) return null
  const now = (await io.nowMs()) / 1000
  const sessionId = await io.sessionId()
  return {
    io, event, payload, config, root, sessionId, now,
    state: await load(io, root, sessionId, now),
    pilotExecutor: await isPilotExecutor(io),
  }
}
