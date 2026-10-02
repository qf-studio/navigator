// prompt_brief — mirror of hooks/ops/prompt_brief.py (ported TASK-84). Ambiguous task-shaped
// prompts get the NAV-BRIEF instruction plus relevant memories.
import { getPath } from '../lib/config'
import { forCtx, recordAxes } from '../lib/judge'
import { recall } from '../lib/memory'
import { type Ambiguity, scoreAmbiguity } from '../lib/scoring'
import { stripAll } from '../lib/sentinels'
import type { Op, OpCtx, OpResult } from '../lib/types'

const RECALL_TIMEOUT_MS = 3000
const RECALL_LIMIT = 5
const MAX_CONCEPTS = 8
const STOPWORDS = new Set([
  'this', 'that', 'these', 'those', 'with', 'from', 'into', 'onto',
  'over', 'under', 'about', 'after', 'before', 'please', 'then',
  'them', 'they', 'their', 'have', 'been', 'will', 'would', 'should',
  'could', 'make', 'sure', 'need', 'want', 'like', 'some', 'more',
  'when', 'what', 'where', 'which', 'until', 'done', 'everything',
])

export const extractConcepts = (message: string): string[] => {
  const out: string[] = []
  for (const token of message.toLowerCase().match(/[a-z][a-z\-_]{3,}/g) ?? []) {
    if (STOPWORDS.has(token) || out.includes(token)) continue
    out.push(token)
    if (out.length >= MAX_CONCEPTS) break
  }
  return out
}

/** Python str(float) for the score/threshold the brief prints. */
const pyNum = (n: number): string => (Number.isInteger(n) ? `${n}.0` : `${n}`)

export const briefLines = (
  r: Ambiguity, threshold: number, memories: string, contradiction = true,
): string[] => {
  const lines = [`🧭 NAV-BRIEF: ambiguous task-shaped prompt (score=${pyNum(r.score)}, threshold=${pyNum(threshold)})`]
  if (r.undefined_dimensions.length > 0) lines.push(`Undefined: ${r.undefined_dimensions.join(', ')}`)
  let fields = "  Goal | Scope | Approach | Limits | Verify | Won't do"
  if (contradiction) fields += ' | Contradiction'
  lines.push('', 'Render a one-screen INTENT BRIEF before writing any code:', fields)
  if (contradiction) {
    lines.push('Contradiction: "improving X worsens Y" or "none". If declared, '
      + 'query prior resolutions before Approach (skill: nav-brief).')
  }
  lines.push('Pre-fill defaults from the memories below when present. Max 2 open questions.',
    'Wait for user confirmation before implementation. (skill: nav-brief)')
  if (memories) lines.push('', '## Relevant Memories', memories)
  return lines
}

/** Python str slicing `text[:n]` on code points. */
const head = (text: string, n: number): string => Array.from(text).slice(0, n).join('')

const run = async (ctx: OpCtx): Promise<OpResult | null> => {
  if (ctx.pilotExecutor) return null
  const message = stripAll(String(ctx.payload.prompt ?? ''))
  if (!message) return null
  const threshold = Number(getPath(ctx.config, 'brief_hook.ambiguity_threshold', 0.5))
  const budget = Math.trunc(Number(getPath(ctx.config, 'brief_hook.memory_budget_chars', 1200)))
  const judgment = await forCtx(ctx, message)
  const result = scoreAmbiguity(message, judgment)
  recordAxes(ctx.state, result.judge?.axes)
  ctx.judgeAxes = { ...ctx.judgeAxes, ...result.judge?.axes }
  if (!result.task_shaped || result.score < threshold) return null
  const concepts = extractConcepts(message)
  const memories = concepts.length === 0 ? ''
    : head(await recall(ctx.io, ctx.root, { concepts, limit: RECALL_LIMIT, timeoutMs: RECALL_TIMEOUT_MS }), budget)
  const contradiction = Boolean(getPath(ctx.config, 'brief_hook.contradiction_field', true))
  return { additional_context: briefLines(result, threshold, memories, contradiction).join('\n') }
}

export const promptBrief: Op = {
  spec: { name: 'prompt_brief', phase: 'injectors', configKey: 'brief_hook' },
  run,
}
