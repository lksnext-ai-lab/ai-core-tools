# Architecture Overview

> Part of [Mattin AI Documentation](../README.md)

## Overview

Mattin AI is a comprehensive AI toolbox platform built as a **multi-tenant web application** with a clear separation between backend API services and frontend client applications. The system provides LLM integration, RAG capabilities, vector database management, and AI agent execution within a flexible workspace architecture.

### High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend Layer                       │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │  Base Library    │  │  Client Projects │                │
│  │  (React/TypeScript) │  (Custom Themes) │                │
│  └──────────────────┘  └──────────────────┘                │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ HTTP/WebSocket
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                        Backend Layer                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Internal API │  │  Public API  │  │   MCP API    │      │
│  │ (Session)    │  │ (API Keys)   │  │ (Protocol)   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│         │                  │                  │              │
│         └──────────────────┴──────────────────┘              │
│                           │                                  │
│         ┌─────────────────┴─────────────────┐               │
│         │                                    │               │
│    ┌────▼─────┐        ┌────────────┐  ┌───▼──────┐        │
│    │ Services │        │ Repositories │  │ Tools   │        │
│    │ (Logic)  │ ─────▶ │ (Data)      │  │ (AI/LLM)│        │
│    └──────────┘        └────────────┘  └──────────┘        │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      Data Layer                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ PostgreSQL   │  │ PGVector /   │  │ LLM Providers│      │
│  │ (Relational) │  │ Qdrant       │  │ (External)   │      │
│  │              │  │ (Vectors)    │  │              │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

## System Components

### Backend (Python/FastAPI)

The backend is built with **FastAPI** and follows a layered architecture:

- **Router Layer**: Three router groups (Internal, Public, MCP) handling different authentication and use cases
- **Service Layer**: Business logic for agents, silos, files, conversations, and more
- **Repository Layer**: Data access abstraction using SQLAlchemy ORM
- **Models**: SQLAlchemy ORM models representing database entities
- **Tools**: AI/LLM integration utilities (LangChain, vector stores, embeddings)

See [Backend Architecture](backend.md) for detailed information.

### Frontend (React/TypeScript)

The frontend is split into two parts:

- **Base Library** (`@lksnext/ai-core-tools-base`): Core React components, hooks, contexts, and services
- **Client Projects**: Customized applications consuming the base library with custom themes and configurations

This architecture allows for a **single codebase** powering multiple branded client applications.

See [Frontend Architecture](frontend.md) for detailed information.

### Database (PostgreSQL + pgvector)

- **PostgreSQL 16+** with the **pgvector extension** for vector similarity search
- **SQLAlchemy ORM** for model definitions and query abstraction
- **Alembic** for schema migrations and version control
- **Connection pooling** for efficient resource management

See [Database Schema](database.md) for model details.

### Vector Stores

Two supported backends for embedding storage and retrieval:

- **PGVector**: Embeddings stored in PostgreSQL using the pgvector extension
- **Qdrant**: Standalone vector database with high-performance similarity search

Both backends are abstracted through LangChain's vector store interface.

See [RAG & Vector Stores](../ai/rag-vector-stores.md) for more.

### LLM Providers

Multi-provider LLM support via **LangChain**:

- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude)
- MistralAI
- Azure OpenAI
- Google (Gemini)
- Ollama (local models)

See [LLM Integration](../ai/llm-integration.md) for configuration details.

## Data Flow

### Internal API Flow (Frontend ↔ Backend)

```
User → Frontend → /internal/* → Session Auth → Router → Service → Repository → Database
                                                      ↓
                                             LangChain Tools → LLM / Vector Store
```

1. User interacts with frontend application
2. Frontend sends authenticated HTTP request to `/internal/*` endpoint
3. **Session-based authentication** validates the user (OIDC or FAKE mode)
4. Router passes request to appropriate service
5. Service implements business logic, calling repositories for data access
6. Service may invoke LangChain tools for AI operations
7. Response returns through the stack to frontend

### Public API Flow (External Clients ↔ Backend)

```
API Client → /public/v1/* → API Key Auth → Router → Service → Repository → Database
                                                 ↓
                                        LangChain Tools → LLM / Vector Store
```

1. External application sends API request with API key in header
2. **API key authentication** validates the request with rate limiting
3. Router, service, repository flow same as internal API
4. JSON response returned to client

### Agent Execution Flow

```
Request → Agent Service → Agent Executor (LangGraph) → Memory/Checkpointer
                              ↓
                        LLM + Tools + Skills
                              ↓
                    Vector Store Retrieval (optional)
                              ↓
                         Response
```

1. Agent execution request received via internal or public API
2. `AgentExecutionService` loads agent configuration and skills
3. **LangGraph agent executor** invokes LLM with tools and conversation memory
4. Agent may use **RAG** (retrieval from vector stores) for context
5. Agent response streamed back via Server-Sent Events (SSE)

See [Agent System](../ai/agent-system.md) for details.

## Multi-Tenancy Model

Mattin AI uses an **app-centric multi-tenancy model** where workspaces (called "Apps") isolate resources and access:

### App (Workspace)

An **App** is the primary isolation boundary:
- Each user can create multiple apps
- Apps contain agents, silos, repositories, conversations, and other resources
- Apps are **not shared by default** between users

### Role-Based Access Control (RBAC)

**Role hierarchy**: `omniadmin > owner > administrator > editor > viewer > user > guest`

- **Owner**: App creator, full control
- **Administrator**: Can manage app settings and invite users
- **Editor**: Can modify content (agents, conversations, etc.)
- **Viewer**: Read-only access
- **User**: Authenticated user with no specific app access
- **Guest**: Unauthenticated user

See [Role Authorization](../reference/role-authorization.md) for implementation details.

### Collaboration

Users can collaborate on apps via the **AppCollaborator** model:
- App owner can invite users with specific roles
- Collaborators inherit role permissions within the app context
- Collaboration invites can be accepted or declined

## Technology Stack

### Backend
- **Python 3.11+**: Modern async Python features
- **FastAPI**: High-performance async web framework
- **SQLAlchemy 2.x**: ORM with async support
- **Alembic**: Database migration tool
- **LangChain/LangGraph**: LLM orchestration and agent execution
- **Pydantic v2**: Data validation and serialization
- **Uvicorn**: ASGI server

### Frontend
- **React 18**: Functional components with hooks
- **TypeScript**: Type-safe JavaScript
- **Vite**: Fast build tool and dev server
- **Tailwind CSS**: Utility-first styling
- **React Query**: Server state management
- **Context API**: Global state management

### Database & Infrastructure
- **PostgreSQL 16+**: Relational database with pgvector extension
- **PGVector / Qdrant**: Vector database backends
- **Docker & Docker Compose**: Containerization
- **Redis** (optional): Caching and session storage

### Authentication
- **OIDC (OpenID Connect)**: Production authentication via EntraID/Azure AD
- **Session-based auth**: Cookie sessions for internal API
- **API keys**: Token-based auth for public API

## Deployment Architecture

Mattin AI can be deployed in multiple configurations:

- **Docker Compose**: Single-server deployment with all services
- **Kubernetes**: Scalable multi-node deployment
- **Manual**: Separate backend, frontend, and database hosts

See [Deployment Guide](../guides/deployment.md) for instructions.

## See Also

- [Backend Architecture](backend.md)
- [Frontend Architecture](frontend.md)
- [Database Schema](database.md)
- [LLM Integration](../ai/llm-integration.md)
- [RAG & Vector Stores](../ai/rag-vector-stores.md)
- [Agent System](../ai/agent-system.md)
