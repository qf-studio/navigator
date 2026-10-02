import { describe, expect, test } from 'claude-code/testing'

import { deepMerge } from '../lib/config'
import { CONFIG_DEFAULTS } from '../lib/gen/config-defaults.gen'
import type { Io, Json } from '../lib/types'
import { promptTier1 } from '../ops/prompt_tier1'
import { PLUGIN_VERSION, TIER1_CASES, TIER1_GRAPH, TIER1_MARKERS, TIER1_VARIANTS } from './fixtures/tier1.gen'

const files: Record<string, string> = {
  '/r/.agent/knowledge/graph.json': JSON.stringify(TIER1_GRAPH),
  '/p/.claude-plugin/plugin.json': JSON.stringify({ version: PLUGIN_VERSION }),
}
const io: Io = {
  pluginRoot: '/p',
  read: async path => { const f = files[path]; if (f === undefined) throw new Error('missing'); return f },
  write: async () => {}, exists: async path => path in files,
  list: async path => (path === '/r/.agent/.context-markers'
    ? TIER1_MARKERS.map(name => ({ name, mtimeMs: 0, kind: 'file' as const })) : []),
  run: async () => ({ exitCode: 1, stdout: '' }), cwd: async () => '/r', sessionId: async () => 's',
  nowMs: async () => 0, version: async () => ({ version: '2.1.287' }), env: async () => ({}),
  setOwned: async () => {}, disowned: async () => [], noteCrash: async () => 0, disown: async () => {},
  http: async () => ({ ok: false, status: 500, text: '' }), sleep: async () => {},
}

const configOf = (name: string): Json => {
  const patch = (TIER1_VARIANTS as Record<string, Json>)[name] ?? {}
  return deepMerge(JSON.parse(JSON.stringify(CONFIG_DEFAULTS)) as Json, patch)
}

describe('prompt_tier1 parity with hooks/ops/prompt_tier1.py', () => {
  test('corpus present', () => { expect(TIER1_CASES.length).toBeGreaterThan(150) })
  test('answers and telemetry match', async () => {
    const misses: string[] = []
    for (const c of TIER1_CASES) {
      const state = JSON.parse(JSON.stringify(c.prior)) as Json
      const result = await promptTier1.run({
        io, event: 'UserPromptSubmit', payload: { prompt: c.prompt }, config: configOf(c.variant),
        root: '/r', sessionId: 's', now: 0, pilotExecutor: false, state,
      })
      if (JSON.stringify(result) !== JSON.stringify(c.result)
        || JSON.stringify(state) !== JSON.stringify(c.after)) misses.push(`${c.variant}: ${JSON.stringify(c.prompt)}`)
    }
    expect(misses.slice(0, 5)).toEqual([])
  })
})
