# Navigator Plugin Deployment Guide

How Navigator is packaged and published to the Claude Code marketplace. This is a **maintainer-facing** guide; the
canonical step-by-step lives in the [`nav-release` skill](../skills/nav-release/SKILL.md) and the release SOPs under
`.agent/sops/development/`. Releases are **automated by CI** — you push a tag, the workflow publishes.

> **For users**, installation is two commands:
> ```bash
> /plugin marketplace add qf-studio/navigator
> /plugin install navigator
> ```

---

## The marketplace model

A Claude Code **marketplace is just a Git repository** — no special hosting. Navigator is its own single-plugin
marketplace at `github.com/qf-studio/navigator`:

```
github.com/qf-studio/navigator
├── .claude-plugin/
│   ├── plugin.json         # the plugin manifest
│   └── marketplace.json    # the marketplace manifest (lists this plugin)
├── skills/                 # 30 skills (the plugin's surface)
├── hooks/                  # 8 lifecycle hook scripts
├── .github/workflows/      # test.yml + release.yml (CI)
└── releases/               # per-version RELEASE-NOTES-vX.Y.Z.md
```

When a user runs `/plugin marketplace add qf-studio/navigator`, Claude Code reads `marketplace.json`; `/plugin
install navigator` then resolves the `navigator` entry and copies the plugin into the user's plugin cache.

---

## Plugin manifest (`.claude-plugin/plugin.json`)

Navigator is **skills + hooks** — there is no `commands` array (legacy `/nav:*` slash commands were removed; skills
auto-invoke on natural language). The manifest fields that matter:

```jsonc
{
  "name": "navigator",
  "version": "6.16.0",                              // bumped every release (see Versioning)
  "description": "...",
  "author": { "name": "Aleks Petrov", "email": "aleks@quantflow.studio" },
  "homepage": "https://github.com/qf-studio/navigator",
  "repository": "https://github.com/qf-studio/navigator",  // a string, not an object
  "license": "MIT",
  "keywords": ["context-management", "knowledge-graph", "theory-of-mind", "..."],
  "skills": ["./skills/nav-start", "./skills/nav-graph", "..."],   // one entry per skill dir
  "hooks": {
    "SessionStart":  [{ "hooks": [{ "type": "command", "command": "sh -c 'f=\"${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/marketplaces/navigator-marketplace}/hooks/nav_dispatch.py\"; if [ -f \"$f\" ]; then exec python3 \"$f\" SessionStart; fi'", "timeout": 10 }] }],
    "PreCompact":    [/* ... */],
    "PostCompact":   [/* ... */],
    "Stop":          [/* ... */],
    "UserPromptSubmit": [/* ... */],
    "PreToolUse":    [{ "matcher": "Read",       "hooks": [/* ... */] }],
    "PostToolUse":   [{ "matcher": "Edit|Write", "hooks": [/* ... */] }]
  }
}
```

**Hook command pattern (do not regress):** every hook uses
`${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/marketplaces/navigator-marketplace}/hooks/X.py`. The parameter-expansion
fallback runs the hook whether or not `CLAUDE_PLUGIN_ROOT` is set; a bare `if [ -n "$CLAUDE_PLUGIN_ROOT" ]` guard
silently no-ops the hook when the var is unset (the v6.14.0 silent-fail class). The release validator's
`--verify-hooks` smoke test guards this.

**Skill command pattern:** `CLAUDE_PLUGIN_ROOT` is set for hook commands only; the Bash tool
runs skill commands without it. The session_start op therefore writes the root it resolved to
`~/.config/navigator/plugin-root` on every start, and every `SKILL.md` resolves
`PLUGIN_DIR` as env var → that file → the marketplace clone (`tests/test_skill_plugin_root.py`
pins the snippet). The plugin cache is versioned (`.../navigator/<version>/`), so a flat
cache path is never a valid root.

## Marketplace manifest (`.claude-plugin/marketplace.json`)

Thin by design — it names the marketplace and points at the plugin:

```jsonc
{
  "name": "navigator-marketplace",
  "displayName": "Navigator",
  "owner": { "name": "Aleks Petrov", "email": "aleks@quantflow.studio" },
  "metadata": { /* ... */ },
  "plugins": [{ "name": "navigator", "source": "./" }]
}
```

---

## Versioning

A version bump touches **all version-carrying files together** — the release validator fails the build if any drift:

| File | What carries the version |
|------|--------------------------|
| `.claude-plugin/plugin.json` | `version` field |
| `.claude-plugin/marketplace.json` | version in `metadata` / changelog |
| `README.md` | version badge |
| `CLAUDE.md` | config sample + "Navigator Version" footer |
| `.agent/.nav-config.json` | `version` field |
| `releases/RELEASE-NOTES-v<X.Y.Z>.md` | new per-version notes file (canonical path) |

`nav-release` and the CI `release_validator.py --check-version` enforce consistency; never hand-bump a subset.

---

## Release pipeline (automated)

Two GitHub Actions workflows drive everything:

- **`test.yml`** — runs `make test` (per-directory unittest discovery) on every push and PR. The pre-merge gate.
- **`release.yml`** — triggers on `v*` tag push. Two jobs:
  1. **validate** — `make test`, then `release_validator.py` with `--check-all` (skills exist + committed + versions
     consistent), `--verify-hook-paths` (every manifest hook path resolves to a file — guards the v6.15.6 regression
     class), `--check-version <tag>`, and `--verify-tag <tag>`.
  2. **release** — locates `releases/RELEASE-NOTES-v<version>.md`, marks pre-release from the tag suffix
     (`alpha`/`beta`/`rc`), and creates (or updates in place) the GitHub release with the notes attached.

### Cutting a release

Use the **`nav-release` skill** (`"release Navigator vX.Y.Z"`), which validates first, then:

```bash
# 1. Commit the version bump
git add . && git commit -m "chore(release): prepare vX.Y.Z"

# 2. Push to main
git push origin main

# 3. Tag and push — THIS triggers release.yml, which publishes the GitHub release
git tag -a vX.Y.Z -m "Navigator vX.Y.Z: <summary>"
git push origin vX.Y.Z
```

> **Never run `gh release create` locally.** The workflow owns publication; a local create races CI and historically
> caused "release with the same tag name already exists" failures.

### Verify the release

```bash
# Watch the publish run; non-zero exit if it fails
gh run watch --exit-status "$(gh run list --workflow=release.yml --limit=1 --json databaseId --jq '.[0].databaseId')"
gh release view vX.Y.Z --json tagName,name,isDraft,assets
```

On success the marketplace auto-serves the new tag; users update with `/plugin update navigator`.

---

## Pre-release checklist

- [ ] All skills exist, committed, and listed in `plugin.json`
- [ ] Version consistent across all 6 version-carrying files
- [ ] `releases/RELEASE-NOTES-vX.Y.Z.md` written
- [ ] `release_validator.py --verify-hooks` passes (hook smoke test) when hooks/manifest changed
- [ ] Tag created **after** all commits
- [ ] `release.yml` run is green and the release is published with notes attached

---

## Related

- **Skill**: [`nav-release`](../skills/nav-release/SKILL.md) — the interactive release walkthrough
- **SOP**: `.agent/sops/development/release-workflow.md` — the canonical end-to-end release SOP
- **Manifests**: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`
- **CI**: `.github/workflows/release.yml`, `.github/workflows/test.yml`
