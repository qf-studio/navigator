# TASK-75: Readable research reports — answer-first layout for nav-deep-research

**Status**: ✅ Released v7.4.0 — 2026-09-12

## Context

**Problem**: the v7.3.0 pipeline produced correct, well-cited reports that were walls of
prose. The first live run's `## Summary` was one 1,969-character paragraph; ten blocks
in the body exceeded 700 characters. The writer contract fixed section names and the
citation form, nothing about layout, so the LLM writer defaulted to essay prose. The
same paragraph was then quoted verbatim to the user at ship time.

**Contradiction resolved**: a report dense enough to carry every cited nuance worsens
the reader's ability to get the answer from the first screen. Separation in structure:
the Summary is a fixed answer-first block (Answer line, bullets, counter-position), the
detail moves into per-item sections with a lead sentence and "What the sources show"
bullets, and comparisons go into an At-a-glance table. The prose density stays; the
shape changes.

## Implementation

- `skills/nav-deep-research/reference/REPORT-FORMAT.md` (new) — the layout, the rules,
  the fix path for each gate failure, an abridged example. The writer reads it at step 3;
  the orchestrator uses it to fix gate failures.
- `functions/report_parse.py` — `summary_structure()` (Answer line + bullet count),
  `paragraphs()` / `long_paragraphs()` (prose blocks before Sources; bullets measured
  item by item; tables, headings, fenced code exempt); `REQUIRED_SECTIONS` now includes
  `Open questions`; constants `MAX_PARAGRAPH_CHARS = 700`, `MIN_SUMMARY_BULLETS = 2`.
- `functions/ship_gate.py` — two new checks, twelve in total: `summary-scannable`
  and `no-wall-of-text` (detail names the section and the first words of each
  offending block). Same rule as before: fixed in the report, never in the gate.
- `agents/deep-research-writer.md` — takes `report_format`, reads it first, plans the
  At-a-glance table and the Answer sentence before writing; skeleton updated.
- `agents/deep-research-patcher.md` — keeps the cap when applying hunks; never merges
  bullets into prose; keeps the Answer line.
- `steps/3-draft.md` — passes `report_format` (`"${NDR%/functions}/reference/…"`); the
  pre-check now covers the six structural checks.
- `steps/6-ship.md` — ship message is a short bullet block followed by the Summary
  verbatim, which is now the reader's first screen by construction.
- Tests: `test_ship_gate.py` fixture rewritten to the new layout; new cases for the
  Answer line, bullet minimum, wall detection with section naming, table/code/bullet
  exemptions, Open questions required.

## Verification

- `make test` green (70 tests in the skill's functions dir; full suite unchanged).
- New gate run on both v7.3.0 reports: 10/12 pass; the two failures are exactly
  `summary-scannable` and `no-wall-of-text` (the defect this task fixes). Shipped runs
  keep their `ship.json`; the gate is not re-run on finished runs.
- Writer A/B on identical inputs: the WebGPU run's 22 source notes and atomic items
  seeded into a scratch run; one writer spawned with the new prompt; new gate run with
  `--no-write`: 12/12 pass; 0 blocks over the cap (was 10), longest block 323 chars
  (was 1,969), 59 bullets (was 29), same 22 sources and 12 typed findings. Full table
  in `releases/RELEASE-NOTES-v7.4.0.md`. The scratch run was deleted afterwards.

## Accepted limitations

- The cap is a character count, not a readability score. Five long sentences pass.
- The critic does not judge layout; the gate does. A patcher hunk that overflows the
  cap is caught at step 6 and split by the orchestrator.
- Existing reports are not reformatted. A `refetch` + rerun produces the new layout.
