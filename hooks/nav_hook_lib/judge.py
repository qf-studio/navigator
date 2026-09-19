#!/usr/bin/env python3
"""nav_hook_lib.judge — typed prompt judgments from a System One model (TASK-79).

One HTTP request per prompt answers several typed questions at once (noul =
yes/no probability, score = position on an ordered rubric). The answers overlay
the keyword scorers in ``scoring`` — per axis, and only when decisive:

  - a noul counts only outside the ``[noul_low, noul_high]`` band;
  - a score counts only when its ``confidence >= min_confidence``;
  - everything else — undecided axis, timeout, missing key, HTTP or parse
    error, feature disabled — leaves the heuristic in charge for that axis.

Ships OFF (``judge.enabled`` in config.DEFAULTS). The prompt leaves the machine
when enabled, so the op hands over the strip_all()'d text and this module
redacts secret-shaped tokens and head-caps it before it becomes request state.
Never raises to a caller, never writes stderr (mem-034: sentinels.py is the
only stderr writer under hooks/).

Provider: TypeSafe ``POST /v1/systemone`` (docs.typesafe.ai/api). Only stdlib.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

try:
    from nav_hook_lib import config
except ImportError:  # run as a script: python3 hooks/nav_hook_lib/judge.py --check
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from nav_hook_lib import config

DEFAULTS = {
    "enabled": False,
    "provider": "typesafe",
    "endpoint": "https://api.typesafe.ai/v1/systemone",
    "model": "jev-latest",
    "timeout_ms": 1500,
    # Sweep 2026-09-19 on fixtures/judge_eval.json (60 prompts): band 0.4/0.6
    # + floor 0.4 scored best on all three axes; see TASK-79 "Eval run".
    "min_confidence": 0.4,
    "noul_low": 0.4,
    "noul_high": 0.6,
    "api_key_env": "TYPESAFE_API_KEY",
    "api_key_file": "~/.config/typesafe/api_key",
    "max_state_chars": 4000,
}

# Ordered rubric levels. Index / (len - 1) normalizes a score to 0..1.
COMPLEXITY_LEVELS = (
    "trivial: a one-line answer or a single small edit",
    "small: one file, under an hour of work",
    "substantial: several files, a new feature, or a refactor of one module",
    "large: a cross-cutting refactor, a new subsystem, or multi-day work",
)
AMBIGUITY_LEVELS = (
    "clear: scope, target files or components, and done-criteria are explicit",
    "partly: the goal is clear but scope, limits, or done-criteria are missing",
    "vague: the goal itself is open to interpretation",
)
# Level weights for the 0..1 ambiguity value. "partly" sits below the 0.5
# brief threshold on its own (eval 2026-09-19: a linear 0.5 briefed every
# "bump the version" prompt); only real "vague" mass pulls a prompt over.
AMBIGUITY_WEIGHTS = (0.0, 0.35, 1.0)

QUESTIONS = {
    "is_task": {
        "type": "noul",
        "instructions": (
            "The message asks the assistant to change something: write or edit code, "
            "files, configuration, or documents. Questions, chat, status reports, "
            "pasted logs, and replies confirming or answering the assistant do not count."
        ),
    },
    "wants_loop": {
        "type": "noul",
        "instructions": (
            "The user explicitly asks for unattended, autonomous iteration until the "
            "work is finished (for example 'run until done', 'keep going until it "
            "passes', 'do all of them without stopping'). Merely mentioning words like "
            "'loop', 'loop mode', or 'until' in passing, in a quote, or in pasted text "
            "does not count."
        ),
    },
    "complexity": {
        "type": "score",
        "instructions": "How much work does fulfilling this request take?",
        "criteria": list(COMPLEXITY_LEVELS),
    },
    "ambiguity": {
        "type": "score",
        "instructions": (
            "How underspecified is the request, judged by whether scope, limits, and "
            "acceptance criteria are stated?"
        ),
        "criteria": list(AMBIGUITY_LEVELS),
    },
    "scope_defined": {
        "type": "noul",
        "instructions": "The request names the files, components, or area it applies to.",
    },
    "limits_defined": {
        "type": "noul",
        "instructions": (
            "The request states boundaries: what not to touch, a size or count limit, "
            "a time box, or constraints on the approach."
        ),
    },
    "approach_defined": {
        "type": "noul",
        "instructions": "The request says how the work should be done, not only what.",
    },
    "verification_defined": {
        "type": "noul",
        "instructions": (
            "The request states how success will be checked: tests to pass, expected "
            "output, or explicit acceptance criteria."
        ),
    },
}
DIMENSIONS = ("scope", "limits", "approach", "verification")

# Secret-shaped tokens redacted before the prompt leaves the machine.
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password|passwd|bearer)"
               r"\s*[:=]\s*['\"]?\S+"),
    re.compile(r"\bapikey_[A-Za-z0-9_]{16,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\b[0-9a-f]{40,}\b"),
)
REDACTED = "[redacted]"


@dataclass
class Judgment:
    """Parsed answers plus the thresholds that decide when each axis counts."""

    is_task: float
    wants_loop: float
    complexity: float            # 0..1 (score / top level)
    complexity_confidence: float
    ambiguity: float             # 0..1
    ambiguity_confidence: float
    dimensions: dict             # name -> probability the dimension is defined
    model: str = ""
    latency_ms: int = 0
    input_tokens: int = 0
    thresholds: dict = field(default_factory=dict)

    # -- decisions -------------------------------------------------------
    def task_verdict(self):
        return decide(self.is_task, self.thresholds)

    def loop_verdict(self):
        return decide(self.wants_loop, self.thresholds)

    def complexity_if_confident(self):
        if self.complexity_confidence >= self._min_confidence():
            return self.complexity
        return None

    def ambiguity_if_confident(self):
        if self.ambiguity_confidence >= self._min_confidence():
            return self.ambiguity
        return None

    def dimension_verdict(self, name):
        p = self.dimensions.get(name)
        if p is None:
            return None
        return decide(p, self.thresholds)

    def complexity_level(self) -> str:
        return _level_name(COMPLEXITY_LEVELS, self.complexity)

    def _min_confidence(self) -> float:
        return float(self.thresholds.get("min_confidence", DEFAULTS["min_confidence"]))


def decide(p, thresholds=None):
    """True above ``noul_high``, False below ``noul_low``, None in between."""
    thresholds = thresholds or {}
    low = float(thresholds.get("noul_low", DEFAULTS["noul_low"]))
    high = float(thresholds.get("noul_high", DEFAULTS["noul_high"]))
    try:
        p = float(p)
    except (TypeError, ValueError):
        return None
    if p >= high:
        return True
    if p <= low:
        return False
    return None


def _level_name(levels, normalized: float) -> str:
    index = int(round(max(0.0, min(1.0, normalized)) * (len(levels) - 1)))
    return levels[index].split(":", 1)[0]


# ---------------------------------------------------------------------------
# Settings / key
# ---------------------------------------------------------------------------

def settings(cfg) -> dict:
    """The ``judge`` block merged over DEFAULTS (tolerant of a missing block)."""
    merged = dict(DEFAULTS)
    block = cfg.get("judge") if isinstance(cfg, dict) else None
    if isinstance(block, dict):
        merged.update(block)
    return merged


def _key_from_env(cfg_settings: dict):
    env_name = str(cfg_settings.get("api_key_env") or DEFAULTS["api_key_env"])
    return env_name, (os.environ.get(env_name) or "").strip()


def _key_from_file(cfg_settings: dict):
    raw = cfg_settings.get("api_key_file") or DEFAULTS["api_key_file"]
    path = Path(os.path.expanduser(str(raw)))
    try:
        if path.is_file():
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            return path, (lines[0].strip() if lines else "")
    except Exception:
        pass
    return path, ""


def api_key(cfg_settings: dict):
    """Env var first, then the key file; ``None`` when neither yields a key."""
    _name, key = _key_from_env(cfg_settings)
    if key:
        return key
    _path, key = _key_from_file(cfg_settings)
    return key or None


def key_source(cfg_settings: dict):
    """Where the key comes from: ``"env:NAME"``, ``"file:PATH"``, or ``None``.

    Never returns the key itself — safe to print in a session banner.
    """
    name, key = _key_from_env(cfg_settings)
    if key:
        return f"env:{name}"
    path, key = _key_from_file(cfg_settings)
    if key:
        return f"file:{path}"
    return None


def setup_hint(cfg_settings: dict) -> str:
    """One paragraph telling a user how to supply a key (no secrets inside)."""
    name, _ = _key_from_env(cfg_settings)
    path = cfg_settings.get("api_key_file") or DEFAULTS["api_key_file"]
    return (
        f"Get a key at https://console.typesafe.ai/keys, then either export {name} "
        f"in the environment Claude Code runs in, or write it to {path} "
        f"(chmod 600). Verify with: python3 hooks/nav_hook_lib/judge.py --check "
        f"(from the plugin root). Until a key is found the keyword heuristics answer."
    )


# ---------------------------------------------------------------------------
# Request / response
# ---------------------------------------------------------------------------

def redact_secrets(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def build_request(prompt: str, cfg_settings: dict) -> dict:
    cap = int(cfg_settings.get("max_state_chars") or DEFAULTS["max_state_chars"])
    state = redact_secrets(prompt or "")[:cap]
    return {
        "state": state,
        "model": str(cfg_settings.get("model") or DEFAULTS["model"]),
        "questions": QUESTIONS,
    }


def _noul(answers: dict, name: str) -> float:
    return float(answers[name]["noul"])


def _score(answers: dict, name: str, levels, weights=None) -> tuple:
    """(normalized 0..1 value, confidence) for a score answer.

    With ``weights`` and a probabilities map, the value is the probability-
    weighted sum over levels; otherwise the linear ``score / top`` position.
    """
    entry = answers[name]
    top = len(levels) - 1
    probabilities = entry.get("probabilities")
    if weights is not None and isinstance(probabilities, dict) and probabilities:
        value = sum(float(probabilities.get(str(i), 0.0)) * weights[i]
                    for i in range(len(levels)))
    else:
        value = float(entry["score"]) / top
    return max(0.0, min(1.0, value)), float(entry.get("confidence", 0.0))


def parse_response(doc: dict, thresholds: dict = None) -> Judgment:
    """Map the API document onto a Judgment. Raises on a malformed shape."""
    answers = doc["answers"]
    complexity, complexity_conf = _score(answers, "complexity", COMPLEXITY_LEVELS)
    ambiguity, ambiguity_conf = _score(answers, "ambiguity", AMBIGUITY_LEVELS,
                                       AMBIGUITY_WEIGHTS)
    dims = {name: _noul(answers, f"{name}_defined") for name in DIMENSIONS}
    usage = doc.get("usage") or {}
    return Judgment(
        is_task=_noul(answers, "is_task"),
        wants_loop=_noul(answers, "wants_loop"),
        complexity=complexity,
        complexity_confidence=complexity_conf,
        ambiguity=ambiguity,
        ambiguity_confidence=ambiguity_conf,
        dimensions=dims,
        model=str(doc.get("model") or ""),
        input_tokens=int(usage.get("input_tokens") or 0),
        thresholds=dict(thresholds or {}),
    )


def _thresholds(cfg_settings: dict) -> dict:
    return {
        "min_confidence": cfg_settings.get("min_confidence", DEFAULTS["min_confidence"]),
        "noul_low": cfg_settings.get("noul_low", DEFAULTS["noul_low"]),
        "noul_high": cfg_settings.get("noul_high", DEFAULTS["noul_high"]),
    }


def call(prompt: str, cfg_settings: dict, opener=None):
    """One request; a Judgment, or ``None`` on any failure. Never raises."""
    opener = opener or urllib.request.urlopen
    try:
        key = api_key(cfg_settings)
        if not key or not (prompt or "").strip():
            return None
        body = json.dumps(build_request(prompt, cfg_settings)).encode("utf-8")
        request = urllib.request.Request(
            str(cfg_settings.get("endpoint") or DEFAULTS["endpoint"]),
            data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "User-Agent": "navigator-judge/1",
            },
            method="POST",
        )
        timeout = float(cfg_settings.get("timeout_ms") or DEFAULTS["timeout_ms"]) / 1000.0
        started = time.monotonic()
        with opener(request, timeout=timeout) as response:
            doc = json.load(response)
        judgment = parse_response(doc, _thresholds(cfg_settings))
        judgment.latency_ms = int((time.monotonic() - started) * 1000)
        return judgment
    except Exception:
        return None


def judge_prompt(prompt: str, cfg, opener=None):
    """Feature-gated entry: ``None`` unless ``judge.enabled`` and a key exist."""
    cfg_settings = settings(cfg)
    if not cfg_settings.get("enabled"):
        return None
    if config.is_pilot_executor():
        return None
    return call(prompt, cfg_settings, opener=opener)


# ---------------------------------------------------------------------------
# CLI: python3 judge.py --check   (setup verification; prints no secrets)
# ---------------------------------------------------------------------------

CHECK_PROMPT = "fix the typo in README line 12"


def check(cfg=None, opener=None, out=print) -> int:
    """Report enable flag, key source and a live round-trip. 0 = ready."""
    if cfg is None:
        cfg = config.load(Path.cwd())
    cfg_settings = settings(cfg)
    enabled = bool(cfg_settings.get("enabled"))
    out(f"judge.enabled: {'true' if enabled else 'false'}"
        + ("" if enabled else "   (say 'enable judge' or set judge.enabled in .agent/.nav-config.json)"))
    source = key_source(cfg_settings)
    out(f"api key: {source or 'NOT FOUND'}")
    if not source:
        out(setup_hint(cfg_settings))
        return 1
    live = dict(cfg_settings, enabled=True)
    judgment = call(CHECK_PROMPT, live, opener=opener)
    if judgment is None:
        out(f"round trip: FAILED ({live.get('endpoint')}, timeout {live.get('timeout_ms')} ms) "
            "— check the key, network, or raise judge.timeout_ms")
        return 2
    out(f"round trip: ok — {judgment.model}, {judgment.latency_ms} ms, "
        f"{judgment.input_tokens} input tokens; "
        f"is_task={judgment.is_task:.2f} complexity={judgment.complexity_level()}")
    return 0


def main(argv=None, opener=None, out=print) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Navigator typed prompt judge")
    parser.add_argument("--check", action="store_true",
                        help="verify config, key source and a live round trip")
    args = parser.parse_args(argv)
    if args.check:
        return check(opener=opener, out=out)
    parser.print_help()
    return 0


_CACHE_ATTR = "_judgment"
_UNSET = object()


def for_ctx(ctx, message: str, opener=None):
    """Judgment for this dispatch, computed once and cached on ``ctx``.

    prompt_gate and prompt_brief both score the same prompt; the second caller
    reuses the first's answer (or its ``None``) instead of paying a second call.
    """
    cached = getattr(ctx, _CACHE_ATTR, _UNSET)
    if cached is not _UNSET:
        return cached
    judgment = judge_prompt(message, getattr(ctx, "config", None), opener=opener)
    try:
        setattr(ctx, _CACHE_ATTR, judgment)
    except Exception:
        pass
    return judgment


if __name__ == "__main__":
    import sys
    sys.exit(main())
