import { expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

const PLUGIN = 'nav-status'
const CWD = '/repo'
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
  return { writes, envSets }
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
