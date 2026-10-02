#!/usr/bin/env bash
#
# Navigator version bump
#
# Updates every version-bearing file from a single argument, then runs the
# release validator to assert they all agree. Replaces the manual, vim-driven
# multi-file edit the release SOP used to document (and which routinely drifted).
#
# Usage:
#   ./scripts/bump-version.sh 6.16.0
#
# Files updated (the five canonical version locations):
#   .claude-plugin/plugin.json        top-level "version"
#   .claude-plugin/marketplace.json   metadata.version
#   README.md                         version-X.Y.Z-blue badge
#   CLAUDE.md                         **Navigator Version**: X.Y.Z
#   .agent/.nav-config.json           top-level "version"
#
# Returns:
#   0 - all files updated and consistent
#   1 - bad argument, an expected token was not found, or versions disagree

set -euo pipefail

NEW_VERSION="${1:-}"

if [ -z "$NEW_VERSION" ]; then
    echo "Usage: $0 <version>   (e.g. $0 6.16.0)" >&2
    exit 1
fi

# Accept X.Y.Z with an optional pre-release suffix (e.g. 6.16.0-rc1).
if ! printf '%s' "$NEW_VERSION" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$'; then
    echo "Error: '$NEW_VERSION' is not a valid semantic version (expected X.Y.Z)" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

echo "Bumping Navigator to v$NEW_VERSION ..."

# Targeted, format-preserving in-place edits (python3 is already the test
# runtime, so no jq / GNU-vs-BSD sed portability headaches). Each pattern
# replaces exactly one version token and fails loudly if it matches nothing.
python3 - "$NEW_VERSION" <<'PY'
import re
import sys
from pathlib import Path

new = sys.argv[1]
root = Path.cwd()

SEMVER = r'[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.]+)?'

edits = [
    (".claude-plugin/plugin.json",
     r'("version":\s*")' + SEMVER + r'(")',
     r'\g<1>' + new + r'\g<2>'),
    (".claude-plugin/marketplace.json",
     r'("version":\s*")' + SEMVER + r'(")',
     r'\g<1>' + new + r'\g<2>'),
    ("README.md",
     r'(version-)' + SEMVER + r'(-blue\.svg)',
     r'\g<1>' + new + r'\g<2>'),
    ("CLAUDE.md",
     r'(\*\*Navigator Version\*\*:\s*)' + SEMVER,
     r'\g<1>' + new),
    (".agent/.nav-config.json",
     r'("version":\s*")' + SEMVER + r'(")',
     r'\g<1>' + new + r'\g<2>'),
]

failed = False
for rel, pattern, repl in edits:
    path = root / rel
    if not path.exists():
        print(f"  ERROR: {rel} not found", file=sys.stderr)
        failed = True
        continue
    text = path.read_text()
    new_text, count = re.subn(pattern, repl, text, count=1)
    if count == 0:
        print(f"  ERROR: no version token matched in {rel}", file=sys.stderr)
        failed = True
        continue
    path.write_text(new_text)
    print(f"  updated {rel}")

sys.exit(1 if failed else 0)
PY

echo
echo "Regenerating mod data (a fixture embeds the plugin version) ..."
python3 scripts/gen_mod_data.py

echo
echo "Verifying all files agree on v$NEW_VERSION ..."
python3 skills/nav-release/functions/release_validator.py --check-version "$NEW_VERSION"

echo
echo "✅ Bumped to v$NEW_VERSION. Review the diff, then commit and tag."
