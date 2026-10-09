# Changelog

All notable changes to the Mattin AI project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Breaking Changes

- **Public API `/call` with human approval**: agents with a human-approval middleware no longer return `409` from `/chat/{agent_id}/call`; the response carries `status: "requires_approval"` and a `pending_approval` to answer through the new `/approvals/{approval_id}/decisions` endpoints. `/call` responses now always include `status`.
- **Internal resume endpoint replaced**: `POST /internal/apps/{app}/agents/{agent}/chat/resume` is replaced by `POST /internal/approvals/{approval_id}/decisions/stream` (JSON decisions addressed by `action_id`) and `POST /internal/approvals/{approval_id}/cancel`.

### Added

- **Human approvals with expiry**: every human-in-the-loop pause is recorded with its owner and an expiry (`approval_timeout_seconds`, default 1 h). Unanswered approvals are rejected (never approved) by a background sweep, so conversations never stay paused. Answers are accepted once (compare-and-set) and only from the requester.
- **Approvals in the marketplace chat**, with countdown, cancel and a locked composer while waiting; channels that cannot ask a person (MCP, scheduled tasks, OpenAI-compatible API, platform chatbot) reject the pause and return `409 approval_not_supported_in_channel`.
- **Agent stream heartbeats and run timeout**: SSE `: ping` comments every 15 s and `AICT_AGENT_RUN_TIMEOUT_SECONDS` (default 600) per turn.

### Changed

- **AI services used by middlewares cannot be deleted**: `DELETE /internal/apps/{app}/ai-services/{id}` returns `409` naming the summarization/PII middlewares that reference it.
- **Middleware export/import**: middlewares can be exported and imported on their own and travel with agent and full-app exports (AI services by name). `Middleware.is_frozen`, never applied, is dropped.
- **Agents used as tools run their middlewares**; the tools their approval rules gate are withheld because a sub-agent cannot pause. Renaming an agent moves the approval rules that name it.
- **Conversation summarization defaults**: agents with memory now summarize at 85% of the model's input window (at most 150,000 tokens; 32,000 for models without a profile), keep the last 20 messages and summarize the whole older history. The summarization middleware uses the same values when its trigger or token limit is left empty. The agent form no longer shows the memory management fields.

### Fixed

- **Deleting an agent with conversations failed** (`Conversation.agent_id` had no ON DELETE action) and **app deletion left invisible agents behind** with their conversations: conversations now cascade (migration `agentdel001`), their checkpoints, media, sandboxes and files are removed, and an app deletion aborts instead of orphaning an agent.
- **Turn workspace path**: the local workspace built from the caller's identity is now checked to stay under `TMP_BASE_FOLDER` (CodeQL `py/path-injection`).
- **Full-app import lost tool agents**: agents were imported in name order, so an agent sorted before its tool agent lost the tool silently, and `is_tool` was not exported. Tool agents now import first and keep `is_tool`.
- **Memory could be turned off under a human-approval middleware** when an agent update omitted `middleware_ids`.
- **Summaries lost older context**: the default summarization trimmed the history it summarized to 20 tokens (`memory_summarize_threshold`), so each summary only saw the latest message and dropped the previous summary.

## [0.5.0] - 2026-10-01

### Breaking Changes

- **FAKE auth mode retired**: `AICT_LOGIN=FAKE` and the dev-login endpoint no longer exist. Use `OIDC` or the new `LOCAL` mode.
- **`SECRET_KEY` is mandatory**: The backend fails fast at startup if `SECRET_KEY` is missing, shorter than 32 characters, or a known-insecure placeholder.
- **Plugin system removed**: The `mattin.plugins` entry-point loader and the `/internal/capabilities` endpoint are gone. SharePoint sync and agent metrics are now regular core features.
- **Provider auth errors return 400**: Unauthorized errors from LLM/embedding providers are mapped to HTTP 400 instead of 401, so they no longer log the user out.
- **Release images**: Pushing to `main` no longer builds an image. Stable images are built when a GitHub Release is published (see *Changed*).
- **`requirements.txt` removed**: Dependencies are managed exclusively with Poetry.

### Added

- **LOCAL authentication mode**: Self-hosted, admin-provisioned email + password login with cookie sessions, CSRF protection, refresh-token rotation, per-IP/account throttling and lockout, set/change-password flows, and optional SMTP delivery of set-password emails.
- **Platform-level roles**: Viewer / editor / admin roles at platform level; omniadmin accounts are protected from role changes and hidden from the users list.
- **User deletion and app-ownership transfer**: Admins can delete users transferring or cascading their apps; owners can offer, accept, decline or cancel voluntary ownership transfers.
- **Scheduled tasks**: Agent-based scheduled tasks (DBOS) with run history, produced files, retention, and read-only publication in the marketplace.
- **Code-interpreter sandbox**: Sandbox subsystem (OpenSandbox / E2B / Daytona) for agents with `enable_code_interpreter`, plus `opensandbox-server` and code-interpreter images published to GHCR.
- **Skill packages**: Skills can bundle files (scripts, references, templates), platform-wide system skills are seeded from `system_defaults.yaml`, opt-in skill router, sandbox activation, and Claude plugin import.
- **Metadata-aware RAG**: Dynamic retrieval tool with metadata filtering, per-agent RAG configuration, sub-agent dynamic retrieval, Qdrant `$in` operator, and a resource reindex action.
- **Playground media**: Media upload, audio chunking, agent video support with multiple videos per chat, agent-level media processing configuration, clipboard image paste, and chat response timers.
- **New providers**: AWS Bedrock (AI + embeddings), OpenRouter (AI), and Google embedding models.
- **Output parsers**: Support for optional fields in structured outputs.
- **MCP**: Authentication token support for external MCP servers.
- **Docker**: Multi-environment local stack (`mattin.ps1`) and containerized dev user seeding.

### Changed

- **Release image tagging**: The backend/frontend CI now tags `develop` builds with a moving `nightly` alias, and builds stable images when a **GitHub Release is published** — tagged `X.Y.Z`, `X.Y` and `latest` (the leading `v` is dropped; pre-releases are excluded from `latest`). Pushing to `main` no longer builds an image.
- **Agent metrics reworked**: Metrics dashboards at platform, app and agent level as part of the core.
- **OpenAI Responses API**: OpenAI models use the Responses API so reasoning models work with tools; `temperature` is no longer sent to reasoning models.
- **Current date in system prompt**: The current date is injected into the system prompt instead of being exposed as a tool.
- **Dependencies**: FastAPI upgraded to 0.142 and Starlette to 1.7; vulnerable dependencies upgraded; unused OpenStack Mistral client dropped.
- **Docker**: Defaults to 2 uvicorn workers with a parametrizable DB pool.
- **CI**: SonarCloud analysis for backend and frontend, PR comments, and restricted `GITHUB_TOKEN` permissions.

### Fixed

- **Resilience**: Chat turns and browser tabs stay alive when a dependency fails; DB connection pool hardened against exhaustion; sync DB connections released during LLM streaming and SSE endpoints.
- **Security**: SonarCloud blocker and critical vulnerabilities resolved; anti-enumeration dummy hash derived from random bytes; viewer write exemption matched by route.
- **Sandbox**: 500 errors, cross-user sandbox sharing, and checkpoint data loss after merge.
- **Multi-worker**: Attached-file listings work across uvicorn workers, a single cleanup leader is elected (cross-platform), and agent file uploads respect the file lifecycle to stop disk leaks.
- **RAG**: Resource reindex no longer duplicates chunks; recursive splitter and domain page chunking; silently ignored search filters; public silo search forwards `search_type` / `score_threshold`; PDF/text files vectorized at upload time.
- **Agents**: Attached document content restored in chat turns; MCP tools loaded for agents used as tools; agent-as-tool `args_schema` pinned; MCP + structured output schema completion and sanitized tool names.
- **Auth / OIDC**: Duplicate user creation race condition; auth bootstrap flash and OIDC callback alignment; omniadmins visible/invitable and app admins can invite collaborators.
- **Frontend**: Prompt template defaults to `{question}` and is never saved empty; API base URL resolution with empty runtime placeholder; conversation delete confirmation modal.
- **Misc**: App name conflict checks scoped to the importing user; PGVector/LangChain tables ensured at startup.

## [0.4.2] - 2026-05-21

### Added

- **SharePoint Sync (EE Plugin)**: New Enterprise Edition plugin module (`mattin-ai-plugins/mattin_sharepoint`) that synchronises SharePoint document libraries into Mattin AI repositories. Provides a Graph API client, background worker, and dedicated router/service/repository layers for scheduled content ingestion.
- **Streaming Middleware Source Filtering**: Middleware-level source filtering for SSE streaming responses, with unit test coverage for `streaming_utils`.
- **API Key Recovery on Masked Test-Connection**: When testing a connection for an AI or Embedding service whose key is masked, the stored API key is now recovered and used for the test request instead of sending the masked placeholder.

### Changed

- **LangSmith Tracing Restored (LangChain 1.x)**: Tracing is re-enabled via a centralised `backend/tools/langsmith_config.py` module that works with LangChain 1.x. A per-app `POST /internal/apps/{id}/langsmith/test` endpoint validates connectivity without requiring a server restart.
- **`DEFAULT_MEMORY_SUMMARIZE_THRESHOLD` Centralised**: The constant is now defined once in a shared location and defaulted to `20`. All references updated.

### Fixed

- **PDF Image Artifacts in Silo Indexing**: An artifact-cleaning pass is added to the silo indexing pipeline to strip image-only or decorative chunks produced by `PyMuPDFLoader`, preventing noisy vector store entries.
- **MCP Tools Not Loaded for Agent-as-Tool**: MCP tool configurations were not being loaded when an agent is invoked as a sub-tool by another agent. All configured MCP tools are now wired in regardless of call depth.
- **Embedding Service Model ID Using Description**: The embedding service was incorrectly using the `description` field as the model ID when constructing the embedding client. The correct `model_id` field is now used.
- **Provider-Side Tools Not Deselected**: Selecting a different tool provider in the agent form was not clearing previously selected provider-side tools, leading to stale tool selections being saved.
- **Default Prompt Template for New Agents**: New agents now default to `{question}` as the prompt template instead of an empty string, avoiding empty-prompt errors on first use.
- **Conversation Delete Requires Double-Click**: Deleting a conversation required a double-click. Replaced with a single-click action that opens a confirmation modal, consistent with the rest of the UI.

## [0.4.1] - 2026-04-30

### Added

- **Domain Crawling Policies**: Complete rewrite of the domain crawling pipeline. The legacy `Url` table is replaced by three new models — `DomainUrl`, `CrawlPolicy`, and `CrawlJob` — with dedicated repositories and services (`DomainUrlService`, `CrawlPolicyService`, `CrawlJobService`, `CrawlExecutorService`, `CrawlSchedulerService`). Policies support configurable allowed/blocked URL globs, crawl depth, frequency, user-agent, and adaptive interval backoff. An asyncio worker pool is wired into the FastAPI lifespan for background crawling.
- **Domain Detail Page — 3-Tab UI**: The Domain Detail page is fully rewritten with a three-tab layout: *Configuration* (settings + crawl policy form), *URLs* (enriched URL table with status, discovery source, next-crawl countdown, per-URL detail drawer), and *Job History* (live-polling crawl job progress panel with cancel support and a "Run Now" button).
- **Provider-Driven AI/Embedding Service Wizard**: A four-step wizard (pick provider → enter credentials → select model → confirm) replaces the free-text model name input for creating AI and Embedding services in both app and system scopes. The wizard renders model cards with capability chips, a "New" badge for recent entries, capability filters, search, skeleton loading, and provider-specific error guidance (401 → API key link, 404 → fall back to manual ID).
- **Provider Model Discovery Service**: Backend pipeline (`ProviderModelDiscoveryService`) that queries each provider's models endpoint (OpenAI, Anthropic, MistralAI, Google AI Studio, Ollama), normalises results to a shared `ProviderModelInfo` schema, filters by purpose (chat vs. embedding), drops non-chat models (dall-e, moderation, dated snapshots), and sorts newest-first using `created_at` or version embedded in the model ID.
- **Provider Listing and Test-Connection Endpoints**: New `POST .../list-models` endpoints for AI services, embedding services, system AI services, and system embedding services. Credentials in the request body are used for the listing call and are never persisted. New `POST embedding-services/test-connection` endpoints (app and system scope) mirror the existing AI service test-connection pattern.
- **Marketplace Chat SSE Streaming**: New `POST /internal/marketplace/conversations/{id}/chat/stream` endpoint that mirrors the agent stream endpoint (metadata → tool/thinking → token… → done|error) via `AgentStreamingService`. Quota is only incremented when the `done` event is emitted, so aborted or errored streams do not burn quota. `MarketplaceChatPage` is rewritten to use the shared `useStreamingChat` hook, `StreamingMessage`, scroll-to-bottom FAB, and abort button — matching playground UX exactly.
- **Multimodal RAG**: Video and audio processing with separate chunking configurations per media type. Chunk index is preserved on visual and audio chunks for modality correlation during retrieval. Processing mode is set on media records after video analysis completes.
- **OpenAI API Compatibility**: New `enable_openai_api` per-app setting and a public `/public/v1/openai` router providing OpenAI-compatible `GET /models`, `POST /chat/completions` (including streaming), and vision endpoints. `app_id` parameter now accepts both integer IDs and URL-safe slugs for rate-limit, CORS, and file-size enforcement.
- **Output Parser: Dict/JSON Field Type**: Added `dict` / JSON object as a supported field type in `OutputParser`, alongside the existing string, number, boolean, and array types.
- **GitHub Actions CI/CD Workflows**: Added backend and frontend Docker image build-and-push workflows targeting `ghcr.io/lksnext-ai-lab/mattinai-{backend,frontend}`. Triggers: push to `develop`/`main`, version tags, pull requests (build-only), and `workflow_dispatch`. Docker layer cache via `type=gha` for fast reruns.
- **Demo Workspace Import**: Added a curated demo workspace JSON (`demo_app.json`) with 2 AI services (OpenAI + Ollama), 6 pre-configured agents, and an AWS Docs Search MCP config for showcase and onboarding purposes.
- **Shared UI Primitives Library**: Introduced a foundation for consistent UX across all pages — Sonner toast surface (replaces ad-hoc banners and `window.alert()`), `ConfirmationModal` + `useConfirm` hook (promise-based delete/warning dialogs), `DataTable` wrapper (search, sorting, auto Actions column), `useApiMutation` hook (pairs `toast.promise` with result-based control flow), and `MESSAGES` constants for entity-aware copy. All providers are mounted in `ExtensibleBaseApp` and re-exported from the library entry point.
- **Inline Conversation Title Editing**: Users can now edit conversation titles inline in the Recent Conversations panel. App and agent info is also displayed alongside each conversation.
- **Google AI Studio Frontend Config**: Added Google AI Studio as a selectable provider in the frontend AI service configuration flow.

### Changed

- **Crawling Architecture**: The legacy `Url` model, `UrlRepository`, and `UrlService` are removed. All crawling data is now managed through the new `DomainUrl` / `CrawlPolicy` / `CrawlJob` pipeline with proper normalisation, glob-based filtering, and content hashing to skip unchanged pages.
- **AI/Embedding Service Pages**: All four service pages (settings AI, settings embedding, admin system AI, admin system embedding) now use `ServiceWizard` for creates and a `CompactServiceEditor` for edits. The legacy `BaseServiceForm` / `AIServiceForm` / `EmbeddingServiceForm` component tree is removed.
- **UI Standardization Across All Pages**: Every listing and form page is migrated to the shared `useApiMutation` + `useConfirm` + Sonner toast pattern. `window.confirm()` / `window.alert()` calls are eliminated. Bespoke inline-error blocks and `setNotification` banners are replaced with `toast.error` / `toast.success`. Modals now close only after a confirmed successful save, preventing the "error but entity was created" anti-pattern.
- **Immutability Enforcement**: `vector_db_type` and `embedding_service_id` are now immutable after an entity (Silo, Domain, Repository) is created. The create and update endpoints are split to enforce this at the API layer.
- **Media Configuration**: Audio and video transcription/analysis configuration (chunk duration, overlap, model selection) is moved from individual media uploads to the Repository level, so all media in a repository shares the same processing config.
- **Docker Deployment**: Deployment is centralised under `docker/` with Caddy as the reverse proxy. A single port 80 is exposed to the host; all backend, frontend, Postgres, and Qdrant services are on an internal Docker network. The same `docker-compose.yaml` is used for both local development and client server deployments — only `.env` changes.
- **Container Image Names**: Docker images published to GHCR are renamed from `ia-core-tools-{backend,frontend}` to `mattinai-{backend,frontend}` to match the product name.
- **Alembic Migration Linearization**: The empty merge migration node (`f7a5d9c1e834`) introduced during the multimodal branch is dropped; `14b4c9c42164`'s `down_revision` is updated so `alembic heads` returns a single head without the empty merge node.
- **Documentation**: Updated RAG, API reference, and integration docs for the silo playground revamp, multimodal RAG, and the new Docker deployment layout.

### Fixed

- **System AI Services 500 on List**: `available_providers` was required in `AIServiceDetailSchema` but not populated by the GET endpoints, causing a 500 response whenever the system AI services table had rows. Defaulted to `[]` (matching `EmbeddingServiceDetailSchema`).
- **MCP Config and Output Parser Create 500**: `create_or_update_mcp_config` and `create_or_update_output_parser` were calling the GET handler reuse with `AppRole` and `Session` arguments swapped, raising `'AppRole' object has no attribute 'query'` after a successful commit.
- **Repository Update 500**: The `streamline` repository refactor had removed `RepositoryService.update_repository_router`, leaving every `PUT /internal/apps/{id}/repositories/{id}` returning 500. Restored the method and added `transcription_service_id` / `video_ai_service_id` fields to `UpdateRepositorySchema` which the frontend was already sending.
- **Layout Overflow and Streaming Scroll**: The App Settings sidebar was pushing the document past 100vh and triggering the browser scrollbar. The root is now pinned to `h-screen + overflow-hidden`. Streaming auto-scroll now uses a `userScrolledUpRef` so wheel events always win the race against the next token flush; `scrollIntoView` is replaced with `container.scrollTo` to prevent scroll propagation to ancestor containers.
- **Qdrant Document Deletion Filter Format**: `QdrantStore.delete_documents()` now auto-detects and handles both PGVector-style filters (`field`, `value`, etc.) and Qdrant-native filters (`must`, `should`, `must_not` clauses), fixing document deletion failures in media and repository deletion workflows.
- **`chunk_index` Preservation**: `chunk_index` is now correctly preserved on visual and audio chunks, enabling modality correlation during retrieval (previously lost on re-indexing passes).
- **`processing_mode` Not Set After Video Analysis**: `processing_mode` is now set on the media record after video analysis completes, so the status is no longer stuck at `pending` for processed video media.
- **Vertex AI OOM on Large Videos**: Inline video uploads to Vertex AI are now capped at 50 MB before base64 encoding to prevent out-of-memory errors during video analysis.
- **Google `ChatGoogleGenerativeAI` List-Form Content**: Video analysis response parsing now handles the list-form content returned by `ChatGoogleGenerativeAI`, which previously raised a type error when the content was not a plain string.
- **System AI Services Missing from Repository Selectors**: Repository service selectors (transcription service, video AI service) now include system-level AI services, not only app-scoped ones.
- **TypeScript Build Errors**: Fixed `PlatformChatbotPanel` (`MouseEvent` passed as `string` to `handleSend`), `SystemAIServicesPage` (missing `created_at` / `available_providers` on `SystemAIService` interface), and `ProviderModelInfo` (missing `created_at` field required by `ModelSelectionStep`) — all of which broke `npm run build:lib`.
- **Qdrant Docker Healthcheck**: The Qdrant container healthcheck is switched from an HTTP curl probe to a bash `/dev/tcp` socket check, because recent Qdrant images (Debian 12 slim) ship without `curl` or `wget`.
- **Credential Whitespace**: Leading/trailing and internal whitespace in pasted API keys and credentials is now normalized across all relevant Pydantic schemas to prevent silent authentication failures.
- **DOCX Indexing**: Added missing `docx2txt` dependency; DOCX files were silently failing to index.
- **Skill Create 500**: Fixed swapped `db` / `role` argument order in the skill create router; the modal now also closes on a successful save.
- **Same-Origin Frontend Deployments**: An empty `VITE_API_BASE_URL` is now correctly respected for same-origin deployments (e.g. when the frontend is served from the same host as the backend), instead of being treated as a missing value.
- **Test Suite Reliability**: Fixed `patch.object` targets in subscription and freeze service tests to survive `importlib.reload()`; updated test factories, auth fixtures, endpoint paths, and mock targets to align with current codebase state.

## [0.4.0] - 2026-03-30

### Added

- **Platform Chatbot Widget**: Platform-wide chatbot widget with follow-up suggestions, surfaced as a persistent `PlatformChatbotWidget` overlay available across all app pages.
- **Platform Chatbot Components**: Added `PlatformChatbotWidget`, `Button`, and `Panel` React components to the frontend component library.
- **Platform Chatbot Context**: Added `PlatformChatbotContext` providing session and conversation history management for the platform chatbot.
- **Platform Chatbot API Integration**: Added platform chatbot API methods to `ApiService`; new internal router registered at `/internal/platform-chatbot` with config and chat endpoints; `PlatformChatbotConfigResponse` and `PlatformChatbotChatRequest` Pydantic schemas.
- **Platform Chatbot System Config**: Added `platform_chatbot_agent_id` field to `system_defaults.yaml` to designate the system-level chatbot agent.
- **SaaS Embedding Services**: System embedding services are now included in the Domain and Repository selectors in SaaS mode, making shared infrastructure available to tenant workflows.
- **SaaS Mode Improvements**: Various SaaS mode, marketplace, and admin-panel improvements introduced in the SaaS mode feature branch.

### Changed

- **Agent Execution Pipeline**: Unified the streaming and non-streaming agent execution paths into a single pipeline, eliminating code duplication and improving maintainability.
- **Platform Chatbot Panel**: Simplified `PlatformChatbotPanel` — extracted an `unescape` helper function and fixed abort-controller cleanup on unmount.
- **Documentation**: Updated API reference, architecture guides, and integration docs to reflect user activation flows, system settings, marketplace file handling, and new database models.

### Fixed

- **LLM Usage Tracking in Streaming**: System LLM usage is now correctly tracked in the streaming execution path, which had previously been omitted.
- **SaaS Mode Bug Fixes**: Addressed multiple SaaS mode issues identified during PR review, including edge cases in marketplace and admin flows.

## [0.3.18] - 2026-03-11

### Added

- **Marketplace Call Quota Enforcement**: Added per-user call quota tracking and enforcement for marketplace agents, including `MarketplaceUsageTracking` table, `MarketplaceQuotaService`, and quota enforcement on the marketplace conversation chat route.
- **OMNIADMIN Quota Reset**: Added endpoint for OMNIADMIN users to reset marketplace call quotas for any user.
- **Marketplace Quota UI**: Added quota usage display in chat UI, call usage section on user profile page, and Reset Quota action in admin user list.
- **GFM Table Support**: Added `remark-gfm` plugin for GitHub Flavored Markdown table rendering in chat messages.

### Changed

- **Chat Bubble Layout**: Removed max-width constraint on message bubbles for better content display.

### Fixed

- **Non-conversational Agents**: Fixed `NoneType` iterable error when middleware returns `None` for non-conversational agents.
- **Silo Validation (Security)**: Validated that silo belongs to app in public API document endpoints to prevent cross-app data access.
- **Quota Enforcement**: Enforced marketplace call quota checks on the agent chat route.

## [0.3.17] - 2026-03-08

### Added

- **Release Manager Agent**: Added dedicated agent for orchestrating complete release workflows (version bump, changelog, merge, tag, GitHub release).
- **Agent Documentation**: Added `.github/README.md` documenting all specialized Copilot agents and their capabilities.

## [0.3.16] - 2026-03-08

### Added

- **Chat Image Rendering**: Added inline display support for agent-generated images in chat conversations.
- **SSL Connectivity Option**: Added configuration support to disable SSL verification / allow unsafe SSL connections for integrations that require it.
- **System Settings Management**: Added a full app-scoped settings management experience under `/apps/:appId/settings`, including dedicated sections for `general`, `ai-services`, `embedding-services`, `api-keys`, `collaboration`, `mcp-configs`, and `data-structures`.

### Changed

- **Gemini Chat Handling**: Improved Gemini call handling and rendering behavior for native Gemini-generated images.
- **Development Agent Config**: Updated development agent definitions/instructions.

### Fixed

- **Chat UI Stability**: Resolved image flickering in chat when rendering generated images.
- **Frontend Routing**: Removed orphan non-app-scoped `/settings/*` routes (`ai-services`, `api-keys`, `collaboration`, `embedding-services`, `general`, `mcp-configs`, `data-structures`) that rendered settings pages with undefined `appId` and broken tab navigation.
- **System Settings Access**: Settings pages are now consistently reachable only through app-scoped routes (`/apps/:appId/settings`), preventing undefined context errors.
- **Navigation Targets**: Header settings link and About page shortcuts no longer point to dead non-app-scoped settings routes.

## [0.3.15] - 2026-03-02

### Added

#### Marketplace Agent Ratings
- **Agent Rating System**: User-contributed star ratings for marketplace agents
  - `AgentMarketplaceRating` model — one rating per user per profile, 1-5 stars
  - Rating endpoints: POST `/marketplace/agents/{id}/rate` and GET `/marketplace/agents/{id}/my-rating`
  - Rating requires at least one prior marketplace conversation with the agent
  - Denormalized rating stats in `AgentMarketplaceProfile`: `rating_avg`, `rating_count`

#### Marketplace UI Enhancements
- **Star Rating Component**: Interactive and read-only star display (sm/md sizes)
- **Marketplace Agent Card**:
  - Show rating average + conversation count stats row
  - "Start Chat" button that creates conversation and navigates directly to chat
- **Marketplace Agent Detail Page**:
  - Rating summary header (avg, count, conversation count)
  - Interactive rating sidebar card for users with prior conversations
  - Locked rating UI with hint for users without prior conversations
  - Automatic fetch of user's own rating on page load

#### Marketplace Conversation Tracking
- **Conversation Counter**: Automatically increment `conversation_count` on `AgentMarketplaceProfile` when a new marketplace conversation is created
- **Enhanced Catalog API**: Expose `conversation_count`, `rating_avg`, `rating_count` in catalog and detail response schemas

#### Marketplace Sorting
- **"Top Rated" Sort**: Primary sort by `rating_avg DESC NULLS LAST`, secondary by `rating_count DESC`, tertiary alphabetical

#### Marketplace Metadata
- **Published Date Display**: Always show agent published date in YYYY/MM/DD format on marketplace cards (shows "—" when null)

### Changed

- **Agent Form**: (refer to previous entries)

### Fixed

- **Marketplace API**: Removed explicit `Content-Type` header that was silently overwriting `Authorization` header in rating requests (#8d7f66d)
- **Marketplace Profile**: Back-fill `published_at` timestamp in `create_or_update_marketplace_profile()` for agents published before timestamp field existed (#2d6f20b)

## [0.3.14] - 2026-02-28

### Added

#### Agent Development Tools
- **Python Code Interpreter**: Execute Python code within agent conversations
  - Subprocess-based Python REPL tool with sandboxed execution
  - Automatic file system synchronization for generated outputs
  - Support for file uploads available to agent scripts
  - Dependencies: pandas, openpyxl for data processing

#### Provider-Side Tools
- **Provider-Aware Tool Injection**: Map generic tool names to provider-specific implementations
  - Support for OpenAI, Anthropic, Google, and Azure providers
  - Generic tool names: `web_search`, `image_generation`, `code_interpreter`, `file_search`
  - Provider-specific tool routing in `create_agent()` execution flow
  - `server_tools` JSON field added to Agent model (with migration)

#### File Download Support
- **Workspace Download Tool**: Download files from agent working directories
  - `download_url_to_workspace` tool for programmatic file retrieval
  - Working directory now computed for all agent executions (not just code interpreter)
  - File type detection with proper categorization for images and documents
  - Signed URL endpoint pattern for secure file downloads in agents and marketplace

#### Image Generation
- **Multimodal Image Output**: Handle AI-generated images within conversations
  - Image generation call blocks decoded from base64 and saved to working directory
  - Auto-registration of generated files for download and display
  - UI support for image renders in conversation history

#### Community Governance
- **Code of Conduct**: Adopted community conduct standards for contributors and users

### Changed

- **Agent File Management**: Attached files panel now refreshes automatically after agent responses without requiring page reload (#30c3331)
- **Agent Form UI**: Added Capabilities section with clickable tool cards showing provider compatibility

### Fixed

- **Marketplace**: Refresh attachments panel after agent generates files (#30c3331)

## [0.3.13] - 2026-02-28

### Added

#### Agent Marketplace
- **Agent Marketplace Platform**: Full marketplace system for publishing and discovering agents
  - Marketplace catalog page with search, filtering, and agent cards
  - Agent detail page with conversation history viewing
  - Chat page with simplified consumer experience
  - Profile management section for agent publishing
  - USER role for marketplace consumers
  - Marketplace visibility, profile, and conversation source models
  - MarketplaceService for catalog, profiles, and conversations management
  - Marketplace API router with dedicated endpoints

#### Media & Transcription
- **Audio/Video Processing**: Complete media management system
  - Media upload, storage, and management in repositories
  - Audio and video transcription with configurable services
  - Background task processing for media with polling
  - Transcription service selection in frontend
  - YouTube URL support for media import
  - Media deletion with automatic embedding cleanup
  - Chunking support for audio/video with min/max duration and overlap

#### MCP Integration
- **MCP Server Support**: Expose agents as MCP tools for external consumption
  - MCP server configuration and management
  - Agent-to-MCP-tool mapping system
  - MCP server handler with JSON-RPC 2.0 support
  - Authentication support for MCP servers
  - Connection testing endpoints for MCP configs
  - Documentation for implementing authentication in MCP servers

#### Testing Infrastructure
- **Testing Framework**: Comprehensive testing infrastructure
  - Integration tests for agents, apps, and repositories
  - Unit test suite with pytest fixtures
  - `@test` Copilot agent for test development assistance
  - Testing strategy documentation
  - Test coverage for core services

#### Access Control
- **Role-Based Access Control (RBAC)**: Enhanced permission management
  - VIEWER role implementation with read-only access
  - Role hierarchy system in frontend
  - Role-based access dependencies for all resources
  - Access validation for AI services and embedding services
  - Collaboration page UI improvements for all roles

#### Vector Database
- **Vector Database Abstraction**: Multi-backend vector store support
  - Per-silo vector database type selection (PGVector or Qdrant)
  - Qdrant backend support with metadata filtering
  - VectorStoreInterface abstraction layer
  - Frontend UI for vector database type selection
  - Enhanced error handling for empty documents

#### AI Service Features
- **Connection Testing**: AI service and MCP config validation
  - Connection test endpoints with timeout and validation
  - Resource cleanup after connection tests
  - Error logging improvements for MCP configs
  - Frontend connection test UI

#### Copilot Agents
- **Specialized Agents**: Enhanced development workflow
  - `@test` agent for testing assistance
  - `@oss-manager` agent for open-source governance
  - `@plan-executor` agent for structured plan execution
  - `@alembic-expert` agent for database migrations
  - `@git-github` agent with git handoff convention
  - `commit-and-push` skill for standardized git workflows

#### Documentation
- **Complete Documentation Overhaul**: Comprehensive project documentation
  - Architecture documentation (data flow, technology stack, design decisions)
  - AI & LLM integration guides
  - RAG system documentation
  - API reference documentation (internal and public APIs)
  - Authentication guide
  - Deployment guide
  - File processing reference
  - Environment variables reference
  - Role authorization reference
