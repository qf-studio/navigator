#!/usr/bin/env python3
"""
Navigator Config Migrator
Migrates .nav-config.json to latest version, adding missing sections.

Usage:
    python3 config_migrator.py .agent/.nav-config.json

Output:
    Updated config with new sections added
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Fallback version used only if plugin.json cannot be located/read.
# The real current version is loaded at runtime from .claude-plugin/plugin.json
# (see _read_plugin_version below). Keeping a fallback avoids hard-failing
# migrations on broken installs, but it intentionally lags far behind so a
# stale literal cannot silently downgrade a user's config.
_FALLBACK_VERSION = "0.0.0"


def _read_plugin_version() -> str:
    """
    Resolve the current Navigator version from .claude-plugin/plugin.json.

    Walks upward from this file's location looking for a sibling
    ``.claude-plugin/plugin.json``. This works both when invoked from the
    plugin source repo and from an installed plugin cache directory, since
    Claude Code preserves the ``skills/<skill>/functions/`` layout.

    Returns the ``version`` field, or ``_FALLBACK_VERSION`` if the file
    cannot be found or parsed.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / ".claude-plugin" / "plugin.json"
        if candidate.is_file():
            try:
                with open(candidate, "r") as f:
                    data = json.load(f)
                version = data.get("version")
                if isinstance(version, str) and version:
                    return version
            except (OSError, json.JSONDecodeError):
                break
            break
    return _FALLBACK_VERSION


CURRENT_VERSION = _read_plugin_version()

# Config sections added in each version.
#
# Each top-level key is the Navigator version that INTRODUCED the config
# block(s) under it. get_missing_configs seeds a block only when the user's
# recorded version is <= the introduction version AND the block is absent
# (see get_missing_configs), so this is purely additive and idempotent —
# a user upgrading from an old version receives every block introduced after
# them, while a user already ahead of a given version is assumed to have it.
#
# Default shapes are copied verbatim from the live .agent/.nav-config.json so
# upgraded users get the same discoverable opt-out keys the project ships with.
#
# v7.0.0 successor-block decision (TASK-63 Phase 1): v7 ops kept the v6 config
# keys verbatim (workflow_enforcer_hook, read_guard_hook, etc. — see
# hooks/nav_hook_lib/registry.py OpSpec.config_key), so NO successor blocks and
# NO renames exist. strict_block inheritance is therefore satisfied by the
# additive-only rule: existing blocks are never touched, so the user's
# enforcement posture carries over unchanged, and rollback to v6.18.1 finds its
# config intact. No derived-seed machinery is needed.
#
# v7.0.0 block shapes MUST match hooks/nav_hook_lib/config.py DEFAULTS — that
# file is the runtime's layered-config contract and the source of truth
# (test_config_migrator.py cross-checks). Every net-new blocking/injecting
# capability seeds OFF (mem-037 class: prove before enable); only the
# dispatcher and the systemMessage-only safety surfaces (config_guard,
# setup_hook — warnings on explicit events, never blocking) ship ON.
VERSION_CONFIGS: Dict[str, Dict[str, Any]] = {
    "5.0.0": {
        "tom_features": {
            "verification_checkpoints": True,
            "confirmation_threshold": "high-stakes",
            "profile_enabled": True,
            "diagnose_enabled": True,
            "belief_anchors": False
        }
    },
    "5.1.0": {
        "loop_mode": {
            "enabled": False,
            "max_iterations": 5,
            "stagnation_threshold": 3,
            "exit_requires_explicit_signal": True,
            "show_status_block": True,
            "iteration_approval": "none",
            "periodic_interval": 3,
            "never_pause_on_stagnation": False,
            "stagnation_diversify_strategy": "combine"
        }
    },
    "5.4.0": {
        "simplification": {
            "enabled": False,
            "trigger": "post-implementation",
            "scope": "modified"
        }
    },
    "5.5.0": {
        "auto_update": {
            "enabled": True,
            "check_interval_hours": 1
        }
    },
    "5.6.0": {
        "task_mode": {
            "enabled": True,
            "auto_detect": True,
            "defer_to_skills": True,
            "complexity_threshold": 0.5,
            "show_phase_indicator": True
        }
    },
    "6.0.0": {
        "knowledge_graph": {
            "enabled": True,
            "auto_capture_corrections": True,
            "auto_capture_decisions": True,
            "auto_surface_relevant": True,
            "max_session_memories": 5,
            "confidence_decay_rate": 0.01,
            "staleness_threshold_days": 90,
            "git_tracked": True
        }
    },
    "6.9.0": {
        "session_start_hook": {
            "enabled": True,
            "include_sections": [
                "navigator",
                "marker",
                "config",
                "graph",
                "profile",
                "tasks",
                "auto_update"
            ],
            "char_budget": 9500
        }
    },
    "6.10.0": {
        "compact_hook": {
            "enabled": True,
            "include_transcript_summary": True,
            "include_git_state": True,
            "char_budget": 8000,
            "append_post_compact_summary": True
        }
    },
    "6.11.0": {
        "task_graph_sync_hook": {
            "enabled": True
        },
        "workflow_state_hook": {
            "enabled": True
        },
        "profile_sync_hook": {
            "enabled": True
        }
    },
    "6.11.1": {
        "workflow_enforcer_hook": {
            "enabled": True,
            "strict_block": True
        }
    },
    "6.12.0": {
        "read_guard_hook": {
            "enabled": True,
            "warn_threshold": 3,
            "escalate_threshold": 5,
            "strict_block": True,
            "allowlist": [
                "DEVELOPMENT-README.md",
                ".nav-config.json",
                ".user-profile.json",
                "knowledge/graph.json"
            ]
        }
    },
    "7.0.0": {
        "dispatcher": {
            "enabled": True
        },
        "tier1": {
            "enabled": False,
            "rules": {
                "nav_stats": True,
                "show_features": True,
                "list_markers": True,
                "graph_health": True,
                "nav_version": True
            }
        },
        "stop_completion": {
            "enabled": False,
            "continue_enabled": False,
            "max_continues": 2
        },
        "jit_memory": {
            "enabled": False
        },
        "subagent_context": {
            "enabled": False,
            "budget_chars": 2000
        },
        "failure_diagnosis": {
            "enabled": False
        },
        "config_guard": {
            "enabled": True
        },
        "setup_hook": {
            "enabled": True
        }
    },
    "7.3.0": {
        "deep_research": {
            "enabled": False,
            "max_sources": 30,
            "min_sources": 8,
            "fetchers": 4,
            "max_full_reads": 10,
            "critic_enabled": True,
            "models": {"fetcher": "sonnet", "writer": "opus", "critic": "opus", "patcher": "opus"}
        }
    },
    "7.9.0": {
        "adhd_mode": {
            "enabled": True,
            "on": None
        }
    },
    "8.3.0": {
        "reply_modes": {
            "enabled": True
        },
        "ste_mode": {
            "enabled": True,
            "on": None
        }
    },
}


def parse_version(version: str) -> Tuple[int, int, int]:
    """Parse version string to tuple for comparison."""
    parts = version.replace("v", "").split(".")
    return tuple(int(p) for p in parts[:3])


def version_less_than(v1: str, v2: str) -> bool:
    """Check if v1 < v2."""
    return parse_version(v1) < parse_version(v2)


def get_missing_configs(current_version: str, config: Dict) -> Dict[str, Any]:
    """
    Determine which config sections are missing based on version.

    Args:
        current_version: Current config version
        config: Current config dict

    Returns:
        Dict of missing config sections to add
    """
    missing = {}

    for version, configs in VERSION_CONFIGS.items():
        # Check if this version's configs should be added
        if version_less_than(current_version, version) or current_version == version:
            for key, default_value in configs.items():
                if key not in config:
                    missing[key] = default_value

    return missing


def migrate_config(config_path: str, dry_run: bool = False) -> Dict[str, Any]:
    """
    Migrate config to latest version.

    Args:
        config_path: Path to .nav-config.json
        dry_run: If True, don't write changes

    Returns:
        Dict with migration results
    """
    path = Path(config_path)

    if not path.exists():
        return {
            "success": False,
            "error": f"Config not found: {config_path}",
            "changes": []
        }

    try:
        with open(path, 'r') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Invalid JSON: {e}",
            "changes": []
        }

    current_version = config.get("version", "1.0.0")
    changes = []

    # Get missing configs
    missing = get_missing_configs(current_version, config)

    # Add missing sections
    for key, value in missing.items():
        config[key] = value
        changes.append({
            "action": "added",
            "key": key,
            "value": value
        })

    # Update version — only when the existing config is OLDER than the
    # current Navigator version. A direction-blind `!=` here previously
    # caused downgrades when the running plugin's CURRENT_VERSION was a
    # stale literal lower than the user's installed version (issue #7).
    if version_less_than(current_version, CURRENT_VERSION):
        old_version = current_version
        config["version"] = CURRENT_VERSION
        changes.append({
            "action": "updated",
            "key": "version",
            "old": old_version,
            "new": CURRENT_VERSION
        })

    # Write if not dry run and there are changes
    if changes and not dry_run:
        with open(path, 'w') as f:
            json.dump(config, f, indent=2)
            f.write("\n")  # Trailing newline

    return {
        "success": True,
        "config_path": str(path),
        "old_version": current_version,
        # Reflect the version actually stored in the config. If the user is
        # already on a newer version we leave it alone (see guard above), so
        # reporting CURRENT_VERSION here would be a lie.
        "new_version": config.get("version", current_version),
        "changes": changes,
        "config": config
    }


def format_changes(result: Dict) -> str:
    """Format migration result for display."""
    if not result["success"]:
        return f"❌ Migration failed: {result['error']}"

    if not result["changes"]:
        return f"✅ Config already up to date (v{result['new_version']})"

    lines = [
        f"✅ Config migrated: v{result['old_version']} → v{result['new_version']}",
        "",
        "Changes:"
    ]

    for change in result["changes"]:
        if change["action"] == "added":
            key = change["key"]
            lines.append(f"  + {key}: (new section added)")
        elif change["action"] == "updated":
            lines.append(f"  ~ {change['key']}: {change['old']} → {change['new']}")

    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Migrate Navigator config")
    parser.add_argument("config_path", help="Path to .nav-config.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show changes without applying")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")

    args = parser.parse_args()

    result = migrate_config(args.config_path, dry_run=args.dry_run)

    if args.json:
        # Don't include full config in JSON output (too verbose)
        output = {k: v for k, v in result.items() if k != "config"}
        print(json.dumps(output, indent=2))
    else:
        print(format_changes(result))

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
