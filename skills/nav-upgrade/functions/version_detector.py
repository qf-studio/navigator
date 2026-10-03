#!/usr/bin/env python3
"""
Navigator Version Detector

Detects current Navigator version and checks for updates from GitHub releases.

Usage:
    python version_detector.py
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional
from urllib import request

REPO = 'qf-studio/navigator'


def get_current_version() -> Optional[str]:
    """
    Get currently installed Navigator version from `claude plugin list`.

    `claude plugin list` prints a multi-line block per plugin:
        ❯ navigator@navigator-marketplace
          Version: 6.15.6
          Scope: user
          Status: ✔ enabled

    The plugin name and version sit on separate lines, so a single-line
    regex never matched the version. Scan forward from the navigator entry
    until a Version: line appears, resetting at the next plugin's `❯` row.

    Returns:
        Version string (e.g., "6.15.6") or None if not found
    """
    try:
        result = subprocess.run(
            ['claude', 'plugin', 'list'],
            capture_output=True,
            text=True,
            timeout=10
        )

        in_navigator_block = False
        for line in result.stdout.split('\n'):
            if 'navigator' in line.lower() and '@' in line:
                in_navigator_block = True
                continue
            if in_navigator_block:
                match = re.search(r'Version:\s*v?(\d+\.\d+\.\d+)', line)
                if match:
                    return match.group(1)
                if line.strip().startswith('❯'):
                    in_navigator_block = False

        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return None


def get_plugin_json_version() -> Optional[str]:
    """
    Fallback: read the version from the highest-versioned cached plugin install.

    Claude Code installs plugins under a version-keyed cache layout:
        ~/.claude/plugins/cache/<marketplace>/navigator/<version>/.claude-plugin/plugin.json

    The previous static path list (~/.config/claude/..., flat
    ~/.claude/plugins/navigator/...) never matched this layout, so the
    fallback always returned None. Glob the cache and pick the newest
    version directory (mirrors release_validator._resolve_plugin_dir_for_test).

    Returns:
        Version string or None
    """
    cache_root = Path.home() / '.claude' / 'plugins' / 'cache'
    candidates = list(cache_root.glob('*/navigator/*/.claude-plugin/plugin.json'))

    def _version_key(plugin_json: Path):
        # The version directory is two levels above .claude-plugin/plugin.json.
        version_dir = plugin_json.parent.parent.name
        return [int(x) for x in re.findall(r'\d+', version_dir)]

    for plugin_json in sorted(candidates, key=_version_key, reverse=True):
        try:
            with open(plugin_json, 'r') as f:
                data = json.load(f)
                version = data.get('version')
                if version:
                    return version
        except (json.JSONDecodeError, OSError):
            continue

    return None


def fetch_candidate_releases() -> List[Dict]:
    """
    Fetch recent releases from GitHub, newest first, excluding drafts/prereleases.

    Raises on network/API failure - caller decides how to handle it.
    """
    url = f'https://api.github.com/repos/{REPO}/releases?per_page=10'
    req = request.Request(url)
    req.add_header('User-Agent', 'Navigator-Version-Detector')

    with request.urlopen(req, timeout=10) as response:
        data = json.load(response)

    return [r for r in data if not r.get('draft') and not r.get('prerelease')]


def validate_release_tag(tag_name: str) -> Dict:
    """
    Validate that a release tag's plugin.json version matches the tag itself.

    A release published without a matching plugin.json version bump (bad
    automation, or a human tagging before the version sync) would otherwise
    be offered as an update that never actually changes the installed
    version, causing a phantom-update loop every session.

    Returns:
        Dict with:
        - valid: True if plugin.json version matches the tag, or if the
          validation fetch itself failed (fail-open - don't block updates
          on a flaky/offline network)
        - plugin_version: the version found in plugin.json, or None
        - network_error: True if the validation fetch failed
    """
    expected_version = tag_name.lstrip('v')
    url = f'https://raw.githubusercontent.com/{REPO}/{tag_name}/.claude-plugin/plugin.json'

    try:
        req = request.Request(url)
        req.add_header('User-Agent', 'Navigator-Version-Detector')

        with request.urlopen(req, timeout=10) as response:
            data = json.load(response)
            plugin_version = data.get('version')
    except Exception:
        return {'valid': True, 'plugin_version': None, 'network_error': True}

    return {
        'valid': plugin_version == expected_version,
        'plugin_version': plugin_version,
        'network_error': False,
    }


def get_latest_version_from_github() -> Dict:
    """
    Get latest valid Navigator version from GitHub releases API.

    Walks releases newest-first and skips any whose plugin.json version
    doesn't match its tag (malformed release) so it's never offered as an
    update. A validation fetch failure fails open - that candidate is
    offered as-is rather than blocking on network flakiness.

    Returns:
        Dict with version, release_url, and changes
    """
    try:
        candidates = fetch_candidate_releases()
    except Exception as e:
        return {
            'version': None,
            'error': str(e)
        }

    for release in candidates:
        tag_name = release.get('tag_name', '')
        if not tag_name:
            continue

        validation = validate_release_tag(tag_name)
        if not validation['valid']:
            print(
                f"release {tag_name} has plugin.json {validation['plugin_version']} "
                "— malformed release, ignoring",
                file=sys.stderr
            )
            continue

        # Extract version from tag_name (e.g., "v3.3.0" → "3.3.0")
        version = tag_name.lstrip('v')

        # Parse release notes for key changes
        body = release.get('body', '')
        changes = parse_release_notes(body)

        return {
            'version': version,
            'release_url': release.get('html_url', ''),
            'release_date': release.get('published_at', '').split('T')[0],
            'changes': changes
        }

    return {
        'version': None,
        'error': 'No valid release found (all candidates failed plugin.json validation)'
    }


def parse_release_notes(body: str) -> Dict:
    """
    Parse release notes to extract key changes.

    Args:
        body: Release notes markdown

    Returns:
        Dict with new_skills, updated_skills, new_features, breaking_changes
    """
    changes = {
        'new_skills': [],
        'updated_skills': [],
        'new_features': [],
        'breaking_changes': []
    }

    # Extract new skills
    skill_pattern = r'-\s+\*\*(\w+-[\w-]+)\*\*:.*\(NEW\)'
    for match in re.finditer(skill_pattern, body):
        changes['new_skills'].append(match.group(1))

    # Extract features from "What's New" section
    features_section = re.search(r'##\s+.*What.*s New(.*?)(?=##|\Z)', body, re.DOTALL | re.IGNORECASE)
    if features_section:
        # Find bullet points
        for line in features_section.group(1).split('\n'):
            if line.strip().startswith('-') or line.strip().startswith('*'):
                feature = line.strip().lstrip('-*').strip()
                if feature and len(feature) < 100:  # Reasonable feature description
                    changes['new_features'].append(feature)

    # Check for breaking changes
    if 'breaking change' in body.lower() or '⚠️' in body:
        breaking_section = re.search(r'##\s+.*Breaking.*Changes(.*?)(?=##|\Z)', body, re.DOTALL | re.IGNORECASE)
        if breaking_section:
            for line in breaking_section.group(1).split('\n'):
                if line.strip().startswith('-') or line.strip().startswith('*'):
                    change = line.strip().lstrip('-*').strip()
                    if change:
                        changes['breaking_changes'].append(change)

    return changes


def compare_versions(current: str, latest: str) -> int:
    """
    Compare two semantic versions.

    Args:
        current: Current version (e.g., "3.2.0")
        latest: Latest version (e.g., "3.3.0")

    Returns:
        -1 if current < latest (update available)
         0 if current == latest (up to date)
         1 if current > latest (ahead of latest, e.g., dev version)
    """
    try:
        current_parts = [int(x) for x in current.split('.')]
        latest_parts = [int(x) for x in latest.split('.')]

        # Pad to same length
        while len(current_parts) < len(latest_parts):
            current_parts.append(0)
        while len(latest_parts) < len(current_parts):
            latest_parts.append(0)

        # Compare
        for c, l in zip(current_parts, latest_parts):
            if c < l:
                return -1
            elif c > l:
                return 1

        return 0
    except (ValueError, AttributeError):
        return 0  # Can't compare, assume equal


def detect_version() -> Dict:
    """
    Detect current and latest Navigator versions.

    Returns:
        Complete version detection report
    """
    # Get current version
    current_version = get_current_version()

    if not current_version:
        # Fallback to plugin.json
        current_version = get_plugin_json_version()

    # Get latest version from GitHub
    latest_info = get_latest_version_from_github()
    latest_version = latest_info.get('version')

    # Determine if update available
    update_available = False
    if current_version and latest_version:
        comparison = compare_versions(current_version, latest_version)
        update_available = (comparison == -1)

    # Build report
    report = {
        'current_version': current_version,
        'latest_version': latest_version,
        'update_available': update_available,
        'release_url': latest_info.get('release_url', ''),
        'release_date': latest_info.get('release_date', ''),
        'changes': latest_info.get('changes', {}),
        'error': latest_info.get('error'),
        'recommendation': get_recommendation(current_version, latest_version, update_available)
    }

    return report


def get_recommendation(current: Optional[str], latest: Optional[str], update_available: bool) -> str:
    """Generate recommendation based on version status."""
    if not current:
        return "Navigator not detected. Install: /plugin marketplace add qf-studio/navigator && /plugin install navigator"

    if not latest:
        return "Could not check for updates. Try again later or check GitHub releases manually."

    if update_available:
        return f"Update recommended: v{current} → v{latest}. Run: /plugin update navigator"

    return f"You're on the latest version (v{current}). No update needed."


def main():
    """CLI entry point."""
    report = detect_version()

    # Output as JSON
    print(json.dumps(report, indent=2))

    # Exit with code
    # 0 = up to date
    # 1 = update available
    # 2 = error
    if report.get('error'):
        sys.exit(2)
    elif report.get('update_available'):
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
