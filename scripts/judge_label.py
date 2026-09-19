#!/usr/bin/env python3
"""judge_label — build and label a real-session prompt set for the judge eval (TASK-80 A).

    python3 scripts/judge_label.py extract [--limit 400] [--per-project 60] [--out PATH]
    python3 scripts/judge_label.py label   [--fixture PATH]     # one key per prompt, TTY
    python3 scripts/judge_label.py sheet   [--out PATH]         # markdown sheet for an editor
    python3 scripts/judge_label.py import  [--sheet PATH]       # read the filled sheet back
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


# One keystroke per prompt. TASK/LOOP imply task-shaped; "ambiguous" only
# matters for task-shaped prompts.
KEYS = {
    "n": ("DIRECT", False, False),  # not a task: question, reply, chat, pasted log
    "d": ("DIRECT", True, False),   # small, clear task
    "t": ("TASK", True, False),     # substantial, clear
    "a": ("TASK", True, True),      # substantial, needs a brief
    "l": ("LOOP", True, False),     # asks for autonomous iteration
}
KEY_HELP = ("n = not a task   d = small clear task   t = substantial   "
            "a = substantial + needs brief   l = loop   s = skip   q = quit")


def apply_key(item: dict, key: str) -> bool:
    if key not in KEYS:
        return False
    item["tier"], item["task"], item["ambiguous"] = KEYS[key]
    return True


def cmd_label(args) -> int:
    path = Path(args.fixture)
    doc = load(path)
    if not sys.stdin.isatty():
        print("label needs a terminal (stdin is not a TTY). Run it in a normal shell, "
              "or use: judge_label.py sheet  -> edit the markdown -> judge_label.py import")
        return 2
    todo = [p for p in doc["prompts"] if p.get("tier") is None]
    print(f"{len(todo)} unlabeled of {len(doc['prompts'])}.\n{KEY_HELP}\n")
    done = 0
    try:
        for index, item in enumerate(todo, 1):
            print("─" * 72)
            print(f"[{index}/{len(todo)}]  {item['text'][:500]}"
                  + ("…" if len(item["text"]) > 500 else ""))
            answer = input("> ").strip().lower()
            if answer == "q":
                break
            if apply_key(item, answer):
                done += 1
                save(path, doc)
    except (EOFError, KeyboardInterrupt):
        print()
    print(f"labeled this run: {done}   total: {len(labeled(doc))} / {len(doc['prompts'])}")
    return 0


SHEET_HEADER = ("# Judge labels — fill the `key` column (n/d/t/a/l), leave blank to skip\n"
                "# " + KEY_HELP + "\n\n| id | key | prompt |\n|---|---|---|\n")


def cmd_sheet(args) -> int:
    doc = load(Path(args.fixture))
    rows = []
    for item in doc["prompts"]:
        if item.get("tier") is not None:
            continue
        text = item["text"].replace("|", "\\|").replace("\n", " ")[:300]
        rows.append(f"| {item['id']} |  | {text} |")
    Path(args.out).write_text(SHEET_HEADER + "\n".join(rows) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} rows to {args.out} — fill `key`, then: judge_label.py import")
    return 0


def cmd_import(args) -> int:
    path = Path(args.fixture)
    doc = load(path)
    by_id = {item["id"]: item for item in doc["prompts"]}
    applied = 0
    for line in Path(args.sheet).read_text(encoding="utf-8").splitlines():
        if not line.startswith("| ") or line.startswith("| id ") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        item = by_id.get(cells[0])
        if item is not None and apply_key(item, cells[1].lower()):
            applied += 1
    save(path, doc)
    print(f"applied {applied} labels   total: {len(labeled(doc))} / {len(doc['prompts'])}")
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
    for name, func in (("label", cmd_label), ("status", cmd_status),
                       ("sheet", cmd_sheet), ("import", cmd_import)):
        sp = sub.add_parser(name)
        sp.add_argument("--fixture", default=str(DEFAULT_OUT))
        sp.set_defaults(func=func)
        if name == "sheet":
            sp.add_argument("--out", default=str(DEFAULT_OUT.with_suffix(".sheet.md")))
        if name == "import":
            sp.add_argument("--sheet", default=str(DEFAULT_OUT.with_suffix(".sheet.md")))
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
