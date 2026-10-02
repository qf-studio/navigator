// Transcript tail reader, port of nav_hook_lib/transcript.py plus the Stop gate's turn scan
// (stop_completion._turn_scan). Same tail slice, same JSON-line tolerance, same backward
// scans. All failures degrade to empty results.
import { isDict, pySplitlines, pyStrip, pyTruthy } from './stop-py'
import type { Io, Json } from './types'

export const DEFAULT_TAIL_CHARS = 500_000

const FILE_PATH_TOOLS = new Set(['Edit', 'Write', 'MultiEdit', 'NotebookEdit'])

const expandUser = async (io: Io, path: string): Promise<string> => {
  if (path !== '~' && !path.startsWith('~/')) return path
  const home = (await io.env()).HOME
  return home ? `${home}${path.slice(1)}` : path
}

/** transcript.tail_text: last `maxChars` characters (code points); '' on any failure. */
export const tailText = async (io: Io, path: unknown, maxChars = DEFAULT_TAIL_CHARS): Promise<string> => {
  if (typeof path !== 'string') return ''
  try {
    // Path.read_text() opens in universal-newline mode: \r\n and \r arrive as \n.
    const text = (await io.read(await expandUser(io, path))).replace(/\r\n?/g, '\n')
    if (text.length <= maxChars) return text
    const points = Array.from(text)
    return points.length <= maxChars ? text : points.slice(points.length - maxChars).join('')
  } catch {
    return ''
  }
}

/** transcript.tail_entries: JSON-object lines in file order; undecodable lines skipped. */
export const tailEntries = async (io: Io, path: unknown, maxChars = DEFAULT_TAIL_CHARS): Promise<Json[]> => {
  const entries: Json[] = []
  for (const raw of pySplitlines(await tailText(io, path, maxChars))) {
    const line = pyStrip(raw)
    if (!line) continue
    try {
      const obj: unknown = JSON.parse(line)
      if (isDict(obj)) entries.push(obj)
    } catch {
      continue
    }
  }
  return entries
}

/** `obj.get("message") or obj`, then the isinstance(dict) check. */
const messageOf = (obj: Json): Json | null => {
  const msg = pyTruthy(obj.message) ? obj.message : obj
  return isDict(msg) ? msg : null
}

/** transcript.last_assistant_turn: (text, tool names) of the most recent assistant turn. */
export const lastAssistantTurn = async (io: Io, path: unknown): Promise<[string, Set<string>]> => {
  const chunks: string[] = []
  const tools = new Set<string>()
  for (const obj of (await tailEntries(io, path)).reverse()) {
    const msg = messageOf(obj)
    if (msg === null || msg.role !== 'assistant') continue
    const content = msg.content
    if (typeof content === 'string') chunks.push(content)
    else if (Array.isArray(content)) {
      for (const block of content) {
        if (!isDict(block)) continue
        if (typeof block.text === 'string') chunks.push(block.text)
        if (block.type === 'tool_use' && typeof block.name === 'string') tools.add(block.name)
      }
    }
    if (chunks.length > 0 || tools.size > 0) break
  }
  return [chunks.join('\n'), tools]
}

export type Evidence = { file_paths: string[]; bash: [string, boolean][] }

/** stop_completion._turn_scan: last text, tool names and evidence over the ending turn. */
export const turnScan = async (io: Io, payload: Json): Promise<[string, Set<string>, Evidence]> => {
  let text = ''
  const tools = new Set<string>()
  const filePaths: string[] = []
  const bashUses: [unknown, string][] = []
  const resultErrors = new Map<string, boolean>()
  const tpath = payload.transcript_path
  const entries = pyTruthy(tpath) ? await tailEntries(io, tpath) : []
  for (const obj of entries.reverse()) {
    const msg = messageOf(obj)
    if (msg === null) continue
    const role = msg.role
    const content = msg.content
    if (role === 'user') {
      if (typeof content === 'string' && pyStrip(content)) break
      if (Array.isArray(content)) {
        if (content.some(block => isDict(block) && block.type === 'text')) break
        for (const block of content) {
          if (!isDict(block) || block.type !== 'tool_result') continue
          if (typeof block.tool_use_id === 'string') resultErrors.set(block.tool_use_id, pyTruthy(block.is_error))
        }
      }
      continue
    }
    if (role !== 'assistant') continue
    const chunks: string[] = []
    if (typeof content === 'string') chunks.push(content)
    else if (Array.isArray(content)) {
      for (const block of content) {
        if (!isDict(block)) continue
        if (typeof block.text === 'string') chunks.push(block.text)
        if (block.type === 'tool_use' && typeof block.name === 'string') {
          const name = block.name
          tools.add(name)
          const inp = block.input
          if (!isDict(inp)) continue
          if (FILE_PATH_TOOLS.has(name)) {
            for (const key of ['file_path', 'notebook_path']) {
              const val = inp[key]
              if (typeof val === 'string' && val) filePaths.push(val)
            }
          } else if (name === 'Bash' && typeof inp.command === 'string') {
            bashUses.push([block.id, inp.command])
          }
        }
      }
    }
    if (chunks.length > 0 && !text) text = chunks.join('\n')
  }
  const inline = payload.last_assistant_message
  if (typeof inline === 'string' && pyStrip(inline)) text = inline
  const bash: [string, boolean][] = bashUses.map(([tid, cmd]) =>
    [cmd, typeof tid === 'string' ? (resultErrors.get(tid) ?? false) : false])
  return [text, tools, { file_paths: filePaths, bash }]
}
