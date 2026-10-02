// stop_state — mirror of hooks/ops/stop_state.py (TASK-61, ported TASK-84 step 5c).
// Stop-event recorder: stamps the tristate turn.signals.check_shown from the last assistant
// turn and is THE turn-lifecycle reset barrel (reads counter, tier1/stop fuses, held count).
import { getPath } from '../lib/config'
import { stripAll } from '../lib/sentinels'
import { B, WS, isDict, pyLen, pyStrip, pyTruthy } from '../lib/stop-py'
import { lastAssistantTurn } from '../lib/stop-transcript'
import type { Io, Json, Op, OpCtx, OpResult } from '../lib/types'

const WORKFLOW_CHECK_RE = new RegExp(`WORKFLOW${WS}+CHECK`, 'iu')
const NAV_STATUS_RE = /NAVIGATOR_STATUS/iu
const LOOP_PHASE_RE = new RegExp(`${B}Phase:${WS}*(INIT|RESEARCH|IMPL|VERIFY|COMPLETE)${B}`, 'u')

/** Tool names that mean the turn acted on the codebase (shared with stop_completion). */
export const TASK_ACTION_TOOLS = new Set(['Edit', 'Write', 'MultiEdit', 'NotebookEdit', 'Bash', 'Task', 'Agent'])

/** The Python op's `{"ack": True}` (the dispatcher's bare `{}` acknowledgment). */
const ACK = { ack: true } as unknown as OpResult

const lastTurn = async (io: Io, payload: Json): Promise<[string, Set<string>]> => {
  const inline = payload.last_assistant_message
  if (typeof inline === 'string' && pyStrip(inline)) return [inline, new Set()]
  const tpath = payload.transcript_path
  if (!pyTruthy(tpath)) return ['', new Set()]
  return lastAssistantTurn(io, tpath)
}

/** THE single audited turn-lifecycle reset path (stop_state.reset_turn_slots). */
export const resetTurnSlots = (ctx: OpCtx): void => {
  if (getPath(ctx.config, 'read_guard_hook.enabled', true) !== false) ctx.state.reads = { turn_count: 0 }
  let completion = ctx.state.completion
  if (!isDict(completion)) {
    completion = {}
    ctx.state.completion = completion
  }
  const c = completion as Json
  c.tier1_fuse = false
  c.stop_fuse = false
  c.held_count = 0
}

const run = async (ctx: OpCtx): Promise<OpResult | null> => {
  if (pyTruthy(ctx.payload.stop_hook_active)) return ACK
  const [raw, tools] = await lastTurn(ctx.io, ctx.payload)
  const text = stripAll(raw)
  const checkPresent = WORKFLOW_CHECK_RE.test(text)
  const navStatus = NAV_STATUS_RE.test(text)
  const phase = LOOP_PHASE_RE.exec(text)?.[1] ?? null
  let checkShown: boolean | null = null
  if (checkPresent) checkShown = true
  else if ([...tools].some(t => TASK_ACTION_TOOLS.has(t))) checkShown = false
  ctx.state.turn = {
    signals: { check_shown: checkShown, nav_status_shown: navStatus, loop_phase: phase },
    assistant_text_chars: pyLen(text),
    tools_used: [...tools].sort(),
  }
  resetTurnSlots(ctx)
  return ACK
}

export const stopState: Op = {
  spec: { name: 'stop_state', phase: 'recorders', configKey: 'workflow_state_hook' },
  run,
}
