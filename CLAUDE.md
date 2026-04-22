# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Mattin AI** is an extensible AI toolbox platform providing LLM integration, RAG systems, vector databases, and AI agent management. The project uses a **FastAPI backend** and a **React frontend** distributed as a reusable npm library for client-specific deployments.

**Tech Stack**: Python 3.11+, FastAPI, SQLAlchemy, Alembic, LangChain/LangGraph, PostgreSQL + pgvector, React 18, TypeScript, Vite, Tailwind CSS.

## Development Commands

### Backend

```bash
poetry install
uvicorn backend.main:app --reload --port 8000

# Migrations
alembic upgrade head
alembic revision --autogenerate -m "description"
alembic downgrade -1                            # Always test rollback
```

### Frontend

```bash
cd frontend
npm install
npm run dev                     # Dev server (port 5173)
npm run build:lib               # Build reusable library package
npm run build:lib:watch         # Watch mode for library development
npm run lint
```

### Testing

```bash
# Start test DB (port 5433, separate from dev DB)
docker compose -f docker/docker-compose.yaml --profile test up -d db_test
# Or use the helper that auto-manages the test DB lifecycle:
./scripts/test.sh -m integration

# Unit tests — no DB needed
pytest tests/unit/ -v

# Integration tests — require test DB
pytest tests/integration/ -v

# Single test by name
pytest -k "test_name" -v

# Full suite with coverage
pytest -v --cov=backend --cov-report=term-missing
```

Test DB connection: `postgresql://test_user:test_pass@localhost:5433/test_db`. Config in `pyproject.toml` under `[tool.pytest.ini_options]` — `pytest-env` sets env vars before module load (critical for DB URL).

### Docker

Despliegue single-host con Caddy como reverse proxy. Mismo setup para dev local y servidores cliente — solo cambia el `.env`.

```bash
cd docker
cp .env.example .env             # Editar claves y AICT_OMNIADMINS
docker compose up -d --build
docker compose logs -f backend
docker compose down -v           # Parar y borrar volúmenes
```

- Único puerto publicado al host: 80 (Caddy). Back/front/Postgres/Qdrant solo en red interna.
- Acceso: `http://localhost/` en local, `http://<ip-servidor>/` en cliente.
- Swagger: `/docs/internal` y `/docs/public` desde el mismo origen.
- Utilities aisladas (p. ej. Qdrant + web UI): `docker/utilities/`.

### Client Project Management

```bash
./deploy/scripts/create-client-project.sh <client-name>
./deploy/scripts/update-client.sh <client-name>
./deploy/scripts/publish-library.sh
```

## Domain Model

**App (Workspace)**: Central tenant unit. Every resource (agents, silos, repos, services, API keys) is scoped to an App.

**Role hierarchy** (lowest → highest): `VIEWER` → `EDITOR` → `ADMINISTRATOR` → `OWNER` → `OMNIADMIN` (set via `AICT_OMNIADMINS` env var). Enforced with `@require_min_role(AppRole.EDITOR)` decorators.

### Core Entities

| Entity | Purpose |
|--------|---------|
| **Agent** | Core AI agent. Configured with system prompt, LLM (AIService), optional RAG (Silo), memory settings, output parser, skills, and MCP tool configs. Agents with `is_tool=True` can be used as tools by other agents. |
| **OCRAgent** | Agent subclass (STI via `type` column). Dual-LLM: vision model for scanned pages + text model for structuring output. |
| **AIService** | LLM provider config (OpenAI, Anthropic, MistralAI, Azure, Google, Custom). |
| **EmbeddingService** | Embedding model config for vector stores. |
| **Skill** | Reusable markdown prompt block attached to agents (M:N). Injected into system prompt at execution time. |
| **OutputParser** | JSON-schema definition for structured LLM output. Dynamically generates a Pydantic model at runtime. |
| **Conversation** | Chat session. Memory state in LangGraph's PostgreSQL checkpointer; metadata in Conversation table. |
| **Silo** | Vector store container. Maps to a collection (`silo_{id}`) in PGVector or Qdrant (configurable per silo). |
| **Repository** | File-based document store linked to a Silo. Uploaded files are vectorized into the silo's collection. |
| **Domain** | Web scraping source. Crawled URLs vectorized into linked Silo. |
| **MCPServer** | Exposes agents as MCP tools to external clients (Claude Desktop, Cursor). |
| **MCPConfig** | Connection config for external MCP servers consumed as tool sources by agents. |
| **APIKey** | 64-character key for public API + MCP access. Scoped to an App. Shown once on creation. |

### Key Entity Relationships

```
User ──owns──► App (1:N)
User ◄──collaborates──► App  (M:N via AppCollaborator with role + status: PENDING→ACCEPTED/DECLINED)

App ──has──► Agent, Silo, Repository, Domain, AIService, EmbeddingService,
             OutputParser, Skill, MCPServer, MCPConfig, APIKey (all 1:N)

Agent ──uses──► AIService (N:1)
Agent ──links──► Silo (N:1, optional)
Agent ──uses──► OutputParser (N:1, optional)
Agent ◄──► Skill, MCPConfig, Agent (M:N — agent-as-tool composition)

Silo ◄── Repository, Domain (1:N)
MCPServer ◄──► Agent (M:N via mcp_server_agents)
```

## Architecture

### Backend (`backend/`)

```
backend/
├── main.py              # FastAPI app entry point (lifespan: CheckpointerCacheService, OIDC)
├── models/              # SQLAlchemy ORM models (import ALL via models/__init__.py)
├── schemas/             # Pydantic request/response schemas
├── repositories/        # Data access layer
├── services/            # Business logic layer
├── routers/
│   ├── internal/        # Frontend-backend API (session/OIDC auth)
│   ├── public/v1/       # External API (X-API-KEY auth, rate limiting)
│   └── mcp/             # JSON-RPC 2.0 MCP endpoints (X-API-KEY auth)
├── tools/               # AI/LLM integration utilities
│   ├── ai/              # LLM provider implementations
│   └── vector_store_factory.py  # Factory for PGVector/Qdrant backends
└── auth/                # Authentication handlers
```

**Patterns:**
- Business logic in **services**, data access in **repositories**, routing in **routers**
- DB sessions via dependency injection: `db: Session = Depends(get_db)`
- Role-based access: `@require_min_role(AppRole.OWNER)`
- Async/await for LangChain and I/O operations

**Agent Execution** (`backend/services/agent_execution_service.py`):
```
User message + optional files
  → Process file attachments (PDF extraction, image encoding)
  → Get/create conversation (thread_{agent_id}_{session_id})
  → Build LangGraph chain: LLM + tools (agent-as-tool + MCP + silo retriever) + memory
  → agent_chain.ainvoke() → apply OutputParser → persist conversation → return response
```

**Memory**: `AsyncPostgresSaver` in PostgreSQL. Config per agent: `has_memory`, `memory_max_messages` (default 20), `memory_max_tokens` (default 4000), `memory_summarize_threshold` (default 10).

### Frontend (`frontend/src/`)

```
frontend/src/
├── core/                # ExtensibleBaseApp.tsx — library entry point
├── components/          # Reusable UI (ui/, forms/, playground/)
├── pages/               # Page-level components
├── services/            # api.ts — centralized HTTP client
├── contexts/            # React contexts (user, theme, settings)
└── auth/                # OIDC authentication
```

**Patterns:**
- All HTTP calls via `api.ts` — never direct `fetch()`
- Global state via React Context (`useUser()`, `useTheme()`)
- Route protection via `ProtectedRoute` and `AdminRoute` components

### Client Projects (`clients/<name>/`)

Frontend-only projects consuming `@lksnext/ai-core-tools-base`. All customization via `src/config/clientConfig.ts` (theme, branding, auth config, API URL, feature flags, custom routes). Never modify the base library for client-specific features.

When base library changes:
```bash
cd frontend && npm run build:lib
cd ../clients/<client-name> && npm install
```

## Environment Configuration

### Backend `.env`

```env
SQLALCHEMY_DATABASE_URI=postgresql://user:pass@localhost:5432/dbname
AICT_LOGIN=FAKE                 # FAKE (dev) | LOCAL (SaaS email+password) | OIDC (production)
SECRET_KEY=your-secret-key
AICT_OMNIADMINS=admin@example.com

OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
MISTRAL_API_KEY=...

VECTOR_DB_TYPE=PGVECTOR         # or QDRANT
QDRANT_URL=http://localhost:6333

# OIDC (if AICT_LOGIN=OIDC)
ENTRA_TENANT_ID=...
ENTRA_CLIENT_ID=...
ENTRA_CLIENT_SECRET=...

# Optional
LANGSMITH_TRACING=false
LANGSMITH_API_KEY=...
```

### Frontend `.env`

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_OIDC_ENABLED=false
VITE_OIDC_AUTHORITY=https://...
VITE_OIDC_CLIENT_ID=...
VITE_OIDC_REDIRECT_URI=http://localhost:5173/auth/success
VITE_OIDC_SCOPE=openid profile email
```

Local dev: port 5173 (Vite). Docker: port 3000.

## Notable Behaviors

- **Per-silo vector DB type**: Each silo independently uses PGVector or Qdrant
- **Dynamic Pydantic models**: OutputParser JSON schemas become Pydantic models at runtime
- **Multimodal chat**: Agents accept images (base64 or signed static URLs)
- **Secure static files**: `/static/{path}` requires cryptographic signature
- **Cascade deletion**: `AppService.delete_app()` performs ordered deletion across all entity types
- **LangSmith tracing**: Optional per-app tracing via `App.langsmith_api_key`
- **MCP dual-role**: Mattin AI acts as both MCP server (exposing agents) and MCP client (consuming external tool servers)

## Anti-Patterns

- Direct `fetch()` in frontend — use `api.ts`
- Business logic in routers — belongs in services
- Raw SQL queries — use SQLAlchemy ORM
- Modifying base library for client-specific features — use `clientConfig.ts`
- Skipping migration downgrade tests — always verify rollback works
- Manual version bumping — use semantic versioning tooling

## Additional Documentation

- `docs/CLIENT_SETUP_GUIDE.md` — Client project setup
- `docs/AUTHENTICATION_MIGRATION_GUIDE.md` — Auth system details
- `docs/EXTERNAL_MCP_SETUP.md` — MCP integration
- `docs/testing/` — Full testing guide
- `.github/copilot-instructions.md` — Comprehensive domain reference and agent conventions
- API Docs: http://localhost:8000/docs/internal and http://localhost:8000/docs/public
