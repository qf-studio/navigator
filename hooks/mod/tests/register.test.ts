import { expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

import { JUDGE_CASES } from './fixtures/judge.gen'

const PLUGIN = 'navigator'
const CWD = '/repo'
const AGENT = `${CWD}/.agent`
const CFG = '/cfg'
const PERSONAL = `${CFG}/adhd-mode.json`
const REPO_CONFIG = `${CWD}/.agent/.nav-config.json`
const SURFACES = ['terminal', 'desktop'] as const

type Files = Record<string, string>
type Write = { path: string; text: string }
type EnvSet = { name: string; value?: string }

// The world beneath the plugin: an in-memory FS, a fixed cwd, a fixed usage.
const world = (on: On, files: Files, percentIn?: number | (() => number)) => {
  const allWrites: Write[] = []
  // Only writes to the personal switch; the runtime state file is saved every event.
  const writes: Write[] = []
  const envSets: EnvSet[] = []
  const opened: string[] = []
  // A Navigator project: ops only run where `.agent/` exists (v7 parity).
  if (!(`${AGENT}/.nav-config.json` in files)) files[`${AGENT}/.nav-config.json`] = '{}'
  on('session.version', () => ({ value: { version: '2.1.287', base: '2.1.287', builtAt: '' } }))
  on('session.id', () => ({ value: 'session-1' }))
  mock.env(on, { HOME: '/home/me', NAVIGATOR_CONFIG_HOME: CFG })
  mock.clock(on, { now: 1_700_000_000_000 })
  on('session.cwd', () => ({ value: CWD }))
  on('session.usage', () => {
    const percent = typeof percentIn === 'function' ? percentIn() : percentIn
    return {
      value: {
        startedAt: 0,
        context: { window: 200000, ...(percent === undefined ? {} : { percent }) },
        rateLimits: [],
      },
    }
  })
  on('fs.exists', (_$, e) => ({
    value: e.path in files || Object.keys(files).some(p => p.startsWith(`${e.path}/`)),
  }))
  on('fs.read', (_$, e) =>
    e.path in files ? { value: files[e.path] ?? '' } : { deny: `missing ${e.path}` },
  )
  on('fs.write', (_$, e) => {
    allWrites.push({ path: e.path, text: e.text })
    if (e.path === PERSONAL) writes.push({ path: e.path, text: e.text })
    files[e.path] = e.text
    return { value: undefined }
  })
  on('env.set', (_$, e) => {
    envSets.push({ name: e.name, value: e.value })
    return { value: undefined }
  })
  on('prompt.submit', (_$, e) => ({ text: e.text, context: e.context }))
  on('tool.call', (_$, e) => ({ result: {}, text: e.tool === 'Read' ? 'x'.repeat(8000) : 'ok' }))
  on('turn.complete', (_$, e) => ({ text: e.answer }))
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  on('classic.SessionStart', () => ({}))
  on('ui.render', { component: 'AbovePrompt' }, () => ({ type: 'engine', ref: 0 }))
  on('ui.render', { component: 'Pane' }, () => ({ type: 'engine', ref: 0 }))
  on('ui.open', (_$, e) => {
    opened.push(e.id)
    return { value: { isPlaced: true } }
  })
  on('command.register', (_$, e) => ({ value: { command: e.name } }))
  on('command.run', () => ({}))
  on('fs.list', (_$, e) => ({
    value: Object.keys(files)
      .filter(f => f.startsWith(`${e.path}/`))
      .map(f => ({
        name: f.slice(e.path.length + 1), kind: 'file' as const, size: 1,
        mtimeMs: (files[f] ?? '').length, isLink: false,
      })),
  }))
  curlReply = null
  on('process.run', (_$, e) => {
    if (e.argv[0] === 'curl') {
      const out = curlReply?.(String(e.argv[e.argv.length - 1])) ?? null
      const exitCode = out === null ? 7 : 0
      return { value: { exitCode, stdout: out ?? '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    }
    return { value: {
      exitCode: 0, stderr: '', isStdoutTruncated: false, isStderrTruncated: false,
      stdout: e.argv[0] === 'sh'
        ? String(e.argv[2]).startsWith('find')
          ? '400000\n'
          : '.agent/tasks/TASK-15-x.md|# TASK-15: Marketing plan\n'
            + '.agent/tasks/TASK-80-judge.md|# TASK-80: Typed judge, phase 2\n'
        : String(e.argv[1]).endsWith('graph_manager.py')
          ? 'Total Nodes: 195\nTotal Edges: 843\nMemories: 71\n'
          : e.argv.includes('--concepts')
            ? '- PATTERN: "hooks dispatch through one entry point" (88%)\n'
            : '- PITFALL: "stop gate over-fires on heredoc Bash" (90%)\n- DECISION: "state v2 atomic" (95%)\n',
    } }
  })
  return { writes, allWrites, envSets, opened }
}

const submit = ($: Engine, text: string) =>
  $.prompt.submit({ text, origin: { kind: 'composer' }, wait: false })

const complete = ($: Engine, answer: string) =>
  $.turn.complete({ answer, durationMs: 1, isAborted: false, turnId: 't1', reason: 'answer' })

const band = ($: Engine, surface: (typeof SURFACES)[number], hasSurvey = false) =>
  $.ui.mount({
    plugin: PLUGIN,
    surface,
    component: 'AbovePrompt',
    props: {
      hasSurvey,
      isWorking: false,
      maxRows: 5,
      bodyColumns: 80,
      scroll: { offset: 0, bodyRows: 5 },
      view: {},
    },
  })

test('(a) injects the ADHD block when the personal switch is on', async ($, on) => {
  world(on, { [PERSONAL]: JSON.stringify({ on: true }) })
  const r = await submit($, 'fix the flaky test')
  expect(r.drop).toBeUndefined()
  expect(r.context).toHaveLength(1)
  expect(r.context?.[0]?.startsWith('ADHD MODE: on (')).toBe(true)
  expect(r.text).toBe('fix the flaky test')
})

test('(a2) injects nothing when nothing is switched on', async ($, on) => {
  world(on, {})
  const r = await submit($, 'fix the flaky test')
  expect(r.drop).toBeUndefined()
  expect((r.context ?? []).some(c => c.includes('ADHD MODE: on ('))).toBe(false)
})

test('(b) a repo pin off wins over the personal switch', async ($, on) => {
  world(on, {
    [PERSONAL]: JSON.stringify({ on: true }),
    [REPO_CONFIG]: JSON.stringify({ adhd_mode: { on: false } }),
  })
  const r = await submit($, 'fix the flaky test')
  expect(r.drop).toBeUndefined()
  expect((r.context ?? []).some(c => c.includes('ADHD MODE: on ('))).toBe(false)
})

test('(c) "adhd mode on" drops the prompt and writes the personal file', async ($, on) => {
  const { writes } = world(on, {})
  const r = await submit($, 'adhd mode on')
  expect(typeof r.drop).toBe('string')
  expect(r.drop).toContain('ADHD mode: on (personal, /cfg/adhd-mode.json)')
  expect(writes).toHaveLength(1)
  expect(writes[0]?.path).toBe(PERSONAL)
  expect(JSON.parse(writes[0]?.text ?? '{}').on).toBe(true)
})

test('(c2) "adhd mode" reports status without writing', async ($, on) => {
  const { writes } = world(on, { [PERSONAL]: JSON.stringify({ on: true }) })
  const r = await submit($, 'adhd mode')
  expect(r.drop).toContain('ADHD mode: on (personal switch, /cfg/adhd-mode.json).')
  expect(r.drop).toContain('Say "adhd mode on" or "adhd mode off".')
  expect(writes).toHaveLength(0)
})

test('(c3) a prompt that merely mentions ADHD is not a toggle', async ($, on) => {
  const { writes } = world(on, {})
  const r = await submit($, 'I have ADHD, keep replies short')
  expect(r.drop).toBeUndefined()
  expect(writes).toHaveLength(0)
})

test('(d) the band is one quiet line: waypoint, then destination once known', async ($, on) => {
  world(on, {}, 42)
  await complete($, 'NAVIGATOR_STATUS\nPhase: IMPL\nIteration: 2/5\nNext Action: run tests\n')
  for (const surface of SURFACES) {
    const ui = await band($, surface)
    expect((await ui.find({ type: 'Text' }))?.text ?? '').toBe('on route: ● impl 2/4 · next: run tests')
    await ui.unmount()
  }
  await $.command.run(NAV_CMD)
  const ui = await band($, 'terminal')
  expect((await ui.find({ type: 'Text' }))?.text ?? '').toBe('on route: Typed judge, phase 2 · ● impl 2/4 · next: run tests')
  await ui.unmount()
})

test('(d2) a goal stated in a brief becomes the destination', async ($, on) => {
  world(on, {})
  await complete($, '| Goal | Ship the route view |\n| Scope | pane + band |\nPhase: RESEARCH\n')
  const ui = await band($, 'terminal')
  expect((await ui.find({ type: 'Text' }))?.text ?? '').toBe('on route: Ship the route view · ● research 1/4')
  await ui.unmount()
})

test('(d3) the band is quiet before any turn and under a survey', async ($, on) => {
  world(on, {}, 42)
  const quiet = await band($, 'terminal')
  expect(await quiet.find({ type: 'Text' })).toBeUndefined()
  await quiet.unmount()
  await complete($, 'Phase: VERIFY\n')
  const survey = await band($, 'terminal', true)
  expect(await survey.find({ type: 'Text' })).toBeUndefined()
  await survey.unmount()
})

test('(d4) subagent turns do not drive the band', async ($, on) => {
  world(on, {}, 42)
  await $.turn.complete({
    answer: 'Phase: RESEARCH\n', durationMs: 1, isAborted: false,
    turnId: 't2', reason: 'answer', agentId: 'agent-1',
  })
  const ui = await band($, 'terminal')
  expect(await ui.find({ type: 'Text' })).toBeUndefined()
  await ui.unmount()
})

test('(e) session.start claims ADHD ownership through the environment', async ($, on) => {
  const { envSets } = world(on, {})
  await $.session.start({ cwd: CWD, surface: 'terminal', isInteractive: true })
  expect(envSets).toContainEqual({ name: 'NAVIGATOR_MOD_OWNS', value: 'prompt_gate,prompt_tier1,prompt_adhd,prompt_brief,read_guard,jit_memory,graph_sync,profile_sync,failure_diagnosis,stop_completion,stop_state,session_start,compact_marker,subagent_context,config_guard,setup' })
})

const NAV_CMD = {
  command: 'nav', args: '', origin: { kind: 'composer' as const },
  presentation: { isFullscreen: false, columns: 120 },
}

const navPane = ($: Engine, surface: (typeof SURFACES)[number]) =>
  $.ui.mount({
    plugin: PLUGIN,
    surface,
    component: 'Pane',
    requestId: 'nav',
    props: {
      title: 'Navigator', isFocused: true, bodyColumns: 60, placement: 'inline',
      scroll: { offset: 0, bodyRows: 20 }, view: {},
    },
  })

test('(f) /nav: context, session, reads on top; then the task with its leg, memories, open tasks', async ($, on) => {
  const { opened } = world(on, {
    [`${AGENT}/knowledge/graph.json`]: JSON.stringify({ concept_index: { hooks: [], session: [] } }),
  }, 42)
  await complete($, 'Phase: IMPL\nNext: wire the band\n')
  await $.command.run(NAV_CMD)
  expect(opened).toContain('nav')
  for (const surface of SURFACES) {
    const ui = await navPane($, surface)
    const texts = (await ui.findAll({ type: 'Text' })).map(t => t.text).join('\n')
    expect(texts).toContain('TASK-80   Typed judge, phase 2')
    expect(texts).toContain('● 2/4     impl') // the current leg, numbered
    expect(texts).toContain('→ then    verify')
    expect(texts).not.toContain('research') // passed legs stay out of the pane
    expect(texts).not.toContain('wire the band') // the reply's next line is not the route
    for (const card of ['context', 'session', 'reads', 'task', 'memories', 'in progress']) expect(texts).toContain(card)
    expect(texts.indexOf('context')).toBeLessThan(texts.indexOf('task'))
    expect(texts).toContain('42%')
    expect(texts).toContain('compact safe')
    expect(texts).toContain('phase IMPL')
    expect(texts).toContain('graph 195 nodes')
    expect(texts).toContain('0  0 docs')
    expect(texts).toContain('stop gate over-fires on heredoc Bash') // memories for the open tasks
    expect(texts).toContain('○ TASK-15  Marketing plan')
    expect(texts).not.toContain('judge  ') // nothing judged yet: no card, no key
    expect(await ui.findAll({ type: 'Button' })).toHaveLength(5) // 2 memories + m c r
    await ui.unmount()
  }
})

test('(h) phase is sticky across turns and the leg clock counts turns', async ($, on) => {
  world(on, {}, 10)
  await $.command.run(NAV_CMD)
  await complete($, 'Phase: IMPL\n')
  await complete($, 'Removed the marker.\n\nNext: run the mod tests.\n')
  const all = await texts($)
  expect(all).toContain('● 2/4     impl')
  expect(all).toContain('1 turn here')
})

const texts = async ($: Engine) => {
  const ui = await navPane($, 'terminal')
  const all = (await ui.findAll({ type: 'Text' })).map(t => t.text).join('\n')
  await ui.unmount()
  return all
}

test('(i) reads card: doc and code reads counted, three code reads in a turn say "use an Agent"', async ($, on) => {
  world(on, { [`${AGENT}/.nav-config.json`]: '{}' }, 20)
  await $.command.run(NAV_CMD)
  await $.tool.call({ tool: 'Read', file_path: `${AGENT}/tasks/TASK-80.md` } as never)
  await $.turn.complete({
    answer: 'done', durationMs: 1, isAborted: false, turnId: 'a1', reason: 'answer', agentId: 'sub-1',
    usage: {
      model: 'm', input_tokens: 1000, output_tokens: 500,
      cache_read_input_tokens: 30000, cache_creation_input_tokens: 0,
    },
  } as never)
  await complete($, 'Next: commit it\n')
  let all = await texts($)
  expect(all).toContain('1  1 docs')
  expect(all).toContain('fan-out ok')
  for (const f of ['a.py', 'b.py', 'c.py']) await $.tool.call({ tool: 'Read', file_path: `${CWD}/${f}` } as never)
  all = await texts($)
  expect(all).toContain('4  1 docs')
  expect(all).toContain('use an Agent')
  await complete($, 'ok\n') // the verdict is the last turn's until a new read lands
  expect(await texts($)).toContain('use an Agent')
  await $.tool.call({ tool: 'Read', file_path: `${AGENT}/system/x.md` } as never)
  expect(await texts($)).toContain('fan-out ok')
})

test('(j) a committed turn turns the fuel hint into a nudge', async ($, on) => {
  world(on, { [`${AGENT}/.nav-config.json`]: '{}' }, 20)
  await $.command.run(NAV_CMD)
  await $.tool.call({ tool: 'Bash', command: 'git commit -m x' } as never)
  await complete($, 'Committed.\n')
  expect(await texts($)).toContain('good moment to compact')
})

test('(l) context forecast projects turns to 70%', async ($, on) => {
  let percent = 10
  world(on, {}, () => percent)
  await $.command.run(NAV_CMD)
  for (const p of [10, 20, 30]) { percent = p; await complete($, 'step\n') }
  expect(await texts($)).toContain('compact due') // ~4 turns to 70% at this slope
})

test('(n) classic.SessionStart re-announces ownership before the Python child runs', async ($, on) => {
  const { envSets } = world(on, {})
  await $.classic.SessionStart({ source: 'compact' } as never)
  expect(envSets).toContainEqual({ name: 'NAVIGATOR_MOD_OWNS', value: 'prompt_gate,prompt_tier1,prompt_adhd,prompt_brief,read_guard,jit_memory,graph_sync,profile_sync,failure_diagnosis,stop_completion,stop_state,session_start,compact_marker,subagent_context,config_guard,setup' })
})

test('(o) read_guard through tool.call: warn as context at 3, deny at 5', async ($, on) => {
  world(on, { [`${AGENT}/.nav-config.json`]: '{}' }, 10)
  const readDoc = (i: number) =>
    $.tool.call({ tool: 'Read', file_path: `${AGENT}/tasks/T-${i}.md`, tool_use_id: `tu-${i}` } as never)
  const results = []
  for (let i = 1; i <= 5; i += 1) results.push(await readDoc(i) as { deny?: string; context?: readonly string[] })
  expect(results[0]?.context ?? []).toEqual([])
  expect((results[2]?.context ?? []).join('\n')).toContain('[nav-read-guard] 3 .agent/ files read this turn')
  expect(results[4]?.deny ?? '').toContain('blocked at 5 .agent/ reads')
})

test('(p) two substantive prompts away from the destination open the off-route panel', async ($, on) => {
  world(on, { [`${AGENT}/.nav-config.json`]: '{}' }, 20)
  await $.command.run(NAV_CMD)
  await submit($, 'what should I post on threads about marketing feedback replies')
  let ui = await band($, 'terminal')
  expect((await ui.find({ type: 'Text' }))?.text ?? '').not.toContain('off route')
  await ui.unmount()
  await submit($, 'draft another threads reply for the marketing audience please')
  ui = await band($, 'terminal')
  expect((await ui.find({ type: 'Text' }))?.text ?? '').toMatch(/^off route: .+ · \/nav to park or go back$/)
  await ui.unmount()
  const all = await texts($)
  expect(all).toContain('⚠ off route')
  expect(all).toContain('last 2 prompts are about')
  expect(all).toContain('destination is "Typed judge, phase 2"')
})

test('(q) short replies never count, and an on-topic prompt clears the detour', async ($, on) => {
  world(on, { [`${AGENT}/.nav-config.json`]: '{}' }, 20)
  await $.command.run(NAV_CMD)
  await submit($, 'yes go ahead')
  await submit($, 'ok')
  expect(await texts($)).not.toContain('⚠ off route')
  await submit($, 'what should I post on threads about marketing feedback replies')
  await submit($, 'draft another threads reply for the marketing audience please')
  await submit($, 'back to the typed judge phase 2 evidence collection')
  expect(await texts($)).not.toContain('⚠ off route')
})

test('(r) park writes a task stub and returns to the route', async ($, on) => {
  const { allWrites } = world(on, {
    [`${AGENT}/.nav-config.json`]: '{}',
    [`${AGENT}/tasks/TASK-84-v8.md`]: '# TASK-84: v8',
  }, 20)
  await $.command.run(NAV_CMD)
  await submit($, 'what should I post on threads about marketing feedback replies')
  await submit($, 'draft another threads reply for the marketing audience please')
  const ui = await navPane($, 'terminal')
  await ui.press({ key: 'park' })
  await ui.unmount()
  const stub = allWrites.find(w => /\/\.agent\/tasks\/TASK-85-.+\.md$/.test(w.path))
  expect(stub?.text ?? '').toContain('# TASK-85: ')
  expect(stub?.text ?? '').toContain('Parked')
  expect(stub?.text ?? '').toContain('> what should I post on threads')
  expect(await texts($)).not.toContain('⚠ off route')
})

test('(s) a task checklist becomes the route', async ($, on) => {
  world(on, {
    [`${AGENT}/.nav-config.json`]: '{}',
    [`${CWD}/.agent/tasks/TASK-80-judge.md`]: '# TASK-80\n- [x] collect evidence\n- [ ] add surface\n- [ ] ship\n',
  }, 20)
  await $.command.run(NAV_CMD)
  const all = await texts($)
  expect(all).toContain('● 2/3     add surface')
  expect(all).toContain('→ then    ship')
  expect(all).not.toContain('collect evidence')
})

test('(s2) a numbered plan with ✅ progress headings becomes the route', async ($, on) => {
  world(on, {
    [`${AGENT}/.nav-config.json`]: '{}',
    [`${CWD}/.agent/tasks/TASK-80-judge.md`]: [
      '# TASK-80', '## Work breakdown', '| # | Step |', '|---|---|',
      '| 1 | Baseline | ', '| 2 | Port the scorer; keep parity | ', '| 3 | Ship |',
      '## Progress log', '### Step 1 — baseline ✅',
    ].join('\n'),
  }, 20)
  await $.command.run(NAV_CMD)
  const all = await texts($)
  expect(all).toContain('● 2/3     Port the scorer')
  expect(all).not.toContain('keep parity')
  expect(all).toContain('→ then    Ship')
  expect(all).not.toContain('Baseline')
})

// Prometheus of .agent/grafana/docker-compose.yml behind `curl` (the panel never uses
// $.http.fetch: sessions with nonessential traffic disabled refuse it, loopback included).
let curlReply: ((url: string) => string | null) | null = null
const prometheus = (_on: On, fetches: string[], up = true) => {
  const vector = (rows: [Record<string, string>, number][]) => JSON.stringify({
    status: 'success',
    data: { resultType: 'vector', result: rows.map(([metric, v]) => ({ metric, value: [1, String(v)] })) },
  })
  curlReply = url => {
    fetches.push(url)
    if (!up) return null
    const q = decodeURIComponent(/query=([^&]*)/.exec(url)?.[1] ?? '')
    const week = q.includes('[7d]')
    return url.includes('/query_range')
      ? JSON.stringify({ status: 'success', data: { resultType: 'matrix', result: [{ metric: {}, values: [[1, '10'], [2, '40']] }] } })
      : q.includes('cost') ? vector([[{}, week ? 31.8 : 4.12]])
      : q.includes('token_usage') ? vector([[{ type: 'input' }, 100_000], [{ type: 'cacheRead' }, 900_000], [{ type: 'output' }, 50_000]])
      : q.includes('commit') ? vector([[{}, week ? 41 : 6]])
      : q.includes('lines') ? vector([[{ type: 'added' }, 820], [{ type: 'removed' }, 214]])
      : vector([[{}, 7800]])
  }
}

test('(t) the session card shows Prometheus numbers when the local stack answers', async ($, on) => {
  world(on, {}, 20)
  const fetches: string[] = []
  prometheus(on, fetches)
  await $.command.run(NAV_CMD)
  const all = await texts($)
  expect(all).toContain('$4.12')
  expect(all).toContain('1.1M · 90% cache')
  expect(all).toContain('7d $31.80 · 41 commits')
  expect(all).toContain('tokens/min · prometheus :9092')
  expect(all).not.toContain('phase —') // the Prometheus lines replace the local ones
  expect(fetches).toHaveLength(12) // probe + range + 10 instant queries
  expect(fetches.every(u => u.startsWith('http://localhost:9092/api/v1/'))).toBe(true)
})

test('(t4) a non-loopback prometheus_url is never read', async ($, on) => {
  world(on, {
    [`${AGENT}/.nav-config.json`]: JSON.stringify({ dashboard: { prometheus_url: 'http://prom.example.com:9090' } }),
  }, 20)
  const fetches: string[] = []
  prometheus(on, fetches)
  await $.command.run(NAV_CMD)
  expect(await texts($)).not.toContain('prometheus')
  expect(fetches).toHaveLength(0)
})

test('(t2) a stopped stack leaves the local session card after one refused probe', async ($, on) => {
  world(on, {}, 20)
  const fetches: string[] = []
  prometheus(on, fetches, false)
  await $.command.run(NAV_CMD)
  const all = await texts($)
  expect(all).not.toContain('prometheus')
  expect(all).toContain('phase —')
  expect(fetches).toHaveLength(1)
})

test('(t3) dashboard.enabled false never fetches', async ($, on) => {
  world(on, { [`${AGENT}/.nav-config.json`]: JSON.stringify({ dashboard: { enabled: false } }) }, 20)
  const fetches: string[] = []
  prometheus(on, fetches)
  await $.command.run(NAV_CMD)
  expect(await texts($)).not.toContain('prometheus')
  expect(fetches).toHaveLength(0)
})

// The typed judge answers through $.http.fetch; the key comes from the personal file.
const judged = (on: On, files: Files, caseIndex: number) => {
  files[`${AGENT}/.nav-config.json`] = JSON.stringify({ judge: { enabled: true } })
  files['/home/me/.config/typesafe/api_key'] = 'k-test\n'
  const doc = (JUDGE_CASES[caseIndex] as { doc: unknown }).doc
  on('http.fetch', () => ({ value: { status: 200, ok: true, headers: {}, text: JSON.stringify(doc) } }))
}

test('(u) the judge card: verdict in words, the effect, the axes it overrode; j opens the tally', async ($, on) => {
  const files: Files = {}
  judged(on, files, 30) // "make the onboarding better": task, substantial, ambiguous; brief shown
  world(on, files, 20)
  await $.command.run(NAV_CMD)
  expect(await texts($)).not.toContain('judge  ')
  const r = await submit($, 'make the onboarding better')
  expect(r.context?.join('\n') ?? '').toContain('NAV-BRIEF')
  const ui = await navPane($, 'terminal')
  let all = (await ui.findAll({ type: 'Text' })).map(t => t.text).join('\n')
  expect(all).toContain('judge  task · substantial · unclear  → brief shown   ↑ complexity, task: jev over rule')
  expect(all).toContain('jev-1.13.0')
  expect(all).not.toContain('calls')
  await ui.press({ key: 'judge' })
  all = (await ui.findAll({ type: 'Text' })).map(t => t.text).join('\n')
  expect(all).toContain('1 calls · 0 failed · latency')
  expect(all).toContain('task        agreed 0 · overrode 1 · undecided 0 · jev over rule 100%')
  expect(all).toContain('complexity  agreed 0 · overrode 1 · undecided 0 · jev over rule 100%')
  expect(all).toContain('unclear     agreed 1 · overrode 0 · undecided 0 · jev over rule 0%')
  await ui.unmount()
})

test('(u2) a chat prompt reads "chat · direct"; no card without a judgment', async ($, on) => {
  const files: Files = {}
  judged(on, files, 9) // "what does loop mode actually do?"
  world(on, files, 20)
  await $.command.run(NAV_CMD)
  await submit($, 'what does loop mode actually do?')
  const all = await texts($)
  // complexity moved (0.02) but stayed in the same tier: that axis counts as agreed, not overrode
  expect(all).toContain('judge  chat  → direct   ↑ loop: jev over rule')
  expect(all).not.toContain('unclear')
})

test('(v) a pinned memory rides the next prompt once', async ($, on) => {
  world(on, {}, 20)
  await $.command.run(NAV_CMD)
  const ui = await navPane($, 'terminal')
  await ui.press({ key: 'mem-0' })
  expect((await ui.findAll({ type: 'Text' })).map(t => t.text).join('\n')).toContain('● pinned for your next prompt')
  await ui.unmount()
  const first = await submit($, 'go on')
  expect(first.context?.join('\n') ?? '').toContain('Navigator memory pinned by the user for this prompt: stop gate over-fires on heredoc Bash')
  const second = await submit($, 'go on')
  expect(second.context?.join('\n') ?? '').not.toContain('pinned')
  expect(await texts($)).toContain('▸ pins a memory into your next prompt')
})
