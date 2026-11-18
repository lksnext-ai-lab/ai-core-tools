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
| `AICT_LOGIN` | No | `OIDC` | Authentication mode: `OIDC` (Microsoft Entra) or `LOCAL` (admin-provisioned email+password). FAKE mode is retired. |
| `SECRET_KEY` | **Yes** | — | Application secret key. Must be at least 32 characters and not a known placeholder. App fails fast at startup if the check fails. Used to sign JWTs and set-password tokens — rotating this value invalidates all active sessions. |
| `AICT_OMNIADMINS` | No | — | Comma-separated email addresses of superusers |
| `JWT_ALGORITHM` | No | `HS256` | **Legacy — read but unused at runtime.** LOCAL mode hardcodes HS256. |
| `JWT_EXPIRATION_HOURS` | No | `24` | **Legacy — read but unused at runtime.** Access token TTL is controlled by `LOCAL_ACCESS_TTL_MINUTES`. |

> Generate a safe `SECRET_KEY`: `python -c "import secrets; print(secrets.token_hex(32))"`

**OIDC mode**:
```bash
AICT_LOGIN=OIDC
SECRET_KEY=<64-char hex string>
AICT_OMNIADMINS=admin@example.com
```

**LOCAL mode** (self-hosted email+password):
```bash
AICT_LOGIN=LOCAL
SECRET_KEY=<64-char hex string>
AICT_OMNIADMINS=admin@example.com
```

### LOCAL Mode Tuning

All variables are optional. The defaults are suitable for most deployments.

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTH_COOKIE_SECURE` | `true` | Controls the `Secure` flag on session cookies. Set `false` only for plain-HTTP local development — never in production. |
| `LOCAL_ACCESS_TTL_MINUTES` | `15` | Access token lifetime in minutes |
| `LOCAL_REFRESH_TTL_DAYS` | `14` | Refresh token lifetime in days |
| `LOCAL_LOCKOUT_THRESHOLD` | `5` | Failed login attempts before account lockout |
| `LOCAL_LOCKOUT_BASE_SECONDS` | `60` | Base lockout duration in seconds (exponential backoff: `base * 2^(attempts - threshold)`) |
| `LOCAL_TOKEN_LEEWAY_SECONDS` | `30` | Clock-skew tolerance for JWT validation |
| `LOCAL_SET_PASSWORD_TOKEN_MAX_AGE_HOURS` | `48` | Validity window for admin-issued set-password links |

### SMTP (LOCAL Mode)

Used to email set-password links when calling `POST /internal/admin/users/{id}/reset-link`. Both `SMTP_HOST` and `SMTP_FROM` must be set to enable email delivery. When either is absent a `NoopEmailSender` is used: the token is returned only in the admin API response body (never logged) and the admin must forward it manually. For newly created users (`POST /internal/admin/users/local`) the token is always returned only in the response body — no email is sent regardless of SMTP configuration.

| Variable | Default | Description |
|----------|---------|-------------|
| `SMTP_HOST` | — | SMTP relay hostname. Required for email delivery. |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | — | SMTP authentication username (optional) |
| `SMTP_PASSWORD` | — | SMTP authentication password. Never logged. |
| `SMTP_TLS` | `true` | Enable STARTTLS |
| `SMTP_FROM` | — | Sender address (e.g. `no-reply@example.com`). Required for email delivery. |
| `SMTP_TIMEOUT_SECONDS` | `10` | Per-connection SMTP timeout |

**Example (LOCAL mode with SMTP)**:
```bash
AICT_LOGIN=LOCAL
SECRET_KEY=<64-char hex string>
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=no-reply@example.com
SMTP_PASSWORD=smtp-password
SMTP_FROM=no-reply@example.com
```

### LLM API Keys

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | No | — | OpenAI API key (sk-...) |
| `ANTHROPIC_API_KEY` | No | — | Anthropic API key |
| `MISTRAL_API_KEY` | No | — | MistralAI API key |
| `AZURE_OPENAI_API_KEY` | No | — | Azure OpenAI API key |
| `AZURE_OPENAI_ENDPOINT` | No | — | Azure OpenAI endpoint URL |
| `GOOGLE_API_KEY` | No | — | Google Gemini API key for AI Studio LLMs and embeddings |

**Example**:
```bash
OPENAI_API_KEY=sk-proj-...
ANTHROPIC_API_KEY=sk-ant-...
MISTRAL_API_KEY=...
```

**Note**: API keys are optional. Configure only the providers you plan to use.

Google AI Studio and Vertex AI credentials can also be configured per AI Service or Embedding Service in the Mattin AI UI. Vertex AI uses a service-account JSON, project ID, and region stored on the service configuration rather than a global environment variable.

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

> **LangChain 1.x naming**: Since v0.4.2, Mattin AI uses the `LANGSMITH_*` prefix (not the older `LANGCHAIN_*` prefix). The central module `backend/tools/langsmith_config.py` handles both per-app keys (stored on the `App` model) and the global env-var fallback.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LANGSMITH_TRACING` | No | `false` | Enable global LangSmith tracing fallback (`true`/`1`/`on`/`yes`) |
| `LANGSMITH_API_KEY` | No | — | LangSmith API key (global fallback; per-app key takes precedence) |
| `LANGSMITH_PROJECT` | No | `default` | LangSmith project name (global fallback) |
| `LANGSMITH_ENDPOINT` | No | `https://api.smith.langchain.com` | Custom LangSmith endpoint |

**Example**:
```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_pt_...
LANGSMITH_PROJECT=mattin-ai-production
```

**Per-app tracing**: Each app can store its own LangSmith API key (`App.langsmith_api_key`). This takes priority over the global env vars. Test connectivity via `POST /internal/apps/{id}/langsmith/test`.

### Embedding Requests

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AICT_EMBEDDING_REQUEST_TIMEOUT_SECONDS` | No | `120` | Client-side timeout (seconds) of embedding calls; retries are unchanged. Applies to OpenAI, MistralAI, Custom/HuggingFace, Ollama and AWS Bedrock embedding services. Azure AI and Google (AI Studio, Vertex AI) clients have no timeout parameter, so it does not apply to them |

See [App Chat](../ai/app-chat.md#attachment-indexing).

### Agent and Chat Execution Limits

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AICT_AGENT_RECURSION_LIMIT` | No | `50` | Graph step limit of an agent run (every model call and tool call is a step). Not an integer or below 1: warning and default |
| `AICT_CHAT_RECURSION_LIMIT` | No | `100` | Same, for App Chat turns only (they spend more steps). Reaching it ends the Chat turn with `STEP_LIMIT_REACHED` and keeps the conversation. Same fallback rule |
| `CHAT_MAX_FILES_PER_TURN` | No | `10` | App Chat: files (uploads plus references) per message; `0` = unlimited; HTTP 422 `TOO_MANY_FILES` beyond it (`/messages` and `/stream`) |
| `ATTACHMENT_INDEXING_TURN_BUDGET_S` | No | `120` | App Chat: total seconds of attachment indexing per turn; `0` = unlimited; keep well below `AICT_AGENT_RUN_TIMEOUT_SECONDS` |

Sizing: the Chat's middleware chain costs about 3 graph steps per tool-using model call, so 100 allows about 33 such calls per Chat turn and the agent default of 50 about 16. See [App Chat](../ai/app-chat.md#step-limit).

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

### SaaS Mode

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AICT_DEPLOYMENT_MODE` | No | `self_managed` | Deployment mode: `self_managed` or `saas` |
| `STRIPE_API_KEY` | SaaS | — | Stripe secret key (`sk_test_...` for dev, `sk_live_...` for prod) |
| `STRIPE_WEBHOOK_SECRET` | SaaS | — | Stripe webhook signing secret (`whsec_...`) |
| `STRIPE_PRICE_ID_STARTER` | SaaS | — | Stripe Price ID for the Starter plan |
| `STRIPE_PRICE_ID_PRO` | SaaS | — | Stripe Price ID for the Pro plan |
| `EMAIL_FROM` | SaaS | — | Sender address for transactional emails |
| `SMTP_HOST` | SaaS | `localhost` | SMTP server host |
| `SMTP_PORT` | SaaS | `587` | SMTP server port |
| `SMTP_USER` | No | — | SMTP username (optional) |
| `SMTP_PASS` | No | — | SMTP password (optional) |

> **Note**: Variables marked **SaaS** are required only when `AICT_DEPLOYMENT_MODE=saas`. The application will refuse to start if any are missing.

**Example (local dev / SaaS test)**:
```bash
AICT_DEPLOYMENT_MODE=saas

# Stripe test keys
STRIPE_API_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID_STARTER=price_starter_test
STRIPE_PRICE_ID_PRO=price_pro_test

# Email
EMAIL_FROM=noreply@yourdomain.com
SMTP_HOST=localhost
SMTP_PORT=587
```

See [SaaS Mode Guide](../guides/saas-mode.md) for complete setup instructions.

### Sandbox Providers

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SANDBOX_DEFAULT_PROVIDER` | No | `opensandbox` | Default code interpreter sandbox provider: `opensandbox`, `daytona`, or `e2b` |
| `SANDBOX_ALLOWED_PROVIDERS` | No | `opensandbox,daytona,e2b` | Comma-separated provider names apps may select |
| `OPENSANDBOX_DOMAIN` | OpenSandbox | `localhost:8080` | OpenSandbox server host and port |
| `OPENSANDBOX_API_KEY` | OpenSandbox | — | OpenSandbox server API key, sent by the backend in the `OPEN-SANDBOX-API-KEY` header. **Mandatory when the `opensandbox` compose profile is enabled** (at least 32 characters, see [OpenSandbox server](#opensandbox-server-docker-compose-profile)) |
| `OPENSANDBOX_CODE_INTERPRETER_IMAGE` | No | `opensandbox/code-interpreter:v1.0.2` (code default, `backend/config.py`); `ghcr.io/lksnext-ai-lab/mattinai-code-interpreter:${IMAGE_TAG:-develop}` in `docker/docker-compose.yaml` | OpenSandbox code interpreter image |
| `DAYTONA_API_KEY` | Daytona | — | Daytona API key |
| `DAYTONA_API_URL` | No | SDK default | Daytona API URL |
| `DAYTONA_TARGET` | No | org default | Daytona target/region |
| `DAYTONA_IMAGE` | No | — | Optional Daytona image for sandbox creation |
| `DAYTONA_SNAPSHOT` | No | — | Optional Daytona snapshot for sandbox creation |
| `DAYTONA_WORKSPACE` | No | `workspace` | Workspace root inside Daytona sandboxes |
| `DAYTONA_SUPPORTED_LANGUAGES` | No | `python,bash` | Languages exposed through the Daytona provider |
| `DAYTONA_AUTO_STOP_INTERVAL` | No | `2` | Daytona auto-stop interval in minutes. Defaults to the global idle timeout rounded up to minutes |
| `E2B_API_KEY` | E2B | — | E2B API key |
| `E2B_TEMPLATE` | No | SDK default | Optional E2B sandbox template name or ID |
| `E2B_WORKSPACE` | No | `/home/user/workspace` | Workspace root inside E2B sandboxes |
| `E2B_SUPPORTED_LANGUAGES` | No | `python,javascript,bash` | Languages exposed through the E2B provider |
| `E2B_ALLOW_INTERNET_ACCESS` | No | `true` | Whether E2B sandboxes may access the internet |
| `SANDBOX_DEFAULT_TIMEOUT_S` | No | `30` | Per-execution timeout in seconds |
| `SANDBOX_SKILL_BOOTSTRAP_TIMEOUT_S` | No | `120` | Timeout for a skill's bootstrap script inside the sandbox. Deliberately more generous than `SANDBOX_DEFAULT_TIMEOUT_S` — bootstrap scripts are allowed to assume network egress (e.g. `pip install`) to prepare a skill's runtime dependencies. |
| `SANDBOX_SESSION_TTL_H` | No | `2` | Max sandbox lifetime in hours for providers that enforce TTL |
| `SANDBOX_IDLE_TIMEOUT_S` | No | `120` | Max idle time before cached sandboxes are stopped/destroyed |
| `SANDBOX_REAPER_INTERVAL_S` | No | `30` | How often the backend checks for idle sandboxes |
| `SANDBOX_CREATE_TIMEOUT_S` | No | `60` | Timeout for creating or reconnecting a sandbox |
| `SANDBOX_MAX_OUTPUT_CHARS` | No | `20000` | Maximum characters returned by one code execution (truncated beyond it) |
| `SANDBOX_MAX_EXECUTIONS_PER_TURN` | No | `5` | Code execution budget **per turn** (not per process). For agents it counts REPL executions; in the App Chat one budget is shared by the REPL tools and `Bash`. `0` is **not** unlimited: it refuses every execution |
| `SANDBOX_RENEW_MINUTES` | No | `30` | Minutes before a sandbox's TTL is proactively renewed |
| `SANDBOX_TEST_CONNECTION_ALLOW_PRIVATE` | No | `false` | `true` lets the Sandbox Services "Test connection" probe loopback, link-local and private addresses (needed to test the bundled `opensandbox:8080`). Leave `false` if untrusted tenants can configure their own sandbox endpoints |
| `SANDBOX_TEST_CONNECTION_TIMEOUT_S` | No | `20` | Bound of the create/run/destroy probe of "Test connection" |
| `OPENSANDBOX_SUPPORTED_LANGUAGES` | No | `python,bash` | Languages exposed through the OpenSandbox provider (comma-separated) |
| `OPENSANDBOX_MAX_CONTEXTS_PER_LANGUAGE` | No | `4` | Parallel code contexts per language inside one OpenSandbox sandbox (the compose file default is also `4`; `docker/.env.example` sets `6`) |

The Chat code interpreter, its limits and the output delivery caps below are described in [App Chat](../ai/app-chat.md#code-interpreter).

#### App Chat sandbox limits

`SANDBOX_MAX_SESSIONS_PER_USER` and `SANDBOX_MAX_SESSIONS_PER_APP` are counted **per backend process**, not across workers; `0` = unlimited. `SANDBOX_EVICT_MIN_IDLE_S` and `SANDBOX_CHAT_BASH_MAX_TIMEOUT_S` apply to the Chat only.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SANDBOX_MAX_SESSIONS_PER_USER` | No | `3` | Live sandboxes per user, App Chat only |
| `SANDBOX_MAX_SESSIONS_PER_APP` | No | `10` | Live sandboxes per App, App Chat only |
| `SANDBOX_EVICT_MIN_IDLE_S` | No | `60` | Minimum idle seconds before the Chat may evict one of the requester's own sandboxes to make room (`0` = no minimum). Another user's sandbox is never evicted |
| `SANDBOX_CHAT_BASH_MAX_TIMEOUT_S` | No | `60` | Ceiling of one `Bash` call in the Chat, seconds (minimum `1`) |

#### Sandbox output files (agents and App Chat)

The caps apply **per turn** (`0` = no cap, except where noted); only the pull concurrency is per process.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SANDBOX_PULL_MAX_FILES` | No | `20` | Output files delivered per turn (`0` = no cap) |
| `SANDBOX_PULL_MAX_FILE_BYTES` | No | `52428800` (50 MB) | Size of one file (`0` = no cap). Do not set this and `SANDBOX_PULL_MAX_TOTAL_BYTES` both to `0`: the pull then reads files without a bound |
| `SANDBOX_PULL_MAX_TOTAL_BYTES` | No | `104857600` (100 MB) | Total bytes per turn (`0` = no cap) |
| `SANDBOX_PULL_TIME_BUDGET_S` | No | `20` | Time budget of one turn's pull, seconds (`0` = no budget) |
| `SANDBOX_PULL_MAX_CONCURRENT` | No | `2` | Pulls running at once per process (a value below 1 is treated as 1) |

All these values are clamped to `>= 0`. `SANDBOX_MAX_CONCURRENT_SESSIONS` is **not** an environment variable: the process-wide cap of 50 live sandboxes is a code default (`backend/services/sandbox_session_service.py`) that `backend/config.py` does not read.

#### OpenSandbox server (Docker compose profile)

Variables of the bundled `opensandbox` profile in `docker/docker-compose.yaml` (`docker/opensandbox/entrypoint.py`). Operations, exposure and mitigations: `docker/README.md`, section "OpenSandbox: exposición y mitigaciones".

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENSANDBOX_API_KEY` | **Yes** (profile) | — | `>= 32` characters of `[A-Za-z0-9._~+/=-]`, not a known placeholder. A preflight service makes `docker compose --profile opensandbox up` fail without a valid key. Generate: `python -c "import secrets; print(secrets.token_hex(32))"`. The backend uses the same variable |
| `OPENSANDBOX_INSECURE_SERVER` | No | — | Dev only. `YES` alone no longer lets the server start without a key |
| `OPENSANDBOX_ALLOW_INSECURE_DEV` | No | — | Dev only. `1`, together with `OPENSANDBOX_INSECURE_SERVER=YES` and an empty key, starts the control plane **without authentication** (logged as ERROR on every start). Never where untrusted code can run |
| `OPENSANDBOX_LOG_LEVEL` | No | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`. `DEBUG` may log proxied frame payloads: not for shared deployments |
| `OPENSANDBOX_BIND_HOST` | No | auto-detected | IP the API listens on (never `0.0.0.0` or `::`). By default the server binds to its address on the control network only, so sandbox code cannot reach the API. The shipped compose file does not forward this variable to the container; it is read by the entrypoint if you pass it through an override |
| `SANDBOX_NETWORK_NAME` | No | `docker_sandbox-workloads` | Name of the Docker network sandboxes run on; also rendered into the server config. Use a different name for a second OpenSandbox server on the same host |
| `OPENSANDBOX_SERVER_VERSION` | No | `0.1.11` | Build argument: `opensandbox-server` pip version packaged in the image |
| `COMPOSE_FILE` | No | — | Docker Compose variable. Set to `docker-compose.yaml:docker-compose.sandbox-hardened.yaml` for the **hardened mode** (no egress from sandboxes; Docker Engine >= 28; `pip install` in sandboxes stops working) |

Breaking change for existing deployments of the profile: set `OPENSANDBOX_API_KEY`, remove `OPENSANDBOX_INSECURE_SERVER=YES` from `.env`, pull or rebuild the images and recreate the network with `docker compose --profile opensandbox down` followed by `up -d` (live sandboxes are lost; the backend recreates them on demand). Never publish port 8080 of `opensandbox` on `0.0.0.0`.

### Service End of Service

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AICT_SYSTEM_SERVICE_END_OF_SERVICE_WARNING_DAYS` | No | `30` | Days before a service's end-of-service date during which it is shown as `deprecated`. `0` = no deprecated phase. Overrides the system setting `service_end_of_service_warning_days` (default in `backend/system_defaults.yaml`) |

The warning window only affects display. A service is blocked at runtime as soon as its date is reached, whatever this value is. `SANDBOX_DEFAULT_PROVIDER` (the env/system default provider) has no lifecycle. See [Knowledge Base AI Services](../guides/chat-bot/kb-ai-services.md#service-end-of-service).

### Skill Package Import

Hardened limits applied by the in-memory zip reader (`backend/utils/safe_zip.py`) when a skill package (`.zip`) is imported — via the app-scoped `/skills/import` route, the admin `/system-skills/import` route, or a Claude Code plugin import. All are optional; an invalid value (non-numeric, NaN/infinite, below the documented minimum) makes the backend fail fast at startup rather than silently falling back to the default.

| Variable | Default | Description |
|----------|---------|--------------|
| `SKILL_IMPORT_MAX_FILES` | `500` | Maximum number of file entries in an uploaded skill package |
| `SKILL_IMPORT_MAX_TOTAL_BYTES` | `52428800` (50 MiB) | Maximum cumulative **uncompressed** size of an uploaded skill package |
| `SKILL_IMPORT_MAX_FILE_BYTES` | `10485760` (10 MiB) | Maximum **uncompressed** size of a single file inside a skill package |
| `SKILL_IMPORT_MAX_RATIO` | `100` | Maximum uncompressed/compressed ratio (zip-bomb guard), measured against the uploaded archive size |
| `SKILL_IMPORT_MAX_ARCHIVE_BYTES` | `26214400` (25 MiB) | Maximum size of the uploaded (compressed) archive itself |
| `SKILL_IMPORT_MAX_CONCURRENCY` | `2` | Maximum number of skill package import/export operations processed concurrently per backend process (shared bulkhead — both hold a whole package in memory); exceeding it returns HTTP 429 |
| `SKILL_IMPORT_MAX_PLUGIN_SKILLS` | `25` | Maximum number of candidate skills (top-level `skills/<name>/` directories) accepted from a single Claude Code plugin archive import |
| `SKILL_IMPORT_LOCK_TIMEOUT_SECONDS` | `5` | Per-app advisory lock timeout applied while importing one candidate skill from a Claude Code plugin archive; bounds how long a contended import can hold the shared import/export bulkhead before that candidate is reported busy |

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

**LOCAL mode** (OIDC disabled):
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

Variables specific to `docker/docker-compose.yaml`:

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

# Authentication — LOCAL mode for local development
AICT_LOGIN=LOCAL
SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
AUTH_COOKIE_SECURE=false        # Required for plain-HTTP local dev

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
AICT_LOGIN=LOCAL
SECRET_KEY=<generate a strong key — minimum 32 chars>

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

- [Authentication Guide](../guides/authentication.md) — OIDC and LOCAL mode setup, cookie transport, provisioning workflow, and migration from FAKE mode
- [Deployment Guide](../guides/deployment.md) — Docker and Kubernetes configuration
- [LLM Integration](../ai/llm-integration.md) — API key configuration for LLM providers
