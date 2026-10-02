// graph_sync — mirror of hooks/ops/graph_sync.py (TASK-61/62, ported TASK-84 step 5b).
// PostToolUse(Edit|Write) on .agent/tasks/<PREFIX>-<n>*.md with an initialized graph runs
// task_to_graph.py --action add; TaskCreated/TaskCompleted do the same for a payload-named
// task doc. Edit|Write always answer {"ack": true} (the v6 `{}` doc); diagnostics go to stderr.
import { basename, isObject, pyJoin, relativeTo, runCaptured, syncLine } from '../lib/toolops-path'
import type { Json, Op, OpCtx, OpResult } from '../lib/types'

const V6_TOOLS = new Set(['Edit', 'Write'])
const LIFECYCLE_EVENTS = new Set(['TaskCreated', 'TaskCompleted'])
const LIFECYCLE_PATH_KEYS = ['task_path', 'file_path', 'path', 'task_file']
const TASK_PATH_RE = /\.agent\/tasks\/([A-Z][A-Z0-9]*[-_]\p{Nd}+[\p{L}\p{N}_\-.]*)\.md$/u
const SYNC_TIMEOUT_MS = 8000
const PREFIX = 'nav_task_graph_sync'

export type AckResult = OpResult & { ack?: true }

const validateTaskPath = async (ctx: OpCtx, candidate: unknown): Promise<string | null> => {
  if (typeof candidate !== 'string' || !candidate) return null
  const path = pyJoin(ctx.root, candidate)
  const rel = relativeTo(path, ctx.root)
  if (rel === null || !TASK_PATH_RE.test(rel)) return null
  return (await ctx.io.exists(path)) ? path : null
}

const lifecycleTaskPath = async (ctx: OpCtx): Promise<string | null> => {
  const task = ctx.payload.task
  const sources: Json[] = [ctx.payload, ...(isObject(task) ? [task] : [])]
  for (const source of sources) {
    for (const key of LIFECYCLE_PATH_KEYS) {
      const path = await validateTaskPath(ctx, source[key])
      if (path !== null) return path
    }
  }
  return null
}

const sync = async (ctx: OpCtx, taskPath: string, graphPath: string, lines: string[]): Promise<void> => {
  const syncer = `${ctx.io.pluginRoot}/skills/nav-graph/functions/task_to_graph.py`
  if (!(await ctx.io.exists(syncer))) {
    lines.push(`${PREFIX}: ${syncer} missing`)
    return
  }
  const outcome = await runCaptured(ctx.io, ['python3', syncer, '--action', 'add', '--task-path',
    taskPath, '--graph-path', graphPath], ctx.root, SYNC_TIMEOUT_MS)
  lines.push(syncLine(PREFIX, outcome, `${PREFIX}: upserted ${basename(taskPath)}`))
}

const run = async (ctx: OpCtx): Promise<OpResult | null> => {
  const graphPath = `${ctx.root}/.agent/knowledge/graph.json`
  if (LIFECYCLE_EVENTS.has(ctx.event)) {
    if (!(await ctx.io.exists(graphPath))) return null
    const taskPath = await lifecycleTaskPath(ctx)
    if (taskPath === null) return null
    const lines: string[] = []
    await sync(ctx, taskPath, graphPath, lines)
    return lines.length > 0 ? { stderr: lines.join('\n') } : null
  }
  if (!V6_TOOLS.has(String(ctx.payload.tool_name))) return null
  const result: AckResult = { ack: true }
  const lines: string[] = []
  if (await ctx.io.exists(graphPath)) {
    const input = isObject(ctx.payload.tool_input) ? ctx.payload.tool_input : {}
    const taskPath = await validateTaskPath(ctx, input.file_path)
    if (taskPath !== null) await sync(ctx, taskPath, graphPath, lines)
  }
  if (lines.length > 0) result.stderr = lines.join('\n')
  return result
}

export const graphSync: Op = {
  spec: { name: 'graph_sync', phase: 'recorders', configKey: 'task_graph_sync_hook' },
  run,
}
