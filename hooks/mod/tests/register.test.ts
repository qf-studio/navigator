import { expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

import { JUDGE_CASES } from './fixtures/judge.gen'

const PLUGIN = 'navigator'
const CWD = '/repo'
const AGENT = `${CWD}/.agent`
const CFG = '/cfg'
const PERSONAL = `${CFG}/adhd-mode.json`
const PERSONAL_STE = `${CFG}/ste-mode.json`
const REPO_CONFIG = `${CWD}/.agent/.nav-config.json`
const SURFACES = ['terminal', 'desktop'] as const

type Files = Record<string, string>
type Write = { path: string; text: string }
type EnvSet = { name: string; value?: string }

// The world beneath the plugin: an in-memory FS, a fixed cwd, a fixed usage.
const world = (on: On, files: Files, percentIn?: number | (() => number)) => {
  const allWrites: Write[] = []
  const submitted: string[] = [] // what reached the engine's prompt.submit
  // Only writes to the personal switch; the runtime state file is saved every event.
  const writes: Write[] = []
  const envSets: EnvSet[] = []
  const opened: string[] = []
  // A Navigator project: ops only run where `.agent/` exists (v7 parity).
  if (!(`${AGENT}/.nav-config.json` in files)) files[`${AGENT}/.nav-config.json`] = '{}'
  // Two in-progress task docs unless the test brings its own (TASK-91: the Status line decides).
  if (!Object.keys(files).some(f => f.startsWith(`${AGENT}/tasks/`))) {
    files[`${AGENT}/tasks/TASK-15-x.md`] = '# TASK-15: Marketing plan\n\n**Status**: 🚧 In Progress\n'
    files[`${AGENT}/tasks/TASK-80-judge.md`] = '# TASK-80: Typed judge, phase 2\n\n**Status**: 🚧 In Progress\n'
  }
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
    if (e.path === PERSONAL || e.path === PERSONAL_STE) writes.push({ path: e.path, text: e.text })
    files[e.path] = e.text
    return { value: undefined }
  })
  on('env.set', (_$, e) => {
    envSets.push({ name: e.name, value: e.value })
    return { value: undefined }
  })
  on('prompt.submit', (_$, e) => { submitted.push(e.text); return { text: e.text, context: e.context } })
  // A Bash command ending in `# ro` is one core holds read-only (TASK-85 evidence).
  on('tool.call', (_$, e) => ({
    result: {}, text: e.tool === 'Read' ? 'x'.repeat(8000) : 'ok',
    ...(e.tool === 'Bash' && /# ro$/.test(String((e as { command?: string }).command)) ? { isReadOnly: true as const } : {}),
  }))
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
        ? '400000\n' // the docs-tree byte count
        : String(e.argv[1]).endsWith('graph_manager.py')
          ? 'Total Nodes: 195\nTotal Edges: 843\nMemories: 71\n'
          : e.argv.includes('--concepts')
            ? '- PATTERN: "hooks dispatch through one entry point" (88%)\n'
            : '- PITFALL: "stop gate over-fires on heredoc Bash" (90%)\n- DECISION: "state v2 atomic" (95%)\n',
    } }
  })
  return { writes, allWrites, envSets, opened, submitted }
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

test('(c4) "use ste" writes the STE file only; both blocks stack in table order', async ($, on) => {
  const { writes } = world(on, { [PERSONAL]: JSON.stringify({ on: true }) })
  const t = await submit($, 'use ste')
  expect(t.drop).toContain('STE mode: on (personal, /cfg/ste-mode.json)')
  expect(t.drop).toContain('Say "ste mode off" to stop.')
  expect(writes).toHaveLength(1)
  expect(writes[0]?.path).toBe(PERSONAL_STE)
  const r = await submit($, 'fix the flaky test')
  expect(r.context).toHaveLength(1)
  const ctx = r.context?.[0] ?? ''
  expect(ctx.startsWith('ADHD MODE: on (')).toBe(true)
  expect(ctx).toContain('\n\nSTE MODE: on (')
  expect(ctx.indexOf('ADHD MODE')).toBeLessThan(ctx.indexOf('STE MODE'))
})

test('(c5) a disabled mode answers its toggle without writing', async ($, on) => {
  const { writes } = world(on, { [REPO_CONFIG]: JSON.stringify({ ste_mode: { enabled: false } }) })
  const r = await submit($, 'ste mode on')
  expect(r.drop).toContain('STE mode: disabled in this repo (ste_mode.enabled')
  expect(writes).toHaveLength(0)
})

test('(d) the band is one quiet line: waypoint, then destination once known', async ($, on) => {
  world(on, {}, 42)
  await complete($, 'NAVIGATOR_STATUS\nPhase: IMPL\nIteration: 2/5\nNext Action: run tests\n')
  for (const surface of SURFACES) {
    const ui = await band($, surface)
    expect((await ui.find({ type: 'Text' }))?.text ?? '').toBe('nav · ● 2/4 impl · 3 legs left')
    await ui.unmount()
  }
  await $.command.run(NAV_CMD)
  const ui = await band($, 'terminal')
  expect((await ui.find({ type: 'Text' }))?.text ?? '').toBe('nav · TASK-80 · ● 2/4 impl · 3 legs left')
  await ui.unmount()
})

test('(d2) a goal stated in a brief becomes the destination', async ($, on) => {
  world(on, {})
  await complete($, '| Goal | Ship the route view |\n| Scope | pane + band |\nPhase: RESEARCH\n')
  const ui = await band($, 'terminal')
  expect((await ui.find({ type: 'Text' }))?.text ?? '').toBe('nav · Ship the route view · ● 1/4 research · 4 legs left')
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
  expect(envSets).toContainEqual({ name: 'NAVIGATOR_MOD_OWNS', value: 'prompt_gate,prompt_tier1,prompt_modes,prompt_brief,read_guard,jit_memory,graph_sync,profile_sync,failure_diagnosis,stop_completion,stop_state,session_start,compact_marker,subagent_context,config_guard,setup' })
})

const NAV_CMD = {
  command: 'nav', args: '', origin: { kind: 'composer' as const },
  presentation: { isFullscreen: false, columns: 120 },
}

const navPane = ($: Engine, surface: (typeof SURFACES)[number], bodyColumns = 72) =>
  $.ui.mount({
    plugin: PLUGIN,
    surface,
    component: 'Pane',
    requestId: 'nav',
    props: {
      title: 'Navigator', isFocused: true, bodyColumns, placement: 'inline', // 72 is the pane's own default width
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
    expect(texts).toContain('→ then    verify')
    expect(texts).toContain('3 legs left') // impl, verify, complete; no leg finished yet: no eta
    expect(texts).not.toContain('research') // passed legs stay out of the pane
    expect(texts).not.toContain('wire the band') // the reply's next line is not the route
    for (const card of ['context', 'session', 'next', 'memories']) expect(texts).toContain(card)
    expect(texts.indexOf('context')).toBeLessThan(texts.indexOf('next'))
    expect(texts).toContain('42%')
    expect(texts).toContain('compact safe')
    expect(texts).toContain('phase IMPL')
    expect(texts).toContain('graph 195 nodes')
    expect(texts).toContain('stop gate over-fires on heredoc Bash') // memories for the open tasks
    expect(texts).not.toContain('judge  ') // nothing judged yet: no card, no key
    expect(texts).not.toContain('docs') // reads and the task list wait behind d
    expect(texts).not.toContain('TASK-15')
    const buttons = (await ui.findAll({ type: 'Button' })).map(b => b.text)
    expect(buttons).toContain('● 2/4  impl') // the current leg is the press
    expect(buttons).toHaveLength(8) // leg + 2 memories + m c r d l
    await ui.press({ key: 'details' })
    const more = (await ui.findAll({ type: 'Text' })).map(t => t.text).join('\n')
    expect(more).toContain('0  0 docs')
    expect(more).toContain('○ TASK-15  Marketing plan')
    await ui.press({ key: 'details' }) // state persists into the next surface's pass
    await ui.unmount()
  }
})

test('(h) phase is sticky across turns and the leg clock counts turns', async ($, on) => {
  world(on, {}, 10)
  await $.command.run(NAV_CMD)
  await complete($, 'Phase: RESEARCH\n')
  await complete($, 'Phase: IMPL\n')
  await complete($, 'Removed the marker.\n\nNext: run the mod tests.\n')
  const all = await texts($)
  expect(all).toContain('1 turn here')
  expect(all).toContain('eta ~1m · 3 legs left') // research took 1 turn of 1 ms: pace known, floored to a minute
})

test('(h2) n submits the current leg as the prompt', async ($, on) => {
  const { submitted } = world(on, {}, 10)
  await $.command.run(NAV_CMD)
  await complete($, 'Phase: IMPL\n')
  const ui = await navPane($, 'terminal')
  await ui.press({ key: 'leg' })
  await ui.unmount()
  expect(submitted).toEqual(['Do the next leg of TASK-80: impl'])
})

const texts = async ($: Engine, details = false) => {
  const ui = await navPane($, 'terminal')
  if (details) await ui.press({ key: 'details' })
  const all = (await ui.findAll({ type: 'Text' })).map(t => t.text).join('\n')
  if (details) await ui.press({ key: 'details' })
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
  let all = await texts($, true)
  expect(all).toContain('1  1 docs')
  expect(all).toContain('fan-out ok')
  for (const f of ['a.py', 'b.py', 'c.py']) await $.tool.call({ tool: 'Read', file_path: `${CWD}/${f}` } as never)
  all = await texts($, true)
  expect(all).toContain('4  1 docs')
  expect(all).toContain('use an Agent')
  await complete($, 'ok\n') // the verdict is the last turn's until a new read lands
  expect(await texts($, true)).toContain('use an Agent')
  await $.tool.call({ tool: 'Read', file_path: `${AGENT}/system/x.md` } as never)
  expect(await texts($, true)).toContain('fan-out ok')
})

test('(i2) reads through Bash count like the Read tool: cat/sed on .agent/ is a doc read, three code files say "use an Agent"', async ($, on) => {
  world(on, { [`${AGENT}/.nav-config.json`]: '{}' }, 20)
  await $.command.run(NAV_CMD)
  await $.tool.call({ tool: 'Bash', command: `sed -n '1,40p' ${AGENT}/tasks/TASK-80.md | head` } as never)
  let all = await texts($, true)
  expect(all).toContain('1  1 docs')
  expect(all).toContain('fan-out ok')
  await $.tool.call({ tool: 'Bash', command: 'cat hooks/a.ts hooks/b.ts && grep -n x hooks/c.ts' } as never)
  all = await texts($, true)
  expect(all).toContain('4  1 docs')
  expect(all).toContain('use an Agent')
  await $.tool.call({ tool: 'Bash', command: 'cat notes.md > /tmp/out.md' } as never) // a write: not a read
  expect(await texts($, true)).toContain('4  1 docs')
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
  expect(envSets).toContainEqual({ name: 'NAVIGATOR_MOD_OWNS', value: 'prompt_gate,prompt_tier1,prompt_modes,prompt_brief,read_guard,jit_memory,graph_sync,profile_sync,failure_diagnosis,stop_completion,stop_state,session_start,compact_marker,subagent_context,config_guard,setup' })
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
    [`${AGENT}/tasks/TASK-84-v8.md`]: '# TASK-84: v8\n\n**Status**: 🚧 In Progress\n',
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
    [`${CWD}/.agent/tasks/TASK-80-judge.md`]: '# TASK-80\n**Status**: 🚧 In Progress\n- [x] collect evidence\n- [ ] add surface\n- [ ] ship\n',
  }, 20)
  await $.command.run(NAV_CMD)
  const all = await texts($)
  expect(all).toContain('→ then    ship')
  expect(all).not.toContain('collect evidence')
  const ui = await navPane($, 'terminal')
  expect((await ui.findAll({ type: 'Button' })).map(b => b.text)).toContain('● 2/3  add surface')
  await ui.unmount()
})

test('(s3) on the last leg the leg row carries "last leg" since there is no then', async ($, on) => {
  world(on, {
    [`${AGENT}/.nav-config.json`]: '{}',
    [`${CWD}/.agent/tasks/TASK-80-judge.md`]: '# TASK-80\n**Status**: 🚧 In Progress\n- [x] collect evidence\n- [x] add surface\n- [ ] ship\n',
  }, 20)
  await $.command.run(NAV_CMD)
  const all = await texts($)
  expect(all).not.toContain('→ then')
  expect(all).toContain('last leg')
})

test('(s2) a numbered plan with ✅ progress headings becomes the route', async ($, on) => {
  world(on, {
    [`${AGENT}/.nav-config.json`]: '{}',
    [`${CWD}/.agent/tasks/TASK-80-judge.md`]: [
      '# TASK-80', '**Status**: 🚧 In Progress', '## Work breakdown', '| # | Step |', '|---|---|',
      '| 1 | Baseline | ', '| 2 | Port the scorer; keep parity | ', '| 3 | Ship |',
      '## Progress log', '### Step 1 — baseline ✅',
    ].join('\n'),
  }, 20)
  await $.command.run(NAV_CMD)
  const all = await texts($)
  expect(all).not.toContain('keep parity')
  expect(all).toContain('→ then    Ship')
  expect(all).not.toContain('Baseline')
  const ui = await navPane($, 'terminal')
  expect((await ui.findAll({ type: 'Button' })).map(b => b.text)).toContain('● 2/3  Port the scorer')
  await ui.unmount()
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
  expect(all).toContain('tokens/min')
  expect(all).not.toContain('prometheus') // the source shows with the details only
  expect(all).not.toContain('phase —') // the Prometheus lines replace the local ones
  expect(await texts($, true)).toContain('session · prometheus :9092')
  expect(fetches).toHaveLength(12) // probe + range + 10 instant queries
  expect(fetches.every(u => u.startsWith('http://localhost:9092/api/v1/'))).toBe(true)
})

test('(t5) the session card follows the turns: Prometheus is read again after each one', async ($, on) => {
  world(on, {}, 20)
  const fetches: string[] = []
  prometheus(on, fetches)
  await $.command.run(NAV_CMD)
  expect(fetches).toHaveLength(12)
  await complete($, 'one turn\n')
  expect(fetches).toHaveLength(24)
  await $.turn.complete({
    answer: 'sub', durationMs: 1, isAborted: false, turnId: 's1', reason: 'answer', agentId: 'sub-1',
  } as never)
  expect(fetches).toHaveLength(24) // subagent turns do not
})

test('(t6) a turn that wrote under .agent/ reloads the task list and marker', async ($, on) => {
  const files: Files = {}
  world(on, files, 20)
  await $.command.run(NAV_CMD)
  expect(await texts($)).not.toContain('marker')
  files[`${AGENT}/.context-markers/fresh-2026-10-03.md`] = '# marker'
  await complete($, 'no write\n')
  expect(await texts($)).not.toContain('fresh-2026-10-03') // nothing under .agent/ was written
  await $.tool.call({ tool: 'Write', file_path: `${AGENT}/tasks/TASK-80.md`, content: 'x' } as never)
  await complete($, 'wrote a doc\n')
  expect(await texts($)).toContain('marker    fresh-2026-10-03')
})

test('(t7) a mutating Bash that names .agent/ reloads the pane at turn end like Edit does (TASK-89)', async ($, on) => {
  const files: Files = {}
  world(on, files, 20)
  await $.command.run(NAV_CMD)
  files[`${AGENT}/.context-markers/fresh-2026-10-05.md`] = '# marker'
  await $.tool.call({ tool: 'Bash', command: `cat ${AGENT}/tasks/TASK-80.md # ro` } as never) // a read
  await complete($, 'read only\n')
  expect(await texts($)).not.toContain('fresh-2026-10-05')
  await $.tool.call({ tool: 'Bash', command: `cat > ${AGENT}/tasks/TASK-80.md <<'EOF'\nx\nEOF` } as never)
  await complete($, 'wrote through bash\n')
  expect(await texts($)).toContain('marker    fresh-2026-10-05')
})

test('(t8) git mv / git commit reload the pane too; other mutating Bash does not', async ($, on) => {
  const files: Files = {}
  world(on, files, 20)
  await $.command.run(NAV_CMD)
  files[`${AGENT}/.context-markers/moved-2026-10-05.md`] = '# marker'
  await $.tool.call({ tool: 'Bash', command: 'npm run build' } as never)
  await complete($, 'built\n')
  expect(await texts($)).not.toContain('moved-2026-10-05')
  await $.tool.call({ tool: 'Bash', command: 'git mv a/TASK-81.md a/archive/TASK-81.md' } as never)
  await complete($, 'archived\n')
  expect(await texts($)).toContain('marker    moved-2026-10-05')
})

test('(t9) editing the active task doc moves the next card before the turn ends (TASK-89)', async ($, on) => {
  const files: Files = {
    [`${AGENT}/.nav-config.json`]: '{}',
    [`${CWD}/.agent/tasks/TASK-80-judge.md`]: '# TASK-80\n**Status**: 🚧 In Progress\n- [ ] collect evidence\n- [ ] add surface\n- [ ] ship\n',
  }
  world(on, files, 20)
  await $.command.run(NAV_CMD)
  expect(await texts($)).toContain('→ then    add surface')
  files[`${CWD}/.agent/tasks/TASK-80-judge.md`] = '# TASK-80\n**Status**: 🚧 In Progress\n- [x] collect evidence\n- [ ] add surface\n- [ ] ship\n'
  await $.tool.call({ tool: 'Edit', file_path: `${CWD}/.agent/tasks/TASK-80-judge.md`, old_string: 'a', new_string: 'b' } as never)
  const mid = await texts($) // no turn.complete yet: the leg already advanced
  expect(mid).toContain('→ then    ship')
  expect(mid).not.toContain('collect evidence')
})

test('(t10) a subagent turn marks docs touched: the parent turn reloads the pane', async ($, on) => {
  const files: Files = {}
  world(on, files, 20)
  await $.command.run(NAV_CMD)
  files[`${AGENT}/.context-markers/agent-2026-10-05.md`] = '# marker'
  await $.turn.complete({
    answer: 'done', durationMs: 1, isAborted: false, turnId: 'a1', reason: 'answer', agentId: 'sub-1',
    usage: { model: 'm', input_tokens: 1, output_tokens: 1, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 },
  } as never)
  await complete($, 'agent finished\n')
  expect(await texts($)).toContain('marker    agent-2026-10-05')
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

test('(u4) stacked below 72 columns: the judge version takes its own line, the next card wraps', async ($, on) => {
  const files: Files = {}
  judged(on, files, 30)
  world(on, files, 20)
  await $.command.run(NAV_CMD)
  await submit($, 'make the onboarding better')
  const wide = await navPane($, 'terminal', 72)
  const wideVersion = (await wide.findAll({ type: 'Text' })).filter(t => t.text === 'jev-1.13.0')
  expect(wideVersion).toHaveLength(1) // in the row layout the version sits beside the verdict
  await wide.unmount()
  const narrow = await navPane($, 'terminal', 46)
  const lines = (await narrow.findAll({ type: 'Text' })).map(t => t.text)
  expect(lines.filter(t => t === 'jev-1.13.0')).toHaveLength(1) // its own line
  expect(lines.join('\n')).toContain('judge  task · substantial · unclear')
  expect(lines.join('\n')).toContain('TASK-80   Typed judge, phase 2') // not truncated
})

test('(u) the judge card: verdict in words, the effect, the axes it overrode; j opens the tally', async ($, on) => {
  const files: Files = {}
  judged(on, files, 30) // "make the onboarding better": task, substantial, ambiguous; brief shown
  const { allWrites } = world(on, files, 20)
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
  // TASK-86: the trail and the label keys
  expect(all).toMatch(/\d\d:\d\d · task · substantial · unclear  "make the onboarding better"/)
  expect((await ui.findAll({ type: 'Button' })).map(b => b.text)).toEqual(expect.arrayContaining(['verdict right', 'wrong']))
  await ui.press({ key: 'confirm' })
  const written = allWrites.find(w => w.path === `${CFG}/judge-labels.json`)
  const doc = JSON.parse(written?.text ?? '{}') as { prompts: Record<string, unknown>[] }
  expect(doc.prompts).toHaveLength(1)
  expect(doc.prompts[0]).toMatchObject({ text: 'make the onboarding better', tier: 'TASK', task: true, ambiguous: true, project: 'repo', source: 'pane', judged: 'task · substantial · unclear' })
  all = (await ui.findAll({ type: 'Text' })).map(t => t.text).join('\n')
  expect(all).toContain(' ✓ task · substantial · unclear  "make the onboarding better"')
  expect((await ui.findAll({ type: 'Button' })).map(b => b.text)).not.toContain('verdict right') // labeled once
  await ui.unmount()
})

test('(u3) a disputed verdict lands in the label file with tier null for judge_label.py to label', async ($, on) => {
  const files: Files = { [`${CFG}/judge-labels.json`]: JSON.stringify({ _doc: 'x', prompts: [{ text: 'older', tier: 'DIRECT', task: false, ambiguous: false }] }) }
  judged(on, files, 9)
  const { allWrites } = world(on, files, 20)
  await $.command.run(NAV_CMD)
  await submit($, 'what does loop mode actually do?')
  const ui = await navPane($, 'terminal')
  await ui.press({ key: 'judge' })
  await ui.press({ key: 'dispute' })
  await ui.unmount()
  const doc = JSON.parse(allWrites.find(w => w.path === `${CFG}/judge-labels.json`)?.text ?? '{}') as { prompts: Record<string, unknown>[] }
  expect(doc.prompts).toHaveLength(2) // the older entry survives
  expect(doc.prompts[1]).toMatchObject({ text: 'what does loop mode actually do?', tier: null, disputed: true, judged: 'chat' })
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

// A Stop transcript in the harness shape: one Bash tool_use, its result, a closing line.
const bashTurn = (cmd: string): string => [
  { type: 'user', message: { role: 'user', content: 'check the port' } },
  { type: 'assistant', message: { role: 'assistant', content: [
    { type: 'text', text: 'looking' }, { type: 'tool_use', name: 'Bash', id: 'b0', input: { command: cmd } }] } },
  { type: 'user', message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: 'b0', is_error: false, content: 'ok' }] } },
  { type: 'assistant', message: { role: 'assistant', content: [{ type: 'text', text: 'Port 9464 is held by 97009; nothing changed.' }] } },
].map(e => JSON.stringify(e)).join('\n') + '\n'

const GATE_ON = JSON.stringify({ stop_completion: { enabled: true, continue_enabled: true, max_continues: 2 } })

test("(w) Stop gate: a Bash-only turn Claude Code held read-only never forces a continuation", async ($, on) => {
  const cmd = 'sqlite3 db.sqlite "select 1" # ro' // unknown head: the allowlist alone says mutating
  world(on, { [`${AGENT}/.nav-config.json`]: GATE_ON, [`${CWD}/t.jsonl`]: bashTurn(cmd) }, 20)
  on('classic.Stop', () => ({}))
  await $.tool.call({ tool: 'Bash', command: cmd } as never)
  const r = await $.classic.Stop({ transcript_path: `${CWD}/t.jsonl`, stop_hook_active: false, session_id: 'session-1' } as never)
  expect((r as { block?: unknown }).block).toBeUndefined()
})

test('(w2) the same turn without the read-only verdict is gated on the allowlist, and blocks', async ($, on) => {
  const cmd = 'sqlite3 db.sqlite "select 1"'
  world(on, { [`${AGENT}/.nav-config.json`]: GATE_ON, [`${CWD}/t.jsonl`]: bashTurn(cmd) }, 20)
  on('classic.Stop', () => ({}))
  await $.tool.call({ tool: 'Bash', command: cmd } as never)
  const r = await $.classic.Stop({ transcript_path: `${CWD}/t.jsonl`, stop_hook_active: false, session_id: 'session-1' } as never)
  expect(String((r as { block?: unknown }).block ?? '')).toContain('mutated the codebase')
})
