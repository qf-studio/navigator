import { expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

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
  on('process.run', (_$, e) => ({
    value: {
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
    },
  }))
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

test('(d) the band shows phase, context percent and next action', async ($, on) => {
  world(on, {}, 42)
  await complete($, 'NAVIGATOR_STATUS\nPhase: IMPL\nIteration: 2/5\nNext Action: run tests\n')
  for (const surface of SURFACES) {
    const ui = await band($, surface)
    const text = (await ui.find({ type: 'Text' }))?.text ?? ''
    expect(text).toContain('phase IMPL')
    expect(text).toContain('ctx 42%')
    expect(text).toContain('next: run tests')
    await ui.unmount()
  }
})

test('(d2) the band reads a bold Next action: line', async ($, on) => {
  world(on, {})
  await complete($, '**Next action:** run the tests.\n\n- detail one\n')
  const ui = await band($, 'terminal')
  const text = (await ui.find({ type: 'Text' }))?.text ?? ''
  expect(text).toContain('next: run the tests.')
  expect(text).not.toContain('ctx')
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
  expect(envSets).toContainEqual({ name: 'NAVIGATOR_MOD_OWNS', value: 'prompt_gate,prompt_tier1,prompt_adhd,prompt_brief,read_guard,jit_memory,graph_sync,profile_sync,failure_diagnosis,stop_completion,stop_state' })
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

test('(f) /nav opens the pane with task, context bar and memories', async ($, on) => {
  const { opened } = world(on, {
    [`${AGENT}/knowledge/graph.json`]: JSON.stringify({ concept_index: { hooks: [], session: [] } }),
    [`${AGENT}/.context-markers/z-newest-by-mtime.md`]: 'xx',
    [`${AGENT}/.context-markers/a-older.md`]: '',
  }, 42)
  await complete($, 'Phase: IMPL\n')
  await $.command.run(NAV_CMD)
  expect(opened).toContain('nav')
  for (const surface of SURFACES) {
    const ui = await navPane($, surface)
    const texts = (await ui.findAll({ type: 'Text' })).map(t => t.text).join('\n')
    expect(texts).toContain('TASK-80')
    expect(texts).toContain('42%')
    expect(texts).toContain('z-newest-by-mtime')
    expect(texts).toContain('TASK-15')
    expect(texts).toContain('Typed judge, phase 2')
    expect(texts).toContain('~100.0K tokens')
    expect(texts).toContain('stop gate over-fires on heredoc Bash')
    expect(await ui.findAll({ type: 'Button' })).toHaveLength(5)
    expect(texts).toContain('compact: hold, mid-task')
    await ui.unmount()
  }
})

test('(g) a pinned memory rides the next prompt once', async ($, on) => {
  world(on, { [`${AGENT}/.nav-config.json`]: '{}' })
  await $.command.run(NAV_CMD)
  const ui = await navPane($, 'terminal')
  await ui.press({ key: 'mem-0' })
  const first = await submit($, 'fix the gate')
  expect(first.context?.some(c => c.includes('stop gate over-fires'))).toBe(true)
  const second = await submit($, 'and again')
  expect((second.context ?? []).some(c => c.includes('stop gate over-fires'))).toBe(false)
  await ui.unmount()
})

test('(h) phase is sticky across turns and a "Next:" line feeds the band', async ($, on) => {
  world(on, {}, 10)
  await complete($, 'Phase: IMPL\n')
  await complete($, 'Removed the marker.\n\nNext: run the mod tests.\n')
  const ui = await band($, 'terminal')
  const text = (await ui.find({ type: 'Text' }))?.text ?? ''
  expect(text).toContain('phase IMPL')
  expect(text).toContain('next: run the mod tests.')
  await ui.unmount()
})

const texts = async ($: Engine) => {
  const ui = await navPane($, 'terminal')
  const all = (await ui.findAll({ type: 'Text' })).map(t => t.text).join('\n')
  await ui.unmount()
  return all
}

test('(i) doc reads and subagent turns feed the savings panel', async ($, on) => {
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
  const all = await texts($)
  expect(all).toContain('loaded 8.0KB of 400.0KB')
  expect(all).toContain('(1 reads)')
  expect(all).toContain('1 turns · 31.5K tokens processed outside')
  expect(all).toContain('~98.0K tokens')
  expect(all).toContain('commit it')
})

test('(j) a committed turn turns the compact hint into a nudge', async ($, on) => {
  world(on, { [`${AGENT}/.nav-config.json`]: '{}' }, 20)
  await $.command.run(NAV_CMD)
  await $.tool.call({ tool: 'Bash', command: 'git commit -m x' } as never)
  await complete($, 'Committed.\n')
  expect(await texts($)).toContain('good moment to compact: just committed')
})

test('(k) memories follow the concepts the prompt names', async ($, on) => {
  world(on, {
    [`${AGENT}/.nav-config.json`]: '{}',
    [`${AGENT}/knowledge/graph.json`]: JSON.stringify({ concept_index: { hooks: [], session: [] } }),
  }, 20)
  await $.command.run(NAV_CMD)
  await submit($, 'why do the hooks fire twice')
  const all = await texts($)
  expect(all).toContain('for: hooks')
  expect(all).toContain('hooks dispatch through one entry point')
})

test('(l) context forecast projects turns to 70%', async ($, on) => {
  let percent = 10
  world(on, {}, () => percent)
  await $.command.run(NAV_CMD)
  for (const p of [10, 20, 30]) { percent = p; await complete($, 'step\n') }
  expect(await texts($)).toContain('~4 turns to 70%')
})

test('(n) classic.SessionStart re-announces ownership before the Python child runs', async ($, on) => {
  const { envSets } = world(on, {})
  await $.classic.SessionStart({ source: 'compact' } as never)
  expect(envSets).toContainEqual({ name: 'NAVIGATOR_MOD_OWNS', value: 'prompt_gate,prompt_tier1,prompt_adhd,prompt_brief,read_guard,jit_memory,graph_sync,profile_sync,failure_diagnosis,stop_completion,stop_state' })
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
