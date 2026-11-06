# SOP: Pilot's test gate is red on Navigator while CI is green

**Category**: debugging
**Created**: 2026-11-06
**Origin**: GH-40/41/42 — three Pilot tasks held `pilot-needs-human`, nine blind gate passes, two lost branches in one day.

## Symptoms

- The issue comment says "Held (pilot-needs-human): `make test` is red on main outside CI".
- The gate tail shows only `OK` lines and `make: *** [test] Error 1`.
- The board shows the same `GH-<n>` row failed several times in an hour, then `stalled`.

## Where the gate runs

- Founder box `i-0e0c1ca34e7b561f9` (eu-central-1, profile `quantflow`), 4 vCPU, Python 3.9,
  load 7–13 while a worker runs. CI pins Python 3.12 on an idle runner.
- The gate is `make test` from `internal/quality/runner.go`, run with the daemon's own
  environment (`os.Environ()` + `PILOT_CHANGED_*`), **5-minute cap**, and the feedback shows
  the **last 20 lines of stderr only**. Stdout is dropped.
- A failed run deletes its worktree and never pushes the branch.

## Procedure

1. **Reproduce on the box as the daemon user** (read-only):
   ```bash
   aws ssm send-command --instance-ids i-0e0c1ca34e7b561f9 --document-name AWS-RunShellScript \
     --parameters '{"commands":["sudo -u ec2-user env HOME=/home/ec2-user bash -c \"cd /var/lib/pilot/repos/startups/navigator && make test\" >/tmp/mt.out 2>/tmp/mt.err; echo rc=$?; sed -n \"/FAILED SUITES/,\\$p\" /tmp/mt.err"]}'
   ```
   The repo there needs `git -c safe.directory='*'`. Read the result with
   `aws ssm get-command-invocation`. The daemon log is `/home/ec2-user/.pilot/logs/daemon.log`;
   its "Failed to fetch issues" 503 lines are the Jira poller and are noise.
2. **Reproduce locally on Python 3.9** (Xcode ships 3.9.6):
   ```bash
   mkdir -p /tmp/py39 && ln -sf /Applications/Xcode.app/Contents/Developer/usr/bin/python3 /tmp/py39/python3
   PATH=/tmp/py39:$PATH make test
   ```
3. **Classify the red suite** from the `FAILED SUITES` block:
   - `TypeError ... |` at import or `sys.stdlib_module_names` → Python 3.9 incompatibility (mem-124).
   - `test_user_prompt_submit_p95_under_200ms` → host load; the budget scales with a measured
     interpreter start since 4341008, so a fresh failure means a real regression (mem-125).
   - `None != 5` in read_guard's double-fire test → a session variable in the environment
     (`PILOT_EXECUTOR`, `NAVIGATOR_MOD_OWNS`); `make test` scrubs them since 0e5a7e9.
   - No `FAILED SUITES` block but `Error 1` → the gate hit its 5-minute cap; check wall time.
4. **Before Pilot discards the branch**, back it up from the worktree:
   ```bash
   git -c safe.directory='*' -C /tmp/pilot-worktree-GH-<n>-* push origin HEAD:refs/heads/pilot/GH-<n>-wip
   ```
   (run as `ec2-user`). Review it by hand like PR #44/#45/#46 when the queue is slow.
5. **Fix on main, confirm CI green on both 3.9 and 3.12**, then **re-arm**:
   - failed row: cycle the `pilot` label;
   - stalled row (past 5 drops): remove `pilot-needs-human`, add `pilot-retry-ready`
     (the label event must postdate the stall), wait up to 16 minutes for the sweep
     (`GH-5212: stalled task re-armed`), then the poller dispatches (mem-127).
6. **"Task held: prerequisite not on main"** → a backticked repo path in the issue body does not
   exist on `origin/main` (gitignored runtime files, globs). Reword to prose; `gh issue edit`
   clears the hold on the next poll.

## What already protects this repo

- `Makefile test`: parallel suites, stderr-only output, env scrub, `FAILED SUITES` summary.
- `.github/workflows/test.yml`: matrix 3.9 (ubuntu-24.04) + 3.12.
- `hooks/test_nav_dispatch.py`: p95 budget × host slowdown.

## Related

- mem-123 (gate tail), mem-124 (3.9 floor), mem-125 (timing budget), mem-126 (slash-command
  recorder), mem-127 (re-arm recipe); `.agent/DEVELOPMENT-README.md` § GH-40…42.
