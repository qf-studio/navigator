// Which v7 ops the mod runs in place of Python (TASK-84). The list is announced to the
// Python runtime through NAVIGATOR_MOD_OWNS; runtime._dispatch skips every name in it.
import type { Io } from './lib/types'

/** Ops ported to the mod. An op joins this list in the same commit as its parity tests. */
export const OWNED: readonly string[] = [
  'prompt_gate', 'prompt_tier1', 'prompt_adhd', 'prompt_brief',
  'read_guard', 'jit_memory', 'graph_sync', 'profile_sync', 'failure_diagnosis',
  'stop_completion', 'stop_state',
]

export const MIN_CC = '2.1.287'
export const BREAKER_LIMIT = 3

const parts = (v: string): number[] => v.split(/[.-]/).slice(0, 3).map(n => Number.parseInt(n, 10) || 0)

/** -1 / 0 / 1 for dotted versions; suffixes such as `-dev` are ignored. */
export const compareVersions = (a: string, b: string): number => {
  const [x, y] = [parts(a), parts(b)]
  for (let i = 0; i < 3; i += 1) {
    const d = (x[i] ?? 0) - (y[i] ?? 0)
    if (d !== 0) return d < 0 ? -1 : 1
  }
  return 0
}

export const supportsMods = async (io: Io): Promise<boolean> => {
  const v = await io.version()
  return compareVersions(v.base ?? v.version, MIN_CC) >= 0
}

export const ownedNow = async (io: Io): Promise<string[]> => {
  if (!(await supportsMods(io))) return []
  const off = await io.disowned()
  return OWNED.filter(name => !off.includes(name))
}

export const owns = async (io: Io, name: string): Promise<boolean> =>
  (await ownedNow(io)).includes(name)

export const announce = async (io: Io): Promise<void> => {
  await io.setOwned((await ownedNow(io)).join(','))
}

/** Count a crash; at BREAKER_LIMIT hand the op back to Python for the rest of the session. */
export const noteCrash = async (io: Io, name: string): Promise<boolean> => {
  if ((await io.noteCrash(name)) < BREAKER_LIMIT) return false
  await io.disown(name)
  await announce(io)
  return true
}
