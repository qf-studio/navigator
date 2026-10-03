#!/usr/bin/env python3
"""Unit tests for version_detector's current-version parsing and cache fallback.

Guards two MED findings from audit wf_0dc1b9ce-7d8:
  - get_current_version() parsed a single line of `claude plugin list`, but the
    name and version live on separate lines, so it never matched.
  - get_plugin_json_version() used static install paths that never matched the
    version-keyed cache layout, so the fallback always returned None.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))

import version_detector as vd  # noqa: E402


# Real-shape `claude plugin list` output: name and version on separate lines.
PLUGIN_LIST_FIXTURE = """\
Installed plugins:

❯ navigator@navigator-marketplace
  Version: 6.15.6
  Scope: user
  Status: ✔ enabled

❯ some-other-plugin@other-marketplace
  Version: 1.2.3
  Scope: user
  Status: ✔ enabled
"""


class GetCurrentVersionTest(unittest.TestCase):
    def _run_with_stdout(self, stdout):
        fake = mock.Mock(stdout=stdout, returncode=0)
        with mock.patch.object(vd.subprocess, "run", return_value=fake):
            return vd.get_current_version()

    def test_parses_version_from_multiline_block(self):
        self.assertEqual(self._run_with_stdout(PLUGIN_LIST_FIXTURE), "6.15.6")

    def test_does_not_grab_following_plugin_version(self):
        # The navigator block's version must win, not the next plugin's 1.2.3.
        self.assertEqual(self._run_with_stdout(PLUGIN_LIST_FIXTURE), "6.15.6")

    def test_missing_navigator_returns_none(self):
        other = "❯ other-plugin@x\n  Version: 1.0.0\n  Scope: user\n"
        self.assertIsNone(self._run_with_stdout(other))

    def test_claude_not_installed_returns_none(self):
        with mock.patch.object(vd.subprocess, "run", side_effect=FileNotFoundError):
            self.assertIsNone(vd.get_current_version())


class GetPluginJsonVersionTest(unittest.TestCase):
    def _build_cache(self, home: Path, versions):
        base = home / ".claude" / "plugins" / "cache" / "navigator-marketplace" / "navigator"
        for v in versions:
            plugin_dir = base / v / ".claude-plugin"
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "plugin.json").write_text(json.dumps({"version": v}))

    def test_resolves_highest_version_from_cache(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            # 6.10.0 must beat 6.9.0 numerically (not lexically).
            self._build_cache(home, ["6.9.0", "6.10.0", "6.15.6"])
            with mock.patch.object(vd.Path, "home", lambda: home):
                self.assertEqual(vd.get_plugin_json_version(), "6.15.6")

    def test_returns_none_when_cache_absent(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            with mock.patch.object(vd.Path, "home", lambda: home):
                self.assertIsNone(vd.get_plugin_json_version())


def _release(tag, prerelease=False, draft=False, body=""):
    return {
        "tag_name": tag,
        "prerelease": prerelease,
        "draft": draft,
        "html_url": f"https://github.com/qf-studio/navigator/releases/{tag}",
        "published_at": "2026-07-01T00:00:00Z",
        "body": body,
    }


class _FakeResponse:
    """Minimal context-manager stand-in for urlopen()'s response object."""

    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self._payload).encode()


class GetLatestVersionFromGithubTest(unittest.TestCase):
    """Guards GH-25: a release tag whose plugin.json disagrees with the tag
    must never be offered as an update (phantom-update loop otherwise)."""

    def _mock_urlopen(self, releases, plugin_versions):
        """releases: list of release dicts from the /releases endpoint.
        plugin_versions: dict tag -> version string returned by the raw
        plugin.json fetch for that tag (missing tag -> raises, simulating a
        network failure on the validation fetch only).
        """

        def fake_urlopen(req, timeout=10):
            url = req.full_url if hasattr(req, "full_url") else req
            if "api.github.com" in url:
                return _FakeResponse(releases)
            # raw.githubusercontent.com/<repo>/<tag>/.claude-plugin/plugin.json
            tag = url.split("/")[-3]
            if tag not in plugin_versions:
                raise OSError("network unreachable")
            return _FakeResponse({"version": plugin_versions[tag]})

        return mock.patch.object(vd.request, "urlopen", side_effect=fake_urlopen)

    def test_matching_release_is_offered(self):
        releases = [_release("v6.16.0")]
        with self._mock_urlopen(releases, {"v6.16.0": "6.16.0"}):
            result = vd.get_latest_version_from_github()
        self.assertEqual(result["version"], "6.16.0")
        self.assertIsNone(result.get("error"))

    def test_mismatched_release_skipped_next_considered(self):
        releases = [_release("v6.17.0"), _release("v6.16.0")]
        with self._mock_urlopen(
            releases, {"v6.17.0": "6.16.9", "v6.16.0": "6.16.0"}
        ):
            result = vd.get_latest_version_from_github()
        self.assertEqual(result["version"], "6.16.0")

    def test_validation_fetch_error_fails_open(self):
        """No plugin_versions entry for the tag -> validation fetch raises,
        but the release must still be offered (fail-open)."""
        releases = [_release("v6.16.0")]
        with self._mock_urlopen(releases, {}):
            result = vd.get_latest_version_from_github()
        self.assertEqual(result["version"], "6.16.0")

    def test_prerelease_excluded(self):
        releases = [_release("v6.17.0-beta.1", prerelease=True), _release("v6.16.0")]
        with self._mock_urlopen(
            releases, {"v6.17.0-beta.1": "6.17.0-beta.1", "v6.16.0": "6.16.0"}
        ):
            result = vd.get_latest_version_from_github()
        self.assertEqual(result["version"], "6.16.0")

    def test_releases_endpoint_failure_returns_error(self):
        with mock.patch.object(
            vd.request, "urlopen", side_effect=OSError("network down")
        ):
            result = vd.get_latest_version_from_github()
        self.assertIsNone(result["version"])
        self.assertIn("network down", result["error"])

    def test_all_candidates_malformed_returns_error(self):
        releases = [_release("v6.16.0")]
        with self._mock_urlopen(releases, {"v6.16.0": "6.15.9"}):
            result = vd.get_latest_version_from_github()
        self.assertIsNone(result["version"])


class ValidateReleaseTagTest(unittest.TestCase):
    def test_matching_version_is_valid(self):
        def fake_urlopen(req, timeout=10):
            return _FakeResponse({"version": "6.16.0"})

        with mock.patch.object(vd.request, "urlopen", side_effect=fake_urlopen):
            result = vd.validate_release_tag("v6.16.0")
        self.assertTrue(result["valid"])
        self.assertFalse(result["network_error"])

    def test_mismatched_version_is_invalid(self):
        def fake_urlopen(req, timeout=10):
            return _FakeResponse({"version": "6.15.9"})

        with mock.patch.object(vd.request, "urlopen", side_effect=fake_urlopen):
            result = vd.validate_release_tag("v6.16.0")
        self.assertFalse(result["valid"])
        self.assertEqual(result["plugin_version"], "6.15.9")

    def test_network_failure_fails_open(self):
        with mock.patch.object(vd.request, "urlopen", side_effect=OSError("boom")):
            result = vd.validate_release_tag("v6.16.0")
        self.assertTrue(result["valid"])
        self.assertTrue(result["network_error"])


if __name__ == "__main__":
    unittest.main()
