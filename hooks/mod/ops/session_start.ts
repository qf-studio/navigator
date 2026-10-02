// session_start — mirror of hooks/ops/session_start.py (TASK-61, ported TASK-84 step 5d).
// SessionStart: archive the v6 state files once, then inject the Navigator session block
// (config, drift, graph stats, memories, profile, open tasks, marker, navigator index).
import { getPath } from '../lib/config'
import { personalPath, resolve, statusLine } from '../lib/adhd'
import { pyInt } from '../lib/life-budget'
import {
  type PyDict, type PyValue, cpLen, cpSlice, dumps, fromJs, get, isDict, isFile, loads,
  orEmptyGet, pyStr, safeJson, safeRead, splitlines, statOf, strip, stripChars, textOut, truthy,
} from '../lib/life-py'
import type { Io, Op, OpCtx, OpResult } from '../lib/types'
import { JUDGE_DEFAULTS } from '../lib/gen/judge-data.gen'
import { globMd, titleOf } from './compact_marker'

export const SENTINEL = '<!-- nav-session-start-injected:v1 -->'
const CHAR_BUDGET = 9500
const TRUNCATION_FOOTER = '\n\n[truncated: ask nav-start for full detail]'
const DEFAULT_SECTIONS = ['navigator', 'marker', 'config', 'graph', 'profile', 'tasks', 'auto_update']
const LEGACY_STATE_FILES = ['.nav-workflow-state.json', '.nav-read-counter.json', '.nav-profile-sync-state.json']
const ARCHIVE_DIR = '.nav-v6-state.bak'

/** Copy the v6 per-hook state files into .nav-v6-state.bak/ (first snapshot wins). */
export const archiveLegacyState = async (io: Io, agent: string): Promise<void> => {
  try {
    const sources: string[] = []
    for (const name of LEGACY_STATE_FILES) if (await isFile(io, `${agent}/${name}`)) sources.push(name)
    for (const name of sources) {
      const dest = `${agent}/${ARCHIVE_DIR}/${name}`
      if ((await statOf(io, dest)) !== null) continue
      await io.write(dest, await io.read(`${agent}/${name}`))
    }
  } catch {
    // archival never costs the user their context injection
  }
}

const section = {
  navigator: async (io: Io, root: string) => {
    const nav = await safeRead(io, `${root}/.agent/DEVELOPMENT-README.md`, 8000)
    return nav ? `## Navigator Index (.agent/DEVELOPMENT-README.md)\n\n${nav}` : null
  },
  marker: async (io: Io, root: string) => {
    const dir = `${root}/.agent/.context-markers`
    const raw = await safeRead(io, `${dir}/.active`, 200)
    if (!raw) return null
    const name = strip(raw)
    if (!name) return null
    const path = name.startsWith('/') ? name : `${dir}/${name}`
    const body = await safeRead(io, path, 6000)
    if (!body) return `## Active Marker\n\n\`${name}\` referenced but file missing.`
    return `## Active Marker: \`${name}\`\n\nUser was working on this before compact. Offer to resume.\n\n${body}`
  },
}

const sliceLast5 = (v: PyValue): PyValue => {
  if (!truthy(v)) return []
  if (Array.isArray(v)) return v.slice(-5)
  if (typeof v === 'string') return cpSlice(v, -5)
  throw new TypeError('unsliceable')
}

const judgeNotice = async (io: Io, block: PyValue): Promise<string> => {
  if (!isDict(block) || !truthy(get(block, 'enabled'))) return ''
  try {
    const merged: PyDict = new Map(Object.entries(JUDGE_DEFAULTS).map(([k, v]) => [k, fromJs(v)]))
    for (const [k, v] of block) merged.set(k, v)
    const envName = pyStr(truthy(get(merged, 'api_key_env')) ? get(merged, 'api_key_env') : JUDGE_DEFAULTS.api_key_env)
    const env = await io.env()
    const fromEnv = envName === 'TYPESAFE_API_KEY' ? strip(env.TYPESAFE_API_KEY ?? '') : ''
    let source: string | null = fromEnv ? `env:${envName}` : null
    const rawFile = pyStr(truthy(get(merged, 'api_key_file')) ? get(merged, 'api_key_file') : JUDGE_DEFAULTS.api_key_file)
    if (source === null) {
      const path = (rawFile === '~' || rawFile.startsWith('~/')) && env.HOME ? env.HOME + rawFile.slice(1) : rawFile
      const text = await safeRead(io, path)
      const lines = text === null ? [] : splitlines(strip(text))
      if (lines.length > 0 && strip(lines[0] as string)) source = `file:${path}`
    }
    if (source) return `\n\nTyped judge: on (${pyStr(get(merged, 'model'))}, key from ${source}).`
    return '\n\n⚠️  Typed judge is enabled but no API key was found — the keyword '
      + 'heuristics are answering. '
      + `Get a key at https://console.typesafe.ai/keys, then either export ${envName} `
      + `in the environment Claude Code runs in, or write it to ${rawFile} `
      + '(chmod 600). Verify with: python3 hooks/nav_hook_lib/judge.py --check '
      + '(from the plugin root). Until a key is found the keyword heuristics answer.'
  } catch {
    return ''
  }
}

const adhdNotice = async (io: Io, config: Record<string, unknown>): Promise<string> => {
  try {
    const path = personalPath(await io.env())
    const personal = await safeJson(io, path)
    const on = personal === null ? null : get(personal, 'on')
    const line = statusLine(resolve(getPath(config, 'adhd_mode.on'), on), path)
    return line ? `\n\n${line}` : ''
  } catch {
    return ''
  }
}

const configSection = async (io: Io, root: string, layered: Record<string, unknown>) => {
  const cfg = await safeJson(io, `${root}/.agent/.nav-config.json`)
  if (cfg === null || cfg.size === 0) return null
  const summary: PyDict = new Map<string, PyValue>([
    ['version', get(cfg, 'version')],
    ['project_management', get(cfg, 'project_management')],
    ['task_prefix', get(cfg, 'task_prefix')],
    ['team_chat', get(cfg, 'team_chat')],
    ['loop_mode', orEmptyGet(get(cfg, 'loop_mode'), 'enabled')],
    ['task_mode', orEmptyGet(get(cfg, 'task_mode'), 'enabled')],
    ['knowledge_graph', orEmptyGet(get(cfg, 'knowledge_graph'), 'enabled')],
    ['tom_features', get(cfg, 'tom_features')],
    ['auto_update', orEmptyGet(get(cfg, 'auto_update'), 'enabled')],
  ])
  return `## Navigator Config (.agent/.nav-config.json)\n\n\`\`\`json\n${dumps(summary, 2)}\n\`\`\``
    + await judgeNotice(io, get(cfg, 'judge')) + await adhdNotice(io, layered)
}

const profileSection = async (io: Io, root: string) => {
  const profile = await safeJson(io, `${root}/.agent/.user-profile.json`)
  if (profile === null || profile.size === 0) return null
  const body: PyDict = new Map<string, PyValue>([
    ['preferences', get(profile, 'preferences', new Map())],
    ['recent_corrections', sliceLast5(get(profile, 'corrections', []))],
    ['goals', sliceLast5(get(profile, 'goals', []))],
  ])
  return `## User Profile (Theory of Mind)\n\nApply these preferences for this session.\n\n\`\`\`json\n${dumps(body, 2)}\n\`\`\``
}

const runScript = async (io: Io, rel: string, args: string[], timeoutMs: number): Promise<string | null> => {
  const script = `${io.pluginRoot}/skills/${rel}`
  if (!(await isFile(io, script))) return null
  try {
    return textOut((await io.run(['python3', script, ...args], io.pluginRoot, timeoutMs)).stdout)
  } catch {
    return null
  }
}

const graphSection = async (io: Io, root: string) => {
  const graph = `${root}/.agent/knowledge/graph.json`
  if (!(await isFile(io, graph))) return null
  if (!(await isFile(io, `${io.pluginRoot}/skills/nav-graph/functions/graph_manager.py`))) {
    return '## Knowledge Graph\n\nGraph present (stats helper not found).'
  }
  const out = await runScript(io, 'nav-graph/functions/graph_manager.py', ['--action', 'stats', '--graph-path', graph], 4000)
  const text = strip(out ?? '')
  return text ? `## Knowledge Graph Stats\n\n\`\`\`\n${cpSlice(text, 0, 1500)}\n\`\`\`` : null
}

const autoUpdateSection = async (io: Io, root: string) => {
  const out = await runScript(io, 'nav-start/functions/auto_updater.py',
    ['--check-drift', '--config-path', `${root}/.agent/.nav-config.json`], 4000)
  const raw = strip(out ?? '')
  if (!raw) return null
  let data: PyValue
  try {
    data = loads(raw)
  } catch {
    return null
  }
  if (!isDict(data)) return null
  if (!truthy(get(data, 'has_drift'))) return null
  const message = truthy(get(data, 'message')) ? get(data, 'message') : 'Navigator version drift detected.'
  return `## Auto-Update\n\n⚠️  ${pyStr(message)}`
}

const memoriesSection = async (io: Io, root: string, limit: number) => {
  const graph = `${root}/.agent/knowledge/graph.json`
  if (!(await isFile(io, graph))) return null
  const out = await runScript(io, 'nav-graph/functions/memory_recall.py', ['--auto', '--agent-dir',
    `${root}/.agent`, '--graph-path', graph, '--limit', String(limit), '--format', 'compact'], 3000)
  const text = strip(out ?? '')
  if (!text) return null
  return '## Relevant Memories\n\nPrior knowledge matching your open tasks/marker — factor these '
    + `in before planning.\n\n${cpSlice(text, 0, 1200)}`
}

const tasksSection = async (io: Io, root: string) => {
  const dir = `${root}/.agent/tasks`
  if ((await statOf(io, dir))?.kind !== 'dir') return null
  const entries: string[] = []
  try {
    for (const name of await globMd(io, dir)) {
      if (name.toUpperCase().startsWith('README')) continue
      const head = (await safeRead(io, `${dir}/${name}`, 600)) ?? ''
      const title = titleOf(head, name)
      let status = 'open'
      for (const line of splitlines(head)) {
        const low = line.toLowerCase()
        if (low.includes('status') && low.includes(':')) {
          status = stripChars(strip(line.slice(line.indexOf(':') + 1)), '*` ')
          break
        }
      }
      entries.push(`- \`${name}\` — ${title} [${status}]`)
      if (entries.length >= 20) {
        entries.push('- … (more in .agent/tasks/)')
        break
      }
    }
  } catch {
    return null
  }
  return entries.length === 0 ? null : `## Open Tasks\n\n${entries.join('\n')}`
}

export const buildBody = async (ctx: OpCtx): Promise<string> => {
  const { io, root, config } = ctx
  const include = getPath(config, 'session_start_hook.include_sections', DEFAULT_SECTIONS)
  if (!Array.isArray(include) && typeof include !== 'string') throw new TypeError('not iterable')
  const enabled = new Set<string>(Array.isArray(include) ? include.map(String) : Array.from(include))
  const budget = pyInt(getPath(config, 'session_start_hook.char_budget'), CHAR_BUDGET)
  const surface = truthy(fromJs(getPath(config, 'knowledge_graph.auto_surface_relevant', true)))
  const maxMemories = pyInt(getPath(config, 'knowledge_graph.max_session_memories'), 5)
  const source = pyStr(truthy(fromJs(ctx.payload.source)) ? fromJs(ctx.payload.source) : 'startup')

  const header = [
    SENTINEL, '# Navigator Session Start', `_source: ${source}_`, '',
    'This block was injected by the SessionStart hook — Navigator content '
      + 'is already in your context. Do NOT re-Read these files. Render the '
      + 'session summary directly from this data.',
    '',
  ]
  if (source === 'resume') header.splice(2, 0, '**RESUMED FROM PREVIOUS SESSION** — prioritize active marker.')

  const sections: string[] = []
  const add = async (name: string, build: () => Promise<string | null>) => {
    if (!enabled.has(name)) return
    let out: string | null
    try {
      out = await build()
    } catch {
      return
    }
    if (out) sections.push(out)
  }
  if (source === 'resume') await add('marker', () => section.marker(io, root))
  await add('config', () => configSection(io, root, config))
  await add('auto_update', () => autoUpdateSection(io, root))
  await add('graph', () => graphSection(io, root))
  if (surface) {
    enabled.add('memories')
    await add('memories', () => memoriesSection(io, root, maxMemories))
  }
  await add('profile', () => profileSection(io, root))
  await add('tasks', () => tasksSection(io, root))
  if (source !== 'resume') await add('marker', () => section.marker(io, root))
  await add('navigator', () => section.navigator(io, root))

  let body = `${header.join('\n')}\n\n${sections.join('\n\n---\n\n')}`
  if (cpLen(body) > budget) body = cpSlice(body, 0, budget - cpLen(TRUNCATION_FOOTER)) + TRUNCATION_FOOTER
  return body
}

const run = async (ctx: OpCtx): Promise<OpResult | null> => {
  const agent = `${ctx.root}/.agent`
  if ((await statOf(ctx.io, agent))?.kind !== 'dir') return null
  await archiveLegacyState(ctx.io, agent)
  const body = await buildBody(ctx)
  return body ? { additional_context: body } : null
}

export const sessionStart: Op = {
  spec: { name: 'session_start', phase: 'injectors', configKey: 'session_start_hook' },
  run,
}

