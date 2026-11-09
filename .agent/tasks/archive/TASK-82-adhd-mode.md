# TASK-82: ADHD mode — a per-person output-shaping switch, on/off mid-session

**Status**: ✅ Implemented — 2026-10-01 (unreleased; ships in v7.9.0 with the multi-Claude removal). Both open questions answered: inject on every prompt; personal-global switch with repo pin.

## Context

The user's output-shaping rules for ADHD live as a hardcoded line in `~/.claude/CLAUDE.md`.
That is always-on, applies to every project and every subagent, cannot be switched off for
a pairing session or a demo, and is invisible to tooling. The ask: an **ADHD mode** that can
be flipped on and off, including mid-session, whose rules are injected only while on and
are otherwise absent from the instructions.

Reference reviewed (2026-10-01, Sonnet research run):

- `uditakhourii/adhd` — **not** an ADHD-reader mode. The name denotes a tree-of-thought
  divergence skill (5 parallel framed agents + a critic). No output rules. Not a starting
  point.
- `ayghri/i-have-adhd` (mirror `beyonddream/claude-i-have-adhd`) — the real match. A
  session-persistent prose mode (`/i-have-adhd` … "stop adhd mode"). Ten rules: lead with
  action; number multi-step work; end with one sub-two-minute next action; suppress
  tangents; restate state ("step 3 of 5") every turn; give time estimates; make wins
  visible; flat tone for errors; cap lists at 5 (now/later split); no preamble or recap.
  Override cases: user asks to explain, destructive action looms, debug spiral, real
  ambiguity, rule would delete the answer. Gaps: no "time-critical first, bold the
  deadline", no "name the single most important pending item", no enforcement, no
  subagent exclusion, no per-person scoping, state is only the transcript.

What Navigator can do better: a hook-runtime op makes the mode deterministic (no prose
"stays on until"), scoped to the person, excluded from subagents, and toggled without a
restart because config is loaded on every dispatch.

## Design

**Op**: `hooks/ops/prompt_adhd.py`, event `UserPromptSubmit`. Two roles in one op:

1. **Responder** (phase `responders`, before `prompt_brief`): exact-match toggle phrases
   on the `strip_all`'d prompt — `adhd mode on|off`, `enable|disable adhd mode`,
   `stop adhd mode`, `start adhd mode`. Flips the switch, answers with
   `decision: block` + one line (`ADHD mode: on — personal, ~/.config/navigator`), zero
   model invocation (mem-053 channel, same as Tier-1). Independent of `tier1.enabled`.
2. **Injector** (phase `injectors`, listed first so it lands above the brief): while on,
   `additional_context` carries the rule block (~450 chars, ~110 tokens) on **every**
   prompt. Declarative framing ("The reader has ADHD. Output shape: …") so it survives
   the prompt-injection filter the way jit_memory content does.

**Rule block** (v1, built in): the four rules from the user's global CLAUDE.md line first
(ONE next action up top; time-critical first and **bold**; bullets over prose; name the
single most important pending item), then the i-have-adhd rules that add something:
number bounded steps; restate "step k of n" on multi-step work; cap lists at 5 with a
now/later split; flat tone for errors; no preamble or recap; end with one sub-two-minute
action. Same override cases as i-have-adhd, plus: never shorten error output or test
results.

**Switch (where "on" lives)**: ADHD is a trait of the person, not the repo, so the
primary switch is per-person and global: `~/.config/navigator/adhd-mode.json`
(`{"enabled": true, "updated": "<iso>"}`; `NAVIGATOR_CONFIG_HOME` overrides, same
pattern as `onboarding_paths.py`). A repo can pin it either way via
`adhd_mode.enabled: true|false` in `.agent/.nav-config.json` or the gitignored
`.nav-config.local.json`; DEFAULTS seeds `adhd_mode.enabled: null` = "defer to the
personal file". Resolution: local > shared > personal file > off.

**Exclusions**: `PILOT_EXECUTOR` → op silent (no human reader). `SubagentStart`
(`subagent_context`) does not carry the block, so research/writer agents are unaffected.
Deep-research reports and nav-brief output keep their own formats; the rules apply to
the assistant's replies, not to artifacts, and the block says so.

**Surfaces**:
- `nav-features`: row `adhd_mode` (type config, default off, `--local` supported;
  `enable adhd_mode` with no flag writes the personal file, not the shared config).
- `session_start`: one status line `ADHD mode: on (personal)` when on.
- `registry.py`: two `OpSpec` rows (`prompt_adhd` responders + injectors, config key
  `adhd_mode`, budget 300 ms).
- `budget.py`: UserPromptSubmit clamp unchanged (block fits well under it).
- Docs: CLAUDE.md runtime table row; nav-features SKILL.md; docs site page.
- The user's global CLAUDE.md line is removed by the user once the mode is on, so the
  rules exist in exactly one place.

**Not doing**: post-hoc output rewriting (no channel for it); per-rule toggles in v1
(one switch; a personal `rules_file` override can come later); any change to subagent
prompts.

## Plan

1. `nav_hook_lib/personal.py`: tiny reader/writer for `~/.config/navigator/<name>.json`
   (reuse by future per-person settings). Tests: env override, missing file, bad JSON.
2. `hooks/ops/prompt_adhd.py` + `test_prompt_adhd.py`: toggle phrases (exact, case-
   insensitive, trailing punctuation tolerated; never inside longer prompts), resolution
   order, block content snapshot, pilot silence, budget.
3. `registry.py` rows; `config.DEFAULTS["adhd_mode"]`; `prompt_tier1.FEATURE_BLOCKS`;
   `config_migrator.VERSION_CONFIGS["7.9.0"]` + test lists.
4. `feature_manager.py` entry with the personal-file branch; `session_start` status line.
5. Docs + changelog; release as 7.9.0 together with the multi-Claude removal.

## Verify

- `adhd mode on` → blocked answer, no model turn (`num_turns=0` in the transcript);
  next prompt's context carries the block; `adhd mode off` → next prompt has none.
- Toggle mid-session with no restart; toggle in repo A is visible in repo B.
- `.nav-config.local.json` `adhd_mode.enabled: false` wins over the personal file.
- A spawned `navigator-research` agent transcript contains no ADHD block.
- `make test` green; UserPromptSubmit dispatch p95 unchanged (≤200 ms).

Size: ~half a day.

## Done (2026-10-01)

- `nav_hook_lib/personal.py` (per-person JSON under `~/.config/navigator`, `NAVIGATOR_CONFIG_HOME`
  override), `nav_hook_lib/adhd.py` (phrases, resolution, rule block, state), `ops/prompt_adhd.py`
  (responder row after prompt_tier1, budget 200 ms). 11 + 10 + 13 new tests incl. the dispatcher
  subprocess path; `make test` green.
- `adhd_mode` block in DEFAULTS / live config / migrator 7.9.0; `nav-features` row with the
  personal-file branch; session-start status line; CLAUDE.md, nav-features SKILL.md,
  DEVELOPMENT-README ops table, changelog.
- Live check on this repo: `adhd mode` answers via decision:block; dispatch ~0.5 s with the judge
  call included. Not switched on for the author yet.

## Open questions (answered)

1. Inject on every prompt (robust, ~110 tokens each) or once per session plus after
   compaction (cheaper, drifts on long sessions)? Recommendation: every prompt.
2. Personal-global switch with repo override (recommended) or repo-local only
   (`.nav-config.local.json`, one toggle per project)?
