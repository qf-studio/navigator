// jit_memory — mirror of hooks/ops/jit_memory.py (TASK-62, ported TASK-84 step 5b).
// PostToolUse(Edit|Write|MultiEdit|NotebookEdit): an edit to hooks/**.py injects the declarative
// mem-034/mem-035 summary once per session (jit.injected[] dedupe, session-scoped section).
import { isObject, pyJoin, relativeTo } from '../lib/toolops-path'
import type { Op, OpCtx, OpResult } from '../lib/types'

const MEMORY_IDS = ['mem-034', 'mem-035']
/** registry.MUTATING_TOOLS: the PostToolUse matcher for the edit-driven ops. */
export const MUTATING_TOOLS = new Set(['Edit', 'Write', 'MultiEdit', 'NotebookEdit'])
const HOOK_FILE_RE = /^hooks\/.+\.py$/u

export const PITFALL_CONTEXT =
  'Recorded Navigator pitfalls for code under hooks/ (knowledge graph, '
  + 'injected once per session):\n'
  + '- mem-034 (pitfall, 1.0): a UserPromptSubmit hook that exits 2 blocks '
  + 'the model from running entirely, and stderr that echoes the trigger '
  + 'phrase verbatim re-triggers the block recursively on later prompts.\n'
  + '- mem-035 (pitfall, 1.0): PreToolUse/PostToolUse plain stdout and '
  + 'additionalContext were silently dropped in v6 (live-verified v6.12.0); '
  + 'the TASK-57 spike memories, not harness docs, are the record of which '
  + 'hookSpecificOutput sub-channels actually deliver.'

export const editedHookFile = (payload: Record<string, unknown>, root: string): string | null => {
  const input = isObject(payload.tool_input) ? payload.tool_input : {}
  const candidate = input.file_path || input.notebook_path
  if (typeof candidate !== 'string' || !candidate) return null
  const rel = relativeTo(pyJoin(root, candidate), root)
  if (rel === null || !HOOK_FILE_RE.test(rel)) return null
  return rel
}

const run = async (ctx: OpCtx): Promise<OpResult | null> => {
  if (editedHookFile(ctx.payload, ctx.root) === null) return null
  if (ctx.state.jit === undefined) ctx.state.jit = {}
  const jit = ctx.state.jit
  if (!isObject(jit)) throw new TypeError('jit section is not an object') // Python crashes too
  let injected = jit.injected
  if (!Array.isArray(injected)) {
    injected = []
    jit.injected = injected
  }
  const list = injected as unknown[]
  if (MEMORY_IDS.every(id => list.includes(id))) return null
  for (const id of MEMORY_IDS) if (!list.includes(id)) list.push(id)
  return { additional_context: PITFALL_CONTEXT }
}

export const jitMemory: Op = {
  spec: {
    name: 'jit_memory', phase: 'injectors', configKey: 'jit_memory',
    matcher: payload => MUTATING_TOOLS.has(String(payload.tool_name)),
  },
  run,
}
