// Navigator mod (v8 runtime, TASK-84): status band, /nav pane, ADHD-mode injection.
//
// Spike for the v8 runtime question (see memory project-claude-code-mods-assessment).
// Owned ops are announced through NAVIGATOR_MOD_OWNS (op names); runtime._dispatch skips
// them. Unloaded, the Python ops keep doing the same job.

import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type {
  NavActivity, NavDestination, NavHistory, NavJudge, NavOffRoute, NavPane, NavReads, NavStatus, NavTrip,
  NavUsage, NavWaypointClock,
} from '../../types'
import { readJson } from './lib/config'
import { makeCtx } from './lib/context'
import { surfaceHealth } from './lib/life-health'
import { getPath, isPilotExecutor, loadConfig } from './lib/config'
import { RELEASES_URL, dueForCheck, latestStable, updateNotice, updateSettings } from './lib/update'
import type { Io } from './lib/types'
import { projectRoot, run } from './lib/project'
import { EVENT_OPS } from './ops'
import { announce } from './owns'
import { runEvent } from './runner'
import type { Judgment } from './lib/scoring'
import {
  NO_READS, countRead, endTurnReads, fanOutText, judgeTally, judgeView, latestMarker, parseGraphStats,
  parseMemories, parseTasks, rateKind, tokensOf, turnsTo,
} from './ui/nav'
import {
  arrived, bandText, buildRoute, captureGoal, contentWords, currentWaypoint, detourTopic, isOffRoute,
  nextTaskNumber, parkedTaskDoc, parseSteps, slugOf,
} from './ui/route'
import type { Step, Waypoint } from './ui/route'
import { statusOf } from './ui/status'
import {
  PER_MINUTE, PER_MINUTE_SPAN_SEC, PER_MINUTE_STEP_SEC, buildTrip, parseMatrix, parseVector,
  isLoopback, secondsSinceMidnight, tripQueries,
} from './ui/trip'
import { PALETTE, compact, gauge, percentColor, sparkline } from './ui/palette'

const PLUGIN = 'navigator'
const PANE = 'nav'
const NO_ACTIVITY: NavActivity = {
  docsBytes: 0, docsReads: 0, agentRuns: 0, agentTokens: 0, committed: false,
  lastTurnCommitted: false,
}
const NO_HISTORY: NavHistory = { ctx: [], saved: [] }
const EMPTY_NAV: NavPane = {
  tasks: [], marker: null, graph: null, docsTreeBytes: 0, memories: [],
}
const STATE_FILE = '.agent/.nav-runtime-state.json'
const DOC_DIRS = '.agent/DEVELOPMENT-README.md .agent/tasks .agent/system .agent/sops .agent/philosophy'

const status = atom({ plugin: 'navigator', key: 'status' } as const, null as NavStatus | null)
const pane = atom({ plugin: 'navigator', key: 'pane' } as const, null as NavPane | null)
const activity = atom({ plugin: 'navigator', key: 'activity' } as const, NO_ACTIVITY)
const usage = atom({ plugin: 'navigator', key: 'usage' } as const, null as NavUsage | null)
const history = atom({ plugin: 'navigator', key: 'history' } as const, NO_HISTORY)
const destination = atom({ plugin: 'navigator', key: 'destination' } as const, null as NavDestination | null)
const offRoute = atom({ plugin: 'navigator', key: 'offRoute' } as const, null as NavOffRoute | null)
const waypointClock = atom({ plugin: 'navigator', key: 'waypointClock' } as const, null as NavWaypointClock | null)
const trip = atom({ plugin: 'navigator', key: 'trip' } as const, null as NavTrip | null)
const reads = atom({ plugin: 'navigator', key: 'reads' } as const, NO_READS)
const judge = atom({ plugin: 'navigator', key: 'judge' } as const, null as NavJudge | null)
const showJudge = atom({ plugin: 'navigator', key: 'showJudge' } as const, false)
// A memory the user pinned in the pane; rides the next prompt as context, then clears.
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

/** Collect what the pane shows: open tasks, the active task's steps, memories, newest marker, graph size. */
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
  const memories = await run(ioOf($), ['python3', `${functions}/memory_recall.py`, '--auto',
    '--agent-dir', '.agent', '--graph-path', graphPath, '--limit', String(MEMORY_LINES), '--format', 'compact'], root)
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
    memories: parseMemories(memories),
  }))
}

/** The `judge` section of the shared runtime state (tallies behind the pane's `j`). */
const judgeSection = async ($: EngineInterface): Promise<unknown> => {
  const io = ioOf($)
  const root = await projectRoot(io)
  if (root === null) return null
  return (await readJson(io, `${root}/${STATE_FILE}`))?.judge ?? null
}

// The Prometheus of `.agent/grafana/docker-compose.yml` (host port 9092).
const PROMETHEUS_URL = 'http://localhost:9092'
const TRIP_TIMEOUT_S = 1

/**
 * The trip panel's numbers from a Prometheus on this machine; null (panel hidden) when the stack
 * is down, has no Claude Code metrics, the URL is not loopback, `dashboard.enabled` is false, or
 * under Pilot. Runs on /nav and refresh. Read with curl, not $.http.fetch: a session with
 * CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC refuses every plugin fetch, loopback included, and
 * nothing here leaves the host.
 */
const refreshTrip = async ($: EngineInterface): Promise<void> => {
  const io = ioOf($)
  const root = await projectRoot(io)
  const cfg = root === null ? null : await loadConfig(io, root)
  const base = String(getPath(cfg, 'dashboard.prometheus_url', PROMETHEUS_URL)).replace(/\/+$/, '')
  if (root === null || cfg === null || getPath(cfg, 'dashboard.enabled', true) !== true
    || !isLoopback(base) || await isPilotExecutor(io)) {
    await update($, trip, () => null)
    return
  }
  const get = async (path: string, query: string, extra = ''): Promise<string | null> => {
    const url = `${base}/api/v1/${path}?query=${encodeURIComponent(query)}${extra}`
    const out = await run(io, ['curl', '-sfg', '--noproxy', '*', '--max-time', String(TRIP_TIMEOUT_S), url],
      root, (TRIP_TIMEOUT_S + 1) * 1000)
    return out === '' ? null : out
  }
  const now = await $.clock.now()
  const end = Math.floor(now / 1000)
  const queries = Object.entries(tripQueries(secondsSinceMidnight(now)))
  // One probe first, so a stopped stack costs one refused connection, not eleven.
  const probe = await get('query', tripQueries(0)['week.tokens']!, `&time=${end}`)
  const probed = probe === null ? null : parseVector(probe)
  if (probed === null || Object.keys(probed).length === 0) {
    await update($, trip, () => null)
    return
  }
  const [range, ...vectors] = await Promise.all([
    get('query_range', PER_MINUTE,
      `&start=${end - PER_MINUTE_SPAN_SEC}&end=${end}&step=${PER_MINUTE_STEP_SEC}`),
    ...queries.map(([, q]) => get('query', q, `&time=${end}`)),
  ])
  const results = Object.fromEntries(queries.map(([key], i) => {
    const text = vectors[i]
    return [key, text == null ? null : parseVector(text)]
  }))
  const built = buildTrip(results, range == null ? null : parseMatrix(range))
  const source = `prometheus ${/:\d+$/.exec(base)?.[0] ?? base}`
  await update($, trip, () => (built === null ? null : { ...built, source }))
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
const TASK_LABEL = 10 // task card: label column before the text
const MEMORY_LINES = 3
const PANE_COLUMNS = 72

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
    await Promise.all([refreshPane($), refreshTrip($).catch(() => {})])
    await $.ui.open({
      id: PANE, title: 'Navigator', focus: true, closeOnEscape: true, columns: PANE_COLUMNS,
    })
    return {}
  })

  on('tool.call', { tool: 'Read' }, async ($, e, next) => {
    const pre = await runFor($, 'PreToolUse', toolPayload(e as unknown as Record<string, unknown>))
    if (pre?.deny != null) return { deny: pre.deny }
    const ran = await next(e)
    const isDoc = e.file_path.includes('/.agent/')
    if (ran.deny === undefined) {
      await update($, reads, r => countRead({ ...NO_READS, ...r }, isDoc))
    }
    if (isDoc && ran.deny === undefined) {
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
    if (ctx !== null) {
      await update($, judge, () => judgeView(ctx.judgment as Judgment | null | undefined, ctx.judgeAxes, merged?.context ?? null))
    }
    const memory = await read($, pinned)
    if (memory !== null) await update($, pinned, () => null)
    const extra = [
      ...(merged?.context ? [merged.context] : []),
      ...(memory === null ? [] : [`Navigator memory pinned by the user for this prompt: ${memory}`]),
    ]
    const entered = extra.length > 0
      ? await next({ ...e, context: [...(e.context ?? []), ...extra] })
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
    await update($, reads, r => endTurnReads({ ...NO_READS, ...r }))
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
    const t = await read($, trip)
    const r = { ...NO_READS, ...((await read($, reads)) ?? {}) }
    const j = await read($, judge)
    const judgeOpen = await read($, showJudge)
    const chosen = await read($, pinned)
    const percent = s?.ctxPercent ?? null
    const pct = percent === null ? '--%' : `${Math.round(percent)}%`
    const ctxColor = percentColor(percent)
    const left = turnsTo(hist.ctx, 70)
    const lowFuel = (percent !== null && percent >= 70) || (left !== null && left <= LOW_FUEL_TURNS)
    const isOff = (detour?.count ?? 0) >= OFF_ROUTE_AFTER
    const at = here === null ? 0 : route.indexOf(here) + 1
    const then = here === null ? null : route.slice(at).find(w => w.state === 'todo') ?? null
    const window = u?.rates[0]
    const cacheHit = t?.today.cacheHit ?? t?.week.cacheHit ?? null
    const tally = judgeOpen ? judgeTally(await judgeSection($)) : []
    const panel = { borderStyle: 'round', borderColor: PALETTE.border, paddingX: 1 } as const
    const title = (text: string, color: string = PALETTE.accent) => (
      <Box marginBottom={1}><Text color={color}>{text}</Text></Box>
    )
    const dimLabel = (text: string) => <Text color={PALETTE.dim}>{text.padEnd(TASK_LABEL)}</Text>

    return (
      <Box flexDirection="column">
        <Box flexDirection="row">
          <Box {...panel} flexDirection="column" width="31%">
            {title('context')}
            <Text wrap="truncate-end">
              <Text color={ctxColor} bold>{pct}</Text> <Text color={ctxColor}>{gauge(percent, 10)}</Text>
            </Text>
            <Text color={lowFuel ? PALETTE.warning : PALETTE.dim} wrap="truncate-end">
              {lowFuel ? 'compact due' : a.lastTurnCommitted ? 'good moment to compact' : 'compact safe'}
            </Text>
            <Text color={PALETTE.accent}>{sparkline(hist.ctx, 14)}</Text>
          </Box>
          <Box {...panel} flexDirection="column" width="43%">
            {title('session')}
            {t === null ? (
              <Box flexDirection="column">
                <Text wrap="truncate-end">
                  <Text color={PALETTE.success} bold>{u?.usd == null ? '--' : `$${u.usd.toFixed(2)}`}</Text>
                  <Text color={PALETTE.dim}>{window ? `  ${rateKind(window.kind)} ${Math.round(window.percentUsed)}%` : ''}</Text>
                </Text>
                <Text color={PALETTE.label} wrap="truncate-end">{s?.phase ? `phase ${s.phase}` : 'phase —'}</Text>
                <Text color={PALETTE.dim} wrap="truncate-end">{p.graph ? `graph ${compact(p.graph.nodes)} nodes` : 'graph —'}</Text>
              </Box>
            ) : (
              <Box flexDirection="column">
                <Text wrap="truncate-end">
                  <Text color={PALETTE.success} bold>${t.today.usd.toFixed(2)}</Text>
                  <Text color={PALETTE.dim}>  {compact(t.today.tokens)}{cacheHit === null ? '' : ` · ${Math.round(cacheHit * 100)}% cache`}</Text>
                </Text>
                <Text color={PALETTE.dim} wrap="truncate-end">7d ${t.week.usd.toFixed(2)} · {t.week.commits} commits</Text>
                <Text wrap="truncate-end">
                  <Text color={PALETTE.accent}>{sparkline(t.perMinute, 12)}</Text>
                  <Text color={PALETTE.dim}>  tokens/min · {t.source}</Text>
                </Text>
              </Box>
            )}
          </Box>
          <Box {...panel} flexDirection="column" width="26%">
            {title('reads')}
            <Text wrap="truncate-end">
              <Text color={PALETTE.accent} bold>{r.total}</Text>
              <Text color={PALETTE.dim}>  {r.docs} docs</Text>
            </Text>
            <Text color={fanOutText(r) === 'fan-out ok' ? PALETTE.dim : PALETTE.warning}>{fanOutText(r)}</Text>
            <Text> </Text>
          </Box>
        </Box>

        {j === null ? null : (
          <Box {...panel} flexDirection="column">
            <Box flexDirection="row" justifyContent="space-between">
              <Text wrap="truncate-end">
                <Text color={PALETTE.accent}>judge  </Text>
                <Text color={PALETTE.label} bold>{j.verdict}</Text>
                <Text color={PALETTE.dim}>  → {j.effect}</Text>
                {j.override === null ? null : <Text color={PALETTE.warning}>   {j.override}</Text>}
              </Text>
              <Text color={PALETTE.dim}>{j.model}</Text>
            </Box>
            {tally.map(line => <Text color={PALETTE.dim} wrap="truncate-end">{line}</Text>)}
          </Box>
        )}

        <Box {...panel} flexDirection="column">
          {title('task')}
          {dest === null ? (
            <Text color={PALETTE.dim} wrap="wrap">no destination · say what you're building, or mark a task in progress</Text>
          ) : (
            <Text wrap="truncate-end">
              <Text color={PALETTE.accent} bold>{(dest.taskId ?? 'brief').padEnd(TASK_LABEL)}</Text>
              <Text color={PALETTE.label}>{dest.title}</Text>
            </Text>
          )}
          {here !== null ? (
            <Box flexDirection="row" justifyContent="space-between">
              <Text wrap="truncate-end">
                <Text color={PALETTE.accent}>{`● ${at}/${route.length}`.padEnd(TASK_LABEL)}</Text>
                <Text color={PALETTE.label} bold>{here.label}</Text>
              </Text>
              {clock && clock.turns > 0 ? (
                <Text color={PALETTE.dim}>{clock.turns} {clock.turns === 1 ? 'turn' : 'turns'} here</Text>
              ) : null}
            </Box>
          ) : arrived(route) ? (
            <Text color={PALETTE.success}>arrived · pick the next destination</Text>
          ) : s?.next ? (
            <Text wrap="truncate-end">{dimLabel('→ next')}<Text color={PALETTE.label}>{s.next}</Text></Text>
          ) : null}
          {then === null ? null : (
            <Text wrap="truncate-end">{dimLabel('→ then')}<Text color={PALETTE.dim}>{then.label}</Text></Text>
          )}
          {p.marker === null ? null : (
            <Text wrap="truncate-end">{dimLabel('marker')}<Text color={PALETTE.dim}>{p.marker}</Text></Text>
          )}
        </Box>

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
        ) : null}

        <Box {...panel} flexDirection="column">
          {title('memories')}
          {p.memories.length === 0 && <Text color={PALETTE.dim}>none for the open tasks</Text>}
          {p.memories.slice(0, MEMORY_LINES).map((m, i) => (
            <Box flexDirection="row">
              <Button key={`mem-${i}`} label={chosen === m.text ? '●' : '▸'} plain
                onPress={() => update($, pinned, () => (chosen === m.text ? null : m.text))} />
              <Text wrap="truncate-end">
                <Text> </Text>
                <Text color={PALETTE.accent} bold>{m.kind.toLowerCase()}</Text>
                <Text color={PALETTE.dim}>{m.percent === null ? '' : ` ${m.percent}%`}</Text>
                <Text color={chosen !== null && chosen !== m.text ? PALETTE.dim : PALETTE.label}>  {m.text}</Text>
              </Text>
            </Box>
          ))}
          <Text color={PALETTE.dim}>
            {chosen === null ? '▸ pins a memory into your next prompt' : '● pinned for your next prompt'}
          </Text>
        </Box>

        <Box {...panel} flexDirection="column">
          {title('open tasks')}
          {p.tasks.length === 0 && <Text color={PALETTE.dim}>none marked in progress</Text>}
          {[...p.tasks].reverse().slice(0, 5).map(task => (
            <Text wrap="truncate-end">
              <Text color={task.id === dest?.taskId ? PALETTE.success : PALETTE.dim}>{task.id === dest?.taskId ? '● ' : '○ '}</Text>
              <Text color={task.id === dest?.taskId ? PALETTE.label : PALETTE.dim}>{task.id}</Text>
              <Text color={PALETTE.dim}>{task.title ? `  ${task.title}` : ''}</Text>
            </Text>
          ))}
        </Box>

        <Box flexDirection="row" columnGap={2} paddingX={1}>
          <Button key="marker" label="marker" hotkey="m" plain
            onPress={() => $.prompt.submit({ text: 'Create context marker checkpoint', asUser: true })} />
          <Text color={PALETTE.dim}>·</Text>
          <Button key="compact" label="compact" hotkey="c" plain onPress={() => $.session.compact()} />
          <Text color={PALETTE.dim}>·</Text>
          <Button key="refresh" label="refresh" hotkey="r" plain onPress={() => Promise.all([refreshPane($), refreshTrip($).catch(() => {})])} />
          {j === null ? null : <Text color={PALETTE.dim}>·</Text>}
          {j === null ? null : (
            <Button key="judge" label="judge" hotkey="j" plain onPress={() => update($, showJudge, v => !v)} />
          )}
        </Box>
      </Box>
    )
  })
}
