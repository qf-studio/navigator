// Build the per-event context the ops see, mirror of the SimpleNamespace in runtime._dispatch.
import { getPath, isPilotExecutor, loadConfig } from './config'
import { projectRoot } from './project'
import type { Io, Json, OpCtx } from './types'

/** null outside a Navigator project or with the dispatcher kill switch off (v7 parity). */
export const makeCtx = async (io: Io, event: string, payload: Json): Promise<OpCtx | null> => {
  const root = await projectRoot(io)
  if (root === null) return null
  const config = await loadConfig(io, root)
  if (getPath(config, 'dispatcher.enabled', true) === false) return null
  return {
    io, event, payload, config, root,
    pilotExecutor: await isPilotExecutor(io),
    now: (await io.nowMs()) / 1000,
  }
}
