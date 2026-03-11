# Environment Variables

> Part of [Mattin AI Documentation](../README.md)

## Overview

Mattin AI is configured via **environment variables** stored in `.env` files. Different `.env` files are used for development, Docker, and production deployments.

**Configuration files**:
- **Backend**: `.env` (root directory or `backend/.env`)
- **Frontend**: `frontend/.env`
- **Docker**: `.env.docker` (for docker-compose)

## Backend Variables

### Database

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SQLALCHEMY_DATABASE_URI` | Yes | — | Full PostgreSQL connection string |
| `DATABASE_HOST` | No | `localhost` | PostgreSQL host |
| `DATABASE_PORT` | No | `5432` | PostgreSQL port |
| `DATABASE_USER` | No | `mattin` | Database user |
| `DATABASE_PASSWORD` | Yes | — | Database password |
| `DATABASE_NAME` | No | `mattin_ai` | Database name |

**Example**:
```bash
SQLALCHEMY_DATABASE_URI=postgresql://mattin:password@localhost:5432/mattin_ai
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_USER=mattin
DATABASE_PASSWORD=secure_password_here
DATABASE_NAME=mattin_ai
```

**Docker**:
```bash
SQLALCHEMY_DATABASE_URI=postgresql://mattin:password@postgres:5432/mattin_ai
DATABASE_HOST=postgres  # Service name in docker-compose
```

### Authentication

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AICT_LOGIN` | No | `OIDC` | Authentication mode: `OIDC` or `FAKE` |
| `SECRET_KEY` | Yes | — | Session encryption key (256-bit) |
| `AICT_OMNIADMINS` | No | — | Comma-separated emails of superusers |
| `JWT_ALGORITHM` | No | `HS256` | JWT signing algorithm |
| `JWT_EXPIRATION_HOURS` | No | `24` | JWT token expiration (hours) |

**Example**:
```bash
AICT_LOGIN=OIDC
SECRET_KEY=your-256-bit-secret-key-here-change-in-production
AICT_OMNIADMINS=admin@example.com,superuser@example.com
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24
```

**Development** (FAKE mode):
```bash
AICT_LOGIN=FAKE
SECRET_KEY=dev-secret-key
```

### LLM API Keys

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | No | — | OpenAI API key (sk-...) |
| `ANTHROPIC_API_KEY` | No | — | Anthropic API key |
| `MISTRAL_API_KEY` | No | — | MistralAI API key |
| `AZURE_OPENAI_API_KEY` | No | — | Azure OpenAI API key |
| `AZURE_OPENAI_ENDPOINT` | No | — | Azure OpenAI endpoint URL |
| `GOOGLE_API_KEY` | No | — | Google Gemini API key |

**Example**:
```bash
OPENAI_API_KEY=sk-proj-...
ANTHROPIC_API_KEY=sk-ant-...
MISTRAL_API_KEY=...
```

**Note**: API keys are optional. Configure only the providers you plan to use.

### Vector Database

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VECTOR_DB_TYPE` | No | `PGVECTOR` | Vector DB backend: `PGVECTOR` or `QDRANT` |
| `QDRANT_URL` | No | — | Qdrant server URL (if using Qdrant) |
| `QDRANT_API_KEY` | No | — | Qdrant API key (for Qdrant Cloud) |

**Example (PGVector)**:
```bash
VECTOR_DB_TYPE=PGVECTOR
# No additional config needed (uses PostgreSQL)
```

**Example (Qdrant)**:
```bash
VECTOR_DB_TYPE=QDRANT
QDRANT_URL=http://localhost:6333
# QDRANT_API_KEY=...  # For Qdrant Cloud
```

### Entra ID (OIDC)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OAUTH_PROVIDER` | No | `ENTRAID` | Provider: `ENTRAID` or `GOOGLE` |
| `ENTRA_TENANT_ID` | OIDC | — | Azure tenant ID |
| `ENTRA_CLIENT_ID` | OIDC | — | Azure application (client) ID |
| `ENTRA_CLIENT_SECRET` | OIDC | — | Azure client secret |
| `ENTRA_REDIRECT_URI` | No | `/auth/callback` | OAuth redirect URI |

**Example**:
```bash
AICT_LOGIN=OIDC
OAUTH_PROVIDER=ENTRAID
ENTRA_TENANT_ID=your-tenant-id
ENTRA_CLIENT_ID=your-client-id
ENTRA_CLIENT_SECRET=your-client-secret
ENTRA_REDIRECT_URI=http://localhost:8000/auth/callback
```

**Google OAuth** (alternative):
```bash
OAUTH_PROVIDER=GOOGLE
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback
```

### LangSmith

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LANGCHAIN_TRACING_V2` | No | `false` | Enable LangSmith tracing |
| `LANGCHAIN_API_KEY` | No | — | LangSmith API key |
| `LANGCHAIN_PROJECT` | No | — | LangSmith project name |

**Example**:
```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_...
LANGCHAIN_PROJECT=mattin-ai-production
```

### Application Settings

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FRONTEND_URL` | No | `http://localhost:5173` | Frontend URL (for CORS, redirects) |
| `AICT_MODE` | No | `SELF-HOSTED` | Deployment mode |
| `REPO_BASE_FOLDER` | No | `./data/repositories` | File repository storage path |
| `TMP_BASE_FOLDER` | No | `./data/tmp` | Temporary files path |

**Example**:
```bash
FRONTEND_URL=http://localhost:3000
AICT_MODE=SELF-HOSTED
REPO_BASE_FOLDER=./data/repositories
TMP_BASE_FOLDER=./data/tmp
```

### CORS Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CORS_ORIGIN_DEV_SERVER` | No | `http://localhost:5173` | React dev server origin |
| `CORS_ORIGIN_DEV_SERVER_ALT` | No | `http://127.0.0.1:5173` | Alternative localhost |
| `CORS_ORIGIN_DOCKER` | No | `http://localhost:3000` | Docker frontend origin |

### MCP

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MCP_SERVERS_PATH` | No | — | Path to local MCP servers |
| `MCP_DEBUG` | No | `false` | Enable MCP debugging |

**Example**:
```bash
MCP_SERVERS_PATH=/path/to/mcp-servers
MCP_DEBUG=true
```

## Frontend Variables

All frontend variables use the `VITE_` prefix (Vite convention).

### API Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VITE_API_BASE_URL` | No | `http://localhost:8000` | Backend API base URL |
| `VITE_INTERNAL_API_URL` | No | `/internal` | Internal API path |
| `VITE_PUBLIC_API_URL` | No | `/public/v1` | Public API path |

**Example**:
```bash
VITE_API_BASE_URL=http://localhost:8000
VITE_INTERNAL_API_URL=/internal
VITE_PUBLIC_API_URL=/public/v1
```

**Production**:
```bash
VITE_API_BASE_URL=https://api.your-domain.com
```

### OIDC Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VITE_OIDC_ENABLED` | No | `false` | Enable OIDC authentication |
| `VITE_OIDC_AUTHORITY` | OIDC | — | OIDC authority URL |
| `VITE_OIDC_CLIENT_ID` | OIDC | — | OIDC client ID |
| `VITE_OIDC_REDIRECT_URI` | No | `/auth/success` | OIDC redirect URI |
| `VITE_OIDC_SCOPE` | No | `openid profile email` | OIDC scopes |
| `VITE_OIDC_AUDIENCE` | No | — | OIDC audience (optional) |

**Example (Azure Entra ID)**:
```bash
VITE_OIDC_ENABLED=true
VITE_OIDC_AUTHORITY=https://login.microsoftonline.com/{tenant-id}/v2.0
VITE_OIDC_CLIENT_ID=your-azure-client-id
VITE_OIDC_REDIRECT_URI=http://localhost:5173/auth/success
VITE_OIDC_SCOPE=openid profile email
```

**Development** (FAKE mode):
```bash
VITE_OIDC_ENABLED=false
```

### Client Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VITE_CLIENT_ID` | No | — | Client identifier |
| `VITE_CLIENT_NAME` | No | `Mattin AI` | Client display name |

**Example**:
```bash
VITE_CLIENT_ID=acme-corp
VITE_CLIENT_NAME=ACME Corp AI Platform
```

## Docker Variables

Variables specific to `docker-compose.yaml`:

### Port Mappings

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BACKEND_PORT` | No | `8000` | Backend host port |
| `FRONTEND_PORT` | No | `3000` | Frontend host port |
| `DATABASE_PORT` | No | `5432` | PostgreSQL host port |

**Example** (`.env.docker`):
```bash
BACKEND_PORT=8000
FRONTEND_PORT=3000
DATABASE_PORT=5432
```

### Volume Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATA_DIR` | No | `./data` | Host data directory |
| `POSTGRES_DATA_DIR` | No | `./data/postgres` | PostgreSQL data directory |

## Environment File Examples

### Development (.env)

```bash
# Database
SQLALCHEMY_DATABASE_URI=postgresql://mattin:password@localhost:5432/mattin_ai
DATABASE_PASSWORD=dev_password

# Authentication
AICT_LOGIN=FAKE
SECRET_KEY=dev-secret-key-for-local-testing-only

# LLM API Keys (optional for development)
OPENAI_API_KEY=sk-proj-...

# Frontend URL
FRONTEND_URL=http://localhost:5173

# Omniadmins
AICT_OMNIADMINS=admin@example.com
```

### Docker (.env.docker)

```bash
# Database
DATABASE_USER=mattin
DATABASE_PASSWORD=mattin_secure_2024
DATABASE_NAME=mattin_ai
DATABASE_PORT=5432

# Authentication
AICT_LOGIN=FAKE
SECRET_KEY=docker-secret-key-change-in-production

# Ports
BACKEND_PORT=8000
FRONTEND_PORT=3000

# LLM API Keys
OPENAI_API_KEY=sk-proj-...
ANTHROPIC_API_KEY=sk-ant-...

# Frontend URL
FRONTEND_URL=http://localhost:3000

# Omniadmins
AICT_OMNIADMINS=admin@example.com
```

### Production (.env.production)

```bash
# Database
SQLALCHEMY_DATABASE_URI=postgresql://mattin:STRONG_PASSWORD@prod-db:5432/mattin_ai
DATABASE_PASSWORD=STRONG_DATABASE_PASSWORD

# Authentication
AICT_LOGIN=OIDC
SECRET_KEY=PRODUCTION_SECRET_KEY_256_BIT_RANDOM
AICT_OMNIADMINS=admin@company.com

# Entra ID
OAUTH_PROVIDER=ENTRAID
ENTRA_TENANT_ID=production-tenant-id
ENTRA_CLIENT_ID=production-client-id
ENTRA_CLIENT_SECRET=production-client-secret
ENTRA_REDIRECT_URI=https://api.your-domain.com/auth/callback

# LLM API Keys
OPENAI_API_KEY=sk-proj-PRODUCTION_KEY
ANTHROPIC_API_KEY=sk-ant-PRODUCTION_KEY

# Frontend URL
FRONTEND_URL=https://your-domain.com

# LangSmith (monitoring)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_PRODUCTION_KEY
LANGCHAIN_PROJECT=mattin-ai-production

# Vector DB
VECTOR_DB_TYPE=QDRANT
QDRANT_URL=https://qdrant.your-domain.com
QDRANT_API_KEY=PRODUCTION_QDRANT_KEY
```

## Security Best Practices

1. **Never commit `.env` files**: Add to `.gitignore`
2. **Use strong secrets**: Generate random 256-bit keys for `SECRET_KEY`
3. **Rotate credentials**: Periodically rotate API keys and secrets
4. **Environment-specific files**: Use different `.env` files for dev/staging/production
5. **Secret management**: Use secret managers (Azure Key Vault, AWS Secrets Manager) in production
6. **Restrict omniadmins**: Limit `AICT_OMNIADMINS` to trusted administrators only

## Generating Secure Keys

### SECRET_KEY (256-bit)

```bash
# Python
python -c "import secrets; print(secrets.token_urlsafe(32))"

# OpenSSL
openssl rand -base64 32

# Node.js
node -e "console.log(require('crypto').randomBytes(32).toString('base64'))"
```

### Database Password

```bash
# Strong random password
openssl rand -base64 24
```

## See Also

- [Authentication Guide](../guides/authentication.md) — OIDC and FAKE mode setup
- [Deployment Guide](../guides/deployment.md) — Docker and Kubernetes configuration
- [LLM Integration](../ai/llm-integration.md) — API key configuration for LLM providers
