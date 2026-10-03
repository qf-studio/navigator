#!/bin/bash
#
# Navigator Version Checker
#
# Checks if user is running latest version and prompts to update if outdated.
#
# Usage:
#   ./scripts/check-version.sh
#
# Returns:
#   0 - Up to date
#   1 - Update available
#   2 - Error (cannot check)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get current version from plugin.json
get_current_version() {
    if [ -f "$PLUGIN_DIR/.claude-plugin/plugin.json" ]; then
        grep -o '"version"[[:space:]]*:[[:space:]]*"[^"]*"' "$PLUGIN_DIR/.claude-plugin/plugin.json" | \
            cut -d'"' -f4
    else
        echo "unknown"
    fi
}

# Get latest version from GitHub
get_latest_version() {
    # Try GitHub API first
    local latest_version=$(curl -s https://api.github.com/repos/qf-studio/navigator/releases/latest | \
        grep '"tag_name":' | \
        sed -E 's/.*"v([^"]+)".*/\1/')

    if [ -n "$latest_version" ]; then
        echo "$latest_version"
        return 0
    fi

    # Fallback: check plugin.json in main branch
    local fallback_version=$(curl -s https://raw.githubusercontent.com/qf-studio/navigator/main/.claude-plugin/plugin.json | \
        grep -o '"version"[[:space:]]*:[[:space:]]*"[^"]*"' | \
        cut -d'"' -f4)

    if [ -n "$fallback_version" ]; then
        echo "$fallback_version"
        return 0
    fi

    # Cannot determine latest version
    return 1
}

# Compare versions (returns 0 if v1 < v2, 1 otherwise)
version_lt() {
    # Remove 'v' prefix if present
    local v1=${1#v}
    local v2=${2#v}

    # Equal versions are never "less than".
    [ "$v1" = "$v2" ] && return 1

    # v1 < v2 iff v1 sorts first under version ordering (sort -V handles
    # numeric segments correctly, e.g. 6.9.0 < 6.10.0). Returns the exit
    # status of the final test: 0 when v1 sorts first, 1 otherwise.
    local first
    first=$(printf '%s\n%s\n' "$v1" "$v2" | sort -V | head -n1)
    [ "$first" = "$v1" ]
}

# Main execution
main() {
    local current_version=$(get_current_version)

    if [ "$current_version" = "unknown" ]; then
        echo -e "${RED}⚠️  Cannot determine current Navigator version${NC}"
        echo "   Expected: .claude-plugin/plugin.json"
        return 2
    fi

    echo -e "${BLUE}🔍 Checking Navigator version...${NC}"
    echo -e "   Current: ${GREEN}v$current_version${NC}"

    # Split declaration from assignment so $? reflects get_latest_version's
    # exit status, not `local`'s (which is almost always 0 and masked the
    # network-failure guard below).
    local latest_version
    latest_version=$(get_latest_version)

    if [ $? -ne 0 ] || [ -z "$latest_version" ]; then
        echo -e "${YELLOW}⚠️  Cannot check for updates (network issue or GitHub API limit)${NC}"
        echo "   You can manually check: https://github.com/qf-studio/navigator/releases"
        return 2
    fi

    echo -e "   Latest:  ${GREEN}v$latest_version${NC}"
    echo

    if version_lt "$current_version" "$latest_version"; then
        # Update available
        echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${YELLOW}📦 Update Available: v$current_version → v$latest_version${NC}"
        echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo
        echo -e "${BLUE}What's new in v$latest_version:${NC}"
        echo "   See: https://github.com/qf-studio/navigator/releases/tag/v$latest_version"
        echo
        echo -e "${GREEN}To update Navigator:${NC}"
        echo '   Say: "Update Navigator"'
        echo "   Or run: cd $PLUGIN_DIR && git pull origin main"
        echo
        echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        return 1
    else
        # Up to date
        echo -e "${GREEN}✅ Navigator is up to date!${NC}"
        return 0
    fi
}

# Execute only when run directly, not when sourced (lets tests exercise
# version_lt() without triggering the network check in main).
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    main "$@"
fi
