---
description: Full production-readiness sweep of the app (or an area) — parallel auditors produce a prioritized roadmap of what's needed to ship to production.
argument-hint: "[area: backend|frontend|ai|security|all]"
allowed-tools: [Agent, Read, Glob, Grep, Bash, Skill]
---

# /production-audit — What's missing for production

Scope: **$ARGUMENTS**  (optional area; default `all`)

You are the tech lead commissioning a production-readiness assessment of **Mattin AI**. This is a whole-codebase (or whole-area) sweep, not a diff review.

## Steps

1. **Frame the scope.** Default to the full app. If an area is given, focus the auditors there. Optionally run `codebase-explorer` first to enumerate the modules/surfaces to cover so nothing is missed.

2. **Run the auditor panel in parallel** (single message, multiple Agent calls), each over its domain across the scoped code. They hold findings against the `production-standards` rubric:
   - `production-readiness-analyst` — observability, error handling, config, migrations/rollback, deploy, GO/NO-GO.
   - `reliability-auditor` (SRE) — **concurrency** (races, locking, idempotency, pools, async), **fault tolerance/resilience** (timeouts, retries, fallbacks, bulkheads, graceful shutdown), and **isolation** (tenant, fault, resource, network, runtime).
   - `security-auditor` — OWASP, authz/tenant isolation, secrets, CORS, LLM risks.
   - `performance-auditor` — N+1, blocking I/O, indexes, bundle/render.
   - `architecture-reviewer` — layering, coupling, pattern drift.
   - `accessibility-auditor` — WCAG (if frontend in scope).
   - `dependency-auditor` — CVEs, pinning, licenses.

3. **Synthesize a roadmap.** Deduplicate, group by dimension, sort by **severity × effort (S/M/L)**. Produce:
   - A one-paragraph **production verdict** (GO / NO-GO + the blocking items).
   - A prioritized table: blocker → high → medium → nice-to-have, each with `file:line`, impact, and a concrete fix + rough effort.
   - Suggested next actions (e.g. "create a spec for the top 3 blockers via `/spec`").

## Finish

Present the roadmap. This command is read-only — it neither edits nor commits. Offer to turn the top blockers into specs (`/spec`) or fixes (`/fix`).
