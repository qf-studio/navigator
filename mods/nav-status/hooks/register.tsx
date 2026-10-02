// nav-status: Navigator's status band, Navigator pane and ADHD-mode injection as a
// Claude Code mod.
//
// Spike for the v8 runtime question (see memory project-claude-code-mods-assessment).
// While loaded it owns ADHD mode end to end and tells the Python runtime so through
// NAVIGATOR_MOD_OWNS; unloaded, hooks/ops/prompt_adhd.py keeps doing the same job.

import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { NavPane, NavReads, NavStatus } from '../types'
import {
  RULE_BLOCK, classify, personalBody, personalPath, resolve, toggleReason,
} from './adhd'
import { EMPTY_NAV, bar, cut, latestMarker, parseMemories, parseTaskList } from './nav'
import { bandLine, isQuiet, statusOf } from './status'

const PLUGIN = 'nav-status'
const PANE = 'nav'
const SHARED_CONFIG = '.agent/.nav-config.json'
const LOCAL_CONFIG = '.agent/.nav-config.local.json'
const NO_READS: NavReads = { total: 0, docs: 0 }

const status = atom({ plugin: 'nav-status', key: 'status' } as const, null as NavStatus | null)
const pane = atom({ plugin: 'nav-status', key: 'pane' } as const, null as NavPane | null)
const reads = atom({ plugin: 'nav-status', key: 'reads' } as const, NO_READS)
const pinned = atom({ plugin: 'nav-status', key: 'pinned' } as const, null as string | null)

type Json = Record<string, unknown>

const readJson = async ($: EngineInterface, path: string): Promise<Json | null> => {
  try {
    const parsed: unknown = JSON.parse(String(await $.fs.read(path)))
    return parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Json)
      : null
  } catch {
    return null
  }
}

const parentOf = (dir: string): string | null => {
  const at = dir.lastIndexOf('/')
  return at <= 0 ? null : dir.slice(0, at)
}

/** Nearest ancestor of cwd holding `.agent/`, as nav_hook_lib.hio.project_root. */
const projectRoot = async ($: EngineInterface): Promise<string | null> => {
  let dir: string | null = await $.session.cwd()
  while (dir !== null) {
    if (await $.fs.exists(`${dir}/.agent`)) return dir
    dir = parentOf(dir)
  }
  return null
}

/** `adhd_mode.on` after DEFAULTS < shared < local merging; undefined when unset. */
const repoPin = async ($: EngineInterface): Promise<unknown> => {
  const root = await projectRoot($)
  if (root === null) return undefined
  const pinOf = (cfg: Json | null): unknown => {
    const block = cfg?.adhd_mode
    return block !== null && typeof block === 'object' && 'on' in (block as Json)
      ? (block as Json).on
      : undefined
  }
  const local = pinOf(await readJson($, `${root}/${LOCAL_CONFIG}`))
  return local !== undefined ? local : pinOf(await readJson($, `${root}/${SHARED_CONFIG}`))
}

const personalFile = async ($: EngineInterface): Promise<string> =>
  personalPath({
    NAVIGATOR_CONFIG_HOME: await $.env.get('NAVIGATOR_CONFIG_HOME'),
    XDG_CONFIG_HOME: await $.env.get('XDG_CONFIG_HOME'),
    HOME: await $.env.get('HOME'),
  })

const resolveAdhd = async ($: EngineInterface, pinnedCfg: unknown, path: string) =>
  resolve(pinnedCfg, (await readJson($, path))?.on)

const run = async (
  $: EngineInterface, argv: readonly string[], cwd: string,
): Promise<string> => {
  try {
    const r = await $.process.run(argv, { cwd, timeoutMs: 5000 })
    return r.exitCode === 0 ? r.stdout : ''
  } catch {
    return ''
  }
}

/** Collect what the pane shows: in-progress task, newest marker, relevant memories. */
const refreshPane = async ($: EngineInterface): Promise<void> => {
  const root = await projectRoot($)
  if (root === null) {
    await update($, pane, () => EMPTY_NAV)
    return
  }
  const recall = `${$.plugin.root}/../../skills/nav-graph/functions/memory_recall.py`
  const tasks = await run($, ['sh', '-c',
    'grep -il "status.*\\(🚧\\|in progress\\)" .agent/tasks/*.md'], root)
  const memories = await run($, ['python3', recall, '--auto', '--agent-dir', '.agent',
    '--graph-path', '.agent/knowledge/graph.json', '--limit', '4', '--format', 'compact'], root)
  const markers = await $.fs.list(`${root}/.agent/.context-markers`).catch(() => [])
  await update($, pane, () => ({
    task: parseTaskList(tasks),
    marker: latestMarker(markers.map(m => m.name)),
    memories: parseMemories(memories),
  }))
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.env.set('NAVIGATOR_MOD_OWNS', 'adhd')
    await $.command.register({ name: 'nav', description: 'Open the Navigator pane' })
    await refreshPane($)
    return next(e)
  })

  // $.state resets on /clear, /resume and /branch; session.start does not fire again.
  on('classic.SessionStart', { source: ['clear', 'resume', 'fork'] }, async ($, e, next) => {
    await refreshPane($)
    return next(e)
  })

  on('command.run', { command: 'nav' }, async $ => {
    await refreshPane($)
    await $.ui.open({ id: PANE, title: 'Navigator', focus: true, closeOnEscape: true })
    return {}
  })

  on('tool.call', { tool: 'Read' }, async ($, e, next) => {
    const isDoc = e.file_path.includes('/.agent/')
    await update($, reads, r => ({ total: r.total + 1, docs: r.docs + (isDoc ? 1 : 0) }))
    return next(e)
  })

  on('prompt.submit', async ($, e, next) => {
    if (await $.env.get('PILOT_EXECUTOR')) return next(e)
    const kind = classify(e.text)
    const pinnedCfg = await repoPin($)
    const path = await personalFile($)
    if (kind === null) {
      const { on: active } = await resolveAdhd($, pinnedCfg, path)
      const memory = await read($, pinned)
      if (memory !== null) await update($, pinned, () => null)
      const extra = [
        ...(active ? [RULE_BLOCK] : []),
        ...(memory === null ? [] : [`Navigator memory pinned by the user for this prompt: ${memory}`]),
      ]
      if (extra.length === 0) return next(e)
      return next({ ...e, context: [...(e.context ?? []), ...extra] })
    }
    if (kind === 'status') {
      const resolved = await resolveAdhd($, pinnedCfg, path)
      return { drop: toggleReason({ kind, pinned: pinnedCfg, resolved, path, wrote: false }) }
    }
    const wanted = kind === 'on'
    const wrote = await $.fs.write(path, personalBody(wanted, await $.clock.now()))
      .then(() => true, () => false)
    if (!wrote) $.ui.toast(`${PLUGIN}: could not write ${path}`)
    const resolved = await resolveAdhd($, pinnedCfg, path)
    return { drop: toggleReason({ kind, pinned: pinnedCfg, resolved, path, wrote }) }
  })

  on('turn.complete', async ($, e, next) => {
    if (e.agentId !== undefined) return next(e)
    const percent = (await $.session.usage()).context.percent
    const fresh = statusOf(e.answer, percent === undefined ? null : percent)
    await update($, status, () => fresh)
    return next(e)
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const s = await read($, status)
    if (e.props.hasSurvey || isQuiet(s) || s === null) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    return (
      <Box>
        <Text dimColor wrap="truncate-end">{bandLine(s, e.props.bodyColumns)}</Text>
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const s = await read($, status)
    const p = (await read($, pane)) ?? EMPTY_NAV
    const r = await read($, reads)
    const chosen = await read($, pinned)
    const width = Math.max(24, e.props.bodyColumns)
    const percent = s?.ctxPercent ?? null
    const pct = percent === null ? '--%' : `${Math.round(percent)}%`
    const phase = s?.phase ? `phase ${s.phase}` : 'phase —'
    const task = p.task ?? 'no task in progress'
    const compactHint = percent !== null && percent >= 70 ? 'compact: due' : 'compact: safe'
    const marker = p.marker === null ? '' : ` · last marker ${cut(p.marker, 32)}`
    const fanOut = r.total - r.docs >= 5 ? '  → use an Agent' : ''
    const pinHint = chosen === null
      ? 'press ▸ to pin a memory into your next prompt'
      : 'pinned: rides your next prompt once'

    return (
      <Box flexDirection="column">
        <Box flexDirection="row" columnGap={2}>
          <Text bold>{cut(task, width - phase.length - 3)}</Text>
          <Text dimColor>{phase}</Text>
        </Box>
        <Text>context {bar(percent, Math.max(10, width - 14))} {pct}</Text>
        <Text dimColor>{compactHint}{marker}</Text>
        <Text> </Text>
        <Text>Reads this session  {r.total}  ({r.docs} in .agent/){fanOut}</Text>
        <Text>Memories matched    {p.memories.length}</Text>
        <Text> </Text>
        <Text dimColor>── relevant memories ──</Text>
        {p.memories.length === 0 && <Text dimColor>none for the open tasks</Text>}
        {p.memories.map((m, i) => (
          <Box flexDirection="row" columnGap={1}>
            <Button
              key={`mem-${i}`}
              label={chosen === m.text ? '●' : '▸'}
              plain
              onPress={() => update($, pinned, () => (chosen === m.text ? null : m.text))}
            />
            <Text wrap="truncate-end">
              {m.kind} {cut(m.text, width - m.kind.length - 10)}
              {m.percent === null ? '' : ` (${m.percent}%)`}
            </Text>
          </Box>
        ))}
        <Text> </Text>
        <Text dimColor>{pinHint}</Text>
        <Box flexDirection="row" columnGap={3}>
          <Button
            key="marker"
            label="marker"
            hotkey="m"
            plain
            onPress={() => $.prompt.submit({ text: 'Create context marker checkpoint', asUser: true })}
          />
          <Button
            key="compact"
            label="compact"
            hotkey="c"
            plain
            onPress={() => $.session.compact()}
          />
          <Button
            key="graph"
            label="graph"
            hotkey="g"
            plain
            onPress={() => $.prompt.submit({ text: 'graph health', asUser: true })}
          />
          <Button key="refresh" label="refresh" hotkey="r" plain onPress={() => refreshPane($)} />
        </Box>
      </Box>
    )
  })
}
