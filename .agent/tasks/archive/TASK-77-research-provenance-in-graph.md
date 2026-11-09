# TASK-77: Research provenance in the graph — fetch date + content hash on every cited URL

**Status**: ✅ Released v7.5.1 — 2026-09-14

## Context

**Problem**: nav-deep-research commits the report, the critic's findings and the graph
memories, but the fetched page bodies (`.agent/research/<slug>/sources/`) are gitignored
third-party text. A teammate reading a memory from the repo got the claim and a URL, and
no way to tell when the page was read or whether it has changed since. Worse, on the
first live report every Key findings bullet lost its citations on the way into the
graph: `report_parse.key_findings()` parsed line by line, writers wrap bullets at ~90
columns, and the `[n]` sat on the continuation line. Twelve memories would have carried
`nav-deep-research run <slug>` as evidence instead of URLs. The ship gate did not catch
it because `key-findings-typed` only checks the type prefix, which is on the first line.

**Contradiction resolved**: keeping the audit trail with the project worsens the repo
(third-party page bodies committed). Separation: the body stays local and refetchable;
the two facts that make a citation auditable later — fetch date and content hash — are
folded into the committed memory's evidence text. No graph schema change.

## Implementation

- `functions/report_parse.py` — `bullet_items()` joins a top-level `- ` bullet with its
  indented continuation lines; `key_findings()` parses the joined item, so wrapped
  bullets keep their cites and full text. Trailing punctuation no longer floats after
  cite removal (`"one [1]."` → `"one."`).
- `functions/report_to_graph.py` — `provenance_by_url()` reads the run's local source
  notes (`source_store.load_notes`) and maps every URL form a note carries (requested,
  final, canonical) to `fetched YYYY-MM-DD, sha256 <12 hex>`; blocked/skipped notes are
  excluded. `build_findings()` tags each cited URL: `https://… (fetched 2026-09-10,
  sha256 aab8bb007ea7)`. Notes missing (another machine, pruned run) → URL only, as
  before. `source_store.py refetch` reports `sha_match` against the same hash.
- Tests: wrapped-bullet regression, tag formatting, tag derived from a real note on disk,
  URL-only fallback without notes (74 in the skill's functions dir).
- Docs: `steps/6-ship.md`, CLAUDE.md Deep Research entry.

## Verification

- `make test` green.
- Dry-run on the v7.3.0 WebGPU report (22 sources, 12 findings): before the parser fix,
  0 of 12 memories carried a URL; after, 12 of 12 carry URLs and all 12 are tagged with
  fetch date and hash. Not ingested (off-topic for this repo's graph).
- Ship gate on the same report unchanged: fails only `summary-scannable` and
  `no-wall-of-text`, the two v7.4.0 layout checks TASK-75 documented for this report.

## Accepted limitations

- A 12-hex hash prefix, not the full digest: enough to detect drift on refetch, short
  enough to keep memory summaries readable.
- The tag proves which content version the run read, not that the claim is true. The
  critic pass remains the support check.
- Runs ingested before v7.5.1 keep their URL-only evidence; re-run
  `report_to_graph.py --run <slug>` on a machine that still has the notes to re-tag.
