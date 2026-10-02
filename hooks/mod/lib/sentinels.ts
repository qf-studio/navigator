// Mirror of nav_hook_lib/sentinels.py strip_all/wrap; tag table generated from Python.
import { TAGS } from './gen/sentinels.gen'

type Tag = keyof typeof TAGS

const escape = (s: string): string => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

const BLOCK_PATTERNS = Object.values(TAGS)
  .filter(t => t.kind === 'block' && t.close !== null)
  .map(t => new RegExp(`${escape(t.open)}[\\s\\S]*?${escape(t.close as string)}`, 'g'))

const ORIGINAL_PROMPT_LINE = /^\s*Original prompt:.*$/gm

export const wrap = (tag: Tag, text: string): string => {
  const spec = TAGS[tag]
  return spec.kind === 'block' ? `${spec.open}\n${text}\n${spec.close}` : `${spec.open}\n${text}`
}

/** Remove every registered sentinel; drop `Original prompt:` lines only if one was removed. */
export const stripAll = (text: string): string => {
  if (!text) return text
  let out = text
  for (const pattern of BLOCK_PATTERNS) out = out.replace(pattern, '')
  for (const spec of Object.values(TAGS)) {
    out = out.split(spec.open).join('')
    if (spec.close !== null) out = out.split(spec.close).join('')
  }
  return out !== text ? out.replace(ORIGINAL_PROMPT_LINE, '') : out
}

export const REDACTION_PLACEHOLDER = '[redacted]'

/** sentinels.redact_phrases: replace each phrase case-insensitively with the placeholder. */
export const redactPhrases = (text: string, phrases: readonly string[]): string =>
  phrases.filter(Boolean).reduce(
    (t, p) => t.replace(new RegExp(p.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&'), 'giu'), REDACTION_PLACEHOLDER),
    text,
  )
