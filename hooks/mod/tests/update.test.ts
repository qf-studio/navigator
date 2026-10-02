import { describe, expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

import { dueForCheck, latestStable, updateNotice, updateSettings } from '../lib/update'

const releases = (...items: Record<string, unknown>[]): string => JSON.stringify(items)

describe('update notice logic (TASK-81)', () => {
  test('latest stable skips drafts, prereleases and odd tags', () => {
    expect(latestStable(releases(
      { tag_name: 'v8.1.0-rc1', prerelease: true }, { tag_name: 'v8.0.1', draft: true },
      { tag_name: 'nightly' }, { tag_name: 'v8.0.0' }, { tag_name: 'v7.9.0' },
    ))).toBe('8.0.0')
    expect(latestStable('not json')).toBeNull()
    expect(latestStable('{"message":"rate limited"}')).toBeNull()
  })
  test('notice only when the latest is newer than the running version', () => {
    expect(updateNotice('8.0.0', '8.0.1')).toContain('8.0.0 installed · 8.0.1 available')
    expect(updateNotice('8.0.0', '8.0.0')).toBeNull()
    expect(updateNotice('8.0.1', '8.0.0')).toBeNull()
    expect(updateNotice('8.0.0', null)).toBeNull()
  })
  test('settings accept the boolean and the block form', () => {
    expect(updateSettings({ auto_update: true })).toEqual({ enabled: true, intervalHours: 1 })
    expect(updateSettings({ auto_update: false }).enabled).toBe(false)
    expect(updateSettings({ auto_update: { enabled: true, check_interval_hours: 6 } }).intervalHours).toBe(6)
  })
  test('interval gate', () => {
    expect(dueForCheck(undefined, 0, 1)).toBe(true)
    expect(dueForCheck(0, 30 * 60 * 1000, 1)).toBe(false)
    expect(dueForCheck(0, 60 * 60 * 1000, 1)).toBe(true)
  })
})

describe('session.start update check', () => {
  const world = (on: On,
    opts: { pilot?: string; latest?: string; fetches: string[]; toasts: string[] }) => {
    mock.env(on, { HOME: '/h', ...(opts.pilot ? { PILOT_EXECUTOR: opts.pilot } : {}) })
    mock.store(on)
    mock.clock(on, { now: 10_000_000 })
    on('session.cwd', () => ({ value: '/repo' }))
    on('session.version', () => ({ value: { version: '2.1.287', base: '2.1.287', builtAt: '' } }))
    on('fs.exists', (_$, e) => ({ value: e.path === '/repo/.agent' }))
    on('fs.read', (_$, e) => (e.path.endsWith('.claude-plugin/plugin.json')
      ? { value: JSON.stringify({ version: '8.0.0' }) } : { deny: 'missing' }))
    on('http.fetch', (_$, e) => {
      opts.fetches.push(e.url)
      return { value: { status: 200, ok: true, headers: {}, text: releases({ tag_name: `v${opts.latest ?? '8.0.0'}` }) } }
    })
    on('ui.toast', (_$, e) => { opts.toasts.push(e.text); return { value: undefined } })
    on('env.set', () => ({ value: undefined }))
    on('command.register', (_$, e) => ({ value: { command: e.name } }))
    on('process.run', () => ({ value: { exitCode: 1, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
    on('fs.list', () => ({ value: [] }))
    on('session.start', (_$, e) => ({ cwd: e.cwd }))
  }
  const start = ($: Engine) => $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })

  test('newer release → one toast with the update command; second start is throttled', async ($, on) => {
    const fetches: string[] = []
    const toasts: string[] = []
    world(on, { latest: '8.0.1', fetches, toasts })
    await start($)
    await start($)
    expect(fetches).toHaveLength(1)
    expect(toasts.filter(t => t.includes('8.0.1 available'))).toHaveLength(2)
    expect(toasts[0]).toContain('claude plugin update navigator@navigator-marketplace')
  })
  test('same version → no toast', async ($, on) => {
    const fetches: string[] = []
    const toasts: string[] = []
    world(on, { latest: '8.0.0', fetches, toasts })
    await start($)
    expect(toasts.filter(t => t.includes('available'))).toHaveLength(0)
  })
  test('under Pilot → no network at all', async ($, on) => {
    const fetches: string[] = []
    const toasts: string[] = []
    world(on, { pilot: '1', latest: '9.0.0', fetches, toasts })
    await start($)
    expect(fetches).toHaveLength(0)
    expect(toasts).toHaveLength(0)
  })
})
