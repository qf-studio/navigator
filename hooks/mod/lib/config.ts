// Layered config, mirror of nav_hook_lib/config.py: DEFAULTS < shared < local.
// isPilotExecutor() is the only PILOT_EXECUTOR policy decision in the mod.
import { CONFIG_DEFAULTS } from './gen/config-defaults.gen'
import type { Io, Json, OpSpec } from './types'

const SHARED = '.agent/.nav-config.json'
const LOCAL = '.agent/.nav-config.local.json'

const isObject = (v: unknown): v is Json => v !== null && typeof v === 'object' && !Array.isArray(v)

/** Dicts merge key-wise; scalars and lists replace wholesale; unknown keys survive. */
export const deepMerge = (base: Json, over: Json): Json => {
  const out: Json = { ...base }
  for (const [k, v] of Object.entries(over)) {
    const b = out[k]
    out[k] = isObject(b) && isObject(v) ? deepMerge(b, v) : v
  }
  return out
}

export const readJson = async (io: Io, path: string): Promise<Json | null> => {
  try {
    const parsed: unknown = JSON.parse(await io.read(path))
    return isObject(parsed) ? parsed : null
  } catch {
    return null
  }
}

export const loadConfig = async (io: Io, root: string): Promise<Json> => {
  const defaults = JSON.parse(JSON.stringify(CONFIG_DEFAULTS)) as Json
  const shared = (await readJson(io, `${root}/${SHARED}`)) ?? {}
  const local = (await readJson(io, `${root}/${LOCAL}`)) ?? {}
  return deepMerge(deepMerge(defaults, shared), local)
}

/** `get(cfg, "a.b.c", fallback)`; a present null leaf is returned, not defaulted. */
export const getPath = (cfg: unknown, dotted: string, fallback: unknown = undefined): unknown => {
  let node: unknown = cfg
  for (const part of dotted.split('.')) {
    if (!isObject(node) || !(part in node)) return fallback
    node = node[part]
  }
  return node
}

/** runtime._config_allows: an op with a config key runs only when `<key>.enabled` is true. */
export const configAllows = (cfg: Json, spec: OpSpec): boolean =>
  spec.configKey === null || getPath(cfg, `${spec.configKey}.enabled`, false) === true

/** THE only PILOT_EXECUTOR policy read in the mod: any non-empty value is true (v7 parity). */
export const isPilotExecutor = async (io: Io): Promise<boolean> =>
  Boolean((await io.env()).PILOT_EXECUTOR)
