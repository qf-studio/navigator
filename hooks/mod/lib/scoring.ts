// Port of the runtime-used part of nav_hook_lib/scoring.py (TASK-84): loop triggers,
// additive message complexity, detect_workflow + judge overlay, and the ambiguity axis.
// Tables are generated from Python; parity is asserted over tests/fixtures/scoring.gen.ts.
//
// Python's `\b`, `\w`, `\d`, `\s` are Unicode-aware; JS `\b` is ASCII-only even with the
// `u` flag. W below is Python's word class ([\p{L}\p{N}_]) and B an exact `\b` emulation.
import {
  ACCEPTANCE_PHRASES, AMBIGUITY_DIMENSIONS, APPROACH_CONNECTORS, COMPLEXITY_INDICATORS,
  CONFIRMATION_MAX_WORDS, CONFIRMATION_PREFIXES, JUDGE_LOOP_PHRASE, LIMITER_WORDS, LOOP_TRIGGERS,
  MULTI_FILE_INDICATORS, QUESTION_STARTERS, SCORES, TASK_SHAPED_VERBS, VAGUE_SCOPE_SIGNALS,
} from './gen/scoring-data.gen'

const W = '[\\p{L}\\p{N}_]'
const B = `(?:(?<=${W})(?!${W})|(?<!${W})(?=${W}))`

// `-` stays unescaped: outside a class it is literal, and `\-` is a syntax error in `u` mode.
const escape = (s: string): string => s.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&')

const cache = new Map<string, RegExp>()
const re = (source: string, flags = 'u'): RegExp => {
  const key = `${flags}:${source}`
  let hit = cache.get(key)
  if (hit === undefined) {
    hit = new RegExp(source, flags)
    cache.set(key, hit)
  }
  return hit
}

/** Python round(x, 2) for the tenths-sums this module produces (half-even on ties). */
const round2 = (x: number): number => {
  const scaled = x * 100
  const floor = Math.floor(scaled)
  const diff = scaled - floor
  const eps = 1e-9
  if (Math.abs(diff - 0.5) < eps) return (floor % 2 === 0 ? floor : floor + 1) / 100
  return Math.round(scaled) / 100
}

/** Python `str.lower().strip()` analogues. */
const lower = (s: string): string => s.toLowerCase()
const PY_WS = /^[\s\u001c-\u001f\u0085]+|[\s\u001c-\u001f\u0085]+$/gu
const strip = (s: string): string => s.replace(PY_WS, '')
const rstrip = (s: string): string => s.replace(/[\s\u001c-\u001f\u0085]+$/u, '')

/** scoring.contains_phrase: whole-word match, case-sensitive (callers lower-case). */
export const containsPhrase = (text: string, phrase: string): boolean =>
  re(`${B}${escape(phrase)}${B}`).test(text)

/** scoring._amb_contains_phrase: like containsPhrase, multiword phrases tolerate \s+. */
const ambContainsPhrase = (text: string, phrase: string): boolean =>
  re(`${B}${phrase.split(' ').map(escape).join('\\s+')}${B}`).test(text)

export const detectLoopTrigger = (message: string): [boolean, string | null] => {
  const m = lower(message)
  for (const trigger of LOOP_TRIGGERS) if (containsPhrase(m, trigger)) return [true, trigger]
  return [false, null]
}

export const calculateMessageComplexity = (message: string): [number, string[]] => {
  const m = lower(message)
  let score = 0
  const matched: string[] = []
  for (const i of COMPLEXITY_INDICATORS.high) {
    if (containsPhrase(m, i)) { score += 0.3; matched.push(`high:${i}`) }
  }
  for (const i of COMPLEXITY_INDICATORS.medium) {
    if (containsPhrase(m, i)) { score += 0.2; matched.push(`medium:${i}`) }
  }
  for (const i of COMPLEXITY_INDICATORS.low) {
    if (containsPhrase(m, i)) { score += 0.1; matched.push(`low:${i}`) }
  }
  for (const i of MULTI_FILE_INDICATORS) {
    if (containsPhrase(m, i)) { score += 0.2; matched.push(`multi-file:${i}`); break }
  }
  return [Math.min(score, 1.0), matched]
}

/** The typed judge's verdicts, as the Python Judgment exposes them (lib/judge.ts). */
export type Judgment = {
  model: string
  latencyMs: number
  loopVerdict: () => boolean | null
  complexityIfConfident: () => number | null
  complexityLevel: () => string | null
  taskVerdict: () => boolean | null
  ambiguityIfConfident: () => number | null
  dimensionVerdict: (name: string) => boolean | null
}

type Axis = 'overridden' | 'agreed' | 'undecided'
export type JudgeInfo = {
  model: string; latency_ms: number; overrides: string[]; axes: Record<string, Axis>
}

export type Workflow = {
  loop_mode: boolean
  loop_trigger: string | null
  task_mode: boolean
  complexity: number
  complexity_indicators: string[]
  recommended_mode: 'LOOP' | 'TASK' | 'DIRECT'
  judge?: JudgeInfo
}

const applyJudgment = (
  j: Judgment, loop: boolean, phrase: string | null, complexity: number, indicators: string[],
  threshold = 0.5,
): [boolean, string | null, number, string[], JudgeInfo] => {
  const overrides: string[] = []
  const axes: Record<string, Axis> = {}
  const verdict = j.loopVerdict()
  if (verdict === null) axes.loop = 'undecided'
  else if (verdict !== loop) {
    loop = verdict
    phrase = verdict ? JUDGE_LOOP_PHRASE : null
    overrides.push('loop')
    axes.loop = 'overridden'
  } else axes.loop = 'agreed'
  const judged = j.complexityIfConfident()
  if (judged === null) axes.complexity = 'undecided'
  else {
    const same = (judged >= threshold) === (complexity >= threshold)
    axes.complexity = same ? 'agreed' : 'overridden'
    complexity = judged
    indicators = [`judge:${j.complexityLevel()}`]
    overrides.push('complexity')
  }
  return [loop, phrase, complexity, indicators,
    { model: j.model, latency_ms: j.latencyMs, overrides, axes }]
}

export const detectWorkflow = (message: string, judgment: Judgment | null = null): Workflow => {
  let [loop, phrase] = detectLoopTrigger(message)
  let [complexity, indicators] = calculateMessageComplexity(message)
  let info: JudgeInfo | null = null
  if (judgment !== null) {
    ;[loop, phrase, complexity, indicators, info] =
      applyJudgment(judgment, loop, phrase, complexity, indicators)
  }
  const taskMode = complexity >= 0.5
  const result: Workflow = {
    loop_mode: loop,
    loop_trigger: phrase,
    task_mode: taskMode,
    complexity: round2(complexity),
    complexity_indicators: indicators,
    recommended_mode: loop ? 'LOOP' : taskMode ? 'TASK' : 'DIRECT',
  }
  if (info !== null) result.judge = info
  return result
}

// ---- ambiguity axis -------------------------------------------------------------------

const WORD_RE = /[a-z']+/g
const PATH_RE = re(`[\\p{L}\\p{N}_.\\-]+/[\\p{L}\\p{N}_.\\-/]+`)
const FILE_RE = re(`${B}[\\p{L}\\p{N}_\\-]+\\.(?:py|ts|tsx|js|jsx|md|json|yaml|yml|go|rb|java|rs|css|html)${B}`, 'iu')
const NUMBER_RE = re(`${B}\\p{Nd}+(?:\\.\\p{Nd}+)?${B}`)

const words = (text: string): string[] => text.match(WORD_RE) ?? []

const firstMatch = (text: string, phrases: readonly string[]): string => {
  for (const p of phrases) if (ambContainsPhrase(text, p)) return p
  return ''
}

const isQuestion = (text: string): boolean => {
  if (rstrip(text).endsWith('?')) return true
  const w = words(text)
  return w.length > 0 && (QUESTION_STARTERS as readonly string[]).includes(w[0] as string)
}

const isConfirmation = (text: string): boolean => {
  const w = words(text)
  if (w.length === 0 || w.length > CONFIRMATION_MAX_WORDS) return false
  const normalized = w.join(' ')
  return CONFIRMATION_PREFIXES.some(p => {
    const bare = words(p).join(' ')
    return normalized === bare || normalized.startsWith(`${bare} `)
  })
}

export type Ambiguity = {
  score: number
  task_shaped: boolean
  undefined_dimensions: string[]
  matched_signals: string[]
  judge?: { axes: Record<string, Axis> }
}

const EMPTY: Ambiguity = { score: 0.0, task_shaped: false, undefined_dimensions: [], matched_signals: [] }

export const scoreAmbiguityHeuristic = (prompt: string): Ambiguity => {
  const text = strip(lower(prompt ?? ''))
  if (!text) return { ...EMPTY }
  if (isQuestion(text)) return { ...EMPTY, matched_signals: ['gate:question'] }
  if (isConfirmation(text)) return { ...EMPTY, matched_signals: ['gate:confirmation'] }
  const verb = firstMatch(text, TASK_SHAPED_VERBS)
  if (!verb) return { ...EMPTY }
  const signals = [`verb:${verb}`]
  let score = SCORES.BASE_SCORE
  const vague = firstMatch(text, VAGUE_SCOPE_SIGNALS)
  if (vague) { score += SCORES.VAGUE_BONUS; signals.push(`vague:${vague}`) }
  const hasFile = PATH_RE.test(prompt) || FILE_RE.test(prompt)
  const hasNumber = NUMBER_RE.test(text)
  const limiter = firstMatch(text, LIMITER_WORDS)
  const acceptance = firstMatch(text, ACCEPTANCE_PHRASES)
  const approach = firstMatch(text, APPROACH_CONNECTORS)
  if (hasFile) { score -= SCORES.CREDIT_FILE_PATH; signals.push('credit:file_path') }
  if (hasNumber) { score -= SCORES.CREDIT_NUMBER; signals.push('credit:number') }
  if (limiter) { score -= SCORES.CREDIT_LIMITER; signals.push(`credit:limiter:${limiter}`) }
  if (acceptance) { score -= SCORES.CREDIT_ACCEPTANCE; signals.push(`credit:acceptance:${acceptance}`) }
  const undef: string[] = []
  if (!hasFile) undef.push('scope')
  if (!limiter && !acceptance) undef.push('limits')
  if (!approach) undef.push('approach')
  if (!acceptance) undef.push('verification')
  return {
    score: round2(Math.max(0.0, Math.min(1.0, score))),
    task_shaped: true,
    undefined_dimensions: undef,
    matched_signals: signals,
  }
}

export const scoreAmbiguity = (prompt: string, judgment: Judgment | null = null): Ambiguity => {
  const h = scoreAmbiguityHeuristic(prompt)
  if (judgment === null) return h
  const tv = judgment.taskVerdict()
  const taskShaped = tv === null ? h.task_shaped : tv
  const axes: Record<string, Axis> = {}
  axes.task = tv === null ? 'undecided' : tv === h.task_shaped ? 'agreed' : 'overridden'
  if (!taskShaped) {
    return { score: 0.0, task_shaped: false, undefined_dimensions: [], matched_signals: [],
      judge: { axes } }
  }
  const signals = [...h.matched_signals]
  let score: number
  let heuristicUndefined: Set<string>
  if (h.task_shaped) {
    score = h.score
    heuristicUndefined = new Set(h.undefined_dimensions)
  } else {
    signals.push('judge:task')
    score = SCORES.BASE_SCORE
    heuristicUndefined = new Set(AMBIGUITY_DIMENSIONS)
  }
  const judged = judgment.ambiguityIfConfident()
  if (judged === null) axes.ambiguity = 'undecided'
  else {
    axes.ambiguity = (judged >= 0.5) === (score >= 0.5) ? 'agreed' : 'overridden'
    score = judged
    signals.push('judge:ambiguity')
  }
  const undef = AMBIGUITY_DIMENSIONS.filter(name => {
    const v = judgment.dimensionVerdict(name)
    return v === null ? heuristicUndefined.has(name) : !v
  })
  return {
    score: round2(Math.max(0.0, Math.min(1.0, score))),
    task_shaped: true,
    undefined_dimensions: [...undef],
    matched_signals: signals,
    judge: { axes },
  }
}
