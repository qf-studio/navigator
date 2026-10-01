#!/usr/bin/env python3
"""
Tests for config_migrator.

Focus areas (regression coverage for issue #7):
- CURRENT_VERSION is loaded from .claude-plugin/plugin.json (not hardcoded).
- Migration is direction-aware: configs newer than CURRENT_VERSION are NOT
  downgraded.
- Older configs still receive missing sections and a version bump.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Make sibling module importable when run via `python3 -m unittest`.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config_migrator  # noqa: E402
from config_migrator import (  # noqa: E402
    _read_plugin_version,
    migrate_config,
    version_less_than,
)


def _write_config(tmpdir: Path, payload: dict) -> Path:
    path = tmpdir / ".nav-config.json"
    path.write_text(json.dumps(payload))
    return path


class ReadPluginVersionTests(unittest.TestCase):
    def test_reads_version_from_plugin_json(self):
        repo_root = Path(__file__).resolve().parents[3]
        plugin_json = repo_root / ".claude-plugin" / "plugin.json"
        self.assertTrue(plugin_json.is_file(), f"missing {plugin_json}")

        expected = json.loads(plugin_json.read_text())["version"]
        self.assertEqual(_read_plugin_version(), expected)

    def test_module_current_version_matches_plugin_json(self):
        repo_root = Path(__file__).resolve().parents[3]
        plugin_json = repo_root / ".claude-plugin" / "plugin.json"
        expected = json.loads(plugin_json.read_text())["version"]
        self.assertEqual(config_migrator.CURRENT_VERSION, expected)


class MigrateConfigDirectionTests(unittest.TestCase):
    def test_newer_config_is_not_downgraded(self):
        # Simulate a user whose installed config is ahead of the plugin's
        # CURRENT_VERSION. This is the bug from issue #7: previously the
        # `!=` comparison rewrote `version` to the (stale) CURRENT_VERSION.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            future = "999.0.0"
            cfg_path = _write_config(tmp, {"version": future})

            result = migrate_config(str(cfg_path))

            self.assertTrue(result["success"])
            # No version-update change should have been recorded.
            version_updates = [
                c for c in result["changes"]
                if c.get("action") == "updated" and c.get("key") == "version"
            ]
            self.assertEqual(version_updates, [])

            # On-disk file must still record the newer version.
            on_disk = json.loads(cfg_path.read_text())
            self.assertEqual(on_disk["version"], future)
            self.assertEqual(result["new_version"], future)

    def test_equal_version_is_noop_for_version_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            cfg_path = _write_config(
                tmp, {"version": config_migrator.CURRENT_VERSION}
            )

            result = migrate_config(str(cfg_path))

            self.assertTrue(result["success"])
            version_updates = [
                c for c in result["changes"]
                if c.get("action") == "updated" and c.get("key") == "version"
            ]
            self.assertEqual(version_updates, [])

    def test_older_config_is_upgraded(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            cfg_path = _write_config(tmp, {"version": "1.0.0"})

            result = migrate_config(str(cfg_path))

            self.assertTrue(result["success"])
            version_updates = [
                c for c in result["changes"]
                if c.get("action") == "updated" and c.get("key") == "version"
            ]
            self.assertEqual(len(version_updates), 1)
            self.assertEqual(version_updates[0]["old"], "1.0.0")
            self.assertEqual(
                version_updates[0]["new"], config_migrator.CURRENT_VERSION
            )

            on_disk = json.loads(cfg_path.read_text())
            self.assertEqual(
                on_disk["version"], config_migrator.CURRENT_VERSION
            )

    def test_older_config_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            cfg_path = _write_config(tmp, {"version": "1.0.0"})

            result = migrate_config(str(cfg_path), dry_run=True)

            self.assertTrue(result["success"])
            self.assertTrue(any(
                c.get("action") == "updated" and c.get("key") == "version"
                for c in result["changes"]
            ))
            # File untouched.
            on_disk = json.loads(cfg_path.read_text())
            self.assertEqual(on_disk, {"version": "1.0.0"})


class VersionLessThanSanityTests(unittest.TestCase):
    def test_basic_orderings(self):
        self.assertTrue(version_less_than("1.0.0", "2.0.0"))
        self.assertTrue(version_less_than("5.7.0", "6.12.0"))
        self.assertFalse(version_less_than("6.12.0", "5.7.0"))
        self.assertFalse(version_less_than("6.12.0", "6.12.0"))


# v7 hooks-runtime blocks (TASK-63 Phase 1) and the Tier-1 whitelist rule ids
# (TASK-62). Shapes are contracted to hooks/nav_hook_lib/config.py DEFAULTS.
V7_BLOCKS = {
    "dispatcher",
    "tier1",
    "stop_completion",
    "jit_memory",
    "subagent_context",
    "failure_diagnosis",
    "config_guard",
    "setup_hook",
}

TIER1_RULE_IDS = {
    "nav_stats",
    "show_features",
    "list_markers",
    "graph_health",
    "nav_version",
}

# Every feature / hook block VERSION_CONFIGS knows how to seed, regardless of
# introduction version. Keep in sync with config_migrator.VERSION_CONFIGS.
ALL_FEATURE_BLOCKS = {
    "deep_research",  # 7.3.0 (TASK-74)
    "tom_features",
    "loop_mode",
    "simplification",
    "auto_update",
    "task_mode",
    "knowledge_graph",
    "session_start_hook",
    "compact_hook",
    "task_graph_sync_hook",
    "workflow_state_hook",
    "profile_sync_hook",
    "workflow_enforcer_hook",
    "read_guard_hook",
} | V7_BLOCKS

# Blocks introduced strictly after v5.3.0 — the set a real v5.3.0 user is
# missing and should receive on upgrade. tom_features (5.0.0) and loop_mode
# (5.1.0) predate 5.3.0, so that user already has them and they must NOT be
# re-seeded (introduction-version contract).
POST_5_3_0_BLOCKS = ALL_FEATURE_BLOCKS - {"tom_features", "loop_mode"}


class FeatureBlockSeedingTests(unittest.TestCase):
    """wp9/TASK-52: VERSION_CONFIGS seeds every v5.x/v6.x feature + hook block."""

    def test_version_configs_cover_every_known_block(self):
        # Guards against a block being added to the live config but forgotten
        # in the migrator (the original drift this work-package fixed).
        seeded = {
            key
            for blocks in config_migrator.VERSION_CONFIGS.values()
            for key in blocks
        }
        self.assertEqual(seeded, ALL_FEATURE_BLOCKS)

    def test_pre_feature_config_seeds_all_blocks(self):
        # A config older than every feature block receives all of them.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            cfg_path = _write_config(tmp, {"version": "4.0.0"})

            result = migrate_config(str(cfg_path))

            self.assertTrue(result["success"])
            added = {
                c["key"] for c in result["changes"] if c.get("action") == "added"
            }
            self.assertEqual(added, ALL_FEATURE_BLOCKS)

            on_disk = json.loads(cfg_path.read_text())
            for block in ALL_FEATURE_BLOCKS:
                self.assertIn(block, on_disk)
            # Default shapes are copied verbatim from the live config.
            self.assertEqual(on_disk["read_guard_hook"]["escalate_threshold"], 5)
            self.assertEqual(on_disk["session_start_hook"]["char_budget"], 9500)
            self.assertFalse(on_disk["loop_mode"]["enabled"])

    def test_v5_3_0_config_seeds_only_newer_blocks(self):
        # Introduction-version contract: a v5.3.0 user keeps their pre-5.3.0
        # blocks untouched and receives everything introduced after 5.3.0.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            cfg_path = _write_config(tmp, {"version": "5.3.0"})

            result = migrate_config(str(cfg_path))

            self.assertTrue(result["success"])
            added = {
                c["key"] for c in result["changes"] if c.get("action") == "added"
            }
            self.assertEqual(added, POST_5_3_0_BLOCKS)

            on_disk = json.loads(cfg_path.read_text())
            self.assertNotIn("tom_features", on_disk)
            self.assertNotIn("loop_mode", on_disk)

    def test_seeding_is_idempotent_on_second_run(self):
        # First migrate brings the config to CURRENT_VERSION; a second run must
        # add nothing and bump nothing.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            cfg_path = _write_config(tmp, {"version": "4.0.0"})

            migrate_config(str(cfg_path))
            first_pass = json.loads(cfg_path.read_text())

            second = migrate_config(str(cfg_path))

            self.assertTrue(second["success"])
            self.assertEqual(second["changes"], [])
            self.assertEqual(json.loads(cfg_path.read_text()), first_pass)

    def test_existing_block_is_not_overwritten(self):
        # User customisation of an already-present block survives migration.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            cfg_path = _write_config(
                tmp,
                {
                    "version": "4.0.0",
                    "read_guard_hook": {"enabled": False},
                },
            )

            migrate_config(str(cfg_path))

            on_disk = json.loads(cfg_path.read_text())
            self.assertEqual(on_disk["read_guard_hook"], {"enabled": False})


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_V6_18_1 = (
    REPO_ROOT / "hooks" / "nav_hook_lib" / "fixtures" / "nav-config-v6.18.1.json"
)


def _load_runtime_defaults() -> dict:
    """Import hooks/nav_hook_lib/config.py DEFAULTS — the v7 shape contract."""
    hooks_dir = str(REPO_ROOT / "hooks")
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    from nav_hook_lib import config as hook_config  # noqa: E402
    return hook_config.DEFAULTS


def _migrated_fixture(tmp: Path) -> dict:
    """Copy the pristine v6.18.1 fixture into tmp, migrate it, return on-disk doc."""
    cfg_path = tmp / ".nav-config.json"
    cfg_path.write_text(FIXTURE_V6_18_1.read_text())
    result = migrate_config(str(cfg_path))
    assert result["success"], result
    return json.loads(cfg_path.read_text())


class V7MigrationTests(unittest.TestCase):
    """TASK-63 Phase 2: additive-only v7 seeding against the pristine fixture."""

    def test_pristine_v6_18_1_every_v6_key_survives_byte_identical(self):
        # Additive-only contract: rollback to v6.18.1 must find its config
        # intact. Every pre-existing key serializes byte-identically.
        original = json.loads(FIXTURE_V6_18_1.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            on_disk = _migrated_fixture(Path(tmp))

        for key, value in original.items():
            if key == "version":
                continue  # version legitimately bumps with the plugin
            self.assertIn(key, on_disk, f"v6 key deleted by migration: {key}")
            self.assertEqual(
                json.dumps(on_disk[key], indent=2),
                json.dumps(value, indent=2),
                f"v6 key mutated by migration: {key}",
            )

    def test_v7_seed_keys_agree_with_runtime_defaults_key_for_key(self):
        # Drift guard (integration): the migrator's 7.0.0 entry, the runtime
        # DEFAULTS v7 blocks, and this test's V7_BLOCKS set must agree — a
        # block added to one surface but not the others is exactly the drift
        # class this pins (DEFAULTS is the source of truth).
        defaults = _load_runtime_defaults()
        seeded = set(config_migrator.VERSION_CONFIGS["7.0.0"])
        self.assertEqual(seeded, V7_BLOCKS)
        for block in sorted(V7_BLOCKS):
            self.assertIn(block, defaults, f"v7 seed absent from DEFAULTS: {block}")

    def test_v7_blocks_added_matching_runtime_defaults(self):
        # hooks/nav_hook_lib/config.py DEFAULTS is the runtime's contract; the
        # seeded shapes must match it. tier1.rules is the one deliberate
        # difference: DEFAULTS layers {} (per-rule keys come from user config),
        # the migrator seeds the TASK-62 whitelist explicitly so every rule is
        # discoverable and individually toggleable.
        defaults = _load_runtime_defaults()
        with tempfile.TemporaryDirectory() as tmp:
            on_disk = _migrated_fixture(Path(tmp))

        for block in V7_BLOCKS:
            self.assertIn(block, on_disk, f"v7 block not seeded: {block}")

        for block in sorted(V7_BLOCKS - {"tier1"}):
            self.assertEqual(on_disk[block], defaults[block], f"shape drift: {block}")

        self.assertEqual(set(on_disk["tier1"]), set(defaults["tier1"]))
        self.assertEqual(on_disk["tier1"]["enabled"], defaults["tier1"]["enabled"])
        self.assertEqual(
            on_disk["tier1"]["rules"], {rule: True for rule in TIER1_RULE_IDS}
        )

    def test_new_blocking_features_seed_off(self):
        # mem-037 class: every net-new blocking/injecting capability ships OFF;
        # only the dispatcher itself is ON. continue_enabled stays False
        # permanently (mem-051: continue:true is a no-op) with the cap at 2.
        with tempfile.TemporaryDirectory() as tmp:
            on_disk = _migrated_fixture(Path(tmp))

        self.assertTrue(on_disk["dispatcher"]["enabled"])
        self.assertFalse(on_disk["tier1"]["enabled"])
        self.assertFalse(on_disk["stop_completion"]["enabled"])
        self.assertFalse(on_disk["stop_completion"]["continue_enabled"])
        self.assertEqual(on_disk["stop_completion"]["max_continues"], 2)
        self.assertFalse(on_disk["jit_memory"]["enabled"])
        self.assertFalse(on_disk["subagent_context"]["enabled"])
        self.assertFalse(on_disk["failure_diagnosis"]["enabled"])
        # systemMessage-only safety surfaces (never blocking) seed ON.
        self.assertTrue(on_disk["config_guard"]["enabled"])
        self.assertTrue(on_disk["setup_hook"]["enabled"])

    def test_strict_block_posture_inherited_not_reset(self):
        # No successor blocks exist (v7 ops kept the v6 config keys verbatim),
        # so inheritance == additive-only: the user's strict_block value must
        # come through migration unchanged, true or false.
        for posture in (True, False):
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                doc = json.loads(FIXTURE_V6_18_1.read_text())
                doc["workflow_enforcer_hook"]["strict_block"] = posture
                doc["read_guard_hook"]["strict_block"] = posture
                cfg_path = _write_config(tmp, doc)

                migrate_config(str(cfg_path))

                on_disk = json.loads(cfg_path.read_text())
                self.assertIs(on_disk["workflow_enforcer_hook"]["strict_block"], posture)
                self.assertIs(on_disk["read_guard_hook"]["strict_block"], posture)

    def test_strict_block_absent_gets_shipped_default(self):
        # A config predating the enforcement blocks receives the shipped
        # defaults (strict_block: true) — the third row of the fixture matrix.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            cfg_path = _write_config(tmp, {"version": "6.11.0"})

            migrate_config(str(cfg_path))

            on_disk = json.loads(cfg_path.read_text())
            self.assertTrue(on_disk["workflow_enforcer_hook"]["strict_block"])
            self.assertTrue(on_disk["read_guard_hook"]["strict_block"])

    def test_cli_double_run_is_byte_identical(self):
        # TASK-45 pattern: exercise the real CLI against a tmp fixture, twice.
        # Second run must change nothing on disk (byte-identical) and report
        # up-to-date. Run once with hook-style env vars set and once with them
        # unset (mem-036 discipline: both env states must behave identically).
        script = str(Path(config_migrator.__file__).resolve())
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            cfg_path = tmp / ".nav-config.json"
            cfg_path.write_text(FIXTURE_V6_18_1.read_text())

            env_set = dict(os.environ)
            env_set["CLAUDE_PROJECT_DIR"] = str(tmp)
            first = subprocess.run(
                [sys.executable, script, str(cfg_path)],
                capture_output=True, text=True, env=env_set,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            snapshot = cfg_path.read_bytes()

            env_unset = {
                k: v for k, v in os.environ.items()
                if not k.startswith("CLAUDE_") and k != "PILOT_EXECUTOR"
            }
            second = subprocess.run(
                [sys.executable, script, str(cfg_path)],
                capture_output=True, text=True, env=env_unset,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("already up to date", second.stdout)
            self.assertEqual(cfg_path.read_bytes(), snapshot)


if __name__ == "__main__":
    unittest.main()
