# TASK-XX: [Feature Name]

## Ticket
- **Ticket**: [Project Management URL]
- **Status**: In Progress / Completed
- **Sprint/Milestone**: [Name]
- **Assignee**: [Name]

---

## Context

[Explain WHY this feature is being built. What problem does it solve? What value does it provide?]

**Goal**: [Two or three plain sentences: the problem and the end state. nav-route prints them.]

---

## Route

<!-- The route in plain words: one line per step, no internal codes, no state words (the
     state comes from GitHub and the checkboxes). A trailing parenthesis holds the ticket
     (#12), "operator" for a step a person does, and "needs 1, 2". Read by nav-route and
     the /nav pane. Phases below hold the technical detail. -->

### Phase 1: [Phase Name]
- [ ] 1. [What this step does, in plain words]
- [ ] 2. [What the next step does] (needs 1)

### Side tracks
- [ ] [Work outside the main route]

### Waits for you
- [ ] [A decision or an action for the user]

---

## Implementation Plan

### Phase 1: [Phase Name]
- [ ] Sub-task 1 (TASK-XX.1)
- [ ] Sub-task 2 (TASK-XX.2)
- [ ] Sub-task 3 (TASK-XX.3)

### Phase 2: [Phase Name]
- [ ] Sub-task 4 (TASK-XX.4)
- [ ] Sub-task 5 (TASK-XX.5)

### Phase 3: [Phase Name] (Optional)
- [ ] Sub-task 6 (TASK-XX.6)
- [ ] Sub-task 7 (TASK-XX.7)

---

## Technical Decisions

### Technology Choices
- **Framework/Library**: [Choice] - [Reason]
- **Architecture Pattern**: [Choice] - [Reason]
- **State Management**: [Choice] - [Reason]

### Design Patterns
- [Pattern 1]: [Why it's used]
- [Pattern 2]: [Why it's used]

### Performance Considerations
- [Consideration 1]
- [Consideration 2]

---

## Dependencies

### Required
- **TASK-YY**: [Description of dependency]
- **Third-party service**: [What's needed]
- **Infrastructure**: [What needs to be set up]

### Blocks
- **TASK-ZZ**: [What this feature enables]
- **Future work**: [What depends on this]

---

## Implementation Notes

### File Structure
```
src/
├── [directory]/
│   ├── [new-file].ts
│   └── [modified-file].ts
```

### Key Components
1. **Component/Module 1**: [Purpose]
2. **Component/Module 2**: [Purpose]
3. **Component/Module 3**: [Purpose]

### Integration Points
- [System A]: [How it integrates]
- [System B]: [How it integrates]

---

## Testing Strategy

### Unit Tests
- [ ] [Component 1] unit tests
- [ ] [Component 2] unit tests
- [ ] [Utility function] tests

### Integration Tests
- [ ] [Integration scenario 1]
- [ ] [Integration scenario 2]

### E2E Tests (if applicable)
- [ ] [User flow 1]
- [ ] [User flow 2]

---

## Verify

Run these commands to validate the implementation:

```bash
# Run tests
[test command for this feature]

# Type check
[type check command]

# Build
[build command]
```

---

## Done

Observable outcomes that prove completion:

- [ ] [Specific file/API exists and exports expected interface]
- [ ] [Tests pass - specify count or coverage target]
- [ ] [Build succeeds without errors]
- [ ] [User-observable behavior works as specified]

---

## Completion Checklist

### Development
- [ ] All sub-tasks implemented
- [ ] Code follows project standards
- [ ] No linting errors
- [ ] Type safety verified

### Testing
- [ ] Unit tests written (target: 90%+ coverage)
- [ ] Integration tests written
- [ ] E2E tests written (if applicable)
- [ ] All tests passing

### Documentation
- [ ] Code comments added where needed
- [ ] System docs updated (if architecture changed)
- [ ] SOP created (if new pattern)
- [ ] README updated (if public-facing)

### Review & Deploy
- [ ] Code review completed
- [ ] PR approved and merged
- [ ] Deployed to staging
- [ ] Smoke tested in staging
- [ ] Deployed to production
- [ ] Post-deploy verification

### Finalization
- [ ] Ticket marked as completed
- [ ] Team notified (if significant feature)
- [ ] Documentation archived via `/nav:update-doc feature TASK-XX`

---

## Notes & Learnings

### Challenges Encountered
- [Challenge 1]: [How it was resolved]
- [Challenge 2]: [How it was resolved]

### Future Improvements
- [Improvement idea 1]
- [Improvement idea 2]

### Related SOPs Created
- [SOP 1]: [Link]
- [SOP 2]: [Link]

---

**Created**: [Date]
**Completed**: [Date]
**Total Time**: [Estimate]
