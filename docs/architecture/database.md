# Database Schema

> Part of [Mattin AI Documentation](../README.md)

## Overview

Mattin AI uses **PostgreSQL 16+** with the **pgvector extension** for vector similarity search. Database interactions are managed through:

- **SQLAlchemy 2.x ORM**: Model definitions, relationships, queries
- **Alembic**: Schema migrations and version control
- **asyncpg** (via psycopg3): Async PostgreSQL driver (Windows-compatible)
- **Connection pooling**: Efficient connection management for web and agent memory

## Core Models

**22 SQLAlchemy models** represent the database schema. Below are the primary entities:

### User

**Table**: `User`  
**Purpose**: Application users (authenticated via OIDC or FAKE mode)

| Column | Type | Description |
|--------|------|-------------|
| `user_id` | Integer (PK) | Unique user identifier |
| `name` | String(255) | User's display name |
| `email` | String(255) | User's email (unique) |
| `sub` | String(255) | OIDC subject identifier |
| `role` | String(45) | Global role (omniadmin, user, guest) |
| `create_date` | DateTime | Account creation timestamp |
| `is_active` | Boolean | Whether the user account is active (default `true`). Inactive users cannot log in or call the API. |

**Relationships**:
- `owned_apps` → List of apps owned by this user
- `collaborations` → App collaboration invites

### App (Workspace)

**Table**: `App`  
**Purpose**: Multi-tenant workspace (primary isolation boundary)

| Column | Type | Description |
|--------|------|-------------|
| `app_id` | Integer (PK) | Unique app identifier |
| `name` | String(255) | App name |
| `slug` | String(100) | URL-safe identifier (unique) |
| `owner_id` | Integer (FK → User) | App owner |
| `agent_rate_limit` | Integer | Rate limit per agent (requests/minute) |
| `max_file_size_mb` | Integer | Max file upload size (MB) |
| `agent_cors_origins` | String(1000) | Allowed CORS origins |
| `langsmith_api_key` | String(255) | LangSmith API key for tracing |
| `create_date` | DateTime | App creation timestamp |

**Relationships**:
- `owner` → User who created the app
- `collaborators` → AppCollaborator entries (users with access)
- `agents` → List of agents in this app
- `silos` → List of vector stores in this app
- `repositories` → List of file repositories
- `domains` → List of web domains
- `ai_services` → List of LLM configurations
- `embedding_services` → List of embedding configurations
- `mcp_servers` → List of MCP servers
- `api_keys` → List of API keys

### AppCollaborator

**Table**: `app_collaborators`  
**Purpose**: App collaboration (multi-user access with roles)

| Column | Type | Description |
|--------|------|-------------|
| `collaboration_id` | Integer (PK) | Unique collaboration ID |
| `app_id` | Integer (FK → App) | App being shared |
| `user_id` | Integer (FK → User) | Collaborating user |
| `role` | String(45) | User's role in this app (owner, admin, editor, viewer) |
| `status` | String(45) | Invitation status (pending, accepted, declined) |
| `invited_at` | DateTime | Invitation timestamp |

**Relationships**:
- `app` → App being collaborated on
- `user` → Collaborating user

### Agent

**Table**: `Agent`  
**Purpose**: AI agent configuration (LLM-based conversational agents)

| Column | Type | Description |
|--------|------|-------------|
| `agent_id` | Integer (PK) | Unique agent identifier |
| `app_id` | Integer (FK → App) | Owning app |
| `name` | String(255) | Agent name |
| `description` | String(1000) | Agent description |
| `system_prompt` | Text | System prompt for LLM |
| `prompt_template` | Text | User prompt template |
| `type` | String(45) | Agent type (agent, tool) |
| `status` | String(45) | Agent status (active, inactive) |
| `is_tool` | Boolean | Whether agent is a tool |
| `service_id` | Integer (FK → AIService) | LLM service configuration |
| `silo_id` | Integer (FK → Silo) | Default vector store for RAG |
| `request_count` | Integer | Number of requests served |
| `create_date` | DateTime | Agent creation timestamp |

**Relationships**:
- `app` → Owning app
- `service` → AIService (LLM configuration)
- `silo` → Default Silo (vector store for RAG)
- `conversations` → List of conversations
- `skill_associations` → AgentSkill (many-to-many)
- `mcp_associations` → AgentMCP (many-to-many)
- `tool_associations` → AgentTool (many-to-many, self-referential)

### Silo (Vector Store)

**Table**: `Silo`  
**Purpose**: Vector store configuration for RAG (Retrieval-Augmented Generation)

| Column | Type | Description |
|--------|------|-------------|
| `silo_id` | Integer (PK) | Unique silo identifier |
| `app_id` | Integer (FK → App) | Owning app |
| `name` | String(255) | Silo name |
| `description` | Text | Silo description |
| `vector_db_type` | String(45) | Vector DB backend (PGVECTOR, QDRANT) |
| `embedding_service_id` | Integer (FK → EmbeddingService) | Embedding configuration |
| `retrieval_count` | Integer | Number of vectors to retrieve |
| `create_date` | DateTime | Silo creation timestamp |

**Relationships**:
- `app` → Owning app
- `embedding_service` → EmbeddingService configuration
- `repositories` → List of associated repositories

### Repository

**Table**: `Repository`  
**Purpose**: File repository (stores documents for RAG ingestion)

| Column | Type | Description |
|--------|------|-------------|
| `repository_id` | Integer (PK) | Unique repository identifier |
| `app_id` | Integer (FK → App) | Owning app |
| `silo_id` | Integer (FK → Silo) | Associated vector store |
| `name` | String(255) | Repository name |
| `description` | Text | Repository description |
| `status` | String(45) | Status (active, processing, error) |
| `create_date` | DateTime | Repository creation timestamp |

**Relationships**:
- `app` → Owning app
- `silo` → Associated Silo
- `resources` → List of files (Resource entities)
- `folders` → Folder structure

### Domain

**Table**: `Domain`  
**Purpose**: Web domain for scraping (RAG ingestion from websites)

| Column | Type | Description |
|--------|------|-------------|
| `domain_id` | Integer (PK) | Unique domain identifier |
| `app_id` | Integer (FK → App) | Owning app |
| `name` | String(255) | Domain name (e.g., example.com) |
| `base_url` | String(500) | Base URL for scraping |
| `silo_id` | Integer (FK → Silo) | Target vector store |
| `status` | String(45) | Crawl status (active, paused, error) |
| `create_date` | DateTime | Domain creation timestamp |

**Relationships**:
- `app` → Owning app
- `silo` → Target Silo for embeddings
- `urls` → List of URLs within this domain

### URL

**Table**: `Url`  
**Purpose**: Individual URL within a domain

| Column | Type | Description |
|--------|------|-------------|
| `url_id` | Integer (PK) | Unique URL identifier |
| `domain_id` | Integer (FK → Domain) | Owning domain |
| `url` | String(1000) | Full URL |
| `title` | String(500) | Page title |
| `content` | Text | Scraped content |
| `status` | String(45) | Scrape status (pending, scraped, error) |
| `last_scraped` | DateTime | Last scrape timestamp |

**Relationships**:
- `domain` → Owning domain

## AI Service Models

### AIService

**Table**: `AIService`  
**Purpose**: LLM provider configuration (OpenAI, Anthropic, etc.)

| Column | Type | Description |
|--------|------|-------------|
| `service_id` | Integer (PK) | Unique service identifier |
| `app_id` | Integer (FK → App) | Owning app |
| `name` | String(255) | Service name |
| `provider` | String(45) | Provider (openai, anthropic, mistral, azure, google, ollama) |
| `model` | String(255) | Model name (e.g., gpt-4, claude-3-opus) |
| `api_key` | String(500) | Encrypted API key |
| `base_url` | String(500) | API base URL (for custom endpoints) |
| `temperature` | Float | LLM temperature (0.0-1.0) |
| `max_tokens` | Integer | Max output tokens |
| `create_date` | DateTime | Service creation timestamp |

**Relationships**:
- `app` → Owning app
- `agents` → List of agents using this service

### AgentMarketplaceProfile

**Table**: `agent_marketplace_profiles`  
**Purpose**: Marketplace metadata for published agents (1:1 with Agent)

| Column | Type | Description |
|--------|------|-------------|
| `profile_id` | Integer (PK) | Unique profile identifier |
| `agent_id` | Integer (FK → Agent, unique) | Associated agent |
| `display_name` | String(255) | Public-facing name |
| `short_description` | String(160) | Brief summary for catalog |
| `long_description` | Text | Full markdown description |
| `category` | String(50) | Category key (enum) |
| `tags` | JSON | List of tags (max 5) |
| `icon_url` | String(500) | Icon image URL |
| `cover_image_url` | String(500) | Cover banner URL |
| `visibility` | String(20) | Marketplace visibility (enum) |
| `create_date` | DateTime | Profile creation timestamp |
| `update_date` | DateTime | Last update timestamp |

**Relationships**:
- `agent` → Associated agent (1:1)

**Visibility values**: `unpublished`, `private`, `public`

**Category values**: `customer_support`, `education`, `research_analysis`, `content_creation`, `development_tools`, `business_finance`, `health_wellness`, `other`

### AgentMarketplaceRating

**Table**: `AgentMarketplaceRating`  
**Purpose**: One star rating (1–5) per user per marketplace agent profile. Users may only rate agents they have had at least one marketplace conversation with.

| Column | Type | Description |
|--------|------|--------------|
| `id` | Integer (PK) | Unique rating identifier |
| `profile_id` | Integer (FK → AgentMarketplaceProfile, CASCADE) | Rated agent profile |
| `user_id` | Integer (FK → User, CASCADE) | User who submitted the rating |
| `rating` | Integer | Star rating value (1–5) |
| `created_at` | DateTime | When the rating was first submitted |
| `updated_at` | DateTime | When the rating was last updated |

**Unique constraint**: `(profile_id, user_id)` — one rating per user per agent.

**Relationships**:
- `profile` → `AgentMarketplaceProfile` (the rated agent)
- `user` → `User` who made the rating

**Notes**: Submitting a second rating for the same agent updates the existing record rather than creating a new one. The profile's `rating_avg` and `rating_count` are recalculated atomically on each upsert.

### EmbeddingService

**Table**: `EmbeddingService`  
**Purpose**: Embedding model configuration (for vector generation)

| Column | Type | Description |
|--------|------|-------------|
| `service_id` | Integer (PK) | Unique service identifier |
| `app_id` | Integer (FK → App) | Owning app |
| `name` | String(255) | Service name |
| `provider` | String(45) | Provider (openai, huggingface, ollama) |
| `model` | String(255) | Model name (e.g., text-embedding-3-small) |
| `api_key` | String(500) | Encrypted API key |
| `dimensions` | Integer | Embedding dimensions |
| `create_date` | DateTime | Service creation timestamp |

**Relationships**:
- `app` → Owning app
- `silos` → List of silos using this service

### BaseService

**Table**: `BaseService`  
**Purpose**: Base class for service models (abstract, not instantiated directly)

Provides common fields and methods for AIService and EmbeddingService.

## Configuration Models

### MCPConfig

**Table**: `MCPConfig`  
**Purpose**: Model Context Protocol configuration

| Column | Type | Description |
|--------|------|-------------|
| `config_id` | Integer (PK) | Unique config identifier |
| `app_id` | Integer (FK → App) | Owning app |
| `name` | String(255) | Config name |
| `protocol_version` | String(45) | MCP protocol version |
| `config_data` | JSON | Configuration JSON |
| `create_date` | DateTime | Config creation timestamp |

**Relationships**:
- `app` → Owning app

### MCPServer

**Table**: `mcp_servers`  
**Purpose**: MCP server instance

| Column | Type | Description |
|--------|------|-------------|
| `server_id` | Integer (PK) | Unique server identifier |
| `app_id` | Integer (FK → App) | Owning app |
| `name` | String(255) | Server name |
| `command` | String(500) | Server command |
| `args` | JSON | Command arguments |
| `env` | JSON | Environment variables |
| `status` | String(45) | Server status (running, stopped) |

**Relationships**:
- `app` → Owning app
- `agents` → AgentMCPServer (many-to-many)

### OutputParser

**Table**: `OutputParser`  
**Purpose**: Structured output parser configuration (Pydantic models for LLM output)

| Column | Type | Description |
|--------|------|-------------|
| `parser_id` | Integer (PK) | Unique parser identifier |
| `app_id` | Integer (FK → App) | Owning app |
| `name` | String(255) | Parser name |
| `schema` | JSON | Pydantic schema JSON |
| `create_date` | DateTime | Parser creation timestamp |

**Relationships**:
- `app` → Owning app

### Skill

**Table**: `Skill`  
**Purpose**: Agent skills (legacy system, being phased out)

| Column | Type | Description |
|--------|------|-------------|
| `skill_id` | Integer (PK) | Unique skill identifier |
| `app_id` | Integer (FK → App) | Owning app |
| `name` | String(255) | Skill name |
| `description` | Text | Skill description |
| `code` | Text | Skill code/definition |

**Relationships**:
- `app` → Owning app
- `agents` → AgentSkill (many-to-many)

### Folder

**Table**: `Folder`  
**Purpose**: Folder structure within repositories

| Column | Type | Description |
|--------|------|-------------|
| `folder_id` | Integer (PK) | Unique folder identifier |
| `repository_id` | Integer (FK → Repository) | Owning repository |
| `parent_id` | Integer (FK → Folder) | Parent folder (self-referential) |
| `name` | String(255) | Folder name |
| `path` | String(500) | Full folder path |

**Relationships**:
- `repository` → Owning repository
- `parent` → Parent folder
- `children` → Child folders
- `resources` → Files in this folder

### SystemSetting

**Table**: `system_settings`  
**Purpose**: Platform-wide configuration settings managed by OMNIADMIN users. Values are resolved in order: **environment variable → database override → default** (from `system_defaults.yaml`).

| Column | Type | Description |
|--------|------|--------------|
| `key` | String(100) (PK) | Unique setting identifier |
| `value` | Text (nullable) | Database override value (null = use default) |
| `type` | String(20) | Value type: `string`, `integer`, `boolean`, `float`, `json`, `string_list` |
| `category` | String(50) | UI grouping category (e.g., `marketplace`, `general`, `limits`) |
| `description` | String(500) | Human-readable description of the setting |
| `updated_at` | DateTime | When the value was last changed |

**Notes**:
- Environment variable names follow the pattern `AICT_SETTING_<KEY_UPPERCASE>` (e.g., `AICT_SETTING_MARKETPLACE_CALL_QUOTA`).
- The defaults file `backend/system_defaults.yaml` defines all valid keys, their types, categories, and fallback values.
- Settings are managed via the Admin API (`GET/PUT/DELETE /internal/admin/settings/{key}`).

**Built-in settings**:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `marketplace_call_quota` | integer | `0` | Max marketplace API calls per user per month. `0` = unlimited. |

## Content Models

### Conversation

**Table**: `Conversation`  
**Purpose**: Conversation history (agent chat sessions)

| Column | Type | Description |
|--------|------|-------------|
| `conversation_id` | Integer (PK) | Unique conversation identifier |
| `agent_id` | Integer (FK → Agent) | Agent used in this conversation |
| `user_id` | Integer (FK → User) | User who started the conversation |
| `title` | String(255) | Conversation title |
| `messages` | JSON | Message history (serialized) |
| `source` | String(20) | Conversation source (enum) |
| `create_date` | DateTime | Conversation start timestamp |
| `last_message_date` | DateTime | Last message timestamp |

**Relationships**:
- `agent` → Agent used
- `user` → User who owns the conversation

**Source values**: `playground`, `marketplace`, `api`

### Media

**Table**: `media`  
**Purpose**: Media files (images, audio, video)

| Column | Type | Description |
|--------|------|-------------|
| `media_id` | Integer (PK) | Unique media identifier |
| `filename` | String(255) | Original file name |
| `storage_path` | String(500) | File storage path |
| `mime_type` | String(100) | MIME type |
| `file_size` | Integer | File size in bytes |
| `create_date` | DateTime | Upload timestamp |

### Resource

**Table**: `Resource`  
**Purpose**: Individual file within a repository

| Column | Type | Description |
|--------|------|-------------|
| `resource_id` | Integer (PK) | Unique resource identifier |
| `repository_id` | Integer (FK → Repository) | Owning repository |
| `folder_id` | Integer (FK → Folder) | Parent folder |
| `name` | String(255) | File name |
| `filename` | String(255) | Original file name |
| `storage_path` | String(500) | File storage path |
| `file_type` | String(45) | MIME type |
| `file_size` | Integer | File size in bytes |
| `status` | String(45) | Processing status (pending, processed, error) |
| `create_date` | DateTime | Upload timestamp |

**Relationships**:
- `repository` → Owning repository
- `folder` → Parent folder

### APIKey

**Table**: `api_keys`  
**Purpose**: API keys for public API access

| Column | Type | Description |
|--------|------|-------------|
| `key_id` | Integer (PK) | Unique key identifier |
| `app_id` | Integer (FK → App) | Owning app |
| `name` | String(255) | Key name/description |
| `key_hash` | String(255) | Hashed API key |
| `rate_limit` | Integer | Rate limit (requests/minute) |
| `status` | String(45) | Key status (active, revoked) |
| `create_date` | DateTime | Key creation timestamp |

**Relationships**:
- `app` → Owning app

### OCRAgent

**Table**: `ocr_agents`  
**Purpose**: OCR-specific agent configuration

| Column | Type | Description |
|--------|------|-------------|
| `ocr_agent_id` | Integer (PK) | Unique OCR agent identifier |
| `app_id` | Integer (FK → App) | Owning app |
| `name` | String(255) | OCR agent name |
| `config` | JSON | OCR configuration |

**Relationships**:
- `app` → Owning app

### MarketplaceUsage

**Table**: `marketplace_usage`  
**Purpose**: Tracks per-user monthly API call counts to marketplace agents

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | Unique record identifier |
| `user_id` | Integer (FK → User) | User whose usage is tracked |
| `year` | Integer | Calendar year of the usage period |
| `month` | Integer | Calendar month (1–12) of the usage period |
| `call_count` | Integer | Number of marketplace agent calls in this period |

**Unique constraint**: `(user_id, year, month)` — one record per user per month.

**Relationships**:
- `user` → User whose calls are counted (cascade delete)

**Notes**:
- Records for past months are retained for auditing; they are never automatically deleted.
- Quota enforcement reads `marketplace_call_quota` from the `system_settings` table. A value of `0` means unlimited.
- OMNIADMIN users are always exempt from quota limits regardless of this table.

## Migrations

All schema changes are managed via **Alembic**:

- **48+ migration files** in `alembic/versions/`
- **Model registry**: `backend/models/__init__.py` (all models imported)
- **Migration workflow**: See [Developer Guide](../dev-guide.md)

**Naming conventions**:
- **Entity tables**: PascalCase (`Agent`, `Silo`, `User`)
- **Junction tables**: snake_case (`agent_skills`, `agent_mcps`, `agent_tools`)
- **Primary keys**: `<table_name_lower>_id` (e.g., `agent_id`, `silo_id`)

**Common migration commands**:

```bash
# Create migration
alembic revision --autogenerate -m "Add field_name to model_name"

# Apply migration
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

**Best practices**:
- Every migration must have both `upgrade()` and `downgrade()`
- Test rollback before committing
- Descriptive revision messages
- Never modify already-applied migrations

## Enums

Mattin AI uses string-based enum values stored in database columns. These are validated at the application level.

### MarketplaceVisibility

**Column**: `agent_marketplace_profiles.visibility`  
**Purpose**: Controls agent visibility in marketplace

| Value | Description |
|-------|-------------|
| `unpublished` | Not listed in marketplace (default) |
| `private` | Listed but only accessible via direct link |
| `public` | Publicly listed and discoverable |

### ConversationSource

**Column**: `Conversation.source`  
**Purpose**: Tracks where conversation originated

| Value | Description |
|-------|-------------|
| `playground` | Agent playground (app management UI) |
| `marketplace` | Marketplace consumer chat |
| `api` | Public API or MCP endpoint |

### CollaborationRole

**Column**: `app_collaborators.role`  
**Purpose**: Defines user permissions within an app

**Role hierarchy**: `omniadmin > owner > administrator > editor > viewer > user > guest`

| Value | Description |
|-------|-------------|
| `omniadmin` | Superuser with cross-app access (set via env var) |
| `owner` | App creator, full control |
| `administrator` | Can manage app settings and collaborators |
| `editor` | Can create/edit agents, resources, services |
| `viewer` | Read-only access to app resources |
| `user` | Authenticated user, marketplace access only |
| `guest` | Unauthenticated user (future use) |

**Note**: The `USER` role was added for marketplace consumers who need authenticated access without app permissions.

## Connection Pooling

SQLAlchemy connection pool configuration (`db/database.py`):

- **Pool size**: 20 connections
- **Max overflow**: 10 additional connections
- **Recycle time**: 1 hour (connections recycled after 3600 seconds)

Two connection pools are used:

1. **SQLAlchemy pool** (web requests): Standard web request handling
2. **Checkpointer pool** (LangGraph agent memory): Configured in `services/agent_cache_service.py`

Both pools are initialized on app startup and closed on shutdown.

## See Also

- [Backend Architecture](backend.md)
- [RAG & Vector Stores](../ai/rag-vector-stores.md)
- [Developer Guide](../dev-guide.md) (Alembic workflow)
- [Architecture Overview](overview.md)
