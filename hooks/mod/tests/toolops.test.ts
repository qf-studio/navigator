import { describe, expect, test } from 'claude-code/testing'

import { deepMerge } from '../lib/config'
import { CONFIG_DEFAULTS } from '../lib/gen/config-defaults.gen'
import { normalize } from '../lib/toolops-path'
import type { Io, Json, Op } from '../lib/types'
import { failureDiagnosis } from '../ops/failure_diagnosis'
import { graphSync } from '../ops/graph_sync'
import { jitMemory } from '../ops/jit_memory'
import { profileSync } from '../ops/profile_sync'
import { readGuard } from '../ops/read_guard'
import { EDIT_CASES } from './fixtures/toolops-edit.gen'
import { FAILURE_CASES } from './fixtures/toolops-failure.gen'
import { READ_GUARD_SEQUENCES } from './fixtures/toolops-readguard.gen'

const OPS: Record<string, Op> = {
  read_guard: readGuard, jit_memory: jitMemory, graph_sync: graphSync,
  profile_sync: profileSync, failure_diagnosis: failureDiagnosis,
}

const configOf = (patch: Json): Json =>
  deepMerge(JSON.parse(JSON.stringify(CONFIG_DEFAULTS)) as Json, patch)

type Case = (typeof EDIT_CASES)[number]

/** An Io replaying one recorded Python case: its files, subprocess outcomes and recall. */
const replay = (c: Case) => {
  const exists = new Set(c.exists.map(normalize))
  const outcomes = [...c.runs]
  const argv: string[][] = []
  let concepts: string[] | null = null
  const io: Io = {
    pluginRoot: '/p',
    read: async path => {
      const f = c.files[normalize(path)]
      if (f === undefined) throw new Error('missing')
      return f
    },
    write: async () => {},
    exists: async path => exists.has(normalize(path)),
    list: async () => [],
    run: async args => {
      if (String(args[1]).endsWith('memory_recall.py')) {
        const at = args.indexOf('--concepts')
        concepts = at < 0 ? [] : String(args[at + 1]).split(',')
        return c.summary ? { exitCode: 0, stdout: c.summary } : { exitCode: 1, stdout: '' }
      }
      return { exitCode: 1, stdout: '' }
    },
    runCapture: async args => {
      argv.push([...args])
      const o = outcomes.shift() ?? { rc: 0, stdout: '', stderr: '' }
      if (o.raise === 'timeout') throw Object.assign(new Error('still running'), { name: 'TimeoutError' })
      if (o.raise === 'failure') throw new Error(o.message ?? '')
      return { exitCode: o.rc ?? 0, stdout: o.stdout ?? '', stderr: o.stderr ?? '' }
    },
    cwd: async () => '/r', sessionId: async () => 's', nowMs: async () => 0,
    version: async () => ({ version: '2.1.287' }), env: async () => ({}), setOwned: async () => {},
    disowned: async () => [], noteCrash: async () => 0, disown: async () => {},
    http: async () => ({ ok: false, status: 500, text: '' }), sleep: async () => {},
  }
  return { io, argv, concepts: () => concepts }
}

const runCase = async (c: Case) => {
  const r = replay(c)
  const state = JSON.parse(JSON.stringify(c.state)) as Json
  const op = OPS[c.op]
  if (!op) throw new Error(`unknown op ${c.op}`)
  const result = await op.run({
    io: r.io, event: c.event, payload: c.payload, config: configOf(c.config), root: '/r',
    sessionId: 's', now: c.now, pilotExecutor: false, state,
  })
  return { result, state, argv: r.argv, concepts: r.concepts() }
}

const mismatches = async (cases: readonly Case[]): Promise<string[]> => {
  const misses: string[] = []
  for (const c of cases) {
    const got = await runCase(c)
    const want = c.expected
    const same = JSON.stringify(got.result) === JSON.stringify(want.result)
      && JSON.stringify(got.state) === JSON.stringify(want.state)
      && JSON.stringify(got.argv) === JSON.stringify(want.argv)
      && JSON.stringify(got.concepts) === JSON.stringify(want.concepts)
    if (!same) misses.push(`${c.op}/${c.event}: ${JSON.stringify(c.payload)} → ${JSON.stringify(got)}`)
  }
  return misses
}

describe('tool-event op parity with the Python ops (step 5b)', () => {
  test('corpora present', () => {
    expect(READ_GUARD_SEQUENCES.length).toBe(20)
    expect(EDIT_CASES.length).toBeGreaterThan(120)
    expect(FAILURE_CASES.length).toBe(32)
  })

  test('read_guard: counter, dedupe, staleness, thresholds over 20 read sequences', async () => {
    const misses: string[] = []
    for (const seq of READ_GUARD_SEQUENCES) {
      const state = JSON.parse(JSON.stringify(seq.prior)) as Json
      const config = configOf(seq.config)
      for (const [i, step] of seq.steps.entries()) {
        const result = await readGuard.run({
          io: replay(EDIT_CASES[0] as Case).io, event: 'PreToolUse', payload: step.payload,
          config, root: '/r', sessionId: 's', now: step.now, pilotExecutor: false, state,
        })
        if (JSON.stringify(result) !== JSON.stringify(step.result)
          || JSON.stringify(state) !== JSON.stringify(step.state)) {
          misses.push(`${seq.variant} step ${i}: ${JSON.stringify(result)} / ${JSON.stringify(state)}`)
          break
        }
      }
    }
    expect(misses.slice(0, 3)).toEqual([])
  })

  test('jit_memory, graph_sync, profile_sync: results, state and subprocess argv', async () => {
    expect((await mismatches(EDIT_CASES)).slice(0, 3)).toEqual([])
  })

  test('failure_diagnosis: results and recall concepts', async () => {
    expect((await mismatches(FAILURE_CASES)).slice(0, 3)).toEqual([])
  })
})

describe('tool-event op specs mirror registry.py', () => {
  test('names, phases, config keys', () => {
    expect(Object.values(OPS).map(o => [o.spec.name, o.spec.phase, o.spec.configKey])).toEqual([
      ['read_guard', 'gates', 'read_guard_hook'],
      ['jit_memory', 'injectors', 'jit_memory'],
      ['graph_sync', 'recorders', 'task_graph_sync_hook'],
      ['profile_sync', 'recorders', 'profile_sync_hook'],
      ['failure_diagnosis', 'injectors', 'failure_diagnosis'],
    ])
  })
  test('matchers: Read for read_guard, the mutating tools for jit/profile', () => {
    expect(readGuard.spec.matcher?.({ tool_name: 'Read' })).toBe(true)
    expect(readGuard.spec.matcher?.({ tool_name: 'Grep' })).toBe(false)
    for (const tool of ['Edit', 'Write', 'MultiEdit', 'NotebookEdit']) {
      expect(jitMemory.spec.matcher?.({ tool_name: tool })).toBe(true)
      expect(profileSync.spec.matcher?.({ tool_name: tool })).toBe(true)
    }
    expect(jitMemory.spec.matcher?.({ tool_name: 'Bash' })).toBe(false)
  })
  test('without runCapture the syncs still run and report an empty stderr', async () => {
    const c = EDIT_CASES.find(x => x.op === 'graph_sync' && x.event === 'PostToolUse'
      && JSON.stringify(x.expected.result).includes('upserted TASK-12')) as Case
    const r = replay(c)
    delete r.io.runCapture
    const result = await graphSync.run({
      io: { ...r.io, run: async () => ({ exitCode: 0, stdout: 'ok' }) }, event: c.event,
      payload: c.payload, config: configOf({}), root: '/r', sessionId: 's', now: 0,
      pilotExecutor: false, state: {},
    })
    expect(JSON.stringify(result)).toContain('upserted TASK-12-x.md')
  })
})
