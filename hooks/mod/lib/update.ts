// TASK-81 point 1, mod side (TASK-84): a truthful, read-only update notice. The running
// version is the mod's own manifest (never `claude plugin list` from inside a hook); the
// latest stable comes from the GitHub releases API, at most once per check interval.
import { compareVersions } from '../owns'
import { getPath } from './config'
import { run } from './project'
import type { Io, Json } from './types'

export const RELEASES_URL = 'https://api.github.com/repos/qf-studio/navigator/releases?per_page=10'
export const UPDATE_COMMAND = 'claude plugin update navigator@navigator-marketplace'
const SEMVER = /^\d+\.\d+\.\d+$/

/** First non-draft, non-prerelease release whose tag is a plain semver. */
export const latestStable = (releasesJson: string): string | null => {
  try {
    const list: unknown = JSON.parse(releasesJson)
    if (!Array.isArray(list)) return null
    for (const r of list as Json[]) {
      if (r.draft === true || r.prerelease === true) continue
      const v = String(r.tag_name ?? '').replace(/^v/, '')
      if (SEMVER.test(v)) return v
    }
  } catch {
    // fail silent: no notice
  }
  return null
}

export type UpdateSettings = { enabled: boolean; intervalHours: number; curlFallback: boolean }

/**
 * `auto_update` may be a bool (older configs) or `{enabled, check_interval_hours, curl_fallback}`.
 * `curl_fallback` seeds off: it is outbound traffic the engine was told to refuse.
 */
export const updateSettings = (cfg: Json): UpdateSettings => {
  const raw = cfg.auto_update
  if (typeof raw === 'boolean') return { enabled: raw, intervalHours: 1, curlFallback: false }
  return {
    enabled: getPath(cfg, 'auto_update.enabled', true) !== false,
    intervalHours: Number(getPath(cfg, 'auto_update.check_interval_hours', 1)) || 1,
    curlFallback: getPath(cfg, 'auto_update.curl_fallback', false) === true,
  }
}

export const CURL_TIMEOUT_S = 3

/** The same GET as the engine fetch, as a curl argv: no shell, no secrets, URL last. */
export const curlArgv = (url: string): string[] => [
  'curl', '-sf', '--max-time', String(CURL_TIMEOUT_S),
  '-H', 'Accept: application/vnd.github+json', '-H', 'User-Agent: navigator-update/1', url,
]

/**
 * Releases JSON via curl, or null. Used only when the engine refused `$.http.fetch` (a session
 * with CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC refuses every plugin fetch) and the user opted
 * in with `auto_update.curl_fallback: true`. A missing curl or a non-2xx answer is a quiet null.
 */
export const releasesViaCurl = async (io: Io, cwd: string): Promise<string | null> => {
  const out = await run(io, curlArgv(RELEASES_URL), cwd, (CURL_TIMEOUT_S + 1) * 1000)
  return out.trim() === '' ? null : out
}

export const dueForCheck = (lastCheckedMs: unknown, nowMs: number, intervalHours: number): boolean =>
  typeof lastCheckedMs !== 'number' || nowMs - lastCheckedMs >= intervalHours * 3600 * 1000

export const updateNotice = (installed: string, latest: string | null): string | null =>
  latest !== null && compareVersions(latest, installed) > 0
    ? `Navigator ${installed} installed · ${latest} available · run: ${UPDATE_COMMAND}`
    : null
