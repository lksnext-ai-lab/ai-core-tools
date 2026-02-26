# Internal API

> Part of [Mattin AI Documentation](../README.md)

## Overview

The **Internal API** (`/internal/*`) provides endpoints for **frontend-to-backend communication** in the Mattin AI web application. All endpoints use **session-based authentication** (OIDC or FAKE mode) and enforce **role-based access control** (RBAC).

**Base URL**: `http://localhost:8000/internal` (dev) or `https://your-domain.com/internal` (production)

**Authentication**: Session cookie (set after OIDC login or FAKE mode auto-login)

**OpenAPI Docs**: `http://localhost:8000/docs/internal`

## Authentication

### Session-Based Auth

After successful OIDC login (or FAKE mode auto-login), a session cookie is set. All Internal API requests must include this cookie.

**OIDC Flow**:

```
1. User clicks "Login" → Redirect to /internal/auth/login
2. Backend redirects to EntraID/Azure AD
3. User authenticates with provider
4. Provider redirects to /internal/auth/callback with auth code
5. Backend exchanges code for tokens
6. Session cookie set → User redirected to app
```

**FAKE Mode** (development):

```
User opens app → Auto-logged in as mock user → Session cookie set
```

### get_current_user Dependency

All internal endpoints use the `get_current_user_oauth` dependency:

```python
from routers.internal.auth_utils import get_current_user_oauth

@router.get("/")
async def list_agents(
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    user_id = auth_context.user_id
    # ...
```

**Returns**: `AuthContext` with user info (`user_id`, `email`, `name`, `role`)

### Role-Based Access Control

Endpoints enforce minimum role requirements via `require_min_role`:

```python
from routers.controls.role_authorization import require_min_role, AppRole

@router.post("/")
async def create_agent(
    role: AppRole = Depends(require_min_role("editor")),
    db: Session = Depends(get_db)
):
    # Only users with 'editor' role or higher can access
    ...
```

**Role hierarchy**: `omniadmin > owner > administrator > editor > viewer > user > guest`

## Endpoints

### Apps & Workspaces

**Base**: `/internal/apps`

| Method | Endpoint | Purpose | Min Role |
|--------|----------|---------|----------|
| GET | `/` | List user's apps | user |
| POST | `/` | Create new app | user |
| GET | `/{app_id}` | Get app details | viewer |
| PUT | `/{app_id}` | Update app | owner |
| DELETE | `/{app_id}` | Delete app | owner |
| GET | `/{app_id}/usage` | Get app usage stats | viewer |

**Example: List Apps**

```http
GET /internal/apps
Cookie: session=...

Response:
[
  {
    "app_id": 1,
    "name": "My Workspace",
    "slug": "my-workspace",
    "owner_id": 123,
    "create_date": "2024-01-15T10:30:00Z"
  }
]
```

### Collaboration

**Base**: `/internal/collaboration`

| Method | Endpoint | Purpose | Min Role |
|--------|----------|---------|----------|
| GET | `/apps/{app_id}/collaborators` | List collaborators | viewer |
| POST | `/apps/{app_id}/invite` | Invite user to app | administrator |
| PUT | `/collaboration/{collab_id}/accept` | Accept invitation | (invited user) |
| DELETE | `/collaboration/{collab_id}` | Remove collaborator | administrator |

### Agents

**Base**: `/internal/agents`

| Method | Endpoint | Purpose | Min Role |
|--------|----------|---------|----------|
| GET | `/` | List agents in app | viewer |
| POST | `/` | Create new agent | editor |
| GET | `/{agent_id}` | Get agent details | viewer |
| PUT | `/{agent_id}` | Update agent | editor |
| DELETE | `/{agent_id}` | Delete agent | editor |
| POST | `/{agent_id}/chat` | Execute agent chat | viewer |
| POST | `/{agent_id}/reset` | Reset conversation | viewer |

**Example: Create Agent**

```http
POST /internal/agents?app_id=1
Cookie: session=...
Content-Type: application/json

{
  "name": "Customer Support Bot",
  "description": "Answers customer questions",
  "system_prompt": "You are a helpful assistant.",
  "service_id": 1,
  "silo_id": 2,
  "temperature": 0.7
}

Response:
{
  "agent_id": 10,
  "name": "Customer Support Bot",
  "app_id": 1,
  ...
}
```

**Example: Chat with Agent**

```http
POST /internal/agents/10/chat?app_id=1
Cookie: session=...
Content-Type: multipart/form-data

message=How do I reset my password?
files=@screenshot.png

Response: (Server-Sent Events stream)
data: {"type":"token","content":"To"}
data: {"type":"token","content":" reset"}
data: {"type":"token","content":" your"}
...
data: {"type":"done"}
```

### Silos & Vector Stores

**Base**: `/internal/silos`

| Method | Endpoint | Purpose | Min Role |
|--------|----------|---------|----------|
| GET | `/` | List silos in app | viewer |
| POST | `/` | Create new silo | editor |
| GET | `/{silo_id}` | Get silo details | viewer |
| PUT | `/{silo_id}` | Update silo | editor |
| DELETE | `/{silo_id}` | Delete silo | editor |

**Example: Create Silo**

```http
POST /internal/silos?app_id=1
Cookie: session=...
Content-Type: application/json

{
  "name": "Knowledge Base",
  "description": "Company documentation",
  "vector_db_type": "PGVECTOR",
  "embedding_service_id": 1,
  "retrieval_count": 5
}
```

### Repositories

**Base**: `/internal/repositories`

| Method | Endpoint | Purpose | Min Role |
|--------|----------|---------|----------|
| GET | `/` | List repositories in app | viewer |
| POST | `/` | Create new repository | editor |
| GET | `/{repo_id}` | Get repository details | viewer |
| PUT | `/{repo_id}` | Update repository | editor |
| DELETE | `/{repo_id}` | Delete repository | editor |
| POST | `/{repo_id}/files` | Upload file to repository | editor |
| DELETE | `/{repo_id}/files/{file_id}` | Delete file | editor |

**Example: Upload File**

```http
POST /internal/repositories/5/files?app_id=1
Cookie: session=...
Content-Type: multipart/form-data

file=@document.pdf
folder_id=null

Response:
{
  "resource_id": 42,
  "filename": "document.pdf",
  "file_size": 1024000,
  "status": "processing"
}
```

### Domains

**Base**: `/internal/domains`

| Method | Endpoint | Purpose | Min Role |
|--------|----------|---------|----------|
| GET | `/` | List domains in app | viewer |
| POST | `/` | Create new domain | editor |
| GET | `/{domain_id}` | Get domain details | viewer |
| PUT | `/{domain_id}` | Update domain | editor |
| DELETE | `/{domain_id}` | Delete domain | editor |
| POST | `/{domain_id}/crawl` | Start crawling domain | editor |

### AI Services

**Base**: `/internal/ai_services`

| Method | Endpoint | Purpose | Min Role |
|--------|----------|---------|----------|
| GET | `/` | List AI services in app | viewer |
| POST | `/` | Create new AI service | editor |
| GET | `/{service_id}` | Get AI service details | viewer |
| PUT | `/{service_id}` | Update AI service | editor |
| DELETE | `/{service_id}` | Delete AI service | editor |

**Example: Create AI Service**

```http
POST /internal/ai_services?app_id=1
Cookie: session=...
Content-Type: application/json

{
  "name": "GPT-4 Service",
  "provider": "openai",
  "model": "gpt-4-turbo",
  "api_key": "sk-...",
  "temperature": 0.7,
  "max_tokens": 4096
}
```

### Embedding Services

**Base**: `/internal/embedding_services`

| Method | Endpoint | Purpose | Min Role |
|--------|----------|---------|----------|
| GET | `/` | List embedding services | viewer |
| POST | `/` | Create new embedding service | editor |
| GET | `/{service_id}` | Get embedding service details | viewer |
| PUT | `/{service_id}` | Update embedding service | editor |
| DELETE | `/{service_id}` | Delete embedding service | editor |

### Conversations

**Base**: `/internal/conversations`

| Method | Endpoint | Purpose | Min Role |
|--------|----------|---------|----------|
| GET | `/` | List user's conversations | viewer |
| GET | `/{conversation_id}` | Get conversation history | viewer |
| DELETE | `/{conversation_id}` | Delete conversation | viewer |

### MCP Configs

**Base**: `/internal/mcp_configs`

| Method | Endpoint | Purpose | Min Role |
|--------|----------|---------|----------|
| GET | `/` | List MCP configs in app | viewer |
| POST | `/` | Create new MCP config | editor |
| GET | `/{config_id}` | Get MCP config details | viewer |
| PUT | `/{config_id}` | Update MCP config | editor |
| DELETE | `/{config_id}` | Delete MCP config | editor |

### MCP Servers

**Base**: `/internal/mcp_servers`

| Method | Endpoint | Purpose | Min Role |
|--------|----------|---------|----------|
| GET | `/` | List MCP servers in app | viewer |
| POST | `/` | Create new MCP server | editor |
| GET | `/{server_id}` | Get MCP server details | viewer |
| PUT | `/{server_id}` | Update MCP server | editor |
| DELETE | `/{server_id}` | Delete MCP server | editor |
| POST | `/{server_id}/start` | Start MCP server | editor |
| POST | `/{server_id}/stop` | Stop MCP server | editor |

### Skills

**Base**: `/internal/skills`

| Method | Endpoint | Purpose | Min Role |
|--------|----------|---------|----------|
| GET | `/` | List skills in app | viewer |
| POST | `/` | Create new skill | editor |
| GET | `/{skill_id}` | Get skill details | viewer |
| PUT | `/{skill_id}` | Update skill | editor |
| DELETE | `/{skill_id}` | Delete skill | editor |

**Note**: Skills are legacy and being phased out.

### Output Parsers

**Base**: `/internal/output_parsers`

| Method | Endpoint | Purpose | Min Role |
|--------|----------|---------|----------|
| GET | `/` | List output parsers in app | viewer |
| POST | `/` | Create new output parser | editor |
| GET | `/{parser_id}` | Get output parser details | viewer |
| PUT | `/{parser_id}` | Update output parser | editor |
| DELETE | `/{parser_id}` | Delete output parser | editor |

### Admin

**Base**: `/internal/admin`

| Method | Endpoint | Purpose | Min Role |
|--------|----------|---------|----------|
| GET | `/users` | List all users | omniadmin |
| GET | `/users/{user_id}` | Get user details | omniadmin |
| PUT | `/users/{user_id}` | Update user | omniadmin |
| DELETE | `/users/{user_id}` | Delete user | omniadmin |

### OCR

**Base**: `/internal/ocr`

| Method | Endpoint | Purpose | Min Role |
|--------|----------|---------|----------|
| POST | `/extract` | Extract text from image | viewer |

### Folders

**Base**: `/internal/folders`

| Method | Endpoint | Purpose | Min Role |
|--------|----------|---------|----------|
| GET | `/` | List folders in repository | viewer |
| POST | `/` | Create new folder | editor |
| DELETE | `/{folder_id}` | Delete folder | editor |

### API Keys

**Base**: `/internal/api_keys`

| Method | Endpoint | Purpose | Min Role |
|--------|----------|---------|----------|
| GET | `/` | List API keys for app | viewer |
| POST | `/` | Create new API key | owner |
| DELETE | `/{key_id}` | Revoke API key | owner |

**Example: Create API Key**

```http
POST /internal/api_keys?app_id=1
Cookie: session=...
Content-Type: application/json

{
  "name": "Production API Key",
  "rate_limit": 100
}

Response:
{
  "key_id": 5,
  "key": "mattin_...",  // Only shown once!
  "name": "Production API Key",
  "rate_limit": 100
}
```

### User Profile

**Base**: `/internal/user`

| Method | Endpoint | Purpose | Min Role |
|--------|----------|---------|----------|
| GET | `/profile` | Get current user profile | user |
| PUT | `/profile` | Update user profile | user |

### Version

**Base**: `/internal/version`

| Method | Endpoint | Purpose | Min Role |
|--------|----------|---------|----------|
| GET | `/` | Get backend version info | (no auth) |

**Example Response**:

```json
{
  "version": "0.2.37",
  "environment": "development",
  "python_version": "3.11.5"
}
```

## Error Responses

**Standard error format**:

```json
{
  "detail": "Error message"
}
```

**HTTP Status Codes**:

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request (validation error) |
| 401 | Unauthorized (not authenticated) |
| 403 | Forbidden (insufficient permissions) |
| 404 | Not Found |
| 409 | Conflict (duplicate resource) |
| 500 | Internal Server Error |

## Pagination

Some list endpoints support pagination:

**Query parameters**:
- `page`: Page number (default: 1)
- `per_page`: Items per page (default: 30, max: 100)

**Response includes**:
```json
{
  "items": [...],
  "total": 150,
  "page": 1,
  "per_page": 30,
  "pages": 5
}
```

## See Also

- [Public API](public-api.md) — External API for programmatic access
- [Backend Architecture](../architecture/backend.md) — Router implementation details
- [Authentication Guide](../guides/authentication.md) — OIDC setup
- [Role Authorization](../reference/role-authorization.md) — RBAC details
