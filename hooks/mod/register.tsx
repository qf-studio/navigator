// Navigator mod (v8 runtime, TASK-84): status band, /nav pane, ADHD-mode injection.
//
// Spike for the v8 runtime question (see memory project-claude-code-mods-assessment).
// Owned ops are announced through NAVIGATOR_MOD_OWNS (op names); runtime._dispatch skips
// them. Unloaded, the Python ops keep doing the same job.

import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type {
  NavActivity, NavDestination, NavHistory, NavOffRoute, NavPane, NavStatus, NavUsage, NavWaypointClock,
} from '../../types'
import { readJson } from './lib/config'
import { makeCtx } from './lib/context'
import { surfaceHealth } from './lib/life-health'
import { isPilotExecutor, loadConfig } from './lib/config'
import { RELEASES_URL, dueForCheck, latestStable, updateNotice, updateSettings } from './lib/update'
import type { Io } from './lib/types'
import { projectRoot, run } from './lib/project'
import { EVENT_OPS } from './ops'
import { announce } from './owns'
import { runEvent } from './runner'
import {
  clockOf, latestMarker, parseGraphStats, parseTasks, rateKind, tokensOf, turnsTo,
} from './ui/nav'
import {
  arrived, bandText, buildRoute, captureGoal, contentWords, currentWaypoint, detourTopic, isOffRoute,
  nextTaskNumber, parkedTaskDoc, parseSteps, routeView, slugOf, waypointText,
} from './ui/route'
import type { Step, Waypoint } from './ui/route'
import { statusOf } from './ui/status'
import { PALETTE, compact, gauge, percentColor, sparkline } from './ui/palette'

const PLUGIN = 'navigator'
const PANE = 'nav'
const NO_ACTIVITY: NavActivity = {
  docsBytes: 0, docsReads: 0, agentRuns: 0, agentTokens: 0, committed: false,
  lastTurnCommitted: false,
}
const NO_HISTORY: NavHistory = { ctx: [], saved: [] }
const EMPTY_NAV: NavPane = {
  tasks: [], marker: null, graph: null, docsTreeBytes: 0,
}
const DOC_DIRS = '.agent/DEVELOPMENT-README.md .agent/tasks .agent/system .agent/sops .agent/philosophy'

const status = atom({ plugin: 'navigator', key: 'status' } as const, null as NavStatus | null)
const pane = atom({ plugin: 'navigator', key: 'pane' } as const, null as NavPane | null)
const activity = atom({ plugin: 'navigator', key: 'activity' } as const, NO_ACTIVITY)
const usage = atom({ plugin: 'navigator', key: 'usage' } as const, null as NavUsage | null)
const history = atom({ plugin: 'navigator', key: 'history' } as const, NO_HISTORY)
const destination = atom({ plugin: 'navigator', key: 'destination' } as const, null as NavDestination | null)
const offRoute = atom({ plugin: 'navigator', key: 'offRoute' } as const, null as NavOffRoute | null)
const waypointClock = atom({ plugin: 'navigator', key: 'waypointClock' } as const, null as NavWaypointClock | null)
const showTasks = atom({ plugin: 'navigator', key: 'showTasks' } as const, false)

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
  stat: async path => {
    try {
      const st = await $.fs.stat(path)
      return { kind: st.kind, mtimeMs: st.mtimeMs }
    } catch {
      return null
    }
  },
  localOffsetMinutes: ms => -new Date(ms).getTimezoneOffset(),
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

/** Collect what the pane shows: open tasks, the active task's steps, newest marker, graph size. */
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
  const stats = await run(ioOf($), ['python3', `${functions}/graph_manager.py`, '--action', 'stats',
    '--graph-path', graphPath], root)
  const markers = await $.fs.list(`${root}/.agent/.context-markers`).catch(() => [])
  const treeBytes = Number((await run(ioOf($), ['sh', '-c',
    `find ${DOC_DIRS} -name '*.md' -type f -exec cat {} + 2>/dev/null | wc -c`], root)).trim()) || 0
  const taskList = parseTasks(tasks)
  const active = taskList[taskList.length - 1]
  let steps: Step[] = []
  if (active?.path) {
    try {
      steps = parseSteps(String(await $.fs.read(`${root}/${active.path}`)))
    } catch {
      steps = []
    }
  }
  await update($, pane, () => ({
    tasks: taskList,
    steps,
    marker: latestMarker(markers),
    graph: parseGraphStats(stats),
    docsTreeBytes: treeBytes,
  }))
}

/** Run the ops registered for a (Python-named) event; null outside a Navigator project. */
const runFor = async ($: EngineInterface, event: string, payload: Record<string, unknown>) => {
  const io = ioOf($)
  const ctx = await makeCtx(io, event, payload)
  if (ctx === null) return null
  // runtime._surface_health: SessionStart leads with the last dispatch error, if unsurfaced.
  const leading = event === 'SessionStart' ? await surfaceHealth(io, `${ctx.root}/.agent`) : null
  const merged = await runEvent(ctx, EVENT_OPS[event] ?? [], leading)
  if (merged.toast) $.ui.toast(merged.toast, { timeoutMs: 10000 })
  return merged
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

const OFF_ROUTE_AFTER = 2 // consecutive substantive prompts away from the destination
const LOW_FUEL_TURNS = 5
const ROUTE_AHEAD = 4 // steps listed past the done fold

/** Where the session is headed: a goal Claude stated in a brief, else the active task. */
const navState = async ($: EngineInterface) => {
  const p = await readPane($)
  const s = await read($, status)
  const chosen = await read($, destination)
  const task = p.tasks[p.tasks.length - 1] ?? null
  const dest: NavDestination | null = chosen
    ?? (task ? { title: task.title || task.id, taskId: task.id, source: 'task' } : null)
  const route: Waypoint[] = buildRoute(p.steps ?? [], s?.phase ?? null)
  return { p, s, dest, route, here: currentWaypoint(route) }
}

const destinationWords = (dest: NavDestination | null, route: readonly Waypoint[]): Set<string> =>
  dest === null ? new Set() : contentWords([dest.title, dest.taskId ?? '', ...route.map(w => w.label)].join(' '))

/** Write a task stub for the detour and return to the route. */
const parkDetour = async ($: EngineInterface): Promise<void> => {
  const detour = await read($, offRoute)
  const root = await projectRoot(ioOf($))
  if (detour === null || root === null) return
  const { dest } = await navState($)
  const names = (await $.fs.list(`${root}/.agent/tasks`).catch(() => [])).map(f => f.name)
  const id = `TASK-${nextTaskNumber(names)}`
  const date = new Date(await $.clock.now()).toISOString().slice(0, 10)
  await $.fs.write(`${root}/.agent/tasks/${id}-${slugOf(detour.topic)}.md`,
    parkedTaskDoc(id, detour.topic, detour.prompt, dest?.title ?? 'no destination', date))
  await update($, offRoute, () => null)
  $.ui.toast(`Parked as ${id}: ${detour.topic}`)
}

/** Make the detour the destination; the old one stays in the task list. */
const switchToDetour = async ($: EngineInterface): Promise<void> => {
  const detour = await read($, offRoute)
  if (detour === null) return
  const title = detour.prompt.split('\n')[0]?.trim().slice(0, 60) || detour.topic
  await update($, destination, (): NavDestination => ({ title, taskId: null, source: 'brief' }))
  await update($, offRoute, () => null)
  await update($, waypointClock, () => null)
}

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
    // Announce before next(): modules run before settings hooks, so the Python
    // SessionStart child already sees what the mod owns.
    await announce(ioOf($))
    if (e.source === 'clear' || e.source === 'resume' || e.source === 'fork') await refreshPane($)
    const r = await next(e)
    const merged = await runFor($, 'SessionStart', e as unknown as Record<string, unknown>)
    return withContext(r, merged?.context)
  })

  on('classic.PreCompact', async ($, e, next) => {
    const r = await next(e)
    await runFor($, 'PreCompact', e as unknown as Record<string, unknown>)
    return r
  })

  on('classic.PostCompact', async ($, e, next) => {
    const r = await next(e)
    await runFor($, 'PostCompact', e as unknown as Record<string, unknown>)
    return r
  })

  on('classic.SubagentStart', async ($, e, next) => {
    const r = await next(e)
    const merged = await runFor($, 'SubagentStart', e as unknown as Record<string, unknown>)
    return withContext(r, merged?.context)
  })

  on('classic.ConfigChange', async ($, e, next) => {
    const r = await next(e)
    await runFor($, 'ConfigChange', e as unknown as Record<string, unknown>)
    return r
  })

  on('classic.Setup', async ($, e, next) => {
    const r = await next(e)
    const merged = await runFor($, 'Setup', e as unknown as Record<string, unknown>)
    return withContext(r, merged?.context)
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
    const entered = merged?.context
      ? await next({ ...e, context: [...(e.context ?? []), merged.context] })
      : await next(e)
    if (entered.drop === undefined) {
      const { dest, route } = await navState($)
      if (isOffRoute(e.text, destinationWords(dest, route))) {
        await update($, offRoute, prev => ({
          topic: prev?.topic ?? detourTopic(e.text),
          prompt: prev?.prompt ?? e.text,
          count: (prev?.count ?? 0) + 1,
        }))
      } else if (contentWords(e.text).size >= 4) {
        await update($, offRoute, () => null) // back on the destination's vocabulary
      }
    }
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
    const goal = captureGoal(e.answer)
    if (goal !== null) await update($, destination, (): NavDestination => ({ title: goal, taskId: null, source: 'brief' }))
    const { here } = await navState($)
    const label = here?.label ?? null
    await update($, waypointClock, prev => (label === null ? null
      : prev?.label === label ? { label, turns: prev.turns + 1 } : { label, turns: 0 }))
    return next(e)
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    const { s, dest, route, here } = await navState($)
    const detour = await read($, offRoute)
    const left = turnsTo((await readHistory($)).ctx, 70)
    const percent = s?.ctxPercent ?? null
    const at = here === null ? 0 : route.indexOf(here) + 1
    const text = bandText({
      destination: dest?.title ?? null,
      waypoint: here?.label ?? null,
      position: at,
      total: route.length,
      next: s?.next ?? null,
      offRoute: (detour?.count ?? 0) >= OFF_ROUTE_AFTER ? (detour?.topic ?? 'a detour') : null,
      lowFuel: (percent !== null && percent >= 70) || (left !== null && left <= LOW_FUEL_TURNS),
    }, e.props.bodyColumns)
    if (!text) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    return (
      <Box>
        <Text color={PALETTE.dim} wrap="truncate-end">{text}</Text>
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const { p, s, dest, route, here } = await navState($)
    const u = await read($, usage)
    const a = await readActivity($)
    const hist = await readHistory($)
    const detour = await read($, offRoute)
    const clock = await read($, waypointClock)
    const tasksOpen = await read($, showTasks)
    const percent = s?.ctxPercent ?? null
    const pct = percent === null ? '--%' : `${Math.round(percent)}%`
    const ctxColor = percentColor(percent)
    const left = turnsTo(hist.ctx, 70)
    const lowFuel = (percent !== null && percent >= 70) || (left !== null && left <= LOW_FUEL_TURNS)
    const avoided = tokensOf(Math.max(0, p.docsTreeBytes - a.docsBytes))
    const isOff = (detour?.count ?? 0) >= OFF_ROUTE_AFTER
    const done = arrived(route)
    const view = routeView(route, ROUTE_AHEAD)
    const window = u?.rates[0]
    const panel = { borderStyle: 'round', borderColor: PALETTE.border, paddingX: 1 } as const
    const title = (text: string, color: string = PALETTE.accent) => (
      <Box marginBottom={1}><Text color={color}>{text}</Text></Box>
    )

    return (
      <Box flexDirection="column">
        {isOff && detour !== null ? (
          <Box {...panel} borderColor={PALETTE.warning} flexDirection="column">
            {title('⚠ off route', PALETTE.warning)}
            <Text wrap="truncate-end" color={PALETTE.label}>last {detour.count} prompts are about "{detour.topic}"</Text>
            <Text wrap="truncate-end" color={PALETTE.dim}>
              destination is "{dest?.title ?? 'not set'}"{here ? ` (${here.label})` : ''}
            </Text>
            <Text> </Text>
            <Box flexDirection="row" columnGap={3}>
              <Button key="park" label="park as new task" hotkey="p" plain onPress={() => parkDetour($)} />
              <Button key="back" label="back to route" hotkey="b" plain
                onPress={() => update($, offRoute, () => null)} />
              <Button key="switch" label="switch" hotkey="s" plain onPress={() => switchToDetour($)} />
            </Box>
          </Box>
        ) : (
          <Box {...panel} flexDirection="column">
            {title('destination')}
            {dest === null ? (
              <Text color={PALETTE.dim} wrap="wrap">no destination · say what you're building, or t to pick a task</Text>
            ) : (
              <Box flexDirection="row" justifyContent="space-between">
                <Text bold color={PALETTE.label} wrap="truncate-end">{dest.title}</Text>
                <Text color={PALETTE.dim}>{dest.taskId ?? (dest.source === 'brief' ? 'from brief' : '')}</Text>
              </Box>
            )}
          </Box>
        )}

        <Box {...panel} flexDirection="column">
          {title(here === null ? 'route' : `route · ${route.indexOf(here) + 1}/${route.length}`)}
          {view.done > 0 ? (
            <Text color={done ? PALETTE.success : PALETTE.dim} wrap="truncate-end">
              ✓ {view.done} done{view.last === null || done ? '' : ` · last: ${view.last.label}`}
            </Text>
          ) : null}
          {view.ahead.map(w => (
            <Text color={w.state === 'current' ? PALETTE.label : PALETTE.dim} bold={w.state === 'current'}
              wrap="truncate-end">{waypointText(w)}</Text>
          ))}
          {view.more > 0 ? <Text color={PALETTE.dim}>+ {view.more} more</Text> : null}
          <Text> </Text>
          {done ? (
            <Text color={PALETTE.success}>arrived · next: pick a destination</Text>
          ) : (
            <Box flexDirection="column">
              <Text wrap="truncate-end">
                <Text color={PALETTE.dim}>next   </Text>
                <Text color={PALETTE.label}>{s?.next ?? '—'}</Text>
              </Text>
              {clock && here ? (
                <Text color={PALETTE.dim}>since  {clock.turns} {clock.turns === 1 ? 'turn' : 'turns'} on this waypoint</Text>
              ) : null}
            </Box>
          )}
        </Box>

        <Box flexDirection="row">
          <Box {...panel} flexDirection="column" flexGrow={1} width="50%">
            {title('fuel (context)')}
            <Text wrap="truncate-end">
              <Text color={ctxColor} bold>{pct}</Text> <Text color={ctxColor}>{gauge(percent, 10)}</Text>
            </Text>
            <Text color={lowFuel ? PALETTE.warning : PALETTE.dim} wrap="truncate-end">
              {left === null ? 'growth flat' : `~${left} turns left`}
            </Text>
            <Text color={lowFuel ? PALETTE.warning : PALETTE.dim} wrap="truncate-end">
              {lowFuel ? 'compact at next waypoint' : a.lastTurnCommitted ? 'good moment to compact' : 'compact: hold'}
            </Text>
            <Text color={PALETTE.dim} wrap="truncate-end">
              {u?.usd == null ? '' : `$${u.usd.toFixed(2)}`}
              {window ? ` · ${rateKind(window.kind)} ${Math.round(window.percentUsed)}%` : ''}
            </Text>
          </Box>
          <Box {...panel} flexDirection="column" flexGrow={1} width="50%">
            {title('saved')}
            <Text color={PALETTE.success} bold wrap="truncate-end">~{compact(avoided)} tokens</Text>
            <Text color={PALETTE.dim} wrap="truncate-end">docs {compact(a.docsBytes)}B of {compact(p.docsTreeBytes)}B</Text>
            <Text color={PALETTE.dim} wrap="truncate-end">
              {a.agentRuns === 0 ? 'agents: none yet' : `agents ${compact(a.agentTokens)} outside`}
            </Text>
            <Text color={PALETTE.accent}>{sparkline(hist.saved, 14)}</Text>
          </Box>
        </Box>

        {tasksOpen ? (
          <Box {...panel} flexDirection="column">
            {title('open tasks')}
            {p.tasks.length === 0 && <Text color={PALETTE.dim}>none marked in progress</Text>}
            {[...p.tasks].reverse().slice(0, 6).map(t => (
              <Text wrap="truncate-end">
                <Text color={t.id === dest?.taskId ? PALETTE.success : PALETTE.dim}>{t.id === dest?.taskId ? '● ' : '○ '}</Text>
                <Text color={t.id === dest?.taskId ? PALETTE.label : PALETTE.dim}>{t.id}</Text>
                <Text color={PALETTE.dim}>{t.title ? `  ${t.title}` : ''}</Text>
              </Text>
            ))}
          </Box>
        ) : null}

        <Box flexDirection="row" columnGap={2} paddingX={1}>
          <Button key="marker" label="marker" hotkey="m" plain
            onPress={() => $.prompt.submit({ text: 'Create context marker checkpoint', asUser: true })} />
          <Text color={PALETTE.dim}>·</Text>
          <Button key="compact" label="compact" hotkey="c" plain onPress={() => $.session.compact()} />
          <Text color={PALETTE.dim}>·</Text>
          <Button key="tasks" label="tasks" hotkey="t" plain onPress={() => update($, showTasks, v => !v)} />
          <Text color={PALETTE.dim}>·</Text>
          <Button key="refresh" label="refresh" hotkey="f" plain onPress={() => refreshPane($)} />
        </Box>
      </Box>
    )
  })
}
