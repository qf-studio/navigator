// prompt_modes — mirror of hooks/ops/prompt_modes.py (ADHD TASK-82, STE TASK-93).
// Toggle phrases answer with decision:block (dropped prompt, zero model turn); while any
// mode resolves on, every other prompt carries the active rule blocks in table order.
import { getPath, readJson } from '../lib/config'
import {
  MODES, type Mode, classify, injection, modeEnabled, personalBody, personalPath, resolve,
  toggleReason,
} from '../lib/reply_modes'
import { stripAll } from '../lib/sentinels'
import type { Op, OpCtx, OpResult } from '../lib/types'

const isEnabled = (ctx: OpCtx, mode: Mode): boolean =>
  modeEnabled(getPath(ctx.config, `${mode.configKey}.enabled`))

const resolved = async (ctx: OpCtx, mode: Mode, path: string) =>
  resolve(getPath(ctx.config, `${mode.configKey}.on`), (await readJson(ctx.io, path))?.on)

const run = async (ctx: OpCtx): Promise<OpResult | null> => {
  if (ctx.pilotExecutor) return null
  const message = stripAll(String(ctx.payload.prompt ?? '')).trim()
  if (!message) return null
  const env = await ctx.io.env()
  const hit = classify(message)
  if (hit !== null) {
    const { mode, kind } = hit
    const path = personalPath(env, mode)
    const enabled = isEnabled(ctx, mode)
    let wrote = false
    if (enabled && kind !== 'status') {
      wrote = await ctx.io.write(path, personalBody(kind === 'on', ctx.now * 1000))
        .then(() => true, () => false)
    }
    const pinned = getPath(ctx.config, `${mode.configKey}.on`)
    const r = await resolved(ctx, mode, path)
    return {
      decision: 'block',
      reason: toggleReason({ mode, kind, enabled, pinned, resolved: r, path, wrote }),
    }
  }
  const blocks: string[] = []
  for (const mode of MODES) {
    if (!isEnabled(ctx, mode)) continue
    if ((await resolved(ctx, mode, personalPath(env, mode))).on) blocks.push(mode.ruleBlock)
  }
  const context = injection(blocks)
  return context === null ? null : { additional_context: context }
}

export const promptModes: Op = {
  spec: { name: 'prompt_modes', phase: 'responders', configKey: 'reply_modes' },
  run,
}
