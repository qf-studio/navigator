// Port of nav_hook_lib/judge.py (TASK-79/80, ported TASK-84): the TypeSafe typed judge.
// One request per prompt answers eight questions; decisive axes override the heuristics.
// Differences from Python, by platform: the key env var is fixed to TYPESAFE_API_KEY (the
// mod can read only literal env names), and the timeout is a race against $.clock.sleep
// ($.http.fetch has no timeout option).
import {
  AMBIGUITY_LEVELS, AMBIGUITY_WEIGHTS, COMPLEXITY_LEVELS, DIMENSIONS, JUDGE_DEFAULTS, QUESTIONS,
  REDACTED,
} from './gen/judge-data.gen'
import type { Judgment } from './scoring'
import type { Io, Json } from './types'

export type JudgeSettings = typeof JUDGE_DEFAULTS & Json
type Thresholds = { min_confidence: number; noul_low: number; noul_high: number }

const W = '[\\p{L}\\p{N}_]'
const B = `(?:(?<=${W})(?!${W})|(?<!${W})(?=${W}))`
const SECRET_PATTERNS: RegExp[] = [
  new RegExp(`${B}(?:api[_-]?key|token|secret|password|passwd|bearer)\\s*[:=]\\s*['"]?\\S+`, 'giu'),
  new RegExp(`${B}apikey_[A-Za-z0-9_]{16,}`, 'gu'),
  new RegExp(`${B}sk-[A-Za-z0-9_\\-]{16,}`, 'gu'),
  new RegExp(`${B}(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}`, 'gu'),
  new RegExp(`${B}AKIA[0-9A-Z]{16}${B}`, 'gu'),
  new RegExp(`${B}xox[abprs]-[A-Za-z0-9\\-]{10,}`, 'gu'),
  new RegExp(`${B}eyJ[A-Za-z0-9_\\-]{8,}\\.[A-Za-z0-9_\\-]{8,}\\.[A-Za-z0-9_\\-]{8,}`, 'gu'),
  new RegExp(`${B}[0-9a-f]{40,}${B}`, 'gu'),
]

export const redactSecrets = (text: string): string =>
  SECRET_PATTERNS.reduce((t, p) => t.replace(p, REDACTED), text)

export const settings = (cfg: Json | null): JudgeSettings => {
  const block = cfg?.judge
  return { ...JUDGE_DEFAULTS, ...(block && typeof block === 'object' ? (block as Json) : {}) } as JudgeSettings
}

const thresholdsOf = (s: JudgeSettings): Thresholds => ({
  min_confidence: Number(s.min_confidence ?? JUDGE_DEFAULTS.min_confidence),
  noul_low: Number(s.noul_low ?? JUDGE_DEFAULTS.noul_low),
  noul_high: Number(s.noul_high ?? JUDGE_DEFAULTS.noul_high),
})

/** Python slicing on code points: `text[:cap]`. */
const head = (text: string, cap: number): string => Array.from(text).slice(0, cap).join('')

export const buildRequest = (prompt: string, s: JudgeSettings): Json => ({
  state: head(redactSecrets(prompt ?? ''), Number(s.max_state_chars || JUDGE_DEFAULTS.max_state_chars)),
  model: String(s.model || JUDGE_DEFAULTS.model),
  questions: QUESTIONS,
})

export const decide = (p: unknown, t: Thresholds): boolean | null => {
  const v = typeof p === 'number' ? p : Number.parseFloat(String(p))
  if (Number.isNaN(v)) return null
  if (v >= t.noul_high) return true
  if (v <= t.noul_low) return false
  return null
}

/** Python round() on a float: banker's rounding at .5. */
const pyRound = (x: number): number => {
  const f = Math.floor(x)
  const d = x - f
  if (d === 0.5) return f % 2 === 0 ? f : f + 1
  return Math.round(x)
}

const levelName = (levels: readonly string[], normalized: number): string => {
  const index = pyRound(Math.max(0, Math.min(1, normalized)) * (levels.length - 1))
  return (levels[index] ?? '').split(':', 1)[0] ?? ''
}

type Answer = { noul?: number; score?: number; confidence?: number; probabilities?: Record<string, number> }

const scoreOf = (
  answers: Record<string, Answer>, name: string, levels: readonly string[],
  weights?: readonly number[],
): [number, number] => {
  const entry = answers[name]
  if (entry === undefined) throw new Error(`missing answer ${name}`)
  const top = levels.length - 1
  const probs = entry.probabilities
  let value: number
  if (weights !== undefined && probs && Object.keys(probs).length > 0) {
    value = levels.reduce((sum, _, i) => sum + Number(probs[String(i)] ?? 0) * (weights[i] ?? 0), 0)
  } else {
    if (entry.score === undefined) throw new Error(`missing score ${name}`)
    value = Number(entry.score) / top
  }
  return [Math.max(0, Math.min(1, value)), Number(entry.confidence ?? 0)]
}

const noul = (answers: Record<string, Answer>, name: string): number => {
  const v = answers[name]?.noul
  if (v === undefined) throw new Error(`missing noul ${name}`)
  return Number(v)
}

/** Map the API document onto a Judgment. Throws on a malformed shape (caller fails open). */
export const parseResponse = (doc: Json, t: Thresholds, latencyMs = 0): Judgment => {
  const answers = doc.answers as Record<string, Answer>
  const [complexity, complexityConf] = scoreOf(answers, 'complexity', COMPLEXITY_LEVELS)
  const [ambiguity, ambiguityConf] = scoreOf(answers, 'ambiguity', AMBIGUITY_LEVELS, AMBIGUITY_WEIGHTS)
  const dims: Record<string, number> = {}
  for (const d of DIMENSIONS) dims[d] = noul(answers, `${d}_defined`)
  const isTask = noul(answers, 'is_task')
  const wantsLoop = noul(answers, 'wants_loop')
  return {
    model: String(doc.model ?? ''),
    latencyMs,
    taskVerdict: () => decide(isTask, t),
    loopVerdict: () => decide(wantsLoop, t),
    complexityIfConfident: () => (complexityConf >= t.min_confidence ? complexity : null),
    ambiguityIfConfident: () => (ambiguityConf >= t.min_confidence ? ambiguity : null),
    dimensionVerdict: name => (name in dims ? decide(dims[name], t) : null),
    complexityLevel: () => levelName(COMPLEXITY_LEVELS, complexity),
  }
}

const expandHome = (path: string, home: string | undefined): string =>
  path.startsWith('~/') && home ? `${home}${path.slice(1)}` : path

/** Env var first, then the key file; null when neither yields a key. Never logged. */
export const apiKey = async (io: Io, s: JudgeSettings): Promise<string | null> => {
  const env = await io.env()
  const fromEnv = (env.TYPESAFE_API_KEY ?? '').trim()
  if (fromEnv) return fromEnv
  try {
    const path = expandHome(String(s.api_key_file || JUDGE_DEFAULTS.api_key_file), env.HOME)
    const first = (await io.read(path)).trim().split('\n')[0]?.trim() ?? ''
    return first || null
  } catch {
    return null
  }
}

/** One request; a Judgment, or null on any failure or timeout. Never throws. */
export const call = async (io: Io, prompt: string, s: JudgeSettings): Promise<Judgment | null> => {
  try {
    const key = await apiKey(io, s)
    if (!key || !(prompt ?? '').trim()) return null
    const started = await io.nowMs()
    const timeoutMs = Number(s.timeout_ms || JUDGE_DEFAULTS.timeout_ms)
    const response = await Promise.race([
      io.http(String(s.endpoint || JUDGE_DEFAULTS.endpoint), {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${key}`,
          'Content-Type': 'application/json',
          'User-Agent': 'navigator-judge/1',
        },
        body: JSON.stringify(buildRequest(prompt, s)),
      }),
      io.sleep(timeoutMs).then(() => null),
    ])
    if (response === null || !response.ok) return null
    const doc = JSON.parse(response.text) as Json
    return parseResponse(doc, thresholdsOf(s), Math.round((await io.nowMs()) - started))
  } catch {
    return null
  }
}

/** Feature-gated entry: null unless `judge.enabled`, outside Pilot. */
export const judgePrompt = async (
  io: Io, prompt: string, cfg: Json, pilotExecutor: boolean,
): Promise<Judgment | null> => {
  const s = settings(cfg)
  if (!s.enabled || pilotExecutor) return null
  return call(io, prompt, s)
}

export { thresholdsOf }

// ---- per-event cache and telemetry (judge.for_ctx / record_call / record_axes) ---------

const AXES = ['loop', 'complexity', 'task', 'ambiguity']
const OUTCOMES = ['overridden', 'agreed', 'undecided']

const section = (state: Json): Json => {
  const block = state.judge
  if (block !== null && typeof block === 'object' && !Array.isArray(block)) return block as Json
  const fresh: Json = {}
  state.judge = fresh
  return fresh
}

const int = (v: unknown): number => (typeof v === 'number' ? Math.trunc(v) : 0)

export const recordCall = (state: Json, judgment: Judgment | null, enabled: boolean): void => {
  if (!enabled) return
  const b = section(state)
  b.calls = int(b.calls) + 1
  if (judgment === null) {
    b.failed = int(b.failed) + 1
    return
  }
  b.model = judgment.model
  b.latency_last_ms = Math.trunc(judgment.latencyMs)
  b.latency_max_ms = Math.max(int(b.latency_max_ms), Math.trunc(judgment.latencyMs))
}

export const recordAxes = (state: Json, axes: Record<string, string> | undefined): void => {
  if (!axes || Object.keys(axes).length === 0) return
  const b = section(state)
  const table = (b.axes !== null && typeof b.axes === 'object' ? b.axes : {}) as Record<string, Json>
  b.axes = table
  for (const [axis, outcome] of Object.entries(axes)) {
    if (!AXES.includes(axis) || !OUTCOMES.includes(outcome)) continue
    const row = table[axis] ?? {}
    row[outcome] = int(row[outcome]) + 1
    table[axis] = row
  }
}

/** The judgment for this event, computed once and shared by gate and brief. */
export const forCtx = async (
  ctx: { io: Io; config: Json; pilotExecutor: boolean; state: Json; judgment?: unknown },
  message: string,
): Promise<Judgment | null> => {
  if (ctx.judgment !== undefined) return ctx.judgment as Judgment | null
  const judgment = await judgePrompt(ctx.io, message, ctx.config, ctx.pilotExecutor)
  ctx.judgment = judgment
  recordCall(ctx.state, judgment, Boolean(settings(ctx.config).enabled) && !ctx.pilotExecutor)
  return judgment
}
