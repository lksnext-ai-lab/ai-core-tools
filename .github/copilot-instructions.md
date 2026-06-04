# Mattin AI - Global Copilot Instructions

This file provides repository-wide guidance for GitHub Copilot when working with the Mattin AI codebase.

## Project Overview

**Mattin AI** is an extensible AI toolbox platform providing:
- LLM integration (OpenAI, Anthropic, MistralAI, Azure OpenAI, Google, Ollama)
- RAG systems with multiple vector database backends (PGVector, Qdrant)
- AI agent management and execution
- Multi-tenant workspace architecture

**Tech Stack:**
- **Backend**: Python 3.11+, FastAPI, SQLAlchemy, Alembic, LangChain/LangGraph
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS
- **Database**: PostgreSQL with pgvector extension
- **Infrastructure**: Docker, Docker Compose

## Product & Domain Reference

This section describes **what Mattin AI does** from a product and domain perspective, so that every agent has shared context without needing to rediscover it from the codebase.

### Core Concepts

**App (Workspace)**: The central tenant unit. Every resource in the system (agents, silos, repos, services, API keys) is scoped to an App. Each App has an `owner`, a URL-safe `slug`, configurable rate limits, CORS origins, and max file sizes. Users create Apps to organize their AI work.

**User**: A platform account (email, name). A User can own multiple Apps and be a collaborator on others. Users authenticate in one of three modes set via `AICT_LOGIN`: `FAKE` (simplified email-only flow for local development), `LOCAL` (SaaS email + password with `UserCredential`), or `OIDC` (Azure Entra ID, used in production).

**Collaborator**: Users can be invited to an App with a specific role. The invitation workflow has states: `PENDING` → `ACCEPTED` / `DECLINED`.

### Role-Based Access Control

Roles from lowest to highest privilege:

| Role | Access Level |
|------|-------------|
| **VIEWER** | Read-only access to app resources |
| **EDITOR** | Create/edit agents, repos, silos, services, etc. |
| **ADMINISTRATOR** | Full app management except ownership transfer |
| **OWNER** | Full control including collaborator management and app deletion |
| **OMNIADMIN** | Cross-app superadmin (set via `AICT_OMNIADMINS` env var) |

Access is enforced with `@require_min_role(AppRole.EDITOR)` decorators on routes. All resources are filtered by `app_id` for tenant isolation.

### Domain Entities

#### AI Entities

| Entity | Purpose |
|--------|---------|
| **Agent** | Core AI agent. Configured with a system prompt, an LLM (via AIService), optional RAG (via Silo), memory settings, temperature, output parser, skills, and MCP tool configs. Can be composed: agents marked `is_tool=True` can be used as tools by other agents. |
| **OCRAgent** | Specialized Agent subclass (STI via `type` column). Dual-LLM: a vision model for scanned pages and a text model for structuring output. |
| **AIService** | LLM provider configuration. Stores provider type (OpenAI, Anthropic, MistralAI, Azure, Google, Custom), endpoint, API key. Each App can have multiple. |
| **EmbeddingService** | Embedding model configuration for vector stores. Providers: OpenAI, MistralAI, Ollama, Custom/HuggingFace, Azure OpenAI, Google AI Studio, Google Cloud Vertex AI. Provider selection happens via `backend/tools/embeddingTools.py`. |
| **Skill** | Reusable markdown prompt block that can be attached to agents (M:N via `agent_skills`). Injected into the agent's system prompt at execution time. |
| **OutputParser** | JSON-schema definition for structured LLM output. Stored as a `fields` JSON column. At runtime, dynamically generates a Pydantic model. Used by agents for structured responses and by silos for metadata filtering. |
| **Conversation** | Tracks a chat session between a user and an agent. Memory state stored in LangGraph's PostgreSQL checkpointer. Metadata (title, message count, last message) stored in the Conversation table. |

#### RAG / Content Entities

| Entity | Purpose |
|--------|---------|
| **Silo** | Vector store container. Each silo maps to a collection (`silo_{id}`) in a vector DB (PGVector or Qdrant, configurable per silo). Linked to an EmbeddingService. Agents connect to a Silo for RAG retrieval. |
| **Repository** | File-based document store. Contains uploaded files organized in folders. Every Repository is linked to a Silo — uploaded files are vectorized into that silo's collection. |
| **Resource** | Individual file within a Repository (PDF, text, etc.). |
| **Folder** | Hierarchical folder structure within a Repository. Self-referencing for nesting. |
| **Media** | Audio/video content within a Repository. Supports direct upload or YouTube URLs. Transcribed with configurable chunking (min/max duration, overlap), then vectorized. |
| **Domain** | Web scraping source. Configured with a base URL and CSS selectors. Crawled URLs are vectorized into the linked Silo. |
| **DomainUrl / CrawlPolicy / CrawlJob** | Domain crawling pipeline. `DomainUrl` is each individual URL discovered, `CrawlPolicy` defines per-domain crawl rules, `CrawlJob` tracks an in-flight crawl run. |
| **SharePointSource** | Microsoft SharePoint connector configured per Silo. Syncs documents from a SharePoint location into the silo's collection. |
| **SharePointFile** | Individual file synced from a `SharePointSource` (mirrors `Resource` for the SharePoint case). |

#### MCP Entities (Dual-Role Architecture)

Mattin AI acts as **both** an MCP server and an MCP client:

| Entity | Role | Purpose |
|--------|------|---------|
| **MCPServer** | Server (outbound) | Exposes agents as MCP tools to external clients (Claude Desktop, Cursor). Has a slug for URL routing, rate limiting, and agent-to-tool mappings. |
| **MCPConfig** | Client (inbound) | Stores connection config for external MCP servers that agents can consume as tool sources. Linked to agents via `agent_mcps` join table. |

#### Auth Entity

| Entity | Purpose |
|--------|---------|
| **APIKey** | 64-character key for programmatic access (public API + MCP). Scoped to an App, owned by a User. Shown once on creation. |
| **UserCredential** | Hashed email/password credentials used when `AICT_LOGIN=LOCAL` (SaaS mode). One-to-one with `User`. |

#### Marketplace & Billing Entities

| Entity | Purpose |
|--------|---------|
| **AgentMarketplaceProfile** | Public marketplace listing for an Agent (description, category, tags). One-to-one with `Agent`. |
| **AgentMarketplaceRating** | User ratings/reviews of marketplace-published agents. |
| **MarketplaceUsage** | Counter for marketplace invocations of an agent. |
| **Subscription** | A User's subscription plan. References a `TierConfig`, has `SubscriptionTier`, `BillingStatus`. |
| **TierConfig** | Defines a pricing tier (Free, Pro, Enterprise…) and the feature limits / quotas it grants. |
| **UsageRecord** | Per-resource billable usage records (API calls, file uploads, etc.) for quota enforcement and billing. |
| **SystemSetting** | Cross-app key/value system configuration (OMNIADMIN-managed). |

### Entity Relationships (Key FKs)

```
User ──owns──► App (1:N)
User ◄──collaborates──► App (M:N via AppCollaborator with role + status)

App ──has──► Agent, Silo, Repository, Domain, AIService, EmbeddingService,
             OutputParser, Skill, MCPServer, MCPConfig, APIKey (all 1:N)

Agent ──uses──► AIService (N:1)           # Which LLM to call
Agent ──links──► Silo (N:1, optional)     # RAG knowledge base
Agent ──uses──► OutputParser (N:1, opt.)  # Structured output
Agent ◄──► Skill (M:N via agent_skills)
Agent ◄──► MCPConfig (M:N via agent_mcps)
Agent ◄──► Agent (M:N via agent_tools)    # Agent-as-tool composition

Silo ──uses──► EmbeddingService (N:1)
Silo ◄── Repository (1:N)
Silo ◄── Domain (1:N)

Repository ──► Resource (1:N), Folder (1:N), Media (1:N)
Domain ──► Url (1:N)

MCPServer ◄──► Agent (M:N via mcp_server_agents)
```

### API Surface

Three distinct API groups with different authentication:

| Group | Prefix | Auth | Purpose |
|-------|--------|------|---------|
| **Internal** | `/internal` | Session/JWT (OIDC or dev) | Frontend ↔ Backend. Full CRUD for all entities. |
| **Public v1** | `/public/v1` | `X-API-KEY` header | External programmatic access. Chat, file upload, repo/silo ops. |
| **MCP** | `/mcp/v1` | `X-API-KEY` header | JSON-RPC 2.0 for Model Context Protocol. |

**Public API controls:** per-app rate limiting (`App.agent_rate_limit`), CORS origin validation (`App.agent_cors_origins`), file size limits (`App.max_file_size_mb`).

### Key User Workflows

1. **Create App** → Configure AI services (LLM + embedding) → Create agents → Chat via playground or API
2. **Build knowledge base** → Create silo → Create repository → Upload files → Files vectorized → Link silo to agent → Agent uses RAG
3. **Web scraping for RAG** → Create silo → Create domain with URL + selectors → Scrape → Content vectorized
4. **Media transcription** → Upload audio/video to repository → Transcribed → Chunked → Vectorized
5. **Structured output** → Create output parser (JSON schema) → Attach to agent → Agent returns structured JSON
6. **Agent composition** → Mark agent as `is_tool` → Link as tool to another agent → Parent agent delegates to child
7. **MCP server exposure** → Create MCPServer → Attach agents → External tools (Claude Desktop, Cursor) connect via slug URL
8. **MCP tool consumption** → Create MCPConfig with external server connection → Link to agent → Agent uses external tools
9. **Collaboration** → Owner invites users by email with role → Invitee accepts → Collaborator accesses app resources
10. **API access** → Generate API key → Use `X-API-KEY` header for public API or MCP endpoints

### Agent Execution Flow

```
User message (+ optional files)
  → AgentExecutionService.execute_agent_chat()
    → Process file attachments (PDF text extraction, image encoding)
    → Get/create conversation session (if memory enabled)
    → Build LangGraph agent chain:
        • LLM from AIService config
        • Tools: agent-as-tool children + MCP client tools + silo retriever
        • Skills injected into system prompt
        • Memory via LangGraph PostgreSQL checkpointer
    → Format prompt via prompt_template
    → agent_chain.ainvoke(messages, config)
    → Apply output parser (if configured)
    → Update conversation metadata + request count
    → Return {response, agent_id, conversation_id, metadata}
```

### Memory Management

- **Storage**: LangGraph's `AsyncPostgresSaver` in PostgreSQL
- **Thread ID**: `thread_{agent_id}_{session_id}`
- **Config per agent**: `has_memory`, `memory_max_messages` (default 20), `memory_max_tokens` (default 4000), `memory_summarize_threshold` (default 10)
- **Strategies**: Token counting (tiktoken), message trimming (keeps recent N, preserves system messages), tool message cleanup

### Client Deployment Model

The frontend is a **reusable npm library** (`@lksnext/ai-core-tools-base`):
- Base library provides all pages, components, contexts, auth, themes
- Client projects (`clients/<name>/`) import the library and customize via `clientConfig.ts`: theme, branding, auth config, API URL, feature flags, custom routes
- All clients share the same backend

### Notable Features

- **Per-silo vector DB type**: Each silo independently uses PGVector or Qdrant
- **Dynamic Pydantic models**: OutputParser JSON schemas become Pydantic models at runtime
- **Multimodal chat**: Agents accept images alongside text (base64 or signed static URLs)
- **Secure static files**: `/static/{path}` requires cryptographic signature
- **Cascade deletion**: `AppService.delete_app()` performs ordered deletion across all entity types
- **LangSmith tracing**: Optional per-app tracing via `App.langsmith_api_key` (project = app name), with a global env-var fallback (`LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY` + `LANGSMITH_PROJECT`) for development. Validated via `POST /internal/apps/{id}/langsmith/test`. Central helper: `backend/tools/langsmith_config.py`.

## Specialized Agents

For domain-specific tasks, invoke these specialized agents:

| Agent | Invoke With | Use For |
|-------|-------------|---------|
| Issue Reader | `@issue-reader` (or `/start-from-issue`) | **Entry point for issue-driven work**. Reads a GitHub issue via the `@github` MCP server, emits an Issue Analysis block, and offers handoff to `@feature-planner` (formal spec) or `@quick-executor` (autonomous ad-hoc) |
| Bug Analyzer | `@bug-analyzer` (or `/report-bug`) | **Entry point for chat-reported bugs** (no GitHub issue needed). Investigates the codebase to locate the root cause, emits a Bug Analysis block with `file:line` evidence + a regression test, and offers handoff to `@quick-executor` (small fix, reproduce-first) or `@feature-planner` (large/architectural). Read-only. |
| Backend Expert | `@backend-expert` | Python/FastAPI development, services, repositories |
| React Expert | `@react-expert` | React/TypeScript frontend, components, hooks |
| Alembic Expert | `@alembic-expert` | Database migrations, schema changes |
| Git & GitHub | `@git-github` | Git workflows, issues, PRs, releases, branching |
| Test Expert | `@test-expert` | Writing, debugging, and maintaining tests — pytest fixtures, unit/integration test setup, mocking, CI coverage |
| Version Bumper | `@version-bumper` | Semantic versioning in `pyproject.toml` (mainly next-dev-cycle bump after a release) |
| AI Dev Architect | `@ai-dev-architect` | Agent / instruction / prompt / skill file management — the Copilot ecosystem itself |
| Quick Executor | `@quick-executor` (or `/quick-execute`) | **Autonomous ad-hoc executor**. Twin of `@plan-executor` without the `/plans/` spec. Auto-invokes implementer subagents, runs git directly with commit / push / PR confirmation gates. Use for bugs and small fixes you want executed end-to-end without manual handoffs. |
| Feature Planner | `@feature-planner` | Structured feature planning, specs, and plan tracking in `/plans`; supports plan extensions |
| Plan Executor | `@plan-executor` | Reads plans from `/plans`, generates sequenced step files for implementation agents, executes plan extensions with continuous step numbering |
| Documentation Manager | `@docs-manager` | Documentation management, index/TOC, freshness tracking |
| Open Source Manager | `@oss-manager` | Licensing, community files, changelog *content*, release notes, OSS governance |
| Release Manager | `@release-manager` | Complete release workflow — version bump, changelog, merge to main, tagging, GitHub releases |
| Website Maintainer | `@website-maintainer` | Cross-repo agent for the `mattinai.github.io` landing site — syncs content, translations (ES/EN/EU), version references after each release |

## Architecture Conventions

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
│   ├── public/v1/       # External API (X-API-KEY, rate-limited, CORS-validated)
│   ├── mcp/             # JSON-RPC 2.0 MCP endpoints (X-API-KEY)
│   └── controls/        # Cross-cutting middleware: rate limit, CORS, file size
├── tools/               # AI/LLM integration utilities
│   ├── ai/              # LLM provider implementations
│   ├── embeddingTools.py        # Embedding provider factory (OpenAI, Mistral, Google, Vertex…)
│   ├── vector_store_factory.py  # Per-silo factory: PGVector or Qdrant
│   └── langsmith_config.py      # Per-app + global LangSmith tracing config
└── auth/                # Authentication handlers (FAKE, LOCAL, OIDC)
```

**Patterns:**
- Use **dependency injection** for database sessions: `db: Session = Depends(get_db)`
- Apply **role-based access** with: `@require_min_role(AppRole.OWNER)`
- Keep business logic in **services**, not routers
- Use **async/await** for LangChain and I/O operations

### Frontend (`frontend/`)

```
frontend/src/
├── core/                # ExtensibleBaseApp (library entry point) and config
├── components/          # Reusable UI components
│   ├── ui/              # Generic UI elements
│   ├── forms/           # Form components
│   └── playground/      # Agent playground components
├── pages/               # Page-level components
├── services/            # API client (api.ts — all HTTP goes through here)
├── contexts/            # React contexts (user, theme, settings)
├── constants/           # Shared constants (agentConstants.ts, messages.ts).
│                        # Must stay in sync with backend defaults — e.g.
│                        # DEFAULT_MEMORY_SUMMARIZE_THRESHOLD matches the
│                        # Agent model default in the backend.
└── auth/                # OIDC authentication
```

**Patterns:**
- Use the centralized `api.ts` service for all HTTP calls
- Access global state via React Context (`useUser()`, `useTheme()`)
- Style with Tailwind CSS utility classes
- Protect routes with `ProtectedRoute` and `AdminRoute` components

### Client Projects (`clients/`)

Client-specific frontends that consume `@lksnext/ai-core-tools-base` library.
- All customization via `src/config/clientConfig.ts`
- Theme files in `src/themes/`
- **Never modify** the base library directly for client-specific features

## Code Style Guidelines

### Python

```python
# Function and variable names: snake_case
def process_user_request(user_id: int) -> None:
    pass

# Class names: PascalCase
class UserService:
    pass

# Constants: UPPER_SNAKE_CASE
MAX_RETRY_ATTEMPTS = 3

# Type hints: Always use for function signatures
async def get_agent(agent_id: int, db: Session) -> Agent | None:
    pass
```

### TypeScript/React

```typescript
// Component names: PascalCase
const UserProfile: React.FC<UserProfileProps> = ({ userId }) => {
  // Hook naming: use prefix
  const [isLoading, setIsLoading] = useState(false);
  
  // Event handlers: handle prefix
  const handleSubmit = () => { /* ... */ };
  
  return <div className="p-4">{/* JSX */}</div>;
};

// Interface names: PascalCase, describe what it's for
interface UserProfileProps {
  userId: string;
  onUpdate?: (user: User) => void;
}
```

## Database & Migrations

- **Always** create Alembic migrations for model changes
- Follow the migration workflow in `.github/instructions/alembic.instructions.md`
- Test migrations both upgrade AND downgrade before committing

```bash
# Create migration
alembic revision --autogenerate -m "Add field_name to model_name"

# Apply
alembic upgrade head

# Rollback (test this!)
alembic downgrade -1
```

## Agent Handoff Convention

Implementation agents (`@backend-expert`, `@react-expert`, `@alembic-expert`, `@docs-manager`, `@test-expert`) **do not run git commands**. When they finish a task, they:

1. Provide a **change summary** with type, scope, description, and files changed
2. Suggest the user invoke `@git-github` to commit, push, or create a PR

**Workflow:**
```
@backend-expert  →  (implements feature)  →  suggests @git-github
@react-expert    →  (implements UI)       →  suggests @git-github
@alembic-expert  →  (creates migration)   →  suggests @git-github
@docs-manager    →  (updates docs)        →  suggests @git-github
@test-expert            →  (writes tests)        →  suggests @git-github
```

The `@git-github` agent follows the `git-github` skill (`.github/skills/git-github.skill.md`) for the standard commit/push/PR workflow.

## Commit & Issue Guidelines

- Follow commit, branch and GitHub CLI conventions in `.github/instructions/git-github.instructions.md` (GPG signing, GitFlow, `--body-file` rule, remotes, labels)
- Use [Conventional Commits](https://www.conventionalcommits.org/): `type(scope): description`

## Common Commands

### Development

```bash
# Backend
poetry install
uvicorn backend.main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev

# Full stack (Docker)
cd docker && docker compose up -d --build    # App served at http://localhost/
```

### Testing

```bash
# Fast unit tests — no database needed
pytest tests/unit/ -v

# Integration tests with auto-managed test DB (ephemeral Postgres on port 5433)
./scripts/test.sh -m integration

# Or manually:
docker compose -f docker/docker-compose.yaml --profile test up -d db_test
pytest tests/integration/ -v

# Full suite with coverage
pytest -v --cov=backend --cov-report=term-missing

# Run a single test by name
pytest -k "test_name" -v

# Frontend linting (no frontend tests yet — Phase 5)
cd frontend && npm run lint
```

> See `docs/testing/` for the full testing guide. Use `@test-expert` for help writing or debugging tests.

### Library Publishing

```bash
# Build base library
cd frontend && npm run build:lib

# Publish to npm
npm run publish:npm
```

## Anti-Patterns to Avoid

- ❌ Direct `fetch()` calls in frontend — use `api.ts` service
- ❌ Business logic in routers — move to services
- ❌ Raw SQL queries — use SQLAlchemy ORM
- ❌ Hardcoded secrets — use environment variables
- ❌ Modifying base library for client-specific needs — customize via `clientConfig.ts`
- ❌ Manual version bumping — use `@version-bumper` agent
- ❌ Skipping migration downgrades — always test rollback

## Environment Variables

Key variables to set (see `CLAUDE.md` for full list):

| Variable | Purpose |
|----------|---------|
| `SQLALCHEMY_DATABASE_URI` | PostgreSQL connection string |
| `AICT_LOGIN` | Auth mode: `FAKE` (dev) \| `LOCAL` (SaaS email+password) \| `OIDC` (production) |
| `AICT_MODE` | Deployment mode: `SELF-HOSTED` \| `SAAS` (changes feature flags and billing behavior) |
| `AICT_OMNIADMINS` | Comma-separated emails granted OMNIADMIN role |
| `SECRET_KEY` | Session encryption key |
| `OPENAI_API_KEY` | LLM provider API key (one per provider used) |
| `VECTOR_DB_TYPE` | Default vector store backend: `PGVECTOR` \| `QDRANT` (overridable per-silo) |
| `LANGSMITH_TRACING` / `LANGSMITH_API_KEY` / `LANGSMITH_PROJECT` | Optional global LangSmith tracing fallback when no per-app key is set |

## Quick Reference Links

- API Docs (Internal): http://localhost:8000/docs/internal
- API Docs (Public): http://localhost:8000/docs/public
- Frontend Dev: http://localhost:5173
- Full documentation: `docs/` directory
