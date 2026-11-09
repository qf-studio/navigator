# TASK-54: nav-pilot — Dispatch Handoff Skill (Navigator → Pilot)

**Status**: ✅ Implemented — 2026-06-15 (shipped in v6.16.0)
**Created**: 2026-06-15
**Assignee**: Manual

---

## Context

**Problem**: We use Navigator with Pilot frequently, but the handoff is manual.
Today `nav-task` emits a task doc and a human runs
`gh issue create --body-file .agent/tasks/TASK-XX.md` by hand, then has to
remember the `pilot` label and paste the resulting issue link somewhere.

**Goal**: A focused skill, `nav-pilot`, that owns the one-way dispatch: create
the `pilot`-labeled GitHub issue Pilot polls, and record the issue reference
back into the task doc.

**Scope decisions (confirmed with user 2026-06-15)**:
- Owns **dispatch handoff only** — one-way Navigator → Pilot.
- **No validation.** Spec checking is Pilot's job (its `spec_validator`); the
  skill does not lint the doc.
- Label is **`pilot`** so Pilot picks the issue up.
- Out: monitoring workers, pulling results back, full round-trip.
- Interface: **GitHub issues only** via `gh` CLI. No `pilot` binary/repo locally.

**Boundary with `nav-task`**: `nav-task` authors/archives docs; `nav-pilot`
consumes a finished doc and dispatches it. No authoring logic duplicated.

---

## Acceptance Criteria

- [ ] `nav-pilot` auto-invokes on "dispatch TASK-XX to Pilot", "hand off to Pilot",
      "send to Pilot", "queue for Pilot".
- [ ] Resolves the target doc (explicit `TASK-XX`, else the active task).
- [ ] Title derived from the doc's H1; body is the doc file (`--body-file`).
- [ ] Pre-flight confirmation shows title, label (`pilot`), repo, and a body
      summary before any network call; `--dry-run` prints the `gh` command
      without executing.
- [ ] On confirm, creates a `pilot`-labeled GitHub issue via `gh issue create`.
- [ ] Issue number/URL recorded into the doc's `## Refs`; status → `🚀 Dispatched`.

---

## Implementation

### Phase 1: Skill flow
**Goal**: Resolve → confirm → dispatch → record.

**Tasks**:
- [ ] `SKILL.md` with triggers, steps, ToM pre-flight checkpoint, `--dry-run`.
- [ ] Resolve doc + extract H1 title; build the `gh issue create` command:
      `gh issue create --label pilot --title <h1> --body-file <doc>`
      (repo defaults to the current git origin; `--repo` override optional).
- [ ] Record-back: edit the doc's `## Refs` + status line with the issue URL.

**Files**:
- `skills/nav-pilot/SKILL.md`

### Phase 2: Wiring & docs
**Tasks**:
- [ ] Register `./skills/nav-pilot` in `.claude-plugin/plugin.json`.
- [ ] Add `pilot` block to `.agent/.nav-config.json`
      (`label: "pilot"`, optional `repo`).
- [ ] Document in `CLAUDE.md`, `README.md`, `.agent/system/plugin-patterns.md`.
- [ ] Add `.agent/sops/integrations/pilot-handoff.md`.

**Files**:
- `.claude-plugin/plugin.json`, `.agent/.nav-config.json`, `CLAUDE.md`,
  `README.md`, `.agent/system/plugin-patterns.md`,
  `.agent/sops/integrations/pilot-handoff.md`

---

## Out of Scope

- **Validating the doc** against `spec_validator` — Pilot's responsibility.
- Monitoring Pilot workers / queue status.
- Pulling PR/results back and archiving completed issues.
- Direct `pilot` CLI invocation (no local repo/binary — `gh` only).

---

## Technical Decisions

| Decision | Options Considered | Chosen | Reasoning |
|----------|-------------------|--------|-----------|
| Skill boundary | extend nav-task vs new skill | new skill | One pattern per skill; nav-task authors, nav-pilot dispatches |
| Validation | lint locally vs delegate | delegate to Pilot | Confirmed: spec checking is Pilot's job, not ours |
| Issue interface | pilot CLI vs gh | `gh` | Confirmed: GitHub-only access |
| Target repo | configured vs current origin | current origin (override optional) | `gh` defaults to the repo you're in; least config |
| Safety on dispatch | auto-create vs confirm + dry-run | confirm + `--dry-run` | Outward-facing artifact; ToM high-stakes checkpoint |

---

## Verify

```bash
grep -q '"./skills/nav-pilot"' .claude-plugin/plugin.json   # registered
# Manual dry-run in /Users/aleks.petrov/Projects/tmp/nav-test:
#   "dispatch TASK-XX to Pilot" --dry-run  → prints gh command, no network
# Live:
#   gh issue list --label pilot   → shows the created issue
```

---

## Done

- [x] `nav-pilot` registered (`.claude-plugin/plugin.json`) and auto-invokes on trigger phrases
- [x] Dry-run path documented (`SKILL.md` Step 4) — prints command without executing
- [ ] Live dispatch verified end-to-end (deferred — would create a real issue)
- [x] SOP added (`.agent/sops/integrations/pilot-handoff.md`); `pilot` config block added

**Note**: `spec_validator` regex confirmed from marketplace.json v6.15.4 changelog:
`^##\s+(Acceptance|Implementation|Context|Background|Approach|Design|Refs)\b` —
structural any-match; polling label is deployment-configurable. Validates the
no-lint + configurable-`pilot`-label design.

---

## Refs

- Memory: pilot-navigator-relationship (data flow: doc → labeled issue → Pilot)
- `skills/nav-task/SKILL.md` (task doc this skill consumes)
- `skills/nav-skill-creator/SKILL.md` (skill authoring conventions)

---

## Notes

Shipping this skill is a release → version bump touches all 6 version files
(marketplace.json, plugin.json, README badge, CLAUDE.md, .nav-config.json,
RELEASE-NOTES) per the recorded version-bump correction.

**Last Updated**: 2026-06-15
