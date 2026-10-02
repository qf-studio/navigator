import { expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

const PLUGIN = 'nav-status'
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
const world = (on: On, files: Files, percent?: number) => {
  const writes: Write[] = []
  const envSets: EnvSet[] = []
  const opened: string[] = []
  mock.env(on, { HOME: '/home/me', NAVIGATOR_CONFIG_HOME: CFG })
  mock.clock(on, { now: 1_700_000_000_000 })
  on('session.cwd', () => ({ value: CWD }))
  on('session.usage', () => ({
    value: {
      startedAt: 0,
      context: { window: 200000, ...(percent === undefined ? {} : { percent }) },
      rateLimits: [],
    },
  }))
  on('fs.exists', (_$, e) => ({
    value: e.path in files || Object.keys(files).some(p => p.startsWith(`${e.path}/`)),
  }))
  on('fs.read', (_$, e) =>
    e.path in files ? { value: files[e.path] ?? '' } : { deny: `missing ${e.path}` },
  )
  on('fs.write', (_$, e) => {
    writes.push({ path: e.path, text: e.text })
    files[e.path] = e.text
    return { value: undefined }
  })
  on('env.set', (_$, e) => {
    envSets.push({ name: e.name, value: e.value })
    return { value: undefined }
  })
  on('prompt.submit', (_$, e) => ({ text: e.text, context: e.context }))
  on('turn.complete', (_$, e) => ({ text: e.answer }))
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
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
        name: f.slice(e.path.length + 1), kind: 'file' as const, size: 1, mtimeMs: 0, isLink: false,
      })),
  }))
  on('process.run', (_$, e) => ({
    value: {
      exitCode: 0, stderr: '', isStdoutTruncated: false, isStderrTruncated: false,
      stdout: e.argv[0] === 'sh'
        ? '.agent/tasks/TASK-15-x.md\n.agent/tasks/TASK-80-judge.md\n'
        : '- PITFALL: "stop gate over-fires on heredoc Bash" (90%)\n- DECISION: "state v2 atomic" (95%)\n',
    },
  }))
  return { writes, envSets, opened }
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
  expect(r.context ?? []).toHaveLength(0)
})

test('(b) a repo pin off wins over the personal switch', async ($, on) => {
  world(on, {
    [PERSONAL]: JSON.stringify({ on: true }),
    [REPO_CONFIG]: JSON.stringify({ adhd_mode: { on: false } }),
  })
  const r = await submit($, 'fix the flaky test')
  expect(r.drop).toBeUndefined()
  expect(r.context ?? []).toHaveLength(0)
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

test('(d2) the band falls back to the first line of the reply', async ($, on) => {
  world(on, {})
  await complete($, '**Next action:** run the tests.\n\n- detail one\n')
  const ui = await band($, 'terminal')
  const text = (await ui.find({ type: 'Text' }))?.text ?? ''
  expect(text).toContain('next: Next action: run the tests.')
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
  expect(envSets).toContainEqual({ name: 'NAVIGATOR_MOD_OWNS', value: 'adhd' })
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
    [`${AGENT}/.context-markers/a-old.md`]: '',
    [`${AGENT}/.context-markers/b-new.md`]: '',
  }, 42)
  await complete($, 'Phase: IMPL\n')
  await $.command.run(NAV_CMD)
  expect(opened).toContain('nav')
  for (const surface of SURFACES) {
    const ui = await navPane($, surface)
    const texts = (await ui.findAll({ type: 'Text' })).map(t => t.text).join('\n')
    expect(texts).toContain('TASK-80')
    expect(texts).toContain('phase IMPL')
    expect(texts).toContain('42%')
    expect(texts).toContain('last marker b-new')
    expect(texts).toContain('PITFALL stop gate over-fires')
    expect(await ui.findAll({ type: 'Button' })).toHaveLength(6)
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
