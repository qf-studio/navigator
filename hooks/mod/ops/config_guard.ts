// config_guard — mirror of hooks/ops/config_guard.py (TASK-62, ported TASK-84 step 5d).
// ConfigChange: re-parse the shared and local config files; one warning when either does not
// parse. Python's json error position is reproduced exactly (lib/life-py loads).
import { JSONDecodeError, isDict, loads, safeRead, strip, typeName } from '../lib/life-py'
import type { Op, OpCtx, OpResult } from '../lib/types'

export const CONFIG_RELPATH = '.agent/.nav-config.json'
const GUARDED = [CONFIG_RELPATH, '.agent/.nav-config.local.json']

/** Parse-failure description, or null when the file is a JSON object. */
export const invalidDetail = (raw: string): string | null => {
  try {
    const data = loads(raw)
    return isDict(data) ? null : `top level is ${typeName(data)}, expected a JSON object`
  } catch (e) {
    if (e instanceof JSONDecodeError) return `invalid JSON at line ${e.lineno} column ${e.colno}`
    return 'invalid JSON'
  }
}

const run = async (ctx: OpCtx): Promise<OpResult | null> => {
  for (const rel of GUARDED) {
    const raw = await safeRead(ctx.io, `${ctx.root}/${rel}`)
    if (raw === null || !strip(raw)) continue
    const detail = invalidDetail(raw)
    if (detail === null) continue
    const layer = rel === CONFIG_RELPATH
      ? 'built-in defaults'
      : 'the shared config without your personal overrides'
    return {
      system_message: `nav-config: ${rel} is unreadable (${detail}); `
        + `Navigator is running on ${layer} until the file parses.`,
    }
  }
  return null
}

export const configGuard: Op = {
  spec: { name: 'config_guard', phase: 'injectors', configKey: 'config_guard' },
  run,
}
