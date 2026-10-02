// failure_diagnosis — mirror of hooks/ops/failure_diagnosis.py (TASK-62, ported TASK-84 5b).
// PostToolUseFailure: recall graph pitfalls for the tool name + error tokens; keep only PITFALL
// lines sharing a >=4-char token with the error. Raw error text is never echoed back.
import { recall } from '../lib/memory'
import { stripAll } from '../lib/sentinels'
import { isObject, pySplitLines, pyStrip } from '../lib/toolops-path'
import type { Json, Op, OpCtx, OpResult } from '../lib/types'

const RECALL_LIMIT = 5
const RECALL_TIMEOUT_MS = 3000
const MAX_ERROR_TOKENS = 8
const MAX_LINES = 3
const TOKEN_RE = /[a-z][a-z0-9_-]{3,}/g
const STOPWORDS = new Set([
  'error', 'errors', 'failed', 'failure', 'exception', 'traceback',
  'cannot', 'could', 'would', 'should', 'with', 'from', 'when', 'that',
  'this', 'file', 'line', 'does', 'have', 'been', 'while', 'into',
])
// Python `\b` after PITFALL: the next character must not be a (Unicode) word character.
const PITFALL_LINE_RE = /^\s*-\s*PITFALL(?![\p{L}\p{N}_])/iu

const nonBlank = (v: unknown): v is string => typeof v === 'string' && pyStrip(v) !== ''

export const errorText = (payload: Json): string => {
  for (const key of ['error', 'error_message', 'message']) {
    const v = payload[key]
    if (nonBlank(v)) return v
  }
  const response = payload.tool_response
  if (nonBlank(response)) return response
  if (isObject(response)) {
    for (const key of ['error', 'stderr', 'message']) {
      const v = response[key]
      if (nonBlank(v)) return v
    }
  }
  return ''
}

export const errorTokens = (text: string): string[] => {
  const out: string[] = []
  for (const token of text.toLowerCase().match(TOKEN_RE) ?? []) {
    if (STOPWORDS.has(token) || out.includes(token)) continue
    out.push(token)
    if (out.length >= MAX_ERROR_TOKENS) break
  }
  return out
}

const matchingPitfallLines = (summary: string, tokens: readonly string[]): string[] => {
  const matched: string[] = []
  for (const line of pySplitLines(summary)) {
    if (!PITFALL_LINE_RE.test(line)) continue
    const lowered = line.toLowerCase()
    if (tokens.some(t => lowered.includes(t))) matched.push(pyStrip(line))
    if (matched.length >= MAX_LINES) break
  }
  return matched
}

const run = async (ctx: OpCtx): Promise<OpResult | null> => {
  const toolName = ctx.payload.tool_name
  if (typeof toolName !== 'string' || !toolName) return null
  const tokens = errorTokens(stripAll(errorText(ctx.payload)))
  if (tokens.length === 0) return null
  const summary = await recall(ctx.io, ctx.root, {
    concepts: [toolName.toLowerCase(), ...tokens], limit: RECALL_LIMIT, timeoutMs: RECALL_TIMEOUT_MS,
  })
  if (!summary) return null
  const matched = matchingPitfallLines(summary, tokens)
  if (matched.length === 0) return null
  const header = `Recorded pitfall(s) in the project knowledge graph matching this ${toolName} failure:`
  return { additional_context: [header, ...matched].join('\n') }
}

export const failureDiagnosis: Op = {
  spec: { name: 'failure_diagnosis', phase: 'injectors', configKey: 'failure_diagnosis' },
  run,
}
