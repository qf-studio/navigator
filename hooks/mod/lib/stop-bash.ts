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
  'release view', 'release list', 'repo view', 'label list',
  'search prs', 'search issues', 'search code', 'search repos',
])
const SEGMENT_SPLIT = /\|\||&&|;|\||\n/
const SUBSTITUTION = /\$\(([^()]*)\)|`([^`]*)`/g
const ASSIGNMENT = /^[A-Za-z_][A-Za-z0-9_]*=/
const REDIRECT = new RegExp(`[0-9]*>>?${WS}*(${NWS}+)`, 'gu')
const TRANSPARENT_HEADS = new Set(['if', 'elif', 'then', 'else', 'do', 'while', 'until', '!', 'time'])
const STANDALONE_HEADS = new Set(['for', 'done', 'fi', 'esac', 'case'])

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
  for (const m of text.matchAll(REDIRECT)) {
    const target = m[1] ?? ''
    if (target !== '/dev/null' && !target.startsWith('&')) return false
  }
  for (const segment of text.split(SEGMENT_SPLIT)) {
    let tokens = pySplit(segment)
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
    if (head === 'git') {
      const sub = tokens.slice(1).find(t => !t.startsWith('-')) ?? ''
      if (!READONLY_GIT_SUBCMDS.has(sub)) return false
    } else if (head === 'gh') {
      const pair = tokens.slice(1).filter(t => !t.startsWith('-')).slice(0, 2)
      if (!READONLY_GH_SUBCMDS.has(pair.join(' '))) return false
    } else if (head === 'curl') {
      if (tokens.slice(1).some(curlWrites)) return false
    } else if (!READONLY_BASH_CMDS.has(head)) {
      return false
    }
  }
  return true
}
