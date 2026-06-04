---
description: Spec-driven development — turn a request or issue into a formal spec + execution plan under .claude/specs/<slug>/.
argument-hint: "<feature request, or #issue number>"
allowed-tools: [Agent, Read, Glob, Grep, Bash, Skill]
---

# /spec — Create a spec and execution plan

Request: **$ARGUMENTS**

You are the tech lead orchestrating spec-driven development. Drive this sequence from the main conversation (subagents cannot spawn subagents — you pass each one's output to the next).

## Steps

1. **Context gathering.** If the request references a GitHub issue, first run the `issue-triager` agent to produce an Issue Analysis. Then run `codebase-explorer` to map the affected files, existing patterns, and reusable utilities for this request. Keep the returned context.

2. **Specification.** Invoke the `product-analyst` agent with the request + the gathered context. It writes `.claude/specs/<slug>/spec.md` (consult the `spec-driven` skill for the template) and registers it in `.claude/specs/index.yaml`. Derive `<slug>` (kebab-case) from the title.

3. **Resolve blockers.** If `spec.md` has blocking Open Questions, ask the user those questions now (use AskUserQuestion) and fold the answers in before planning.

4. **Architecture & plan.** Invoke the `solution-architect` agent with the finalized spec. It writes `.claude/specs/<slug>/plan.md`: architecture decisions + ordered, atomic steps, each assigned to one expert agent with FR/AC and gating auditors.

5. **Summarize.** Report the slug, the goals, the step list (agent per step), and any risks/open questions. Mark the spec `ready` when it is.

## Hand-off

End by telling the user: **"Spec `<slug>` is ready. Run `/implement <slug>` to execute it."** Do not start implementing — `/spec` only plans. Never commit (`.claude/specs/` is not tracked).
