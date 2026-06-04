---
name: spec-driven
description: Templates and conventions for spec-driven development under .claude/specs/ (spec.md, plan.md, status.yaml, index.yaml). Background knowledge for planning and execution commands.
user-invocable: false
allowed-tools: Read, Write, Edit
---

# spec-driven — Spec & plan conventions

The single source of truth for how features are specified and executed in this Claude Code system. All artifacts live under `.claude/specs/` and are **never committed to git** (they are internal working docs; the guard hook blocks staging them).

## Directory layout

```
.claude/specs/
├── index.yaml                     # registry of all specs
└── <slug>/                        # kebab-case, 2-5 words
    ├── spec.md                    # WHAT & WHY (product-analyst)
    ├── plan.md                    # HOW: sequenced steps (solution-architect)
    ├── status.yaml                # execution manifest (/implement)
    └── decisions.md               # optional ADR log
```

`<slug>` is kebab-case derived from the feature title (e.g. `user-api-keys`, `s3-storage-garage`).

## index.yaml

```yaml
specs:
  - slug: user-api-keys
    title: "User API Key Management"
    status: draft            # draft → refining → ready → in-progress → implemented → archived
    created: "2026-06-04"
    updated: "2026-06-04"
    issue: "https://github.com/lksnext-ai-lab/ai-core-tools/issues/123"   # optional
    summary: "Let users create, rotate, and revoke personal API keys."
```

## spec.md template

```markdown
# <Feature Name>

> **Status**: draft | refining | ready | in-progress | implemented | archived
> **Slug**: <slug>   **Created**: YYYY-MM-DD   **Updated**: YYYY-MM-DD
> **Issue**: <URL or "none">

## Context
Why now? Current state of the system.

## Problem Statement
What problem, for whom.

## Goals
- ...

## Non-Goals
- Explicitly out of scope.

## Functional Requirements
### FR-1: <title>
<description>

## Non-Functional Requirements
### NFR-1: <title>
<performance / security / scalability / accessibility / observability>

## Acceptance Criteria
- [ ] AC-1: <testable criterion>
- [ ] AC-2: ...

## Edge Cases
- <boundary condition> → <expected behavior>

## Dependencies
- Depends on: ...   Blocks: ...

## Risks
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|

## Open Questions
- [ ] ...
```

## plan.md template

```markdown
# Execution Plan: <Feature Name>

> **Spec**: <slug>   **Base branch**: develop   **Feature branch**: <type>/<slug>

## Architecture Decisions
- AD-1: <decision> — <rationale> (alternatives considered)

## Steps
### step_001 — <short title>
- **Agent**: backend-engineer | frontend-engineer | database-engineer | ai-engineer | test-engineer | devops-engineer | docs-engineer
- **FR/AC**: FR-1, AC-1
- **Depends on**: none
- **Task**: <complete, self-contained prompt — the agent must not need to read the spec>
- **Expected outcome**: <deliverables, files touched>
- **Review board**: <which auditors run on this step's diff>

### step_002 — ...
```

Steps are atomic, ordered, and each names a single target agent and the auditors that gate it. Database changes precede the backend code that uses them; tests can come first for bug fixes (reproduce-first).

## status.yaml template

```yaml
slug: <slug>
branch: <type>/<slug>
started: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
overall_status: in-progress      # in-progress | completed | blocked
steps:
  - step: "001"
    title: "<title>"
    agent: backend-engineer
    status: pending              # pending | in-progress | in-review | needs-revision | done | blocked
    fr: ["FR-1"]
    ac: ["AC-1"]
    review_rounds: 0             # self-correction loop iterations consumed
    committed: false
```

## Status lifecycle

`spec.md` status: `draft → refining → ready → in-progress → implemented → archived`.
A spec must be `ready` before `/implement` runs. `/implement` sets it `in-progress`, then `implemented` once all FR/AC are covered and committed.

## Naming

- Requirements: `FR-N`, `NFR-N`, acceptance: `AC-N`.
- Extensions to a shipped spec: continue numbering (`FR-8`, `AC-6`) and continue step numbers — never restart.
