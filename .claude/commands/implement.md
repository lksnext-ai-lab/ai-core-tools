---
description: Execute a spec's plan step-by-step with the self-correction loop (expert → review board → fix → re-audit) and confirmation-gated commits.
argument-hint: "<slug> [step]"
allowed-tools: [Agent, Read, Glob, Grep, Bash, Edit, Skill]
---

# /implement — Execute a plan with self-correcting review

Target: **$ARGUMENTS**  (spec slug, optionally a single `step_NNN`)

You are the tech lead. You execute the plan from the main conversation, spawning one expert per step, auditing each step's diff with the relevant review board, looping until it converges, then committing behind confirmation gates. **This is the heart of the system — do not skip the audit loop.**

## Setup

1. Read `.claude/specs/<slug>/plan.md` and `status.yaml` (create `status.yaml` from the `spec-driven` template if absent). If no plan exists, tell the user to run `/spec` or `/plan` and stop.
2. Ensure a feature branch via the `git-workflow` skill (off `develop`, named per the plan). Working tree must be clean.
3. Set the spec status to `in-progress`.

## Per-step loop (for each pending step, respecting dependencies)

1. **Implement.** Invoke the step's assigned expert (`backend-engineer` / `frontend-engineer` / `database-engineer` / `ai-engineer` / `test-engineer` / `devops-engineer` / `docs-engineer`) with the step's full self-contained task. Run any `## Terminal Commands Required` the expert returns (e.g. `alembic upgrade head`, `pytest`).

2. **Audit (review board).** Per the `review-board` skill, select the auditors for the files this step touched and run them **in parallel** (single message, multiple Agent calls) on the diff. Collect findings.

3. **Self-correct loop.** While there are CRITICAL or HIGH findings and rounds < 3:
   - Re-invoke the **same expert** with the full finding text (file:line + concrete fix) as its task.
   - Re-audit only the changed files.
   - increment round.
   If CRITICAL/HIGH remain after 3 rounds → stop the step, mark it `needs-revision` in `status.yaml`, surface the remaining findings, and ask the user how to proceed. MEDIUM/LOW never block — collect them as follow-ups.

4. **Verify.** For steps with tests, ensure the relevant tests pass (`test-engineer` or run `pytest -k ...`).

5. **Commit gate.** Via the `git-workflow` skill: stage only the application files this step changed (never `.claude/specs/**` or secrets), show `git diff --staged --name-status` + the Conventional Commits message, and **pause for the user's `yes`** before committing.

6. Update `status.yaml` (status `done`, `review_rounds`, `committed: true`).

## Finish

When all steps are `done`: optionally run a final `/review` pass on the full branch diff. Then offer the **push** and **PR** confirmation gates (via `git-workflow`). Set the spec status to `implemented`. Report a summary: steps done, findings fixed, follow-ups (MEDIUM/LOW), and the branch/PR.

Never push or open a PR without an explicit gate. Never commit `.claude/specs/`.
