import { describe, expect, test } from 'claude-code/testing'

import { deepMerge } from '../lib/config'
import { CONFIG_DEFAULTS } from '../lib/gen/config-defaults.gen'
import type { Io, Json, OpCtx } from '../lib/types'
import { promptBrief } from '../ops/prompt_brief'
import { promptGate } from '../ops/prompt_gate'
import { OP_CASES as BRIEF_TIGHT } from './fixtures/ops-brief-tight.gen'
import { OP_CASES as DEFAULTS } from './fixtures/ops-defaults.gen'
import { OP_CASES as LENIENT } from './fixtures/ops-lenient.gen'
import { OP_VARIANTS } from './fixtures/ops-variants.gen'

const OP_CASES = [...DEFAULTS, ...LENIENT, ...BRIEF_TIGHT]

// No graph, no judge key: recall returns '' and the judge stays off, as in the fixtures.
const io: Io = {
  pluginRoot: '/p', read: async () => { throw new Error('none') }, write: async () => {},
  exists: async () => false, list: async () => [], run: async () => ({ exitCode: 1, stdout: '' }),
  cwd: async () => '/r', sessionId: async () => 's', nowMs: async () => 0,
  version: async () => ({ version: '2.1.287' }), env: async () => ({}), setOwned: async () => {},
  disowned: async () => [], noteCrash: async () => 0, disown: async () => {},
  http: async () => ({ ok: false, status: 500, text: '' }), sleep: async () => {},
}

const configs: Record<string, Json> = Object.fromEntries(OP_VARIANTS.map(v =>
  [v.name, deepMerge(JSON.parse(JSON.stringify(CONFIG_DEFAULTS)) as Json, v.patch as Json)]))

const ctxFor = (c: (typeof OP_CASES)[number]): OpCtx => ({
  io, event: 'UserPromptSubmit', payload: { prompt: c.prompt }, config: configs[c.variant] ?? {},
  root: '/r', sessionId: 's', now: 0, pilotExecutor: false,
  state: { turn: { signals: { check_shown: c.check } } },
})

describe('op parity with the Python ops (judge off, no graph)', () => {
  test('corpus present', () => { expect(OP_CASES.length).toBeGreaterThan(3000) })
  test('prompt_gate: context and strict block', async () => {
    const misses: string[] = []
    for (const c of OP_CASES) {
      const got = await promptGate.run(ctxFor(c))
      if (JSON.stringify(got) !== JSON.stringify(c.gate)) misses.push(`${c.variant}/${String(c.check)}: ${c.prompt}`)
    }
    expect(misses.slice(0, 5)).toEqual([])
  })
  test('prompt_brief: NAV-BRIEF text', async () => {
    const misses: string[] = []
    for (const c of OP_CASES.filter(x => x.check === null)) {
      const got = await promptBrief.run(ctxFor(c))
      if (JSON.stringify(got) !== JSON.stringify(c.brief)) misses.push(`${c.variant}: ${c.prompt}`)
    }
    expect(misses.slice(0, 5)).toEqual([])
  })
})
