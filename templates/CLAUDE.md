# [Project Name] - Claude Code Configuration

## Context

[Brief project description - explain what this project does]

**Tech Stack**: [List your technologies, e.g., Next.js, TypeScript, PostgreSQL]

**Core Principle**: [Key architectural principle, e.g., "API-first design with type safety"]

**Last Updated**: 2026-10-20
**Navigator Version**: 8.4.11

---

## Navigator

**Navigator runtime**: workflow enforcement (session context, workflow gating, read
guarding, intent briefs, completion gating, compact markers) lives in the hook runtime,
not in prose in this file. Off-switches live in `.agent/.nav-config.json`: every hook
block has `enabled` (e.g. `workflow_enforcer_hook.enabled: false`), gating blocks also
take `strict_block: false` to warn instead of block, Tier-1 instant answers toggle per
rule under `tier1.rules` (feature-wide: `tier1.enabled`), and forced continuation stays
off unless `stop_completion.continue_enabled: true`. Setting the `PILOT_EXECUTOR`
environment variable disables interactive/blocking hook behavior for non-interactive
executors. Project docs live in `.agent/` — start from `.agent/DEVELOPMENT-README.md`
and load task/system/SOP docs on demand, not upfront.

---

## Project-Specific Code Standards

[Customize for your project's framework and patterns]

- **Architecture**: KISS, DRY, SOLID principles
- **TypeScript**: Strict mode, no `any` without justification
- **Line Length**: Max 100 characters
- **Testing**: High coverage (backend 90%+, frontend 85%+)

## Forbidden Actions

- ❌ No Claude Code mentions in commits/code
- ❌ No package.json modifications without approval
- ❌ Never commit secrets/API keys/.env files
- ❌ Don't delete tests without replacement

[Add project-specific violations here]
