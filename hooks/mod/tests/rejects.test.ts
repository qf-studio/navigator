import { describe, expect, test } from 'claude-code/testing'

import { KEEP_LINES, REJECTS_PATH, REWRITE_AT, appendReject, rejectLine } from '../lib/rejects'
import type { Io, Json, Op, OpCtx, OpResult } from '../lib/types'
import { runOps } from '../runner'
import { REJECT_LINES } from './fixtures/rejects.gen'

type FakeIo = Io & { files: Record<string, string> }

const fakeIo = (): FakeIo => {
  const io: FakeIo = {
    files: {},
    pluginRoot: '/plugin',
    read: async path => {
      const text = io.files[path]
      if (text === undefined) throw new Error('ENOENT')
      return text
    },
    write: async (path, text) => { io.files[path] = text },
    exists: async path => path in io.files,
    list: async () => [],
    run: async () => ({ exitCode: 1, stdout: '' }),
    cwd: async () => '/repo',
    sessionId: async () => 's1',
    nowMs: async () => 0,
    version: async () => ({ version: '2.1.287', base: '2.1.287' }),
    env: async () => ({}),
    setOwned: async () => {},
    disowned: async () => [],
    noteCrash: async () => 0,
    disown: async () => {},
    http: async () => ({ ok: false, status: 500, text: '' }),
    sleep: async () => {},
  }
  return io
}

const REJECT = { reason: 'too many reads', evidence: { path: 'tasks/x.md', count: 5 } }

const ctxOf = (io: Io, event: string, extra: Partial<OpCtx> = {}): OpCtx => ({
  io, event, payload: {}, config: {}, root: '/repo', pilotExecutor: false, now: 1700000000,
  sessionId: 's1', state: {}, ...extra,
})

// Named after an owned op so the ownership check lets it run.
const gate = (result: OpResult): Op => ({
  spec: { name: 'read_guard', phase: 'gates', configKey: null },
  run: async () => result,
})

const linesOf = (io: FakeIo): Json[] =>
  (io.files[`/repo/${REJECTS_PATH}`] ?? '').split('\n').filter(Boolean).map(l => JSON.parse(l) as Json)

describe('reject log parity with nav_hook_lib/rejects.py (TASK-88)', () => {
  test('rejectLine produces the Python bytes for every corpus entry', () => {
    for (const c of REJECT_LINES) {
      expect(rejectLine(c.ts, c.session, c.event, c.op, c.tool, c.reject as Json, c.suppressed)).toBe(c.line)
    }
  })
})

describe('runner appends one line per refusal', () => {
  test('a blocking gate with reject writes the line and strips the key from the merge', async () => {
    const io = fakeIo()
    const merged = await runOps(ctxOf(io, 'PreToolUse', { payload: { tool_name: 'Read' } }), [
      gate({ exit_code: 2, stderr: 'blocked', reject: REJECT }),
    ])
    expect(merged.deny).toBe('blocked')
    expect(linesOf(io)).toEqual([{
      ts: '2023-11-14T22:13:20+00:00', session: 's1', event: 'PreToolUse', op: 'read_guard', tool: 'Read',
      reason: 'too many reads', evidence: { path: 'tasks/x.md', count: 5 },
    }])
  })
  test('a Stop block has no tool key; a non-blocking result writes nothing', async () => {
    const io = fakeIo()
    await runOps(ctxOf(io, 'Stop'), [gate({ decision: 'block', reason: 'finish', reject: REJECT })])
    const [line] = linesOf(io)
    expect(line?.op).toBe('read_guard')
    expect('tool' in (line ?? {})).toBe(false)
    expect('suppressed' in (line ?? {})).toBe(false)
    const quiet = fakeIo()
    const merged = await runOps(ctxOf(quiet, 'Stop'), [gate({ stderr: 'warn only', reject: REJECT })])
    expect(merged.notes).toBe('warn only')
    expect(linesOf(quiet)).toEqual([])
  })
  test('reject_log.enabled false keeps the block and skips the file', async () => {
    const io = fakeIo()
    const merged = await runOps(ctxOf(io, 'Stop', { config: { reject_log: { enabled: false } } }), [
      gate({ decision: 'block', reason: 'finish', reject: REJECT }),
    ])
    expect(merged.block).toBe('finish')
    expect(linesOf(io)).toEqual([])
  })
  test('under Pilot the line is marked suppressed and no block escapes', async () => {
    const io = fakeIo()
    const merged = await runOps(ctxOf(io, 'Stop', { pilotExecutor: true }), [
      gate({ decision: 'block', reason: 'finish', reject: REJECT }),
    ])
    expect(merged.block).toBeNull()
    expect(linesOf(io)[0]?.suppressed).toBe(true)
  })
  test('appendReject keeps the newest lines once past the rewrite mark', async () => {
    const io = fakeIo()
    const path = `/repo/${REJECTS_PATH}`
    io.files[path] = Array.from({ length: REWRITE_AT }, (_, i) => `{"n":${i}}`).join('\n') + '\n'
    expect(await appendReject(io, '/repo', '{"n":"last"}')).toBe(true)
    const lines = io.files[path]?.split('\n').filter(Boolean) ?? []
    expect(lines.length).toBe(KEEP_LINES)
    expect(lines[lines.length - 1]).toBe('{"n":"last"}')
    expect(JSON.parse(lines[0] ?? '{}').n).toBe(REWRITE_AT - KEEP_LINES + 1)
  })
})
