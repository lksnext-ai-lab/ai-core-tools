# .github — AI-Driven Development Infrastructure

This directory contains the configuration for GitHub-native tooling and a structured multi-agent AI development workflow built on GitHub Copilot.

## Directory Structure

```
.github/
├── agents/                      # Specialized Copilot agents (13)
├── instructions/                # Scoped instruction files
├── skills/                      # Shared procedural definitions
├── workflows/                   # GitHub Actions CI/CD pipelines
├── copilot-instructions.md      # Master repo-wide guidance
└── PULL_REQUEST_TEMPLATE.md     # PR submission template
```

---

## Agents (`agents/`)

Invoke any agent with `@<agent-name>` in GitHub Copilot Chat. Each agent has a tightly scoped domain and delegates to others rather than duplicating work.

### Agent map (delegation overview)

```
Ad-hoc Orchestration:
  @conductor ──► @backend-expert   ┐
             ├──► @react-expert    │ dispatched one at a time
             ├──► @alembic-expert  │ via user-clicked handoff buttons
             ├──► @test-expert     │ (button labels match agent names)
             ├──► @docs-manager    │
             ├──► @oss-manager     │
             ├──► @version-bumper  │
             └──► @git-github      ┘

Feature Lifecycle:
  @feature-planner ──► @plan-executor ──► @backend-expert  ┐
                            │          ├──► @react-expert   │ subagents
                            │          ├──► @alembic-expert │ (file ops only,
                            │          └──► @docs-manager   ┘ no terminal)
                            │
                            └── git-github.skill.md ──► git / gh CLI  (run directly by plan-executor)

Release Lifecycle:
  @release-manager ──► @version-bumper  (subagent, file ops)
                   ├──► @oss-manager    (subagent, file ops)
                   └── git / gh CLI     (run directly by release-manager)

AI Environment:
  @ai-dev-architect ──► (creates/maintains all .github/ artifacts)

Direct invocation by the user (never subagents):
  @git-github   — full terminal access: branch, commit, push, PR, issues, releases
```

> **`@conductor` vs `@plan-executor`**: Use `@conductor` for ad-hoc tasks (bug fixes, small features, one-off operations) where you want immediate guided execution without a pre-written spec. Use `@feature-planner` + `@plan-executor` for large, planned features that need a tracked `spec.md` and step-by-step execution files in `/plans/`.

> **Why `@git-github` is not used as a subagent**: it requires terminal execution (`tools: [execute]`), which is unavailable in subagent context. Agents that need git operations either run commands directly via the `git-github.skill.md` skill (`@plan-executor`, `@release-manager`) or hand off to the user with a change summary for them to invoke `@git-github` directly (`@backend-expert`, `@react-expert`, `@alembic-expert`, `@test-expert`, `@docs-manager`).

---

### `@conductor`

**Purpose**: Ad-hoc workflow orchestrator. Analyzes any task, determines the right sequence of specialist agents, maintains a Mission Context block that travels through every handoff, and guides the user step-by-step. Does not write code, run commands, or implement anything — only plans, sequences, and directs.

**Key capabilities**:
- Reads the codebase before sequencing to give sub-agents accurate file paths and patterns
- Maintains a cumulative **Mission Context** block (task description, per-step status, locked-in decisions) at the top of every response
- Dispatches to exactly one specialist agent at a time via VS Code native handoff buttons
- Updates the Mission Context when a sub-agent returns (marks steps done, adds new constraints)
- Redirects release tasks to `@release-manager` and formal feature specs to `@feature-planner` / `@plan-executor`
- Handles blockers by surfacing 2–3 options for the user rather than auto-recovering

**Standard sequences**:
```
Full-stack feature:  @backend-expert → @alembic-expert → @test-expert → @react-expert → @docs-manager → @git-github
Backend-only:        @backend-expert → @alembic-expert (if models changed) → @test-expert → @git-github
Frontend-only:       @react-expert → @git-github
Bug fix:             @backend-expert or @react-expert → @test-expert → @git-github
Docs update:         @docs-manager → @git-github
```

**Skip rules**: `@alembic-expert` if no model changes; `@test-expert` if user opts out; `@docs-manager` if change is internal only.

**When to use**: Implementing features, fixing bugs, writing tests, updating docs — any multi-step ad-hoc task.

**Do NOT use for**: Formal feature specs (use `@feature-planner` + `@plan-executor`) or releases (use `@release-manager`).

**Dispatches to** (one at a time, via handoff buttons):
- `@backend-expert`, `@react-expert`, `@alembic-expert`, `@test-expert`, `@docs-manager`, `@oss-manager`, `@version-bumper`, `@git-github`

**Redirects to**:
- `@release-manager` — for any release workflow
- `@feature-planner` / `@plan-executor` — for tasks needing a formal spec in `/plans/`

**Never does**:
- ❌ Write application code, migrations, tests, or docs
- ❌ Run git, shell, or CLI commands
- ❌ Dispatch more than one agent at a time
- ❌ Orchestrate releases
- ❌ Execute pre-written plan files

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

**Auto-invokes as subagents** (file operations only, no terminal): `@backend-expert`, `@react-expert`, `@alembic-expert`, `@docs-manager`
**Runs directly** (terminal): all git/gh operations via the `git-github.skill.md` skill
**Pauses for confirmation**: every commit, PR creation

**Receives from**:
- `@feature-planner` — the `spec.md` it consumes

**Delegates to** (auto-invoked as subagents):
- `@backend-expert` — models, services, routes
- `@react-expert` — frontend components and pages
- `@alembic-expert` — database migrations
- `@docs-manager` — documentation updates at plan completion

**Note**: `@git-github` is NOT used as a subagent here. `@plan-executor` executes git/gh commands directly following `git-github.skill.md`.

---

### `@backend-expert`

**Purpose**: Expert Python/FastAPI developer. Implements models, schemas, repositories, services, and API routes following the project's layered architecture.

**Key capabilities**:
- FastAPI (async/await, dependency injection, lifecycle, OpenAPI docs)
- SQLAlchemy ORM — models, relationships, query optimization, connection pooling
- Pydantic v2 — request/response validation, `model_dump()`, `model_validate()`
- LangChain integration — LLM chains, RAG, streaming SSE, vector stores
- Authentication and RBAC (`@require_min_role`)
- Layered architecture: Router → Service → Repository → Model

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

**Purpose**: Expert React/TypeScript frontend developer. Implements components, pages, hooks, forms, and state management using the project's patterns.

**Key capabilities**:
- React 18+ — functional components, hooks, concurrent features
- TypeScript — strict typing, generic components, utility types
- State management — Context API, React Query / TanStack Query, Zustand
- Tailwind CSS — utility-first styling following the project's theme system
- React Router v6 — nested routes, lazy loading, protected routes
- Accessibility — semantic HTML, ARIA, keyboard navigation
- Performance — `React.memo`, `useMemo`, `useCallback`, code splitting

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

**Purpose**: Specialist in Alembic database migrations and schema evolution. Creates, reviews, and troubleshoots migrations for the project's PostgreSQL + pgvector setup.

**Key capabilities**:
- Autogenerate and hand-crafted migrations
- Always writes `upgrade()` + `downgrade()` — reversibility is mandatory
- Manages the migration revision chain (`down_revision` linkage)
- Handles PostgreSQL-specific types (JSONB, ENUM, UUID, pgvector)
- Ignores LangChain-managed tables (`langchain_pg_collection`, `langchain_pg_embedding`)
- Troubleshoots multiple heads with `alembic merge`

**Project conventions**:
- Table naming: PascalCase for entities (`Agent`, `Silo`), snake_case for junctions (`agent_skills`)
- All commands via `poetry run alembic <command>`
- New models must be imported in `backend/models/__init__.py`

**When to use**: Any time a SQLAlchemy model is created or modified.

**Companion instruction**: `.github/instructions/.alembic.instructions.md` — auto-applied to `alembic/**` files.

**Delegates to**:
- `@backend-expert` — for model implementation questions

**Note**: Cannot invoke `@git-github` as a subagent (no terminal access). Provides a change summary for the user to invoke `@git-github` directly.

**Receives from**:
- `@backend-expert` — after model changes
- `@plan-executor` — step files for migration tasks

---

### `@test-expert`

**Purpose**: Expert in writing and maintaining backend tests using pytest. Covers unit tests (no DB, mocked dependencies) and integration tests (real PostgreSQL via TestClient).

**Key capabilities**:
- Transaction isolation pattern (`join_transaction_mode="create_savepoint"`) — every test rolls back cleanly
- Full fixture chain: `test_engine` → `db` → `fake_user` → `fake_app` → `fake_agent` → `auth_headers` / `owner_headers`
- Factory-boy factories for bulk test data (`UserFactory`, `AgentFactory`, etc.)
- Mocking with `mocker.patch()`, `AsyncMock`, `mocker.spy()`
- Knows the correct auth endpoint: `POST /internal/auth/dev-login`
- Coverage targets: ≥40% unit, ≥65% combined

**Commands**:
```bash
pytest tests/unit/ -v                   # No DB needed — fast
./scripts/test.sh -m integration         # Auto-manages ephemeral test DB
pytest -k "test_name" -v -s            # Single test with output
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

**Purpose**: Autonomous expert in git operations and GitHub CLI workflows. Handles all branching, committing (GPG-signed), pushing, PR creation, issue management, and releases. **Always invoked directly by the user** — never used as a subagent, because it requires terminal execution which is unavailable in subagent context.

**Key capabilities**:
- Conventional Commits format: `type(scope): description`
- GPG-signed commits (`git commit -S`) — always, no exceptions
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

**Companion instruction**: `.github/instructions/.git-github.instructions.md` — auto-applied globally.
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
- Standard releases: merges `develop` → `main` with `--no-ff`, creates signed tag, pushes both
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

## Instructions (`instructions/`)

Scoped `.instructions.md` files automatically applied by Copilot based on the files being edited.

| File | Scope | Purpose |
|---|---|---|
| `.alembic.instructions.md` | `alembic/**` | Migration conventions, downgrade requirements, naming rules |
| `.git-github.instructions.md` | `**` (global) | GPG signing, branch naming, Conventional Commits, remote config |
| `.docs.instructions.md` | `docs/**` | Documentation structure, kebab-case naming, metadata tracking |
| `.plan-extensions.instructions.md` | `plans/**` | Extension workflow, global step numbering, `status.yaml` structure |

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
