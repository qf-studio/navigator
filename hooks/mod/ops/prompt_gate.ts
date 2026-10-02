// prompt_gate — mirror of hooks/ops/prompt_gate.py (ported TASK-84). Loop-trigger and
// complexity soft-warn (WORKFLOW CHECK), and the strict block when the prior turn skipped its
// check while this prompt asks for autonomous iteration.
import { getPath } from '../lib/config'
import { LOOP_TRIGGERS } from '../lib/gen/scoring-data.gen'
import { forCtx, recordAxes } from '../lib/judge'
import { detectWorkflow, type Workflow } from '../lib/scoring'
import { redactPhrases, stripAll, wrap } from '../lib/sentinels'
import type { Json, Op, OpCtx, OpResult } from '../lib/types'

export const BLOCK_MESSAGE =
  'Navigator workflow_enforcer: blocked.\n'
  + '  Why: the prior assistant turn skipped its required workflow '
  + 'check block, but your prompt requests autonomous iteration.\n'
  + '  State: .agent/.nav-runtime-state.json turn.signals.check_shown=false\n'
  + '  How to proceed (your choice):\n'
  + '    1. Send any different prompt that does not request '
  + 'autonomous iteration. The next assistant response will '
  + 'restore state; then retry your original prompt.\n'
  + '    2. Edit .agent/.nav-runtime-state.json and set '
  + 'turn.signals.check_shown=true.\n'
  + '    3. Disable strict enforcement: set '
  + 'workflow_enforcer_hook.strict_block=false in '
  + '.agent/.nav-config.json.'

const priorCheckShown = (state: Json): unknown => {
  const turn = state.turn
  if (turn === null || typeof turn !== 'object') return null
  const signals = (turn as Json).signals
  if (signals === null || typeof signals !== 'object') return null
  return (signals as Json).check_shown ?? null
}

/** Python f"{x:17}" for str (left-aligned) and f"{x:<19}" for str/float. */
const padRight = (s: string, n: number): string => (s.length >= n ? s : s + ' '.repeat(n - s.length))
const pyFloat = (n: number): string => (Number.isInteger(n) ? `${n}.0` : `${n}`)

export const warnLines = (r: Workflow, taskModeEnabled: boolean): string[] => {
  const w: string[] = []
  if (r.loop_mode) {
    w.push(`⚠️  LOOP MODE TRIGGER DETECTED: '${r.loop_trigger ?? 'unknown'}'`)
    w.push('   Show NAVIGATOR_STATUS blocks and use EXIT_SIGNAL.')
  }
  if (r.task_mode && taskModeEnabled) {
    w.push(`⚠️  TASK MODE RECOMMENDED: complexity=${pyFloat(r.complexity)}`)
    w.push('   Show phase tracking (RESEARCH → IMPL → VERIFY → COMPLETE).')
  }
  if (w.length === 0) return []
  if (r.judge) w.push(`ℹ️  Judged by ${r.judge.model || 'judge'} (${r.judge.latency_ms} ms)`)
  return [...w,
    '',
    'Remember to show WORKFLOW CHECK block!',
    '┌─────────────────────────────────────┐',
    '│ WORKFLOW CHECK                      │',
    '├─────────────────────────────────────┤',
    `│ Loop trigger: ${padRight(r.loop_mode ? 'YES' : 'NO', 17)} │`,
    `│ Complexity: ${padRight(pyFloat(r.complexity), 19)} │`,
    `│ Mode: ${padRight(r.recommended_mode, 24)} │`,
    '└─────────────────────────────────────┘',
  ]
}

const run = async (ctx: OpCtx): Promise<OpResult | null> => {
  if (ctx.pilotExecutor) return null
  const message = stripAll(String(ctx.payload.prompt ?? ''))
  if (!message) return null
  const strict = Boolean(getPath(ctx.config, 'workflow_enforcer_hook.strict_block', true))
  const taskMode = Boolean(getPath(ctx.config, 'task_mode.enabled', true))
  const judgment = await forCtx(ctx, message)
  const result = detectWorkflow(message, judgment)
  recordAxes(ctx.state, result.judge?.axes)
  if (strict && result.loop_mode && priorCheckShown(ctx.state) === false) {
    return { exit_code: 2, stderr: redactPhrases(wrap('nav-workflow-block', BLOCK_MESSAGE), LOOP_TRIGGERS) }
  }
  const lines = warnLines(result, taskMode)
  return lines.length === 0 ? null : { additional_context: lines.join('\n') }
}

export const promptGate: Op = {
  spec: { name: 'prompt_gate', phase: 'gates', configKey: 'workflow_enforcer_hook' },
  run,
}
