# SOP: Typed Prompt Judge (TypeSafe Jev) — setup and troubleshooting

**Since**: v7.7.0 (TASK-79)
**Ships**: OFF. The prompt text leaves the machine when on, so it is opt-in per project.

## What it does

With `judge.enabled`, each prompt is sent once to TypeSafe's Jev model with eight typed
questions (is it a task, does it ask for autonomous iteration, complexity, ambiguity, and
whether scope / limits / approach / verification are stated). Decisive answers override
Navigator's keyword scorers for that axis. Undecided answers, a timeout, a missing key or
any error keep the keyword heuristics, so turning it on can only change behavior when the
model is sure.

## Setup (three steps)

1. **Key**: create one at https://console.typesafe.ai/keys. Provide it one of two ways:
   - `export TYPESAFE_API_KEY=...` in the environment Claude Code runs in (shell profile
     or `~/.claude/settings.json` → `env`), or
   - write it to `~/.config/typesafe/api_key` and `chmod 600` the file.
   The env var wins when both exist. Never put the key in `.agent/.nav-config.json`; that
   file is committed.
2. **Enable**: say `enable judge` (nav-features), or set in `.agent/.nav-config.json`:
   ```json
   { "judge": { "enabled": true } }
   ```
3. **Verify**: from the plugin root (or the checkout),
   ```
   python3 hooks/nav_hook_lib/judge.py --check
   ```
   prints the enable flag, the key *source* (never the key), and a live round trip with
   model, latency and tokens. Exit 0 = ready, 1 = no key, 2 = round trip failed.

Session start shows `Typed judge: on (jev-latest, key from env:TYPESAFE_API_KEY)` when the
key resolves, or a warning with the same hint when it does not.

## Config keys (`judge` block, all optional)

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `false` | master switch |
| `model` | `jev-latest` | `jev-latest` moves with releases; pin `jev-1.13.0` for stable answers |
| `timeout_ms` | `1500` | fuse; UserPromptSubmit has a 5 s manifest budget |
| `min_confidence` | `0.4` | score axes (complexity, ambiguity) count at or above |
| `noul_low` / `noul_high` | `0.4` / `0.6` | yes/no axes count outside this band |
| `api_key_env` | `TYPESAFE_API_KEY` | env var name |
| `api_key_file` | `~/.config/typesafe/api_key` | fallback file |
| `max_state_chars` | `4000` | prompt head cap before sending |

Thresholds came from a sweep over 60 labeled prompts (see TASK-79); replay it with
`python3 scripts/judge_eval.py --replay hooks/nav_hook_lib/fixtures/judge_eval_recorded.json`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| WORKFLOW CHECK never shows "Judged by" | judge off, or no key | `--check`; enable; supply key |
| Session start warns "no API key was found" | key not in the hook's environment | export in the shell that launches Claude Code, or use the key file |
| `--check` exit 2 | 401 (bad key), 429 (rate limit), network | rotate key; retry; raise `timeout_ms` |
| A prompt is still misclassified | judge undecided → heuristic answered | lower the band / floor per project, or pin a model |
| Costs | ~700 input tokens per prompt, output free | ~$0.00003 per prompt at list price |

## Privacy

The strip_all()'d prompt is secret-redacted (`apikey_…`, `sk-…`, `ghp_…`, AWS, Slack, JWT,
long hex, `key=`/`token=` pairs) and head-capped before it becomes request state. Tool
output, files and transcript never leave; only the user prompt does. Under
`PILOT_EXECUTOR` the judge never runs.
