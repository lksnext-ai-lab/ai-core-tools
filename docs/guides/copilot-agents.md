# Copilot Agents, Skills & Instructions

> Part of [Mattin AI Documentation](../README.md)

## Overview

Mattin AI uses a **multi-agent GitHub Copilot architecture** to accelerate development across the entire stack. The system is composed of three building blocks that live under `.github/`:

| Concept | Location | Purpose |
|---------|----------|---------|
| **Agents** | `.github/agents/*.agent.md` | Specialized AI personas invoked with `@agent-name` |
| **Skills** | `.github/skills/*.skill.md` | Reusable step-by-step procedures (templates) |
| **Instructions** | `.github/instructions/*.instructions.md` | Auto-applied rules scoped to file patterns |

A fourth file, `.github/copilot-instructions.md`, provides **global guidance** that is always active regardless of which agent is invoked.

---

## Agents

Agents are domain-specific Copilot personas. Each agent defines its **competencies**, **workflow**, **do/don't rules**, and **delegation boundaries** (what it hands off to other agents).

### Quick Reference

| Agent | Invoke | Domain | Lines |
|-------|--------|--------|-------|
| Backend Expert | `@backend-expert` | Python, FastAPI, SQLAlchemy, LangChain | 784 |
| React Expert | `@react-expert` | React 18+, TypeScript, Tailwind | 413 |
| Alembic Expert | `@alembic-expert` | Database migrations, schema evolution | 300 |
| Documentation Manager | `@docs-manager` | `docs/` management, freshness tracking | 320 |
| Git & GitHub | `@git-github` | Git workflows, GitHub CLI, PRs, releases | 280 |
| AI Dev Architect | `@ai-dev-architect` | Agent/skill/instruction management | 580 |
| Version Bumper | `@version-bumper` | Semantic versioning in `pyproject.toml` | 99 |
| Test Agent | `@test` | Testing Copilot agent infrastructure | 14 |

### Backend Expert (`@backend-expert`)

The most comprehensive agent. Covers all backend development aspects:

- **FastAPI**: async patterns, dependency injection, middleware, lifecycle
- **SQLAlchemy**: ORM models, relationships, connection pooling, query optimization
- **Pydantic v2**: schemas, validators, `model_validate()`, `model_dump()`, `ConfigDict`
- **LangChain**: LLM integration, chains, agents, memory, tools, vector stores, RAG, streaming SSE
- **Layered architecture**: Routes → Services → Repositories → Models
- **Authentication**: OAuth2/OIDC, JWT, session, API keys, RBAC
- Complete CRUD code examples (Model, Schema, Repository, Service, Router, Tests)

**Delegates to**: `@alembic-expert` (migrations), `@git-github` (version control), `@version-bumper` (versioning)

### React Expert (`@react-expert`)

Specializes in modern React/TypeScript frontend development:

- React 18+ functional components, hooks, and concurrent features
- TypeScript type safety with generic components and utility types
- State management (Context API, React Query, Zustand, Redux Toolkit)
- Performance optimization (React.memo, code splitting, virtualization)
- Styling (Tailwind CSS, CSS Modules, styled-components)
- UI libraries (MUI, shadcn/ui, Chakra, Radix)
- Testing (React Testing Library, Jest, Playwright)
- Accessibility (ARIA, keyboard navigation, screen readers)

**Delegates to**: `@version-bumper` (versioning)

### Alembic Expert (`@alembic-expert`)

Handles all database migration tasks:

- Migration creation via `poetry run alembic revision --autogenerate`
- Full `op.*` operations reference (table, column, index, constraint, data, batch)
- Model registry management (`backend/models/__init__.py`)
- Schema safety: reversibility, non-destructive changes, zero-downtime
- PostgreSQL specifics: pgvector, JSONB, indexes
- Troubleshooting: merge conflicts, failed migrations, multiple heads

**Companion instruction**: `.alembic.instructions.md` (auto-applied to `alembic/**`)

**Delegates to**: `@backend-expert` (model implementation), `@git-github` (version control), `@version-bumper` (versioning)

### Documentation Manager (`@docs-manager`)

Manages all documentation in `docs/`:

- Git-based change tracking via `docs/.doc-metadata.yaml` baseline
- Commit analysis and documentation freshness auditing
- Index/TOC management (`docs/README.md` as authoritative TOC)
- Section creation, restructuring, and cross-reference validation

**Usage examples**:
```
@docs-manager update docs           — Full refresh from git history
@docs-manager what changed?         — Audit freshness without editing
@docs-manager add section about X   — Create new documentation
@docs-manager reorganize the index  — Restructure TOC
```

**Delegates to**: Consults `@backend-expert`, `@react-expert`, `@alembic-expert` for code understanding; `@ai-dev-architect` for new agent files; `@version-bumper` for versioning

### Git & GitHub (`@git-github`)

Comprehensive Git and GitHub CLI agent:

- Branch management with `type/description` naming (`feature/`, `bug/`, `fix/`, `clean/`)
- Conventional Commits format: `type(scope): description`
- GPG-signed commits (`git commit -S`)
- GitHub CLI operations (issues, PRs, releases) using `--body-file`
- Multi-remote operations: GitHub (`origin`) + GitLab (`lks`)
- Release management with `gh release`

**Companion instructions**: `.gh-commit.instructions.md` (GPG signing), `.gh-issues.instructions.md` (`--body-file` rule)

**Delegates to**: `@backend-expert` / `@react-expert` (code), `@alembic-expert` (migrations), `@version-bumper` (versioning)

### AI Dev Architect (`@ai-dev-architect`)

A meta-agent for managing the AI-assisted development ecosystem:

- Agent design and system prompt engineering
- Scoped/global instruction file creation
- Skill design with parameterization and step orchestration
- CLAUDE.md, Cursor, and Windsurf rule management
- MCP server setup and tool definition
- Agent ecosystem audit (relevance, accuracy, overlap, gaps)

Uses all three skills: `new-agent.skill.md`, `new-skill.skill.md`, `new-instruction.skill.md`

**Delegates to**: `@backend-expert`, `@react-expert` (implementation); `@version-bumper` (versioning)

### Version Bumper (`@version-bumper`)

A single-purpose agent that only bumps version numbers in `pyproject.toml`:

- Reads current version from `[tool.poetry].version`
- Determines bump type from intent: bug fix → PATCH, feature → MINOR, breaking change → MAJOR
- Calculates and applies new version
- Reports: `✓ Version bumped: X.X.X → Y.Y.Y (TYPE bump)`

**Constraints**: Only modifies the `version` field; never bumps multiple levels at once.

### Test Agent (`@test`)

A minimal stub agent used for testing Copilot agent infrastructure. No substantive capabilities defined.

---

## Skills

Skills are **reusable step-by-step procedures** that teach Copilot how to perform specific tasks. They are parameterized templates used by the `@ai-dev-architect` agent to bootstrap new components of the AI tooling ecosystem.

| Skill | File | Purpose |
|-------|------|---------|
| New Agent | `new-agent.skill.md` | Create a new `.agent.md` file |
| New Skill | `new-skill.skill.md` | Create a new `.skill.md` file |
| New Instruction | `new-instruction.skill.md` | Create a new `.instructions.md` file |

### New Agent Skill

Creates a new agent definition with proper structure. Provides the complete agent template (frontmatter, intro, competencies, workflow, do/don't lists, delegation, scope boundaries).

**Parameters**: `name` (required), `slug` (optional), `description` (required), `domains` (required — comma-separated competency areas)

**Steps**:
1. Generate frontmatter with name and description
2. Populate competencies from the actual codebase
3. Set up inter-agent delegation rules (bidirectional)
4. Optionally create companion instruction files

### New Skill Skill

Creates a new skill definition with proper structure: frontmatter, parameters table, sequential steps, verification checklist, and output section.

**Parameters**: `name` (required), `slug` (optional), `description` (required), `parameters` (required — list of input params)

**Guidelines**: Max 5 parameters, map steps to tool invocations, include verification and optional agent linkage.

### New Instruction Skill

Creates a new instruction file with proper scoping. Includes a scoping strategy table and conflict-checking step.

**Parameters**: `name` (required), `slug` (optional), `description` (required), `applyTo` (optional — glob pattern)

**Scoping strategies**:

| Scope | `applyTo` Pattern |
|-------|-------------------|
| All Python files | `**/*.py` |
| Backend only | `backend/**` |
| Frontend only | `frontend/**` |
| Tests only | `tests/**` |
| Alembic only | `alembic/**` |
| Documentation | `docs/**` |
| Global | *(omit `applyTo`)* |

---

## Instructions

Instructions are **auto-applied rules** that activate based on file glob patterns. They enforce conventions without needing to invoke any agent explicitly.

| Instruction | File | Applies To |
|-------------|------|------------|
| Alembic Conventions | `.alembic.instructions.md` | `alembic/**` |
| Documentation Conventions | `.docs.instructions.md` | `docs/**` |
| Git Commit Rules | `.gh-commit.instructions.md` | *(global)* |
| GitHub Issue Rules | `.gh-issues.instructions.md` | *(global)* |

### Alembic Conventions (`.alembic.instructions.md`)

Auto-applied when editing files under `alembic/`. Enforces:

- Every migration must have both `upgrade()` and `downgrade()` functions
- `downgrade()` must fully reverse `upgrade()`
- Descriptive revision messages (not just "update")
- Verify `down_revision` chain before committing
- Never modify already-applied migrations — create new ones
- PascalCase for entity tables (`Agent`, `Silo`), snake_case for junction tables (`agent_skills`)
- Primary keys: `<table_name_lower>_id`
- New models must be imported in `backend/models/__init__.py`
- Ignore LangChain-managed tables (`langchain_pg_collection`, `langchain_pg_embedding`)

### Documentation Conventions (`.docs.instructions.md`)

Auto-applied when editing files under `docs/`. Enforces:

- File naming: `kebab-case.md`, lowercase directory names
- Document structure: title → breadcrumb → overview → content → examples → see-also
- ATX-style headings with language-tagged fenced code blocks
- Relative links for internal references
- `docs/.doc-metadata.yaml` managed by `@docs-manager` only
- `docs/README.md` is the authoritative TOC — every page must be linked there
- Document what **exists**, not what is planned
- Don't duplicate content from `CLAUDE.md` or root `README.md`

### Git Commit Rules (`.gh-commit.instructions.md`)

Always active (global scope). Enforces:

- All commits must be **GPG-signed** before pushing
- Use `git commit -S -m "message"` for signing
- Ensure GPG key is associated with GitHub account
- Verify with `git log --show-signature -1`

### GitHub Issue Rules (`.gh-issues.instructions.md`)

Always active (global scope). Enforces:

- Always use `--body-file` with `gh issue create` (never `--body` or heredoc `<<EOF`)
- Workflow: create temp markdown file → `gh issue create --body-file` → add labels → clean up
- Default repo: `https://github.com/lksnext-ai-lab/ai-core-tools`
- Available labels: `enhancement`, `bug`, `documentation`, `technical-debt`, `good-first-issue`, `help-wanted`, `question`, `discussion`, `invalid`, `wontfix`, `duplicate`

---

## Global Copilot Instructions

The file `.github/copilot-instructions.md` provides **repository-wide guidance** that is always active for every Copilot interaction. It defines:

- **Project overview**: Mattin AI as an extensible AI toolbox platform
- **Tech stack**: Python 3.11+, FastAPI, SQLAlchemy, React 18, TypeScript, PostgreSQL, Docker
- **Agent directory**: Quick reference table of all agents and their invocations
- **Architecture conventions**: Backend layered architecture, frontend component patterns
- **Code style**: Python (snake_case, PascalCase, type hints), TypeScript (PascalCase components, `handle` prefix)
- **Anti-patterns**: No direct `fetch()`, no business logic in routers, no raw SQL, no hardcoded secrets

---

## Architecture: How It All Fits Together

```
.github/
├── copilot-instructions.md          ← Global rules (always active)
├── agents/
│   ├── backend-expert.agent.md      ← @backend-expert
│   ├── react-expert.agent.md        ← @react-expert
│   ├── alembic-expert.agent.md      ← @alembic-expert
│   ├── docs-manager.agent.md        ← @docs-manager
│   ├── git-github.agent.md          ← @git-github
│   ├── ai-dev-architect.agent.md    ← @ai-dev-architect
│   ├── version-bumper.agent.md      ← @version-bumper
│   └── test.agent.md                ← @test
├── skills/
│   ├── new-agent.skill.md           ← Used by @ai-dev-architect
│   ├── new-skill.skill.md           ← Used by @ai-dev-architect
│   └── new-instruction.skill.md     ← Used by @ai-dev-architect
└── instructions/
    ├── .alembic.instructions.md     ← Auto-applied to alembic/**
    ├── .docs.instructions.md        ← Auto-applied to docs/**
    ├── .gh-commit.instructions.md   ← Global (GPG signing)
    └── .gh-issues.instructions.md   ← Global (--body-file rule)
```

### Delegation Graph

Agents delegate work to each other to maintain single-responsibility boundaries:

```
@backend-expert ──→ @alembic-expert (migrations)
       │  └──────→ @version-bumper (versioning)
       │  └──────→ @git-github (version control)
       │
@react-expert ───→ @version-bumper (versioning)
       │
@alembic-expert ─→ @backend-expert (model code)
       │  └──────→ @git-github (version control)
       │  └──────→ @version-bumper (versioning)
       │
@docs-manager ──→ @ai-dev-architect (new agents/instructions)
       │  └─────→ @version-bumper (versioning)
       │
@git-github ────→ @backend-expert / @react-expert (code)
       │  └─────→ @alembic-expert (migrations)
       │  └─────→ @version-bumper (versioning)
       │
@ai-dev-architect → @backend-expert / @react-expert (implementation)
       │  └──────→ @version-bumper (versioning)
```

### Decision Guide: Agent vs Skill vs Instruction

| Need | Use | Why |
|------|-----|-----|
| Expert persona for a domain | **Agent** | Full context, workflow, and delegation rules |
| Repeatable multi-step procedure | **Skill** | Parameterized template, reusable by agents |
| Auto-enforced convention | **Instruction** | Applied automatically by file pattern, no invocation needed |

---

## Creating New Components

To extend the Copilot tooling:

1. **New agent**: Ask `@ai-dev-architect` to create one, or invoke the `new-agent` skill
2. **New skill**: Ask `@ai-dev-architect`, or use the `new-skill` skill template
3. **New instruction**: Ask `@ai-dev-architect`, or use the `new-instruction` skill template

All new components should be documented by updating this page and the [README](../README.md).

---

## See Also

- [Developer Guide](../dev-guide.md) — Development setup and conventions
- [Architecture Overview](../architecture/overview.md) — High-level system design
- [Agent System](../ai/agent-system.md) — Runtime AI agent execution engine (different from Copilot agents)
