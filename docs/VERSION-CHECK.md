# Navigator Version Check

Automatic version checking to keep users on the latest Navigator version.

---

## How It Works

**Runs on**: Every session start ("Start my Navigator session")

**Location**: `scripts/check-version.sh`

**Integration**: nav-start skill (Step 1)

**Behavior**: Non-blocking notification

---

## What It Does

### 1. Checks Current Version

Reads from `.claude-plugin/plugin.json`:

```bash
current_version=$(grep '"version"' .claude-plugin/plugin.json | cut -d'"' -f4)
# Example: "3.4.0"
```

### 2. Checks Latest Version

Queries GitHub API:

```bash
latest_version=$(curl -s https://api.github.com/repos/qf-studio/navigator/releases/latest)
# Example: "3.4.0"
```

**Fallback**: If API fails, checks `plugin.json` in main branch

### 3. Compares Versions

Uses semantic version comparison:

```bash
version_lt "3.3.1" "3.4.0"  # Returns 0 (true)
version_lt "3.4.0" "3.4.0"  # Returns 1 (false)
```

### 4. Shows Notification

**If up to date**:
```
🔍 Checking Navigator version...
   Current: v3.4.0
   Latest:  v3.4.0

✅ Navigator is up to date!
```

**If update available**:
```
🔍 Checking Navigator version...
   Current: v3.3.1
   Latest:  v3.4.0

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 Update Available: v3.3.1 → v3.4.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

What's new in v3.4.0:
   See: https://github.com/qf-studio/navigator/releases/tag/v3.4.0

To update Navigator:
   Say: "Update Navigator"
   Or run: cd /path/to/navigator && git pull origin main

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**If cannot check** (network issue):
```
🔍 Checking Navigator version...
   Current: v3.4.0

⚠️  Cannot check for updates (network issue or GitHub API limit)
   You can manually check: https://github.com/qf-studio/navigator/releases
```

---

## Exit Codes

| Code | Meaning | Behavior |
|------|---------|----------|
| 0 | Up to date | Continue session normally |
| 1 | Update available | Show notification, continue session |
| 2 | Cannot check | Show warning, continue session |

**Important**: Version check **never blocks** session start.

---

## When Version Check Runs

### Automatic (Recommended)

Runs automatically when user starts Navigator session:

```
User: "Start my Navigator session"

→ Step 1: Check version (runs scripts/check-version.sh)
→ Step 2: Load DEVELOPMENT-README.md
→ Step 3: Check for active markers
→ ...
```

### Manual

Users can also check manually:

```bash
cd /path/to/navigator
./scripts/check-version.sh
```

---

## Configuration

No configuration needed - works out of the box.

**Requirements**:
- Internet connection (for GitHub API)
- `curl` installed (standard on macOS/Linux)
- Git repository with remote (for git pull instructions)

**Optional**:
- `gh` CLI (for creating releases)

---

## For Plugin Developers

### Creating New Releases

**Step 1**: Update version in plugin.json

```bash
vim .claude-plugin/plugin.json
# Change "version": "3.4.0" → "3.5.0"
```

**Step 2**: Commit and tag

```bash
git commit -m "chore: bump version to 3.5.0"
git tag -a v3.5.0 -m "Release notes"
git push origin main v3.5.0
```

**Step 3**: Create GitHub release

```bash
gh release create v3.5.0 \
  --title "Navigator v3.5.0 - Feature Name" \
  --notes-file RELEASE-NOTES-v3.5.0.md \
  --latest
```

**Step 4**: Verify version checker works

```bash
./scripts/check-version.sh
# Should show: Current v3.4.0, Latest v3.5.0
```

### Version Check Integration

To integrate version check in other skills:

```bash
# In skill's execution steps
if [ -f "scripts/check-version.sh" ]; then
  bash scripts/check-version.sh
fi

# Continue with skill execution (don't block on exit code)
```

**Always non-blocking** - version check is informational only.

---

## Troubleshooting

### "Cannot determine current Navigator version"

**Cause**: `.claude-plugin/plugin.json` not found or malformed

**Fix**:
```bash
# Verify file exists
ls -la .claude-plugin/plugin.json

# Verify JSON is valid
cat .claude-plugin/plugin.json | python3 -m json.tool
```

### "Cannot check for updates"

**Cause**: Network issue or GitHub API rate limit

**Fix**:
- Check internet connection
- Wait and retry (API rate limit resets hourly)
- Manually check: https://github.com/qf-studio/navigator/releases

### Version comparison wrong

**Cause**: Non-standard version format

**Expected format**: `X.Y.Z` (semantic versioning)
- ✅ `3.4.0`
- ✅ `3.10.2`
- ❌ `3.4` (missing patch version)
- ❌ `v3.4.0` (v prefix removed automatically)

---

## Privacy & Security

**What is sent**:
- HTTP request to `https://api.github.com/repos/qf-studio/navigator/releases/latest`
- No personal data
- No tracking
- No telemetry

**What is NOT sent**:
- Your project files
- Your Navigator configuration
- Your current version (only checked locally)
- Any identifying information

**Offline mode**:
- If no internet: Shows warning, continues
- If GitHub down: Shows warning, continues
- Never blocks Navigator functionality

---

## Version History

| Version | Feature |
|---------|---------|
| 3.4.0 | Initial version check implementation |

---

## See Also

- [Navigator Upgrade Guide](../UPGRADE-v3.4.0.md)
- [Release Workflow SOP](../.agent/sops/development/release-workflow.md)
- [nav-upgrade Skill](../skills/nav-upgrade/SKILL.md)

---

**Last Updated**: 2025-10-22
**Navigator Version**: 3.4.0+
