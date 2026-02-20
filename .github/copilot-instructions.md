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
- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS
- **Database**: PostgreSQL with pgvector extension
- **Infrastructure**: Docker, Docker Compose

## Specialized Agents

For domain-specific tasks, invoke these specialized agents:

| Agent | Invoke With | Use For |
|-------|-------------|---------|
| Backend Expert | `@backend-expert` | Python/FastAPI development, services, repositories |
| React Expert | `@react-expert` | React/TypeScript frontend, components, hooks |
| Alembic Expert | `@alembic-expert` | Database migrations, schema changes |
| Test Agent | `@test` | Writing and debugging tests |
| Version Bumper | `@version-bumper` | Semantic versioning in pyproject.toml |
| AI Dev Architect | `@ai-dev-architect` | Agent/instruction file management |
| Documentation Manager | `@docs-manager` | Documentation management, index/TOC, freshness tracking |

## Architecture Conventions

### Backend (`backend/`)

```
backend/
├── main.py              # FastAPI app entry point
├── models/              # SQLAlchemy ORM models
├── schemas/             # Pydantic request/response schemas
├── repositories/        # Data access layer
├── services/            # Business logic layer
├── routers/
│   ├── internal/        # Frontend-backend API (session auth)
│   └── public/          # External API (API key auth)
├── tools/               # AI/LLM integration utilities
└── auth/                # Authentication handlers
```

**Patterns:**
- Use **dependency injection** for database sessions: `db: Session = Depends(get_db)`
- Apply **role-based access** with: `@require_min_role(AppRole.OWNER)`
- Keep business logic in **services**, not routers
- Use **async/await** for LangChain and I/O operations

### Frontend (`frontend/`)

```
frontend/src/
├── core/                # ExtensibleBaseApp and config
├── components/          # Reusable UI components
│   ├── ui/              # Generic UI elements
│   ├── forms/           # Form components
│   └── playground/      # Agent playground components
├── pages/               # Page-level components
├── services/            # API client (api.ts)
├── contexts/            # React contexts
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
- Follow the migration workflow in `.github/instructions/.alembic.instructions.md`
- Test migrations both upgrade AND downgrade before committing

```bash
# Create migration
alembic revision --autogenerate -m "Add field_name to model_name"

# Apply
alembic upgrade head

# Rollback (test this!)
alembic downgrade -1
```

## Commit & Issue Guidelines

- Follow commit conventions in `.github/instructions/.gh-commit.instructions.md`
- Manage issues per `.github/instructions/.gh-issues.instructions.md`
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
docker-compose up -d
```

### Testing

```bash
# Backend tests
pytest tests/
pytest -k "test_name" -v

# Frontend linting
cd frontend && npm run lint
```

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
| `AICT_LOGIN` | Auth mode: `FAKE` or `OIDC` |
| `SECRET_KEY` | Session encryption key |
| `OPENAI_API_KEY` | LLM provider API key |
| `VECTOR_DB_TYPE` | `PGVECTOR` or `QDRANT` |

## Quick Reference Links

- API Docs (Internal): http://localhost:8000/docs/internal
- API Docs (Public): http://localhost:8000/docs/public
- Frontend Dev: http://localhost:5173
- Full documentation: `docs/` directory
