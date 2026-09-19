#!/usr/bin/env python3
"""nav_hook_lib.config — layered Navigator config for v7 hook ops (TASK-59 Phase 1).

Loads .agent/.nav-config.json over a complete DEFAULTS tree so no op ever
KeyErrors on a missing block. This covers the old-consumer-config risk: a
pristine v6.18.1 config (no v7 blocks) must load with every v7 feature at its
safe/off default (only the dispatcher itself is on; every blocking/injecting
v7 capability ships OFF and is enabled explicitly via TASK-62/63).

is_pilot_executor() is THE single PILOT_EXECUTOR policy point under hooks/ —
v6 re-checked the env var per hook, and one missed check meant an interactive
block under Pilot. A guard test in test_config.py greps the lib for strays
(TASK-61 widens the sweep to all of hooks/).

Pure Python stdlib only.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path

try:
    from . import hio
except ImportError:  # top-level module under per-directory unittest discovery
    import hio

CONFIG_RELPATH = ".agent/.nav-config.json"

# Layered defaults. Sources of truth:
#   - v6 blocks: the in-code defaults of the nine hooks/*.py scripts and the
#     canonical v6.18.1 config (fixtures/nav-config-v6.18.1.json).
#   - v7 blocks: the hooks-runtime plan routing matrix; blocking/injecting
#     features seeded OFF (TASK-62 turns them on deliberately).
# "version" defaults to None: the lib never invents a project version; the
# user's config (or its absence) is the signal config_migrator acts on.
DEFAULTS = {
    "version": None,
    "project_management": "none",
    "task_prefix": "TASK",
    "team_chat": "none",
    "auto_load_navigator": True,
    "compact_strategy": "conservative",
    "task_mode": {
        "enabled": True,
        "auto_detect": True,
        "defer_to_skills": True,
        "complexity_threshold": 0.5,
        "show_phase_indicator": True,
    },
    "tom_features": {
        "verification_checkpoints": True,
        "confirmation_threshold": "high-stakes",
        "profile_enabled": True,
        "diagnose_enabled": True,
        "belief_anchors": False,
    },
    "loop_mode": {
        "enabled": False,
        "max_iterations": 5,
        "stagnation_threshold": 3,
        "exit_requires_explicit_signal": True,
        "show_status_block": True,
        "iteration_approval": "none",
        "periodic_interval": 3,
        "never_pause_on_stagnation": False,
        "stagnation_diversify_strategy": "combine",
    },
    "simplification": {
        "enabled": True,
        "trigger": "post-implementation",
        "scope": "modified",
        "model": "opus",
        "skip_patterns": ["*.test.*", "*.spec.*", "*.md", "*.json", "*.yaml"],
        "max_file_size": 50000,
        "auto_apply": False,
        "preserve_comments": True,
        "rules": {
            "avoid_nested_ternary": True,
            "max_nesting_depth": 3,
            "max_function_length": 50,
            "prefer_explicit_returns": True,
            "consolidate_imports": True,
        },
    },
    "auto_update": {
        "enabled": True,
        "check_interval_hours": 1,
    },
    "pilot": {
        "enabled": True,
        "label": "pilot",
        "repo": None,
    },
    "session_start_hook": {
        "enabled": True,
        "include_sections": [
            "navigator", "marker", "config", "graph", "profile", "tasks", "auto_update",
        ],
        "char_budget": 9500,
    },
    "compact_hook": {
        "enabled": True,
        "include_transcript_summary": True,
        "include_git_state": True,
        "char_budget": 8000,
        "append_post_compact_summary": True,
    },
    "task_graph_sync_hook": {
        "enabled": True,
    },
    "workflow_state_hook": {
        "enabled": True,
    },
    "profile_sync_hook": {
        "enabled": True,
    },
    "workflow_enforcer_hook": {
        "enabled": True,
        "strict_block": True,
    },
    "brief_hook": {
        "enabled": True,
        "ambiguity_threshold": 0.5,
        "memory_budget_chars": 1200,
        "contradiction_field": True,
    },
    "read_guard_hook": {
        "enabled": True,
        "warn_threshold": 3,
        "escalate_threshold": 5,
        "strict_block": True,
        "stale_after_seconds": 300,
        "allowlist": [
            "DEVELOPMENT-README.md",
            ".nav-config.json",
            ".user-profile.json",
            "knowledge/graph.json",
            "research/",
        ],
    },
    "knowledge_graph": {
        "enabled": True,
        "auto_capture_corrections": True,
        "auto_capture_decisions": True,
        "auto_surface_relevant": True,
        "max_session_memories": 5,
        "confidence_decay_rate": 0.01,
        "staleness_threshold_days": 90,
        "git_tracked": True,
    },
    "multi_agent": {
        "enabled": True,
        "default_workflow": "standard",
        "auto_dashboard": False,
        "parallel_limit": 3,
        "retry_attempts": 2,
        "phase_timeout_seconds": 180,
    },
    # ---- v7 blocks (hooks-runtime plan) — blocking features seeded OFF ----
    "dispatcher": {
        "enabled": True,
    },
    "tier1": {
        "enabled": False,
        "rules": {},
    },
    "stop_completion": {
        "enabled": False,
        "continue_enabled": False,  # mem-051: continue:true is a no-op; ships OFF permanently
        "max_continues": 2,
    },
    "jit_memory": {
        "enabled": False,
    },
    "subagent_context": {
        "enabled": False,
        "budget_chars": 2000,  # mem-052: viable at the 2k-char budget
    },
    "failure_diagnosis": {
        "enabled": False,  # injecting feature (PostToolUseFailure) — ships OFF
    },
    # config_guard / setup_hook emit only user-facing systemMessage lines on
    # explicit events (ConfigChange / Setup) — safety surfaces, seeded ON.
    "config_guard": {
        "enabled": True,
    },
    "setup_hook": {
        "enabled": True,
    },
    # ---- v7.3 nav-deep-research (TASK-74) — ships OFF, opt-in ----
    "deep_research": {
        "enabled": False,
        "max_sources": 30,
        "min_sources": 8,
        "fetchers": 4,
        "max_full_reads": 10,
        "critic_enabled": True,
        "models": {"fetcher": "sonnet", "writer": "opus", "critic": "opus", "patcher": "opus"},
    },
    # ---- v7.7 typed prompt judge (TASK-79) — ships OFF, opt-in ----
    # The prompt leaves the machine when enabled (secret-redacted, head-capped).
    # Per axis: nouls decide outside [noul_low, noul_high]; scores decide at
    # min_confidence or above; anything else keeps the keyword heuristic.
    "judge": {
        "enabled": False,
        "provider": "typesafe",
        "endpoint": "https://api.typesafe.ai/v1/systemone",
        "model": "jev-latest",
        "timeout_ms": 1500,
        "min_confidence": 0.4,
        "noul_low": 0.4,
        "noul_high": 0.6,
        "api_key_env": "TYPESAFE_API_KEY",
        "api_key_file": "~/.config/typesafe/api_key",
        "max_state_chars": 4000,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge ``override`` into ``base`` (in place; returns base).

    Dicts merge key-wise; any other value type (scalars, lists) replaces the
    default wholesale. Unknown user keys are preserved — the lib must not
    strip forward/backward-compat config it does not understand.
    """
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def load(root=None) -> dict:
    """Load layered config: user .agent/.nav-config.json deep-merged over DEFAULTS.

    ``root`` is the project root (defaults to hio.project_root()). A missing or
    corrupt user file yields a fresh copy of DEFAULTS. The returned dict is
    always a private copy — callers may mutate it freely.
    """
    if root is None:
        root = hio.project_root()
    cfg = copy.deepcopy(DEFAULTS)
    user = hio.safe_json(Path(root) / ".agent" / ".nav-config.json")
    if user:
        _deep_merge(cfg, user)
    return cfg


def get(cfg, dotted_path, default=None):
    """Fetch ``cfg['a']['b']['c']`` via 'a.b.c'; ``default`` on any miss."""
    node = cfg
    for part in dotted_path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def is_pilot_executor() -> bool:
    """True when running under Pilot's autonomous executor.

    THE ONLY place the PILOT_EXECUTOR env var is read anywhere under
    hooks/ (v7 discipline; guard test in test_config.py). Matches the v6
    semantics: any non-empty value is truthy, unset/empty is False.
    """
    return bool(os.environ.get("PILOT_EXECUTOR"))
