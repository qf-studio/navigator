import { describe, expect, test } from 'claude-code/testing'

import { deepMerge } from '../lib/config'
import { CONFIG_DEFAULTS } from '../lib/gen/config-defaults.gen'
import { sha256Hex } from '../lib/stop-sha256'
import type { Io, Json, Op, OpCtx } from '../lib/types'
import { stopCompletion } from '../ops/stop_completion'
import { stopState } from '../ops/stop_state'
import { CASES as A } from './fixtures/stopops-completion-a.gen'
import { CASES as B } from './fixtures/stopops-completion-b.gen'
import { CASES as C } from './fixtures/stopops-completion-c.gen'
import { COMPLETION_CONFIGS, NOW, STATE_CONFIGS, TRANSCRIPTS } from './fixtures/stopops-meta.gen'
import { CASES as S } from './fixtures/stopops-state.gen'

type Case = (typeof A)[number]

const ioFor = (c: Case): Io => ({
  pluginRoot: '/p',
  read: async path => {
    const m = /^\/t\/(.+)\.jsonl$/.exec(path)
    const text = m?.[1] === undefined ? undefined : TRANSCRIPTS[m[1]]
    if (text === undefined) throw new Error(`missing ${path}`)
    return text
  },
  write: async () => {}, exists: async () => false, list: async () => [],
  run: async argv => {
    if (argv.join(' ') !== 'git status --porcelain') throw new Error(`unexpected ${argv.join(' ')}`)
    if (c.gitResult === null) throw new Error('git timed out')
    return { exitCode: c.gitResult.exitCode, stdout: c.gitResult.stdout }
  },
  cwd: async () => '/r', sessionId: async () => 's', nowMs: async () => 0,
  version: async () => ({ version: '2.1.287' }), env: async () => ({ HOME: '/home/me' }),
  setOwned: async () => {}, http: async () => ({ ok: false, status: 500, text: '' }),
  sleep: async () => {}, disowned: async () => [], noteCrash: async () => 0, disown: async () => {},
})

const configOf = (table: Record<string, unknown>, name: string): Json =>
  deepMerge(JSON.parse(JSON.stringify(CONFIG_DEFAULTS)) as Json, (table[name] ?? {}) as Json)

const replay = async (op: Op, c: Case, table: Record<string, unknown>): Promise<string | null> => {
  const payload: Json = { ...c.payload }
  if (c.transcript !== null) payload.transcript_path = `/t/${c.transcript}.jsonl`
  const ctx: OpCtx = {
    io: ioFor(c), event: 'Stop', payload, config: configOf(table, c.config), root: '/r',
    sessionId: 's', now: NOW, pilotExecutor: c.pilot, state: JSON.parse(JSON.stringify(c.prior)) as Json,
  }
  const result = await op.run(ctx)
  const same = JSON.stringify(result) === JSON.stringify(c.result)
    && JSON.stringify(ctx.state) === JSON.stringify(c.after)
  return same ? null : `${c.group} ${String(c.transcript)} ${JSON.stringify(c.payload)} ${c.config} `
    + `${c.git} prior=${JSON.stringify(c.prior)} got=${JSON.stringify(result)} state=${JSON.stringify(ctx.state)}`
}

describe('Stop ops parity with hooks/ops/stop_completion.py and stop_state.py', () => {
  test('corpora present and exercising every branch', () => {
    const completion = [...A, ...B, ...C]
    expect(completion.length).toBeGreaterThan(900)
    expect(S.length).toBeGreaterThan(1000)
    expect(completion.filter(c => c.result !== null).length).toBeGreaterThan(50)
    expect(completion.some(c => JSON.stringify(c.after).includes('tree_digest'))).toBe(true)
    expect(S.filter(c => JSON.stringify(c.after).includes('"check_shown":true')).length).toBeGreaterThan(10)
    expect(S.filter(c => JSON.stringify(c.after).includes('"check_shown":false')).length).toBeGreaterThan(10)
  })
  test('stop_completion: result and state written', async () => {
    const misses: string[] = []
    for (const c of [...A, ...B, ...C]) {
      const miss = await replay(stopCompletion, c, COMPLETION_CONFIGS as Record<string, unknown>)
      if (miss !== null) misses.push(miss)
    }
    expect(misses.slice(0, 3)).toEqual([])
  })
  test('stop_state: ack and the turn record + reset barrel', async () => {
    const misses: string[] = []
    for (const c of S) {
      const miss = await replay(stopState, c, STATE_CONFIGS as Record<string, unknown>)
      if (miss !== null) misses.push(miss)
    }
    expect(misses.slice(0, 3)).toEqual([])
  })
  test('sha256 matches known vectors (hashlib)', () => {
    expect(sha256Hex('')).toBe('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')
    expect(sha256Hex('abc')).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
    expect(sha256Hex('é😀\n'.repeat(40))).toBe(sha256Hex('é😀\n'.repeat(40)))
  })
})
