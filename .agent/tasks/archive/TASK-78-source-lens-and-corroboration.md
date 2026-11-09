# TASK-78: Source lens and corroboration — rank by provenance, not by score

**Status**: ✅ Released v7.6.0 — 2026-09-14

## Context

**Problem**: the pipeline plans searches from three lenses (breadth, canonical,
adversarial) but threw the lens away at the queue. Every note in the first live run read
`suggested_by: seed`, so nothing downstream could tell a spec from a blog a generic
search happened to surface. Counting that run by hand after a question on LinkedIn: 22
sources, 14 primary by domain, 12 of 17 finding citations to primary sources — but four
findings rested on a single secondary source, and five weak sources (news re-posts, a
forum thread, two SEO blogs) padded the body without ever reaching a finding. Selection
and critique did the filtering; nothing recorded or enforced it.

**Contradiction resolved**: ranking sources by quality improves trust and worsens
determinism — a quality score is a model opinion wearing a metric's clothes, and the
gate only keeps checks a script can settle. Separation: record provenance at fetch time
(the lens is a fact about which search found the URL, not a judgment of the source), and
let the gate reason about provenance instead of quality.

## Implementation

- `functions/source_store.py` — `LENSES = (breadth, canonical, adversarial, gap)`,
  `DEFAULT_LENS = "unspecified"`, `normalize_lens()`. `store_note()` normalizes into the
  existing `suggested_by` field (no new frontmatter key; the field already meant this).
  Unknown values degrade to `unspecified` rather than failing a fetch. `--lens` is the
  new flag name on `fetch` and `write`, with `--suggested-by` kept as an alias. `digest()`
  emits a `lens:` line so the writer can fill the Sources column.
- `functions/report_parse.py` — `sources_table()` returns a `lens` per row, parsing an
  optional fifth column; pre-TASK-78 four-column tables and unknown values come back as
  `unspecified`.
- `functions/ship_gate.py` — thirteenth check `findings-corroborated`: no Key finding may
  rest on a single `breadth`-lens source. A single `canonical` or `adversarial` source
  passes — a spec, a vendor doc or a bug report can stand alone. Skipped with a pass when
  the table carries no lens data, so old reports still gate.
- `agents/deep-research-critic.md` — fifth pass, **Corroboration**: flag the same case at
  severity major before the gate sees it, fix by citing a corroborating source already on
  disk or moving the claim to Open questions. Explicitly not a reputation ranking.
- `agents/deep-research-writer.md`, `reference/REPORT-FORMAT.md` — Sources table gains the
  `lens` column, copied from the note; the corroboration rule and its fix path.
- `steps/2-sweep.md` — the queue carries the lens, the batch table is `url | atomic_item |
  lens`, gap-wave rows are tagged with the lens that found them or `gap`. Carry it
  accurately: relabelling a breadth hit as canonical is the one way to defeat the check.
- `steps/6-ship.md` — fix path for the new check, and the rule that a lens is never
  relabelled to make the gate pass.
- `agents/deep-research-fetcher.md` — batch row and `--lens` pass-through, never re-judged.

## Verification

- `make test` green; 81 tests in the skill's functions dir (7 new: lens vocabulary,
  storage, digest, optional column parsing, and the three gate cases).
- End-to-end on a scratch run: four notes stored with distinct lenses through the CLI,
  `digest` shows each lens, a report citing a single `breadth` source fails
  `findings-corroborated` naming the finding, and passes after a corroborating citation
  is added. All 13 checks ran.
- The v7.3.0 WebGPU report (no lens column) still evaluates: the new check passes with
  "no lens data in the Sources table", and the only failures remain the two v7.4.0
  layout checks TASK-75 documented for it.
- `--suggested-by` alias verified against the pre-TASK-78 fetcher command shape.

## Accepted limitations

- The lens is self-reported by the orchestrator. Nothing verifies that a URL tagged
  `canonical` really is a spec; the prompts say carry it accurately and the gate detail
  names the finding, so a relabel is visible in review rather than blocked.
- `breadth` is the only lens the gate treats as weak. A single `adversarial` source can
  still be a forum post; the critic's Corroboration pass is the softer net for that.
- Existing runs keep `unspecified` and are exempt. Re-fetching is the only way to
  backfill a lens, and it is not worth it for a shipped run.
- The `min_sources` floor of 8 may be what invites weak sources into the body at all.
  One run is not evidence; revisit after the next live run rather than tuning it now.
