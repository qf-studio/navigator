# The route section of a roadmap or task document

A roadmap is a file in `.agent/roadmaps/` with a title, a `**Goal**:` paragraph and this
section. A task document has the section after its acceptance criteria. Write each step
line one time; do not write a state.

```markdown
## Route

### Phase 1: The gate reads the status line
- [x] 1. Read the status from one shared function. (#48)
- [ ] 2. Show done documents as one count line. (PR #49, needs 1)
- [ ] 3. Install the plugin on the build machine. (operator, needs 2)

### Phase 2: Release
- [ ] 4. Write the release notes.
- [ ] 5. Announce the release. (needs 3, 4)

### Side tracks
- [ ] Repair the test target on macOS. (#52)

### Waits for you
- [ ] Decide the release number.
```

| Part of a step line | Meaning |
|---|---|
| `- [ ]` / `- [x]` | The fallback state. A checked box is always done. |
| `2.` | The order number. A letter is permitted (`4a.`). |
| The text | What the step does, in plain words. An internal code is an error. |
| `(#49)`, `(PR #49)`, `(owner/repo#49)` | The ticket. No ticket shows as "Not filed". |
| `(TASK-12)` | The task document that holds the detail. Its Status line gives the state. |
| `(operator)` | A person does this step. It shows as "Operator step". |
| `(needs 1)`, `(needs 3, 4)` | The steps that must be done first. |
