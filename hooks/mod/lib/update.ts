// TASK-81 point 1, mod side (TASK-84): a truthful, read-only update notice. The running
// version is the mod's own manifest (never `claude plugin list` from inside a hook); the
// latest stable comes from the GitHub releases API, at most once per check interval.
import { compareVersions } from '../owns'
import { getPath } from './config'
import type { Json } from './types'

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

/** `auto_update` may be a bool (older configs) or `{enabled, check_interval_hours}`. */
export const updateSettings = (cfg: Json): { enabled: boolean; intervalHours: number } => {
  const raw = cfg.auto_update
  if (typeof raw === 'boolean') return { enabled: raw, intervalHours: 1 }
  return {
    enabled: getPath(cfg, 'auto_update.enabled', true) !== false,
    intervalHours: Number(getPath(cfg, 'auto_update.check_interval_hours', 1)) || 1,
  }
}

export const dueForCheck = (lastCheckedMs: unknown, nowMs: number, intervalHours: number): boolean =>
  typeof lastCheckedMs !== 'number' || nowMs - lastCheckedMs >= intervalHours * 3600 * 1000

export const updateNotice = (installed: string, latest: string | null): string | null =>
  latest !== null && compareVersions(latest, installed) > 0
    ? `Navigator ${installed} installed · ${latest} available · run: ${UPDATE_COMMAND}`
    : null
