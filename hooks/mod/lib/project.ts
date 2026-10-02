// Project root and skill-script runner shared by ops and the UI.
import type { Io } from './types'

const parentOf = (dir: string): string | null => {
  const at = dir.lastIndexOf('/')
  return at <= 0 ? null : dir.slice(0, at)
}

/** Nearest ancestor of `start` (default: session cwd) holding `.agent/`, as hio.project_root. */
export const projectRoot = async (io: Io, start?: string): Promise<string | null> => {
  let dir: string | null = start ?? (await io.cwd())
  while (dir !== null) {
    if (await io.exists(`${dir}/.agent`)) return dir
    dir = parentOf(dir)
  }
  return null
}

/** Run a command in `cwd`; stdout on exit 0, '' on any failure (fail-open, like v7). */
export const run = async (
  io: Io, argv: readonly string[], cwd: string, timeoutMs = 5000,
): Promise<string> => {
  try {
    const r = await io.run(argv, cwd, timeoutMs)
    return r.exitCode === 0 ? r.stdout : ''
  } catch {
    return ''
  }
}

/** Run a skill script shipped with the plugin (`skills/<skill>/functions/<file>`). */
export const runSkill = async (
  io: Io, script: string, args: readonly string[], cwd: string, timeoutMs = 5000,
): Promise<string> => run(io, ['python3', `${io.pluginRoot}/skills/${script}`, ...args], cwd, timeoutMs)
