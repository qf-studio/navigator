---
name: nav-pilot
description: Dispatch a Navigator task doc to Pilot as a labeled GitHub issue. Use when user says "dispatch TASK-XX to Pilot", "hand off to Pilot", "send to Pilot", or "queue for Pilot". One-way handoff (Navigator authors the spec, Pilot executes autonomously).
allowed-tools: Read, Edit, Bash, Glob
version: 1.0.0
---

# Navigator → Pilot Dispatch Skill

Hand a finished Navigator task doc off to Pilot by creating the `pilot`-labeled
GitHub issue Pilot polls, then record the issue back into the doc.

**This skill does NOT validate the doc.** Spec checking is Pilot's job (its
`spec_validator`). nav-pilot only resolves the doc, creates the labeled issue,
and records the result. It consumes what `nav-task` authored — it does not
author or archive docs itself.

## When to Invoke

Invoke when the user says:
- "Dispatch TASK-XX to Pilot"
- "Hand this off to Pilot" / "send to Pilot"
- "Queue TASK-XX for Pilot" / "create the Pilot issue"

**DO NOT invoke** when:
- User is authoring/archiving a task doc (that's `nav-task`)
- User wants Pilot worker status (out of scope — this skill is one-way)
- No task doc exists yet (tell them to create one with `nav-task` first)

## Execution Steps

### Step 1: Resolve the Target Task Doc

- **Explicit ID** ("TASK-07"): use `.agent/tasks/TASK-07-*.md`.
- **No ID**: pick the active/in-progress task. If ambiguous, list candidates
  (`ls .agent/tasks/*.md`) and ask which one.
- If the file does not exist, stop and tell the user to author it first.

Read the doc and extract:
- **Title** = the first H1 (`# TASK-XX: <name>`), stripped of the `TASK-XX:` prefix
  if present (or keep the full H1 — match what Pilot expects).
- **Body file path** = the doc itself (passed via `--body-file`, never inlined).

### Step 2: Load Pilot Config

Read `pilot` from `.agent/.nav-config.json`:

```json
"pilot": {
  "enabled": true,
  "label": "pilot",
  "repo": null
}
```

- `label` (default `"pilot"`): the label Pilot polls for.
- `repo` (default `null`): target `owner/name`. When `null`, `gh` uses the
  current git repository's origin — do NOT pass `--repo`.

If `pilot.enabled` is `false`, stop and tell the user to enable it.

### Step 3: Build the Command

```bash
gh issue create \
  --title "<H1 title>" \
  --label "<pilot.label>" \
  --body-file ".agent/tasks/TASK-XX-<slug>.md" \
  [--repo "<pilot.repo>"]   # only when pilot.repo is set
```

### Step 4: Pre-flight Confirmation (ToM Checkpoint — high-stakes)

Creating a GitHub issue is an outward-facing action. ALWAYS confirm first:

```
About to dispatch to Pilot:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Repo:  <pilot.repo or "current origin (gh default)">
Title: <H1 title>
Label: <pilot.label>
Body:  .agent/tasks/TASK-XX-<slug>.md (<N> lines)

Command:
  gh issue create --title "..." --label "pilot" --body-file "..."
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Create this issue? [Enter to dispatch / "dry-run" / corrections]
```

**`--dry-run` mode**: if the user asked for a dry run (or says "dry-run" here),
print the exact `gh` command and STOP. Do not execute.

### Step 5: Dispatch

Run the `gh issue create` command. Capture the returned issue URL from stdout
(`gh issue create` prints the URL on success).

If `gh` fails:
- not authenticated → tell the user to run `gh auth login`
- label missing on the repo → offer `gh label create pilot`
- no git remote / repo not found → ask for `pilot.repo` in config

### Step 6: Record Back Into the Doc

Edit the task doc:
- Add the issue URL under `## Refs`:
  `- Pilot issue: <url>`
- Update the status line to `**Status**: 🚀 Dispatched to Pilot`.
- Update `**Last Updated**:` to today.

### Step 7: Confirm

```
✅ Dispatched to Pilot

Issue:  <url>
Label:  pilot
Task:   TASK-XX — <title>

Recorded back into .agent/tasks/TASK-XX-<slug>.md (status → 🚀 Dispatched).
Pilot will pick it up on its next poll of `pilot`-labeled issues.
```

If the knowledge graph is enabled, the Edit will sync via the normal
PostToolUse hook — no extra action needed.

## Error Handling

| Situation | Response |
|-----------|----------|
| No task doc found | Ask which task; suggest `nav-task` to create one |
| `pilot.enabled: false` | Stop; tell user to enable in `.nav-config.json` |
| `gh` not authenticated | Prompt `gh auth login` |
| `pilot` label missing | Offer `gh label create pilot` |
| No remote / repo unknown | Ask user to set `pilot.repo` |

## Success Criteria

- [ ] Correct task doc resolved and H1 used as the issue title
- [ ] Pre-flight confirmation shown before any network call
- [ ] `--dry-run` prints the command without executing
- [ ] Issue created with the `pilot` label
- [ ] Issue URL recorded back into the doc; status → 🚀 Dispatched

## Notes

- One-way by design: monitoring Pilot workers and pulling results back are out
  of scope (see `.agent/tasks/archive/TASK-54-nav-pilot-dispatch-skill.md`).
- Validation is intentionally absent — Pilot's `spec_validator` owns that.
- Pairs with `nav-task` (authors the doc) → `nav-pilot` (dispatches it).
