---
description: Release-readiness checklist before a release — verify tests, migration rollback, changelog, and version. Reports GO/NO-GO; leaves the git release to the user.
argument-hint: "[patch|minor|major]"
allowed-tools: [Agent, Read, Glob, Grep, Bash, Skill]
---

# /ship — Release-readiness check

Bump intent: **$ARGUMENTS**  (optional `patch|minor|major`)

You are the tech lead running a pre-release gate for **Mattin AI**. This command **verifies and reports** — it does not perform the GitFlow release (that lives in the GitHub Copilot `release-manager`; do not invade it).

## Checklist

1. **Branch state.** `git status` clean; on `develop` (or the intended release source); synced with origin.
2. **Tests green.** Run unit tests (`pytest tests/unit/ -v`) and, if the DB is available, integration (`./scripts/test.sh -m integration`). Report results; a failure is a NO-GO.
3. **Migrations.** Confirm every new Alembic migration has a working downgrade (`alembic upgrade head` then `alembic downgrade -1` then `alembic upgrade head` on a disposable DB if available, else inspect the migrations). Missing/irreversible downgrade = NO-GO.
4. **Production readiness & reliability.** Run the `production-readiness-analyst` and `reliability-auditor` agents (in parallel) on the changes since the last release tag (`git log <last-tag>..HEAD`); surface blocking gaps in observability/config/deploy and in concurrency/fault-tolerance/isolation.
5. **Version & changelog.** Read the current version in `pyproject.toml`; given the bump intent, state the target version (SemVer; develop carries `.devN`). Confirm `CHANGELOG.md` has entries covering the changes since the last tag; list anything undocumented.
6. **Dependencies.** Run `dependency-auditor` for any new CVE/license issues introduced since the last release.

## Output

A **GO / NO-GO** verdict with:
- the proposed target version,
- a checklist table (pass/fail per item),
- blocking items with `file:line`,
- the exact next step for the user (e.g. "all green — proceed with your release process" or "fix blockers X, Y first").

This command does not bump versions, tag, push, or open PRs. It reports.
