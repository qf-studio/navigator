// read_guard — mirror of hooks/ops/read_guard.py (TASK-61, ported TASK-84 step 5b).
// PreToolUse(Read): counts non-allowlisted `.agent/` reads per turn, idempotent per
// tool_use_id; warns at warn_threshold, blocks (exit 2 + sentinel stderr) at
// escalate_threshold when strict_block. No Pilot check on purpose (the runner's belt strips
// the block under Pilot, as in v7).
import { getPath } from '../lib/config'
import { wrap } from '../lib/sentinels'
import { isObject, pyJoin, relativeTo } from '../lib/toolops-path'
import type { Json, Op, OpCtx, OpResult } from '../lib/types'

const DEFAULT_ALLOWLIST = [
  'DEVELOPMENT-README.md', '.nav-config.json', '.user-profile.json', 'knowledge/graph.json',
  'research/',
]
const MAX_SEEN_TOOL_USES = 64

const int = (v: unknown): number => Math.trunc(Number(v))

const allowlist = (cfg: Json): string[] => {
  const value = getPath(cfg, 'read_guard_hook.allowlist')
  return Array.isArray(value) ? value.map(String) : DEFAULT_ALLOWLIST
}

const isAllowlisted = (rel: string, allow: readonly string[]): boolean =>
  allow.includes(rel) || allow.some(e => e.endsWith('/') && rel.startsWith(e))

const isStale = (updatedAt: unknown, staleAfter: number, now: number): boolean => {
  if (staleAfter <= 0) return false
  if (typeof updatedAt !== 'number') return false
  return now - updatedAt > staleAfter
}

const toolUseId = (payload: Json): string | null => {
  for (const key of ['tool_use_id', 'toolUseId']) {
    const v = payload[key]
    if (typeof v === 'string' && v) return v
  }
  return null
}

const increment = (ctx: OpCtx, staleAfter: number, id: string | null): number => {
  let reads: Json = isObject(ctx.state.reads) ? ctx.state.reads : {}
  if (isStale(reads.updated_at, staleAfter, ctx.now)) reads = {}
  const seen: unknown[] = Array.isArray(reads.seen_tool_uses) ? reads.seen_tool_uses : []
  let count = int(reads.turn_count ?? 0)
  if (id !== null && seen.includes(id)) {
    reads.turn_count = count
    ctx.state.reads = reads
    return count
  }
  count += 1
  reads.turn_count = count
  reads.updated_at = ctx.now
  if (id !== null) {
    seen.push(id)
    reads.seen_tool_uses = seen.slice(-MAX_SEEN_TOOL_USES)
  }
  ctx.state.reads = reads
  return count
}

export const blockText = (count: number, threshold: number): string => wrap('nav-read-guard-block',
  `Navigator nav-read-guard: blocked at ${count} .agent/ reads `
  + `(escalate_threshold=${threshold}).\n`
  + '  Why: this turn has crossed the bulk-load threshold. Sequential '
  + '.agent/ reads risk 50k+ token consumption and session crash.\n'
  + '  How to proceed (your choice):\n'
  + '    1. Use a Task or Explore agent for the remaining lookups — '
  + 'they read excerpts, not full files, and are designed for '
  + 'multi-file discovery.\n'
  + '    2. Split the work: end this turn, start a new one (the '
  + 'counter resets on every Stop event).\n'
  + '    3. Raise the threshold: set read_guard_hook.escalate_threshold '
  + 'to a higher number in .agent/.nav-config.json.\n'
  + '    4. Disable strict enforcement: set read_guard_hook.strict_block'
  + '=false in .agent/.nav-config.json.')

const run = async (ctx: OpCtx): Promise<OpResult | null> => {
  const payload = ctx.payload
  if (payload.tool_name !== 'Read') return null
  const input = isObject(payload.tool_input) ? payload.tool_input : {}
  const filePath = input.file_path
  if (typeof filePath !== 'string' || !filePath) return null
  const rel = relativeTo(pyJoin(ctx.root, filePath), `${ctx.root}/.agent`)
  if (rel === null) return null
  if (isAllowlisted(rel, allowlist(ctx.config))) return null
  const cfg = ctx.config
  const warnAt = int(getPath(cfg, 'read_guard_hook.warn_threshold', 3))
  const escalateAt = int(getPath(cfg, 'read_guard_hook.escalate_threshold', 5))
  const strict = getPath(cfg, 'read_guard_hook.strict_block', true)
  const staleAfter = int(getPath(cfg, 'read_guard_hook.stale_after_seconds', 300))
  const count = increment(ctx, staleAfter, toolUseId(payload))
  if (count >= escalateAt && strict) {
    return {
      exit_code: 2,
      stderr: blockText(count, escalateAt),
      // TASK-88 reject log: the path goes to the log file, never to stderr.
      reject: {
        reason: `${count} .agent/ reads this turn (escalate_threshold=${escalateAt})`,
        evidence: { path: rel, count, threshold: escalateAt },
      },
    }
  }
  if (count >= escalateAt) {
    return { stderr: `[nav-read-guard] ${count} .agent/ files read this turn. `
      + 'Bulk-load anti-pattern threshold crossed (risk: 50k+ tokens). '
      + 'Use a Task or Explore agent for multi-file discovery.' }
  }
  if (count >= warnAt) {
    return { stderr: `[nav-read-guard] ${count} .agent/ files read this turn. `
      + 'Navigator lazy-loading pattern: load only what the task needs. '
      + 'For broader surveys, use a Task or Explore agent.' }
  }
  return null
}

export const readGuard: Op = {
  spec: {
    name: 'read_guard', phase: 'gates', configKey: 'read_guard_hook',
    matcher: payload => payload.tool_name === 'Read',
  },
  run,
}
