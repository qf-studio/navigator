---
name: nav-release
description: Validate and release Navigator plugin to marketplace. Auto-invoke when user says "release plugin", "publish navigator", "create release", or "deploy new version".
allowed-tools: Read, Bash, Grep, Glob, AskUserQuestion
version: 1.0.0
---

# Navigator Release Skill

Validate plugin integrity and release to marketplace with all safety checks.

## Why This Exists

After v5.1.0 incident where nav-profile was referenced in plugin.json but never committed, causing install failures. This skill ensures:
- All referenced skills exist and are committed
- Version consistency across all files
- Tag created AFTER all commits
- Post-release verification

## When to Invoke

**Auto-invoke when**:
- User says "release plugin", "publish navigator"
- User says "create release", "deploy new version"
- User says "release vX.Y.Z"

**DO NOT invoke if**:
- Just committing changes (no release)
- Updating documentation only
- Testing locally

## Execution Steps

### Step 1: Pre-Release Validation [CRITICAL]

**Run validation script**:

```bash
python3 functions/release_validator.py --check-all
```

This validates:
1. All skills in plugin.json exist
2. All skill files are committed (not untracked)
3. Version consistency across files
4. No uncommitted changes in skills/

**If validation fails**: STOP and fix issues before proceeding.

### Step 1.5: Hook Smoke Test [STRONGLY RECOMMENDED for any release touching hooks or plugin.json]

**Run hook smoke-test**:

```bash
python3 functions/release_validator.py --verify-hooks
```

This executes every plugin manifest hook command via `bash` twice — once with `$CLAUDE_PLUGIN_ROOT` bound to the latest cache version, once with it explicitly unset (`env -u CLAUDE_PLUGIN_ROOT`). It detects the **v6.14.0 silent-fail signature**: a payload-emitting hook (`SessionStart`, `PreCompact`, `PostCompact`) that exits 0 with no stdout and no stderr.

Other hook events (`Stop`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`) are silent by design — they're state-writers or blocking-only — so quiet exit 0 there is correct behavior and is not flagged.

**Expected output on a healthy release**:

```
Hook smoke-test: 20/20 passed, 0 failed

  ✓  SessionStart       [set  ] exit=0 out=10353B err=0B
  ✓  SessionStart       [unset] exit=0 out=10353B err=0B
  ✓  PreCompact         [set  ] exit=0 out=2B err=87B
  ✓  PreCompact         [unset] exit=0 out=2B err=87B
  ...
```

**Regression output** (what v6.14.0 would have shown):

```
  ❌ SessionStart       [unset] silent exit 0 — payload-emitting hook produced no output
     python3 "${CLAUDE_PLUGIN_ROOT:-...}/hooks/nav_session_start.py"
```

**If `--verify-hooks` fails**: STOP. The hook command in plugin.json is broken in the `CLAUDE_PLUGIN_ROOT`-unset case. Fix the command (typically a fallback-path expansion issue) and re-run before proceeding.

**Background**: this check was added in v6.15.2 after v6.14.0 shipped a shell guard (`if [ -n "$CLAUDE_PLUGIN_DIR" ]; then ... fi`) that silently no-opped every hook when the variable was unset. The bug masked itself for two releases because the navigator source repo had a project-local `.claude/settings.json` backstop. Other Nav-initialized projects (no backstop) got zero injection with zero error signal. See `mem-036` and `releases/RELEASE-NOTES-v6.15.1.md` / `v6.15.2.md`.

### Step 2: Display Validation Results

Show validation summary:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NAVIGATOR RELEASE VALIDATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Skills Check:
  [x] nav-loop          ✓ exists, committed
  [x] nav-profile       ✓ exists, committed
  [x] nav-diagnose      ✓ exists, committed
  ...

Version Check:
  plugin.json:      5.1.0 ✓
  marketplace.json: 5.1.0 ✓
  CLAUDE.md:        5.1.0 ✓
  README.md:        5.1.0 ✓

Git Status:
  Uncommitted skills: 0 ✓
  Untracked skills:   0 ✓

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VALIDATION: PASSED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Step 3: Confirm Version

**Ask user to confirm version**:

```
Ready to release Navigator vX.Y.Z

This will:
1. Commit any pending changes
2. Push to origin/main
3. Create and push git tag vX.Y.Z
4. CI workflow (.github/workflows/release.yml) publishes the GitHub release from the tag

Proceed? [Y/n]
```

### Step 4: Execute Release

**If confirmed**, run release sequence:

```bash
# 1. Commit if needed
git add .
git commit -m "chore(release): prepare vX.Y.Z" || true

# 2. Push to origin
git push origin main

# 3. Create and push tag — this triggers .github/workflows/release.yml,
#    which creates the GitHub release from releases/RELEASE-NOTES-vX.Y.Z.md.
git tag -a vX.Y.Z -m "Navigator vX.Y.Z: [description]"
git push origin vX.Y.Z
```

**Do NOT run `gh release create` locally.** The workflow owns release
publication. Local creation races the workflow and historically caused
"release with the same tag name already exists" CI failures.

### Step 5: Post-Release Verification

**Wait for the Publish Release workflow and verify it succeeded**:

```bash
# Watch the most recent run; exits non-zero if it fails.
gh run watch --exit-status "$(gh run list --workflow=release.yml --limit=1 --json databaseId --jq '.[0].databaseId')"

# Confirm the release is published
gh release view vX.Y.Z --json tagName,name,isDraft,assets
```

If the workflow fails, inspect with `gh run view --log-failed` and fix
before retrying — do NOT fall back to `gh release create` locally.

**Verify tag contains all skills**:

```bash
python3 functions/release_validator.py --verify-tag vX.Y.Z
```

**Clear local cache** (for testing):

```bash
rm -rf ~/.claude/plugins/cache/navigator-marketplace/
```

**Instruct user to test**:

```
Release complete! To verify:

1. Run: /plugin install navigator
2. Check plugin list shows vX.Y.Z
3. Verify no errors in plugin details

If errors occur, see: .agent/sops/deployment/plugin-release.md
```

---

### Step 6: Update Installed Plugin + Sync Docs Site

```bash
claude plugin update navigator && claude plugin list | grep -A1 navigator@   # then restart
```

The docs site is a separate repo (`qf-studio/navigator-docs`, local
`~/Projects/startups/navigator-site`, live at https://navigator.quantflow.studio on AWS);
it does not update itself. Bump `lib/version.ts`, add/adjust `content/skills/*.mdx` and
`content/reference/nav-config-schema.mdx` for anything new, `bun run build`, commit and push
`main`, then push a `prod-<VERSION>-$(date +%s)` tag: "Build image" publishes the image to
GHCR and "Deploy QuantFlow AWS" rolls it to ECS and invalidates CloudFront. Confirm the live
version string at navigator.quantflow.studio. Full procedure:
`.agent/sops/development/release-workflow.md` Step 7.

## Predefined Functions

### functions/release_validator.py

Validates plugin integrity before release:

```bash
# Check all skills exist and are committed
python3 functions/release_validator.py --check-all

# Verify specific version
python3 functions/release_validator.py --check-version 5.1.0

# Verify tag contents
python3 functions/release_validator.py --verify-tag v6.15.2

# Smoke-test plugin manifest hook commands (v6.15.2+)
python3 functions/release_validator.py --verify-hooks
```

---

## Error Handling

**Missing skill detected**:
```
❌ VALIDATION FAILED

Missing skills:
  - skills/nav-profile/ (referenced in plugin.json but not found)

Fix: Create the skill or remove from plugin.json
```

**Uncommitted skills detected**:
```
❌ VALIDATION FAILED

Uncommitted skills:
  - skills/nav-loop/ (modified)
  - skills/nav-profile/ (untracked)

Fix: git add skills/ && git commit -m "Add missing skills"
```

**Version mismatch detected**:
```
❌ VALIDATION FAILED

Version mismatch:
  plugin.json:      5.1.0
  marketplace.json: 5.0.0  ← MISMATCH
  CLAUDE.md:        5.1.0

Fix: Update marketplace.json to 5.1.0
```

---

## Success Criteria

Release is successful when:
- [ ] All skills validated (exist + committed)
- [ ] Version consistent across all files
- [ ] Hook smoke-test passes (`--verify-hooks` reports zero failures)
- [ ] Git tag created after all commits
- [ ] Publish Release workflow run completes successfully
- [ ] GitHub release published with notes asset attached
- [ ] Test installation succeeds (no errors)

---

## Quick Reference

```bash
# Full release with validation
"Release Navigator v5.2.0"

# Just validate (no release)
"Validate plugin for release"

# Fix after failed release
"Fix release tag v5.1.0"
```

---

## Related

- **SOP**: `.agent/sops/deployment/plugin-release.md`
- **Config**: `.claude-plugin/plugin.json`
- **Marketplace**: `.claude-plugin/marketplace.json`
