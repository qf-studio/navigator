#!/usr/bin/env python3
"""judge_eval — heuristic scorers vs the typed judge on labeled prompts (TASK-79).

Usage:
    python3 scripts/judge_eval.py [--fixture PATH] [--live] [--record PATH]
                                  [--replay PATH] [--min-confidence F]
                                  [--noul-low F] [--noul-high F]

--live calls the API (needs TYPESAFE_API_KEY or the key file); --record saves
the raw responses so a later --replay run re-scores without network. Prints
per-axis accuracy for heuristic, judge-only, and the blended policy that ships
(judge when decisive, heuristic otherwise), plus latency and token totals.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "hooks"))

from nav_hook_lib import judge, scoring  # noqa: E402

FIXTURE = ROOT / "hooks" / "nav_hook_lib" / "fixtures" / "judge_eval.json"


def heuristic_labels(text: str) -> dict:
    card = scoring.score(text)
    amb = scoring.score_ambiguity(text)
    return {
        "tier": card.tier,
        "task": bool(amb["task_shaped"]),
        "ambiguous": bool(amb["task_shaped"] and amb["score"] >= 0.5),
    }


def blended_labels(text: str, judgment) -> dict:
    card = scoring.score(text, judgment=judgment)
    amb = scoring.score_ambiguity(text, judgment=judgment)
    return {
        "tier": card.tier,
        "task": bool(amb["task_shaped"]),
        "ambiguous": bool(amb["task_shaped"] and amb["score"] >= 0.5),
    }


def judge_only_labels(judgment) -> dict:
    if judgment is None:
        return {}
    loop = judgment.wants_loop >= 0.5
    task = judgment.is_task >= 0.5
    tier = "LOOP" if loop else ("TASK" if judgment.complexity >= 0.5 else "DIRECT")
    return {"tier": tier, "task": task, "ambiguous": task and judgment.ambiguity >= 0.5}


def live_call(text: str, cfg: dict):
    """Raw API document plus latency, or None on failure (mirrors judge.call)."""
    import time
    import urllib.request
    key = judge.api_key(cfg)
    if not key:
        raise SystemExit("no API key: export TYPESAFE_API_KEY or create the key file")
    body = json.dumps(judge.build_request(text, cfg)).encode("utf-8")
    request = urllib.request.Request(
        cfg["endpoint"], data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=cfg["timeout_ms"] / 1000.0) as resp:
            doc = json.load(resp)
    except Exception as exc:  # keep going; the row scores as heuristic-only
        print(f"call failed: {exc}", file=sys.stderr)
        return None
    return {"_doc": doc, "_latency_ms": int((time.monotonic() - started) * 1000)}


def accuracy(rows, key, source) -> tuple:
    hits = total = 0
    for row in rows:
        predicted = row[source].get(key)
        if predicted is None:
            continue
        total += 1
        hits += int(predicted == row["label"][key])
    return hits, total


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture", default=str(FIXTURE))
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--record", help="write raw API docs here (JSON list)")
    parser.add_argument("--replay", help="read raw API docs from here instead of calling")
    parser.add_argument("--min-confidence", type=float)
    parser.add_argument("--noul-low", type=float)
    parser.add_argument("--noul-high", type=float)
    parser.add_argument("--show-misses", action="store_true")
    args = parser.parse_args(argv)

    prompts = json.loads(Path(args.fixture).read_text())["prompts"]
    cfg = dict(judge.DEFAULTS)
    cfg["enabled"] = True
    for name in ("min_confidence", "noul_low", "noul_high"):
        value = getattr(args, name)
        if value is not None:
            cfg[name] = value
    thresholds = judge._thresholds(cfg)

    docs = None
    if args.replay:
        docs = json.loads(Path(args.replay).read_text())
    elif not args.live:
        parser.error("choose --live or --replay PATH")

    recorded = []
    rows = []
    latencies = []
    tokens = 0
    for index, item in enumerate(prompts):
        text = item["text"]
        if docs is not None:
            doc = docs[index]
            judgment = judge.parse_response(doc["_doc"], thresholds) if doc else None
            if judgment is not None:
                judgment.latency_ms = doc.get("_latency_ms", 0)
        else:
            doc = live_call(text, cfg)
            recorded.append(doc)
            judgment = judge.parse_response(doc["_doc"], thresholds) if doc else None
            if judgment is not None:
                judgment.latency_ms = doc["_latency_ms"]
        if judgment is not None:
            latencies.append(judgment.latency_ms)
            tokens += judgment.input_tokens
        rows.append({
            "text": text,
            "label": {"tier": item["tier"], "task": item["task"], "ambiguous": item["ambiguous"]},
            "heuristic": heuristic_labels(text),
            "judge": judge_only_labels(judgment),
            "blended": blended_labels(text, judgment),
            "judgment": judgment,
        })

    if args.record and recorded:
        Path(args.record).write_text(json.dumps(recorded, indent=1))

    print(f"prompts: {len(rows)}   judged: {sum(1 for r in rows if r['judgment'])}")
    if latencies:
        print(f"latency ms: median {statistics.median(latencies):.0f}  "
              f"max {max(latencies)}   input tokens total {tokens}")
    print()
    print(f"{'axis':<10} {'heuristic':>10} {'judge':>10} {'blended':>10}")
    for key in ("tier", "task", "ambiguous"):
        cells = []
        for source in ("heuristic", "judge", "blended"):
            hits, total = accuracy(rows, key, source)
            cells.append(f"{hits}/{total}" if total else "-")
        print(f"{key:<10} {cells[0]:>10} {cells[1]:>10} {cells[2]:>10}")

    if args.show_misses:
        print()
        for row in rows:
            for key in ("tier", "task", "ambiguous"):
                if row["blended"].get(key) != row["label"][key]:
                    j = row["judgment"]
                    detail = ""
                    if j:
                        detail = (f" loop={j.wants_loop:.2f} task={j.is_task:.2f} "
                                  f"cx={j.complexity:.2f}/c{j.complexity_confidence:.2f} "
                                  f"amb={j.ambiguity:.2f}/c{j.ambiguity_confidence:.2f}")
                    print(f"MISS {key:<9} label={row['label'][key]!s:<6} "
                          f"heur={row['heuristic'][key]!s:<6} blended={row['blended'][key]!s:<6}"
                          f"{detail}\n     {row['text'][:90]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
