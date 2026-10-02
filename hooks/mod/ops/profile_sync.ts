// profile_sync — mirror of hooks/ops/profile_sync.py (TASK-61, ported TASK-84 step 5b).
// PostToolUse(Edit|Write) on .user-profile.json: when corrections[] grew past
// profile.last_synced_count, run correction_to_memory.py --action sync and advance the counter
// only on success. Edit|Write always answer {"ack": true}; diagnostics go to stderr.
import { readJson } from '../lib/config'
import { basename, isObject, pyJoin, runCaptured, syncLine } from '../lib/toolops-path'
import type { Op, OpCtx, OpResult } from '../lib/types'
import type { AckResult } from './graph_sync'
import { MUTATING_TOOLS } from './jit_memory'

const V6_TOOLS = new Set(['Edit', 'Write'])
const PROFILE_BASENAME = '.user-profile.json'
const SYNC_TIMEOUT_MS = 8000
const PREFIX = 'nav_profile_sync'

const profileWritePath = async (ctx: OpCtx): Promise<string | null> => {
  const input = isObject(ctx.payload.tool_input) ? ctx.payload.tool_input : {}
  const candidate = input.file_path
  if (typeof candidate !== 'string' || !candidate) return null
  const path = pyJoin(ctx.root, candidate)
  return basename(path) === PROFILE_BASENAME && (await ctx.io.exists(path)) ? path : null
}

const lastSynced = (ctx: OpCtx): number => {
  const section = ctx.state.profile
  if (!isObject(section)) return 0
  return Math.trunc(Number(section.last_synced_count || 0))
}

const sync = async (ctx: OpCtx, profilePath: string, lines: string[]): Promise<void> => {
  const profile = await readJson(ctx.io, profilePath)
  if (profile === null) return
  const corrections = profile.corrections || []
  const current = Array.isArray(corrections) ? corrections.length : 0
  const last = lastSynced(ctx)
  if (current <= last) return
  const graphPath = `${ctx.root}/.agent/knowledge/graph.json`
  if (!(await ctx.io.exists(graphPath))) return
  const syncer = `${ctx.io.pluginRoot}/skills/nav-graph/functions/correction_to_memory.py`
  if (!(await ctx.io.exists(syncer))) {
    lines.push(`${PREFIX}: ${syncer} missing`)
    return
  }
  const outcome = await runCaptured(ctx.io, ['python3', syncer, '--action', 'sync', '--profile-path',
    profilePath, '--graph-path', graphPath, '--last-synced', String(last)], ctx.root, SYNC_TIMEOUT_MS)
  lines.push(syncLine(PREFIX, outcome, `${PREFIX}: synced ${current - last} new correction(s)`))
  if (outcome.kind === 'done' && outcome.exitCode === 0) {
    if (!isObject(ctx.state.profile)) ctx.state.profile = {}
    ;(ctx.state.profile as Record<string, unknown>).last_synced_count = current
  }
}

const run = async (ctx: OpCtx): Promise<OpResult | null> => {
  if (!V6_TOOLS.has(String(ctx.payload.tool_name))) return null
  const result: AckResult = { ack: true }
  const lines: string[] = []
  const profilePath = await profileWritePath(ctx)
  if (profilePath !== null) await sync(ctx, profilePath, lines)
  if (lines.length > 0) result.stderr = lines.join('\n')
  return result
}

export const profileSync: Op = {
  spec: {
    name: 'profile_sync', phase: 'recorders', configKey: 'profile_sync_hook',
    matcher: payload => MUTATING_TOOLS.has(String(payload.tool_name)),
  },
  run,
}
