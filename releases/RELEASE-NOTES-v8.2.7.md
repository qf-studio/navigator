# Navigator v8.2.7 Release Notes

**Release Date**: 2026-10-05
**Type**: Patch — in-progress task detection reads the Status line (TASK-91)

## Fixed

- **A finished task no longer shows as the destination.** The `/nav` next card and the
  compact marker's "In-progress tasks" list decided "in progress" by substring over the whole
  head of a task doc, so TASK-67 (shipped in July, its doc quotes `In Progress` in prose) stayed
  the destination for three months. TASK-67 had fixed exactly this for the knowledge graph;
  two other parsers were left behind. One predicate on both runtimes now reads the
  `**Status**` line alone (🚧 or the whole-word phrase "in progress"); docs without a Status
  line keep the legacy head scan. The pane lists task docs through the engine's file API
  instead of a shell grep.

Tests: Python `InProgressPredicateTests` (+5), kit `nav` TASK-91 cases (+3), lifeops fixtures
with the prose-only, `**Status:**` and `> Status:` forms; pane tests seed real task docs
(153 kit tests). Task doc: `.agent/tasks/TASK-91-in-progress-status-line.md`.
