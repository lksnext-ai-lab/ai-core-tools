---
description: Mattin AI product & domain reference — core concepts, RBAC, all domain entities and relationships, API surface, agent execution flow, memory, client deployment model, and key env vars. Auto-applies on backend/** and frontend/** so the full catalog loads only when implementing, not on every triage/planning/release call.
applyTo: "backend/**,frontend/**,alembic/**,tests/**"
---

# Mattin AI — Domain Model Reference

This describes **what Mattin AI does** from a product/domain perspective. It auto-applies when editing code in `backend/**`, `frontend/**`, `alembic/**`, or `tests/**` — i.e. it loads for every implementer (`@backend-expert`, `@react-expert`, `@alembic-expert`, `@test-expert`). For planning or triage steps that don't touch those paths (e.g. `@feature-planner` writing a spec under `/plans/`), read it explicitly with `#file:.github/instructions/domain-model.instructions.md` when the task involves domain entities.

## Core Concepts

**App (Workspace)**: The central tenant unit. Every resource (agents, silos, repos, services, API keys) is scoped to an App. Each App has an `owner`, a URL-safe `slug`, configurable rate limits, CORS origins, and max file sizes.

**User**: A platform account (email, name). Owns multiple Apps and can collaborate on others. Authenticates via `AICT_LOGIN`: `FAKE` (email-only local dev), `LOCAL` (SaaS email + password with `UserCredential`), or `OIDC` (Azure Entra ID, production).

**Collaborator**: Users invited to an App with a role. Invitation states: `PENDING` → `ACCEPTED` / `DECLINED`.

### Role-Based Access Control

Lowest → highest: **VIEWER** (read-only) → **EDITOR** (create/edit resources) → **ADMINISTRATOR** (full app mgmt except ownership transfer) → **OWNER** (full control incl. collaborators + deletion) → **OMNIADMIN** (cross-app superadmin via `AICT_OMNIADMINS`).

Enforced with `@require_min_role(AppRole.EDITOR)` on routes. All resources filtered by `app_id` for tenant isolation.

## Domain Entities

### AI Entities

| Entity | Purpose |
|--------|---------|
| **Agent** | Core AI agent: system prompt, LLM (AIService), optional RAG (Silo), memory, temperature, output parser, skills, MCP tool configs. Agents with `is_tool=True` are usable as tools by other agents. |
| **OCRAgent** | Agent subclass (STI via `type`). Dual-LLM: vision model for scanned pages + text model for structuring output. |
| **AIService** | LLM provider config (OpenAI, Anthropic, MistralAI, Azure, Google, Custom): type, endpoint, API key. Multiple per App. |
| **EmbeddingService** | Embedding model config for vector stores. Providers: OpenAI, MistralAI, Ollama, Custom/HuggingFace, Azure OpenAI, Google AI Studio, Google Cloud Vertex AI. Selection via `backend/tools/embeddingTools.py`. |
| **Skill** | Reusable markdown prompt block attached to agents (M:N via `agent_skills`). Injected into the system prompt at execution. |
| **OutputParser** | JSON-schema for structured output (`fields` JSON column). Dynamically generates a Pydantic model at runtime. Used by agents and for silo metadata filtering. |
| **Conversation** | Chat session between a user and an agent. Memory in LangGraph's PostgreSQL checkpointer; metadata (title, count, last message) in the Conversation table. |

### RAG / Content Entities

| Entity | Purpose |
|--------|---------|
| **Silo** | Vector store container → collection (`silo_{id}`) in PGVector or Qdrant (per-silo). Linked to an EmbeddingService. Agents connect for RAG retrieval. |
| **Repository** | File-based document store (files in folders). Linked to a Silo — uploaded files are vectorized into that collection. |
| **Resource** | Individual file within a Repository (PDF, text, etc.). |
| **Folder** | Hierarchical, self-referencing folder structure within a Repository. |
| **Media** | Audio/video in a Repository. Direct upload or YouTube URL. Transcribed with configurable chunking, then vectorized. |
| **Domain** | Web scraping source (base URL + CSS selectors). Crawled URLs vectorized into the linked Silo. |
| **DomainUrl / CrawlPolicy / CrawlJob** | Crawl pipeline: discovered URL · per-domain rules · in-flight crawl run. |
| **SharePointSource / SharePointFile** | Microsoft SharePoint connector per Silo and its synced files. |

### MCP Entities (Dual-Role)

Mattin AI is **both** an MCP server and an MCP client:

| Entity | Role | Purpose |
|--------|------|---------|
| **MCPServer** | Server (outbound) | Exposes agents as MCP tools to external clients (Claude Desktop, Cursor). Slug routing, rate limiting, agent-to-tool mappings. |
| **MCPConfig** | Client (inbound) | Connection config for external MCP servers agents consume as tool sources. Linked via `agent_mcps`. |

### Auth Entities

| Entity | Purpose |
|--------|---------|
| **APIKey** | 64-char key for public API + MCP. Scoped to an App, owned by a User. Shown once. |
| **UserCredential** | Hashed email/password for `AICT_LOGIN=LOCAL`. One-to-one with `User`. |

### Marketplace & Billing Entities

| Entity | Purpose |
|--------|---------|
| **AgentMarketplaceProfile** | Public marketplace listing for an Agent. One-to-one. |
| **AgentMarketplaceRating** | User ratings/reviews of published agents. |
| **MarketplaceUsage** | Counter for marketplace invocations. |
| **Subscription** | A User's plan: references `TierConfig`, has `SubscriptionTier`, `BillingStatus`. |
| **TierConfig** | Pricing tier (Free, Pro, Enterprise…) and feature limits/quotas. |
| **UsageRecord** | Per-resource billable usage for quota/billing. |
| **SystemSetting** | Cross-app key/value config (OMNIADMIN-managed). |

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

## API Surface

Three groups with different auth:

| Group | Prefix | Auth | Purpose |
|-------|--------|------|---------|
| **Internal** | `/internal` | Session/JWT (OIDC or dev) | Frontend ↔ Backend. Full CRUD. |
| **Public v1** | `/public/v1` | `X-API-KEY` header | External programmatic access. Chat, file upload, repo/silo ops. |
| **MCP** | `/mcp/v1` | `X-API-KEY` header | JSON-RPC 2.0 for Model Context Protocol. |

**Public API controls:** per-app rate limiting (`App.agent_rate_limit`), CORS origin validation (`App.agent_cors_origins`), file size limits (`App.max_file_size_mb`).

## Key User Workflows

1. **Create App** → configure AI services (LLM + embedding) → create agents → chat via playground or API
2. **Build knowledge base** → silo → repository → upload files → vectorized → link silo to agent → RAG
3. **Web scraping for RAG** → silo → domain (URL + selectors) → scrape → vectorized
4. **Media transcription** → upload audio/video → transcribed → chunked → vectorized
5. **Structured output** → output parser (JSON schema) → attach to agent → structured JSON
6. **Agent composition** → mark agent `is_tool` → link as tool to another agent → delegation
7. **MCP server exposure** → MCPServer → attach agents → external tools connect via slug URL
8. **MCP tool consumption** → MCPConfig with external server → link to agent → agent uses external tools
9. **Collaboration** → owner invites by email with role → invitee accepts → access
10. **API access** → generate API key → `X-API-KEY` for public API or MCP

## Agent Execution Flow

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

## Memory Management

- **Storage**: LangGraph `AsyncPostgresSaver` in PostgreSQL
- **Thread ID**: `thread_{agent_id}_{session_id}`
- **Config per agent**: `has_memory`, `memory_max_messages` (default 20), `memory_max_tokens` (default 4000), `memory_summarize_threshold` (default 10)
- **Strategies**: token counting (tiktoken), message trimming (keeps recent N, preserves system messages), tool message cleanup

## Client Deployment Model

Frontend is a **reusable npm library** (`@lksnext/ai-core-tools-base`):
- Base library provides all pages, components, contexts, auth, themes
- Client projects (`clients/<name>/`) import it and customize via `clientConfig.ts`: theme, branding, auth config, API URL, feature flags, custom routes
- All clients share the same backend

## Notable Features

- **Per-silo vector DB type**: each silo independently uses PGVector or Qdrant
- **Dynamic Pydantic models**: OutputParser JSON schemas become Pydantic models at runtime
- **Multimodal chat**: agents accept images (base64 or signed static URLs)
- **Secure static files**: `/static/{path}` requires a cryptographic signature
- **Cascade deletion**: `AppService.delete_app()` performs ordered deletion across all entity types
- **LangSmith tracing**: per-app via `App.langsmith_api_key` (project = app name), global env-var fallback (`LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY` + `LANGSMITH_PROJECT`). Validated via `POST /internal/apps/{id}/langsmith/test`. Helper: `backend/tools/langsmith_config.py`.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `SQLALCHEMY_DATABASE_URI` | PostgreSQL connection string |
| `AICT_LOGIN` | Auth mode: `FAKE` (dev) \| `LOCAL` (SaaS email+password) \| `OIDC` (production) |
| `AICT_MODE` | Deployment mode: `SELF-HOSTED` \| `SAAS` (feature flags + billing behavior) |
| `AICT_OMNIADMINS` | Comma-separated emails granted OMNIADMIN |
| `SECRET_KEY` | Session encryption key |
| `OPENAI_API_KEY` | LLM provider API key (one per provider used) |
| `VECTOR_DB_TYPE` | Default vector backend: `PGVECTOR` \| `QDRANT` (overridable per-silo) |
| `LANGSMITH_TRACING` / `LANGSMITH_API_KEY` / `LANGSMITH_PROJECT` | Optional global LangSmith fallback when no per-app key is set |

See `CLAUDE.md` for the full environment list.
