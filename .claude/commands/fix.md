---
description: Bug fix workflow — root-cause analysis, reproduce-first regression test, fix, review, and verification.
argument-hint: "<bug description>"
allowed-tools: [Agent, Read, Glob, Grep, Bash, Edit, Skill]
---

# /fix — Diagnose and fix a bug (reproduce-first)

Bug: **$ARGUMENTS**

You are the tech lead. Fix the bug properly: find the root cause, write a failing test, fix, prove the test passes, and audit.

## Steps

1. **Diagnose.** Run the `root-cause-analyst` agent on $ARGUMENTS. It returns the root cause with `file:line`, the blast radius, and a regression-test design (name, location, fixtures, assertion). If it cannot find the cause confidently, surface that to the user before changing code.

2. **Reproduce.** Invoke the `test-engineer` agent to write the regression test exactly as designed and run it — confirm it **fails for the right reason** on current code. (Skip only if the user explicitly opts out of a test.)

3. **Fix.** Invoke the appropriate expert (`backend-engineer` / `frontend-engineer` / `ai-engineer` / `database-engineer`) with the root cause and the concrete fix. Address sibling occurrences if the analyst found them.

4. **Verify.** Re-run the regression test — it must now pass. Run nearby tests to check for regressions.

5. **Audit.** Run the review board on the diff (per the `review-board` skill) and apply the self-correction loop for any CRITICAL/HIGH findings.

6. **Commit gate.** Via the `git-workflow` skill: stage the fix + test, show the staged diff and a `fix(scope): ...` message, **pause for `yes`**, then commit. Offer push/PR gates if the user wants a PR.

## Finish

Report: root cause, the regression test (and that it failed→passed), files changed, and findings fixed. Never push/PR without a gate.
