---
description: "Audit all open pull requests and integrate them into develop. @pr-triager produces a prioritized PR Health Report (drift, conflicts, CI, reviews), then offers handoff to @pr-integrator to update + squash-merge the safe ones behind confirmation gates."
agent: pr-triager
argument-hint: "Optional PR number to scope to a single PR (e.g. 168). Leave empty to audit all open PRs."
---

Audit the open pull requests for integration into `develop`${input:pr}.

Steps:

1. **Fetch** the latest refs (`git fetch origin --prune`) — read-only.
2. **List** every open PR with `gh pr list --state open` and the integration-relevant JSON fields (base, mergeable, mergeStateStatus, reviewDecision, isDraft, updatedAt, additions, deletions).
3. **Measure drift** for each PR: how far behind `origin/develop` its branch is, and whether the base is actually `develop`.
4. **Emit the PR Health Report** (see your agent definition for the exact format): the per-PR table + the recommended integration order (CLEAN/approved/small first; BEHIND-then-integrate next; isolate DIRTY/huge/stale — failing CI alone is not an isolation reason, the repo has known always-failing tests) + a Blockers & observations section that names policy gaps (e.g. no required reviews, oversized stale PRs).
5. **Recommend** and end with a one-paragraph summary. The handoff button to `@pr-integrator` appears automatically — clicking it integrates the safe PRs in order, updating from develop and squash-merging behind confirmation gates.

Stay read-only: run only read `gh`/`git` queries. Never merge, push, or update branches — that is `@pr-integrator`'s job, and only behind explicit confirmation.
