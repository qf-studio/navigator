import { describe, expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

import { RELEASES_URL, curlArgv, dueForCheck, latestStable, updateNotice, updateSettings } from '../lib/update'

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
    expect(updateSettings({ auto_update: true })).toEqual({ enabled: true, intervalHours: 1, curlFallback: false })
    expect(updateSettings({ auto_update: false }).enabled).toBe(false)
    expect(updateSettings({ auto_update: { enabled: true, check_interval_hours: 6 } }).intervalHours).toBe(6)
  })
  test('curl fallback seeds off and needs an explicit true', () => {
    expect(updateSettings({}).curlFallback).toBe(false)
    expect(updateSettings({ auto_update: { curl_fallback: 'yes' } }).curlFallback).toBe(false)
    expect(updateSettings({ auto_update: { curl_fallback: true } }).curlFallback).toBe(true)
  })
  test('curl argv is the same GET: no shell, the releases URL last', () => {
    const argv = curlArgv(RELEASES_URL)
    expect(argv[0]).toBe('curl')
    expect(argv[argv.length - 1]).toBe(RELEASES_URL)
    expect(argv.join(' ')).not.toContain('sh -c')
  })
  test('interval gate', () => {
    expect(dueForCheck(undefined, 0, 1)).toBe(true)
    expect(dueForCheck(0, 30 * 60 * 1000, 1)).toBe(false)
    expect(dueForCheck(0, 60 * 60 * 1000, 1)).toBe(true)
  })
})

describe('session.start update check', () => {
  type World = {
    pilot?: string; latest?: string; fetches: string[]; toasts: string[]
    config?: Record<string, unknown>; manifest?: false; offline?: true; runs?: (readonly string[])[]
    curl?: string
  }
  const world = (on: On, opts: World) => {
    mock.env(on, { HOME: '/h', ...(opts.pilot ? { PILOT_EXECUTOR: opts.pilot } : {}) })
    mock.store(on)
    mock.clock(on, { now: 10_000_000 })
    on('session.cwd', () => ({ value: '/repo' }))
    on('session.version', () => ({ value: { version: '2.1.287', base: '2.1.287', builtAt: '' } }))
    on('fs.exists', (_$, e) => ({ value: e.path === '/repo/.agent' }))
    on('fs.read', (_$, e) => {
      if (e.path.endsWith('.claude-plugin/plugin.json') && opts.manifest !== false) {
        return { value: JSON.stringify({ version: '8.0.0' }) }
      }
      if (e.path === '/repo/.agent/.nav-config.json' && opts.config) {
        return { value: JSON.stringify(opts.config) }
      }
      return { deny: 'missing' }
    })
    on('http.fetch', (_$, e) => {
      opts.fetches.push(e.url)
      if (opts.offline) return { deny: 'offline' }
      return { value: { status: 200, ok: true, headers: {}, text: releases({ tag_name: `v${opts.latest ?? '8.0.0'}` }) } }
    })
    on('ui.toast', (_$, e) => { opts.toasts.push(e.text); return { value: undefined } })
    on('env.set', () => ({ value: undefined }))
    on('command.register', (_$, e) => ({ value: { command: e.name } }))
    on('process.run', (_$, e) => {
      opts.runs?.push(e.argv)
      const stdout = e.argv[0] === 'curl' && opts.curl ? releases({ tag_name: `v${opts.curl}` }) : ''
      const exitCode = stdout === '' ? 1 : 0
      return { value: { exitCode, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    })
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
  test('fetch failure → no notice, nothing recorded, so the next start retries', async ($, on) => {
    const fetches: string[] = []
    const toasts: string[] = []
    world(on, { offline: true, fetches, toasts })
    await start($)
    await start($)
    // two fetches: a failed check writes no update_checked_at, so nothing throttles the retry
    expect(fetches).toHaveLength(2)
    expect(toasts.filter(t => t.includes('available'))).toHaveLength(0)
  })
  test('refused fetch + curl_fallback → the same GET via curl, one notice, check recorded', async ($, on) => {
    const fetches: string[] = []
    const toasts: string[] = []
    const runs: (readonly string[])[] = []
    world(on, { offline: true, curl: '8.0.1', config: { auto_update: { curl_fallback: true } }, fetches, toasts, runs })
    await start($)
    await start($)
    const curls = runs.filter(argv => argv[0] === 'curl')
    expect(curls).toHaveLength(1)
    expect(curls[0]![curls[0]!.length - 1]).toBe(RELEASES_URL)
    expect(fetches).toHaveLength(1)
    expect(toasts.filter(t => t.includes('8.0.1 available'))).toHaveLength(2)
  })
  test('refused fetch without the opt-in → no curl, no notice', async ($, on) => {
    const fetches: string[] = []
    const toasts: string[] = []
    const runs: (readonly string[])[] = []
    world(on, { offline: true, curl: '8.0.1', fetches, toasts, runs })
    await start($)
    expect(runs.filter(argv => argv[0] === 'curl')).toHaveLength(0)
    expect(toasts.filter(t => t.includes('available'))).toHaveLength(0)
  })
  test('curl fails too → nothing recorded, the next start retries', async ($, on) => {
    const fetches: string[] = []
    const toasts: string[] = []
    const runs: (readonly string[])[] = []
    world(on, { offline: true, config: { auto_update: { curl_fallback: true } }, fetches, toasts, runs })
    await start($)
    await start($)
    expect(runs.filter(argv => argv[0] === 'curl')).toHaveLength(2)
    expect(toasts.filter(t => t.includes('available'))).toHaveLength(0)
  })
  test('manifest unreadable → no notice even when a newer release exists', async ($, on) => {
    const fetches: string[] = []
    const toasts: string[] = []
    world(on, { manifest: false, latest: '9.0.0', fetches, toasts })
    await start($)
    expect(toasts.filter(t => t.includes('available'))).toHaveLength(0)
  })
  test('auto_update.enabled false → no fetch and no notice', async ($, on) => {
    const fetches: string[] = []
    const toasts: string[] = []
    world(on, { config: { auto_update: { enabled: false } }, latest: '9.0.0', fetches, toasts })
    await start($)
    expect(fetches).toHaveLength(0)
    expect(toasts.filter(t => t.includes('available'))).toHaveLength(0)
  })
  test('session start never runs the Claude CLI (no `claude plugin list` from a hook)', async ($, on) => {
    const fetches: string[] = []
    const toasts: string[] = []
    const runs: (readonly string[])[] = []
    world(on, { latest: '8.0.1', fetches, toasts, runs })
    await start($)
    expect(runs.filter(argv => argv[0] === 'claude')).toHaveLength(0)
  })
})
