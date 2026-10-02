// Port of nav_hook_lib/memory.recall: compact ranked-memory summary or '' on any failure.
import type { Io } from './types'

export const recall = async (
  io: Io, root: string, opts: { concepts?: readonly string[]; auto?: boolean; limit?: number;
    timeoutMs?: number },
): Promise<string> => {
  const { concepts, auto = false, limit = 5, timeoutMs = 3000 } = opts
  if ((!concepts || concepts.length === 0) && !auto) return ''
  const graph = `${root}/.agent/knowledge/graph.json`
  if (!(await io.exists(graph))) return ''
  const argv = ['python3', `${io.pluginRoot}/skills/nav-graph/functions/memory_recall.py`]
  if (concepts && concepts.length > 0) argv.push('--concepts', concepts.join(','))
  if (auto) argv.push('--auto')
  argv.push('--agent-dir', `${root}/.agent`, '--graph-path', graph, '--limit', String(limit),
    '--format', 'compact')
  try {
    const r = await io.run(argv, root, timeoutMs)
    return r.exitCode === 0 ? r.stdout.trim() : ''
  } catch {
    return ''
  }
}
