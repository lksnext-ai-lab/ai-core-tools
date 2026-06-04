---
description: End-to-end issue resolution — triage a GitHub issue, route to spec or direct implementation, execute with review, and gate the PR.
argument-hint: "<#issue number or URL>"
allowed-tools: [Agent, Read, Glob, Grep, Bash, Edit, Skill]
---

# /solve-issue — Resolve a GitHub issue end-to-end

Issue: **$ARGUMENTS**

You are the tech lead. Take a GitHub issue from triage to an open PR, choosing the right depth of process.

## Steps

1. **Triage.** Run the `issue-triager` agent on $ARGUMENTS. It emits an Issue Analysis (type, affected areas, candidate FR/AC, scope, suggested branch, recommended path).

2. **Route on scope:**
   - **Large / architectural / schema change / multi-area** → run `/spec` with the issue + Issue Analysis to produce a spec & plan, then `/implement <slug>`.
   - **Small / single-area feature** → skip the formal spec; build a short inline step list and run the `/implement` per-step loop (expert → review board → fix → gated commit) directly.
   - **Bug** → run `/fix` with the issue context (reproduce-first).

3. **Execute** the chosen path. Always apply the review-board self-correction loop on each change (per the `review-board` skill).

4. **Verify** the acceptance criteria are met (run tests; for UI, suggest `/verify` or a manual check).

5. **PR gate.** Via the `git-workflow` skill, after the push gate, open the PR against `develop` with a body that references the issue (`Closes #<n>`), the FR/AC covered, and the review summary. **Pause for the user's `yes`** before `gh pr create`.

## Finish

Report: the route taken, what changed, findings fixed, test results, and the PR link. Never push or open a PR without a gate. Never commit `.claude/specs/`.
