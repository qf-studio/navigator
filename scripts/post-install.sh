#!/bin/bash
# Navigator Plugin Post-Install Hook
# Called automatically by Claude Code after plugin install/update
# Scans for old JITD projects and offers migration

set -e

PLUGIN_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_VERSION=$(grep -o '"version": "[^"]*"' "$PLUGIN_DIR/.claude-plugin/marketplace.json" | cut -d'"' -f4)

# Colors
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🔧 Navigator Plugin Post-Install (v$PLUGIN_VERSION)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Function to migrate a single project
migrate_project() {
    local project_dir="$1"
    local agent_dir="$project_dir/.agent"

    # Skip if no .agent directory
    [ ! -d "$agent_dir" ] && return

    # Check for old config
    if [ -f "$agent_dir/.jitd-config.json" ] && [ ! -f "$agent_dir/.nav-config.json" ]; then
        echo ""
        echo -e "${YELLOW}📦 Navigator project found:${NC} $(basename "$project_dir")"
        echo -e "${YELLOW}🔄 Migration needed:${NC} .jitd-config.json detected"
        echo ""
        echo "   Path: $project_dir"
        echo ""
        echo "Migrate automatically? [Y/n]"
        read -r response

        if [[ "$response" =~ ^([yY][eE][sS]|[yY]|)$ ]]; then
            # Run migration
            bash "$PLUGIN_DIR/scripts/migrate-config.sh" "$project_dir"

            echo ""
            echo -e "${GREEN}💡 Tip:${NC} Run '/nav:migrate' in Claude Code to update documentation"
            echo ""
        else
            echo -e "${YELLOW}⏭️  Skipped migration for $(basename "$project_dir")${NC}"
            echo -e "${BLUE}💡 Run '/nav:migrate' in Claude Code when ready${NC}"
            echo ""
        fi
    fi
}

# Find all Navigator projects in common locations
echo -e "${BLUE}🔍 Scanning for Navigator projects...${NC}"
echo ""

FOUND_COUNT=0

# Scan ~/Projects (customize based on user's workspace)
if [ -d "$HOME/Projects" ]; then
    while IFS= read -r -d '' config_file; do
        project_dir="$(dirname "$(dirname "$config_file")")"
        migrate_project "$project_dir"
        ((FOUND_COUNT++))
    done < <(find "$HOME/Projects" -maxdepth 5 -name ".jitd-config.json" -print0 2>/dev/null)
fi

# Also check current directory if in a project
if [ -f "./.agent/.jitd-config.json" ]; then
    migrate_project "."
    ((FOUND_COUNT++))
fi

if [ $FOUND_COUNT -eq 0 ]; then
    echo -e "${GREEN}✅ No migration needed${NC}"
    echo "   All Navigator projects are up to date"
    echo ""
fi

# Enable OpenTelemetry for Navigator v3.1+
enable_otel() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}📊 Navigator v3.1 - OpenTelemetry Integration${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "Navigator can show real-time session statistics:"
    echo "  • Real token usage (input/output/cache)"
    echo "  • Cache hit rates (CLAUDE.md performance)"
    echo "  • Session costs (actual USD spent)"
    echo "  • Active time tracking"
    echo ""
    echo "Enable OpenTelemetry? [Y/n]"
    read -r response

    if [[ ! "$response" =~ ^([yY][eE][sS]|[yY]|)$ ]]; then
        echo -e "${YELLOW}⏭️  Skipped OpenTelemetry setup${NC}"
        echo -e "${BLUE}💡 Enable later: See .agent/sops/integrations/opentelemetry-setup.md${NC}"
        echo ""
        return
    fi

    # Detect shell config file
    SHELL_CONFIG=""
    if [ -n "$ZSH_VERSION" ] || [ -f "$HOME/.zshrc" ]; then
        SHELL_CONFIG="$HOME/.zshrc"
    elif [ -n "$BASH_VERSION" ] || [ -f "$HOME/.bashrc" ]; then
        SHELL_CONFIG="$HOME/.bashrc"
    else
        echo -e "${YELLOW}⚠️  Could not detect shell config file${NC}"
        echo "Manually add to ~/.zshrc or ~/.bashrc:"
        echo ""
        echo "  export CLAUDE_CODE_ENABLE_TELEMETRY=1"
        echo "  export OTEL_METRICS_EXPORTER=console"
        echo "  export OTEL_METRIC_EXPORT_INTERVAL=10000"
        echo ""
        return
    fi

    # Check if already configured
    if grep -q "CLAUDE_CODE_ENABLE_TELEMETRY" "$SHELL_CONFIG" 2>/dev/null; then
        echo -e "${GREEN}✅ OpenTelemetry already configured in $(basename "$SHELL_CONFIG")${NC}"
        echo ""
        return
    fi

    # Add configuration
    cat >> "$SHELL_CONFIG" << 'OTEL_EOF'

# OpenTelemetry for Claude Code (Navigator v3.1)
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_METRICS_EXPORTER=console
export OTEL_METRIC_EXPORT_INTERVAL=10000  # 10 seconds for development
OTEL_EOF

    echo -e "${GREEN}✅ Added OpenTelemetry configuration to $(basename "$SHELL_CONFIG")${NC}"
    echo ""
    echo -e "${YELLOW}⚠️  Restart your terminal or run:${NC}"
    echo "   source $SHELL_CONFIG"
    echo ""
}

# Run OTel setup
enable_otel

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Post-install complete${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${BLUE}📚 Documentation:${NC} https://github.com/qf-studio/navigator"
echo -e "${BLUE}💬 Issues:${NC} https://github.com/qf-studio/navigator/issues"
echo ""
