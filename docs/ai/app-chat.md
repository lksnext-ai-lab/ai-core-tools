# App Chat

> Part of [Mattin AI Documentation](../index.md) · End-user guide: [Chat in an App](../guides/chat-bot/app-chat.md)

## Overview

The **App Chat** is a per-App chat page (`/apps/:appId/chat`) where any member picks, for every message, the AI service (model), an optional knowledge source (silo), skills and MCP configs. It is meant for people who want to talk to a model over the App's resources without building an agent first.

Technically it is a *hidden internal agent per App* plus a *per-request configuration* resolved from the user's selection:

- The agent is a normal `Agent` row with `kind = 'internal_chat'`, created on first use (no backfill; imported Apps recreate it on demand). It is **shared by every user of the App and never modified**.
- Each turn builds a frozen `ResolvedChatConfig` (AI service, silo, skills, MCP connections, system prompt) that `create_agent`, execution and metrics read instead of the agent's own fields.
- Everything user-specific (conversations, files, selection, defaults, LangGraph thread) is keyed by the calling user.

| Aspect | Value |
|--------|-------|
| Menu entry | "Chat" in the App navigation |
| Minimum role | `VIEWER` (every endpoint) |
| API | `/internal/apps/{app_id}/chat/...` (internal API only) |
| Router | `backend/routers/internal/internal_chat.py` |
| Service | `backend/services/internal_chat/` (`chat_service.py`, `selection_resolver.py`, `resolved_config.py`) |
| Migrations | `ichat001`, `ichat002` |
| Metrics channel | `INTERNAL_CHAT` |
| Env vars | none for the Chat itself; `AICT_EMBEDDING_REQUEST_TIMEOUT_SECONDS` (embedding client timeout, see [Operations](#operations)) |

## The hidden internal agent

`Agent.kind` is `'standard'` (default) or `'internal_chat'`. The internal agent:

- is invisible in agent lists, agent forms (as a tool candidate), export/import, the marketplace, MCP servers, A2A and the public API (including the OpenAI-compatible endpoints);
- answers **404** on every non-Chat surface (agent detail/update/delete, `/chat/{id}/...`, `/files/{id}/...`, OCR, the generic `/internal/conversations` router, public API), indistinguishable from a missing agent;
- is protected at database level by constraints: it cannot be a tool, A2A-enabled, published to the marketplace or have the code interpreter enabled (`ck_agent_internal_chat_unexposed`), must belong to an App, and there is at most one per App (`uq_agent_internal_chat_per_app`).

What a Chat turn does **not** use from the agent: tool associations, server tools, output parser, code interpreter, agent middlewares (so no per-agent PII rules and no human-approval rules), chat filters and the skill router. Memory is always on (LangGraph PostgreSQL checkpointer); history is summarized by the default `SummarizationMiddleware`, built with the turn's own model, and adapted to that model on every call (see [Switching models between turns](#switching-models-between-turns)).

## Per-turn selection

`ChatSelection` is what the client sends with every turn:

```json
{"ai_service_id": 12, "silo_id": 3, "skill_ids": [5, 9], "mcp_config_ids": [2]}
```

`silo_id` is optional; the lists default to empty and hold at most 50 ids. Unknown keys are rejected (422).

`ChatSelectionResolver` is the single door from a client selection to a `ResolvedChatConfig`. It validates **before anything is created** (no conversation, message, metrics event or turn row is written for an invalid selection):

| Situation | Result |
|-----------|--------|
| An id is missing, belongs to another App, or the skill is disabled | 404 `NOT_FOUND`, the same message for every cause |
| AI service (or the silo's embedding service) retired | 409 `SERVICE_RETIRED` |
| An MCP config has an unusable connection config | the turn runs without it and warns (`warnings` in `metadata`) |

Selectable: the App's own AI services plus system ones, silos of the App (not frozen), enabled skills (App and system), the App's MCP configs. Any non-retired AI service is selectable (there is no "chat capable" flag).

`ResolvedChatConfig` rules:

- Frozen, built once per request, threaded explicitly through execution. It is **never assigned onto the ORM `Agent`**: the row is shared, so any attribute written there would leak between concurrent turns.
- ORM objects inside it are valid only within the request session; anything after the run (hooks, logs, metrics) uses the `*_id` / `*_name` snapshots.
- Any future cache must be keyed on `(app_id, to_selection_dict())`, never on the config object.

### Defaults and conversation state

| Table | Key | Content |
|-------|-----|---------|
| `chat_user_default` | PK `(user_id, app_id)` | The user's last selection |
| `chat_conversation_state` | PK `conversation_id` | The conversation's own selection, a `generation` counter (bumped by reset), and the busy marker `busy_token` (UUID) / `busy_until` (timestamptz), both nullable, added by `ichat002` |
| `conversation_turn` | PK `id`; unique `(conversation_id, turn_index)` | Snapshot per assistant message: model, silo, skills, MCP configs (ids + names), linked to the message id and execution event |

Foreign keys (migration `ichat001`):

| Table | Column | References | On delete |
|-------|--------|------------|-----------|
| `conversation_turn` | `conversation_id` | `Conversation` | CASCADE |
| `conversation_turn` | `app_id` | `App` | CASCADE |
| `conversation_turn` | `user_id` (nullable) | `User` | SET NULL |
| `chat_user_default` | `user_id` | `User` | CASCADE |
| `chat_user_default` | `app_id` | `App` | CASCADE |
| `chat_conversation_state` | `conversation_id` | `Conversation` | CASCADE |
| `chat_conversation_state` | `app_id` | `App` | CASCADE |

- A **new conversation** starts from the user's last selection (`chat_user_default`), else the App default: the first non-retired AI service (the App's own, then system ones), with no silo, skills or MCP.
- An **opened conversation** keeps its own selection.
- Both are written when a turn completes, in one transaction with the turn row. Stored selections are sanitized on read: entries that no longer exist or are retired are dropped and reported as `warnings` (`kind`: `ai_service | silo | skill | mcp_config`). If the AI service itself is gone, the selection is `null` and the client must choose again.
- Turn snapshots keep names, so history still shows what answered a message after a resource is deleted (`deleted: true`).

### Switching models between turns

The model can change on every turn of the same conversation, and the whole history lives in one LangGraph thread that stores each AI message exactly as the provider that wrote it produced it (OpenAI reasoning items, Anthropic thinking signatures, Gemini thought signatures, ...). Another provider's converter either raises on those blocks or forwards them to the wire. For Chat turns only, `build_agent_middlewares(..., chat_turn=True)` (called from `backend/tools/agentTools.py` with the turn's service id and model name) appends `HistoryNormalizerMiddleware` (`backend/tools/middleware/history_normalizer.py`) last in the chain:

- **Per call, in the view only.** It rewrites the message list of each model call through `request.override`; nothing stored is modified, so going back to the earlier model gives it its own original messages.
- **Own vs foreign.** An AI message passes through untouched only if it comes from the same wire family and carries the same stamp as the turn (same AI service id and same model). Messages written by another provider, another AI service or another model of the same provider (even with the same provider's blocks) are foreign: they are sent as plain text with the same tool calls (ids unchanged, so the tool results stay paired). A message with plain string content and no provider-specific data is never rewritten. A reasoning-only answer is sent as `[no text response]`.
- **Stamp.** Every Chat answer is stored with `response_metadata["aict_service_id"]` and `["aict_model"]`. Messages stored before the stamp existed, or written under another model name (for example after the service's model name is edited), count as foreign: they are rewritten to text, which is harmless.
- **Interrupted tool calls.** A tool call without a tool result (an interrupted turn) gets a synthetic error result (`Tool call interrupted: no result was recorded.`) in the model's view. Only the Chat does this: a Chat turn can never pause for approval, so an unanswered call is always an interruption. Regular agents keep their existing recovery.
- If the view cannot be built, the turn continues with the original messages and logs a warning (class name only).

What carries over to the new model: the text of the messages and the tool calls and results. What does not: the earlier model's internal reasoning.

#### Long history on a smaller window

Summarization is built with the turn's model, so after a switch to a model with a smaller window its trigger fires before the first model call. The summary input is bounded by `summary_trim_limits` in `backend/tools/middleware/factory.py`, which applies to **every agent with memory**, not only the Chat:

- The older history is sent whole while it fits the summary model's window minus an overhead (2,000 tokens, at most half the window). A conversation that stayed on one model is therefore never trimmed (its older history is about the 85% trigger at most).
- Above that threshold it is trimmed to about 80% of the window (minus the overhead), dropping the middle and keeping the earlier summary when it fits.
- An explicit `trim_tokens` on the summarization middleware wins over this.
- A regular agent on a model without a profile is not bounded; a Chat turn on a model without a profile assumes a window of about 37.6k tokens (the window whose 85% trigger is the 32k fallback).
- A configured trigger larger than the summary model's window logs a warning.
- The summary call is retried only on transient errors: HTTP 4xx other than 408 and 429 (for example a context overflow) are tried once; cancellation is never retried.

## API

Base: `/internal/apps/{app_id}/chat`. Auth is the normal internal session; every route requires at least `viewer`.

### Options and defaults

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/options` | `ai_services`, `silos` (with `source_type`: `repository`, `domain`, `sharepoint`, `silo`), `skills`, `mcp_configs`, `default_selection`, `default_warnings`, `has_usable_model`, `attachment_indexing` (`{enabled, reason}`; `reason` is `null`, `"no_default_embedding_service"` or `"embedding_service_retired"`, see [Attachment indexing](#attachment-indexing)) |
| GET | `/defaults` | The caller's default selection, or `null` if the App has no usable model |
| PUT | `/defaults` | Pin the caller's default (validated like a turn) |

Retired AI services are not offered; silos whose embedding service is retired are listed with `disabled_reason: "embedding_service_retired"`.

### Conversations

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/conversations?limit=50&offset=0` | The caller's conversations, newest first (`limit` 1-100) |
| POST | `/conversations` | Create (`{title?, selection?}`); returns the effective `selection` |
| GET | `/conversations/{id}` | History (`messages` with per-message `turn`), `current_selection`, `warnings`, `pending_approval` |
| PATCH | `/conversations/{id}` | Rename (`{title}`, 1-255 chars) |
| DELETE | `/conversations/{id}` | Delete; 204 |
| POST | `/conversations/{id}/reset` | Forget history, keep selection |

`GET /conversations` never creates the internal agent. A conversation can also be created implicitly by sending a first turn without `conversation_id`.

Reset rotates the conversation's `session_id` (new LangGraph thread) and bumps `generation` in one transaction, then removes the old thread, the turn rows, the attachments that existed before the reset, and temporary media. A turn that was running during a reset or delete persists nothing and drops its own thread.

### Turns

`POST /stream` (Server-Sent Events) and `POST /messages` (one JSON answer) take **multipart form data**:

| Field | Required | Notes |
|-------|----------|-------|
| `message` | yes | Text |
| `selection` | yes | JSON string of a `ChatSelection` |
| `conversation_id` | no | Omit to create the conversation; otherwise it must be the caller's |
| `files` | no | New files for this turn |
| `file_references` | no | JSON array of ids of already attached files. Omitted: all attached files; `[]`: none |
| `search_params` | no | JSON object of silo search parameters |

`prepare_turn` runs before any response exists, so 403/404/409/422 are real HTTP errors, not SSE events.

**One turn at a time per conversation.** A turn on an existing conversation first claims it in `chat_conversation_state` (`busy_token`, `busy_until`, a compare-and-set committed at once). A second message sent while the first is still in flight (another tab, a retry) is refused with **409** `{detail, error_code: "CONVERSATION_BUSY"}` and `Retry-After: 5`, on both `/stream` and `/messages`; as with the other pre-flight errors it is a real HTTP status before any stream starts, and nothing is written for the refused message. A request that creates its own conversation cannot conflict. The claim:

- is released when the turn ends (in the same transaction that stores the turn row), fails, is cancelled or the client disconnects;
- is cleared by a reset;
- is pushed a full TTL ahead right before the model runs;
- expires on its own if the server process dies mid-turn: `BUSY_MARKER_TTL_SECONDS = AGENT_RUN_TIMEOUT_SECONDS + 60` (`backend/services/internal_chat/chat_service.py`), 11 minutes with the default run timeout of 600 s (`AICT_AGENT_RUN_TIMEOUT_SECONDS`), measured on the database clock.

Repository methods: `claim_busy`, `renew_busy`, `release_busy` in `backend/repositories/internal_chat_repository.py`. A lock timeout while claiming is also answered as busy.

**SSE events** (`data: {"type": ..., "data": {...}}`; lines starting with `:` are heartbeats):

| Event | Content |
|-------|---------|
| `metadata` | First event. `conversation_id`, `has_memory`, and `turn_config`: `{ai_service: {id, name}, silo: {id, name} \| null, skills: [{id, name}], mcp_configs: [{id, name}], warnings: [{kind, id}]}`. `warnings` lists selected MCP configs skipped for this turn. The internal agent's id, name and the thread's `session_id` are never sent |
| `token` | `{content}` text chunk |
| `tool_start`, `tool_end` | Tool activity |
| `done` | `{response, conversation_id, files, status: "completed", assistant_message_id, turn}`. `turn` is the `ChatTurnInfo` snapshot (`turn_index`, `ai_service_*`, `silo_*`, `skills`, `mcp_configs`, `created_at`, `warnings`) or `null` if it could not be persisted (the answer is still valid). `turn.warnings` also reports selected MCP configs whose tools failed to load |
| `error` | `{message}`; for a retired service `{message, code: "service_retired"}` |

If the first turn of a conversation created by that very request fails before answering, the empty conversation is removed before the `error` event is delivered.

`POST /messages` returns `{response, conversation_id, metadata: {files_processed, turn_config}, turn}`.

### Conversation files

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/conversations/{id}/files` | Upload one file (`file`); same response shape as the playground upload |
| GET | `/conversations/{id}/files` | List with total size |
| DELETE | `/conversations/{id}/files/{file_id}` | Remove |
| GET | `/conversations/{id}/files/{file_id}/download` | `{download_url, filename}`: a signed `/static` link that **expires after 5 minutes**. Request a fresh one each time |

### Attachment indexing

Files attached through the upload endpoint are either **indexed** (chunked and embedded into a per-conversation temporary silo, then retrieved by relevance when the model needs them) or **sent whole** in the prompt. The choice follows the App setting `default_embedding_service_id`:

| App state | Result | `GET /options` -> `attachment_indexing` |
|-----------|--------|------------------------------------------|
| Default embedding service set, active or deprecated | Indexed | `{enabled: true, reason: null}` |
| Not set | Sent whole | `{enabled: false, reason: "no_default_embedding_service"}` |
| Set but retired | Sent whole (a retired default is never used) | `{enabled: false, reason: "embedding_service_retired"}` |

Details (`backend/services/chat_attachment_service.py`, `chat_service.py`):

- **Setting.** `App.default_embedding_service_id` (nullable FK to the embedding service, `ON DELETE SET NULL`, migration `ichat002`), in the App read and update API (`/internal/apps/{id}`; an update that omits the field leaves it unchanged, `null` clears it). It must be the App's own or a system embedding service and cannot be newly set to a retired one. The App settings page shows it as "Default embedding service", next to the default sandbox.
- **Temp silo.** One per conversation, created with the default at the time of the first indexed upload. If the App default changes later, the conversation's silo keeps the service it was created with (a collection never mixes embedding models).
- **Off the request.** Indexing runs in a small dedicated thread pool on its own database session, with a **60 s** limit per file and at most **2 concurrent jobs per embedding service** (jobs over the cap are not queued). On timeout, provider error, retired service or the cap, the upload still succeeds, the file is kept and `vectorized` is `false`: it is sent whole. A timed-out job cannot be killed; it keeps its slot until it returns.
- **Files sent with a turn.** Files in the `files[]` form field of `/stream` or `/messages` are indexed only if the conversation already has a temp silo; otherwise they are sent whole. The UI always uploads first.
- **Removal.** The temp silo, its repository and vectors are removed when the conversation is deleted or reset and when the user is deleted (their Chat conversations, files, temp silos and threads go with them). A periodic sweep in the file cleanup worker (`sweep_orphan_chat_temp_repositories`, repositories older than 15 minutes, 20 per pass) removes temp repositories of internal-chat conversations that no longer exist.
- **Privacy.** With a default embedding service set, every member's Chat attachments are sent to that embedding provider (which can be a platform-wide system service), and their chunks are stored in the App's vector database until the conversation is reset or deleted.
- **Lifecycle.** An embedding service used as an App default appears in its "used by" view (`apps_using_as_default`) and in lifecycle warnings (`warnings_for_app`, `via: "app default"`).

### Error contract

| Status | When | Body |
|--------|------|------|
| 403 | Not a member of the App (from the role check) or the App is frozen (turns, uploads, options, defaults, create) | `{detail}` |
| 404 | Anything not owned by the caller: another user's conversation or file, a conversation of another App, a missing or cross-App resource id | `{detail: "Resource not found", error_code: "NOT_FOUND"}` |
| 409 | A selected model (or a silo's embedding service) is retired | `{detail, error_code: "SERVICE_RETIRED"}` |
| 409 | `/stream`, `/messages`: a turn of this conversation is still in flight. Header `Retry-After: 5`; nothing is written | `{detail, error_code: "CONVERSATION_BUSY"}` |
| 413 | `/stream`, `/messages` and the file upload: request body larger than the App's file size limit (`max_file_size_mb`; 0 = unlimited; checked from `Content-Length` by `enforce_file_size_limit`) | `{detail}` |
| 422 | Malformed JSON in `selection`, `file_references` or `search_params`; invalid body | `{detail}` (the input is never echoed) |

A frozen App (tier downgrade) keeps existing conversations listable, readable, renamable and deletable, and file list/delete/download work; it takes no new activity.

## Isolation guarantees

- Conversations, files, turns, defaults and LangGraph threads are per user. Another member, administrator, owner or omniadmin of the App cannot read, list, rename, reset, delete or send to someone else's Chat conversation: it is a 404 indistinguishable from a missing one. This includes an omniadmin who is a collaborator of the App. An omniadmin who is not a collaborator gets the App's 403, like any other non-member.
- The `app_id` of every row written comes from the conversation's internal agent, never from request input. Only an allow-listed subset of the caller's context (`user_id`, `email`, `oauth`, `token`) reaches a turn, so API-key, billing, scheduled-task or channel overrides can never leak in.
- A Chat conversation id does not work on the playground or the public API (404), and the Chat never falls back to the shared `default` session or the agent-wide thread.
- The shared agent row is never written during a turn. Concurrent turns of different users with different selections run on independent configs.

## Privacy of content

For Chat turns, failure handling keeps message content out of the turn failure logs and out of the metrics error text:

- **Turn failure logs** carry the exception class chain, `agent_id`, `conversation_id`, a short `correlation_id` and traceback frames (file, line, function), not the provider's error text nor `str(exc)`. Helper: `backend/utils/turn_failure_log.py`.
- **Other warnings on the Chat path** are not covered by that helper. For example, when MCP tools are unavailable or time out, `backend/tools/agentTools.py` still logs the root cause, which can include server-side detail (such as an MCP server's address or error) but not the user's message.
- **Metrics**: the error text is kept as is only for codes the platform builds itself (timeout, cancelled, service retired, `approval_*`). Otherwise the error dashboard stores the exception class chain with `correlation_id=<id>`, so an entry can be matched to its log line, or `<code> (details withheld)`. Tool-call errors are stored as `Tool error (details withheld)`.
- Other channels (playground, public API, ...) log and record exactly as before.
- With **LangSmith** enabled for the App, Chat prompts and answers are sent to the App's LangSmith project like any other agent run. The LangSmith API key can be changed only by the App owner, so the owner controls where Chat prompts are traced (see [App settings permissions](#app-settings-permissions)). Each trace carries selection metadata (`chat_app_id`, `chat_ai_service_*`, `chat_silo_*`, `chat_skill_*`, `chat_mcp_config_*`; ids and names only).

## Behaviours and limits

- **No approvals, no PII rules.** Per-agent human-approval and PII rules of normal agents do not apply in the Chat. Tools that would need approval (for example from an MCP server) cannot run: the Chat cannot answer approvals, so the pause is rejected on the spot, the tool is not executed and the conversation is not left paused (`hitl_approval` ends `cancelled` / `channel_not_interactive`). The expiry worker applies the same rule to a Chat pause it finds stuck after a crash.
- **MCP token forwarding.** The caller's token is forwarded to the selected URL-based MCP servers, exactly as in the playground.
- **MCP is all-or-nothing.** If one selected server cannot be reached, none of the selected MCP tools load and the turn warns for all selected MCP configs.
- **Stale resources.** Resources removed or retired since they were selected are dropped with a warning (stored selections) or rejected (404 / 409) when sent explicitly in a turn.
- **Frozen tier.** Frozen silos and skills are not selectable; a frozen App rejects new activity with 403.
- **Unsupported attachments** on a turn are ignored, as in the playground.
- **File links.** Download links from the download endpoint expire after 5 minutes (`DOWNLOAD_LINK_TTL_SECONDS = 300`). Images referenced in an answer as `file://{file_id}` request a download link once, when the message is rendered, and are not refreshed, so a displayed image can stop loading after five minutes until the conversation is reopened. File download buttons request a fresh link on each click.
- **Detached turns.** A turn keeps running server-side if the user switches conversation or leaves the page; its answer is in the conversation on return.
- **One turn at a time.** A second message to a conversation with a turn in flight is refused with 409 `CONVERSATION_BUSY` and nothing is stored for it (see [Turns](#turns)). In the UI the user sees a translated message (`appChat.transportErrors.conversationBusy`) and the text is put back in the message box.
- **Attachments.** Indexed or sent whole depending on the App's default embedding service (see [Attachment indexing](#attachment-indexing)); a notice on the Chat page says when they are not indexed (administrators get a link to the App settings, other members are told to ask an administrator or owner).
- **Reset race.** Right after a reset, `message_count` / `last_message` may still show the answer of a turn that started before the reset.

### Known limits

- Rare case: if the server process stops while it is rejecting an approval, a conversation that uses a provider other than OpenAI may fail on every message until it is reset (the thread keeps a tool call without an answer). A normal failure closes such calls; a process stop cannot.
- Uploaded originals under `data/tmp/conversations/` are not removed by the cleanup worker; for Chat uploads they are deleted with the file, on reset and on conversation delete (see [Attachment folders from older builds](#attachment-folders-from-older-builds)).
- **Images and vision.** The platform has no per-model vision flag and the Chat never filters the history by capability. Once an image is attached, it is sent with every later turn (all the conversation's files are attached again unless the request sends `file_references=[]`, which the Chat page never does), so switching to a model without vision fails those turns (the provider rejects them; the user sees the generic error). Send an explicit empty file selection, or start a new conversation, to continue on such a model.
- **Models without tool support.** Every Chat turn binds at least one base tool, so a model that cannot take tools fails every turn, even with no silo, skill or MCP selected.
- **Images with `AICT_BASE_URL`.** When `AICT_BASE_URL` is set, images are sent as signed URLs. A "Custom" (Ollama) model probably cannot read them (inferred from the Ollama converter, which expects base64; not confirmed against a real Ollama).
- **Small windows.** If the most recent 20 messages (`keep`) alone exceed a small model's window, the turn still fails; summarization cannot shrink them. Models without a profile (Ollama, Azure AI) use the 32k trigger even if their real context is smaller.
- **Summary written, answer failed.** The summary is stored as its own step, so if the model call after it fails, the conversation's stored history is already compacted into that summary (the turn row and answer do not exist).
- **User image marker.** In the history, a user message that had an inline (base64) image shows a raw `[IMAGE:<hash>]` marker: placeholders are resolved to images only for assistant messages (`conversation_service.py`), and the marker is shared with the playground.
- **Not validated against real providers.** The tests do not call any provider API: provider-side validation (for example Anthropic thinking signatures, OpenAI Responses item pairing, role alternation, real token accounting, image size limits) is not covered. See [Testing](#testing).
- After a server crash in the middle of a turn, that conversation can answer "busy" (409) for several minutes, until its marker expires (11 minutes with the default run timeout). Right after a stream is cut by the client there is a brief window before the previous turn has fully stopped in which a new message can also be answered "busy".
- **No cap on temp silos (accepted risk).** There is deliberately no limit on how many temporary silos a user can create through Chat conversations (one per conversation that has an indexed attachment); this is a product decision. In practice it is bounded by the App's file size limit (413), by at most two concurrent indexing jobs per embedding service, and by the 60 s indexing limit. Temp silos do not count against the tier silo quota and are never frozen.
- Attachments sent whole (no default embedding service, or the file was not indexed) can exceed the model's context window.
- Azure AI and Google (AI Studio and Vertex AI) embedding clients have no client-side timeout (see `AICT_EMBEDDING_REQUEST_TIMEOUT_SECONDS`); the Chat still gives up after 60 s, but the abandoned call keeps its indexing slot until it returns.
- Playground, public API and marketplace uploads still index inline, with no time limit (unchanged).

## Behaviour change outside the Chat

- Playground and public API file/chat endpoints now answer **404 `Conversation not found`** when given a `conversation_id` that is not the caller's for that agent (same user, or same API key). The check applies to agents with memory; for agents without memory the id is only a grouping label for ephemeral files. Previously a foreign id was accepted. Helper: `ChatAttachmentService.require_owned_conversation`.
- **Temporary silos are hidden.** The temp silo of a conversation (playground and Chat), its repository (type `playground_media`) and its metadata output parser no longer appear in silo, repository or output-parser lists, pickers, exports or "used by" views, internal or public. Addressed by id they answer 404 like a missing one; a normal agent cannot be pointed at one; imports cannot bind to one by name; a repository cannot be created with the reserved type. API consumers that listed silos or repositories will no longer see them. The partial index `ix_Repository_silo_id_temp` (migration `ichat002`) serves the visibility lookup.

## App settings permissions

Administrators and above can now update the App settings (`PUT /internal/apps/{id}`; previously only the owner could save). The **LangSmith API key stays owner-only**: an administrator who tries to change or clear it gets 403, and the settings page shows the field read-only for them. A settings update that omits the key (or sends back the masked value) now **keeps** the stored key; clearing it requires sending it empty explicitly, as the owner. Deleting the App, transferring ownership and managing collaborators are unchanged. See [Role Authorization](../reference/role-authorization.md).

## Operations

### Migrations `ichat001` and `ichat002`

Both are additive. `ichat001` revises `chatfiltmerge003`; `ichat002` revises `ichat001` and is the current head.

**`ichat002`**: `chat_conversation_state.busy_token` and `busy_until` (nullable), `App.default_embedding_service_id` (nullable, FK `App_default_embedding_service_id_fkey` to `embedding_service`, `ON DELETE SET NULL`) and the partial index `ix_Repository_silo_id_temp` on `Repository(silo_id)` where `type = 'playground_media'`. No backfill: existing Apps have no default embedding service, so their Chat attachments are sent whole until an administrator sets one.

**`ichat001`**:

- `Agent.kind` (`'standard'` default) with `ck_agent_kind`, `ck_agent_internal_chat_unexposed`, `ck_agent_internal_chat_has_app` and the partial unique index `uq_agent_internal_chat_per_app`.
- `INTERNAL_CHAT` added to the `conversationsource` and `agent_execution_caller_type` enums (`ApprovalChannel` is a string column; Python-only).
- Tables `conversation_turn`, `chat_user_default`, `chat_conversation_state` (foreign keys and delete rules in [Defaults and conversation state](#defaults-and-conversation-state)).

Rollout: deploy the backend before the frontend library; the menu entry appears when a client project updates `@lksnext/ai-core-tools-base` and can be hidden there (see [Hide the menu entry](#hide-the-menu-entry-client-projects)).

### Rolling back

Run the downgrade **before** rolling back the image; an older build does not know the new enum values or `Agent.kind`. Removing both Chat migrations takes two steps back from `ichat002`:

```bash
alembic downgrade ichat001           # reverts ichat002
alembic downgrade chatfiltmerge003   # reverts ichat001
```

(`alembic downgrade chatfiltmerge003` alone runs both in order.) Downgrading `ichat002` drops the busy markers (transient) and the Apps' default embedding service (configuration, lost: set it again after upgrading). The `ichat001` downgrade is destructive by design: it drops the three tables, deletes all Chat conversations and the internal agents (with their approvals and execution events), relabels remaining `agent_execution_event` rows from `INTERNAL_CHAT` to `INTERNAL_PLAYGROUND`, and recreates both enum types without the label. It rewrites `Conversation` and `agent_execution_event` under `ACCESS EXCLUSIVE` locks: use a maintenance window. It does not purge LangGraph checkpoint rows, uploaded files, or the temporary silos, `playground_media` repositories and vectors of the deleted conversations; they stay behind, are not reachable from the UI and are not removed by the orphan sweep (it needs the internal agent, which the downgrade deletes). Remove them by hand if needed.

### Attachment folders from older builds

Persistent uploads (agents with memory and a `conversation_id`) keep the original file under `data/tmp/conversations/{conversation_id}/`, with no user or App in the path, and its metadata under `data/tmp/persistent/agent_{agent_id}_user_{user_id}_app_{app_id}_conv_{conversation_id}/`. Conversation ids are global. Before the ownership check described above, the playground and public API accepted any `conversation_id`, so a deployment that ran an older build can hold files in a `conversations/{id}/` folder that were written by a user who did not own conversation `{id}`, and a legitimate conversation's folder may contain them.

The cleanup worker (`backend/services/file_cleanup_worker.py`) sweeps only `data/tmp/ephemeral/`, `data/tmp/uploads/` and `data/tmp/persistent/` (the latter after `TMP_PERSISTENT_TTL_DAYS`). It never touches `data/tmp/conversations/`. Originals there are removed only when the file is removed, when the conversation is reset or deleted (Chat conversations, which delete the folder), or when the agent is deleted. Nothing expires them by age, so such files stay until deleted by hand.

One-off cleanup (optional): inspect `data/tmp/conversations/*` of deployments that ran an older build and delete files you cannot attribute to the conversation's owner. There is no automated check for this.

### Observability

- Dashboards: the `INTERNAL_CHAT` channel appears in platform and App breakdowns by `channel` ([Agent Metrics](../guides/agent-metrics.md)). Chat runs report the model that answered (the turn's AI service), not the internal agent's own configuration.
- Logs: one INFO line per turn (`internal_chat.turn app_id=... conversation_id=... user_id=... ai_service_id=... silo_id=... skill_ids=... mcp_config_ids=...`). IDs only.
- Failures: search the log for the `correlation_id` shown in the metrics error message.

### Environment variable

| Variable | Default | Description |
|----------|---------|-------------|
| `AICT_EMBEDDING_REQUEST_TIMEOUT_SECONDS` | `120` | Client-side timeout of embedding calls (read when the client is built; retries are not changed). Applied to OpenAI, MistralAI, Custom/HuggingFace, Ollama and AWS Bedrock embedding clients. **Not** applied to Azure AI and Google (AI Studio and Vertex AI), whose clients expose no timeout. Source: `backend/tools/embeddingTools.py` |

Related, already existing: `AICT_AGENT_RUN_TIMEOUT_SECONDS` (default 600) sets the busy-marker expiry (`+ 60 s`).

## Hide the menu entry (client projects)

The entry is part of the default App navigation (`appNavigation`, `/apps/:appId/chat`). To hide it in a client project, in `src/config/clientConfig.ts`:

```typescript
navigation: {
  remove: ['/apps/:appId/chat']
}
```

This removes the **menu entry only**. The routes `/apps/:appId/chat` and `/apps/:appId/chat/:conversationId` stay registered and reachable by URL, and the backend endpoints stay available to every App member. See [Client Project Setup](../guides/client-setup.md#navigation-customization).

## Testing

- Backend: `tests/integration/internal_chat/` (exclusion from every surface, functional API, isolation of state, attachments, router wiring) with shared fakes and the world fixture in `_chat_support.py`. Fakes: the LLM (per AI service), the retriever tool, the MCP client and the metrics write; everything else (router, service, resolver, execution stack, checkpointer, PostgreSQL) is real.
- LangGraph checkpoint tables are not part of `Base.metadata`, so they survive the test schema drop. Assertions on threads must be relative to a baseline taken at the start of the test, not absolute counts.
- Concurrency: `test_chat_isolation_concurrency.py` runs overlapping turns through `httpx.AsyncClient` + `ASGITransport` with one session per request (`get_db` not overridden, data committed and purged afterwards) and a fake model that parks every call on per-turn gates, so overlap is deterministic and asserted, not timed.
- Model switch: `test_chat_model_switch.py` switches provider, service and model between turns of one conversation (summarization, small windows, images, tools, retired models, failure paths, the stamp). It runs the router, services, real checkpointer, real `SummarizationMiddleware`, the real normaliser and PostgreSQL; only the LLM boundary is replaced by `_provider_sim.py`, subclasses of the real LangChain model classes that validate the request with each provider's own installed converter and answer with the message shapes the real adapters produce. **No real provider API is called**: "accepted" means the installed converter takes the messages and tool calls are paired, not that the API would. Capability, context-window and error rejections are hand-written rules. Unit tests: `tests/unit/tools/middleware/test_history_normalizer.py` and `test_summary_input_bound.py`.
- Temp silo visibility: `test_chat_temp_silo_visibility.py` includes a **route-enumeration guard**. A new route that takes a silo or repository id must pass it (hidden temp silos answer 404 like a missing one).
- Frontend: Vitest + Testing Library render tests in `frontend/tests/ui` (`npm run test:ui`).

See [Testing Guide](../testing/README.md).

## See Also

- [Chat in an App](../guides/chat-bot/app-chat.md) — end-user guide
- [Agent System](agent-system.md) — agent execution, memory, skills
- [MCP Integration](mcp-integration.md) — MCP configs consumed as tools
- [Internal API](../api/internal-api.md) — endpoint overview
- [Human approval in the public API](../guides/human-approval.md) — why the Chat does not take part
- [Agent Metrics](../guides/agent-metrics.md) — channels and dashboards
