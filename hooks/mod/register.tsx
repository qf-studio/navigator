// Navigator mod (v8 runtime, TASK-84): status band, /nav pane, ADHD-mode injection.
//
// Spike for the v8 runtime question (see memory project-claude-code-mods-assessment).
// Owned ops are announced through NAVIGATOR_MOD_OWNS (op names); runtime._dispatch skips
// them. Unloaded, the Python ops keep doing the same job.

import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { NavActivity, NavHistory, NavPane, NavStatus, NavUsage } from '../../types'
import { readJson } from './lib/config'
import { makeCtx } from './lib/context'
import { isPilotExecutor, loadConfig } from './lib/config'
import { RELEASES_URL, dueForCheck, latestStable, updateNotice, updateSettings } from './lib/update'
import type { Io } from './lib/types'
import { projectRoot, run } from './lib/project'
import { EVENT_OPS } from './ops'
import { announce } from './owns'
import { runEvent } from './runner'
import {
  clockOf, latestMarker, matchConcepts, parseGraphStats, parseMemories, parseTasks, rateKind,
  tokensOf, turnsTo,
} from './ui/nav'
import { bandLine, isQuiet, statusOf } from './ui/status'
import { PALETTE, compact, gauge, percentColor, sparkline } from './ui/palette'

const PLUGIN = 'navigator'
const PANE = 'nav'
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
const disowned = atom({ plugin: 'navigator', key: 'disowned' } as const, [] as string[])
const crashes = atom({ plugin: 'navigator', key: 'crashes' } as const, {} as Record<string, number>)

/**
 * The mods API narrowed for imported modules (lib/, ops/, owns, runner). The static scan
 * follows `$` only within this file, so every capability is a direct `$.noun.method` here.
 */
const ioOf = ($: EngineInterface): Io => ({
  pluginRoot: $.plugin.root,
  read: async path => String(await $.fs.read(path)),
  write: async (path, text) => {
    await $.fs.write(path, text)
  },
  exists: path => $.fs.exists(path),
  list: async path =>
    (await $.fs.list(path)).map(f => ({ name: f.name, mtimeMs: f.mtimeMs, kind: f.kind })),
  run: async (argv, cwd, timeoutMs) => {
    const r = await $.process.run(argv, { cwd, timeoutMs })
    return { exitCode: r.exitCode, stdout: r.stdout }
  },
  runCapture: async (argv, cwd, timeoutMs) => {
    const r = await $.process.run(argv, { cwd, timeoutMs })
    return { exitCode: r.exitCode, stdout: r.stdout, stderr: r.stderr }
  },
  cwd: () => $.session.cwd(),
  sessionId: async () => (await $.session.id()) || null,
  nowMs: () => $.clock.now(),
  version: async () => {
    const v = await $.session.version()
    return v.base === undefined ? { version: v.version } : { version: v.version, base: v.base }
  },
  env: async () => ({
    PILOT_EXECUTOR: await $.env.get('PILOT_EXECUTOR'),
    NAVIGATOR_CONFIG_HOME: await $.env.get('NAVIGATOR_CONFIG_HOME'),
    XDG_CONFIG_HOME: await $.env.get('XDG_CONFIG_HOME'),
    HOME: await $.env.get('HOME'),
    TYPESAFE_API_KEY: await $.env.get('TYPESAFE_API_KEY'),
  }),
  setOwned: value => $.env.set('NAVIGATOR_MOD_OWNS', value),
  http: async (url, init) => {
    const r = await $.http.fetch(url, init)
    return { ok: r.ok, status: r.status, text: r.text }
  },
  sleep: ms => $.clock.sleep(ms),
  disowned: async () => (await read($, disowned)) ?? [],
  noteCrash: async op => {
    await update($, crashes, c => ({ ...(c ?? {}), [op]: ((c ?? {})[op] ?? 0) + 1 }))
    return ((await read($, crashes)) ?? {})[op] ?? 0
  },
  disown: async op => {
    await update($, disowned, d => [...new Set([...(d ?? []), op])])
  },
})

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

/** Collect what the pane shows: open tasks, newest marker, memories, graph size. */
const refreshPane = async ($: EngineInterface): Promise<void> => {
  const root = await projectRoot(ioOf($))
  if (root === null) {
    await update($, pane, () => EMPTY_NAV)
    return
  }
  const functions = `${$.plugin.root}/skills/nav-graph/functions`
  const graphPath = '.agent/knowledge/graph.json'
  const tasks = await run(ioOf($), ['sh', '-c',
    'for f in $(grep -il "status.*\\(🚧\\|in progress\\)" .agent/tasks/*.md); do '
    + 'printf "%s|%s\\n" "$f" "$(grep -m1 "^# " "$f")"; done'], root)
  const memories = await run(ioOf($), ['python3', `${functions}/memory_recall.py`, '--auto',
    '--agent-dir', '.agent', '--graph-path', graphPath, '--limit', '4', '--format', 'compact'], root)
  const stats = await run(ioOf($), ['python3', `${functions}/graph_manager.py`, '--action', 'stats',
    '--graph-path', graphPath], root)
  const markers = await $.fs.list(`${root}/.agent/.context-markers`).catch(() => [])
  const treeBytes = Number((await run(ioOf($), ['sh', '-c',
    `find ${DOC_DIRS} -name '*.md' -type f -exec cat {} + 2>/dev/null | wc -c`], root)).trim()) || 0
  const graphJson = await readJson(ioOf($), `${root}/${graphPath}`)
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
  const root = await projectRoot(ioOf($))
  const current = await readPane($)
  if (root === null) return
  const hits = matchConcepts(prompt, current.concepts)
  if (hits.length === 0) return
  const functions = `${$.plugin.root}/skills/nav-graph/functions`
  const out = await run(ioOf($), ['python3', `${functions}/memory_recall.py`, '--concepts', hits.join(','),
    '--graph-path', '.agent/knowledge/graph.json', '--limit', '4', '--format', 'compact'], root)
  const memories = parseMemories(out)
  if (memories.length > 0) {
    await update($, pane, p => ({ ...EMPTY_NAV, ...(p ?? {}), memories, memoriesFor: hits.join(', ') }))
  }
}

/** Run the ops registered for a (Python-named) event; null outside a Navigator project. */
const runFor = async ($: EngineInterface, event: string, payload: Record<string, unknown>) => {
  const ctx = await makeCtx(ioOf($), event, payload)
  return ctx === null ? null : runEvent(ctx, EVENT_OPS[event] ?? [])
}

/** The settings-hook payload shape the Python ops read, rebuilt from a tool.call event. */
const toolPayload = (e: Record<string, unknown>): Record<string, unknown> => {
  const { tool, tool_use_id: id, ...input } = e
  return { tool_name: tool, tool_input: input, tool_use_id: id }
}

/** Append one context entry to a classic result (the chain rule: never drop theirs). */
const withContext = <R extends { additionalContext?: string[] }>(r: R, text: string | null | undefined): R =>
  text ? { ...r, additionalContext: [...(r.additionalContext ?? []), text] } : r

// MultiEdit no longer exists as a tool on CC 2.1.287; Python's matcher still lists it (harmless).
const MUTATING = ['Edit', 'Write', 'NotebookEdit'] as const

/** TASK-81: one read-only notice when a newer stable release exists; never updates. */
const checkForUpdate = async ($: EngineInterface): Promise<void> => {
  const io = ioOf($)
  if (await isPilotExecutor(io)) return
  const root = await projectRoot(io)
  if (root === null) return
  const { enabled, intervalHours } = updateSettings(await loadConfig(io, root))
  if (!enabled) return
  const now = await $.clock.now()
  let latest = (await $.store.get('update_latest')) as string | null | undefined
  if (dueForCheck(await $.store.get('update_checked_at'), now, intervalHours)) {
    const response = await Promise.race([
      $.http.fetch(RELEASES_URL, { headers: { Accept: 'application/vnd.github+json' } }),
      $.clock.sleep(4000).then(() => null),
    ]).catch(() => null)
    if (response !== null && response.ok) {
      latest = latestStable(response.text)
      await $.store.set('update_latest', latest ?? null)
      await $.store.set('update_checked_at', now)
    }
  }
  const manifest = await readJson(io, `${$.plugin.root}/.claude-plugin/plugin.json`)
  const installed = typeof manifest?.version === 'string' ? manifest.version : null
  const notice = installed === null ? null : updateNotice(installed, latest ?? null)
  if (notice !== null) $.ui.toast(notice, { timeoutMs: 15000 })
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await announce(ioOf($))
    await checkForUpdate($).catch(() => {})
    await $.command.register({ name: 'nav', description: 'Open the Navigator pane' })
    await refreshPane($)
    return next(e)
  })

  // Runs before the Python SessionStart child (modules precede settings hooks), so the
  // handoff env is in place for it. $.state resets on /clear, /resume and /branch, and
  // session.start does not fire again, so the pane reloads here too.
  on('classic.SessionStart', async ($, e, next) => {
    await announce(ioOf($))
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
    const pre = await runFor($, 'PreToolUse', toolPayload(e as unknown as Record<string, unknown>))
    if (pre?.deny != null) return { deny: pre.deny }
    const ran = await next(e)
    if (e.file_path.includes('/.agent/') && ran.deny === undefined) {
      const bytes = (ran.text ?? '').length
      await update($, activity, a => {
        const x = { ...NO_ACTIVITY, ...a }
        return { ...x, docsBytes: x.docsBytes + bytes, docsReads: x.docsReads + 1 }
      })
    }
    // v8: read_guard's warn reaches the model as context (v7 printed it to stderr only).
    const warn = pre?.notes ?? null
    return warn !== null && ran.deny === undefined ? { ...ran, context: [...(ran.context ?? []), warn] } : ran
  })

  on('tool.call', { tool: MUTATING }, async ($, e, next) => {
    const ran = await next(e)
    if (ran.deny !== undefined || ran.isError === true) return ran
    const post = await runFor($, 'PostToolUse', toolPayload(e as unknown as Record<string, unknown>))
    return post?.context ? { ...ran, context: [...(ran.context ?? []), post.context] } : ran
  })

  on('classic.TaskCreated', async ($, e, next) => {
    const r = await next(e)
    await runFor($, 'TaskCreated', e as unknown as Record<string, unknown>)
    return r
  })

  on('classic.TaskCompleted', async ($, e, next) => {
    const r = await next(e)
    await runFor($, 'TaskCompleted', e as unknown as Record<string, unknown>)
    return r
  })

  on('classic.PostToolUseFailure', async ($, e, next) => {
    const r = await next(e)
    const merged = await runFor($, 'PostToolUseFailure', e as unknown as Record<string, unknown>)
    return withContext(r, merged?.context)
  })

  on('classic.Stop', async ($, e, next) => {
    const r = await next(e)
    const merged = await runFor($, 'Stop', e as unknown as Record<string, unknown>)
    return merged?.block != null ? { ...r, block: merged.block } : r
  })

  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const ran = await next(e)
    if (/\bgit\s+commit\b/.test(e.command) && ran.deny === undefined && ran.isError !== true) {
      await update($, activity, a => ({ ...NO_ACTIVITY, ...a, committed: true }))
    }
    return ran
  })

  on('prompt.submit', async ($, e, next) => {
    const ctx = await makeCtx(ioOf($), 'UserPromptSubmit', { prompt: e.text })
    const merged = ctx === null ? null : await runEvent(ctx, EVENT_OPS.UserPromptSubmit ?? [])
    if (merged?.drop != null) return { drop: merged.drop }
    const memory = await read($, pinned)
    if (memory !== null) await update($, pinned, () => null)
    const extra = [
      ...(merged?.context ? [merged.context] : []),
      ...(memory === null ? [] : [`Navigator memory pinned by the user for this prompt: ${memory}`]),
    ]
    const entered = extra.length === 0
      ? await next(e)
      : await next({ ...e, context: [...(e.context ?? []), ...extra] })
    if (entered.drop === undefined) await recallFor($, e.text)
    return entered
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
