// Read-only Bash classification, port of stop_completion._bash_readonly (TASK-70/71).
// Anything unrecognized is mutating: the Stop gate may over-fire, never under-fire.
import { NWS, WS, pySplit, pyStrip } from './stop-py'

const READONLY_BASH_CMDS = new Set([
  'ls', 'find', 'grep', 'rg', 'cat', 'head', 'tail', 'wc', 'echo', 'pwd',
  'which', 'file', 'stat', 'tree', 'du', 'df', 'type', 'env', 'printenv',
  'uname', 'whoami', 'date', 'diff',
  'ps', 'sort', 'uniq', 'cut', 'tr', 'jq', 'basename', 'dirname',
  'realpath', 'readlink', 'printf', 'read', 'sleep', 'true', 'false',
  'test', '[', '[[',
  'lsof', 'pgrep', 'nproc', 'sw_vers',
  // TASK-90: `cd` changes the shell's directory, not the tree (2026-10-05).
  'cd',
])
// curl reads unless it names an output file (TASK-85): a short flag cluster carrying o/O
// (-o, -O, -sSo) or a long --output*/--remote-name* flag writes.
const curlWrites = (token: string): boolean =>
  token.startsWith('--') ? token.startsWith('--output') || token.startsWith('--remote-name')
    : token.startsWith('-') && (token.includes('o') || token.includes('O'))
const READONLY_GIT_SUBCMDS = new Set([
  'status', 'log', 'diff', 'show', 'branch', 'rev-parse', 'describe',
  'shortlog', 'blame', 'remote', 'ls-files',
  'fetch', 'ls-tree', 'ls-remote', 'cat-file', 'show-ref', 'rev-list',
])
const READONLY_GH_SUBCMDS = new Set([
  'pr view', 'pr list', 'pr checks', 'pr diff', 'pr status',
  'issue view', 'issue list', 'issue status',
  'run view', 'run list', 'workflow view', 'workflow list',
  // TASK-96: `gh run watch` polls a run; it writes nothing.
  'run watch',
  'release view', 'release list', 'repo view', 'label list',
  'search prs', 'search issues', 'search code', 'search repos',
])
// claude resolved by subcommand pair like gh (TASK-96). `plugin update` writes the plugin
// cache, never the tree; install/uninstall/enable/disable can rewrite a project
// `.claude/settings.json` and stay mutating.
const READONLY_CLAUDE_SUBCMDS = new Set(['plugin list', 'plugin validate', 'plugin test', 'plugin update'])
// make resolved by target (TASK-96): every target must look like a test or check and none
// like a build; `make` with no target stays mutating.
const MAKE_READONLY = /test|check|typecheck|validate/
const MAKE_WRITE = /lint|format|build|install/
const SEGMENT_SPLIT = /\|\||&&|;|\||\n/g
// A function definition opens a body on the same segment (TASK-96): `q() { ls; }`.
const FUNC_DEF = /^[A-Za-z_][A-Za-z0-9_]*\(\)\{?$/
const OPENERS = /^[({]+/
const CLOSERS = /[)}]+$/
// The redirect target ends at a `;`, `&` or `|` operator (TASK-96).
const REDIRECT_TRAIL = /[;&|]+$/
const SUBSTITUTION = /\$\(([^()]*)\)|`([^`]*)`/g
const ASSIGNMENT = /^[A-Za-z_][A-Za-z0-9_]*=/
const REDIRECT = new RegExp(`[0-9]*>>?${WS}*(${NWS}+)`, 'gu')
const TRANSPARENT_HEADS = new Set(['if', 'elif', 'then', 'else', 'do', 'while', 'until', '!', 'time'])
const STANDALONE_HEADS = new Set(['for', 'done', 'fi', 'esac', 'case'])

/**
 * stop_completion._strip_structure (TASK-96): a subshell, group or function body is
 * classified by what runs inside. Openers are peeled from the head, closers from every word,
 * empty words dropped, so `(cd x && git status)` reads as read-only while `(rm x)` stays mutating.
 */
const stripStructure = (tokens: string[]): string[] => {
  while (tokens.length > 0) {
    const head = tokens[0] as string
    if (FUNC_DEF.test(head)) { tokens = tokens.slice(1); continue }
    const peeled = head.replace(OPENERS, '')
    if (peeled === head) break
    tokens = (peeled ? [peeled] : []).concat(tokens.slice(1))
  }
  const out: string[] = []
  for (const token of tokens) {
    const t = token.replace(CLOSERS, '')
    if (t) out.push(t)
  }
  return out
}

/** stop_completion._segments (TASK-96): (masked, raw) pairs sliced at the same offsets. */
const segments = (masked: string, raw: string): Array<[string, string]> => {
  const out: Array<[string, string]> = []
  let pos = 0
  for (const m of masked.matchAll(SEGMENT_SPLIT)) {
    out.push([masked.slice(pos, m.index), raw.slice(pos, m.index)])
    pos = m.index + m[0].length
  }
  out.push([masked.slice(pos), raw.slice(pos)])
  return out
}

/**
 * stop_completion._mask_quotes (TASK-94): the contents of quoted spans become `x` of the
 * same length, quote characters kept. `'…'` has no escapes; inside `"…"` a backslash consumes
 * the next character; a backslash outside quotes escapes the next character; an unterminated
 * quote masks to the end. Heads, flags and redirect targets are never inside quotes.
 */
export const maskQuotes = (text: string): string => {
  let out = ''
  let i = 0
  const n = text.length
  while (i < n) {
    const ch = text[i]
    if (ch === "'") {
      out += ch
      i += 1
      while (i < n && text[i] !== "'") { out += 'x'; i += 1 }
      if (i < n) { out += "'"; i += 1 }
    } else if (ch === '"') {
      out += ch
      i += 1
      while (i < n && text[i] !== '"') {
        if (text[i] === '\\' && i + 1 < n) { out += 'xx'; i += 2 } else { out += 'x'; i += 1 }
      }
      if (i < n) { out += '"'; i += 1 }
    } else if (ch === '\\' && i + 1 < n) {
      out += '\\x'
      i += 2
    } else {
      out += ch
      i += 1
    }
  }
  return out
}

export const bashReadonly = (command: unknown): boolean => {
  if (typeof command !== 'string' || !pyStrip(command)) return true
  let text = command
  for (;;) {
    const matches = [...text.matchAll(SUBSTITUTION)]
    if (matches.length === 0) break
    for (const m of matches) {
      if (!bashReadonly(m[1] || m[2] || '')) return false
    }
    text = text.replace(SUBSTITUTION, '')
  }
  const raw = text // TASK-96: awk programs are judged unmasked (`print > "f"` writes)
  text = maskQuotes(text) // TASK-94: quoted | > ; never split or redirect
  for (const m of text.matchAll(REDIRECT)) {
    const target = (m[1] ?? '').replace(REDIRECT_TRAIL, '')
    if (target !== '/dev/null' && !target.startsWith('&')) return false
  }
  for (const [segment, rawSegment] of segments(text, raw)) {
    let tokens = stripStructure(pySplit(segment))
    while (tokens.length > 0 && (TRANSPARENT_HEADS.has(tokens[0] as string) || ASSIGNMENT.test(tokens[0] as string))) {
      tokens = tokens.slice(1)
    }
    if (tokens.length === 0) continue
    let head = tokens[0] as string
    if (STANDALONE_HEADS.has(head)) continue
    if (head === 'command') {
      const rest = tokens.slice(1)
      if (rest.length > 0 && (rest[0] === '-v' || rest[0] === '-V')) continue
      tokens = rest
      if (tokens.length === 0) continue
      head = tokens[0] as string
    }
    if (head.startsWith('/')) {
      // TASK-90: `/bin/ls` (eza-free listing) is `ls`; the basename must still be a known
      // read-only head, so `/usr/bin/rm` stays mutating.
      head = head.slice(head.lastIndexOf('/') + 1)
    }
    if (head === 'git') {
      const sub = tokens.slice(1).find(t => !t.startsWith('-')) ?? ''
      if (!READONLY_GIT_SUBCMDS.has(sub)) return false
    } else if (head === 'gh') {
      const pair = tokens.slice(1).filter(t => !t.startsWith('-')).slice(0, 2)
      if (!READONLY_GH_SUBCMDS.has(pair.join(' '))) return false
    } else if (head === 'claude') {
      // TASK-96: plugin list/validate/test/update never touch the tree.
      const pair = tokens.slice(1).filter(t => !t.startsWith('-')).slice(0, 2)
      if (!READONLY_CLAUDE_SUBCMDS.has(pair.join(' '))) return false
    } else if (head === 'make') {
      // TASK-96: test-shaped targets only; `make` alone or a build stays mutating.
      const targets = tokens.slice(1).filter(t => !t.startsWith('-') && !/[=<>]/.test(t))
      if (targets.length === 0 || targets.some(t => MAKE_WRITE.test(t))
        || !targets.every(t => MAKE_READONLY.test(t))) return false
    } else if (head === 'python3' || head === 'python') {
      // TASK-96: `python3 -m json.tool` is the one python form that only reads.
      if (tokens[1] !== '-m' || tokens[2] !== 'json.tool') return false
    } else if (head === 'awk') {
      // TASK-96: an awk program writes only through `>`; the raw (unmasked) segment is
      // checked because the program is a quoted argument.
      if (rawSegment.includes('>')) return false
    } else if (head === 'curl') {
      if (tokens.slice(1).some(curlWrites)) return false
    } else if (head === 'sed') {
      // TASK-87: `sed -n '1,40p' file` reads; any in-place flag writes.
      if (tokens.slice(1).some(t => t === '--in-place' || t.startsWith('--in-place=')
        || (t.startsWith('-') && !t.startsWith('--') && t.includes('i')))) return false
    } else if (!READONLY_BASH_CMDS.has(head)) {
      return false
    }
  }
  return true
}
