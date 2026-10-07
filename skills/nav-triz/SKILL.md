---
name: nav-triz
description: Divergent solving for a declared contradiction ("improving X worsens Y"). Produces three competing candidates from different TRIZ separation modes, each with cost and downside, then recommends one. Auto-invoke when user says "find a better solution", "alternatives for", "resolve the contradiction", "triz this", or when a nav-brief declares a Contradiction on a substantial task.
version: 1.0.0
---

# Navigator TRIZ Skill

Navigator finds *a* solution fast. This skill exists for the minority of tasks where the
first fitting idea is a compromise: improving one thing worsens another. It forces three
genuinely different candidates onto the table before PLAN picks one, then records the
resolution so the next session can find it.

## When This Fires (and when it must not)

Fires when either:
- The user asks for it: "find a better solution for X", "alternatives for X", "resolve the
  contradiction", "triz this".
- A nav-brief `Contradict` row is not `none` AND the task is substantial (Task Mode
  complexity ≥ 0.5, or touching more than one subsystem).

Does NOT fire for routine work, a brief with `Contradict none`, "just do it" / "quick fix"
passthroughs, or when the user already named the approach. Ceremony is the failure mode of
this skill; when in doubt, skip it and say so in one line. (Resolved before: mem-060,
mem-074 — new blocking behaviour ships opt-in, by condition.)

## Protocol (one screen of output)

1. **State the contradiction** in one line, technical form ("improving A vs worsening B")
   or physical form ("X must be both A and not-A"). If you cannot, stop: there is no
   contradiction, proceed normally.
2. **Ideal Final Result**: what if the function existed with no new code? Name what would
   have to be true. If reachable, that is candidate 0 and usually the answer.
3. **Reuse inventory**: what already does ≥80% of this? `path:line` or `none found`.
4. **Prior resolutions + principle prompts**:
   ```bash
   PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
   [ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
   python3 "$PLUGIN_DIR/skills/nav-triz/functions/triz_suggest.py" \
     --contradiction "<improving A> vs <worsening B>"
   ```
   Prints decisions in this graph that resolved a related tension, then three principle
   prompts from different separation modes (generic trio if nothing matches). Read
   `reference/PRINCIPLES.md` only if a prompt is unclear.
5. **Three candidates**, one per prompt, in the table below. Each MUST name what it
   worsens. A candidate with no downside is a compromise misdescribed, or the IFR.
6. **Recommend one** with the reason in one sentence. Max one open question.
7. **After the work**, if the resolution was non-obvious, capture it:
   ```bash
   python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_manager.py" --action add-memory \
     --memory-type decision --summary "<what was chosen>" --concepts "<a,b>" \
     --contradiction "<A vs B>" --separation <time|space|condition|level> \
     --principle "<principle: concrete move>"
   ```

## Output Template

```
┌─ TRIZ: <short title> ─────────────────────────────────────────────┐
│ Contradiction  improving <A> vs worsening <B>                       │
│ IFR            <no-new-code version; reachable? yes/no>             │
│ Reuse          <path:line does X> | none found                      │
│ Prior          mem-NNN (<separation>) | none                        │
├───┬────────────┬───────────────────────────┬──────┬────────────────┤
│ # │ mode/prin. │ what changes              │ cost │ worsens        │
├───┼────────────┼───────────────────────────┼──────┼────────────────┤
│ 1 │ time / 10  │ ...                       │ S    │ ...            │
│ 2 │ cond / 15  │ ...                       │ M    │ ...            │
│ 3 │ level / 1  │ ...                       │ L    │ ...            │
├───┴────────────┴───────────────────────────┴──────┴────────────────┤
│ Recommend  #<n> — <one-sentence reason>                            │
└────────────────────────────────────────────────────────────────────┘
Open question (0-1): ...
```

Rules: three candidates, not five; different separation modes, not three variants of one
move; each row's "worsens" cell is mandatory; total output fits one screen.

## Hand-offs

- **nav-brief** → here when `Contradict` ≠ none on a substantial task. The brief's
  `Approach` cites the recommended candidate.
- **navigator-research agent** Phase 0.5 already produces IFR + reuse inventory; when it
  reports a contradiction, run this protocol in the main session (agents do not invoke
  skills).
- **Task Mode** RESEARCH phase lists this as the divergence step before PLAN.

## Predefined Functions

`functions/triz_suggest.py --contradiction "<A vs B>" [--graph-path P] [--limit 3] [--format text|json]`
Deterministic, stdlib, always exits 0. Keyword-ranks the ~20 mapped principles, picks one
per separation mode first, pads with prior action / dynamization / segmentation, and lists
prior decisions from the graph via `query_contradictions`.

## Related

- `reference/PRINCIPLES.md` — separation modes + mapped principles (lazy-load)
- `skills/nav-brief/SKILL.md` — Contradict row
- `skills/nav-graph/SKILL.md` Step 3B — capturing tagged decisions
