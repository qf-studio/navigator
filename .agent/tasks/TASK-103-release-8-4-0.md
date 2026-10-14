# TASK-103: Release v8.4.0 — collector stack + session guard; docs site sync

**Status**: 📋 Planned — 2026-10-14
**Parent**: TASK-100 (part C)
**Effort**: S
**Depends on**: TASK-101, TASK-102

## Acceptance Criteria

- [ ] CHANGELOG entry + `releases/RELEASE-NOTES-v8.4.0.md`; version bump across marketplace.json,
      plugin.json, README badge, CLAUDE.md, `.nav-config.json`, release notes.
- [ ] `make release-check` green; tag pushed; release CI (dispatcher, conformance, hermetic
      hooks) green; `--verify-tag`; plugin updated to 8.4.0.
- [ ] Docs site (`navigator-site`, repo qf-studio/navigator-docs): dashboard page documents the
      collector + OTLP env; plugin-ops page lists the session-start metrics notice; `lib/version.ts`
      8.4.0; `prod-8.4.0-<ts>` tag; live version verified.
- [ ] TASK-100..103 archived; DEVELOPMENT-README in-flight header + stamp; marker created.

## Verify
- Release SOP `.agent/sops/deployment/release-workflow.md` steps 1–7 (incl. the four docs-site pitfalls).
