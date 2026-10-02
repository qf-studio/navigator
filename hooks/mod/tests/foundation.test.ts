import { describe, expect, test } from 'claude-code/testing'

import { clamp } from '../lib/budget'
import { configAllows, deepMerge, getPath } from '../lib/config'
import { stripAll } from '../lib/sentinels'
import type { Io, Op, OpCtx, OpResult } from '../lib/types'
import { announce, compareVersions, ownedNow } from '../owns'
import { merge, runOps, suppressBlocking } from '../runner'
import { CLAMP_CASES, STRIP_CASES } from './fixtures/foundation.gen'

type FakeIo = Io & { owned: string[]; crashes: Record<string, number>; off: string[] }

const fakeIo = (version = '2.1.287'): FakeIo => {
  const io: FakeIo = {
    owned: [], crashes: {}, off: [],
    pluginRoot: '/plugin',
    read: async () => { throw new Error('no fs') },
    write: async () => {},
    exists: async () => false,
    list: async () => [],
    run: async () => ({ exitCode: 1, stdout: '' }),
    cwd: async () => '/repo',
    sessionId: async () => 's1',
    nowMs: async () => 0,
    version: async () => ({ version, base: version }),
    env: async () => ({}),
    setOwned: async v => { io.owned = v ? v.split(',') : [] },
    disowned: async () => io.off,
    noteCrash: async op => { io.crashes[op] = (io.crashes[op] ?? 0) + 1; return io.crashes[op] ?? 0 },
    disown: async op => { io.off = [...io.off, op] },
    http: async () => ({ ok: false, status: 500, text: '' }),
    sleep: async () => {},
  }
  return io
}

const ctxOf = (io: Io, event = 'UserPromptSubmit', pilotExecutor = false): OpCtx => ({
  io, event, payload: {}, config: {}, root: '/repo', pilotExecutor, now: 0, sessionId: 's1',
  state: {},
})

// Ops named after OWNED entries so the ownership check lets them run.
const op = (phase: Op['spec']['phase'], result: OpResult | null | (() => never)): Op => ({
  spec: { name: 'prompt_adhd', phase, configKey: null },
  run: async () => (typeof result === 'function' ? result() : result),
})

describe('parity with the Python runtime', () => {
  test('stripAll matches sentinels.strip_all on the fixture corpus', () => {
    for (const c of STRIP_CASES) expect(stripAll(c.input)).toBe(c.output)
  })
  test('clamp matches budget.clamp on the fixture corpus', () => {
    for (const c of CLAMP_CASES) expect(clamp(c.input, c.event)).toBe(c.output)
  })
})

describe('config', () => {
  test('dicts merge key-wise, lists and scalars replace, null leaves survive', () => {
    const merged = deepMerge({ a: { b: 1, c: [1, 2] }, n: 1 }, { a: { c: [3] }, n: null })
    expect(merged).toEqual({ a: { b: 1, c: [3] }, n: null })
    expect(getPath(merged, 'n', 'fallback')).toBeNull()
    expect(getPath(merged, 'a.zzz', 7)).toBe(7)
  })
  test('ops with a config key run only when <key>.enabled is true', () => {
    const spec = { name: 'x', phase: 'injectors' as const, configKey: 'feat' }
    expect(configAllows({ feat: { enabled: true } }, spec)).toBe(true)
    expect(configAllows({ feat: { enabled: false } }, spec)).toBe(false)
    expect(configAllows({}, spec)).toBe(false)
    expect(configAllows({}, { ...spec, configKey: null })).toBe(true)
  })
})

describe('ownership', () => {
  test('versions compare numerically and ignore suffixes', () => {
    expect(compareVersions('2.1.287', '2.1.287')).toBe(0)
    expect(compareVersions('2.1.290-dev', '2.1.287')).toBe(1)
    expect(compareVersions('2.1.99', '2.1.287')).toBe(-1)
  })
  test('below the minimum Claude Code version the mod owns nothing', async () => {
    const io = fakeIo('2.1.284')
    expect(await ownedNow(io)).toEqual([])
    await announce(io)
    expect(io.owned).toEqual([])
  })
  test('at the minimum it announces the owned ops', async () => {
    const io = fakeIo()
    await announce(io)
    expect(io.owned).toContain('prompt_adhd')
  })
})

describe('runner', () => {
  test('a blocking gate drops the prompt and starves later phases', async () => {
    const merged = await runOps(ctxOf(fakeIo()), [
      op('injectors', { additional_context: 'late' }),
      op('gates', { decision: 'block', reason: 'stop here' }),
    ])
    expect(merged.drop).toBe('stop here')
    expect(merged.context).toBeNull()
  })
  test('under Pilot no block escapes and later phases still run', async () => {
    const merged = await runOps(ctxOf(fakeIo(), 'UserPromptSubmit', true), [
      op('gates', { decision: 'block', reason: 'stop', additional_context: 'gate note' }),
      op('injectors', { additional_context: 'late' }),
    ])
    expect(merged.drop).toBeNull()
    expect(merged.context).toBe('gate note\nlate')
  })
  test('contexts join in registry order regardless of phase order', async () => {
    const merged = await runOps(ctxOf(fakeIo()), [
      op('injectors', { additional_context: 'first' }),
      op('responders', { additional_context: 'second' }),
    ])
    expect(merged.context).toBe('first\nsecond')
  })
  test('a crashing op is isolated; three crashes hand it back to Python', async () => {
    const io = fakeIo()
    await announce(io)
    const crash = op('injectors', () => { throw new Error('boom') })
    const ok = { ...op('injectors', { additional_context: 'still here' }) }
    for (let i = 0; i < 3; i += 1) await runOps(ctxOf(io), [crash, ok])
    expect(io.crashes.prompt_adhd).toBe(3)
    expect(io.off).toContain('prompt_adhd')
    expect(io.owned).not.toContain('prompt_adhd')
  })
  test('merge maps blocks per event: drop on prompts, deny on tools, block on Stop', () => {
    expect(merge('PreToolUse', [{ exit_code: 2, stderr: 'too many reads' }]).deny).toBe('too many reads')
    expect(merge('Stop', [{ decision: 'block', reason: 'finish' }]).block).toBe('finish')
    expect(merge('ConfigChange', [{ system_message: 'bad json' }]).toast).toBe('bad json')
  })
  test('suppressBlocking keeps non-blocking output', () => {
    expect(suppressBlocking({ decision: 'block', reason: 'x', additional_context: 'keep' }))
      .toEqual({ additional_context: 'keep' })
  })
})
