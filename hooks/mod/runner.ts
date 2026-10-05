// The mod's dispatch pipeline, mirror of nav_hook_lib.runtime._dispatch (TASK-84):
// phases gates > responders > injectors > recorders, gate short-circuit, Pilot belt,
// per-op crash isolation with a breaker, merge in registry order.
import { clamp } from './lib/budget'
import { configAllows, getPath } from './lib/config'
import { appendReject, rejectLine } from './lib/rejects'
import { isoUtc, save } from './lib/state'
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
export const merge = (
  event: string, results: readonly OpResult[], leading: string | null = null,
): Merged => {
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
  if (leading) contexts.unshift(leading) // health line survives the clamp (runtime parity)
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

const ERROR_TEXT_LIMIT = 200
export const HEALTH_FILE = '.agent/.nav-dispatch-health.json'

/** runtime._describe_error: class name only, never the message (it can carry prompt text). */
export const describeError = (error: unknown): string =>
  error instanceof Error ? error.name
    : String(error).split(/\s+/).filter(Boolean).join(' ').slice(0, ERROR_TEXT_LIMIT)

/** runtime._handle_op_crash: op_errors note + health file the next SessionStart surfaces once. */
const noteOpError = async (ctx: OpCtx, op: string, error: unknown): Promise<void> => {
  const text = describeError(error)
  const ts = isoUtc(ctx.now)
  const meta = (ctx.state.meta ?? {}) as Record<string, unknown>
  const list = Array.isArray(meta.op_errors) ? meta.op_errors : []
  list.push({ op, error: text, ts })
  meta.op_errors = list
  ctx.state.meta = meta
  const doc = { last_error: { ts, event: ctx.event, op, error: text }, surfaced: false }
  await ctx.io.write(`${ctx.root}/${HEALTH_FILE}`, `${JSON.stringify(doc, null, 2)}\n`).catch(() => {})
}

/**
 * runtime._log_reject: THE one reject-log append point in the mod (TASK-88). The `reject` key
 * is always stripped; a line is written only for a result that actually blocks, when
 * `reject_log.enabled` holds. Under Pilot the belt strips the block next, so the line says
 * `suppressed: true`. A failed append never reaches the op or the user.
 */
const logReject = async (ctx: OpCtx, op: string, result: OpResult): Promise<OpResult> => {
  if (!('reject' in result)) return result
  const { reject, ...cleaned } = result
  if (!reject || typeof reject !== 'object' || !isBlocking(cleaned)) return cleaned
  if (getPath(ctx.config, 'reject_log.enabled', true) !== true) return cleaned
  const toolEvent = ctx.event === 'PreToolUse' || ctx.event === 'PostToolUse'
  const tool = toolEvent && typeof ctx.payload.tool_name === 'string' ? ctx.payload.tool_name : null
  const line = rejectLine(isoUtc(ctx.now), ctx.sessionId, ctx.event, op, tool, reject, ctx.pilotExecutor)
  await appendReject(ctx.io, ctx.root, line).catch(() => false)
  return cleaned
}

export const runOps = async (
  ctx: OpCtx, ops: readonly Op[], leading: string | null = null,
): Promise<Merged> => {
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
      await noteOpError(ctx, op.spec.name, error)
      await noteCrash(ctx.io, op.spec.name)
      continue
    }
    if (!result) continue
    result = await logReject(ctx, op.spec.name, result)
    if (ctx.pilotExecutor) result = suppressBlocking(result)
    if (isGate && isBlocking(result)) gateBlocked = true
    outcomes.push({ index, result })
  }
  return merge(ctx.event, outcomes.sort((a, b) => a.index - b.index).map(o => o.result), leading)
}

/** One event end to end: run the ops, then persist the shared runtime state once. */
export const runEvent = async (
  ctx: OpCtx, ops: readonly Op[], leading: string | null = null,
): Promise<Merged> => {
  const merged = await runOps(ctx, ops, leading)
  await save(ctx.io, ctx.root, ctx.state as never, ctx.sessionId, ctx.now)
  return merged
}
