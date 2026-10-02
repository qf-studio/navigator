// Navigator mod (v8 runtime, TASK-84): status band, /nav pane, ADHD-mode injection.
//
// Spike for the v8 runtime question (see memory project-claude-code-mods-assessment).
// Owned ops are announced through NAVIGATOR_MOD_OWNS (op names); runtime._dispatch skips
// them. Unloaded, the Python ops keep doing the same job.

import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { NavActivity, NavHistory, NavPane, NavStatus, NavUsage } from '../../types'
import {
  RULE_BLOCK, classify, personalBody, personalPath, resolve, toggleReason,
} from './lib/adhd'
import {
  clockOf, latestMarker, matchConcepts, parseGraphStats, parseMemories, parseTasks, rateKind,
  tokensOf, turnsTo,
} from './ui/nav'
import { bandLine, isQuiet, statusOf } from './ui/status'
import { PALETTE, compact, gauge, percentColor, sparkline } from './ui/palette'

const PLUGIN = 'navigator'
const PANE = 'nav'
const SHARED_CONFIG = '.agent/.nav-config.json'
const LOCAL_CONFIG = '.agent/.nav-config.local.json'
const NO_ACTIVITY: NavActivity = {
  docsBytes: 0, docsReads: 0, agentRuns: 0, agentTokens: 0, committed: false,
  lastTurnCommitted: false,
}
const NO_HISTORY: NavHistory = { ctx: [], saved: [] }
const EMPTY_NAV: NavPane = {
  tasks: [], marker: null, memories: [], memoriesFor: null, graph: null, concepts: [],
  docsTreeBytes: 0,
}
const DOC_DIRS = '.agent/DEVELOPMENT-README.md .agent/tasks .agent/system .agent/sops .agent/philosophy'

const status = atom({ plugin: 'navigator', key: 'status' } as const, null as NavStatus | null)
const pane = atom({ plugin: 'navigator', key: 'pane' } as const, null as NavPane | null)
const activity = atom({ plugin: 'navigator', key: 'activity' } as const, NO_ACTIVITY)
const usage = atom({ plugin: 'navigator', key: 'usage' } as const, null as NavUsage | null)
const history = atom({ plugin: 'navigator', key: 'history' } as const, NO_HISTORY)
const pinned = atom({ plugin: 'navigator', key: 'pinned' } as const, null as string | null)

// $.state survives a hot reload, so a value written by an older version of this module
// can lack fields added since. Read through these to merge stored values over defaults.
const readPane = async ($: EngineInterface): Promise<NavPane> =>
  ({ ...EMPTY_NAV, ...((await read($, pane)) ?? {}) })
const readHistory = async ($: EngineInterface): Promise<NavHistory> => {
  const h = await read($, history)
  return {
    ctx: Array.isArray(h?.ctx) ? h.ctx : [],
    saved: Array.isArray(h?.saved) ? h.saved : [],
  }
}
const readActivity = async ($: EngineInterface): Promise<NavActivity> =>
  ({ ...NO_ACTIVITY, ...((await read($, activity)) ?? {}) })

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
  const functions = `${$.plugin.root}/skills/nav-graph/functions`
  const graphPath = '.agent/knowledge/graph.json'
  const tasks = await run($, ['sh', '-c',
    'for f in $(grep -il "status.*\\(🚧\\|in progress\\)" .agent/tasks/*.md); do '
    + 'printf "%s|%s\\n" "$f" "$(grep -m1 "^# " "$f")"; done'], root)
  const memories = await run($, ['python3', `${functions}/memory_recall.py`, '--auto',
    '--agent-dir', '.agent', '--graph-path', graphPath, '--limit', '4', '--format', 'compact'], root)
  const stats = await run($, ['python3', `${functions}/graph_manager.py`, '--action', 'stats',
    '--graph-path', graphPath], root)
  const markers = await $.fs.list(`${root}/.agent/.context-markers`).catch(() => [])
  const treeBytes = Number((await run($, ['sh', '-c',
    `find ${DOC_DIRS} -name '*.md' -type f -exec cat {} + 2>/dev/null | wc -c`], root)).trim()) || 0
  const graphJson = await readJson($, `${root}/${graphPath}`)
  const index = graphJson?.concept_index
  const concepts = index !== null && typeof index === 'object' ? Object.keys(index as Json) : []
  await update($, pane, () => ({
    tasks: parseTasks(tasks),
    marker: latestMarker(markers),
    memories: parseMemories(memories),
    memoriesFor: null,
    graph: parseGraphStats(stats),
    concepts,
    docsTreeBytes: treeBytes,
  }))
}

/** Memories for the concepts a prompt names; leaves the pane alone when none match. */
const recallFor = async ($: EngineInterface, prompt: string): Promise<void> => {
  const root = await projectRoot($)
  const current = await readPane($)
  if (root === null) return
  const hits = matchConcepts(prompt, current.concepts)
  if (hits.length === 0) return
  const functions = `${$.plugin.root}/skills/nav-graph/functions`
  const out = await run($, ['python3', `${functions}/memory_recall.py`, '--concepts', hits.join(','),
    '--graph-path', '.agent/knowledge/graph.json', '--limit', '4', '--format', 'compact'], root)
  const memories = parseMemories(out)
  if (memories.length > 0) {
    await update($, pane, p => ({ ...EMPTY_NAV, ...(p ?? {}), memories, memoriesFor: hits.join(', ') }))
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.env.set('NAVIGATOR_MOD_OWNS', 'prompt_adhd')
    await $.command.register({ name: 'nav', description: 'Open the Navigator pane' })
    await refreshPane($)
    return next(e)
  })

  // Runs before the Python SessionStart child (modules precede settings hooks), so the
  // handoff env is in place for it. $.state resets on /clear, /resume and /branch, and
  // session.start does not fire again, so the pane reloads here too.
  on('classic.SessionStart', async ($, e, next) => {
    await $.env.set('NAVIGATOR_MOD_OWNS', 'prompt_adhd')
    if (e.source === 'clear' || e.source === 'resume' || e.source === 'fork') await refreshPane($)
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
    const ran = await next(e)
    if (e.file_path.includes('/.agent/') && ran.deny === undefined) {
      const bytes = (ran.text ?? '').length
      await update($, activity, a => {
        const x = { ...NO_ACTIVITY, ...a }
        return { ...x, docsBytes: x.docsBytes + bytes, docsReads: x.docsReads + 1 }
      })
    }
    return ran
  })

  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const ran = await next(e)
    if (/\bgit\s+commit\b/.test(e.command) && ran.deny === undefined && ran.isError !== true) {
      await update($, activity, a => ({ ...NO_ACTIVITY, ...a, committed: true }))
    }
    return ran
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
      const entered = extra.length === 0
        ? await next(e)
        : await next({ ...e, context: [...(e.context ?? []), ...extra] })
      if (entered.drop === undefined) await recallFor($, e.text)
      return entered
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
    if (e.agentId !== undefined) {
      const used = e.usage
      const tokens = used === undefined ? 0
        : used.input_tokens + used.cache_read_input_tokens + used.cache_creation_input_tokens
          + used.output_tokens
      await update($, activity, a => {
        const x = { ...NO_ACTIVITY, ...a }
        return { ...x, agentRuns: x.agentRuns + 1, agentTokens: x.agentTokens + tokens }
      })
      return next(e)
    }
    const u = await $.session.usage()
    const fresh = statusOf(e.answer, u.context.percent === undefined ? null : u.context.percent)
    await update($, status, prev => ({
      phase: fresh.phase ?? prev?.phase ?? null,
      next: fresh.next ?? prev?.next ?? null,
      ctxPercent: fresh.ctxPercent,
    }))
    await update($, usage, () => ({
      rates: u.rateLimits.map(r => ({
        kind: r.kind, percentUsed: r.percentUsed, resetsAt: r.resetsAt ?? null,
      })),
      usd: u.cost?.usd ?? null,
    }))
    const a = await readActivity($)
    const tree = (await readPane($)).docsTreeBytes
    const h = await readHistory($)
    await update($, activity, x => {
      const y = { ...NO_ACTIVITY, ...x }
      return { ...y, committed: false, lastTurnCommitted: y.committed }
    })
    await update($, history, () => ({
      ctx: [...h.ctx, fresh.ctxPercent ?? 0].slice(-64),
      saved: [...h.saved, tokensOf(Math.max(0, tree - a.docsBytes))].slice(-64),
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
    const p = await readPane($)
    const u = await read($, usage)
    const a = await readActivity($)
    const hist = await readHistory($)
    const chosen = await read($, pinned)
    const percent = s?.ctxPercent ?? null
    const pct = percent === null ? '--%' : `${Math.round(percent)}%`
    const ctxColor = percentColor(percent)
    const current = p.tasks[p.tasks.length - 1] ?? null
    const left = turnsTo(hist.ctx, 70)
    const compactHint = percent !== null && percent >= 70 ? 'compact now: context is high'
      : a.lastTurnCommitted ? 'good moment to compact: just committed'
        : 'compact: hold, mid-task'
    const avoided = tokensOf(Math.max(0, p.docsTreeBytes - a.docsBytes))
    const panel = { borderStyle: 'round', borderColor: PALETTE.border, paddingX: 1 } as const
    const title = (text: string, note?: string) => (
      <Box marginBottom={1}>
        <Text>
          <Text color={PALETTE.accent}>{text}</Text>
          <Text color={PALETTE.dim}>{note ? `  ${note}` : ''}</Text>
        </Text>
      </Box>
    )

    return (
      <Box flexDirection="column">
        {s?.next ? (
          <Box {...panel} flexDirection="column">
            {title('do next')}
            <Text color={PALETTE.label} bold wrap="wrap">{s.next}</Text>
          </Box>
        ) : null}

        <Box flexDirection="row">
          <Box {...panel} flexDirection="column" flexGrow={1} width="50%">
            {title('context')}
            <Text wrap="truncate-end">
              <Text color={ctxColor} bold>{pct}</Text> <Text color={ctxColor}>{gauge(percent, 12)}</Text>
            </Text>
            <Text color={PALETTE.dim} wrap="truncate-end">
              {left === null ? 'growth flat' : `~${left} turns to 70%`}
            </Text>
            <Text color={PALETTE.accent}>{sparkline(hist.ctx, 18)}</Text>
          </Box>
          <Box {...panel} flexDirection="column" flexGrow={1} width="50%">
            {title('session')}
            <Text color={PALETTE.success} bold>{u?.usd == null ? '--' : `$${u.usd.toFixed(2)}`}</Text>
            {(u?.rates ?? []).slice(0, 2).map(r => (
              <Text color={PALETTE.dim} wrap="truncate-end">
                {rateKind(r.kind)} {Math.round(r.percentUsed)}%
                {clockOf(r.resetsAt) === null ? '' : ` · resets ${clockOf(r.resetsAt)}`}
              </Text>
            ))}
          </Box>
        </Box>

        <Box {...panel} flexDirection="column">
          {title('saved this session', 'estimates, ~4 bytes per token')}
          <Text wrap="truncate-end">
            <Text color={PALETTE.success} bold>~{compact(avoided)} tokens</Text>
            <Text color={PALETTE.label}> kept out of context</Text>
          </Text>
          <Text wrap="truncate-end">
            <Text color={PALETTE.dim}>docs    </Text>
            <Text color={PALETTE.label}>
              loaded {compact(a.docsBytes)}B of {compact(p.docsTreeBytes)}B in .agent/
            </Text>
            <Text color={PALETTE.dim}>{a.docsReads > 0 ? `  (${a.docsReads} reads)` : ''}</Text>
          </Text>
          <Text wrap="truncate-end">
            <Text color={PALETTE.dim}>agents  </Text>
            <Text color={PALETTE.label}>
              {a.agentRuns === 0 ? 'none yet'
                : `${a.agentRuns} turns · ${compact(a.agentTokens)} tokens processed outside`}
            </Text>
          </Text>
          <Text color={PALETTE.accent}>{sparkline(hist.saved, 24)}</Text>
        </Box>

        <Box {...panel} flexDirection="column">
          {title('active task')}
          <Text wrap="truncate-end">
            <Text color={PALETTE.accent} bold>{current?.id ?? 'no task in progress'}</Text>
            <Text color={PALETTE.label}>{current?.title ? `  ${current.title}` : ''}</Text>
          </Text>
          <Text color={PALETTE.dim} wrap="truncate-end">
            {p.marker === null ? 'no marker yet' : `marker ${p.marker}`}
          </Text>
          <Text color={percent !== null && percent >= 70 ? PALETTE.warning : PALETTE.dim}>{compactHint}</Text>
        </Box>

        <Box {...panel} flexDirection="column">
          {title('memories', p.memoriesFor === null ? 'for open tasks' : `for: ${p.memoriesFor}`)}
          {p.memories.length === 0 && <Text color={PALETTE.dim}>none matched</Text>}
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
