# Example: a route report

The full form, with the state from the checkboxes (`--no-gh --today 2026-11-14`):

````markdown
# Route report: TASK-7 — Open Tasks shows the real status

_State from the checkboxes, 2026-11-14. The route has no tickets._

## 1. The goal

The session start lists only open work. Done documents are one count line.

## 2. The roadmap

**Phase 1: The gate reads the status line (1 of 3 done)**
- ✓ 1. Read the status from one shared function. — Not filed · Done
- ○ 2. Show done documents as one count line. — Not filed · Next
- ○ 3. Install the plugin on the build machine. — Operator step · Blocked: needs step 2

**Phase 2: Release (0 of 2 done)**
- ○ 4. Write the release notes. — Not filed · Later
- ○ 5. Announce the release. — Not filed · Blocked: needs steps 3 and 4

## 3. Side tracks

- ○ Repair the test target on macOS. — Not filed · Open

## 4. The queue now

Nothing is in the queue.

## 5. What waits for you

1. Decide the release number.
````

The short form one day later, after step 2 is done (`--short --since <marker>`):

````markdown
# Route report (short): TASK-7

- ✓ 2. Show done documents as one count line. — Not filed · Done  ← changed (was: Next)
- ○ 3. Install the plugin on the build machine. — Operator step · Next  ← changed (was: Blocked: needs step 2)
unchanged: 4
````

With `gh`, a ticket step shows its number and the live state, for example
`- ● 2. Show done documents as one count line. — PR #49 · In the queue now`.
