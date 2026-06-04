---
name: review-board
description: Audit protocol for the self-correction loop — severity rubric, auditor selection by file type, finding format, and convergence criteria. Background knowledge for /review, /implement, /production-audit.
user-invocable: false
allowed-tools: Read, Grep, Glob, Bash
---

# review-board — Audit & self-correction protocol

Defines how orchestrating commands audit a diff with a panel of specialist auditor subagents and drive the **self-correction loop** until the change converges.

## Auditor selection (by what the diff touches)

The orchestrator runs only the relevant auditors, **in parallel**, each on the same diff:

| Files touched | Auditors to run |
|---|---|
| `backend/**` (routers/services/repos) | `code-reviewer`, `security-auditor`, `performance-auditor`, `architecture-reviewer` |
| Concurrency-sensitive backend (counters/quotas, async fan-out, background tasks, external calls, sessions/pools) | + `reliability-auditor` |
| `backend/models/**`, `alembic/**` | `architecture-reviewer`, `performance-auditor` (+ migration-safety in `production-readiness-analyst`) |
| `backend/tools/ai/**`, LangChain/LangGraph code | `code-reviewer`, `security-auditor` (prompt-injection), `architecture-reviewer`, `reliability-auditor` (timeouts/fallbacks/checkpointer concurrency) |
| `frontend/**` | `code-reviewer`, `accessibility-auditor`, `performance-auditor` |
| `docker/**`, Helm charts, `deploy/**`, `backend/tasks/**`, `routers/controls/**` | `reliability-auditor`, `production-readiness-analyst` |
| `requirements*.txt`, `pyproject.toml`, `package.json` | `dependency-auditor`, `security-auditor` |
| Any production-bound change (full sweep) | + `production-readiness-analyst`, `reliability-auditor` |

Always include `code-reviewer` for code changes. Skip auditors whose domain the diff does not touch (don't run `accessibility-auditor` on a pure backend diff).

## Severity rubric

| Severity | Meaning | Loop behavior |
|---|---|---|
| **CRITICAL** | Security hole, data loss, broken auth/RBAC, crash, wrong result | MUST fix before commit |
| **HIGH** | Real bug, layering violation, N+1 on a hot path, missing validation | MUST fix before commit |
| **MEDIUM** | Maintainability, missing test, minor perf, a11y gap | Fix if cheap; else log as follow-up |
| **LOW / INFO** | Style, naming, optional improvement | Optional; note only |

## Finding format (every auditor returns this)

```
[SEVERITY] <short title>
- file: path/to/file.py:42
- problem: <what is wrong and why it matters>
- fix: <concrete change — not "improve this">
```

Auditors are **read-only**. They never edit; they report. The orchestrator feeds findings back to the implementing expert.

## Self-correction loop

```
round = 0
implement step  →  audit (parallel auditors)
while (CRITICAL or HIGH findings) and round < MAX_ROUNDS:
    re-invoke the SAME expert with the findings as the task
    re-audit ONLY the changed files
    round += 1
if still CRITICAL/HIGH after MAX_ROUNDS:
    stop, surface remaining findings to the user, mark step needs-revision
else:
    proceed to the commit confirmation gate
```

- `MAX_ROUNDS = 3` by default. Convergence is expected within 1-2 rounds; 3 unresolved rounds signals a design problem worth escalating to the user.
- Pass the **full finding text** to the expert, not a summary — the expert needs `file:line` and the concrete fix.
- Re-audit only the files the fix changed, to keep the loop fast and focused.
- MEDIUM/LOW findings never block the gate; collect them into the step's result and surface them in the final report.

## Synthesis (for /review and /production-audit)

After auditors return, the orchestrator **deduplicates** overlapping findings (same `file:line` from multiple auditors), sorts by severity, and presents one consolidated report. For `/production-audit`, also assign a rough **effort** (S/M/L) per finding and produce a prioritized roadmap (severity × effort).
