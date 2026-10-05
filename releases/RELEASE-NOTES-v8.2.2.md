# Navigator v8.2.2 Release Notes

**Release Date**: 2026-10-05
**Type**: Patch — two `/nav` readability fixes (TASK-88 follow-ups)

## Fixed

- **The next row shows one sentence.** When the active task has no checklist, the band and
  the next card fall back to the reply's first line. A reply that opened with a two-sentence
  status showed a paragraph there. The fallback now keeps the first sentence only; a sentence
  ends at `.`, `!` or `?` followed by whitespace and a capital, digit or markup, so `v8.2.1`
  and `e.g. the` stay whole.
- **Rejects on two lines.** v8.2.1's `1 reject · 12:04 read_guard` still truncated the op name
  at ordinary terminal widths (`2 rejects · 13:15 st…`). The reads card now shows `2 rejects`
  (warning color when non-zero) over `13:15 stop_completion` (dim); no width can cut the op.

Tests: 147 kit tests (+1 for the sentence rule; the pane-model test covers both lines).
