# Navigator v8.3.4 Release Notes

**Release Date**: 2026-10-07
**Type**: Patch — update notice curl fallback under nonessential-traffic-off (TASK-98)

## Added

- **`auto_update.curl_fallback`** (default `false`). A session with
  `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` makes the engine refuse every plugin
  `$.http.fetch`, so the session-start release check never answered on such machines and the
  update notice never fired. With the key set to `true` a refused fetch repeats the same GET
  through `curl` (no shell, same `Accept` and `User-Agent` headers, 3 s cap); the notice then
  fires as on any other machine. The key ships off because the fallback is outbound traffic
  the engine was told to refuse; the natural place to turn it on is
  `.agent/.nav-config.local.json`. A non-2xx answer (rate limit, outage) never falls back,
  so a 403 is not repeated through curl, and a failed curl records nothing, so the next
  start retries. Without the opt-in the behaviour is unchanged byte for byte.

## Changed

- The release check race timeout grows from 4.0 to 4.5 s to cover refusal + curl.
- `nav-init` config template and the `nav-features` auto_update card show the new key.

Tests: kit +5 (`update.test.ts`: seeds off, argv shape, refused fetch + opt-in → one curl +
notice, refused fetch without opt-in → no curl, curl fails → retry); 164 kit tests.
Task doc: `.agent/tasks/TASK-98-update-curl-fallback.md` (TASK-81 follow-up closed).
