// compact_marker — mirror of hooks/ops/compact_marker.py (TASK-61, ported TASK-84 step 5d).
// PreCompact writes a heuristic marker (git state, in-progress tasks, transcript summary) and
// points .active at it; PostCompact appends Claude Code's compact summary to that marker.
import { getPath } from '../lib/config'
import { pyInt } from '../lib/life-budget'
import {
  JSONDecodeError, type PyValue, cpLen, cpSlice, dumps, fromJs, get, isDict, isFile, loads, pyStr,
  safeRead, splitlines, statOf, strip, stripChars, textOut, truthy, universalNewlines,
} from '../lib/life-py'
import type { Io, Op, OpCtx, OpResult } from '../lib/types'

export const NO_SUMMARY_PLACEHOLDER = '_[no summary provided by Claude Code]_'
export const PRE_COMPACT_NOTE =
  '_Written by Navigator PreCompact hook. The companion PostCompact hook '
  + "will append Claude Code's summary below once compact completes._"

const W = '[\\p{L}\\p{N}_]'
const B = `(?:(?<=${W})(?!${W})|(?<!${W})(?=${W}))`
// [\w./-]+\.(?:tsx|json|md|ts|py|sh|js)\b
const PATH_RE = new RegExp(`[\\p{L}\\p{N}_./-]+\\.(?:tsx|json|md|ts|py|sh|js)${B}`, 'gu')

const ACK = { ack: true } as unknown as OpResult

/** datetime.fromtimestamp(now) as calendar fields in the machine's local zone. */
const localParts = (io: Io, nowS: number) => {
  const ms = Math.floor(nowS * 1000)
  const offset = io.localOffsetMinutes ? io.localOffsetMinutes(ms) : -new Date(ms).getTimezoneOffset()
  const d = new Date(ms + offset * 60_000)
  const p2 = (n: number) => String(n).padStart(2, '0')
  return {
    date: `${d.getUTCFullYear()}-${p2(d.getUTCMonth() + 1)}-${p2(d.getUTCDate())}`,
    hm: `${p2(d.getUTCHours())}${p2(d.getUTCMinutes())}`,
    iso: `${d.getUTCFullYear()}-${p2(d.getUTCMonth() + 1)}-${p2(d.getUTCDate())}T`
      + `${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())}:${p2(d.getUTCSeconds())}`,
  }
}

/** `a or b or c` over PyValues. */
const or = (...vals: PyValue[]): PyValue => {
  for (const v of vals.slice(0, -1)) if (truthy(v)) return v
  return vals[vals.length - 1] ?? null
}

class Bail extends Error {}

export const flattenTranscript = async (io: Io, path: string): Promise<string> => {
  if (!(await isFile(io, path))) return ''
  const out: string[] = []
  try {
    const text = universalNewlines(await io.read(path))
    for (const line of text.split('\n')) {
      const raw = strip(line)
      if (!raw) continue
      let obj: PyValue
      try {
        obj = loads(raw)
      } catch (e) {
        if (e instanceof JSONDecodeError) { out.push(raw); continue }
        throw new Bail()
      }
      if (!isDict(obj)) throw new Bail()
      const msg = or(get(obj, 'message'), obj)
      const content = isDict(msg) ? get(msg, 'content') : null
      if (typeof content === 'string') out.push(content)
      else if (Array.isArray(content)) {
        for (const block of content) {
          if (!isDict(block)) continue
          const t = or(get(block, 'text'), get(block, 'input'), get(block, 'output'))
          if (typeof t === 'string') out.push(t)
          else if (t !== null) out.push(cpSlice(dumps(t), 0, 2000))
        }
      }
    }
  } catch {
    return ''
  }
  return out.join('\n')
}

const unique = (xs: readonly string[]): string[] => [...new Set(xs)]

export const compressContext = (text: string, maxLength = 5000): string => {
  if (!text) return '_[transcript unavailable]_'
  const lines = text.split('\n')
  const scan = lines.length > 200 ? [...lines.slice(0, 100), ...lines.slice(-100)] : lines
  const code: string[] = []
  const paths: string[] = []
  const errors: string[] = []
  let inCode = false
  let buffer: string[] = []
  for (const line of scan) {
    const stripped = strip(line)
    if (stripped.startsWith('```')) {
      if (inCode) {
        code.push(buffer.join('\n'))
        buffer = []
      }
      inCode = !inCode
    } else if (inCode) buffer.push(line)
    for (const m of line.matchAll(PATH_RE)) paths.push(m[0])
    const low = line.toLowerCase()
    if (low.includes('error') || low.includes('failed') || low.includes('traceback')) errors.push(stripped)
  }
  const recent = lines.slice(-20)
  const parts: string[] = []
  if (paths.length > 0) parts.push(`**Files/paths mentioned**:\n${unique(paths).slice(0, 10).join('\n')}`)
  if (code.length > 0) parts.push(`**Code snippets**:\n\`\`\`\n${code.slice(0, 3).join('\n\n')}\n\`\`\``)
  if (errors.length > 0) parts.push(`**Errors / issues**:\n${unique(errors).slice(0, 5).join('\n')}`)
  parts.push(`**Recent conversation**:\n${recent.join('\n')}`)
  let compressed = parts.join('\n\n---\n\n')
  if (cpLen(compressed) > maxLength) compressed = `${cpSlice(compressed, 0, maxLength)}\n\n[... truncated ...]`
  return compressed
}

const git = async (io: Io, args: string[], cwd: string): Promise<string | null> => {
  try {
    const r = await io.run(['git', ...args], cwd, 3000)
    return r.exitCode === 0 ? strip(textOut(r.stdout)) : null
  } catch {
    return null
  }
}

export const gitState = async (io: Io, root: string): Promise<string> => {
  const branch = (await git(io, ['rev-parse', '--abbrev-ref', 'HEAD'], root)) || '(unknown)'
  const head = (await git(io, ['log', '-1', '--oneline'], root)) || '(no commits)'
  const status = (await git(io, ['status', '--short'], root)) || ''
  const recent = (await git(io, ['log', '--oneline', '-5'], root)) || ''
  const parts = [`**Branch**: \`${branch}\``, `**HEAD**: \`${head}\``]
  parts.push(status ? `**Working tree**:\n\`\`\`\n${status}\n\`\`\`` : '**Working tree**: clean')
  if (recent) parts.push(`**Recent commits**:\n\`\`\`\n${recent}\n\`\`\``)
  return parts.join('\n\n')
}

/** sorted(dir.glob('*.md')) names: dotfiles and directories included, as pathlib does. */
export const globMd = async (io: Io, dir: string): Promise<string[]> =>
  (await io.list(dir)).map(e => e.name).filter(n => n.endsWith('.md')).sort()

const stem = (name: string): string => {
  const at = name.lastIndexOf('.')
  return at <= 0 ? name : name.slice(0, at)
}

export const titleOf = (head: string, name: string): string => {
  for (const line of splitlines(head)) {
    if (line.startsWith('#')) return strip(stripChars(line, '# ', 'left'))
  }
  return stem(name)
}

export const activeTaskHint = async (io: Io, root: string): Promise<string | null> => {
  const dir = `${root}/.agent/tasks`
  if ((await statOf(io, dir))?.kind !== 'dir') return null
  const candidates: string[] = []
  try {
    for (const name of await globMd(io, dir)) {
      if (name.toUpperCase().startsWith('README')) continue
      const head = (await safeRead(io, `${dir}/${name}`, 400)) ?? ''
      const low = head.toLowerCase()
      if (low.includes('in progress') || low.includes('in-progress') || head.includes('🚧')) {
        candidates.push(`- \`${name}\` — ${titleOf(head, name)}`)
      }
      if (candidates.length >= 5) break
    }
  } catch {
    return null
  }
  return candidates.length === 0 ? null : `**In-progress tasks**:\n${candidates.join('\n')}`
}

const expandUser = async (io: Io, p: string): Promise<string> => {
  if (p !== '~' && !p.startsWith('~/')) return p
  const home = (await io.env()).HOME
  return home ? home + p.slice(1) : p
}

type CompactCfg = { transcript: boolean; git: boolean; budget: number }

export const buildMarker = async (ctx: OpCtx, cfg: CompactCfg): Promise<[string, string]> => {
  const payload = ctx.payload
  let trigger = pyStr(or(fromJs(payload.trigger), 'manual'))
  if (trigger !== 'manual' && trigger !== 'auto') trigger = 'manual'
  const session = pyStr(or(fromJs(payload.session_id), 'unknown'))
  const now = localParts(ctx.io, ctx.now)
  const filename = `before-compact-${trigger}-${now.date}-${now.hm}.md`
  const desc = trigger === 'manual' ? 'user ran /compact' : 'Claude Code auto-compacted'
  const header = [
    `# Before Compact (${trigger})`, '',
    `**Date**: ${now.iso}`,
    `**Trigger**: \`${trigger}\` (${desc})`,
    `**Session**: \`${session}\``, '',
    PRE_COMPACT_NOTE, '',
  ]
  const sections = [header.join('\n')]
  if (cfg.git) sections.push(`## Git State\n\n${await gitState(ctx.io, ctx.root)}`)
  const hint = await activeTaskHint(ctx.io, ctx.root)
  if (hint) sections.push(`## Active Tasks\n\n${hint}`)
  if (cfg.transcript) {
    const raw = fromJs(payload.transcript_path)
    let summary: string
    if (truthy(raw)) {
      const flat = await flattenTranscript(ctx.io, await expandUser(ctx.io, pyStr(raw)))
      summary = compressContext(flat, cfg.budget - 1000)
    } else summary = '_[transcript_path not provided]_'
    sections.push(`## Conversation Summary (heuristic)\n\n${summary}`)
  }
  let body = `${sections.join('\n\n---\n\n')}\n`
  if (cpLen(body) > cfg.budget) body = `${cpSlice(body, 0, cfg.budget - 60)}\n\n[... truncated to char budget ...]\n`
  return [filename, body]
}

const preCompact = async (ctx: OpCtx): Promise<OpResult> => {
  const cfg: CompactCfg = {
    transcript: truthy(fromJs(getPath(ctx.config, 'compact_hook.include_transcript_summary', true))),
    git: truthy(fromJs(getPath(ctx.config, 'compact_hook.include_git_state', true))),
    budget: pyInt(getPath(ctx.config, 'compact_hook.char_budget'), 8000),
  }
  try {
    const dir = `${ctx.root}/.agent/.context-markers`
    const [filename, body] = await buildMarker(ctx, cfg)
    await ctx.io.write(`${dir}/${filename}`, body)
    await ctx.io.write(`${dir}/.active`, `${filename}\n`)
  } catch {
    // v6 posture: a marker-write failure never blocks compact
  }
  return ACK
}

const postCompact = async (ctx: OpCtx): Promise<OpResult> => {
  if (!truthy(fromJs(getPath(ctx.config, 'compact_hook.append_post_compact_summary', true)))) return ACK
  const dir = `${ctx.root}/.agent/.context-markers`
  const active = await safeRead(ctx.io, `${dir}/.active`, 200)
  if (!active) return ACK
  const marker = `${dir}/${strip(active)}`
  if (!(await isFile(ctx.io, marker))) return ACK
  const value = or(fromJs(ctx.payload.compact_summary), NO_SUMMARY_PLACEHOLDER)
  const text = strip(Array.isArray(value) || isDict(value) ? dumps(value, 2) : pyStr(value))
  const at = localParts(ctx.io, ctx.now).iso
  try {
    const existing = await ctx.io.read(marker)
    await ctx.io.write(marker, `${existing}\n\n---\n\n## Compact Summary (Claude Code)\n\n`
      + `_Appended by PostCompact hook at ${at}._\n\n${text}\n`)
  } catch {
    // never blocks compact
  }
  return ACK
}

const run = async (ctx: OpCtx): Promise<OpResult | null> => {
  if ((await statOf(ctx.io, `${ctx.root}/.agent`))?.kind !== 'dir') return null
  if (ctx.event === 'PreCompact') return preCompact(ctx)
  if (ctx.event === 'PostCompact') return postCompact(ctx)
  return null
}

export const compactMarkerPre: Op = {
  spec: { name: 'compact_marker', phase: 'recorders', configKey: 'compact_hook' },
  run,
}
export const compactMarkerPost: Op = compactMarkerPre
