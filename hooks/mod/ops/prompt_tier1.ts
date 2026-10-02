// prompt_tier1 — mirror of hooks/ops/prompt_tier1.py (TASK-62, ported TASK-84). Exact-match
// commands answered with a grot card at zero model invocation (decision:block → dropped
// prompt); near-identical re-prompts after a hit count as suspected false positives.
import { getPath, readJson } from '../lib/config'
import { stripAll } from '../lib/sentinels'
import type { Json, Op, OpCtx, OpResult } from '../lib/types'

export const ESCAPE_LINE = "reply 'ask claude' to run the model"
const MAX_PROMPT_CHARS = 48
const MAX_MARKERS_SHOWN = 10
const SIMILARITY_MAX_EXTRA_TOKENS = 3
const SIMILARITY_MIN_JACCARD = 0.6
const CARD_WIDTH = 60

const COMMANDS: Record<string, string> = {
  'nav stats': 'nav_stats',
  'show features': 'show_features',
  'list markers': 'list_markers',
  'graph health': 'graph_health',
  'nav version': 'nav_version',
}
const RULE_COMMANDS: Record<string, string> = Object.fromEntries(Object.entries(COMMANDS).map(([c, r]) => [r, c]))

const FEATURE_BLOCKS = [
  'task_mode', 'loop_mode', 'simplification', 'auto_update', 'knowledge_graph',
  'session_start_hook', 'workflow_enforcer_hook', 'brief_hook', 'read_guard_hook',
  'task_graph_sync_hook', 'profile_sync_hook', 'workflow_state_hook', 'compact_hook',
  'dispatcher', 'tier1', 'stop_completion', 'jit_memory', 'subagent_context',
  'failure_diagnosis', 'config_guard', 'setup_hook', 'judge',
]

/** Python len() counts code points; every glyph used is one column. */
const len = (s: string): number => Array.from(s).length
const fit = (text: unknown, width: number): string => {
  const t = Array.from(String(text))
  return t.length <= width ? t.join('') : `${t.slice(0, Math.max(0, width - 1)).join('')}…`
}

const border = (left: string, right: string, note: string): string => {
  let label = note ? ` ${note} ` : ''
  let fill = CARD_WIDTH - 3 - len(label)
  if (fill < 1) {
    label = ` ${fit(note, CARD_WIDTH - 6)} `
    fill = CARD_WIDTH - 3 - len(label)
  }
  return `${left}─${label}${'─'.repeat(fill)}${right}`
}

const row = (text: string): string => {
  const inner = CARD_WIDTH - 2
  const body = `  ${fit(text, inner - 2)}`
  return `│${body}${' '.repeat(Math.max(0, inner - len(body)))}│`
}

export const card = (title: string, rows: readonly string[], footer: string): string =>
  [border('╭', '╮', title), row(''), ...rows.map(row), row(''), border('╰', '╯', footer)].join('\n')

const obj = (v: unknown): Json => (v !== null && typeof v === 'object' && !Array.isArray(v) ? (v as Json) : {})
const num = (v: unknown): unknown => (v === undefined ? 0 : v)
/** Python str() for the values these cards print (None → 'None', bool → 'True'). */
const py = (v: unknown): string =>
  v === null ? 'None' : v === true ? 'True' : v === false ? 'False' : String(v)

const graph = async (ctx: OpCtx): Promise<Json> =>
  (await readJson(ctx.io, `${ctx.root}/.agent/knowledge/graph.json`)) ?? {}

const markerNames = async (ctx: OpCtx): Promise<string[]> => {
  try {
    const entries = await ctx.io.list(`${ctx.root}/.agent/.context-markers`)
    return entries.filter(e => e.kind === 'file').map(e => e.name).sort()
  } catch {
    return []
  }
}

const judgeSummary = (state: Json): string[] => {
  const block = obj(state.judge)
  if (!block.calls) return []
  const totals: Record<string, number> = { overridden: 0, agreed: 0, undecided: 0 }
  for (const r of Object.values(obj(block.axes))) {
    for (const o of Object.keys(totals)) totals[o] = (totals[o] ?? 0) + Math.trunc(Number(obj(r)[o] ?? 0))
  }
  return [
    `judge: ${py(block.calls ?? 0)} calls / ${py(block.failed ?? 0)} failed · ${py(block.latency_last_ms ?? 0)} ms last, ${py(block.latency_max_ms ?? 0)} ms max`,
    `judge axes: ${totals.overridden} overridden / ${totals.agreed} agreed / ${totals.undecided} undecided`,
  ]
}

const answers: Record<string, (ctx: OpCtx) => Promise<string>> = {
  nav_stats: async ctx => {
    const stats = obj((await graph(ctx)).stats)
    const reads = obj(ctx.state.reads)
    const tier1 = obj(ctx.state.tier1)
    const meta = obj(ctx.state.meta)
    const errors = Array.isArray(meta.op_errors) ? meta.op_errors : []
    return card('nav stats · zero model tokens', [
      `graph: ${py(num(stats.total_nodes))} nodes / ${py(num(stats.total_edges))} edges / ${py(num(stats.memory_count))} memories`,
      `context markers: ${(await markerNames(ctx)).length}`,
      `reads this turn: ${py(num(reads.turn_count))}`,
      `tier1: ${py(num(tier1.hits))} hits / ${py(num(tier1.false_positives))} suspected false positives`,
      `recent op errors: ${errors.length}`,
      ...judgeSummary(ctx.state),
    ], ESCAPE_LINE)
  },
  show_features: async ctx => card('show features · <block>.enabled', FEATURE_BLOCKS.map(b => {
    const enabled = getPath(ctx.config, `${b}.enabled`, null)
    return `${b}: ${enabled === null ? 'unset' : enabled ? 'on' : 'off'}`
  }), ESCAPE_LINE),
  list_markers: async ctx => {
    const names = await markerNames(ctx)
    if (names.length === 0) return card('list markers', ['No context markers in .agent/.context-markers/'], ESCAPE_LINE)
    const rows = names.slice(-MAX_MARKERS_SHOWN)
    if (names.length > MAX_MARKERS_SHOWN) rows.unshift(`... showing the last ${MAX_MARKERS_SHOWN}`)
    return card(`list markers · ${names.length} total, newest last`, rows, ESCAPE_LINE)
  },
  graph_health: async ctx => {
    const g = await graph(ctx)
    if (Object.keys(g).length === 0) {
      return card('graph health', ['No knowledge graph (.agent/knowledge/graph.json missing)',
        "say 'Initialize knowledge graph' to build one"], ESCAPE_LINE)
    }
    const stats = obj(g.stats)
    const concepts = g.concept_index
    return card('graph health', [
      `schema version: ${py(g.version ?? '?')}`,
      `last updated: ${py(g.last_updated ?? '?')}`,
      `nodes: ${py(num(stats.total_nodes))} | edges: ${py(num(stats.total_edges))} | memories: ${py(num(stats.memory_count))}`,
      `indexed concepts: ${concepts !== null && typeof concepts === 'object' && !Array.isArray(concepts) ? Object.keys(concepts).length : 0}`,
    ], ESCAPE_LINE)
  },
  nav_version: async ctx => {
    const manifest = (await readJson(ctx.io, `${ctx.io.pluginRoot}/.claude-plugin/plugin.json`)) ?? {}
    const plugin = typeof manifest.version === 'string' && manifest.version ? manifest.version : 'unknown'
    const configVersion = ctx.config.version
    const line = typeof configVersion === 'string' ? configVersion : 'unset'
    const drift = plugin === 'unknown' || typeof configVersion !== 'string' ? 'undetermined'
      : plugin === configVersion ? 'none' : `config ${configVersion} != plugin ${plugin}`
    return card('nav version', [
      `Navigator plugin: ${plugin}`, `project config version: ${line}`, `version drift: ${drift}`,
    ], ESCAPE_LINE)
  },
}

const sectionOf = (state: Json, name: string): Json => {
  const s = state[name]
  if (s !== null && typeof s === 'object' && !Array.isArray(s)) return s as Json
  const fresh: Json = {}
  state[name] = fresh
  return fresh
}

const recordHit = (state: Json, rule: string): void => {
  sectionOf(state, 'turn').tier1_hit = rule
  sectionOf(state, 'completion').tier1_fuse = true
  const t = sectionOf(state, 'tier1')
  t.hits = Math.trunc(Number(t.hits ?? 0) || 0) + 1
}

const pySplit = (s: string): string[] => s.split(/[\s\u001c-\u001f\u0085]+/u).filter(Boolean)

export const isNearIdentical = (prompt: string, command: string): boolean => {
  if (prompt === command) return false
  const p = pySplit(prompt)
  const c = pySplit(command)
  if (p.length === 0 || c.length === 0) return false
  if (prompt.includes(command)) {
    const extra = p.length - c.length
    if (extra >= 0 && extra <= SIMILARITY_MAX_EXTRA_TOKENS) return true
  }
  const ps = new Set(p)
  const cs = new Set(c)
  const union = new Set([...ps, ...cs])
  const inter = [...ps].filter(x => cs.has(x)).length
  return union.size > 0 && inter / union.size >= SIMILARITY_MIN_JACCARD
}

const countFalsePositive = (state: Json, normalized: string): void => {
  const turn = state.turn
  if (turn === null || typeof turn !== 'object' || Array.isArray(turn)) return
  const command = RULE_COMMANDS[String((turn as Json).tier1_hit)]
  if (!command) return
  if (isNearIdentical(normalized, command)) {
    const t = sectionOf(state, 'tier1')
    t.false_positives = Math.trunc(Number(t.false_positives ?? 0) || 0) + 1
    delete (turn as Json).tier1_hit
  }
}

const PY_STRIP = /^[\s\u001c-\u001f\u0085]+|[\s\u001c-\u001f\u0085]+$/gu

const run = async (ctx: OpCtx): Promise<OpResult | null> => {
  if (ctx.pilotExecutor) return null
  if (!getPath(ctx.config, 'tier1.enabled', false)) return null
  const candidate = stripAll(String(ctx.payload.prompt ?? '')).replace(PY_STRIP, '')
  if (!candidate || len(candidate) > MAX_PROMPT_CHARS) return null
  const rule = COMMANDS[candidate.toLowerCase()]
  if (rule && getPath(ctx.config, `tier1.rules.${rule}`, true) !== false) {
    recordHit(ctx.state, rule)
    const build = answers[rule]
    return build ? { decision: 'block', reason: await build(ctx) } : null
  }
  countFalsePositive(ctx.state, pySplit(candidate.toLowerCase()).join(' '))
  return null
}

export const promptTier1: Op = {
  spec: { name: 'prompt_tier1', phase: 'responders', configKey: 'tier1' },
  run,
}
