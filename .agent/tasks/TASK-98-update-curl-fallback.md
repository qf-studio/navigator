# TASK-98: Update notice curl fallback under nonessential-traffic-off

**Status**: ✅ Implemented — 2026-10-07 (unreleased)

## Origin

TASK-81 follow-up. The session-start release check (`checkForUpdate` in
`hooks/mod/register.tsx`) uses `$.http.fetch`. A session with
`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` makes the engine refuse every plugin fetch, so
on such machines the update notice never fired. The judge (TASK-84) and the trip panel
already route around the refusal with curl; the release check did not.

## Decision

The fallback is outbound traffic the engine was told to refuse, and new outbound features
seed off. The curl path therefore runs only with `auto_update.curl_fallback: true`
(DEFAULTS < shared < local; the natural place is `.agent/.nav-config.local.json`).
Without the opt-in the behaviour is unchanged: refused fetch, no notice, nothing recorded,
retry on the next start.

## Change

- `hooks/mod/lib/update.ts`: `updateSettings` gains `curlFallback`; `curlArgv(url)` builds
  the same GET as the engine fetch (`-sf --max-time 3`, Accept + User-Agent headers, no
  shell, URL last); `releasesViaCurl(io, cwd)` returns the body or null.
- `hooks/mod/register.tsx`: the fetch promise falls back to curl only on **rejection**
  (the refusal), never on a non-2xx answer (a 403 rate limit would repeat through curl for
  nothing). The race timeout grows from 4000 to 4500 ms to cover refusal + curl.
- `hooks/nav_hook_lib/config.py` DEFAULTS: `auto_update.curl_fallback: False`;
  `config-defaults.gen.ts` regenerated.
- Tests (`hooks/mod/tests/update.test.ts`): seeds off and needs an explicit `true`; argv
  shape; refused fetch + opt-in → one curl, notice, check recorded; refused fetch without
  opt-in → no curl; curl fails too → nothing recorded, retry.

## Verify

- `claude plugin test .` 164/164; `make test` green; `make mod-typecheck` clean.
- Live: the curl argv against the releases API returns `v8.3.3` first on 2026-10-07.
- On this machine the opt-in lives in `.agent/.nav-config.local.json` (gitignored).

## Docs touched

CLAUDE.md (Auto-Update paragraph + config snippet), `skills/nav-init/SKILL.md` template,
`skills/nav-features/SKILL.md`, `.agent/system/plugin-patterns.md`, TASK-81 follow-up list,
DEVELOPMENT-README index. Docs site auto-update page: sync at release.
