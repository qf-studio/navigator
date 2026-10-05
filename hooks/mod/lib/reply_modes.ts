// Reply modes (ADHD TASK-82, STE TASK-93), mirrored from hooks/nav_hook_lib/reply_modes.py
// and hooks/ops/prompt_modes.py. Pure: no `$` here. The op does the I/O and feeds these
// functions. Every mode is one row in MODES; adding a mode is adding a row here and the
// mirrored row in the Python table. Table order is injection order: reply-shape rules
// (ADHD) before sentence rules (STE), so the later block applies inside the earlier one.

export const OP_CONFIG_KEY = 'reply_modes'
export const MAX_PHRASE_CHARS = 32

export type Mode = {
  key: string         // short word in toggle phrases: "adhd mode on"
  label: string       // human label in answers: "ADHD mode: on"
  configKey: string   // repo block: <configKey>.enabled / <configKey>.on
  stateName: string   // personal file: ~/.config/navigator/<stateName>.json
  ruleBlock: string
  extraOn: readonly string[]
  extraOff: readonly string[]
}

export const ADHD_RULE_BLOCK = `ADHD MODE: on (personal setting; "adhd mode off" ends it)
The reader has ADHD. The reply shape that works for them:
- First line: the ONE next action. Time-critical items first, the deadline in bold.
- Bullets over prose. Lists hold at most 5 items; longer ones split into now / later.
- Multi-step work: numbered, one bounded action per step, "step k of n" restated each turn.
- Several things pending: the single most important one is named, not a flat list.
- Errors: cause and fix in a flat tone. Wins stated plainly.
- No preamble, no recap, no pleasantries. The reply ends with one action under two minutes.
Kept in full regardless: error output, test results, anything the user asked to have
explained, and every warning before a destructive action.
Applies to replies only, not to files, reports or commit messages.`

export const STE_RULE_BLOCK = `STE MODE: on (personal setting; "ste mode off" ends it)
The reader wants ASD-STE100 Simplified Technical English. The sentence style that works:
- One idea per sentence. Instructions have 20 words or fewer, descriptions 25 or fewer.
- Instructions use the imperative. Descriptions use the active voice and the present tense.
- One instruction per sentence. A paragraph has one topic and six sentences or fewer.
- No gerunds, no noun clusters over three words, no synonyms for one meaning.
- Full sentences with articles, not labels. Technical names stay as written in the code.
Error output, test results and quoted text stay verbatim. Applies to replies only, inside
any reply-shape rules above.`

export const MODES: readonly Mode[] = [
  { key: 'adhd', label: 'ADHD', configKey: 'adhd_mode', stateName: 'adhd-mode',
    ruleBlock: ADHD_RULE_BLOCK, extraOn: [], extraOff: [] },
  { key: 'ste', label: 'STE', configKey: 'ste_mode', stateName: 'ste-mode',
    ruleBlock: STE_RULE_BLOCK, extraOn: ['use ste'], extraOff: ['stop ste'] },
]

export const byKey = (key: string): Mode | undefined => MODES.find(m => m.key === key)
export const byConfigKey = (configKey: string): Mode | undefined =>
  MODES.find(m => m.configKey === configKey)

// Exact toggle phrases (after normalize). Deliberately no fuzzy matching: a prompt that
// merely mentions a mode must never flip its switch.
export const onPhrases = (m: Mode): Set<string> => new Set([
  `${m.key} mode on`, `${m.key} mode: on`, `${m.key} on`, `enable ${m.key} mode`,
  `start ${m.key} mode`, `turn on ${m.key} mode`, `${m.key} mode enable`, ...m.extraOn,
])
export const offPhrases = (m: Mode): Set<string> => new Set([
  `${m.key} mode off`, `${m.key} mode: off`, `${m.key} off`, `disable ${m.key} mode`,
  `stop ${m.key} mode`, `turn off ${m.key} mode`, `${m.key} mode disable`, ...m.extraOff,
])
export const statusPhrases = (m: Mode): Set<string> => new Set([
  `${m.key} mode`, `${m.key} mode?`, `${m.key} mode status`, `${m.key} status`,
])

export type Toggle = 'on' | 'off' | 'status'
export type Source = 'repo' | 'personal' | 'default'
export type Resolved = { on: boolean; source: Source }

export type EnvVars = {
  NAVIGATOR_CONFIG_HOME?: string
  XDG_CONFIG_HOME?: string
  HOME?: string
}

const normalize = (text: string): string =>
  text.trim().toLowerCase().replace(/\s+/g, ' ').replace(/[ .!]+$/, '').trim()

/** { mode, kind } for an exact toggle phrase of any mode, else null. */
export const classify = (prompt: string): { mode: Mode; kind: Toggle } | null => {
  if (!prompt || prompt.length > MAX_PHRASE_CHARS) return null
  const phrase = normalize(prompt)
  for (const mode of MODES) {
    if (onPhrases(mode).has(phrase)) return { mode, kind: 'on' }
    if (offPhrases(mode).has(phrase)) return { mode, kind: 'off' }
    if (statusPhrases(mode).has(phrase)) return { mode, kind: 'status' }
  }
  return null
}

/** The personal Navigator config dir; same precedence as nav_hook_lib.personal.config_home(). */
export const personalDir = (env: EnvVars): string =>
  env.NAVIGATOR_CONFIG_HOME
    ? env.NAVIGATOR_CONFIG_HOME
    : `${env.XDG_CONFIG_HOME ?? `${env.HOME ?? '~'}/.config`}/navigator`

export const personalPath = (env: EnvVars, mode: Mode): string =>
  `${personalDir(env)}/${mode.stateName}.json`

/** `<configKey>.enabled` — the mode's machinery is available (default true). */
export const modeEnabled = (enabled: unknown): boolean => enabled === undefined || enabled === null
  ? true
  : Boolean(enabled)

/** Repo pin (true/false) wins; a personal bool next; else off by default. */
export const resolve = (pinned: unknown, personal: unknown): Resolved => {
  if (typeof pinned === 'boolean') return { on: pinned, source: 'repo' }
  if (typeof personal === 'boolean') return { on: personal, source: 'personal' }
  return { on: false, source: 'default' }
}

/** One human line for status answers; '' when off by default. */
export const statusLine = (mode: Mode, r: Resolved, path: string): string => {
  if (r.source === 'default') return ''
  const where = r.source === 'repo'
    ? `pinned by repo config ${mode.configKey}.on`
    : `personal switch, ${path}`
  return `${mode.label} mode: ${r.on ? 'on' : 'off'} (${where}).`
}

/** Rule blocks of every enabled mode that resolves on, joined in table order; null when none. */
export const injection = (blocks: readonly string[]): string | null =>
  blocks.length > 0 ? blocks.join('\n\n') : null

export type ToggleOutcome = {
  mode: Mode
  kind: Toggle
  enabled: boolean
  pinned: unknown
  resolved: Resolved
  path: string
  wrote: boolean
}

/** The reason text a dropped toggle prompt shows; mirrors prompt_modes._toggle_reason. */
export const toggleReason = (o: ToggleOutcome): string => {
  const { label, key: word, configKey } = o.mode
  if (!o.enabled) {
    return `${label} mode: disabled in this repo (${configKey}.enabled is false ` +
      'in .agent/.nav-config.json or the .local override). Nothing changed.'
  }
  if (o.kind === 'status') {
    const line = statusLine(o.mode, o.resolved, o.path) || `${label} mode: off (never switched on).`
    return `${line} Say "${word} mode on" or "${word} mode off".`
  }
  const wanted = o.kind === 'on'
  if (!o.wrote) {
    return `${label} mode: could not write the personal switch (${o.path}). Nothing changed.`
  }
  const state = wanted ? 'on' : 'off'
  if (typeof o.pinned === 'boolean') {
    return `${label} mode: personal switch set to ${state}, but this repo pins it ` +
      `${o.pinned ? 'on' : 'off'} via ${configKey}.on in .agent/.nav-config.json ` +
      '(or the .local override). Remove the pin for the switch to apply here.'
  }
  const tail = wanted
    ? `Applies from your next prompt, in every repo. Say "${word} mode off" to stop.`
    : 'The rule block is no longer injected anywhere.'
  return `${label} mode: ${state} (personal, ${o.path}). ${tail}`
}

/** The personal file's body, same keys as reply_modes.set_personal (seconds precision, UTC). */
export const personalBody = (on: boolean, nowMs: number): string => {
  const stamp = new Date(Math.floor(nowMs / 1000) * 1000).toISOString().replace('.000Z', '+00:00')
  return `${JSON.stringify({ on, updated: stamp }, null, 2)}\n`
}
