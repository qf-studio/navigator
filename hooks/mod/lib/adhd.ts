// ADHD mode, mirrored from hooks/nav_hook_lib/adhd.py and hooks/ops/prompt_adhd.py.
// Pure: no `$` here. The hooks module does the I/O and feeds these functions.

export const RULE_BLOCK = `ADHD MODE: on (personal setting; "adhd mode off" ends it)
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

export const MAX_PHRASE_CHARS = 32

const ON_PHRASES = new Set([
  'adhd mode on', 'adhd mode: on', 'adhd on', 'enable adhd mode',
  'start adhd mode', 'turn on adhd mode', 'adhd mode enable',
])
const OFF_PHRASES = new Set([
  'adhd mode off', 'adhd mode: off', 'adhd off', 'disable adhd mode',
  'stop adhd mode', 'turn off adhd mode', 'adhd mode disable',
])
const STATUS_PHRASES = new Set(['adhd mode', 'adhd mode?', 'adhd mode status', 'adhd status'])

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

/** 'on' | 'off' | 'status' for an exact toggle phrase, else null. */
export const classify = (prompt: string): Toggle | null => {
  if (!prompt || prompt.length > MAX_PHRASE_CHARS) return null
  const phrase = normalize(prompt)
  if (ON_PHRASES.has(phrase)) return 'on'
  if (OFF_PHRASES.has(phrase)) return 'off'
  if (STATUS_PHRASES.has(phrase)) return 'status'
  return null
}

/** The personal Navigator config dir; same precedence as nav_hook_lib.personal.config_home(). */
export const personalDir = (env: EnvVars): string =>
  env.NAVIGATOR_CONFIG_HOME
    ? env.NAVIGATOR_CONFIG_HOME
    : `${env.XDG_CONFIG_HOME ?? `${env.HOME ?? '~'}/.config`}/navigator`

export const personalPath = (env: EnvVars): string => `${personalDir(env)}/adhd-mode.json`

/** Repo pin (true/false) wins; a personal bool next; else off by default. */
export const resolve = (pinned: unknown, personal: unknown): Resolved => {
  if (typeof pinned === 'boolean') return { on: pinned, source: 'repo' }
  if (typeof personal === 'boolean') return { on: personal, source: 'personal' }
  return { on: false, source: 'default' }
}

/** One human line for status answers; '' when off by default. */
export const statusLine = (r: Resolved, path: string): string => {
  if (r.source === 'default') return ''
  const where = r.source === 'repo'
    ? 'pinned by repo config adhd_mode.on'
    : `personal switch, ${path}`
  return `ADHD mode: ${r.on ? 'on' : 'off'} (${where}).`
}

export type ToggleOutcome = {
  kind: Toggle
  pinned: unknown
  resolved: Resolved
  path: string
  wrote: boolean
}

/** The reason text a dropped toggle prompt shows; mirrors prompt_adhd._toggle_reason. */
export const toggleReason = (o: ToggleOutcome): string => {
  if (o.kind === 'status') {
    const line = statusLine(o.resolved, o.path) || 'ADHD mode: off (never switched on).'
    return `${line} Say "adhd mode on" or "adhd mode off".`
  }
  const wanted = o.kind === 'on'
  if (!o.wrote) {
    return `ADHD mode: could not write the personal switch (${o.path}). Nothing changed.`
  }
  const state = wanted ? 'on' : 'off'
  if (typeof o.pinned === 'boolean') {
    return `ADHD mode: personal switch set to ${state}, but this repo pins it ` +
      `${o.pinned ? 'on' : 'off'} via adhd_mode.on in .agent/.nav-config.json ` +
      '(or the .local override). Remove the pin for the switch to apply here.'
  }
  const tail = wanted
    ? 'Applies from your next prompt, in every repo. Say "adhd mode off" to stop.'
    : 'The rule block is no longer injected anywhere.'
  return `ADHD mode: ${state} (personal, ${o.path}). ${tail}`
}

/** The personal file's body, same keys as adhd.set_personal (seconds precision, UTC). */
export const personalBody = (on: boolean, nowMs: number): string => {
  const stamp = new Date(Math.floor(nowMs / 1000) * 1000).toISOString().replace('.000Z', '+00:00')
  return `${JSON.stringify({ on, updated: stamp }, null, 2)}\n`
}
