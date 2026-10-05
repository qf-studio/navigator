// stop_completion — mirror of hooks/ops/stop_completion.py (TASK-62, ported TASK-84 step 5c).
// Stop-event forced-continuation gate: a mutating turn with unmet completion indicators and
// no exit signal gets ONE decision:block continuation (fuse, held_count cap, stop_hook_active).
// exit_gate.evaluate_exit is ported inline (min_heuristics=2 over the six-name vocabulary).
import { getPath } from '../lib/config'
import { stripAll } from '../lib/sentinels'
import { bashReadonly } from '../lib/stop-bash'
import { B, WS, isDict, pyInt, pyStrip, pyTruthy } from '../lib/stop-py'
import { sha256Hex } from '../lib/stop-sha256'
import { parseSignals } from '../lib/stop-signals'
import { type Evidence, turnScan } from '../lib/stop-transcript'
import type { Json, Op, OpCtx, OpResult } from '../lib/types'
import { TASK_ACTION_TOOLS } from './stop_state'

export const INDICATOR_VOCABULARY = [
  'code_committed', 'tests_passing', 'code_simplified', 'docs_updated', 'ticket_closed',
  'marker_created',
]
const MIN_HEURISTICS = 2
const DEFAULT_MAX_CONTINUES = 2
const GIT_TIMEOUT_MS = 2000
const TEST_CMD_RE = new RegExp(`${B}(make test|pytest|(python3?${WS}+-m${WS}+)?unittest)${B}`, 'u')

/** `git status --porcelain` at root: {exitCode, stdout}, or null when the call failed. */
const gitStatus = async (ctx: OpCtx): Promise<{ exitCode: number; stdout: string } | null> => {
  try {
    return await ctx.io.run(['git', 'status', '--porcelain'], ctx.root, GIT_TIMEOUT_MS)
  } catch {
    return null
  }
}

const gitClean = async (ctx: OpCtx): Promise<boolean> => {
  const r = await gitStatus(ctx)
  return r !== null && r.exitCode === 0 && !pyStrip(r.stdout)
}

const treeDigest = async (ctx: OpCtx): Promise<string | null> => {
  const r = await gitStatus(ctx)
  return r === null || r.exitCode !== 0 ? null : sha256Hex(r.stdout)
}

/**
 * stop_completion._turn_mutating (TASK-70/71 refinement of mem-037). `bashAllReadOnly` is the
 * mod's extra evidence (TASK-85): Claude Code marked every Bash call of the turn read-only, so a
 * Bash-only turn is not mutating whatever the allowlist says. Python has no such signal.
 */
export const turnMutating = (
  tools: Set<string>, evidence: Evidence, prev: unknown, digest: string | null, bashAllReadOnly = false,
): boolean => {
  const action = [...tools].filter(t => TASK_ACTION_TOOLS.has(t))
  if (action.length === 0) return false
  if (action.some(t => t !== 'Bash')) return true
  if (bashAllReadOnly) return false
  if (!evidence.bash.some(([cmd]) => !bashReadonly(cmd))) return false
  if (prev !== undefined && prev !== null && digest !== null && prev === digest) return false
  return true
}

// TASK-85: the tree digest is compared per session and kept in `tree.digests[session_id]`,
// outside the session-scoped `completion`, so a Stop in another session sharing this repo
// cannot erase it. Bounded to the most recent sessions (stop_completion.TREE_DIGESTS_MAX).
const TREE_DIGESTS_MAX = 8

const prevDigestOf = (ctx: OpCtx, completion: Json): unknown => {
  const sid = ctx.sessionId
  const tree = ctx.state.tree
  const digests = isDict(tree) ? tree.digests : undefined
  if (sid && isDict(digests) && typeof digests[sid] === 'string') return digests[sid]
  return completion.tree_digest
}

const recordDigest = (ctx: OpCtx, digest: string): void => {
  const sid = ctx.sessionId
  if (!sid) return
  const tree: Json = isDict(ctx.state.tree) ? ctx.state.tree : {}
  ctx.state.tree = tree
  const digests: Json = isDict(tree.digests) ? tree.digests : {}
  tree.digests = digests
  delete digests[sid]
  digests[sid] = digest
  for (const key of Object.keys(digests)) {
    if (Object.keys(digests).length <= TREE_DIGESTS_MAX) break
    delete digests[key]
  }
}

const deriveIndicators = async (ctx: OpCtx, evidence: Evidence): Promise<Record<string, boolean>> => {
  const ind: Record<string, boolean> = {}
  if (await gitClean(ctx)) ind.code_committed = true
  for (const [command, isError] of evidence.bash) {
    if (!isError && TEST_CMD_RE.test(command || '')) {
      ind.tests_passing = true
      break
    }
  }
  if (evidence.file_paths.some(p => p.endsWith('.md'))) ind.docs_updated = true
  if (evidence.file_paths.some(p => p.includes('/.context-markers/'))) ind.marker_created = true
  if (getPath(ctx.config, 'project_management', 'none') === 'none') ind.ticket_closed = true
  return ind
}

const maxContinues = (cfg: Json): number => {
  const result = pyInt(getPath(cfg, 'stop_completion.max_continues', DEFAULT_MAX_CONTINUES))
  return result === null || result < 0 ? DEFAULT_MAX_CONTINUES : result
}

const heldCount = (completion: Json): number => {
  const v = completion.held_count ?? 0
  return typeof v === 'number' ? Math.trunc(v) : 0
}

export const reasonText = (met: number, unmet: readonly string[]): string =>
  'Navigator stop_completion: this turn mutated the codebase but looks '
  + `unfinished — ${met}/${INDICATOR_VOCABULARY.length} completion indicators met `
  + `(unmet: ${unmet.join(', ')}) and no completion signal was emitted. `
  + 'Continue and finish the outstanding work (commit, tests, docs, ticket, '
  + 'marker — as applicable). When the task is genuinely complete, end your '
  + 'reply with an HTML-comment-wrapped exit signal so the user never sees '
  + 'it: <!-- nav-signal:v3:{"type":"exit","reason":"..."} --> . '
  + 'This forced continuation is single-shot for this turn.'

const run = async (ctx: OpCtx): Promise<OpResult | null> => {
  if (ctx.pilotExecutor) return null
  const payload = ctx.payload
  if (pyTruthy(payload.stop_hook_active)) return null
  if (!pyTruthy(getPath(ctx.config, 'stop_completion.enabled', false))) return null
  if (!pyTruthy(getPath(ctx.config, 'stop_completion.continue_enabled', false))) return null

  const stored = ctx.state.completion
  const completion: Json = isDict(stored) ? stored : {}
  const attach = (): void => {
    if (ctx.state.completion !== completion) ctx.state.completion = completion
  }
  const prevDigest = prevDigestOf(ctx, completion)
  const digest = await treeDigest(ctx)
  if (digest !== null && digest !== prevDigest) {
    attach()
    completion.tree_digest = digest
    recordDigest(ctx, digest)
  }
  if (pyTruthy(completion.stop_fuse)) return null
  const held = heldCount(completion)
  if (held >= maxContinues(ctx.config)) return null

  const [text, tools, evidence] = await turnScan(ctx.io, payload)
  if (!turnMutating(tools, evidence, prevDigest, digest, ctx.bashAllReadOnly === true)) return null
  if (parseSignals(stripAll(text)).some(sig => sig.type === 'exit')) return null

  const stateInd = isDict(completion.indicators) ? completion.indicators : {}
  const derived = await deriveIndicators(ctx, evidence)
  const filtered: Record<string, boolean> = {}
  for (const name of INDICATOR_VOCABULARY) filtered[name] = pyTruthy(stateInd[name]) || pyTruthy(derived[name])
  // exit_gate.evaluate_exit(filtered, exit_signal=False, min_heuristics=2)
  const met = INDICATOR_VOCABULARY.filter(name => filtered[name]).length
  if (met >= MIN_HEURISTICS) return null

  attach()
  completion.stop_fuse = true
  completion.held_count = held + 1
  completion.signal = { exit_seen: false, heuristics_met: met, held_at: ctx.now }
  const unmet = INDICATOR_VOCABULARY.filter(name => !filtered[name])
  return {
    decision: 'block',
    reason: reasonText(met, unmet),
    // TASK-88 reject log: what the gate saw, so an over-fire shows in one grep.
    reject: {
      reason: `mutating turn, ${met}/${INDICATOR_VOCABULARY.length} indicators met, no exit signal`,
      evidence: { met, unmet, mutating_tools: [...tools].filter(t => TASK_ACTION_TOOLS.has(t)).sort() },
    },
  }
}

export const stopCompletion: Op = {
  spec: { name: 'stop_completion', phase: 'gates', configKey: 'stop_completion' },
  run,
}
