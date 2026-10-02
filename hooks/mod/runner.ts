// The mod's dispatch pipeline, mirror of nav_hook_lib.runtime._dispatch (TASK-84):
// phases gates > responders > injectors > recorders, gate short-circuit, Pilot belt,
// per-op crash isolation with a breaker, merge in registry order.
import { clamp } from './lib/budget'
import { configAllows } from './lib/config'
import { save } from './lib/state'
import type { Merged, Op, OpCtx, OpResult } from './lib/types'
import { noteCrash, owns } from './owns'

const PHASE_RANK = { gates: 0, responders: 1, injectors: 2, recorders: 3 } as const

export const isBlocking = (r: OpResult): boolean =>
  Boolean(r.decision) || r.permission_decision === 'deny'
  || (typeof r.exit_code === 'number' && r.exit_code !== 0)

/** Pilot merge belt: strip every blocking key; non-blocking output passes through. */
export const suppressBlocking = (r: OpResult): OpResult => {
  const out: OpResult = { ...r }
  delete out.decision
  delete out.reason
  if (out.permission_decision === 'deny' || out.permission_decision === 'ask') {
    delete out.permission_decision
    delete out.permission_reason
  }
  if (typeof out.exit_code === 'number' && out.exit_code !== 0) delete out.exit_code
  if (out.continue_ === false) delete out.continue_
  return out
}

/** Fold op results (registry order) into what the mod returns for `event`. */
export const merge = (event: string, results: readonly OpResult[]): Merged => {
  const contexts: string[] = []
  const messages: string[] = []
  const notes: string[] = []
  let reason: string | null = null
  let deny: string | null = null
  let exitText: string | null = null
  for (const r of results) {
    if (r.additional_context) contexts.push(r.additional_context)
    if (reason === null && r.decision === 'block') reason = r.reason ?? ''
    if (deny === null && r.permission_decision === 'deny') deny = r.permission_reason ?? ''
    const blocking = typeof r.exit_code === 'number' && r.exit_code !== 0
    if (exitText === null && blocking) exitText = r.stderr ?? ''
    if (!blocking && r.stderr) notes.push(r.stderr)
    if (r.system_message) messages.push(r.system_message)
  }
  const context = contexts.length === 0 ? null : clamp(contexts.join('\n'), event)
  const prompt = event === 'UserPromptSubmit'
  const tool = event === 'PreToolUse'
  return {
    context: context === '' ? null : context,
    drop: prompt ? (reason ?? exitText) : null,
    deny: tool ? (deny ?? exitText) : null,
    block: !prompt && !tool ? reason : null,
    toast: messages.length === 0 ? null : messages.join('\n'),
    notes: notes.length === 0 ? null : notes.join('\n'),
  }
}

/** runtime._note_op_error: append {op, error, ts} to meta.op_errors (bounded on save). */
const noteOpError = (ctx: OpCtx, op: string, error: unknown): void => {
  const meta = (ctx.state.meta ?? {}) as Record<string, unknown>
  const list = Array.isArray(meta.op_errors) ? meta.op_errors : []
  const name = error instanceof Error ? error.name : typeof error
  list.push({ op, error: `${ctx.event}/${op}: ${name}`, ts: ctx.now })
  meta.op_errors = list
  ctx.state.meta = meta
}

export const runOps = async (ctx: OpCtx, ops: readonly Op[]): Promise<Merged> => {
  const ordered = ops
    .map((op, index) => ({ op, index }))
    .sort((a, b) => PHASE_RANK[a.op.spec.phase] - PHASE_RANK[b.op.spec.phase] || a.index - b.index)
  const outcomes: { index: number; result: OpResult }[] = []
  let gateBlocked = false
  for (const { op, index } of ordered) {
    const isGate = op.spec.phase === 'gates'
    if (!configAllows(ctx.config, op.spec)) continue
    if (!(await owns(ctx.io, op.spec.name))) continue
    if (op.spec.matcher && !op.spec.matcher(ctx.payload)) continue
    if (!isGate && gateBlocked) continue
    let result: OpResult | null
    try {
      result = await op.run(ctx)
    } catch (error) {
      noteOpError(ctx, op.spec.name, error)
      await noteCrash(ctx.io, op.spec.name)
      continue
    }
    if (!result) continue
    if (ctx.pilotExecutor) result = suppressBlocking(result)
    if (isGate && isBlocking(result)) gateBlocked = true
    outcomes.push({ index, result })
  }
  return merge(ctx.event, outcomes.sort((a, b) => a.index - b.index).map(o => o.result))
}

/** One event end to end: run the ops, then persist the shared runtime state once. */
export const runEvent = async (ctx: OpCtx, ops: readonly Op[]): Promise<Merged> => {
  const merged = await runOps(ctx, ops)
  await save(ctx.io, ctx.root, ctx.state as never, ctx.sessionId, ctx.now)
  return merged
}
