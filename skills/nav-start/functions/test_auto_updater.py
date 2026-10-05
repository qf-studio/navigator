#!/usr/bin/env python3
"""Tests for auto_updater.py"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

# Import module for direct testing
sys.path.insert(0, str(Path(__file__).parent))
import auto_updater
from auto_updater import (
    auto_update,
    compare_versions,
    detect_version_drift,
    get_current_version,
    get_installed_plugin_version,
    get_latest_version_from_github,
    get_running_plugin_version,
    reinstall_plugin,
)


class TestCompareVersions(unittest.TestCase):
    """Tests for semantic version comparison.

    Convention: -1 if current < latest, 0 if equal, 1 if current > latest.
    """

    def test_current_older_negative(self):
        self.assertEqual(compare_versions("6.15.5", "6.15.6"), -1)

    def test_equal_zero(self):
        self.assertEqual(compare_versions("6.15.6", "6.15.6"), 0)

    def test_current_newer_positive(self):
        self.assertEqual(compare_versions("6.16.0", "6.15.6"), 1)

    def test_major_difference(self):
        self.assertEqual(compare_versions("5.0.0", "6.0.0"), -1)
        self.assertEqual(compare_versions("7.0.0", "6.0.0"), 1)

    def test_uneven_length_equal(self):
        """'6.15' is padded to '6.15.0' and equals '6.15.0'."""
        self.assertEqual(compare_versions("6.15", "6.15.0"), 0)

    def test_uneven_length_older(self):
        """'6.15' (-> 6.15.0) is older than '6.15.2'."""
        self.assertEqual(compare_versions("6.15", "6.15.2"), -1)

    def test_uneven_length_newer(self):
        """'6.16' (-> 6.16.0) is newer than '6.15.9'."""
        self.assertEqual(compare_versions("6.16", "6.15.9"), 1)


class TestGetCurrentVersion(unittest.TestCase):
    """Tests for parsing version out of `claude plugin list` output."""

    PLUGIN_LIST_OUTPUT = (
        "Installed plugins:\n"
        "❯ navigator@navigator-marketplace\n"
        "  Version: 6.15.6\n"
        "  Scope: user\n"
        "  Status: ✔ enabled\n"
    )

    NO_NAVIGATOR_OUTPUT = (
        "Installed plugins:\n"
        "❯ other-plugin@some-marketplace\n"
        "  Version: 1.2.3\n"
        "  Scope: user\n"
    )

    @patch("auto_updater.subprocess.run")
    def test_parses_navigator_version(self, mock_run):
        mock_run.return_value = SimpleNamespace(
            stdout=self.PLUGIN_LIST_OUTPUT, returncode=0, stderr=""
        )
        self.assertEqual(get_current_version(), "6.15.6")

    @patch("auto_updater.subprocess.run")
    def test_returns_none_without_navigator(self, mock_run):
        mock_run.return_value = SimpleNamespace(
            stdout=self.NO_NAVIGATOR_OUTPUT, returncode=0, stderr=""
        )
        self.assertIsNone(get_current_version())

    @patch("auto_updater.subprocess.run")
    def test_handles_version_prefix_v(self, mock_run):
        """A leading 'v' on the version is stripped by the regex."""
        out = (
            "❯ navigator@navigator-marketplace\n"
            "  Version: v6.10.1\n"
        )
        mock_run.return_value = SimpleNamespace(stdout=out, returncode=0, stderr="")
        self.assertEqual(get_current_version(), "6.10.1")


class TestReinstallPlugin(unittest.TestCase):
    """Tests for the uninstall/add/install fallback flow.

    A failed uninstall must abort before install runs (no inconsistent
    mid-state where the plugin is removed but never reinstalled).
    """

    @patch("auto_updater.time.sleep", return_value=None)
    @patch("auto_updater.subprocess.run")
    def test_failed_uninstall_aborts_before_install(self, mock_run, _mock_sleep):
        """First call (uninstall) fails -> install is never invoked."""

        def fake_run(cmd, *args, **kwargs):
            # cmd is the argv list, e.g. ['claude', 'plugin', 'uninstall', ...]
            if "uninstall" in cmd:
                return SimpleNamespace(returncode=1, stdout="", stderr="boom")
            # Any other call would indicate the flow wrongly continued.
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        mock_run.side_effect = fake_run

        result = reinstall_plugin()

        self.assertFalse(result["success"])
        self.assertIn("Uninstall failed", result["error"])
        self.assertEqual(result["method"], "reinstall")

        # Only the uninstall call should have happened.
        self.assertEqual(mock_run.call_count, 1)
        invoked_cmds = [call.args[0] for call in mock_run.call_args_list]
        # install must NOT appear in any invoked command.
        self.assertFalse(
            any("install" in cmd and "uninstall" not in cmd for cmd in invoked_cmds),
            "install was invoked despite a failed uninstall",
        )

    @patch("auto_updater.time.sleep", return_value=None)
    @patch("auto_updater.subprocess.run")
    def test_failed_install_reported(self, mock_run, _mock_sleep):
        """Uninstall + add succeed but install fails -> success False reported."""

        def fake_run(cmd, *args, **kwargs):
            if "uninstall" in cmd:
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if "add" in cmd:
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if "install" in cmd:
                return SimpleNamespace(returncode=1, stdout="", stderr="install boom")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        mock_run.side_effect = fake_run

        result = reinstall_plugin()

        self.assertFalse(result["success"])
        self.assertEqual(result["method"], "reinstall")
        # All three steps run: uninstall, add, install.
        self.assertEqual(mock_run.call_count, 3)

    @patch("auto_updater.time.sleep", return_value=None)
    @patch("auto_updater.subprocess.run")
    def test_successful_reinstall(self, mock_run, _mock_sleep):
        """All three steps succeed -> success True."""
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="ok", stderr="")

        result = reinstall_plugin()

        self.assertTrue(result["success"])
        self.assertEqual(result["method"], "reinstall")
        self.assertEqual(mock_run.call_count, 3)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self._payload).encode()


def _release(tag, prerelease=False, draft=False):
    return {
        "tag_name": tag,
        "prerelease": prerelease,
        "draft": draft,
        "html_url": f"https://github.com/qf-studio/navigator/releases/{tag}",
        "published_at": "2026-07-01T00:00:00Z",
    }


class GetLatestVersionFromGithubTest(unittest.TestCase):
    """Guards GH-25: same malformed-release validation as version_detector.py."""

    def _mock_urlopen(self, releases, plugin_versions):
        def fake_urlopen(req, timeout=10):
            url = req.full_url if hasattr(req, "full_url") else req
            if "api.github.com" in url:
                return _FakeResponse(releases)
            tag = url.split("/")[-3]
            if tag not in plugin_versions:
                raise OSError("network unreachable")
            return _FakeResponse({"version": plugin_versions[tag]})

        return patch.object(auto_updater.request, "urlopen", side_effect=fake_urlopen)

    def test_matching_release_offered(self):
        with self._mock_urlopen([_release("v6.16.0")], {"v6.16.0": "6.16.0"}):
            result = get_latest_version_from_github()
        self.assertEqual(result["version"], "6.16.0")

    def test_mismatched_release_skipped(self):
        releases = [_release("v6.17.0"), _release("v6.16.0")]
        with self._mock_urlopen(
            releases, {"v6.17.0": "6.16.9", "v6.16.0": "6.16.0"}
        ):
            result = get_latest_version_from_github()
        self.assertEqual(result["version"], "6.16.0")

    def test_validation_failure_fails_open(self):
        with self._mock_urlopen([_release("v6.16.0")], {}):
            result = get_latest_version_from_github()
        self.assertEqual(result["version"], "6.16.0")


class GetInstalledPluginVersionTest(unittest.TestCase):
    def test_resolves_highest_version_from_cache(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            base = home / ".claude" / "plugins" / "cache" / "navigator-marketplace" / "navigator"
            for v in ["6.9.0", "6.16.0"]:
                plugin_dir = base / v / ".claude-plugin"
                plugin_dir.mkdir(parents=True)
                (plugin_dir / "plugin.json").write_text(json.dumps({"version": v}))
            with patch.object(auto_updater.Path, "home", lambda: home):
                self.assertEqual(get_installed_plugin_version(), "6.16.0")


class DetectVersionDriftTest(unittest.TestCase):
    """TASK-81: `--check-drift` runs from inside the session-start hooks (mod and Python).
    It must resolve the plugin version from this script's own manifest, then the plugin
    cache, and never spawn `claude plugin list` - that call misreported the version from a
    hook on 2026-09-06/09 and its 10 s timeout does not fit the 4 s hook budget."""

    def _config(self, version):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({"version": version}, f)
        f.close()
        return f.name

    def _no_subprocess(self):
        def boom(*_a, **_k):
            raise AssertionError("drift check spawned a subprocess")
        return patch.object(auto_updater.subprocess, "run", boom)

    def test_running_version_comes_from_own_manifest(self):
        manifest = Path(auto_updater.__file__).resolve().parents[3] / ".claude-plugin" / "plugin.json"
        self.assertEqual(
            get_running_plugin_version(),
            json.loads(manifest.read_text())["version"],
        )

    def test_drift_uses_manifest_without_any_subprocess(self):
        with self._no_subprocess(), \
                patch.object(auto_updater, "get_running_plugin_version", lambda: "8.2.0"):
            result = detect_version_drift(self._config("8.1.0"))
        self.assertTrue(result["has_drift"])
        self.assertEqual(result["plugin_version"], "8.2.0")
        self.assertEqual(result["project_version"], "8.1.0")

    def test_drift_falls_back_to_cache_when_manifest_missing(self):
        with self._no_subprocess(), \
                patch.object(auto_updater, "get_running_plugin_version", lambda: None), \
                patch.object(auto_updater, "get_installed_plugin_version", lambda: "8.1.1"):
            result = detect_version_drift(self._config("8.1.1"))
        self.assertFalse(result["has_drift"])

    def test_no_version_source_is_not_drift(self):
        with self._no_subprocess(), \
                patch.object(auto_updater, "get_running_plugin_version", lambda: None), \
                patch.object(auto_updater, "get_installed_plugin_version", lambda: None):
            result = detect_version_drift(self._config("8.1.1"))
        self.assertFalse(result["has_drift"])

    def test_drift_source_never_references_the_cli_reader(self):
        """Static guard: a future edit that reintroduces get_current_version() into the
        drift path fails here, not in a session six releases later."""
        import inspect
        self.assertNotIn("get_current_version", inspect.getsource(detect_version_drift))


class AutoUpdatePostUpdateVerificationTest(unittest.TestCase):
    """Guards GH-25: `claude plugin update` reporting success is not enough -
    the installed version must actually match the target, or this is a
    phantom update from a malformed release."""

    def _write_config(self, extra_auto_update=None):
        config = {
            "auto_update": {"enabled": True, **(extra_auto_update or {})}
        }
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        json.dump(config, f)
        f.close()
        return f.name

    def test_version_mismatch_after_update_reports_failed(self):
        config_path = self._write_config()
        try:
            with patch.object(auto_updater, "get_current_version", return_value="6.15.0"), \
                 patch.object(
                     auto_updater, "get_latest_version_from_github",
                     return_value={"version": "6.16.0"}
                 ), \
                 patch.object(
                     auto_updater, "update_plugin_via_claude",
                     return_value={"success": True, "method": "update"}
                 ), \
                 patch.object(
                     auto_updater, "get_installed_plugin_version", return_value="6.15.0"
                 ):
                result = auto_update(config_path)

            self.assertEqual(result["status"], "failed")
            self.assertIn("malformed release", result["message"])

            with open(config_path) as f:
                saved = json.load(f)
            self.assertIn("6.16.0", saved["auto_update"]["ignored_releases"])
        finally:
            Path(config_path).unlink()

    def test_version_match_after_update_reports_updated(self):
        config_path = self._write_config()
        try:
            with patch.object(auto_updater, "get_current_version", return_value="6.15.0"), \
                 patch.object(
                     auto_updater, "get_latest_version_from_github",
                     return_value={"version": "6.16.0"}
                 ), \
                 patch.object(
                     auto_updater, "update_plugin_via_claude",
                     return_value={"success": True, "method": "update"}
                 ), \
                 patch.object(
                     auto_updater, "get_installed_plugin_version", return_value="6.16.0"
                 ), \
                 patch.object(
                     auto_updater, "sync_project_config",
                     return_value={"success": True, "changes": []}
                 ):
                result = auto_update(config_path)

            self.assertEqual(result["status"], "updated")
        finally:
            Path(config_path).unlink()

    def test_ignored_release_is_skipped_without_reattempting_update(self):
        config_path = self._write_config({"ignored_releases": ["6.16.0"]})
        try:
            with patch.object(auto_updater, "get_current_version", return_value="6.15.0"), \
                 patch.object(
                     auto_updater, "get_latest_version_from_github",
                     return_value={"version": "6.16.0"}
                 ), \
                 patch.object(auto_updater, "update_plugin_via_claude") as mock_update:
                result = auto_update(config_path)

            self.assertEqual(result["status"], "skipped")
            mock_update.assert_not_called()
        finally:
            Path(config_path).unlink()


if __name__ == "__main__":
    unittest.main(verbosity=2)
