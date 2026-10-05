import { describe, expect, test } from 'claude-code/testing'

import { deepMerge } from '../lib/config'
import { CONFIG_DEFAULTS } from '../lib/gen/config-defaults.gen'
import { sha256Hex } from '../lib/stop-sha256'
import type { Io, Json, Op, OpCtx } from '../lib/types'
import { agentReadonly, stopCompletion, turnMutating } from '../ops/stop_completion'
import { bashReadonly, maskQuotes } from '../lib/stop-bash'
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

describe('TASK-85: read-only evidence', () => {
  test('curl reads unless it names an output; lsof and pgrep are inspection', () => {
    for (const cmd of [
      "lsof -nP -iTCP:9464 -sTCP:LISTEN 2>/dev/null | tail -n +2",
      "curl -sfg --noproxy '*' --max-time 1 http://localhost:9092/api/v1/query",
      "pgrep -f 'claude --plugin-dir' | head -1",
      "sed -n '1,40p' hooks/mod/register.tsx | head -20",
    ]) expect(bashReadonly(cmd)).toBe(true)
    expect(bashReadonly("sed -i '' 's/a/b/' notes.md")).toBe(false)
    expect(bashReadonly("sed --in-place=.bak 's/a/b/' notes.md")).toBe(false)
    for (const cmd of ['curl -sSo /tmp/f https://x', 'curl -O https://x/f', 'curl --output out.json https://x', 'curl -sS --remote-name https://x/f']) {
      expect(bashReadonly(cmd)).toBe(false)
    }
  })
  test('TASK-90: cd and absolute-path heads read; unknown basenames and relative paths write', () => {
    for (const cmd of [
      '/bin/ls -t .agent/.context-markers/ | head -3',
      'cd .agent/tasks; for f in TASK-6*.md; do grep -m1 Status "$f"; done',
      'cd /tmp && /usr/bin/git status --short',
      'cd', 'cd -',
    ]) expect(bashReadonly(cmd)).toBe(true)
    for (const cmd of ['/usr/bin/rm -rf build', './ls', '~/bin/pilot-board', 'cd /tmp && make build']) {
      expect(bashReadonly(cmd)).toBe(false)
    }
  })
  test('TASK-94: quoted | > ; are arguments; quoting never hides a write', () => {
    expect(maskQuotes('grep "a|b" f > "o"')).toBe('grep "xxx" f > "x"')
    expect(maskQuotes("echo 'it''s' \\| x")).toBe("echo 'xx''x' \\x x")
    expect(maskQuotes('echo "a \\" | b')).toBe('echo "xxxxxxxx')
    for (const cmd of [
      'grep -n "a\\|b" f | head -3', "grep '>' f", "gh pr view 1 --jq '.a | .b'",
      'printf "%s | %s\\n" a b', "echo $'a|b' | cat", 'echo "unterminated | x',
      'echo "a \\" | b"', "grep -rn 'x; rm' . | wc -l",
    ]) expect(bashReadonly(cmd)).toBe(true)
    for (const cmd of [
      'echo "x" > out.txt', 'echo "a" > "$F"', 'sh -c "ls"', 'bash -c "rm x"', "eval 'ls'",
      "xargs rm < 'list'",
    ]) expect(bashReadonly(cmd)).toBe(false)
  })
  test("Claude Code's isReadOnly on every Bash call makes a Bash-only turn non-mutating", () => {
    const evidence = { bash: [['python3 probe.py', false]] as [string, boolean][], file_paths: [] as string[] }
    const tools = new Set(['Bash'])
    expect(turnMutating(tools, evidence as never, undefined, 'D')).toBe(true)
    expect(turnMutating(tools, evidence as never, undefined, 'D', true)).toBe(false)
    // a file tool beside Bash is mutating regardless
    expect(turnMutating(new Set(['Bash', 'Edit']), evidence as never, undefined, 'D', true)).toBe(true)
  })
  test('a read-only subagent is not a task action; unknown types still are (TASK-92)', () => {
    const ro = (agents: (string | null)[], extra: string[] = []) => turnMutating(
      new Set(['Agent', ...extra]),
      { bash: [['git status', false]], file_paths: [], agents } as never, undefined, 'D')
    expect(agentReadonly('navigator:navigator-research')).toBe(true)
    expect(agentReadonly('Explore')).toBe(true)
    expect(agentReadonly('general-purpose')).toBe(false)
    expect(agentReadonly(null)).toBe(false)
    expect(ro(['navigator:navigator-research'], ['Bash'])).toBe(false)
    expect(ro(['Explore', 'task-planner'])).toBe(false)
    expect(ro(['general-purpose'])).toBe(true)
    expect(ro([null])).toBe(true)
    expect(ro(['Explore', 'general-purpose'])).toBe(true)
    expect(ro(['Explore'], ['Edit'])).toBe(true)
    expect(ro(['Explore'], ['Bash'])).toBe(false) // falls through to the Bash evidence
  })
})
