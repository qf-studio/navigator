#!/usr/bin/env python3
"""
Navigator Feature Manager
Display and toggle Navigator features with formatted table output.

Usage:
    python3 feature_manager.py show [--first-session]
    python3 feature_manager.py enable <feature>
    python3 feature_manager.py disable <feature>
    python3 feature_manager.py info <feature>
"""

import sys
import json
import shlex
import shutil
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

# Feature definitions with metadata
FEATURES = {
    "task_mode": {
        "name": "task_mode",
        "display_name": "Task Mode",
        "version": "5.6.0",
        "description": "Auto-detects task complexity, defers to skills",
        "short_desc": "Unified workflow orchestration",
        "config_key": "task_mode",
        "enabled_key": "enabled",
        "default": True,
        "type": "config"
    },
    "tom_features": {
        "name": "tom_features",
        "display_name": "Theory of Mind",
        "version": "5.0.0",
        "description": "Verification checkpoints, user profile, diagnostics",
        "short_desc": "Human-AI collaboration improvements",
        "config_key": "tom_features",
        "enabled_key": "verification_checkpoints",
        "default": True,
        "type": "config"
    },
    "loop_mode": {
        "name": "loop_mode",
        "display_name": "Loop Mode",
        "version": "5.1.0",
        "description": "Autonomous loop execution (enable when needed)",
        "short_desc": "Run until done capability",
        "config_key": "loop_mode",
        "enabled_key": "enabled",
        "default": False,
        "type": "config"
    },
    "simplification": {
        "name": "simplification",
        "display_name": "Simplification",
        "version": "5.4.0",
        "description": "Post-implementation code cleanup with Opus",
        "short_desc": "Automatic code clarity improvements",
        "config_key": "simplification",
        "enabled_key": "enabled",
        "default": True,
        "type": "config"
    },
    "auto_update": {
        "name": "auto_update",
        "display_name": "Auto-Update",
        "version": "5.5.0",
        "description": "Auto-updates on session start",
        "short_desc": "Automatic plugin updates",
        "config_key": "auto_update",
        "enabled_key": "enabled",
        "default": True,
        "type": "config"
    },
    "knowledge_graph": {
        "name": "knowledge_graph",
        "display_name": "Knowledge Graph",
        "version": "6.0.0",
        "description": "Unified project knowledge + experiential memories",
        "short_desc": "Project knowledge graph with memories",
        "config_key": "knowledge_graph",
        "enabled_key": "enabled",
        "default": True,
        "type": "config"
    },
    "multi_agent": {
        "name": "multi_agent",
        "display_name": "Multi-Agent",
        "version": "6.0.0",
        "description": "Parallel agent orchestration (nav-multi skill)",
        "short_desc": "Parallel agent workflows",
        "config_key": "multi_agent",
        "enabled_key": "enabled",
        "default": True,
        "type": "config"
    },
    "multi_claude_scripts": {
        "name": "multi_claude_scripts",
        "display_name": "Multi-Claude Scripts",
        "version": "4.3.0",
        "description": "DEPRECATED (TASK-25) — use native /workflows + Agent tool",
        "short_desc": "Deprecated; superseded by native Workflows",
        "config_key": None,
        "enabled_key": None,
        "default": False,
        "type": "installed",
        "deprecated": True,
        "check_command": "command -v navigator-multi-claude.sh"
    },
    "compact_hook": {
        "name": "compact_hook",
        "display_name": "Compact Hook",
        "version": "6.x",
        "description": "Injects rich summary into compacted sessions",
        "short_desc": "Pre-compact summary injection",
        "config_key": "compact_hook",
        "enabled_key": "enabled",
        "default": True,
        "type": "config"
    },
    "workflow_enforcer_hook": {
        "name": "workflow_enforcer_hook",
        "display_name": "Workflow Enforcer",
        "version": "6.x",
        "description": "Enforces WORKFLOW CHECK block before task responses",
        "short_desc": "Mandatory workflow gate",
        "config_key": "workflow_enforcer_hook",
        "enabled_key": "enabled",
        "default": True,
        "type": "config"
    },
    "read_guard_hook": {
        "name": "read_guard_hook",
        "display_name": "Read Guard",
        "version": "6.x",
        "description": "Warns on excessive Reads (push to agents)",
        "short_desc": "Anti upfront-loading guard",
        "config_key": "read_guard_hook",
        "enabled_key": "enabled",
        "default": True,
        "type": "config"
    },
    "workflow_state_hook": {
        "name": "workflow_state_hook",
        "display_name": "Workflow State",
        "version": "6.x",
        "description": "Tracks current task/phase across the session",
        "short_desc": "Session state persistence",
        "config_key": "workflow_state_hook",
        "enabled_key": "enabled",
        "default": True,
        "type": "config"
    },
    "task_graph_sync_hook": {
        "name": "task_graph_sync_hook",
        "display_name": "Task Graph Sync",
        "version": "6.x",
        "description": "Auto-syncs task files into the knowledge graph",
        "short_desc": "Tasks → knowledge graph",
        "config_key": "task_graph_sync_hook",
        "enabled_key": "enabled",
        "default": True,
        "type": "config"
    },
    "profile_sync_hook": {
        "name": "profile_sync_hook",
        "display_name": "Profile Sync",
        "version": "6.x",
        "description": "Auto-captures preferences/corrections into profile",
        "short_desc": "Profile auto-learning",
        "config_key": "profile_sync_hook",
        "enabled_key": "enabled",
        "default": True,
        "type": "config"
    },
    # v7 hooks-runtime toggles (TASK-63 Phase 6). Defaults mirror
    # hooks/nav_hook_lib/config.py DEFAULTS: dispatcher ON, every net-new
    # blocking/injecting capability OFF until enabled deliberately.
    "dispatcher": {
        "name": "dispatcher",
        "display_name": "Hook Dispatcher",
        "version": "7.0.0",
        "description": "Single hook dispatcher runtime (nav_dispatch)",
        "short_desc": "v7 single-dispatcher hook runtime",
        "config_key": "dispatcher",
        "enabled_key": "enabled",
        "default": True,
        "type": "config"
    },
    "deep_research": {
        "name": "deep_research",
        "display_name": "Deep Research",
        "version": "7.3.0",
        "description": "Web deep research: cited report from fetched sources, critic + ship gate, graph ingestion (nav-deep-research skill)",
        "short_desc": "Web research → cited report → graph",
        "config_key": "deep_research",
        "enabled_key": "enabled",
        "default": False,
        "type": "config"
    },
    "judge": {
        "name": "judge",
        "display_name": "Typed Prompt Judge",
        "version": "7.7.0",
        "description": "Typed judge (TypeSafe Jev) behind the loop/complexity/ambiguity keyword scorers; decisive axes override, the rest fall back. Prompt leaves the machine when on.",
        "short_desc": "Jev judgments overlay the prompt scorers",
        "config_key": "judge",
        "enabled_key": "enabled",
        "default": False,
        "type": "config"
    },
    "tier1": {
        "name": "tier1",
        "display_name": "Tier-1 Answers",
        "version": "7.0.0",
        "description": "Zero-token answers for whitelisted prompts",
        "short_desc": "Prompt-block answers at zero model tokens",
        "config_key": "tier1",
        "enabled_key": "enabled",
        "default": False,
        "type": "config"
    },
    "stop_completion": {
        "name": "stop_completion",
        "display_name": "Stop Completion",
        "version": "7.0.0",
        "description": "Completion gate on Stop (decision:block)",
        "short_desc": "Forced-continuation completion gate",
        "config_key": "stop_completion",
        "enabled_key": "enabled",
        "default": False,
        "type": "config"
    },
    "jit_memory": {
        "name": "jit_memory",
        "display_name": "JIT Memory",
        "version": "7.0.0",
        "description": "Injects relevant memories after tool use",
        "short_desc": "Just-in-time memory injection",
        "config_key": "jit_memory",
        "enabled_key": "enabled",
        "default": False,
        "type": "config"
    },
    "subagent_context": {
        "name": "subagent_context",
        "display_name": "Subagent Context",
        "version": "7.0.0",
        "description": "Injects project context into subagents (2k)",
        "short_desc": "Subagent context injection",
        "config_key": "subagent_context",
        "enabled_key": "enabled",
        "default": False,
        "type": "config"
    },
    "failure_diagnosis": {
        "name": "failure_diagnosis",
        "display_name": "Failure Diagnosis",
        "version": "7.0.0",
        "description": "Surfaces graph pitfalls on tool failures",
        "short_desc": "Pitfall injection on PostToolUseFailure",
        "config_key": "failure_diagnosis",
        "enabled_key": "enabled",
        "default": False,
        "type": "config"
    },
    "config_guard": {
        "name": "config_guard",
        "display_name": "Config Guard",
        "version": "7.0.0",
        "description": "Warns when .nav-config.json edits break JSON",
        "short_desc": "Config validation on ConfigChange",
        "config_key": "config_guard",
        "enabled_key": "enabled",
        "default": True,
        "type": "config"
    },
    "setup_hook": {
        "name": "setup_hook",
        "display_name": "Setup Hint",
        "version": "7.0.0",
        "description": "One-line runtime status on the Setup event",
        "short_desc": "Setup-event onboarding/status line",
        "config_key": "setup_hook",
        "enabled_key": "enabled",
        "default": True,
        "type": "config"
    }
}

CONFIG_PATH = ".agent/.nav-config.json"


def load_config() -> Tuple[Optional[Dict], Optional[str]]:
    """Load nav-config.json, return (config, error)."""
    path = Path(CONFIG_PATH)
    if not path.exists():
        return None, f"Config not found: {CONFIG_PATH}"

    try:
        with open(path, 'r') as f:
            return json.load(f), None
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON: {e}"


def save_config(config: Dict) -> Optional[str]:
    """Save config, return error if any."""
    try:
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)
            f.write("\n")
        return None
    except Exception as e:
        return f"Failed to save: {e}"


def check_installed(check_command: str) -> bool:
    """Return True if the feature's executable resolves on PATH.

    The only installed-type feature probes with `command -v <script>`. We
    resolve the final token (the script name) via shutil.which rather than
    spawning `shell=True` under a bare `except:`, so KeyboardInterrupt and
    SystemExit are never swallowed and no shell parsing is involved.
    """
    if not check_command:
        return False
    tokens = shlex.split(check_command)
    executable = tokens[-1] if tokens else ""
    return bool(executable) and shutil.which(executable) is not None


def is_feature_enabled(config: Dict, feature_name: str) -> bool:
    """Check if a feature is enabled in config or installed."""
    if feature_name not in FEATURES:
        return False

    feature = FEATURES[feature_name]

    # Handle installed type (check if command exists)
    if feature.get("type") == "installed":
        check_cmd = feature.get("check_command")
        if check_cmd:
            return check_installed(check_cmd)
        return False

    # Handle config type
    config_key = feature.get("config_key")
    if not config_key:
        return feature["default"]

    config_section = config.get(config_key, {})

    if isinstance(config_section, dict):
        return config_section.get(feature["enabled_key"], feature["default"])
    return feature["default"]


def format_status(enabled: bool, feature_type: str = "config") -> str:
    """Format status with ASCII characters for consistent width."""
    if feature_type == "installed":
        return "[*]  " if enabled else "[ ]  "
    return "[x]  " if enabled else "[ ]  "


def show_features(config: Dict, first_session: bool = False) -> str:
    """Generate feature table display."""
    version = config.get("version", "unknown")

    lines = []

    if first_session:
        lines.append(f"v{version} Features Now Enabled:")
    else:
        lines.append(f"v{version} Features:")

    lines.append("")

    # Table header
    lines.append("┌─────────────────────────┬────────┬───────────────────────────────────────────────┐")
    lines.append("│ Feature                 │ Status │ Description                                   │")
    lines.append("├─────────────────────────┼────────┼───────────────────────────────────────────────┤")

    # Feature rows
    for feature_name, feature in FEATURES.items():
        enabled = is_feature_enabled(config, feature_name)
        feature_type = feature.get("type", "config")
        status = format_status(enabled, feature_type)

        # Truncate description if needed
        desc = feature["description"][:45]
        if len(feature["description"]) > 45:
            desc = desc[:42] + "..."

        # Format with padding
        name_col = feature_name.ljust(23)
        status_col = status.ljust(6)
        desc_col = desc.ljust(45)

        lines.append(f"│ {name_col} │ {status_col} │ {desc_col} │")

    lines.append("└─────────────────────────┴────────┴───────────────────────────────────────────────┘")
    lines.append("")
    lines.append(f"All v{version} features configured.")

    return "\n".join(lines)


def toggle_feature(config: Dict, feature_name: str, enable: bool) -> Tuple[Dict, str]:
    """Toggle a feature, return (updated_config, message)."""
    if feature_name not in FEATURES:
        available = ", ".join(FEATURES.keys())
        return config, f"❌ Unknown feature: {feature_name}\n\nAvailable: {available}"

    feature = FEATURES[feature_name]

    # Check if feature is toggleable
    if feature.get("type") == "installed":
        if enable:
            return config, f"💡 {feature['display_name']} requires installation.\n\nRun: 'Install multi-Claude workflows'"
        else:
            return config, f"💡 {feature['display_name']} uninstall not yet supported.\n\nManually remove scripts from ~/bin/ if needed."

    config_key = feature["config_key"]
    enabled_key = feature["enabled_key"]

    # Ensure config section exists
    if config_key not in config:
        config[config_key] = {}

    if not isinstance(config[config_key], dict):
        config[config_key] = {}

    # Set the enabled flag
    config[config_key][enabled_key] = enable

    action = "enabled" if enable else "disabled"
    status = "✅" if enable else "⏸ Off"

    message = f"{status} {feature['display_name']} {action}"
    if feature_name == "judge" and enable:
        message += (
            "\n\n🔑 The judge needs a TypeSafe API key (the prompt text is sent to "
            "api.typesafe.ai). Get one at https://console.typesafe.ai/keys, then export "
            "TYPESAFE_API_KEY in the environment Claude Code runs in, or write it to "
            "~/.config/typesafe/api_key (chmod 600). Never put it in .nav-config.json — "
            "that file is committed. Verify: python3 hooks/nav_hook_lib/judge.py --check "
            "from the plugin root. Without a key the keyword heuristics keep answering."
        )

    return config, message


def get_feature_info(feature_name: str, config: Dict) -> str:
    """Get detailed info about a feature."""
    if feature_name not in FEATURES:
        available = ", ".join(FEATURES.keys())
        return f"❌ Unknown feature: {feature_name}\n\nAvailable: {available}"

    feature = FEATURES[feature_name]
    enabled = is_feature_enabled(config, feature_name)
    status = "Enabled" if enabled else "Disabled"

    return f"""{feature['display_name']} (v{feature['version']})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{feature['short_desc']}

Status: {status}
Config key: {feature['config_key']}.{feature['enabled_key']}
Default: {"On" if feature['default'] else "Off"}

Description:
{feature['description']}"""


def main():
    parser = argparse.ArgumentParser(description="Navigator Feature Manager")
    parser.add_argument("command", choices=["show", "enable", "disable", "info"],
                        help="Command to execute")
    parser.add_argument("feature", nargs="?", help="Feature name (for enable/disable/info)")
    parser.add_argument("--first-session", action="store_true",
                        help="Show welcome message for first session")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    # Load config
    config, error = load_config()
    if error:
        print(f"❌ {error}", file=sys.stderr)
        return 1

    if args.command == "show":
        output = show_features(config, first_session=args.first_session)
        print(output)
        return 0

    elif args.command in ["enable", "disable"]:
        if not args.feature:
            print(f"❌ Feature name required for {args.command}", file=sys.stderr)
            return 1

        enable = args.command == "enable"
        config, message = toggle_feature(config, args.feature, enable)

        if message.startswith("❌"):
            print(message, file=sys.stderr)
            return 1

        # Save config
        save_error = save_config(config)
        if save_error:
            print(f"❌ {save_error}", file=sys.stderr)
            return 1

        print(message)
        print()
        print(show_features(config))
        return 0

    elif args.command == "info":
        if not args.feature:
            print("❌ Feature name required for info", file=sys.stderr)
            return 1

        output = get_feature_info(args.feature, config)
        print(output)
        return 0 if not output.startswith("❌") else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
