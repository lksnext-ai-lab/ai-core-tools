# Backend Architecture

> Part of [Mattin AI Documentation](../README.md)

## Overview

The backend is a **Python 3.11+ FastAPI application** following a **layered architecture** pattern:

```
Routers (HTTP endpoints)
    ↓
Services (Business logic)
    ↓
Repositories (Data access)
    ↓
Models (Database entities)
```

**Entry point**: `backend/main.py` — Initializes FastAPI app, mounts routers, configures middleware, and manages application lifespan (startup/shutdown hooks).

**Key features**:
- **Async/await** throughout for I/O-bound operations
- **Dependency injection** for database sessions and authentication
- **Multi-router architecture** (Internal, Public, MCP) with different auth strategies
- **LangChain integration** for LLM orchestration
- **Connection pooling** for PostgreSQL and LangGraph checkpointer

## Router Layer

Three distinct router groups handle different authentication and use cases:

### Internal API Routers (`/internal/*`)

**Authentication**: Session-based (OIDC or FAKE mode)
**Purpose**: Frontend-to-backend communication for the web application

| Router | Endpoint | Purpose |
|--------|----------|---------|
| **admin** | `/internal/admin` | Admin operations, user management |
| **agents** | `/internal/agents` | Agent CRUD, configuration |
| **ai_services** | `/internal/ai_services` | AI service (LLM) configuration |
| **api_keys** | `/internal/api_keys` | API key management |
| **apps** | `/internal/apps` | App (workspace) CRUD |
| **apps_usage** | `/internal/apps_usage` | Usage statistics per app |
| **auth** | `/internal/auth` | Login, logout, session management |
| **collaboration** | `/internal/collaboration` | App collaboration invites |
| **conversations** | `/internal/conversations` | Conversation history management |
| **domains** | `/internal/domains` | Domain management for RAG |
| **embedding_services** | `/internal/embedding_services` | Embedding service config |
| **folders** | `/internal/folders` | Folder management for repositories |
| **mcp_configs** | `/internal/mcp_configs` | MCP configuration CRUD |
| **mcp_servers** | `/internal/mcp_servers` | MCP server management |
| **ocr** | `/internal/ocr` | OCR operations |
| **output_parsers** | `/internal/output_parsers` | Output parser CRUD |
| **repositories** | `/internal/repositories` | Repository CRUD, file operations |
| **silos** | `/internal/silos` | Silo (vector store) CRUD |
| **skills** | `/internal/skills` | Skill management (legacy) |
| **user** | `/internal/user` | User profile |
| **version** | `/internal/version` | Backend version info |

**Common pattern**:
```python
@router.get("/{agent_id}")
async def get_agent(
    agent_id: int,
    app_id: int,
    role: AppRole = Depends(require_min_role(AppRole.VIEWER)),
    db: Session = Depends(get_db)
):
    agent = await agent_service.get_agent(agent_id, app_id, db)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent
```

### Public API Routers (`/public/v1/*`)

**Authentication**: API key-based with rate limiting
**Purpose**: External programmatic access to Mattin AI features

| Router | Endpoint | Purpose |
|--------|----------|---------|
| **agents** | `/public/v1/agents` | Agent execution and management |
| **auth** | `/public/v1/auth` | API key validation |
| **chat** | `/public/v1/chat` | Agent chat execution (streaming SSE) |
| **files** | `/public/v1/files` | File upload and management |
| **ocr** | `/public/v1/ocr` | OCR operations |
| **repositories** | `/public/v1/repositories` | Repository operations |
| **resources** | `/public/v1/resources` | Resource management |
| **silos** | `/public/v1/silos` | Silo operations |

**Common pattern**:
```python
@router.post("/chat")
async def chat(
    request: ChatRequest,
    api_key: APIKey = Depends(verify_api_key),
    rate_limit: None = Depends(rate_limit_dependency),
    db: Session = Depends(get_db)
):
    # Stream response via Server-Sent Events (SSE)
    return StreamingResponse(
        agent_service.stream_chat(request, db),
        media_type="text/event-stream"
    )
```

### MCP Router (`/mcp/v1/*`)

**Authentication**: Custom protocol-based
**Purpose**: Model Context Protocol (MCP) server communication

Handles MCP server-to-backend communication for tool invocation and resource access.

### Controls (Router Utilities)

Reusable dependencies for cross-cutting concerns:

| Control | Purpose |
|---------|---------|
| **rate_limit** | Rate limiting per API key or IP |
| **role_authorization** | Role-based access control (RBAC) |
| **file_size_limit** | Enforce file upload size limits |
| **origins** | Manage allowed CORS origins |

**Example usage**:
```python
from routers.controls.role_authorization import require_min_role, AppRole
from routers.controls.rate_limit import rate_limit_dependency

@router.post("/")
async def create_agent(
    role: AppRole = Depends(require_min_role(AppRole.EDITOR)),
    rate_limit: None = Depends(rate_limit_dependency),
    db: Session = Depends(get_db)
):
    ...
```

## Service Layer

**28 services** implement business logic, isolated from HTTP concerns:

| Service | Purpose |
|---------|---------|
| **agent_cache_service** | LangGraph checkpointer and memory caching |
| **agent_execution_service** | Agent execution orchestration (LangGraph) |
| **agent_service** | Agent CRUD and configuration |
| **ai_service_service** | AI service (LLM) management |
| **api_key_service** | API key generation, validation, revocation |
| **app_collaboration_service** | App collaboration invites and management |
| **app_service** | App (workspace) CRUD |
| **conversation_service** | Conversation history management |
| **domain_service** | Domain management for web scraping |
| **embedding_service_service** | Embedding service management |
| **file_management_service** | File upload, storage, retrieval |
| **file_size_limit_service** | File size limit configuration |
| **folder_service** | Folder CRUD for repositories |
| **mcp_config_service** | MCP configuration management |
| **mcp_server_service** | MCP server lifecycle management |
| **media_service** | Media file handling (images, audio, video) |
| **memory_management_service** | Agent memory and context management |
| **origins_service** | CORS origin configuration |
| **output_parser_service** | Output parser CRUD |
| **rate_limit_service** | Rate limit configuration |
| **repository_service** | Repository CRUD, file operations |
| **resource_service** | Resource management |
| **silo_service** | Silo (vector store) management |
| **skill_service** | Skill management (legacy) |
| **transcription_service** | Audio transcription (Whisper) |
| **url_service** | URL management for domains |
| **user_service** | User profile management |
| **web_crawler_service** | Web scraping and crawling |

**Service pattern**:
```python
class AgentService:
    async def get_agent(self, agent_id: int, app_id: int, db: Session) -> Agent | None:
        repo = AgentRepository()
        agent = await repo.get_by_id(agent_id, db)
        # Verify agent belongs to app (authorization check)
        if agent and agent.app_id != app_id:
            return None
        return agent
```

Services orchestrate multiple repositories, handle business rules, and integrate with external systems (LLMs, vector databases).

## Repository Layer

**19 repositories** provide data access abstraction using **SQLAlchemy ORM**:

| Repository | Model | Purpose |
|------------|-------|---------|
| **agent_repository** | Agent | Agent CRUD |
| **ai_service_repository** | AIService | AI service CRUD |
| **api_key_repository** | APIKey | API key CRUD |
| **app_collaborator_repository** | AppCollaborator | Collaboration CRUD |
| **app_repository** | App | App CRUD |
| **conversation_repository** | Conversation | Conversation CRUD |
| **domain_repository** | Domain | Domain CRUD |
| **embedding_service_repository** | EmbeddingService | Embedding service CRUD |
| **folder_repository** | Folder | Folder CRUD |
| **mcp_config_repository** | MCPConfig | MCP config CRUD |
| **mcp_server_repository** | MCPServer | MCP server CRUD |
| **media_repository** | Media | Media file CRUD |
| **ocr_agent_repository** | OCRAgent | OCR agent CRUD |
| **output_parser_repository** | OutputParser | Output parser CRUD |
| **repository_repository** | Repository | Repository CRUD |
| **resource_repository** | Resource | Resource CRUD |
| **silo_repository** | Silo | Silo CRUD |
| **url_repository** | Url | URL CRUD |
| **user_repository** | User | User CRUD |

**Repository pattern**:
```python
class AgentRepository:
    def get_by_id(self, agent_id: int, db: Session) -> Agent | None:
        return db.query(Agent).filter(Agent.agent_id == agent_id).first()
    
    def get_by_app(self, app_id: int, db: Session) -> list[Agent]:
        return db.query(Agent).filter(Agent.app_id == app_id).all()
    
    def create(self, agent: Agent, db: Session) -> Agent:
        db.add(agent)
        db.commit()
        db.refresh(agent)
        return agent
```

Repositories encapsulate SQL queries and provide a clean interface for data operations.

## Models

**22 SQLAlchemy ORM models** represent database entities:

| Model | Table | Purpose |
|-------|-------|---------|
| **User** | `users` | Application users |
| **App** | `apps` | Workspaces (multi-tenant isolation) |
| **AppCollaborator** | `app_collaborators` | App collaboration |
| **APIKey** | `api_keys` | API keys for public API |
| **AIService** | `ai_services` | LLM provider configurations |
| **EmbeddingService** | `embedding_services` | Embedding model configurations |
| **OutputParser** | `output_parsers` | Structured output parsers |
| **MCPConfig** | `mcp_configs` | MCP configurations |
| **MCPServer** | `mcp_servers` | MCP server instances |
| **MCPServerAgent** | `mcp_server_agents` | MCP server-agent associations |
| **Silo** | `silos` | Vector stores for RAG |
| **Agent** | `agents` | AI agents |
| **OCRAgent** | `ocr_agents` | OCR-specific agents |
| **Conversation** | `conversations` | Conversation history |
| **Repository** | `repositories` | File repositories |
| **Resource** | `resources` | Repository resources (files) |
| **Folder** | `folders` | Folder structure in repositories |
| **Domain** | `domains` | Web domains for scraping |
| **Url** | `urls` | URLs within domains |
| **Media** | `media` | Media files (images, audio, video) |

**Model pattern**:
```python
class Agent(Base):
    __tablename__ = 'agents'
    
    agent_id = Column(Integer, primary_key=True, autoincrement=True)
    app_id = Column(Integer, ForeignKey('apps.app_id'), nullable=False)
    name = Column(String, nullable=False)
    system_prompt = Column(Text)
    llm_config = Column(JSON)
    
    # Relationships
    app = relationship("App", back_populates="agents")
    conversations = relationship("Conversation", back_populates="agent")
```

All models are imported in `backend/models/__init__.py` to ensure SQLAlchemy relationships are properly resolved.

## Schemas

**20+ Pydantic schema modules** define request/response data structures:

| Schema Module | Purpose |
|---------------|---------|
| **agent_schemas** | Agent CRUD requests/responses |
| **ai_service_schemas** | AI service configuration schemas |
| **api_key_schemas** | API key schemas |
| **app_schemas** | App CRUD schemas |
| **conversation_schemas** | Conversation schemas |
| **domain_schemas** | Domain schemas |
| **embedding_service_schemas** | Embedding service schemas |
| **folder_schemas** | Folder schemas |
| **mcp_config_schemas** | MCP config schemas |
| **mcp_server_schemas** | MCP server schemas |
| **output_parser_schemas** | Output parser schemas |
| **repository_schemas** | Repository schemas |
| **resource_schemas** | Resource schemas |
| **silo_schemas** | Silo schemas |
| **skill_schemas** | Skill schemas (legacy) |
| **url_schemas** | URL schemas |
| **user_schemas** | User schemas |

**Schema pattern** (Pydantic v2):
```python
from pydantic import BaseModel, ConfigDict, Field

class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    system_prompt: str | None = None
    llm_config: dict | None = None

class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    agent_id: int
    app_id: int
    name: str
    system_prompt: str | None
    llm_config: dict | None
```

Schemas provide **validation**, **serialization**, and **API documentation** (via OpenAPI/Swagger).

## Utilities

Supporting utilities for cross-cutting concerns:

| Utility | Purpose |
|---------|---------|
| **auth_config** | Authentication configuration (OIDC vs FAKE mode) |
| **config** | Application configuration loader |
| **database** | Database session management, connection pooling |
| **decorators** | Reusable function decorators |
| **error_handlers** | Centralized error handling |
| **logger** | Structured logging with Winston-style API |
| **provider** | EntraID/OIDC provider initialization |
| **security** | Security utilities (signature verification, hashing) |

## Application Lifecycle

### Startup Sequence

1. **Load configuration** from environment variables
2. **Initialize authentication** (OIDC provider if enabled)
3. **Initialize connection pools** (PostgreSQL, LangGraph checkpointer)
4. **Mount routers** (Internal, Public, MCP)
5. **Configure CORS** middleware
6. **Start ASGI server** (Uvicorn)

### Shutdown Sequence

1. **Close connection pools** (checkpointer, database)
2. **Shutdown OIDC provider** (if enabled)
3. **Clean up resources**

Managed by the `lifespan` context manager in `main.py`.

## Key Design Patterns

### Dependency Injection

FastAPI's dependency injection used for:
- Database sessions (`db: Session = Depends(get_db)`)
- Authentication (`user: User = Depends(get_current_user)`)
- Authorization (`role: AppRole = Depends(require_min_role(AppRole.EDITOR))`)
- Rate limiting (`rate_limit: None = Depends(rate_limit_dependency)`)

### Repository Pattern

Separates data access logic from business logic:
- Services call repositories, never directly query the database
- Repositories encapsulate SQL queries
- Enables easier testing and swapping data sources

### Service Layer Pattern

Business logic isolated from HTTP concerns:
- Routers are thin, delegating to services
- Services orchestrate repositories and external systems
- Enables reuse across different API endpoints (internal/public)

## See Also

- [Architecture Overview](overview.md)
- [Database Schema](database.md)
- [Internal API Reference](../api/internal-api.md)
- [Public API Reference](../api/public-api.md)
- [Agent System](../ai/agent-system.md)
