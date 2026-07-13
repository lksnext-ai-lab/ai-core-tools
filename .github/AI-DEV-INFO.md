# .github — AI-Driven Development Infrastructure

This directory contains the configuration for GitHub-native tooling and a structured multi-agent AI development workflow built on GitHub Copilot.

## Directory Structure

```
.github/
├── agents/                      # Specialized Copilot agents (18 — see Agent map below)
├── instructions/                # Path-scoped instruction files (alembic, docs, git-github, handoff, plan-extensions)
├── prompts/                     # Slash-command prompt files (start-from-issue, report-bug, quick-execute, integrate-prs)
├── skills/                      # Shared procedural definitions
├── workflows/                   # GitHub Actions CI/CD pipelines
├── copilot-instructions.md      # Master repo-wide guidance
├── AI-DEV-INFO.md               # This file — index of the AI dev infrastructure
└── PULL_REQUEST_TEMPLATE.md     # PR submission template
```

> **Workspace settings**: `.vscode/settings.json` (at repo root) registers `.github/instructions` and `.github/prompts` so VS Code Copilot auto-discovers them. Make sure your VS Code Copilot extension is up to date.

---

## Agents (`agents/`)

Invoke any agent with `@<agent-name>` in GitHub Copilot Chat. Each agent has a tightly scoped domain and delegates to others rather than duplicating work.

### Agent map (delegation overview)

```
Issue-Driven Entry (start here when work begins from a GitHub issue):
  @issue-reader ──► @feature-planner ──► @plan-executor ──► implementer subagents  (formal, with spec)
                └─► @quick-executor ──► implementer subagents                       (ad-hoc, no spec)

Bug-Driven Entry (start here when a bug is reported in chat, no GitHub issue):
  @bug-analyzer ──► (triage: not a code defect? → verdict + remedy + STOP)
                ├─► @quick-executor ──► implementer subagents   (small fix, reproduce-first; executor files the tracking issue, gated)
                └─► @feature-planner ──► @plan-executor ──► ... (large/architectural fix, with spec)

Ad-hoc Execution (small tasks):
  @quick-executor ──► @backend-expert   ┐
                  ├──► @react-expert    │ auto-invoked as subagents
                  ├──► @alembic-expert  │ (file ops only, no terminal)
                  ├──► @test-expert     │
                  └──► @docs-manager    ┘
                  └── git / gh CLI   ──► (run directly by quick-executor — terminal access)

Feature Lifecycle (formal, spec-driven):
  @feature-planner ──► @plan-executor ──► @backend-expert  ┐
                            │          ├──► @react-expert   │ auto-invoked subagents
                            │          ├──► @alembic-expert │ (file ops only;
                            │          ├──► @test-expert    │  alembic & test return
                            │          └──► @docs-manager   ┘  Terminal Commands)
                            │
                            └── git / gh CLI  ──► (run directly by plan-executor — terminal access)

Release Lifecycle:
  @release-manager ──► @version-bumper  (subagent, file ops)
                   ├──► @oss-manager    (subagent, file ops)
                   ├──► git / gh CLI    (run directly by release-manager)
                   └── @website-maintainer  (cross-repo sync of mattinai.github.io after release)

PR Integration Entry (start here to land open PRs into develop):
  @pr-triager ──► audits all open PRs (drift vs develop, conflicts, CI, reviews) → PR Health Report + order
              └─► @pr-verifier ──► per candidate: check out merged onto develop (local) → confirm it meets its goal/AC
              │                    → DIFFERENTIAL targeted tests (baseline develop vs PR → only NEW failures) → PASS/RISK/FAIL
              └─► @pr-integrator ──► per PASS PR: update from develop → squash-merge (gated) → delete branch
                                     (on conflicts: opt-in assisted resolution via experts, double-gated + diff review; never merges red / unreviewed / DIRTY)

AI Environment:
  @ai-dev-architect ──► (creates/maintains all .github/ artifacts: agents, instructions, prompts, skills)
```

> **`@issue-reader` is the canonical entry point** when you start from a GitHub issue. It reads the issue via the built-in `@github` MCP server, emits an Issue Analysis block, and offers two handoff buttons:
> - **"Plan formally with @feature-planner"** — features, schema changes, multi-area work (tracked in `/plans/`)
> - **"Execute autonomously with @quick-executor"** — bugs, small fixes, single-area work (no spec, end-to-end auto)
>
> You can also invoke it via the slash command `/start-from-issue 123`.

> **`@bug-analyzer` is the canonical entry point** when a bug is reported directly in the chat (no GitHub issue). It investigates the codebase to locate the root cause, emits a **Bug Analysis** block with `file:line` evidence + a regression test, and offers two handoff buttons:
> - **"Fix now with @quick-executor"** — small/localized fixes (most bugs), executed **reproduce-first** (failing test before the fix)
> - **"Plan formally with @feature-planner"** — large/architectural fixes that deserve a tracked spec
>
> Before investigating it **triages** whether the report is even a code defect — if it's config/infra/data/expected/upstream/duplicate it emits a verdict with the real remedy and **stops** (no fix machinery). For genuine code bugs it also emits a ready-to-file **Issue body**; the executor files the GitHub tracking issue (gated, skippable) and the PR closes it with `Closes #N`.
>
> Invoke directly (`@bug-analyzer <description>`) or via the slash command `/report-bug`. It is read-only and runs on Claude Sonnet 5 because root-cause diagnosis is the highest-risk step — a wrong hypothesis wastes the whole downstream fix.

> **`@quick-executor` vs `@plan-executor`**: Both auto-invoke implementer subagents and run git directly with commit/push/PR confirmation gates. The difference is the input:
> - **`@quick-executor`** takes a task description (from an Issue Analysis or directly from you) and decides the subagent sequence on the fly. No spec file, no `/plans/` artifacts. Use for **ad-hoc tasks ≲ 5 files**.
> - **`@plan-executor`** reads a structured spec at `/plans/<slug>/spec.md` (produced by `@feature-planner`) and executes its FR/AC step by step with a tracked `status.yaml`. Use for **features that benefit from a tracked specification**.
>
> Both share the same 3 confirmation gates: **commit**, **push**, **PR**. Everything else is automatic.

> **Why `@git-github` is not used as a subagent**: it requires terminal execution (`tools: [execute]`), which is unavailable in subagent context. Agents that need git operations either run commands directly via the `git-github.skill.md` skill (`@plan-executor`, `@release-manager`) or hand off to the user with a change summary for them to invoke `@git-github` directly (`@backend-expert`, `@react-expert`, `@alembic-expert`, `@test-expert`, `@docs-manager`).

> **Direct invocation by the user** (never as subagents): `@git-github`, `@issue-reader`, `@bug-analyzer`, `@pr-triager`, `@pr-verifier`, `@pr-integrator`.

---

### `@issue-reader`

**Purpose**: Entry point for issue-driven development. Reads a GitHub issue via the built-in `@github` MCP server, distills it into a structured **Issue Analysis** block, and offers two handoff buttons so the user picks the right next agent.

**Key capabilities**:
- Resolves issue references in three forms: `123`, `owner/repo#123`, full GitHub URL
- Uses the GitHub MCP server (`mcp-servers: ['github']`) to fetch title, body, labels, assignees, milestone, comments
- Cross-checks the codebase (`read`/`search`) to verify entities and paths mentioned actually exist
- Recommends `@feature-planner` (features, multi-area, schema change) or `@quick-executor` (bug, small fix, single-area)
- Read-only — never edits code, commits, or modifies the issue on GitHub

**Invocation**:
- `@issue-reader 123` — number defaults to repo `lksnext-ai-lab/ai-core-tools`
- `@issue-reader owner/repo#123` — cross-repo
- `@issue-reader https://github.com/owner/repo/issues/123` — full URL
- `/start-from-issue 123` — slash command equivalent

**Hands off to** (user clicks one):
- `@feature-planner` — formal plan in `/plans/<slug>/spec.md` with `issue_link` set
- `@quick-executor` — autonomous ad-hoc execution, seeded from the Issue Analysis (Suggested branch + subagent sequence derived from Scope)

**Never does**:
- ❌ Write application code, commits, or migrations
- ❌ Modify the issue on GitHub
- ❌ Invent issue content if the MCP server is unavailable (asks the user to paste instead)

**Requires**: the `@github` MCP server to be active in VS Code (`Manage MCP Servers`).

---

### `@bug-analyzer`

**Purpose**: Entry point for bugs reported directly in the chat (no GitHub issue). First **triages** whether the report is a code defect (vs config/infra/data/expected/upstream/duplicate) — stopping with a verdict + remedy if not. For genuine code bugs it investigates the codebase to locate the root cause, distills it into a structured **Bug Analysis** block (plus a ready-to-file Issue body), and offers two handoff buttons. The bug-driven sibling of `@issue-reader`, with an added triage + root-cause investigation phase.

**Model**: `Claude Sonnet 5` — diagnosis is the highest-leverage, highest-risk step (a wrong root cause cascades into a wrong fix). Under token-based billing this is one bounded call, cheap versus the cost of a misdiagnosis.

**Key capabilities**:
- Takes free-text bug reports (`@bug-analyzer the playground freezes uploading a PDF > 10MB`)
- **Triages first** — classifies the report as a code defect vs config/env, infra/connectivity, data, expected behaviour, upstream dependency, or duplicate; if it's not a code bug, emits a **Triage Verdict** with the real remedy and stops (no Bug Analysis, no issue, no fix)
- Asks at most ONE clarifying question if reproduction / expected-vs-actual is missing
- Actively traces the code path (`read`/`search`) and grounds every root-cause claim in real `file:line` evidence
- Verifies suspected library-API misuse against the `context7` / `docs-langchain` MCP before asserting it
- Never fabricates a cause — marks `Confidence: low` and proposes how to instrument when it can't locate it
- Always specifies a regression test that reproduces the bug
- Emits a ready-to-file **Issue body** (per `.github/ISSUE_TEMPLATE/bug_report.md`); the executor files the GitHub tracking issue (gated) before the fix and links it via `Closes #N`
- Read-only — never edits code, runs `gh`, or commits; it emits the Issue body, the executor files it

**Invocation**:
- `@bug-analyzer <description>` — free text
- `/report-bug <description>` — slash command equivalent

**Hands off to** (user clicks one):
- `@quick-executor` — small/localized fix, executed reproduce-first (failing test → fix → green), seeded from the Bug Analysis (`fix/` branch + affected files)
- `@feature-planner` — large/architectural fix; the Bug Analysis becomes the spec's Context/Problem/FR and the regression test an acceptance criterion

**Never does**:
- ❌ Write code, tests, commits, or migrations (read-only — diagnosis only)
- ❌ Fabricate a root cause it cannot ground in `file:line`
- ❌ Create plan files or orchestrate execution

---

### `@quick-executor`

**Purpose**: Autonomous executor for small ad-hoc tasks (bugs, single-area fixes, doc updates, small refactors) that do NOT warrant a formal spec in `/plans/`. The twin of `@plan-executor` without the spec-driven workflow. Auto-invokes implementer subagents, runs git directly with explicit confirmation gates before commit / push / PR.

**Key capabilities**:
- Reads the Issue Analysis block (from `@issue-reader`) or accepts a direct task description
- Decides which implementer subagents to invoke based on the task's scope
- Creates the local feature branch — uses Issue Analysis `Suggested branch` if present, otherwise derives `<type>/<short-slug>`
- Auto-invokes `@backend-expert`, `@react-expert`, `@alembic-expert`, `@test-expert`, `@docs-manager` as subagents (no clicks)
- Runs `git` and `gh` commands directly (has `execute` tool)
- Pauses for explicit user confirmation at 3 points: each commit, push, PR creation
- Redirects to `@feature-planner` if the task turns out to be substantial (3+ areas, new entities, multi-step migrations)

**Invocation**:
- From `@issue-reader` handoff: click "Execute autonomously with @quick-executor"
- Direct: `@quick-executor fix the login redirect loop on Safari`
- Slash command: `/quick-execute <task description>`

**When to use**: Bugs, doc fixes, small refactors, single-area changes, anything ≲ 5 files where you don't need a tracked spec.

**Do NOT use for**: Multi-area features → `@feature-planner` + `@plan-executor`. Releases → `@release-manager`.

**Confirmation gates**: identical pattern to `@plan-executor`
- ⏸️ COMMIT CONFIRMATION — between each subagent's work
- ⏸️ PUSH CONFIRMATION — before publishing the branch
- ⏸️ PR CONFIRMATION — before opening the PR

**Never does**:
- ❌ Write application code (delegates to subagents)
- ❌ Push or open a PR without confirmation
- ❌ Create plan files in `/plans/` (that's `@feature-planner`)
- ❌ Continue silently when a subagent reports `blocked` or `needs-revision`

---

### `@feature-planner`

**Purpose**: Transforms feature ideas into structured, implementation-ready specifications. Maintains all plans as persistent artifacts in `/plans/`.

**Key capabilities**:
- Elicits requirements through targeted questions — never creates a plan from a vague one-liner
- Produces `spec.md` files with requirements (FR-N), acceptance criteria (AC-N), edge cases, dependencies, and risks
- Manages plan lifecycle: `draft` → `refining` → `ready` → `implemented` → `archived`
- Maintains `/plans/index.yaml` as the central plan registry
- Creates plan extensions (`extension-N.plan.md`) for related features discovered post-implementation

**Commands**:
```
@feature-planner plan a new feature for <topic>
@feature-planner refine the plan for <slug>
@feature-planner extend the <slug> plan with extension-1: <description>
@feature-planner list plans
@feature-planner mark <slug> as ready
@feature-planner what can you do?
```

**Filesystem scope**: Read/write only inside `/plans/`. Never touches application code.

**Delegates to**:
- `@plan-executor` — when plan reaches `ready` and the user wants to start implementation
- `@backend-expert` / `@react-expert` — for implementation details beyond high-level notes
- `@alembic-expert` — when the plan involves schema changes
- `@docs-manager` — after implementation to reflect the feature in docs
- `@git-github` — for committing plan files or linking GitHub issues

---

### `@plan-executor`

**Purpose**: Semi-autonomous orchestrator that reads `spec.md` files and drives implementation by invoking the appropriate agents step by step, handling git operations itself, and pausing only for user confirmation before each commit.

**Key capabilities**:
- Generates incremental, self-contained step files (`step_NNN.md`) in `/plans/<slug>/execution/`
- Directly invokes file-operation agents (`@backend-expert`, `@react-expert`, `@alembic-expert`, `@docs-manager`)
- Runs all git operations itself (branch, commit, push, PR) via the `git-github` skill
- Pauses before every commit to show the user staged files and message — never auto-commits
- Tracks progress in `status.yaml` with per-step FR/AC mapping
- Resumes from any point by reading the manifest
- Continues step numbering globally across plan extensions (no reset)

**Commands**:
```
@plan-executor execute plan <slug>
@plan-executor execute extension <slug> extension-1
@plan-executor continue <slug>
@plan-executor status <slug>
@plan-executor what can you do?
```

**Auto-invokes as subagents** (file operations only, no terminal): `@backend-expert`, `@react-expert`, `@alembic-expert`, `@test-expert`, `@docs-manager`
**Runs directly** (terminal): all git/gh operations via the `git-github.skill.md` skill
**Pauses for confirmation**: every commit, PR creation

**Receives from**:
- `@feature-planner` — the `spec.md` it consumes

**Delegates to** (auto-invoked as subagents):
- `@backend-expert` — models, services, routes
- `@react-expert` — frontend components and pages
- `@alembic-expert` — database migrations
- `@test-expert` — unit/integration tests for the implemented FRs/ACs (returns a `## Terminal Commands Required` block with the `pytest` run)
- `@docs-manager` — documentation updates at plan completion

**Note**: `@git-github` is NOT used as a subagent here. `@plan-executor` executes git/gh commands directly following `git-github.skill.md`.

---

### `@backend-expert`

**Purpose**: Senior Python backend engineer (generic role). Implements models, schemas, repositories, services, and API routes following the layered architecture. Project-specific paths and utilities come from `backend-conventions.instructions.md` (auto-applied on `backend/**`).

**Key capabilities** (generic role):
- FastAPI (async/await, dependency injection, lifecycle, OpenAPI docs)
- SQLAlchemy 2.x ORM — `select()`, eager loading, query optimization, connection pooling
- Pydantic v2 — request/response validation, `model_dump()`, `model_validate()`
- LangChain 1.x / LangGraph 1.x / LangSmith / Deep Agents — LCEL chains, `create_agent()`, RAG, streaming, structured output, MCP tools
- Authentication, RBAC, API design, security posture
- Layered architecture: Router → Service → Repository → Model

**Companion instruction**: `.github/instructions/backend-conventions.instructions.md` — auto-applied to `backend/**`. Carries the project's real paths, key utilities (vector store factory, embedding tools, LangSmith config), AICT auth modes, tenant scoping with `@require_min_role`, memory thread-ID format, and Poetry usage.

**When to use**: Any new backend feature, service logic, API endpoint, or LLM integration.

**Handoff protocol**: When done, provides a change summary so the user can invoke `@git-github`:
```
Type: feat | fix | refactor | test | chore
Scope: backend
Files changed: backend/models/..., backend/services/..., backend/routers/...
```

**Delegates to**:
- `@alembic-expert` — when a model change needs a migration (never creates migrations itself)
- `@version-bumper` — for version bumps (never edits `pyproject.toml` directly)

**Note**: Cannot invoke `@git-github` as a subagent (no terminal access). Hands off to the user with a change summary instead.

**Receives from**:
- `@plan-executor` — step files with self-contained task prompts
- `@feature-planner` — spec files to understand feature requirements

---

### `@react-expert`

**Purpose**: Senior React frontend engineer (generic role). Implements components, pages, hooks, forms, and state management. Project-specific paths and the library/client extension model come from `react-conventions.instructions.md` (auto-applied on `frontend/**`).

**Key capabilities** (generic role):
- React 19 — functional components, hooks (incl. `use`, `useActionState`, `useOptimistic`), concurrent features
- TypeScript strict mode — generic components, utility types, discriminated unions
- State management — `useState`, Context, Zustand
- Tailwind CSS — utility-first with required dark mode
- React Router v6 — nested routes, lazy loading, protected routes
- Accessibility — semantic HTML, ARIA, keyboard navigation, WCAG 2.1
- Performance — `React.memo`, `useMemo`, `useCallback`, code splitting

**Companion instruction**: `.github/instructions/react-conventions.instructions.md` — auto-applied to `frontend/**`. Carries the library + per-client extension model, `ExtensibleBaseApp` entry point, centralized `services/api.ts`, constants synced with the backend, Vite commands, and the FAKE/LOCAL/OIDC auth flows.

**When to use**: Any new page, component, form, or frontend hook.

**Handoff protocol**: When done, provides a change summary so the user can invoke `@git-github`:
```
Type: feat | fix | refactor | test
Scope: frontend
Files changed: frontend/src/components/..., frontend/src/pages/...
```

**Delegates to**:
- `@version-bumper` — for version bumps

**Note**: Cannot invoke `@git-github` as a subagent (no terminal access). Hands off to the user with a change summary instead.

**Receives from**:
- `@plan-executor` — step files with self-contained task prompts

---

### `@alembic-expert`

**Purpose**: Expert in Alembic migrations and PostgreSQL schema evolution (generic role). Project-specific naming, model registry, and the ignored-tables filter come from `alembic.instructions.md` (auto-applied on `alembic/**`).

**Key capabilities** (generic role):
- Autogenerate and hand-crafted migrations
- Always writes `upgrade()` + `downgrade()` — reversibility is mandatory
- Manages the migration revision chain (`down_revision` linkage)
- Handles PostgreSQL-specific types (JSONB, ENUM, UUID, pgvector HNSW)
- Troubleshoots multiple heads with `alembic merge`
- Round-trip downgrade test before commit

**When to use**: Any time a SQLAlchemy model is created or modified.

**Companion instruction**: `.github/instructions/alembic.instructions.md` — auto-applied to `alembic/**`. Carries the project's PascalCase / snake_case convention, the `backend/models/__init__.py` registry requirement, the `include_name()` filter for LangChain / LangGraph tables, and the standard migration templates.

**Delegates to**:
- `@backend-expert` — for model implementation questions

**Note**: Cannot invoke `@git-github` as a subagent (no terminal access). Provides a change summary for the user to invoke `@git-github` directly.

**Receives from**:
- `@backend-expert` — after model changes
- `@plan-executor` — step files for migration tasks

---

### `@test-expert`

**Purpose**: Senior pytest engineer for FastAPI + SQLAlchemy projects (generic role). Project-specific fixtures, isolation pattern, factory-boy setup and test DB live in `testing-conventions.instructions.md` (auto-applied on `tests/**`).

**Key capabilities** (generic role):
- Test pyramid: unit (mocked, no DB) → integration (real DB, full HTTP stack) → E2E
- pytest ecosystem (`pytest-asyncio`, `pytest-mock`, `pytest-cov`, `pytest-env`, `factory-boy`)
- Savepoint-based transactional isolation for SQLAlchemy
- Mocking at the import path, not the definition path
- Async testing with `AsyncMock` / `httpx.AsyncClient`

**Companion instruction**: `.github/instructions/testing-conventions.instructions.md` — auto-applied to `tests/**`. Carries the full fixtures map (`fake_user`, `fake_app`, `fake_agent`, `auth_headers`, `owner_headers`), the savepoint isolation pattern in `tests/conftest.py`, factory-boy setup with `configure_factories(db)`, the test DB on port 5433, and the CI workflow.

**Commands**:
```bash
poetry run pytest tests/unit/ -v        # No DB needed — fast
./scripts/test.sh -m integration         # Auto-manages ephemeral test DB
poetry run pytest -k "test_name" -v -s  # Single test with output
```

**Critical rule**: Never use `db.commit()` in tests — always `db.flush()`.

**Delegates to**:
- `@backend-expert` — for service logic questions
- `@alembic-expert` — when fixtures depend on fields added by a migration

**Note**: Cannot invoke `@git-github` as a subagent (no terminal access). Provides a change summary for the user to invoke `@git-github` directly.

**Receives from**:
- `@backend-expert` — after a new service or endpoint is created
- `@plan-executor` — step files for test tasks

---

### `@git-github`

**Purpose**: Autonomous expert in git operations and GitHub CLI workflows. Handles all branching, committing, pushing, PR creation, issue management, and releases. **Always invoked directly by the user** — never used as a subagent, because it requires terminal execution which is unavailable in subagent context.

**Key capabilities**:
- Conventional Commits format: `type(scope): description`
- Plain (unsigned) commits (`git commit`) — no GPG configured
- Always pulls before pushing (`git pull origin <branch>`)
- Uses `--body-file` for all `gh issue create` / `gh pr create` — never `--body` or heredoc
- Multi-remote: `origin` (GitHub, primary) and `lks` (GitLab mirror, only on explicit request)
- Feature branches from `develop`, never from `main`

**Branch naming**:
```
feature/<description>    feat/<plan-slug>
bug/<description>        fix/<description>
clean/<description>
```

**When to use**: Invoked directly by the user after an implementation agent finishes and provides a change summary. Also invoked for any standalone git/GitHub operation (issue creation, branch management, releases outside of plan execution).

> This agent is **not a subagent**. Agents that need git operations at runtime (`@plan-executor`, `@release-manager`) execute git/gh commands directly using the `git-github.skill.md` skill. Implementation agents (`@backend-expert`, `@react-expert`, etc.) cannot run git commands and instead hand off to the user with a change summary.

**Companion instruction**: `.github/instructions/git-github.instructions.md` — auto-applied globally.
**Companion skill**: `.github/skills/git-github.skill.md` — step-by-step procedures used by agents that run git directly.

**Delegates to**:
- `@version-bumper` — when a version bump is needed before a release

**Receives from** (user-mediated handoff, not direct delegation):
- `@backend-expert`, `@react-expert`, `@alembic-expert`, `@test-expert`, `@docs-manager` — provide change summaries; the user then invokes `@git-github`

---

### `@docs-manager`

**Purpose**: Maintains all project documentation in `docs/`. Tracks which git commit docs were last synchronized to and updates only what's needed based on actual code changes.

**Key capabilities**:
- Maintains `docs/index.md` as the authoritative Table of Contents
- Tracks documentation freshness via `docs/.doc-metadata.yaml` (baseline commit SHA)
- Analyzes `git log <baseline>..HEAD` to determine what changed before updating
- Creates new sections following kebab-case naming and the prescribed document structure
- Never documents planned features — only what already exists in code

**Commands**:
```
@docs-manager update docs
@docs-manager what changed since last update?
@docs-manager add a section about <topic>
@docs-manager reorganize the index
@docs-manager what can you do?
```

**Filesystem scope**: Read/write only inside `docs/`.

**Delegates to**:
- `@ai-dev-architect` — when the audit reveals a need for new agents or instruction files
- `@version-bumper` — for version changes (never edits `pyproject.toml` directly)

**Note**: Cannot invoke `@git-github` as a subagent (no terminal access). Provides a change summary for the user to invoke `@git-github` directly.

**Receives from**:
- `@plan-executor` — as the final step of plan execution
- `@feature-planner` — after a plan is marked `implemented`

---

### `@ai-dev-architect`

**Purpose**: Meta-agent responsible for the AI development environment itself. Designs, creates, and maintains Copilot agents, instruction files, skills, and `CLAUDE.md` configurations.

**Key capabilities**:
- Designs new agent definitions following single-responsibility and delegation-over-duplication principles
- Creates scoped instruction files with correct `applyTo` glob patterns
- Designs skill files for repeatable, parameterizable procedures
- Maintains `CLAUDE.md` (Claude Code) and `copilot-instructions.md` (global guidance)
- Audits the agent ecosystem for gaps, overlaps, and outdated instructions
- Decision guide: Skill (repeatable procedure) vs Agent (domain expert) vs Instruction (declarative rule)

**Commands**:
```
@ai-dev-architect create a new agent for <topic>
@ai-dev-architect create an instruction for <scope>
@ai-dev-architect create a skill for <procedure>
@ai-dev-architect audit the agent ecosystem
```

**Companion skills**: `new-agent.skill.md`, `new-instruction.skill.md`, `new-skill.skill.md`

**Delegates to**:
- `@backend-expert` / `@react-expert` — for implementation questions in their domains
- `@version-bumper` — for version changes (never edits `pyproject.toml` directly)

---

### `@release-manager`

**Purpose**: Orchestrates the complete end-to-end release workflow — version bump, changelog, git merge, tagging, and GitHub release creation.

**Key capabilities**:
- Pre-flight validation: clean working tree, on `develop`, synced with remote
- Standard releases: merges `develop` → `main` with `--no-ff`, creates annotated tag, pushes both
- Hotfix releases: branches from `main`, merges back to both `main` and `develop`
- Pre-releases: tags on `develop` without merging to `main`, uses `--prerelease` flag
- Always returns to `develop` after the release completes
- Stops immediately on any error — reports state and recovery steps without auto-recovery

**Commands**:
```
@release-manager release patch          # 0.3.16 → 0.3.17
@release-manager release minor          # 0.3.16 → 0.4.0
@release-manager release major          # 0.3.16 → 1.0.0
@release-manager release 0.4.0-beta.1   # Pre-release
@release-manager status                 # Show commits since last tag
@release-manager preview                # Dry-run
```

**Delegates to** (as subagents, file ops only):
- `@version-bumper` — for all version changes in `pyproject.toml`
- `@oss-manager` — for `CHANGELOG.md` updates and release notes

**Runs directly** (terminal): all git/gh commands of the standard release flow via `git-github.skill.md`. Coordinates with `@git-github` (user-invoked) only for complex scenarios like conflict resolution.

---

### `@version-bumper`

**Purpose**: Single-responsibility agent for semantic versioning. Reads and updates the version field in `pyproject.toml` — nothing else.

**Key capabilities**:
- Reads current version from `[tool.poetry].version`
- Applies MAJOR / MINOR / PATCH bumps following SemVer rules
- Never bumps multiple levels at once
- Only edits the version field — no other changes to `pyproject.toml`

**Commands**:
```
@version-bumper bump patch
@version-bumper bump minor
@version-bumper bump major
```

**Receives from**:
- `@release-manager` — as part of the release workflow
- `@backend-expert`, `@react-expert`, `@docs-manager` — when a bump is needed after implementation

---

### `@oss-manager`

**Purpose**: Open-source governance and community management. Handles licensing compliance, community files, changelog generation, and release notes for the AGPL-3.0 / Commercial dual-license model.

**Key capabilities**:
- Maintains `CHANGELOG.md` in Keep a Changelog format (Added / Changed / Deprecated / Removed / Fixed / Security)
- Drafts GitHub Release descriptions from `git log` history
- Audits dependency licenses for AGPL-3.0 compatibility
- Creates and maintains `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`
- Advises on what type of version bump changes warrant (actual bump delegated to `@version-bumper`)
- Never modifies the `LICENSE` file (verbatim AGPL-3.0 legal text)

**Commands**:
```
@oss-manager audit project health
@oss-manager generate changelog since v1.2.0
@oss-manager create CONTRIBUTING.md
@oss-manager check license compatibility for <package>
@oss-manager draft release notes
```

**Delegates to**:
- `@version-bumper` — for actual version changes
- `@git-github` — for committing, pushing, and creating GitHub Releases
- `@docs-manager` — for changes affecting `docs/LICENSE.md`

**Receives from**:
- `@release-manager` — as part of the release workflow (changelog + release notes step)

---

### `@pr-triager`

**Purpose**: Entry point for landing open PRs into `develop`. Audits every open PR via `gh`/`git` (base, behind-count vs `origin/develop`, mergeable/conflict state, CI, reviews, age, size), classifies each by `mergeStateStatus`, and emits a prioritized **PR Health Report** + integration order. Read-only.

**Model**: `['MAI-Code-1-Flash', 'GPT-5.4 mini', 'GPT-5 mini']` — high-volume `gh` reads, no code generation; MAI-Code-1-Flash with fallbacks.

**Invocation**: `@pr-triager` (all open PRs) · `@pr-triager #168` (one) · `/integrate-prs`.

**Hands off to**: `@pr-verifier` (verify the candidates, recommended) or `@pr-integrator` (skip verification).

**Never does**: merge, push, update branches, or resolve conflicts — diagnosis only.

---

### `@pr-verifier`

**Purpose**: Verification gate between triage and integration. For each integrable candidate it checks out the PR **merged onto the latest develop** (locally, never pushed), confirms it does what its goal/linked issue asks (delegating the correctness read to the area expert), and runs **differential targeted tests** — the selected tests are run on `develop` first as a baseline, then on the PR, so only **new** failures count as regressions (the repo has known always-failing tests). Emits a per-PR **PASS / RISK / FAIL** verdict and hands the PASS ones forward.

**Model**: `Claude Sonnet 5` — correctness judgment + test triage; the highest-leverage gate before a merge.

**Invocation**: from the `@pr-triager` handoff · `@pr-verifier #170` (one) · `@pr-verifier verify the CLEAN PRs`.

**Hands off to**: `@pr-integrator` — the PASS PRs only.

**Never does**: push, merge, edit code, or resolve conflicts (a DIRTY merge → `FAIL (not verifiable)`); leaves the tree clean on `develop`.

---

### `@pr-integrator`

**Purpose**: Integrates PRs into `develop` on the team default (**squash merge**). Per PR: updates the branch from `origin/develop` (merge — never rebase a shared branch), verifies CI is green, and squash-merges **behind confirmation gates**, deleting the branch. Detects whether a **merge queue** is enabled and, if so, just adds approved+green PRs to the queue (the queue handles update-and-retest). On conflicts it offers an **opt-in assisted resolution**: classify the files, delegate to the matching expert subagent (`@backend-expert`/`@react-expert`/`@alembic-expert` by path), then a **mandatory diff-review gate** before anything is staged/pushed/merged — never applies or merges a resolution the user hasn't approved. Runs `gh`/`git` directly.

**Model**: `Claude Sonnet 5` — judgment on merge/conflict safety.

**Confirmation gates**: update-push, merge, plus (when assisted resolution is used) conflict-resolution + resolution-review. Never merges a DIRTY / red / unreviewed / wrong-base / cross-fork PR, nor a conflict resolution the user hasn't reviewed.

**Receives from**: `@pr-verifier` — the PASS PRs (normal path); or `@pr-triager` directly via its "skip verification" handoff.

---

## Instructions (`instructions/`)

Scoped `.instructions.md` files automatically applied by Copilot when matching files are edited. They carry the **project-specific conventions** (paths, key utilities, entities, patterns) — domain-expert agents are kept **role-generic** and lean on these files for the project specifics.

| File | Scope | Purpose |
|---|---|---|
| `domain-model.instructions.md` | `backend/**`, `frontend/**`, `alembic/**`, `tests/**` | Product & domain reference — core concepts, RBAC, all entities + relationships, API surface, agent execution flow, memory, client deployment, env vars. Extracted from `copilot-instructions.md` so the heavy catalog loads only when implementing, not on every triage/planning/release call. |
| `backend-conventions.instructions.md` | `backend/**` | Layered architecture, real file paths, key utilities (`vector_store_factory`, `embeddingTools`, `langsmith_config`), `AICT_LOGIN` auth modes, tenant scoping with `@require_min_role`, memory thread-ID format, Poetry usage |
| `react-conventions.instructions.md` | `frontend/**` | Library + per-client (`clients/<name>/`) extension model, `ExtensibleBaseApp`, centralized `services/api.ts`, constants synced with backend, Vite commands, Tailwind dark mode + a11y |
| `testing-conventions.instructions.md` | `tests/**` | Savepoint-based transactional isolation, full fixtures map, factory-boy setup, test DB on port 5433, CI workflow, mocking patterns |
| `alembic.instructions.md` | `alembic/**` | Migration naming (PascalCase entities, snake_case junctions), model registry in `backend/models/__init__.py`, ignored tables filter, round-trip downgrade test |
| `git-github.instructions.md` | `**` (global) | branch naming, Conventional Commits, remote config (`origin` / `gitlab` / `mattinai`), `gh --body-file` rule |
| `docs.instructions.md` | `docs/**` | Documentation structure, kebab-case naming, metadata tracking |
| `handoff.instructions.md` | `.github/agents/*.agent.md` | Standard protocol for agent-to-agent handoffs via VS Code native buttons |
| `plan-extensions.instructions.md` | `plans/**` | Extension workflow, global step numbering, `status.yaml` structure |

> **Hybrid agent ↔ instruction pattern**: the 4 domain-expert agents (`@backend-expert`, `@react-expert`, `@alembic-expert`, `@test-expert`) are intentionally **generic role-based** — they describe the role (Python backend engineer, React engineer, …) and best practices that apply to any project. The **project-specific knowledge** lives in the matching `*-conventions.instructions.md` files above, and Copilot auto-loads them when the agent is invoked on the relevant files. This keeps the agents reusable across projects while the instructions stay the single source of truth for Mattin AI's conventions.
>
> Workflow-coupled agents (`@bug-analyzer`, `@quick-executor`, `@feature-planner`, `@plan-executor`, `@issue-reader`, `@release-manager`, `@oss-manager`, `@docs-manager`, `@version-bumper`, `@website-maintainer`, `@git-github`, `@ai-dev-architect`) stay project-coupled — their entire purpose IS this project's workflow.

---

## Skills (`skills/`)

Shared procedural definitions invoked by agents when executing common tasks.

| Skill | Purpose |
|---|---|
| `git-github.skill.md` | Step-by-step recipes for branch, commit, push, PR, release operations |
| `new-agent.skill.md` | Bootstrap a new Copilot agent with correct frontmatter and structure |
| `new-instruction.skill.md` | Create a new scoped instruction file |
| `new-skill.skill.md` | Create a new skill definition |

---

## MCP Servers (`.vscode/mcp.json`)

Three MCP servers are configured at the workspace level in `.vscode/mcp.json`. **VS Code Copilot loads them globally for ALL agents** — the per-agent `mcp-servers:` frontmatter field is ignored in local mode (only the GitHub Cloud Agent honors it). Each agent's body documents which MCP servers are relevant to its work via a "Documentation Lookup" section.

| Server | Transport | Used by | Purpose |
|---|---|---|---|
| `github` | HTTP (`https://api.githubcopilot.com/mcp/`) | `@issue-reader` (canonical), any agent that needs GitHub state | Read issues/PRs/repo via a GitHub PAT (input on first use) |
| `context7` | HTTP (`https://mcp.context7.com/mcp`) | `@backend-expert`, `@react-expert`, `@alembic-expert`, `@test-expert` | Official docs for FastAPI, SQLAlchemy 2.x, Pydantic v2, Alembic, pytest, React 19, TypeScript, Vite, Tailwind, and most other libraries. Two-step flow: `resolve-library-id` → `query-docs`. Free anonymous tier or API key for higher rate limits. |
| `langchain-docs` | HTTP (`https://docs.langchain.com/mcp`) | `@backend-expert` (canonical for LangChain ecosystem) | Authoritative docs for LangChain 1.x, LangGraph 1.x, LangSmith and Deep Agents. Always preferred over Context7 for these libraries because it's the official source. |

### Why HTTP, not stdio
HTTP-mode MCP servers don't require Node.js / npm processes spawning. They work across all dev environments (Windows, macOS, Linux, Codespaces) without setup beyond pasting an API key on first use.

### Cost note (Copilot pricing)
MCP tool calls do NOT count as separate premium requests — they happen within the agent's existing conversation. Cost is in the tokens returned by the MCP (the doc snippet inflates context). Querying a 2 KB doc snippet is dramatically cheaper than implementing the wrong API and going through a review cycle.

---

## Workflows (`workflows/`)

### `test.yaml` — CI/CD Pipeline

Runs on push/PR to `feat/**`, `fix/**`, `develop`, and `main`.

| Job | Scope | DB Required |
|---|---|---|
| Unit Tests | `tests/unit/` | No |
| Integration Tests | `tests/integration/` | Yes (PostgreSQL + pgvector) |
| Frontend Lint | `frontend/` | No |

Coverage reports are sent to Codecov with separate `unit` and `integration` flags.

---

## Master Guidance (`copilot-instructions.md`)

The authoritative reference for the entire repository. Contains:

- **Domain model**: all core entities (App, User, Agent, Silo, Repository, Domain, etc.) and their relationships
- **API surface**: `/internal`, `/public/v1`, `/mcp/v1` route conventions
- **Agent execution flow**: memory management, RAG retrieval, LLM call chain
- **Client deployment model**: reusable npm library pattern
- **Code style**: Python snake_case, TypeScript PascalCase, Conventional Commits
- **Key user workflows**: 10 documented end-to-end scenarios

All agents inherit this context automatically.
