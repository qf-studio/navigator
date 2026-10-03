import { describe, expect, test } from 'claude-code/testing'

import { buildRequest, call, parseResponse, redactSecrets, settings, thresholdsOf } from '../lib/judge'
import { detectWorkflow, scoreAmbiguity } from '../lib/scoring'
import type { Io } from '../lib/types'
import { JUDGE_CASES, REDACT_CASES } from './fixtures/judge.gen'

const S = settings({})
const T = thresholdsOf(S)

describe('judge parity with nav_hook_lib/judge.py (60 recorded responses)', () => {
  test('corpus present', () => { expect(JUDGE_CASES.length).toBe(60) })
  test('redact_secrets', () => {
    for (const c of REDACT_CASES) expect(redactSecrets(c.input)).toBe(c.output)
  })
  test('build_request', () => {
    for (const c of JUDGE_CASES) {
      expect(JSON.stringify(buildRequest(c.prompt, S))).toBe(JSON.stringify(c.request))
    }
  })
  test('parsed verdicts', () => {
    for (const c of JUDGE_CASES) {
      const j = parseResponse(c.doc as never, T, c.latency_ms)
      expect({
        task: j.taskVerdict(), loop: j.loopVerdict(), complexity: j.complexityIfConfident(),
        level: j.complexityLevel(), ambiguity: j.ambiguityIfConfident(),
        dimensions: Object.fromEntries(['scope', 'limits', 'approach', 'verification']
          .map(d => [d, j.dimensionVerdict(d)])),
      }).toEqual(c.verdicts)
    }
  })
  test('judged detect_workflow and score_ambiguity', () => {
    for (const c of JUDGE_CASES) {
      const j = parseResponse(c.doc as never, T, c.latency_ms)
      expect(JSON.stringify(detectWorkflow(c.prompt, j))).toBe(JSON.stringify(c.workflow))
      expect(JSON.stringify(scoreAmbiguity(c.prompt, j))).toBe(JSON.stringify(c.ambiguity))
    }
  })
})

describe('judge client', () => {
  const io = (over: Partial<Io>): Io => ({
    pluginRoot: '/p', read: async () => { throw new Error('none') }, write: async () => {},
    exists: async () => false, list: async () => [], run: async () => ({ exitCode: 1, stdout: '' }),
    cwd: async () => '/r', sessionId: async () => 's', nowMs: async () => 0, version: async () => ({ version: '2.1.287' }),
    env: async () => ({ HOME: '/home/me' }), setOwned: async () => {}, disowned: async () => [],
    noteCrash: async () => 0, disown: async () => {},
    http: async () => ({ ok: true, status: 200, text: JSON.stringify((JUDGE_CASES[0] as { doc: unknown }).doc) }),
    sleep: () => new Promise(() => {}),
    ...over,
  })
  test('no key → null, no request', async () => {
    let called = false
    const r = await call(io({ http: async () => { called = true; return { ok: true, status: 200, text: '{}' } } }), 'fix it', S)
    expect(r).toBeNull()
    expect(called).toBe(false)
  })
  test('key from file, Bearer header, parsed judgment', async () => {
    let auth = ''
    const r = await call(io({
      read: async p => (p === '/home/me/.config/typesafe/api_key' ? 'k-123\n' : ''),
      http: async (_u, init) => {
        auth = init.headers.Authorization ?? ''
        return { ok: true, status: 200, text: JSON.stringify((JUDGE_CASES[0] as { doc: unknown }).doc) }
      },
    }), 'fix it', S)
    expect(auth).toBe('Bearer k-123')
    expect(r?.model).toBe('jev-1.13.0')
  })
  test('timeout → null', async () => {
    const r = await call(io({
      env: async () => ({ TYPESAFE_API_KEY: 'k' }),
      http: () => new Promise(() => {}),
      sleep: async () => {},
    }), 'fix it', S)
    expect(r).toBeNull()
  })
  test('a refused fetch falls back to curl: key and body via env and stdin, never argv', async () => {
    const env = async () => ({ TYPESAFE_API_KEY: 'k-9' })
    const doc = JSON.stringify((JUDGE_CASES[0] as { doc: unknown }).doc)
    const runs: { argv: readonly string[]; env: Record<string, string>; stdin: string; timeoutMs: number }[] = []
    const runWith: Io['runWith'] = async (argv, init) => {
      runs.push({ argv, env: init.env, stdin: init.stdin, timeoutMs: init.timeoutMs })
      return { exitCode: 0, stdout: doc }
    }
    const refused = async () => { throw new Error('nonessential network traffic is disabled for this session') }
    const r = await call(io({ env, http: refused, runWith }), 'fix it', S)
    expect(r?.model).toBe('jev-1.13.0')
    expect(runs).toHaveLength(1)
    expect(runs[0]?.argv[0]).toBe('sh')
    expect(runs[0]?.argv.join(' ')).not.toContain('k-9')
    expect(runs[0]?.env).toEqual({ NAV_JUDGE_KEY: 'k-9', NAV_JUDGE_URL: 'https://api.typesafe.ai/v1/systemone', NAV_JUDGE_TIMEOUT: '2' })
    expect(JSON.parse(runs[0]?.stdin ?? '{}').state).toBe('fix it')
    expect(runs[0]?.timeoutMs).toBe(2500)
    // curl failing too → null; an ok fetch never reaches curl
    expect(await call(io({ env, http: refused, runWith: async () => ({ exitCode: 7, stdout: '' }) }), 'fix it', S)).toBeNull()
    let curled = false
    await call(io({ env, runWith: async () => { curled = true; return { exitCode: 0, stdout: doc } } }), 'fix it', S)
    expect(curled).toBe(false)
  })
  test('HTTP error or malformed body → null', async () => {
    const env = async () => ({ TYPESAFE_API_KEY: 'k' })
    expect(await call(io({ env, http: async () => ({ ok: false, status: 500, text: '' }) }), 'x', S)).toBeNull()
    expect(await call(io({ env, http: async () => ({ ok: true, status: 200, text: '{"answers":{}}' }) }), 'x', S)).toBeNull()
  })
})
