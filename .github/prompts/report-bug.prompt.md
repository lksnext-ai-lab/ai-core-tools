---
description: "Report a bug directly in chat (no GitHub issue needed). @bug-analyzer investigates the root cause and produces a Bug Analysis with a fix plan, then offers handoff to @quick-executor (small fix) or @feature-planner (large/architectural)."
agent: bug-analyzer
argument-hint: "Describe the bug — what happened, ideally steps + expected vs actual (e.g. 'playground freezes when uploading a PDF > 10MB')"
---

A bug has been reported: **${input:bug}**.

Steps:

1. **Parse the symptom** — what fails, where it surfaces, and any error text / stack trace included in the description.
2. **Clarify once only if needed** — if reproduction steps or expected-vs-actual are missing and you cannot infer them, ask exactly ONE focused question. Otherwise proceed.
3. **Investigate the root cause** — use `read` / `search` to trace the code path from symptom to cause; cite concrete `file:line` evidence. If the cause looks like a misused library API, verify against the `context7` / `docs-langchain` MCP before asserting it.
4. **Emit the Bug Analysis block** at the top of your response (see your agent definition for the exact format) — fully populated, grounded in real `file:line`. Include the **Suggested branch** (`fix/<short-slug>`) and a **regression test** that reproduces the bug.
5. **Recommend** a path: `@quick-executor` for a small/localized fix, `@feature-planner` if it's large/architectural.
6. **End** with a one-paragraph rationale, reminding the user that the downstream agent will create the `fix/` branch and execute **reproduce-first** (a failing regression test is written before the fix). The two handoff buttons appear automatically.

Do NOT fabricate a root cause: if you cannot locate it with confidence, mark `Confidence: low` and propose how to narrow it down (a log line, a breakpoint, a minimal failing test) instead of guessing.
