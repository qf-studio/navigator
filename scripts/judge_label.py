#!/usr/bin/env python3
"""judge_label — build and label a real-session prompt set for the judge eval (TASK-80 A).

    python3 scripts/judge_label.py extract [--limit 400] [--per-project 60] [--out PATH]
    python3 scripts/judge_label.py label   [--fixture PATH]
    python3 scripts/judge_label.py status  [--fixture PATH]

``extract`` walks ~/.claude/projects/*/*.jsonl, keeps genuine user prompts (no tool
results, no hook feedback, no slash-command echoes, no subagent transcripts), redacts
secret-shaped tokens with ``judge.redact_secrets``, head-caps, deduplicates, and samples
across projects. Labels start empty. ``label`` walks the unlabeled items interactively.
``status`` prints counts.

The output file holds real prompts from private projects: it is gitignored and must stay
local. Only aggregate numbers (scripts/judge_eval.py --fixture <file>) belong in the repo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "hooks"))

from nav_hook_lib import judge  # noqa: E402

DEFAULT_OUT = ROOT / "hooks" / "nav_hook_lib" / "fixtures" / "judge_eval_real.json"
PROJECTS_DIR = Path.home() / ".claude" / "projects"
MAX_CHARS = 1500
MIN_CHARS = 3

# Prompt text that is machine-made, not the user's: skipped at extraction.
SKIP_PREFIXES = (
    "Stop hook feedback:", "<command-", "<local-command", "[Request interrupted",
    "<system-reminder", "<task-notification", "Use the Task tool", "Base directory for",
    "This session is being continued",
)


def is_user_prompt(entry: dict) -> bool:
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return False
    content = (entry.get("message") or {}).get("content")
    if not isinstance(content, str):
        return False  # tool_result lists and other structured turns
    text = content.strip()
    if len(text) < MIN_CHARS or text.startswith(SKIP_PREFIXES):
        return False
    return True


def iter_prompts(jsonl_path: Path):
    with open(jsonl_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if is_user_prompt(entry):
                yield entry["message"]["content"].strip()


def extract(projects_dir: Path, limit: int, per_project: int, seed: int) -> list:
    rng = random.Random(seed)
    per_project_items = {}
    seen = set()
    for project in sorted(p for p in projects_dir.iterdir() if p.is_dir()):
        items = []
        for jsonl in sorted(project.glob("*.jsonl")):
            if jsonl.name.startswith("agent-"):
                continue  # subagent transcripts: prompts written by the model
            for text in iter_prompts(jsonl):
                text = judge.redact_secrets(text)[:MAX_CHARS]
                digest = hashlib.sha256(text.lower().encode("utf-8")).hexdigest()[:16]
                if digest in seen:
                    continue
                seen.add(digest)
                items.append({"id": digest, "project": project.name, "text": text,
                              "tier": None, "task": None, "ambiguous": None})
        if items:
            rng.shuffle(items)
            per_project_items[project.name] = items[:per_project]
    pooled = [item for items in per_project_items.values() for item in items]
    rng.shuffle(pooled)
    return pooled[:limit]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def labeled(doc: dict) -> list:
    return [p for p in doc["prompts"] if p.get("tier") in ("DIRECT", "TASK", "LOOP")]


def cmd_extract(args) -> int:
    prompts = extract(Path(args.projects), args.limit, args.per_project, args.seed)
    doc = {"_doc": "REAL prompts from local sessions — gitignored, never commit. "
                   "Labels: tier DIRECT|TASK|LOOP, task bool, ambiguous bool.",
           "prompts": prompts}
    out = Path(args.out)
    if out.exists() and not args.force:
        print(f"{out} exists; use --force to overwrite (labels would be lost)")
        return 1
    save(out, doc)
    projects = len({p["project"] for p in prompts})
    print(f"wrote {len(prompts)} prompts from {projects} projects to {out}")
    return 0


TIER_KEYS = {"d": "DIRECT", "t": "TASK", "l": "LOOP"}


def cmd_label(args) -> int:
    path = Path(args.fixture)
    doc = load(path)
    todo = [p for p in doc["prompts"] if p.get("tier") is None]
    print(f"{len(todo)} unlabeled of {len(doc['prompts'])}. "
          "Keys: tier d/t/l, then task y/n, then ambiguous y/n. s = skip, q = quit.\n")
    for index, item in enumerate(todo, 1):
        print("─" * 72)
        print(f"[{index}/{len(todo)}] ({item['project'][:40]})")
        print(item["text"][:600] + ("…" if len(item["text"]) > 600 else ""))
        print()
        answer = input("tier [d/t/l/s/q]: ").strip().lower()
        if answer == "q":
            break
        if answer == "s" or answer not in TIER_KEYS:
            continue
        item["tier"] = TIER_KEYS[answer]
        item["task"] = input("task-shaped? [y/n]: ").strip().lower().startswith("y")
        item["ambiguous"] = (item["task"]
                             and input("needs a brief? [y/n]: ").strip().lower().startswith("y"))
        save(path, doc)
    print(f"\nlabeled: {len(labeled(doc))} / {len(doc['prompts'])}")
    return 0


def cmd_status(args) -> int:
    doc = load(Path(args.fixture))
    done = labeled(doc)
    by_tier = {}
    for p in done:
        by_tier[p["tier"]] = by_tier.get(p["tier"], 0) + 1
    print(f"labeled {len(done)} / {len(doc['prompts'])}   {by_tier}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("extract")
    ex.add_argument("--projects", default=str(PROJECTS_DIR))
    ex.add_argument("--limit", type=int, default=400)
    ex.add_argument("--per-project", type=int, default=60)
    ex.add_argument("--seed", type=int, default=79)
    ex.add_argument("--out", default=str(DEFAULT_OUT))
    ex.add_argument("--force", action="store_true")
    ex.set_defaults(func=cmd_extract)
    for name, func in (("label", cmd_label), ("status", cmd_status)):
        sp = sub.add_parser(name)
        sp.add_argument("--fixture", default=str(DEFAULT_OUT))
        sp.set_defaults(func=func)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
