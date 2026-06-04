---
description: Generate or refine the technical execution plan (ordered steps) for an existing spec.
argument-hint: "<slug>"
allowed-tools: [Agent, Read, Glob, Grep, Skill]
---

# /plan — Build/refine the execution plan for a spec

Spec slug: **$ARGUMENTS**

Use this when a `spec.md` exists (from `/spec`) but the `plan.md` is missing, incomplete, or needs revision after spec changes.

## Steps

1. Read `.claude/specs/$ARGUMENTS/spec.md`. If it's missing, tell the user to run `/spec` first and stop.
2. If more codebase context is needed for sound step decomposition, run `codebase-explorer` for the specific areas.
3. Invoke the `solution-architect` agent to (re)write `.claude/specs/$ARGUMENTS/plan.md` per the `spec-driven` skill: architecture decisions + ordered, atomic, self-contained steps, each naming one expert agent, its FR/AC, dependencies, and the gating auditors (per the `review-board` skill).
4. Validate coverage: every FR and AC in the spec is satisfied by at least one step; step ordering respects dependencies (schema → backend → frontend; tests first for fixes; docs last).
5. Report the step list and any gaps.

## Hand-off

End with: **"Plan for `$ARGUMENTS` is ready. Run `/implement $ARGUMENTS`."** Never commit.
