import { describe, expect, test } from 'claude-code/testing'

import { loadConfig } from '../lib/config'
import { surfaceHealth } from '../lib/life-health'
import { JSONDecodeError, PyFloat, PyInt, type PyValue, dumps, floatRepr, loads, splitlines } from '../lib/life-py'
import type { Io, Op } from '../lib/types'
import { compactMarkerPre } from '../ops/compact_marker'
import { configGuard } from '../ops/config_guard'
import { sessionStart } from '../ops/session_start'
import { setup } from '../ops/setup'
import { subagentContext } from '../ops/subagent_context'
import { LIFE_CASES as COMPACT } from './fixtures/lifeops-compact_marker.gen'
import { LIFE_CASES as GUARD } from './fixtures/lifeops-config_guard.gen'
import { GOLDEN_SESSION_CONTEXT, LIFE_CASES as SESSION } from './fixtures/lifeops-session_start.gen'
import { LIFE_CASES as SETUP } from './fixtures/lifeops-setup.gen'
import { LIFE_CASES as SUBAGENT } from './fixtures/lifeops-subagent_context.gen'

type Case = (typeof SESSION)[number]
const FIXED_NOW = 1790000000
const PROJECT = '/T/p'
const PLUGIN = '/T/plugin'
const SCRIPTS: Record<string, string> = {
  'graph_manager.py': 'skills/nav-graph/functions/graph_manager.py',
  'memory_recall.py': 'skills/nav-graph/functions/memory_recall.py',
  'auto_updater.py': 'skills/nav-start/functions/auto_updater.py',
}

/** An in-memory project replaying one recorded case. */
const world = (c: Case) => {
  const files = new Map<string, string>()
  for (const [rel, text] of Object.entries(c.files)) files.set(`${PROJECT}/${rel}`, text)
  for (const script of Object.keys(c.stubs)) files.set(`${PLUGIN}/${SCRIPTS[script]}`, '# stub')
  const initial = new Map(files)
  const mtimes = new Map(Object.entries(c.mtimes).map(([rel, ms]) => [`${PROJECT}/${rel}`, ms]))
  const isDir = (path: string): boolean =>
    path === `${PROJECT}/.agent` || [...files.keys()].some(f => f.startsWith(`${path}/`))
  const stat = async (path: string) =>
    files.has(path) ? { kind: 'file' as const, mtimeMs: mtimes.get(path) ?? 0 }
      : isDir(path) ? { kind: 'dir' as const, mtimeMs: 0 } : null
  const io: Io = {
    pluginRoot: PLUGIN,
    read: async path => {
      const text = files.get(path)
      if (text === undefined) throw new Error(`missing ${path}`)
      return text
    },
    write: async (path, text) => { files.set(path, text) },
    exists: async path => (await stat(path)) !== null,
    list: async dir => {
      const names = new Map<string, 'file' | 'dir'>()
      for (const f of files.keys()) {
        if (!f.startsWith(`${dir}/`)) continue
        const rest = f.slice(dir.length + 1)
        const [head = ''] = rest.split('/')
        names.set(head, rest.includes('/') ? 'dir' : 'file')
      }
      return [...names].map(([name, kind]) => ({
        name, kind, mtimeMs: mtimes.get(`${dir}/${name}`) ?? 0,
      }))
    },
    run: async argv => {
      if (argv[0] === 'git') {
        const spec = (c.git as Record<string, { out: string; code?: number }>)[argv.slice(1).join(' ')]
        return spec === undefined ? { exitCode: 1, stdout: '' } : { exitCode: spec.code ?? 0, stdout: spec.out }
      }
      const script = (argv[1] ?? '').split('/').pop() ?? ''
      const out = (c.stubs as Record<string, string>)[script]
      return out === undefined ? { exitCode: 1, stdout: '' } : { exitCode: 0, stdout: out }
    },
    cwd: async () => PROJECT, sessionId: async () => 's', nowMs: async () => FIXED_NOW * 1000,
    version: async () => ({ version: '2.1.287' }),
    env: async () => c.env as Record<string, string>,
    setOwned: async () => {}, disowned: async () => [], noteCrash: async () => 0, disown: async () => {},
    http: async () => ({ ok: false, status: 500, text: '' }), sleep: async () => {},
    stat, localOffsetMinutes: () => 0,
  }
  const written = (): Record<string, string> => Object.fromEntries([...files]
    .filter(([path, text]) => initial.get(path) !== text && path.startsWith(`${PROJECT}/`))
    .map(([path, text]) => [path.slice(PROJECT.length + 1), text] as const)
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)))
  return { io, written }
}

const replay = async (op: Op, cases: readonly Case[]) => {
  const misses: string[] = []
  for (const c of cases) {
    const { io, written } = world(c)
    const config = await loadConfig(io, PROJECT)
    let result: unknown
    try {
      result = await op.run({
        io, event: c.event, payload: c.payload as Record<string, unknown>, config, root: PROJECT,
        sessionId: 's', state: {}, pilotExecutor: false, now: FIXED_NOW,
      })
    } catch (e) {
      result = `threw ${String(e)}`
    }
    const sameResult = JSON.stringify(result ?? null) === JSON.stringify(c.result)
    const sorted = (m: Record<string, string>) => JSON.stringify(Object.entries(m).sort(([a], [b]) => (a < b ? -1 : 1)))
    const sameFiles = sorted(written()) === sorted(c.written)
    if (!sameResult || !sameFiles) misses.push(`${c.name}${sameResult ? '' : ' (result)'}${sameFiles ? '' : ' (files)'}`)
  }
  return misses
}

describe('lifecycle op parity with the Python ops', () => {
  test('corpora present', () => {
    expect(SESSION.length).toBeGreaterThan(15)
    expect(COMPACT.length).toBeGreaterThan(10)
    expect(GUARD.length).toBeGreaterThan(25)
  })
  test('session_start', async () => { expect(await replay(sessionStart, SESSION)).toEqual([]) })
  test('session_start reproduces the recorded v6 golden context', async () => {
    const c = SESSION.find(x => x.name === 'golden-fixture') as Case
    const { io } = world(c)
    const r = await sessionStart.run({
      io, event: 'SessionStart', payload: c.payload as Record<string, unknown>,
      config: await loadConfig(io, PROJECT), root: PROJECT, sessionId: 's', state: {},
      pilotExecutor: false, now: FIXED_NOW,
    })
    expect(r?.additional_context).toBe(GOLDEN_SESSION_CONTEXT)
  })
  test('compact_marker', async () => { expect(await replay(compactMarkerPre, COMPACT)).toEqual([]) })
  test('subagent_context', async () => { expect(await replay(subagentContext, SUBAGENT)).toEqual([]) })
  test('config_guard', async () => { expect(await replay(configGuard, GUARD)).toEqual([]) })
  test('setup', async () => { expect(await replay(setup, SETUP)).toEqual([]) })
})

describe('python compatibility helpers', () => {
  test('float repr matches CPython', () => {
    const cases: [number, string][] = [[1, '1.0'], [0.5, '0.5'], [1e-7, '1e-07'], [1e16, '1e+16'],
      [1e15, '1000000000000000.0'], [0.0001, '0.0001'], [0.00001, '1e-05'], [-0, '-0.0'], [123.456, '123.456'],
      [1.5e300, '1.5e+300'], [2.5e-10, '2.5e-10']]
    for (const [x, want] of cases) expect(floatRepr(x)).toBe(want)
  })
  test('json.dumps escapes non-ASCII and keeps float repr and key order', () => {
    const v = loads('{"b": 1.0, "a": "naïve 😀", "2": [1e-07, 10000000000000000.0, 7]}')
    expect(dumps(v)).toBe('{"b": 1.0, "a": "na\\u00efve \\ud83d\\ude00", "2": [1e-07, 1e+16, 7]}')
    expect(dumps(new Map<string, PyValue>([['x', new Map()], ['y', []]]), 2)).toBe('{\n  "x": {},\n  "y": []\n}')
    expect(loads('7')).toEqual(new PyInt(7n))
    expect(loads('7.0')).toEqual(new PyFloat(7))
  })
  test('json error positions match the C scanner', () => {
    const at = (s: string): [string, number] => {
      try {
        loads(s)
        return ['ok', -1]
      } catch (e) {
        return e instanceof JSONDecodeError ? [e.msg, e.pos] : ['other', -1]
      }
    }
    expect(at('[1,]')).toEqual(['Illegal trailing comma before end of array', 2])
    expect(at('{"a":1,}')).toEqual(['Illegal trailing comma before end of object', 6])
    expect(at('"a\\u12"')).toEqual(['Invalid \\uXXXX escape', 3])
    expect(at('01')).toEqual(['Extra data', 1])
  })
  test('splitlines follows str.splitlines', () => {
    expect(splitlines('a\r\nb\rc\u2028d\n')).toEqual(['a', 'b', 'c', 'd'])
    expect(splitlines('')).toEqual([])
  })
  test('surfaceHealth shows a recorded error once', async () => {
    const files = new Map([['/T/p/.agent/.nav-dispatch-health.json',
      '{"last_error": {"ts": "x", "event": "Stop", "op": "stop_state", "error": "KeyError"}, "surfaced": false}']])
    const io = {
      read: async (p: string) => files.get(p) ?? '', write: async (p: string, t: string) => { files.set(p, t) },
      stat: async (p: string) => (files.has(p) ? { kind: 'file' as const, mtimeMs: 0 } : null),
    } as unknown as Io
    expect(await surfaceHealth(io, '/T/p/.agent')).toBe('nav-dispatch: last dispatch error: Stop/stop_state: KeyError')
    expect(await surfaceHealth(io, '/T/p/.agent')).toBeNull()
  })
})
