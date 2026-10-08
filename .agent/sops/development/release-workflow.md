# Release Workflow — Standard Operating Procedure

**Category**: Development
**Created**: 2026-06-26 (consolidated)
**Last Updated**: 2026-06-26

> **Canonical release SOP.** Supersedes and replaces the four overlapping docs that previously lived here:
> `version-management.md`, `complete-release-workflow.md`, `navigator-plugin-release-workflow.md`, and
> `plugin-release-workflow.md`. The interactive walkthrough is the [`nav-release` skill](../../../skills/nav-release/SKILL.md);
> the deployment-side checklist (skill existence, cache) is `../deployment/plugin-release.md`.

---

## Context

A release bumps the version across several manifests and docs, writes release notes, then tags. CI publishes the
GitHub release from the tag. The failure mode this SOP prevents is **version drift** (e.g. `marketplace.json` says
6.16.0 but `plugin.json` says 6.15.6) and incomplete/missing release notes.

**Problem**: the version lives in several files; manual edits leave one behind.
**Solution**: one source of truth + a scripted 6-location bump + a CI validation gate.
**Result**: zero drift, idempotent publish.

---

## Single Source of Truth

**SSOT**: `.claude-plugin/marketplace.json` → `metadata.version`.

```json
{
  "metadata": { "version": "6.16.0" },
  "plugins": [{ "name": "navigator", "source": "./" }]
}
```

> The marketplace `plugins[]` entries carry only `name` and `source` — there is **no** `plugins[0].version`.
> `.claude-plugin/plugin.json` `version` is the manifest version that must equal the SSOT; tooling
> (`release_validator.py`, `config_migrator.py`) reads the plugin manifest, not a marketplace plugin entry.

## The 6 bump locations

Every release bumps the same six. Five carry a matchable version string; the sixth is a new per-version notes file.

| # | File | Location | Format |
|---|------|----------|--------|
| 1 | `.claude-plugin/marketplace.json` | `metadata.version` (SSOT) | `"6.16.0"` |
| 2 | `.claude-plugin/plugin.json` | `version` | `"6.16.0"` |
| 3 | `README.md` | badge (line ~8) | `version-6.16.0-blue` |
| 4 | `CLAUDE.md` | footer `**Navigator Version**:` (+ the config-sample `"version"`) | `6.16.0` |
| 5 | `.agent/.nav-config.json` | `version` | `"6.16.0"` |
| 6 | `releases/RELEASE-NOTES-v6.16.0.md` | new file per release | filename |

`.agent/DEVELOPMENT-README.md` also carries a `(vX.Y.Z …)` footer note — refresh it opportunistically; it is not a
gated location. The git tag and GitHub release are produced by CI from the tag (`release.yml`), not hand-edited.

> This list is kept in sync with the authoritative checklist in `.agent/DEVELOPMENT-README.md`
> ("Scenario: releasing a new version"). If the two disagree, DEVELOPMENT-README wins and this SOP must be corrected.

---

## Semantic versioning

| Bump | Example | When |
|------|---------|------|
| **Patch** | 6.16.0 → 6.16.1 | Bug/typo/doc fixes only; no new features, no breaking changes |
| **Minor** | 6.16.0 → 6.17.0 | New features/skills, backward compatible |
| **Major** | 6.16.0 → 7.0.0 | Breaking changes (rename a skill trigger, change `.agent/` layout or config schema) |

Pre-release status is **not** a version-file change — it is driven purely by the tag suffix (`alpha`/`beta`/`rc`),
see Step 4.

---

## The release process

### Step 1 — Analyze state

```bash
jq -r '.metadata.version' .claude-plugin/marketplace.json     # current SSOT
git describe --tags --abbrev=0                                # latest tag
git log --oneline "$(git describe --tags --abbrev=0)"..HEAD   # unreleased commits
```

Pick the new version from the commit set per the semver table above.

### Step 2 — Bump all six locations

The five version-string files are updated by one script, which then runs the validator:

```bash
./scripts/bump-version.sh 6.16.0
```

`bump-version.sh` edits `plugin.json`, `marketplace.json`, `README.md`, `CLAUDE.md`, and `.agent/.nav-config.json`
format-preservingly, then runs `release_validator.py --check-version` and exits non-zero if any token is missing — so
drift can't slip through. Then write the sixth location, the release notes (Step 3).

Quick manual re-check any time:

```bash
python3 skills/nav-release/functions/release_validator.py --check-version 6.16.0
```

### Step 3 — Write release notes

Create `releases/RELEASE-NOTES-v<VERSION>.md` (the canonical path `release.yml` reads). Skeleton:

```markdown
# Navigator v<VERSION>: <Title>

**Released**: <YYYY-MM-DD>  ·  **Type**: <Patch|Minor|Major>  ·  **Status**: <Production|Experimental>

## What's New
### <Feature>
**Problem**: …  **Solution**: …
- <details>

## Bug Fixes
- <fix> (<file:line>)

## Breaking Changes
<None | list>

## Getting Started
/plugin install navigator
```

Optionally add a "What's New in v<VERSION>" section to `README.md` linking the notes file.

### Step 4 — Commit, tag, push

```bash
git add .claude-plugin/marketplace.json .claude-plugin/plugin.json \
        README.md CLAUDE.md .agent/.nav-config.json \
        releases/RELEASE-NOTES-v<VERSION>.md
git commit -m "chore(release): bump version to v<VERSION>"

git push origin main

# Tag AFTER all commits — this triggers release.yml
git tag -a v<VERSION> -m "Navigator v<VERSION>: <summary>"
git push origin v<VERSION>
```

The tag suffix decides pre-release: a tag containing `alpha`/`beta`/`rc` is published with `--prerelease`; otherwise
stable. No manual flag, no marketplace.json field.

### Step 5 — CI publishes (don't publish locally)

The pushed tag triggers `release.yml`:
1. **validate** — `make test`, then `release_validator.py --check-all` (skills exist + committed + versions
   consistent), `--verify-hook-paths`, `--check-version <tag>`, `--verify-tag <tag>`, `--verify-mod`, and since
   TASK-99 `--verify-dispatcher` (registry ops committed + importable, every hook through `nav_dispatch.py`),
   `--verify-conformance $CC_MOD_VERSION` (results file for the pinned Claude Code, one `env` at the top of the
   workflow) and `--verify-hooks` (manifest smoke test, hermetic unset path).
2. **release** — reads `releases/RELEASE-NOTES-v<version>.md`, marks pre-release from the tag suffix, and creates or
   updates the GitHub release in place (idempotent since `bfe3b26`).

> **Never run `gh release create` locally.** The workflow owns publication; a local create races CI and historically
> caused "release with the same tag name already exists" failures. If the workflow fails, fix and **re-run it**.

### Step 6 — Verify

```bash
# Watch the publish run (non-zero exit on failure)
gh run watch --exit-status "$(gh run list --workflow=release.yml --limit=1 --json databaseId --jq '.[0].databaseId')"
gh release view v<VERSION> --json tagName,name,isDraft,assets
python3 skills/nav-release/functions/release_validator.py --verify-tag v<VERSION>
```

Then confirm the README badge renders (Shields.io CDN cache is 5–10 min). Users update with `/plugin update navigator`.

---

### Step 7 — Sync the docs site (manual, every release)

The docs site (`~/Projects/startups/navigator-site`, repo `qf-studio/navigator-docs`, live at
https://navigator.quantflow.studio) is a separate repo — nothing about a plugin release
touches it. Since 2026-10-08 it runs on AWS like pilot-docs: ECS service `navigator-docs` on
the quantflow cluster behind the ALB and CloudFront. A docs release is a `prod-*` tag.
Every release needs:

```bash
cd ~/Projects/startups/navigator-site
# 1. Version chip
sed -i '' 's/CURRENT_VERSION = "v.*"/CURRENT_VERSION = "v<VERSION>"/' lib/version.ts
# 2. Content: new/changed skills -> content/skills/<name>.mdx (+ content/skills/_meta.js, index.mdx);
#    new config keys -> content/reference/nav-config-schema.mdx; concepts/workflows as needed
# 3. Build, commit, push main (build.yml publishes ghcr.io/qf-studio/navigator-docs:main)
bun run build && git add -A && git commit -m "docs(v<VERSION>): sync" && git push origin main
# 4. Release tag: "Build image" -> "Deploy QuantFlow AWS" (GHCR -> ECR -> CloudFormation
#    quantflow-svc-navigator-docs -> ECS stable -> CloudFront invalidation)
TAG="prod-<VERSION>-$(date +%s)" && git tag "$TAG" && git push origin "$TAG"
gh run watch --repo qf-studio/navigator-docs --exit-status \
  "$(gh run list --repo qf-studio/navigator-docs --workflow=deploy-quantflow-aws.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
# 5. Verify (allow a minute for the ECS rollout; the deploy invalidates the CDN)
curl -s https://navigator.quantflow.studio | grep -o 'v[0-9]\.[0-9]\.[0-9]'
```

Link previews: `metadataBase` derives from `NEXT_PUBLIC_SITE_URL`; the Dockerfile bakes
`https://navigator.quantflow.studio` and the code falls back to the same host. The old
Vercel project (navigator-site.vercel.app) is retired. Infra (ECR, service template, CDN
alias, Route 53) lives in `qf-studio/aws-infrastructure-pilot`, owned by Nelya.

## Pre-release checklist

**Before pushing the tag**
- [ ] All skills exist, committed, and listed in `plugin.json`
- [ ] All 6 version locations agree (`bump-version.sh` + validator passed)
- [ ] `releases/RELEASE-NOTES-v<VERSION>.md` written
- [ ] `release_validator.py --verify-hooks` passes when hooks/manifest changed
- [ ] Tag created **after** all commits

**After pushing**
- [ ] `release.yml` run is green; release published with notes attached
- [ ] Versions match across files; README badge renders

---

## Troubleshooting

**"release with the same tag name already exists"** — someone ran `gh release create` locally (or a stale skill did),
racing the workflow. Re-run the workflow; it's idempotent (`gh release edit` + `--clobber`). Never create locally.

```bash
gh run rerun "$(gh run list --workflow=release.yml --limit=1 --json databaseId --jq '.[0].databaseId')"
```

**`make test` fails in `validate` on `test_user_prompt_submit_p95_under_200ms` only** — runner noise
(p95 measured against a 200 ms ceiling; median stays ~75 ms). Seen on v7.8.0 (2026-09-28); the
push-triggered `test.yml` run on the same commit was green. Re-run the failed job, then verify as in Step 6:

```bash
gh run rerun "$(gh run list --workflow=release.yml --limit=1 --json databaseId --jq '.[0].databaseId')" --failed
```

If it flakes twice in a row, raise `NAV_TIMING_MULT` in the workflow or widen the ceiling instead of retrying.

**Version mismatch after release** — update the missing file to the SSOT, commit with a `fix:` prefix, push to `main`
(do **not** recreate the tag).

**Git tag already exists** —
```bash
git tag -d v<VERSION>; git push origin :refs/tags/v<VERSION>
git tag -a v<VERSION> -m "Navigator v<VERSION>"; git push origin v<VERSION>
```

**Forgot pre-release** — `gh release edit v<VERSION> --prerelease` (or fix the tag suffix and re-tag before anyone pulls).

**Badge not rendering** — confirm the `version-<V>-blue` format; Shields.io CDN cache is 5–10 min, hard-refresh.

**A doc still shows the old version** — search by pattern, not line number: `grep -rn "<old-version>" .`. Remember
`CLAUDE.md` carries the version in both the footer and the config sample.

---

## Related

- **Skill**: [`nav-release`](../../../skills/nav-release/SKILL.md) — interactive release walkthrough + validator
- **Deployment companion**: [`../deployment/plugin-release.md`](../deployment/plugin-release.md) — skill-existence / cache checklist
- **Public guide**: [`docs/DEPLOYMENT.md`](../../../docs/DEPLOYMENT.md) — manifest + pipeline overview
- **CI**: `.github/workflows/release.yml`, `.github/workflows/test.yml`
- **Authoritative bump checklist**: `.agent/DEVELOPMENT-README.md`
- **External**: [Semantic Versioning](https://semver.org/), [Conventional Commits](https://www.conventionalcommits.org/)

---

## History

- **2026-06-26**: Consolidated four overlapping release SOPs (`version-management`, `complete-release-workflow`,
  `navigator-plugin-release-workflow`, `plugin-release-workflow`, 1949 lines total) into this single canonical SOP.
  Carried forward the current material (SSOT + 6 locations from version-management 2026-06-04; CI pipeline + idempotent
  publish from complete-release-workflow 2026-06-02) and dropped the v1.5.0/v3.4.0-era manual-flow content.
