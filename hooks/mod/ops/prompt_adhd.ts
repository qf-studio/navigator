// prompt_adhd — mirror of hooks/ops/prompt_adhd.py (TASK-82, ported TASK-84).
// Toggle phrases answer with decision:block (dropped prompt, zero model turn); while the
// resolved state is on, every other prompt carries the rule block.
import { getPath, readJson } from '../lib/config'
import { RULE_BLOCK, classify, personalBody, personalPath, resolve, toggleReason } from '../lib/adhd'
import { stripAll } from '../lib/sentinels'
import type { Op, OpCtx, OpResult } from '../lib/types'

const personalFile = async (ctx: OpCtx): Promise<string> => personalPath(await ctx.io.env())

const run = async (ctx: OpCtx): Promise<OpResult | null> => {
  if (ctx.pilotExecutor) return null
  const message = stripAll(String(ctx.payload.prompt ?? '')).trim()
  if (!message) return null
  const pinned = getPath(ctx.config, 'adhd_mode.on')
  const path = await personalFile(ctx)
  const kind = classify(message)
  if (kind !== null) {
    let wrote = false
    if (kind !== 'status') {
      wrote = await ctx.io.write(path, personalBody(kind === 'on', ctx.now * 1000))
        .then(() => true, () => false)
    }
    const resolved = resolve(pinned, (await readJson(ctx.io, path))?.on)
    return { decision: 'block', reason: toggleReason({ kind, pinned, resolved, path, wrote }) }
  }
  const { on } = resolve(pinned, (await readJson(ctx.io, path))?.on)
  return on ? { additional_context: RULE_BLOCK } : null
}

export const promptAdhd: Op = {
  spec: { name: 'prompt_adhd', phase: 'responders', configKey: 'adhd_mode' },
  run,
}
