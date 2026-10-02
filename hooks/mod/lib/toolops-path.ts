// Helpers shared by the tool-event ops (TASK-84 step 5b). Pure except `runCaptured`, which
// only calls through the Io port.
//
// Python's ops resolve paths with Path.resolve() (realpath: `..` collapsed, symlinks
// followed). The mod has no realpath, so `normalize` collapses `.`/`..` lexically; a path that
// reaches `.agent/` only through a symlink is classified differently (documented delta).
import type { Io } from './types'

/** Python `Path(root) / candidate` rendering: drop empty and `.` segments, keep `..`. */
export const pyJoin = (root: string, candidate: string): string => {
  const base = candidate.startsWith('/') ? candidate : `${root}/${candidate}`
  const parts = base.split('/').filter(p => p !== '' && p !== '.')
  return `/${parts.join('/')}`
}

/** Lexical resolve: collapse `.` and `..` (the realpath stand-in). */
export const normalize = (path: string): string => {
  const out: string[] = []
  for (const part of path.split('/')) {
    if (part === '' || part === '.') continue
    if (part === '..') out.pop()
    else out.push(part)
  }
  return `/${out.join('/')}`
}

/** `path.resolve().relative_to(base.resolve()).as_posix()`, or null when outside `base`. */
export const relativeTo = (path: string, base: string): string | null => {
  const p = normalize(path)
  const b = normalize(base)
  if (p === b) return '.'
  const prefix = b === '/' ? '/' : `${b}/`
  return p.startsWith(prefix) ? p.slice(prefix.length) : null
}

export const basename = (path: string): string => path.split('/').filter(Boolean).pop() ?? ''

/** Python `str.strip()` (Unicode whitespace plus the \x1c-\x1f, \x85 separators). */
export const pyStrip = (s: string): string =>
  s.replace(/^[\s\u001c-\u001f\u0085]+|[\s\u001c-\u001f\u0085]+$/gu, '')

/** Python `str[:n]` on code points. */
export const pyHead = (s: string, n: number): string => Array.from(s).slice(0, n).join('')

/** Python `str.splitlines()`; LINE/PARAGRAPH SEPARATOR built from code points. */
const LINE_BREAKS = new RegExp(
  `\\r\\n|[\\n\\r\\v\\f\\x1c-\\x1e\\x85${String.fromCharCode(0x2028, 0x2029)}]`, 'u')

export const pySplitLines = (s: string): string[] => {
  const lines = s.split(LINE_BREAKS)
  if (lines.length > 0 && lines[lines.length - 1] === '') lines.pop()
  return lines
}


export const isObject = (v: unknown): v is Record<string, unknown> =>
  v !== null && typeof v === 'object' && !Array.isArray(v)

/** True when a `$.process.run` rejection means the timeout fired (wording is to-check). */
export const isTimeout = (error: unknown): boolean =>
  error instanceof Error
  && (error.name === 'TimeoutError' || /time(d)?\s?out|still running/i.test(error.message))

export type RunOutcome =
  | { kind: 'done'; exitCode: number; stdout: string; stderr: string }
  | { kind: 'timeout' }
  | { kind: 'failure'; message: string }

/** Run with stderr when the port offers it; classify rejections like subprocess.run. */
export const runCaptured = async (
  io: Io, argv: readonly string[], cwd: string, timeoutMs: number,
): Promise<RunOutcome> => {
  try {
    if (io.runCapture) {
      const r = await io.runCapture(argv, cwd, timeoutMs)
      return { kind: 'done', exitCode: r.exitCode, stdout: r.stdout, stderr: r.stderr }
    }
    const r = await io.run(argv, cwd, timeoutMs)
    return { kind: 'done', exitCode: r.exitCode, stdout: r.stdout, stderr: '' }
  } catch (error) {
    if (isTimeout(error)) return { kind: 'timeout' }
    return { kind: 'failure', message: error instanceof Error ? error.message : String(error) }
  }
}

/** The v6 diagnostic for a finished sync subprocess, or the timeout/failure line. */
export const syncLine = (prefix: string, outcome: RunOutcome, success: string): string => {
  if (outcome.kind === 'timeout') return `${prefix}: subprocess timeout`
  if (outcome.kind === 'failure') return `${prefix}: subprocess failure: ${outcome.message}`
  if (outcome.exitCode !== 0) {
    const detail = pyHead(pyStrip(outcome.stderr || outcome.stdout), 300)
    return `${prefix}: sync failed (rc=${outcome.exitCode}): ${detail}`
  }
  return success
}
