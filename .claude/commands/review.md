---
description: Run the multi-auditor review board on the current diff and produce a prioritized report; with --fix, apply corrections and re-audit.
argument-hint: "[--fix] [base-ref]"
allowed-tools: [Agent, Read, Glob, Grep, Bash, Edit, Skill]
---

# /review — Multi-auditor review of the current diff

Args: **$ARGUMENTS**  (optional `--fix`; optional base ref, default `develop`)

You are the tech lead. Audit the working changes with the specialist review board and report.

## Steps

1. **Scope the diff.** Determine changed files: `git diff --name-status <base-ref>...HEAD` plus uncommitted changes (`git status --porcelain`, `git diff`). Default base `develop`.

2. **Select & run auditors.** Per the `review-board` skill, pick the auditors matching the touched files and run them **in parallel** (single message, multiple Agent calls) on the diff:
   - backend → `code-reviewer` + `security-auditor` + `performance-auditor` + `architecture-reviewer`
   - frontend → `code-reviewer` + `accessibility-auditor` + `performance-auditor`
   - models/migrations → `architecture-reviewer` + `performance-auditor`
   - AI/LangChain → `code-reviewer` + `security-auditor` + `architecture-reviewer`
   - dependency manifests → `dependency-auditor` + `security-auditor`

3. **Synthesize.** Deduplicate overlapping findings (same `file:line`), sort by severity, and present one consolidated report: CRITICAL → HIGH → MEDIUM → LOW, each with `file:line`, problem, and concrete fix.

4. **If `--fix`:** for CRITICAL/HIGH findings, invoke the appropriate expert(s) to apply the fixes, then re-audit only the changed files (self-correction loop, max 3 rounds). Leave MEDIUM/LOW as listed follow-ups unless the user asks. Do **not** commit — report what changed and let the user decide (or run `/implement`'s gate).

## Finish

Report the consolidated findings and, if `--fix` was used, what was fixed and what remains. This command does not commit or push.
