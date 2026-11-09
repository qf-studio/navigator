# Pilot Handoff (Navigator → Pilot)

**Purpose**: Dispatch a finished Navigator task doc to Pilot as a labeled GitHub issue
**When to use**: A `TASK-XX.md` is ready and you want Pilot to execute it autonomously
**Skill**: `nav-pilot`
**Last Updated**: 2026-06-15

---

## Model

```
nav-task  →  TASK-XX.md  →  nav-pilot  →  gh issue (label: pilot)  →  Pilot polls & runs
(author)     (the spec)     (dispatch)     (the handoff)              (executes)
```

One-way. Navigator authors the spec; Pilot executes. Validation is **Pilot's**
job (`spec_validator`) — nav-pilot does not lint the doc.

## Quick Start

```
"Dispatch TASK-07 to Pilot"
```

The skill resolves the doc, shows a pre-flight confirmation, then runs:

```bash
gh issue create --title "<doc H1>" --label "pilot" --body-file .agent/tasks/TASK-07-*.md
```

and records the issue URL back into the doc (status → 🚀 Dispatched).

## Configuration

`.agent/.nav-config.json`:

```json
"pilot": {
  "enabled": true,
  "label": "pilot",
  "repo": null
}
```

- `label`: the label Pilot polls for (default `pilot`).
- `repo`: `owner/name` to target. Leave `null` to use the current repo's origin
  (`gh` default). Set it when Pilot watches a different repo than the one you
  author docs in.

## Prerequisites

- `gh` installed and authenticated (`gh auth login`).
- The `pilot` label exists on the target repo (`gh label create pilot` if not).

## Dry Run

Ask for a dry run to print the command without creating anything:

```
"Dispatch TASK-07 to Pilot, dry-run"
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `gh: not authenticated` | `gh auth login` |
| `could not add label: 'pilot' not found` | `gh label create pilot` |
| `no git remote` / repo not found | Set `pilot.repo` in `.nav-config.json` |
| Pilot never picks it up | Confirm the label matches Pilot's poll filter |

## Out of Scope

Monitoring Pilot workers and pulling results/PRs back are deliberately not part
of this handoff — see `.agent/tasks/archive/TASK-54-nav-pilot-dispatch-skill.md`.
