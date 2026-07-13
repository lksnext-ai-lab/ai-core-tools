---
description: "Audit, verify, and integrate open pull requests into develop. Three gated stages: @pr-triager produces a prioritized PR Health Report (drift, conflicts, CI, reviews) → @pr-verifier confirms each candidate meets its goal and does not regress develop (differential targeted tests) → @pr-integrator updates + squash-merges the PASS ones behind confirmation gates."
agent: pr-triager
argument-hint: "Optional PR number to scope to a single PR (e.g. 168). Leave empty to audit all open PRs."
---

Audit the open pull requests for integration into `develop`${input:pr}.

This runs as a three-stage, gated pipeline:

1. **Triage (`@pr-triager`, read-only)** — audit every open PR and emit the prioritized PR Health Report.
2. **Verify (`@pr-verifier`)** — for each integrable candidate, confirm it does what its goal/linked issue asks and does not regress develop, then emit a PASS/RISK/FAIL verdict.
3. **Integrate (`@pr-integrator`)** — update from develop and squash-merge the PASS PRs behind confirmation gates.

### Stage 1 — Triage (you, `@pr-triager`)

1. **Fetch** the latest refs (`git fetch origin --prune`) — read-only.
2. **List** every open PR with `gh pr list --state open` and the integration-relevant JSON fields (base, mergeable, mergeStateStatus, reviewDecision, isDraft, updatedAt, additions, deletions).
3. **Measure drift** for each PR: how far behind `origin/develop` its branch is, and whether the base is actually `develop`.
4. **Emit the PR Health Report** (see your agent definition for the exact format): the per-PR table + the recommended integration order (CLEAN/approved/small first; BEHIND-then-integrate next; isolate DIRTY/huge/stale — failing CI alone is not an isolation reason, the repo has known always-failing tests) + a Blockers & observations section that names policy gaps (e.g. no required reviews, oversized stale PRs).
5. **Recommend** and end with a one-paragraph summary.

Stay read-only: run only read `gh`/`git` queries. Never merge, push, or update branches.

### Handoff

The **"Verify PRs with @pr-verifier"** button appears automatically — it verifies the candidates (correctness vs goal + differential targeted tests) and then hands the PASS PRs to `@pr-integrator`. A **"skip verification"** button that goes straight to `@pr-integrator` is also available for trivial batches, but verification is the recommended path.
