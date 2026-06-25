# Mattin AI — Global Copilot Instructions

Repository-wide guidance for GitHub Copilot. **Keep this file lean** — it is re-sent on every request to every agent. Deep references live in scoped instructions and docs (linked below) so the heavy context loads only when relevant.

## Project Overview

**Mattin AI** is an extensible AI toolbox platform:
- LLM integration (OpenAI, Anthropic, MistralAI, Azure OpenAI, Google, Ollama)
- RAG with multiple vector backends (PGVector, Qdrant)
- AI agent management and execution
- Multi-tenant workspace architecture (App = tenant unit)

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic, LangChain/LangGraph · React 19, TypeScript, Vite, Tailwind CSS · PostgreSQL + pgvector · Docker / Docker Compose.

## Where the deep context lives (load on demand — do NOT duplicate here)

| Topic | Source | Loads |
|---|---|---|
| **Domain model, entities, API surface, agent execution flow, memory, env vars** | `.github/instructions/domain-model.instructions.md` | auto on `backend/**`, `frontend/**`, `alembic/**`, `tests/**` (else `#file:` it) |
| **Backend conventions** (paths, layering, utilities, auth modes, tenant scoping) | `backend-conventions.instructions.md` | auto on `backend/**` |
| **Frontend conventions** (library + client model, `api.ts`, constants sync) | `react-conventions.instructions.md` | auto on `frontend/**` |
| **Migrations** (naming, model registry, downgrade test) | `alembic.instructions.md` | auto on `alembic/**` |
| **Testing** (fixtures, savepoint isolation, factory-boy, test DB) | `testing-conventions.instructions.md` | auto on `tests/**` |
| **Git / GitHub** (GitFlow, `--body-file`, remotes) | `git-github.instructions.md` | global |
| **Docs conventions** | `docs.instructions.md` | auto on `docs/**` |
| **Agent system, flows & roster** | `.github/AI-DEV-INFO.md` | reference |

> When a task touches domain entities but you're not editing `backend/**` / `frontend/**` (e.g. planning a spec), pull the model in explicitly: `#file:.github/instructions/domain-model.instructions.md`.

## Access Control (cross-cutting)

Roles low→high: `VIEWER → EDITOR → ADMINISTRATOR → OWNER → OMNIADMIN` (OMNIADMIN set via `AICT_OMNIADMINS`). Enforce on routes with `@require_min_role(AppRole.X)`; **every resource is filtered by `app_id`** for tenant isolation. (Full RBAC + entity detail in `domain-model.instructions.md`.)

## Architecture Conventions

### Backend (`backend/`)

```
backend/
├── main.py              # FastAPI entry point (lifespan: CheckpointerCacheService, OIDC)
├── models/              # SQLAlchemy ORM models (import ALL via models/__init__.py)
├── schemas/             # Pydantic request/response schemas
├── repositories/        # Data access layer
├── services/            # Business logic layer
├── routers/
│   ├── internal/        # Frontend-backend API (session/OIDC auth)
│   ├── public/v1/       # External API (X-API-KEY, rate-limited, CORS-validated)
│   ├── mcp/             # JSON-RPC 2.0 MCP endpoints (X-API-KEY)
│   └── controls/        # Cross-cutting middleware: rate limit, CORS, file size
├── tools/               # AI/LLM integration utilities
│   ├── ai/              # LLM provider implementations
│   ├── embeddingTools.py        # Embedding provider factory
│   ├── vector_store_factory.py  # Per-silo: PGVector or Qdrant
│   └── langsmith_config.py      # Per-app + global LangSmith tracing
└── auth/                # Authentication handlers (FAKE, LOCAL, OIDC)
```

**Patterns:** DI for DB sessions (`db: Session = Depends(get_db)`) · role-based access (`@require_min_role(AppRole.OWNER)`) · business logic in **services**, not routers · `async/await` for LangChain and I/O.

### Frontend (`frontend/src/`)

```
core/         # ExtensibleBaseApp (library entry point) and config
components/    # ui/ · forms/ · playground/
pages/         # Page-level components
services/      # api.ts — ALL HTTP goes through here
contexts/      # user, theme, settings
constants/     # agentConstants.ts, messages.ts — keep in sync with backend defaults
auth/          # OIDC authentication
```

**Patterns:** all HTTP via `api.ts` · global state via Context (`useUser()`, `useTheme()`) · Tailwind utilities · protect routes with `ProtectedRoute` / `AdminRoute`.

### Client Projects (`clients/`)

Consume `@lksnext/ai-core-tools-base`. Customize via `src/config/clientConfig.ts` and `src/themes/`. **Never modify the base library** for client-specific features.

## Code Style

- **Python**: `snake_case` functions/vars, `PascalCase` classes, `UPPER_SNAKE_CASE` constants, type hints on all signatures.
- **TypeScript/React**: `PascalCase` components/interfaces, `use`-prefixed hooks, `handle`-prefixed event handlers, no `any` (use `unknown` + narrow).
- **Commits**: [Conventional Commits](https://www.conventionalcommits.org/) — `type(scope): description`.

## Database & Migrations

- **Always** create Alembic migrations for model changes (see `alembic.instructions.md`).
- Test **both** `upgrade` and `downgrade` before committing (`alembic downgrade -1`).
- Use `@alembic-expert` for migrations.

## Common Commands

```bash
# Backend
poetry install && uvicorn backend.main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev

# Tests
pytest tests/unit/ -v                 # fast, no DB
./scripts/test.sh -m integration      # auto-managed test DB (port 5433)
pytest -v --cov=backend --cov-report=term-missing

# Full stack
cd docker && docker compose up -d --build   # http://localhost/

# Library publish
cd frontend && npm run build:lib && npm run publish:npm
```

## Anti-Patterns to Avoid

- ❌ Direct `fetch()` in frontend — use `api.ts`
- ❌ Business logic in routers — move to services
- ❌ Raw SQL — use SQLAlchemy ORM
- ❌ Hardcoded secrets — use environment variables
- ❌ Modifying the base library for client needs — use `clientConfig.ts`
- ❌ Manual version bumping — use `@version-bumper`
- ❌ Skipping migration downgrades — always test rollback

## Quick Reference Links

- API Docs: http://localhost:8000/docs/internal · http://localhost:8000/docs/public
- Frontend dev: http://localhost:5173 · Full docs: `docs/`
