// nav-status: Navigator's status band, Navigator pane and ADHD-mode injection as a
// Claude Code mod.
//
// Spike for the v8 runtime question (see memory project-claude-code-mods-assessment).
// While loaded it owns ADHD mode end to end and tells the Python runtime so through
// NAVIGATOR_MOD_OWNS; unloaded, hooks/ops/prompt_adhd.py keeps doing the same job.

import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { NavHistory, NavPane, NavReads, NavStatus, NavUsage } from '../types'
import {
  RULE_BLOCK, classify, personalBody, personalPath, resolve, toggleReason,
} from './adhd'
import {
  bar, cut, latestMarker, parseGraphStats, parseMemories, parseTasks, usageLine,
} from './nav'
import { bandLine, isQuiet, statusOf } from './status'
import { PALETTE, compact, gauge, percentColor, sparkline } from './ui'

const PLUGIN = 'nav-status'
const PANE = 'nav'
const SHARED_CONFIG = '.agent/.nav-config.json'
const LOCAL_CONFIG = '.agent/.nav-config.local.json'
const NO_READS: NavReads = { total: 0, docs: 0, turn: 0 }
const NO_HISTORY: NavHistory = { ctx: [], reads: [] }
const EMPTY_NAV: NavPane = { tasks: [], marker: null, memories: [], graph: null }

const status = atom({ plugin: 'nav-status', key: 'status' } as const, null as NavStatus | null)
const pane = atom({ plugin: 'nav-status', key: 'pane' } as const, null as NavPane | null)
const reads = atom({ plugin: 'nav-status', key: 'reads' } as const, NO_READS)
const usage = atom({ plugin: 'nav-status', key: 'usage' } as const, null as NavUsage | null)
const history = atom({ plugin: 'nav-status', key: 'history' } as const, NO_HISTORY)
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

/** Collect what the pane shows: open tasks, newest marker, memories, graph size. */
const refreshPane = async ($: EngineInterface): Promise<void> => {
  const root = await projectRoot($)
  if (root === null) {
    await update($, pane, () => EMPTY_NAV)
    return
  }
  const functions = `${$.plugin.root}/../../skills/nav-graph/functions`
  const graphPath = '.agent/knowledge/graph.json'
  const tasks = await run($, ['sh', '-c',
    'for f in $(grep -il "status.*\\(🚧\\|in progress\\)" .agent/tasks/*.md); do '
    + 'printf "%s|%s\\n" "$f" "$(grep -m1 "^# " "$f")"; done'], root)
  const memories = await run($, ['python3', `${functions}/memory_recall.py`, '--auto',
    '--agent-dir', '.agent', '--graph-path', graphPath, '--limit', '4', '--format', 'compact'], root)
  const stats = await run($, ['python3', `${functions}/graph_manager.py`, '--action', 'stats',
    '--graph-path', graphPath], root)
  const markers = await $.fs.list(`${root}/.agent/.context-markers`).catch(() => [])
  await update($, pane, () => ({
    tasks: parseTasks(tasks),
    marker: latestMarker(markers),
    memories: parseMemories(memories),
    graph: parseGraphStats(stats),
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
    await $.ui.open({
      id: PANE, title: 'Navigator', focus: true, closeOnEscape: true, columns: 64,
    })
    return {}
  })

  on('tool.call', { tool: 'Read' }, async ($, e, next) => {
    const isDoc = e.file_path.includes('/.agent/')
    await update($, reads, r => ({
      total: r.total + 1, docs: r.docs + (isDoc ? 1 : 0), turn: r.turn + 1,
    }))
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
    const u = await $.session.usage()
    const fresh = statusOf(e.answer, u.context.percent === undefined ? null : u.context.percent)
    await update($, status, prev => ({
      phase: fresh.phase ?? prev?.phase ?? null,
      next: fresh.next ?? prev?.next ?? null,
      ctxPercent: fresh.ctxPercent,
    }))
    await update($, usage, () => ({
      rates: u.rateLimits.map(r => ({ kind: r.kind, percentUsed: r.percentUsed })),
      usd: u.cost?.usd ?? null,
    }))
    const turnReads = (await read($, reads)).turn
    await update($, reads, r => ({ ...r, turn: 0 }))
    await update($, history, h => ({
      ctx: [...h.ctx, fresh.ctxPercent ?? 0].slice(-64),
      reads: [...h.reads, turnReads].slice(-64),
    }))
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
    const u = await read($, usage)
    const r = await read($, reads)
    const hist = await read($, history)
    const chosen = await read($, pinned)
    const percent = s?.ctxPercent ?? null
    const pct = percent === null ? '--%' : `${Math.round(percent)}%`
    const ctxColor = percentColor(percent)
    const current = p.tasks[p.tasks.length - 1] ?? null
    const window = u?.rates[0]
    const fanOut = r.total - r.docs >= 5
    const panel = { borderStyle: 'round', borderColor: PALETTE.border, paddingX: 1 } as const
    const title = (text: string) => <Text color={PALETTE.accent}>{text}</Text>

    return (
      <Box flexDirection="column">
        <Box flexDirection="row">
          <Box {...panel} flexDirection="column" flexGrow={1} width="33%">
            {title('context')}
            <Text wrap="truncate-end">
              <Text color={ctxColor} bold>{pct}</Text> <Text color={ctxColor}>{gauge(percent, 10)}</Text>
            </Text>
            <Text color={PALETTE.dim}>{percent !== null && percent >= 70 ? 'compact due' : 'compact safe'}</Text>
            <Text color={PALETTE.accent}>{sparkline(hist.ctx, 14)}</Text>
          </Box>
          <Box {...panel} flexDirection="column" flexGrow={1} width="33%">
            {title('session')}
            <Text wrap="truncate-end">
              <Text color={PALETTE.success} bold>{u?.usd == null ? '--' : `$${u.usd.toFixed(2)}`}</Text>
              <Text color={PALETTE.dim}>{window ? `  ${window.kind} ${Math.round(window.percentUsed)}%` : ''}</Text>
            </Text>
            <Text color={PALETTE.label} wrap="truncate-end">{s?.phase ? `phase ${s.phase}` : 'phase —'}</Text>
            <Text color={PALETTE.dim} wrap="truncate-end">
              {p.graph ? `graph ${compact(p.graph.nodes)} nodes` : 'graph —'}
            </Text>
          </Box>
          <Box {...panel} flexDirection="column" flexGrow={1} width="33%">
            {title('reads')}
            <Text wrap="truncate-end">
              <Text color={fanOut ? PALETTE.warning : PALETTE.accent} bold>{r.total}</Text>
              <Text color={PALETTE.dim}>  {r.docs} docs</Text>
            </Text>
            <Text color={PALETTE.dim}>{fanOut ? 'use an Agent' : 'fan-out ok'}</Text>
            <Text color={PALETTE.accent}>{sparkline(hist.reads, 14)}</Text>
          </Box>
        </Box>

        <Box {...panel} flexDirection="column">
          {title('task')}
          <Text wrap="truncate-end">
            <Text color={PALETTE.accent} bold>{current?.id ?? 'no task in progress'}</Text>
            <Text color={PALETTE.label}>{current?.title ? `  ${current.title}` : ''}</Text>
          </Text>
          {s?.next ? (
            <Text wrap="truncate-end"><Text color={PALETTE.dim}>→ </Text><Text color={PALETTE.label}>{s.next}</Text></Text>
          ) : null}
          <Text color={PALETTE.dim} wrap="truncate-end">
            {p.marker === null ? 'no marker yet' : `marker ${p.marker}`}
          </Text>
        </Box>

        <Box {...panel} flexDirection="column">
          {title('memories')}
          {p.memories.length === 0 && <Text color={PALETTE.dim}>none for the open tasks</Text>}
          {p.memories.map((m, i) => (
            <Box flexDirection="row" columnGap={1}>
              <Button
                key={`mem-${i}`}
                label={chosen === m.text ? '●' : '▸'}
                plain
                onPress={() => update($, pinned, () => (chosen === m.text ? null : m.text))}
              />
              <Box flexGrow={1} flexShrink={1}>
                <Text wrap="wrap" color={chosen !== null && chosen !== m.text ? PALETTE.dim : PALETTE.label}>
                  <Text color={PALETTE.accent} bold>{m.kind.toLowerCase()}</Text>
                  <Text color={PALETTE.dim}>{m.percent === null ? '' : ` ${m.percent}%`}</Text>
                  {'  '}{m.text}
                </Text>
              </Box>
            </Box>
          ))}
          <Text color={PALETTE.dim}>
            {chosen === null ? '▸ pins a memory into your next prompt' : '● pinned for your next prompt'}
          </Text>
        </Box>

        <Box {...panel} flexDirection="column">
          {title('open tasks')}
          {p.tasks.length === 0 && <Text color={PALETTE.dim}>none marked in progress</Text>}
          {[...p.tasks].reverse().slice(0, 6).map(t => (
            <Text wrap="truncate-end">
              <Text color={t.id === current?.id ? PALETTE.success : PALETTE.dim}>
                {t.id === current?.id ? '● ' : '○ '}
              </Text>
              <Text color={t.id === current?.id ? PALETTE.label : PALETTE.dim} bold={t.id === current?.id}>
                {t.id}
              </Text>
              <Text color={PALETTE.dim}>{t.title ? `  ${t.title}` : ''}</Text>
            </Text>
          ))}
        </Box>

        <Box flexDirection="row" columnGap={2} paddingX={1}>
          <Button
            key="marker"
            label="marker"
            hotkey="m"
            plain
            onPress={() => $.prompt.submit({ text: 'Create context marker checkpoint', asUser: true })}
          />
          <Text color={PALETTE.dim}>·</Text>
          <Button
            key="compact"
            label="compact"
            hotkey="c"
            plain
            onPress={() => $.session.compact()}
          />
          <Text color={PALETTE.dim}>·</Text>
          <Button key="refresh" label="refresh" hotkey="r" plain onPress={() => refreshPane($)} />
        </Box>
      </Box>
    )
  })
}
