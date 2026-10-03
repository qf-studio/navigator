#!/usr/bin/env python3
"""
Navigator Plugin Updater

Executes plugin update with retry logic and verification.

Usage:
    python plugin_updater.py [--target-version VERSION]
"""

import argparse
import json
import subprocess
import sys
import time
from typing import Dict


def update_plugin_via_claude() -> Dict:
    """
    Execute /plugin update navigator command.

    Returns:
        Dict with success status and output
    """
    try:
        # Execute update command
        result = subprocess.run(
            ['claude', 'plugin', 'update', 'navigator'],
            capture_output=True,
            text=True,
            timeout=60
        )

        success = result.returncode == 0

        return {
            'success': success,
            'output': result.stdout,
            'error': result.stderr,
            'method': 'update'
        }
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'error': 'Update timed out after 60 seconds',
            'method': 'update'
        }
    except FileNotFoundError:
        return {
            'success': False,
            'error': 'claude command not found. Is Claude Code installed?',
            'method': 'update'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'method': 'update'
        }


def reinstall_plugin() -> Dict:
    """
    Uninstall and reinstall Navigator plugin.

    Returns:
        Dict with success status
    """
    try:
        # Uninstall
        uninstall_result = subprocess.run(
            ['claude', 'plugin', 'uninstall', 'navigator'],
            capture_output=True,
            text=True,
            timeout=30
        )

        if uninstall_result.returncode != 0:
            return {
                'success': False,
                'error': f'Uninstall failed: {uninstall_result.stderr}',
                'method': 'reinstall'
            }

        # Wait a moment
        time.sleep(2)

        # Add from marketplace
        add_result = subprocess.run(
            ['claude', 'plugin', 'marketplace', 'add', 'qf-studio/navigator'],
            capture_output=True,
            text=True,
            timeout=30
        )

        if add_result.returncode != 0:
            return {
                'success': False,
                'error': f'Marketplace add failed: {add_result.stderr}',
                'method': 'reinstall'
            }

        # Wait a moment
        time.sleep(2)

        # Install
        install_result = subprocess.run(
            ['claude', 'plugin', 'install', 'navigator'],
            capture_output=True,
            text=True,
            timeout=60
        )

        success = install_result.returncode == 0

        return {
            'success': success,
            'output': install_result.stdout,
            'error': install_result.stderr if not success else None,
            'method': 'reinstall'
        }
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'error': 'Reinstall timed out',
            'method': 'reinstall'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'method': 'reinstall'
        }


def update_with_retry(target_version: str = None) -> Dict:
    """
    Update Navigator plugin with automatic retry on failure.

    Args:
        target_version: Optional specific version to install

    Returns:
        Dict with final update status
    """
    report = {
        'attempts': [],
        'final_success': False,
        'target_version': target_version
    }

    # Attempt 1: Normal update
    print("Attempting plugin update...", file=sys.stderr)
    attempt1 = update_plugin_via_claude()
    report['attempts'].append(attempt1)

    if attempt1['success']:
        report['final_success'] = True
        return report

    # Attempt 2: Reinstall
    print("Update failed. Attempting reinstall...", file=sys.stderr)
    time.sleep(2)

    attempt2 = reinstall_plugin()
    report['attempts'].append(attempt2)

    if attempt2['success']:
        report['final_success'] = True
        return report

    # Both failed
    return report


def get_post_update_instructions(success: bool, method: str) -> str:
    """Generate post-update instructions."""
    if success:
        return """
✅ Update Successful

Next steps:
1. Restart Claude Code to reload skills
2. Verify version: /plugin list
3. Update project CLAUDE.md: "Update my CLAUDE.md to latest Navigator version"
4. Try new features (if any)
"""
    else:
        return f"""
❌ Update Failed (method: {method})

Troubleshooting:
1. Restart Claude Code
2. Try manual update:
   /plugin uninstall navigator
   /plugin marketplace add qf-studio/navigator
   /plugin install navigator

3. Check internet connection
4. Report issue: https://github.com/qf-studio/navigator/issues
"""


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description='Update Navigator plugin')
    parser.add_argument('--target-version', help='Target version to install', default=None)
    args = parser.parse_args()

    # Run update with retry
    report = update_with_retry(args.target_version)

    # Add instructions
    final_attempt = report['attempts'][-1] if report['attempts'] else {}
    method = final_attempt.get('method', 'unknown')
    report['instructions'] = get_post_update_instructions(report['final_success'], method)

    # Output as JSON
    print(json.dumps(report, indent=2))

    # Exit code
    sys.exit(0 if report['final_success'] else 1)


if __name__ == '__main__':
    main()
