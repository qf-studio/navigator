// setup — mirror of hooks/ops/setup.py (TASK-62, ported TASK-84 step 5d). Setup event: one
// line of runtime status, or the onboarding hint when `.agent/` is missing.
import { getPath } from '../lib/config'
import { fromJs, isFile, pyStr, statOf, truthy } from '../lib/life-py'
import type { Op, OpCtx, OpResult } from '../lib/types'

export const ONBOARDING_HINT =
  'Navigator is not initialized in this project (.agent/ missing). '
  + 'The nav-init skill scaffolds it: say "Initialize Navigator in this project".'

const run = async (ctx: OpCtx): Promise<OpResult | null> => {
  const agent = `${ctx.root}/.agent`
  if ((await statOf(ctx.io, agent))?.kind !== 'dir') return { system_message: ONBOARDING_HINT }
  const version = fromJs(getPath(ctx.config, 'version', null))
  const versionText = truthy(version) ? `v${pyStr(version)}` : 'unversioned'
  const dispatcherOn = truthy(fromJs(getPath(ctx.config, 'dispatcher.enabled', true)))
  const graph = await isFile(ctx.io, `${agent}/knowledge/graph.json`)
  const state = await isFile(ctx.io, `${agent}/.nav-runtime-state.json`)
  return {
    system_message: 'Navigator runtime status: '
      + `config ${versionText}; `
      + `dispatcher ${dispatcherOn ? 'on' : 'off'}; `
      + `knowledge graph ${graph ? 'present' : 'absent'}; `
      + `runtime state ${state ? 'present' : 'not yet written'}.`,
  }
}

export const setup: Op = {
  spec: { name: 'setup', phase: 'injectors', configKey: 'setup_hook' },
  run,
}
