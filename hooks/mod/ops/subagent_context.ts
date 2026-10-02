// subagent_context — mirror of hooks/ops/subagent_context.py (TASK-62, ported TASK-84 5d).
// SubagentStart: a declarative session snapshot (README current task, last marker, top-K
// memories), clamped to the 2k SubagentStart budget.
import { getPath } from '../lib/config'
import { clampCp, pyInt } from '../lib/life-budget'
import { PY_SPACE, cpSlice, safeRead, splitlines, statOf, strip } from '../lib/life-py'
import { recall } from '../lib/memory'
import type { Op, OpCtx, OpResult } from '../lib/types'

const TOP_K = 5
const RECALL_TIMEOUT_MS = 3000
const README_SCAN_CHARS = 20_000
const ACTIVE_TASK_MAX_CHARS = 160

// ^\s*(?:[-*]\s*)?\**current task\**\s*:\s*(.+?)\s*$  with IGNORECASE | MULTILINE
const S = `[${PY_SPACE}]`
const CURRENT_TASK_RE = new RegExp(
  `(?:^|(?<=\\n))${S}*(?:[-*]${S}*)?\\**current task\\**${S}*:${S}*([^\\n]+?)${S}*(?=\\n|$)`, 'iu')

export const activeTask = async (ctx: OpCtx): Promise<string | null> => {
  const text = await safeRead(ctx.io, `${ctx.root}/.agent/DEVELOPMENT-README.md`, README_SCAN_CHARS)
  if (!text) return null
  const m = CURRENT_TASK_RE.exec(text)
  if (!m?.[1]) return null
  const task = strip(m[1])
  return task ? cpSlice(task, 0, ACTIVE_TASK_MAX_CHARS) : null
}

export const lastMarker = async (ctx: OpCtx): Promise<string | null> => {
  const dir = `${ctx.root}/.agent/.context-markers`
  const active = strip((await safeRead(ctx.io, `${dir}/.active`, 200)) ?? '')
  if (active) return active
  try {
    const entries = (await ctx.io.list(dir)).filter(e => e.name.endsWith('.md'))
    let best: { name: string; mtimeMs: number } | null = null
    for (const e of entries) {
      const st = await statOf(ctx.io, `${dir}/${e.name}`)
      if (st?.kind !== 'file') continue
      if (best === null || st.mtimeMs > best.mtimeMs) best = { name: e.name, mtimeMs: st.mtimeMs }
    }
    return best?.name ?? null
  } catch {
    return null
  }
}

const topK = (summary: string, k: number): string =>
  splitlines(summary).filter(line => strip(line)).slice(0, Math.max(0, k)).join('\n')

const run = async (ctx: OpCtx): Promise<OpResult | null> => {
  const parts: string[] = []
  const task = await activeTask(ctx)
  if (task) parts.push(`Active task: ${task}.`)
  const marker = await lastMarker(ctx)
  if (marker) parts.push(`Last context marker: ${marker}.`)
  const k = pyInt(getPath(ctx.config, 'knowledge_graph.max_session_memories'), TOP_K)
  const memories = topK(await recall(ctx.io, ctx.root, { auto: true, limit: k, timeoutMs: RECALL_TIMEOUT_MS }), k)
  if (parts.length === 0 && !memories) return null
  const lines = ['Navigator session snapshot (main-session state, declarative):']
  if (parts.length > 0) lines.push(parts.join(' '))
  if (memories) lines.push('Relevant project memories:', memories)
  let text = clampCp(lines.join('\n'), 'SubagentStart')
  const budget = getPath(ctx.config, 'subagent_context.budget_chars', null)
  if (typeof budget === 'number' && Number.isInteger(budget) && budget > 0
    && budget < Array.from(text).length) text = cpSlice(text, 0, budget)
  return { additional_context: text }
}

export const subagentContext: Op = {
  spec: { name: 'subagent_context', phase: 'injectors', configKey: 'subagent_context' },
  run,
}
