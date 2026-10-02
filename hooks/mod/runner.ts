// The mod's dispatch pipeline, mirror of nav_hook_lib.runtime._dispatch (TASK-84):
// phases gates > responders > injectors > recorders, gate short-circuit, Pilot belt,
// per-op crash isolation with a breaker, merge in registry order.
import { clamp } from './lib/budget'
import { configAllows } from './lib/config'
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
  let reason: string | null = null
  let deny: string | null = null
  let exitText: string | null = null
  for (const r of results) {
    if (r.additional_context) contexts.push(r.additional_context)
    if (reason === null && r.decision === 'block') reason = r.reason ?? ''
    if (deny === null && r.permission_decision === 'deny') deny = r.permission_reason ?? ''
    if (exitText === null && typeof r.exit_code === 'number' && r.exit_code !== 0) {
      exitText = r.stderr ?? ''
    }
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
  }
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
    } catch {
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
