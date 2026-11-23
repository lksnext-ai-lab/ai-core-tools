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
| Migrations | `ichat001`, `ichat002`, `ichat003`, `ichat004` |
| Metrics channel | `INTERNAL_CHAT` |
| Env vars | `AICT_CHAT_RECURSION_LIMIT` ([step limit](#step-limit)), `CHAT_MAX_FILES_PER_TURN` and `ATTACHMENT_INDEXING_TURN_BUDGET_S` ([attachments per turn](#attachment-indexing)); also `AICT_EMBEDDING_REQUEST_TIMEOUT_SECONDS` (embedding client timeout) and the `SANDBOX_*` variables of the [code interpreter](#code-interpreter), see [Operations](#operations) |

## The hidden internal agent

`Agent.kind` is `'standard'` (default) or `'internal_chat'`. The internal agent:

- is invisible in agent lists, agent forms (as a tool candidate), export/import, the marketplace, MCP servers, A2A and the public API (including the OpenAI-compatible endpoints);
- answers **404** on every non-Chat surface (agent detail/update/delete, `/chat/{id}/...`, `/files/{id}/...`, OCR, the generic `/internal/conversations` router, public API), indistinguishable from a missing agent;
- is protected at database level by constraints: it cannot be a tool, A2A-enabled, published to the marketplace or have `enable_code_interpreter` set (`ck_agent_internal_chat_unexposed`, unchanged), must belong to an App, and there is at most one per App (`uq_agent_internal_chat_per_app`). The Chat's code interpreter does not go through that flag: the agent keeps `enable_code_interpreter = false` and the interpreter is enabled only by the turn config (see [Code interpreter](#code-interpreter)).

What a Chat turn does **not** use from the agent: tool associations, server tools, output parser, the agent's own code interpreter flag and sandbox service, agent middlewares (so no per-agent PII rules and no human-approval rules), chat filters and the skill router. Memory is always on (LangGraph PostgreSQL checkpointer); history is summarized by the default `SummarizationMiddleware`, built with the turn's own model, and adapted to that model on every call (see [Switching models between turns](#switching-models-between-turns)).

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

## Code interpreter

The Chat can run code (the sandbox REPL tools and the `Bash` and file builtin tools such as `Read`, `Write` and `Edit`) in a sandbox, so selected skills with bundled scripts can run them. It is **off by default** and is an App-level opt-in. It uses the same sandbox providers (OpenSandbox, Daytona, E2B) as agents; see [Sandbox provider RFC](rfc-sandbox-providers.md).

### Opt-in switch

| Aspect | Value |
|--------|-------|
| Column | `App.chat_code_interpreter_enabled` (Boolean, NOT NULL, server default `false`), migration `ichat003` |
| API | `chat_code_interpreter_enabled` in the App read (`GET /internal/apps/{id}`, `viewer`) and update (`PUT`, `administrator`) payloads |
| Update semantics | Omitted keeps the stored value; an explicit `null` is a 422 (it is a boolean, not nullable) |
| Who changes it | Administrators and above, in the App settings (checkbox "Allow running code in the Chat", next to the default sandbox service). Below administrator the settings page shows it read-only |

The hidden agent is not touched: it keeps `enable_code_interpreter = false` and the database CHECK is unchanged. Enablement comes only from the turn config (`ResolvedChatConfig.sandbox_enabled`, read by `_effective_surface` in `backend/tools/agentTools.py`).

### Which sandbox service a turn uses

One function decides it for both `GET /options` and the turn, `ChatSelectionResolver.code_interpreter_service` (`selection_resolver.py`), so the UI state and the behaviour cannot diverge:

| Switch | App default sandbox service | Result |
|--------|-----------------------------|--------|
| off | any | No code interpreter (`disabled_in_app_settings`) |
| on | set, active or deprecated | That service |
| on | set, retired | No code interpreter (`sandbox_service_retired`), **no fallback** to the system default |
| on | set, but its provider is not registered or not in `SANDBOX_ALLOWED_PROVIDERS`, or its row cannot be read | No code interpreter (`sandbox_provider_unavailable`) |
| on | not set | The **system default**: `SANDBOX_DEFAULT_PROVIDER` with the environment credentials and no service id, as for agents. Provider not registered or not allowed: `sandbox_provider_unavailable` |

A database error while reading the App's sandbox settings means no code interpreter (`sandbox_provider_unavailable`), never the system default. The turn never fails because of it: it runs without the interpreter. The hidden agent's relationships are never consulted; the service is loaded by id.

`GET /options` carries `code_interpreter: {enabled, reason}`, with `reason` one of `disabled_in_app_settings`, `sandbox_service_retired`, `sandbox_provider_unavailable` (`null` when enabled).

The options can say `enabled: true` while a turn still runs without code. With the system default the platform cannot know whether the sandbox host is running (for example the `opensandbox` compose profile is not up): the provider object builds, the first tool call fails to create the sandbox, the tool returns a generic error and the answer is kept. The truth for a turn is `turn_config.code_interpreter` (boolean, `POST /messages` -> `metadata.turn_config`, `/stream` -> `metadata` event): `false` when the turn degraded while it was prepared and, on `/messages`, also when the first tool call could not create the sandbox. On `/stream` the `metadata` event is sent before the run, so a sandbox that cannot be created at the first tool call is not visible there.

What the Chat page shows (`codeInterpreterNotice` in `frontend/src/components/chat/chatSelection.ts`): for `disabled_in_app_settings` a notice only while at least one skill is selected (only skills carry scripts); for `sandbox_service_retired` and `sandbox_provider_unavailable` always. The text says that skills with scripts load but their scripts will not run.

### Sandbox scope and who can use it

- **One sandbox per conversation**, key `conv_{agent_id}_{conversation_id}`, the platform never shares a sandbox key between conversations or users (for OpenSandbox, see accepted risk 1 below). The key is asserted in `_prepare_turn` (`InternalChatSessionError` otherwise).
- Open to **every member of the App, Viewers included**. There is no approval before code runs: the Chat cannot ask (see [Behaviours and limits](#behaviours-and-limits)).
- Created lazily at the first tool call of a turn. Destroyed when the conversation is **reset**, **deleted**, the **user is deleted** or the member is **removed from / leaves the App** (`internal_chat/user_cleanup.py`).
- Skills with bundled scripts always load in the Chat; their scripts run only when the interpreter is on.
- A cached sandbox keeps the service it was created with until it expires or the conversation is reset, except that a change of the App default (App default <-> system default, or another provider) is detected on the next turn and the old sandbox is destroyed and recreated.

### Limits (Chat only)

The session limits and eviction are Chat only (agents keep their previous capacity behaviour) and are counted per process (`backend/services/sandbox_session_service.py`); the Bash cap and background-shell refusal are Chat only (`backend/tools/sandbox/chat_guard.py`). The execution budget is per turn and also applies to agents (REPL executions only; in the Chat it is shared with `Bash`).

| Limit | Setting (default) | Behaviour |
|-------|-------------------|-----------|
| Live sandboxes per user | `SANDBOX_MAX_SESSIONS_PER_USER` (3) | `0` = unlimited |
| Live sandboxes per App | `SANDBOX_MAX_SESSIONS_PER_APP` (10) | `0` = unlimited |
| Eviction | `SANDBOX_EVICT_MIN_IDLE_S` (60) | Over a limit, only the **requester's own** sessions with no active use, no lease and idle for at least this long are evicted (least recently used first). Otherwise the requester gets a capacity error and must wait. Another user's sandbox is never evicted, so a user can be left without a sandbox while others hold the App's 10: by design |
| Turn lease | - | A Chat turn holds a lease on its sandbox from its first use until the turn ends, so it is neither evicted nor reaped mid-turn |
| Executions per turn | `SANDBOX_MAX_EXECUTIONS_PER_TURN` (5) | Per turn. One budget shared by the REPL and `Bash` in the Chat (REPL only for agents); `0` refuses every execution; beyond the budget the tool answers `[Execution budget exceeded: N executions per turn]`. `Write`/`Edit` do not count |
| Bash timeout | `SANDBOX_CHAT_BASH_MAX_TIMEOUT_S` (60) | Ceiling of one `Bash` call |
| Background shells | - | `run_in_background` is refused with a message |
| Idle timeout | `SANDBOX_IDLE_TIMEOUT_S` (120) | An idle sandbox is destroyed together with `work/` and any installed packages. Only `output/` files already pulled to local storage survive. A recreated sandbox receives only the current turn's uploads |

Only `SANDBOX_MAX_SESSIONS_PER_USER` and `SANDBOX_MAX_SESSIONS_PER_APP` (and the pull concurrency below) are **per backend process**, not global across workers (the default deployment runs 2 workers). The execution budget and the output-file caps are per turn.

### Output files

Files the code writes under `output/` are pulled from the sandbox into the turn's local output folder and delivered with the answer. This code is shared by **all agents and the Chat** (`backend/services/sandbox_output_pull.py`):

| Limit | Setting (default) |
|-------|-------------------|
| Files per turn | `SANDBOX_PULL_MAX_FILES` (20) |
| Size of one file | `SANDBOX_PULL_MAX_FILE_BYTES` (50 MB) |
| Total size per turn | `SANDBOX_PULL_MAX_TOTAL_BYTES` (100 MB) |
| Time budget of the whole pull | `SANDBOX_PULL_TIME_BUDGET_S` (20 s; `0` = no budget) |
| Pulls at once, per process | `SANDBOX_PULL_MAX_CONCURRENT` (2; a pull that finds every slot busy is skipped at once, not queued) |

`0` means "no cap" for the three count/size settings. Do **not** set both size caps to `0`: the pull then reverts to an unbounded read of each file. With at least one size cap set, every read is bounded (the provider stops after cap + 1 bytes) and the size reported by `stat` inside the sandbox is only a pre-filter.

Other rules: hidden files and unsafe names (absolute paths, control characters, longer than 200 bytes) are skipped, symlinks and non-regular files are skipped, colliding base names become `x-2.txt`, `x-3.txt`. A slow, failing or oversized pull never fails the turn and the answer text is never changed.

Skipped files are reported, as a count:

- **Chat:** a turn warning `{"kind": "sandbox_output", "id": <count>}` in `turn.warnings` (the `id` is a **count**, not a resource id; it is the number of skipped files when any file was skipped, and 1 only when nothing was skipped but the pull itself failed or ran out of time). The Chat page shows it translated (`appChat.warnings.sandbox_output`).
- **Agents:** `metadata.outputs_skipped` (integer, only when > 0): the `usage` object of `POST /public/v1/chat/{agent_id}/call`, and `outputs_skipped` in the `data` of the SSE `done` event of `/call/stream`. See [Public API](../api/public-api.md#response-fields).

An **E2B** sandbox needs the private streaming client of the pinned E2B SDK (`files._envd_api.stream`) for the bounded read. If the installed SDK does not have it, the provider refuses and no output files are delivered from E2B sandboxes (fails closed, counted as skipped).

### Accepted risks

Read these before turning the switch on for an App. They are deliberate and tracked, not closed:

1. **Sandboxes of a self-hosted OpenSandbox server are not isolated from each other.** Code run by one member can reach other members' sandboxes on the same server, across Apps (the exec daemon of each sandbox has no authentication). Whether E2B and Daytona isolate sandboxes from each other has not been verified by this project. See `docker/README.md`, section "OpenSandbox: exposición y mitigaciones".
2. **Outbound network is on by default** with OpenSandbox: internet, services published on the Docker host and the LAN are reachable from sandbox code, unless the hardened override `docker-compose.sandbox-hardened.yaml` is used (no egress; Docker Engine >= 28; `pip install` stops working).
3. **With no App default sandbox service, the system default sandbox provider is used**: its credentials are used and its usage is charged to the platform (for a self-hosted OpenSandbox, the host's capacity), and its network access applies, for any App whose administrator turns the switch on.
4. **The Chat cannot ask for approval before running code.**
5. **Memory and disk exhaustion by a member (accepted as a known risk for this release; tracked as follow-up).** A member can still exhaust backend memory through two paths: a sandbox with a huge number of files makes the output listing be parsed whole, and a command that prints without end accumulates its stdout in memory until it ends. Both exist for agents too; the Chat exposes them to every member of an App that opted in. No disk quota is configured in `docker/opensandbox/sandbox.toml` for OpenSandbox containers, so a member can also fill the Docker host's disk.

The session limits (above) are per process and do not add up across workers.

## API

Base: `/internal/apps/{app_id}/chat`. Auth is the normal internal session; every route requires at least `viewer`.

### Options and defaults

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/options` | `ai_services`, `silos` (with `source_type`: `repository`, `domain`, `sharepoint`, `silo`), `skills`, `mcp_configs`, `default_selection`, `default_warnings`, `has_usable_model`, `attachment_indexing` (`{enabled, reason}`; `reason` is `null`, `"no_default_embedding_service"` or `"embedding_service_retired"`, see [Attachment indexing](#attachment-indexing)), `code_interpreter` (`{enabled, reason}`; `reason` is `null`, `"disabled_in_app_settings"`, `"sandbox_service_retired"` or `"sandbox_provider_unavailable"`, see [Code interpreter](#code-interpreter)) |
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

Reset rotates the conversation's `session_id` (new LangGraph thread) and bumps `generation` in one transaction, then removes the old thread, the turn rows, the attachments that existed before the reset, and temporary media. Reset and delete also destroy the conversation's code interpreter sandbox (on a dedicated executor, bounded to 10 s by the module constant `SANDBOX_DESTROY_TIMEOUT_S` in `chat_service.py`, not an environment variable; if the provider does not confirm on reset, the persisted sandbox state is kept so the reaper can still find it). A turn that was running during a reset or delete persists nothing and drops its own thread.

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

**Lost marker.** The turn renews the marker before the model runs and during its slow steps. If the renewal finds the marker gone (someone else may now be running the conversation), the turn aborts with the same **409** `CONVERSATION_BUSY` (`Retry-After: 5` on `/messages`; SSE `error` event `conversation_busy` on `/stream`) instead of continuing (`InternalChatService.renew_turn`).

**Database connection.** The request's pooled connection is released before the slow waits (file processing and attachment indexing, the model run, and the destroy/listing awaits of delete and reset), so a slow turn does not hold a connection (`InternalChatService._release_db_connection`).

#### Step limit

Every model call and every tool call is a graph step. A turn that exhausts its steps ends with the error `STEP_LIMIT_REACHED` instead of an answer.

| Setting | Default | Applies to |
|---------|---------|------------|
| `AICT_CHAT_RECURSION_LIMIT` | `100` | Chat turns only (they retrieve knowledge, load skills and run code, so they spend more steps) |
| `AICT_AGENT_RECURSION_LIMIT` | `50` | Every other agent run (playground, public API, ...) |

Both are read once at startup (`backend/tools/agentTools.py`); a value that is not an integer or is below 1 logs a warning and falls back to the default.

**Sizing.** The Chat's middleware chain costs about 3 graph steps per model call that uses tools, so `AICT_CHAT_RECURSION_LIMIT=100` allows about **33** tool-using model calls per turn, and the agent default of 50 about **16**. Tests cut a turn at both points of the graph (right after the model node and right after the tools node) with parallel tool calls: the next turn answers every tool call once and no pending tool runs silently (`test_chat_step_limit.py`).

| Route | Result |
|-------|--------|
| `POST /messages` | HTTP **422** `{detail, error_code: "STEP_LIMIT_REACHED"}` |
| `POST /stream` | SSE `error` event `{message, code: "step_limit_reached"}` |

The text is fixed (never built from the exception). What the Chat does with such a turn:

- **Keeps** the conversation (even one created by that very request), its checkpoint, its files and its sandbox, and releases the busy marker.
- Writes **no turn row** (`conversation_turn`) and no assistant message.
- Runs the bounded [output pull](#output-files) itself, so the files the code already generated are delivered and listed.
- The user can write a follow-up such as "continue": the next turn works on the same checkpoint (covered by tests on both routes).
- Metrics record the error code `STEP_LIMIT_REACHED`.

On the Chat page the error is shown translated (`appChat.transportErrors.stepLimitReached` in the frontend locale files, "write continue to let it carry on").

Logs: every tool call of a Chat turn writes one INFO line, `chat tool=<name> n=<i> outcome=<ok|error:<Class>> ms=<d> conversation_id=<id> turn=<corr>` (`backend/tools/middleware/chat_tool_log.py`; no arguments, no content), and reaching the limit writes one summary line with the number of model calls and tool calls per tool. The playground and the public API are unchanged: they still surface the same `GraphRecursionError` through their generic error handling.

**SSE events** (`data: {"type": ..., "data": {...}}`; lines starting with `:` are heartbeats):

| Event | Content |
|-------|---------|
| `metadata` | First event. `conversation_id`, `has_memory`, and `turn_config`: `{ai_service: {id, name}, silo: {id, name} \| null, skills: [{id, name}], mcp_configs: [{id, name}], warnings: [{kind, id}]}`. `warnings` lists selected MCP configs skipped for this turn. `code_interpreter` (boolean) means "configured and not degraded while the turn was being prepared" (the event is built before the run; see [Code interpreter](#code-interpreter)). The internal agent's id, name and the thread's `session_id` are never sent |
| `token` | `{content}` text chunk |
| `tool_start`, `tool_end` | Tool activity |
| `done` | `{response, conversation_id, files, status: "completed", assistant_message_id, turn}`. `turn` is the `ChatTurnInfo` snapshot (`turn_index`, `ai_service_*`, `silo_*`, `skills`, `mcp_configs`, `created_at`, `warnings`) or `null` if it could not be persisted (the answer is still valid). `turn.warnings` also reports selected MCP configs whose tools failed to load, and `{kind: "sandbox_output", id: <count>}` when output files of the code could not be delivered (`id` is a count of files) |
| `error` | `{message}`; for a retired service `{message, code: "service_retired"}`; for a lost busy marker `{message, code: "conversation_busy"}`; at the step limit `{message, code: "step_limit_reached"}` (see [Step limit](#step-limit)) |

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
- **Per-turn bounds.** `CHAT_MAX_FILES_PER_TURN` (default `10`, `0` = unlimited): one message may carry at most this many files, counting new uploads plus `file_references`; beyond it the request is a **422** `{detail, error_code: "TOO_MANY_FILES"}` (on `/messages` and on `/stream`) before anything is claimed or written. The Chat page shows `appChat.transportErrors.tooManyFiles`, the typed text returns to the message box and the files stay attached. `ATTACHMENT_INDEXING_TURN_BUDGET_S` (default `120`, `0` = unlimited): total time the indexing of one turn's files may take, in addition to the 60 s per file; keep it well below `AICT_AGENT_RUN_TIMEOUT_SECONDS`. Files over the budget are sent whole. The request's database connection is released before indexing waits and the files are committed first, so slow indexing holds no pooled connection.
- **Removal.** The temp silo, its repository and vectors are removed when the conversation is deleted or reset, when the user is deleted (their Chat conversations, files, temp silos and threads go with them) and when the member is removed from the App or leaves it (see [Member removal](#member-removal)). A periodic sweep in the file cleanup worker (`sweep_orphan_chat_temp_repositories`, repositories older than 15 minutes, 20 per pass) removes temp repositories of internal-chat conversations that no longer exist. It matches the repository name against the exact prefix `_playground_{agent_id}_` (`left(name, length(prefix)) = prefix`, not `LIKE`, because `_` is a `LIKE` wildcard: agent 3 would otherwise also match agents 30-39, 300-399, ...).
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
| 422 | `/stream`, `/messages`: more files in one message than `CHAT_MAX_FILES_PER_TURN` (uploads + references). Raised before any claim or stream starts, so on `/stream` it is a plain HTTP 422 body, not an SSE event | `{detail: "Too many files in one message (maximum N)", error_code: "TOO_MANY_FILES"}` |
| 422 | `/messages`: the turn ran out of steps ([Step limit](#step-limit)); the conversation is kept | `{detail, error_code: "STEP_LIMIT_REACHED"}` |

A frozen App (tier downgrade) keeps existing conversations listable, readable, renamable and deletable, and file list/delete/download work; it takes no new activity.

## Isolation guarantees (database and API level; see the Code interpreter section for the sandbox caveat)

- Conversations, files, turns, defaults and LangGraph threads are per user. Another member, administrator, owner or omniadmin of the App cannot read, list, rename, reset, delete or send to someone else's Chat conversation: it is a 404 indistinguishable from a missing one. This includes an omniadmin who is a collaborator of the App. An omniadmin who is not a collaborator gets the App's 403, like any other non-member.
- The `app_id` of every row written comes from the conversation's internal agent, never from request input. Only an allow-listed subset of the caller's context (`user_id`, `email`, `oauth`, `token`) reaches a turn, so API-key, billing, scheduled-task or channel overrides can never leak in.
- A Chat conversation id does not work on the playground or the public API (404), and the Chat never falls back to the shared `default` session or the agent-wide thread.
- The shared agent row is never written during a turn. Concurrent turns of different users with different selections run on independent configs.

### Member removal

When a collaborator is **removed** from an App or **leaves** it (`AppCollaborationService.remove_collaborator` / `leave_app_collaboration`), that member's Chat data **in that App** is deleted with the collaboration. It reuses the two phases of user deletion (`internal_chat/user_cleanup.py`, now with an `app_id`):

1. In the same transaction as the removal: the member's Chat conversation rows of that App (state and turn rows go by foreign-key cascade).
2. After the commit, best effort: temp silo, repository and vectors, sandbox, stored files and the LangGraph thread of each conversation.

A failure of the cleanup is logged by class name and **never blocks the removal** (leftovers are then handled like those of an interrupted cleanup, see [Known limits](#known-limits)). The **owner cannot leave** their App (`App owners cannot leave their own apps`). The same user's Chat data in **other Apps**, and every other member's data, stay.

## Privacy of content

Privacy of the Chat is enforced at the **database and API level against other users of the platform**: another member, an App administrator, the owner or a platform administrator using the Chat cannot read or touch your conversations or files. It is **not** a technical guarantee against the people who configure the App or run the platform, because they control the endpoints a turn talks to:

| Who | What they control | Consequence |
|-----|-------------------|-------------|
| App administrators and owners | AI-service and embedding endpoints, MCP configs and their URLs, skills | A model, embedding or MCP endpoint they point at receives what the turn sends. MCP servers selected by URL receive the member's sign-in token. A skill is text injected into the prompt |
| App owner | The App's LangSmith API key | Chat prompts and answers are traced to that project |
| Platform operator | Environment (LangSmith env fallback, system AI/sandbox services), the database, the host | Full access to everything stored |
| Platform administrators in `LOCAL` auth mode | The admin set-password flow (an admin-triggered token the user, or whoever holds it, consumes to set the password) | A user's password can be set without the user, so the account can be taken over |

Chat content can therefore reach: the **model providers** of the services used, the **embedding provider** (indexed attachments), **MCP servers** (selected tools), **LangSmith**, and the **sandbox provider** (code interpreter).

For Chat turns, failure handling keeps message content out of the turn failure logs and out of the metrics error text. This covers **failure logs and metrics only**: some success-path INFO lines (for example file listings and file-registration messages in `file_management_service.py`) still contain file names.

- **Turn failure logs** carry the exception class chain, `agent_id`, `conversation_id`, a short `correlation_id` and traceback frames (file, line, function), not the provider's error text nor `str(exc)`. Helper: `backend/utils/turn_failure_log.py`.
- **Other warnings on the Chat path** are not covered by that helper. For example, when MCP tools are unavailable or time out, `backend/tools/agentTools.py` still logs the root cause, which can include server-side detail (such as an MCP server's address or error) but not the user's message.
- **Metrics**: the error text is kept as is only for codes the platform builds itself (timeout, cancelled, service retired, `approval_*`). Otherwise the error dashboard stores the exception class chain with `correlation_id=<id>`, so an entry can be matched to its log line, or `<code> (details withheld)`. Tool-call errors are stored as `Tool error (details withheld)`.
- Other channels (playground, public API, ...) log and record exactly as before.
- With **LangSmith** enabled for the App, Chat prompts and answers are sent to the App's LangSmith project like any other agent run. The LangSmith API key can be changed only by the App owner, so the owner controls where Chat prompts are traced (see [App settings permissions](#app-settings-permissions)). Each trace carries selection metadata (`chat_app_id`, `chat_ai_service_*`, `chat_silo_*`, `chat_skill_*`, `chat_mcp_config_*`; ids and names only).

### Image links

When `AICT_BASE_URL` is set, the images of a Chat conversation are sent to the model as signed `/static` URLs (without it they are inlined as base64). For the Chat these URLs are signed with the opaque identity `chat-image`, so **no email** is in the URL, and the URL is never logged (only the file id). The signature is the legacy, non-expiring one **on purpose**: the URL is stored in the checkpoint and replayed to every later turn and provider, so an expiring one would break the history. Consequence: they are **bearer links that do not expire**, held by every model provider the conversation used, by LangSmith (if enabled) and by the checkpoint database. Deleting or resetting the conversation, removing the member from the App, or deleting the user deletes the file and so revokes them. Follow-up: inline base64 or re-signing at replay. The Chat system prompt no longer contains the server's working directory path (the workspace is described with relative paths).

### Accepted risks of the Chat (in addition to the sandbox ones)

- **URL download tool, always on, no approval.** Every Chat turn has the base tool `download_url_to_workspace`, whether or not the code interpreter is on, and the Chat cannot ask for approval. A prompt injection in a document, an MCP result, an upload or a skill can therefore make the model send conversation text to a public URL (for example in the query string of a GET). The tool validates the URL and each redirect against an SSRF guard (`utils/ssrf_guard.py`), but there is a DNS-rebinding window between that check and the request, and the request honours the environment's proxy settings (`requests`). The only mitigation is to choose trusted sources, MCP servers and skills.
- Privacy is not a guarantee against administrators and operators (see above); success-path logs can contain file names.
- Image links do not expire (see above).

## Behaviours and limits

- **No approvals, no PII rules.** Per-agent human-approval and PII rules of normal agents do not apply in the Chat. Tools that would need approval (for example from an MCP server) cannot run: the Chat cannot answer approvals, so the pause is rejected on the spot, the tool is not executed and the conversation is not left paused (`hitl_approval` ends `cancelled` / `channel_not_interactive`). The expiry worker applies the same rule to a Chat pause it finds stuck after a crash.
- **Code runs without approval.** When the App has the [code interpreter](#code-interpreter) on, the model runs code in the sandbox with no human approval step; the Chat has no way to ask.
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
- **Images with `AICT_BASE_URL`.** When `AICT_BASE_URL` is set, images are sent as signed URLs that never expire (see [Image links](#image-links)). A "Custom" (Ollama) model probably cannot read them (inferred from the Ollama converter, which expects base64; not confirmed against a real Ollama).
- **Small windows.** If the most recent 20 messages (`keep`) alone exceed a small model's window, the turn still fails; summarization cannot shrink them. Models without a profile (Ollama, Azure AI) use the 32k trigger even if their real context is smaller.
- **Summary written, answer failed.** The summary is stored as its own step, so if the model call after it fails, the conversation's stored history is already compacted into that summary (the turn row and answer do not exist).
- **User image marker.** In the history, a user message that had an inline (base64) image shows a raw `[IMAGE:<hash>]` marker: placeholders are resolved to images only for assistant messages (`conversation_service.py`), and the marker is shared with the playground.
- **Not validated against real providers.** The tests do not call any provider API: provider-side validation (for example Anthropic thinking signatures, OpenAI Responses item pairing, role alternation, real token accounting, image size limits) is not covered. See [Testing](#testing).
- After a server crash in the middle of a turn, that conversation can answer "busy" (409) for several minutes, until its marker expires (11 minutes with the default run timeout). Right after a stream is cut by the client there is a brief window before the previous turn has fully stopped in which a new message can also be answered "busy".
- **No cap on temp silos (accepted risk).** There is deliberately no limit on how many temporary silos a user can create through Chat conversations (one per conversation that has an indexed attachment); this is a product decision. In practice it is bounded by the App's file size limit (413), by at most two concurrent indexing jobs per embedding service, and by the 60 s indexing limit. Temp silos do not count against the tier silo quota and are never frozen.
- Attachments sent whole (no default embedding service, or the file was not indexed) can exceed the model's context window.
- Azure AI and Google (AI Studio and Vertex AI) embedding clients have no client-side timeout (see `AICT_EMBEDDING_REQUEST_TIMEOUT_SECONDS`); the Chat still gives up after 60 s, but the abandoned call keeps its indexing slot until it returns.
- Playground, public API and marketplace uploads still index inline, with no time limit (unchanged).

### Known limits and follow-ups (code interpreter)

- **Reset or delete while a turn is running** is only safe at service level (a stale turn does not write state back or resurrect the entry). The sandbox key has no generation, so a sandbox created lazily by a pre-reset turn after the reset can reappear under the same key. Not proven at HTTP level.
- **Delete and reset destroy only sandboxes held by the same backend process** (`SandboxSessionService.destroy` pops its in-memory registry). With several workers (the default deployment runs 2), a sandbox held by another worker expires by the provider's TTL (`SANDBOX_SESSION_TTL_H`).
- The idle reaper is in-memory and per worker.
- **Detached subprocesses** started by code survive until the idle timeout.
- There is **no Chat rate limit** beyond one turn per conversation, 5 executions per turn and 3 sandboxes per user.
- There is also a process-wide cap of 50 live sandboxes, shared by agents and the Chat; it is not configurable through an environment variable.
- The OpenSandbox create path logs only through `describe_exc` (class name only on a Chat turn), but `OpenSandboxProvider.destroy_sandbox_id` logs the raw exception, with a traceback, at DEBUG level when the kill by id fails, also on Chat turns.
- A hung output pull keeps its sandbox lease and one of the pull slots until the provider read returns.
- **Nothing was verified against a real sandbox provider.** The tests use in-memory fake providers; the E2B private streaming client and the stop behaviour of OpenSandbox and Daytona streamed reads are only proven against fakes of the SDK shapes.

### Known limits and follow-ups (release)

- **Output-file caps apply to every agent channel**, not only the Chat: 20 files, 50 MB per file, 100 MB in total, a 20 s time budget and 2 concurrent pulls per process. A slow App can degrade others (shared pull slots; a pull that finds them busy is skipped at once). Non-Chat channels get no user-visible warning except `usage.outputs_skipped` (public API) / `outputs_skipped` in the SSE `done` event.
- **Step limit.** A Chat turn that spends `AICT_CHAT_RECURSION_LIMIT` steps ends with `STEP_LIMIT_REACHED` and the user has to write "continue" (see [Step limit](#step-limit)); the playground and public API keep their generic error for the same condition.
- **Summarization depends on private LangChain names.** The Chat's summarization middleware is a subclass that reads private names of the installed LangChain version. If they are missing it falls back to the plain library middleware with one warning (class name). The contract is checked by tests against the installed version (`test_summarization_contract.py`); re-run them on every LangChain bump.
- **Unbounded growth of storage.** Checkpoints, `data/tmp/conversations` and sandbox outputs have no age-based sweep for the Chat. The operator must monitor disk, which on the single-host deployment is shared with PostgreSQL.
- **No per-tenant isolation of the shared pools.** Attachment indexing and output pulls use shared slots, so one App or user can occupy them for others.
- **Image links do not expire** and the Chat always has the URL download tool: see [Image links](#image-links) and [Accepted risks](#accepted-risks-of-the-chat-in-addition-to-the-sandbox-ones).
- **Member removal leftovers.** The cleanup after a removal is best effort and never blocks it: if it fails, files, vectors or a sandbox of that member can stay behind, and nothing retries it (the orphan sweep only covers temp repositories of conversations that no longer exist).

## Behaviour change outside the Chat

- Playground and public API file/chat endpoints now answer **404 `Conversation not found`** when given a `conversation_id` that is not numeric or not the caller's for that agent (same user, or same API key). **Release note for API consumers:** a client that sent an arbitrary string or a foreign id as `conversation_id` to these endpoints now gets 404. The check applies to agents with memory; for agents without memory the id is only a grouping label for ephemeral files. Previously a foreign id was accepted. Helper: `ChatAttachmentService.require_owned_conversation`.
- **Temporary silos are hidden.** The temp silo of a conversation (playground and Chat), its repository (type `playground_media`) and its metadata output parser no longer appear in silo, repository or output-parser lists, pickers, exports or "used by" views, internal or public. Addressed by id they answer 404 like a missing one; a normal agent cannot be pointed at one; imports cannot bind to one by name; a repository cannot be created with the reserved type. API consumers that listed silos or repositories will no longer see them. The partial index `ix_Repository_silo_id_temp` (migration `ichat002`) serves the visibility lookup.

## App settings permissions

Administrators and above can now update the App settings (`PUT /internal/apps/{id}`; previously only the owner could save). The **LangSmith API key stays owner-only**: an administrator who tries to change or clear it gets 403, and the settings page shows the field read-only for them. A settings update that omits the key (or sends back the masked value) now **keeps** the stored key; clearing it requires sending it empty explicitly, as the owner. The **code interpreter switch** (`chat_code_interpreter_enabled`) follows the general rule: administrators and the owner can change it (see [Code interpreter](#code-interpreter)). Deleting the App, transferring ownership and managing collaborators are unchanged. See [Role Authorization](../reference/role-authorization.md).

## Operations

### Migrations `ichat001` to `ichat004`

All four are additive. `ichat001` revises `chatfiltmerge003`; `ichat002` revises `ichat001`; `ichat003` revises `ichat002`; `ichat004` revises `ichat003` and is the current head.

**`ichat004`**: two indexes on `"Conversation"`, created with a plain `CREATE INDEX IF NOT EXISTS` (the repository has no `CONCURRENTLY` pattern, so it takes a short write lock on the table): `ix_conversation_agent_user_updated` on `(agent_id, user_id, updated_at DESC)` (a user's conversation list of the shared internal agent, newest first) and `ix_conversation_agent_api_key_hash` on `(agent_id, api_key_hash)` (the API-key conversation lookup). The model declares both in `__table_args__`. Its downgrade drops both. **On a very large `"Conversation"` table**, create them by hand first without blocking writers, then upgrade (the `IF NOT EXISTS` makes the migration a no-op for them):

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_conversation_agent_user_updated
  ON "Conversation" (agent_id, user_id, updated_at DESC);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_conversation_agent_api_key_hash
  ON "Conversation" (agent_id, api_key_hash);
```

(`CONCURRENTLY` cannot run inside a transaction block, and a failed run leaves an `INVALID` index under the same name: drop it before retrying, or `IF NOT EXISTS` will skip it.)

**`ichat003`**: `App.chat_code_interpreter_enabled` (Boolean, NOT NULL, server default `false`). Existing Apps get `false`: no App runs code in the Chat until an administrator turns it on. Its downgrade drops the column, so the stored opt-ins are lost.

**`ichat002`**: `chat_conversation_state.busy_token` and `busy_until` (nullable), `App.default_embedding_service_id` (nullable, FK `App_default_embedding_service_id_fkey` to `embedding_service`, `ON DELETE SET NULL`) and the partial index `ix_Repository_silo_id_temp` on `Repository(silo_id)` where `type = 'playground_media'`. No backfill: existing Apps have no default embedding service, so their Chat attachments are sent whole until an administrator sets one.

**`ichat001`**:

- `Agent.kind` (`'standard'` default) with `ck_agent_kind`, `ck_agent_internal_chat_unexposed`, `ck_agent_internal_chat_has_app` and the partial unique index `uq_agent_internal_chat_per_app`.
- `INTERNAL_CHAT` added to the `conversationsource` and `agent_execution_caller_type` enums (`ApprovalChannel` is a string column; Python-only).
- Tables `conversation_turn`, `chat_user_default`, `chat_conversation_state` (foreign keys and delete rules in [Defaults and conversation state](#defaults-and-conversation-state)).

Rollout: deploy the backend before the frontend; the menu entry appears with the new frontend image.

### Rolling back

**The old image cannot start against a database at `ichat004` on its own.** `backend/Dockerfile` starts with `alembic upgrade head`, and Alembic fails on a revision it does not know. So a rollback is always: **downgrade first, then deploy the old image**. The downgrade must be run with the **new** image (it holds the revision files); an older build also does not know the new enum values or `Agent.kind`.

What each step reverts:

```bash
alembic downgrade ichat003           # reverts ichat004 (drops the two Conversation indexes)
alembic downgrade ichat002           # reverts ichat003
alembic downgrade ichat001           # reverts ichat002
alembic downgrade chatfiltmerge003   # reverts ichat001
```

(`alembic downgrade chatfiltmerge003` alone runs all four in order.) Go as far back as the image you will deploy needs: an image that still contains `ichat003` needs only the first command; an image from before the Chat needs all of them.

- `ichat004` downgrade: drops the two indexes (no data lost).
- `ichat003` downgrade: drops the code interpreter opt-in of every App.
- `ichat002` downgrade: drops the busy markers (transient) and the Apps' default embedding service (configuration, lost: set it again after upgrading).
- `ichat001` downgrade is destructive by design. It drops the three tables, deletes all Chat conversations and the internal agents (with their approvals and execution events), relabels remaining `agent_execution_event` rows from `INTERNAL_CHAT` to `INTERNAL_PLAYGROUND`, and recreates both enum types without the label. It rewrites `Conversation` and `agent_execution_event` under `ACCESS EXCLUSIVE` locks: use a maintenance window. It also **purges what the internal agents left behind**, matched by the exact prefix of the internal agent's id (not `LIKE`): their temp `playground_media` repositories, the `Media`, `Resource` and `Folder` rows of those repositories, the temp silos, the metadata output parsers of those silos, the PGVector rows of the `silo_{id}` collections, the LangGraph checkpoint rows (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`), and the conversation and turn rows. The purge is idempotent. Checkpoints are deleted by **exact thread id**, built from the internal agents' `Conversation` rows (`thread_{agent}_{session}`) plus `thread_{agent}`; this uses the index and does not scan the large checkpoint tables under the locks. A checkpoint thread whose `Conversation` row was already gone **is left behind** (there is no index-friendly way to find it); it is unreachable for the old code.

Runbook:

1. Take a database backup and open a maintenance window; stop the backend.
2. Record the ids you will need for the file cleanup (step 7), because the downgrade deletes the rows that hold them:
   ```sql
   SELECT conversation_id FROM "Conversation" WHERE source = 'INTERNAL_CHAT';
   SELECT agent_id, app_id FROM "Agent" WHERE kind = 'internal_chat';
   ```
3. If any temp silo of the internal agents is stored in **Qdrant**, delete its collection (`silo_{id}`) first. The `ichat001` downgrade **refuses** in that case: it raises `RuntimeError` naming the silos and changes nothing; after the cleanup, run the downgrade again.
4. Run the downgrade with the new image, as far back as needed (commands above).
5. Deploy the old image.
6. Checkpoint threads whose `Conversation` row was already gone before the downgrade stay in the checkpoint tables (the downgrade does not scan them). They are unreachable for the old code; if you remove them by hand, match the thread id exactly, never with a `LIKE` on `thread_{id}_` (`_` is a wildcard and would also hit other agents' ids).
7. **Files on disk are not removed by the downgrade.** Remove `data/tmp/conversations/{conversation_id}/` for each recorded conversation id and `data/tmp/persistent/agent_{internal_agent_id}_...` for each internal agent id by hand.

What is verified and what is not: the purge, the refusal on Qdrant and the add/drop of the `ichat004` indexes are covered by `tests/integration/test_ichat004_migration.py` (three tests, on an ephemeral test database, including that only the internal agents' leftovers are removed). Not verified: the downgrade on a real production database (volume, lock duration, a real Qdrant), and the old image started against the downgraded database.

### Attachment folders from older builds

Persistent uploads (agents with memory and a `conversation_id`) keep the original file under `data/tmp/conversations/{conversation_id}/`, with no user or App in the path, and its metadata under `data/tmp/persistent/agent_{agent_id}_user_{user_id}_app_{app_id}_conv_{conversation_id}/`. Conversation ids are global. Before the ownership check described above, the playground and public API accepted any `conversation_id`, so a deployment that ran an older build can hold files in a `conversations/{id}/` folder that were written by a user who did not own conversation `{id}`, and a legitimate conversation's folder may contain them.

The cleanup worker (`backend/services/file_cleanup_worker.py`) sweeps only `data/tmp/ephemeral/`, `data/tmp/uploads/` and `data/tmp/persistent/` (the latter after `TMP_PERSISTENT_TTL_DAYS`). It never touches `data/tmp/conversations/`. Originals there are removed only when the file is removed, when the conversation is reset or deleted (Chat conversations, which delete the folder), or when the agent is deleted. Nothing expires them by age, so such files stay until deleted by hand.

One-off cleanup (optional): inspect `data/tmp/conversations/*` of deployments that ran an older build and delete files you cannot attribute to the conversation's owner. There is no automated check for this.

### Observability

- Dashboards: the `INTERNAL_CHAT` channel appears in platform and App breakdowns by `channel` ([Agent Metrics](../guides/agent-metrics.md)). Chat runs report the model that answered (the turn's AI service), not the internal agent's own configuration.
- Logs: one INFO line per turn (`internal_chat.turn app_id=... conversation_id=... user_id=... ai_service_id=... silo_id=... skill_ids=... mcp_config_ids=...`). IDs only.
- Failures: search the log for the `correlation_id` shown in the metrics error message.

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AICT_EMBEDDING_REQUEST_TIMEOUT_SECONDS` | `120` | Client-side timeout of embedding calls (read when the client is built; retries are not changed). Applied to OpenAI, MistralAI, Custom/HuggingFace, Ollama and AWS Bedrock embedding clients. **Not** applied to Azure AI and Google (AI Studio and Vertex AI), whose clients expose no timeout. Source: `backend/tools/embeddingTools.py` |
| `AICT_CHAT_RECURSION_LIMIT` | `100` | Graph step limit of a Chat turn only; invalid or below 1 falls back to the default with a warning. See [Step limit](#step-limit) |
| `AICT_AGENT_RECURSION_LIMIT` | `50` | Graph step limit of every other agent run (same fallback rule). Existed before, undocumented |
| `CHAT_MAX_FILES_PER_TURN` | `10` | Files (uploads + references) per Chat message; `0` = unlimited; HTTP 422 `TOO_MANY_FILES` beyond it (`/messages` and `/stream`) |
| `ATTACHMENT_INDEXING_TURN_BUDGET_S` | `120` | Seconds of indexing allowed per Chat turn; `0` = unlimited; keep well below `AICT_AGENT_RUN_TIMEOUT_SECONDS` |
| `SANDBOX_MAX_SESSIONS_PER_USER`, `SANDBOX_MAX_SESSIONS_PER_APP`, `SANDBOX_EVICT_MIN_IDLE_S`, `SANDBOX_CHAT_BASH_MAX_TIMEOUT_S` | `3`, `10`, `60`, `60` | **Chat only** limits, see [Limits](#limits-chat-only). The two session limits are per backend process |
| `SANDBOX_MAX_EXECUTIONS_PER_TURN` | `5` | Per turn. Applies to agents (REPL executions) and to the Chat (REPL and `Bash` share it); `0` refuses every execution |
| `SANDBOX_PULL_MAX_FILES`, `SANDBOX_PULL_MAX_FILE_BYTES`, `SANDBOX_PULL_MAX_TOTAL_BYTES`, `SANDBOX_PULL_TIME_BUDGET_S`, `SANDBOX_PULL_MAX_CONCURRENT` | `20`, `52428800`, `104857600`, `20`, `2` | Output file delivery (agents and Chat), see [Output files](#output-files) |

Full list with the OpenSandbox server variables (`OPENSANDBOX_API_KEY` is mandatory for the `opensandbox` compose profile): [Environment Variables](../reference/environment-variables.md#sandbox-providers). Operations of the sandbox host: `docker/README.md`. Without the `opensandbox` profile running, a Chat on the system default provider still offers the code tools (the provider is only checked for being registered and allowed): the first call returns a generic error and the answer is written without code. `turn_config.code_interpreter` is then `false` on `/messages` (and `true` on the early `metadata` event of `/stream`).

Related, already existing: `AICT_AGENT_RUN_TIMEOUT_SECONDS` (default 600) sets the busy-marker expiry (`+ 60 s`) and the expected duration of a sandbox turn lease.

## Testing

- Backend: `tests/integration/internal_chat/` (exclusion from every surface, functional API, isolation of state, attachments, router wiring) with shared fakes and the world fixture in `_chat_support.py`. Fakes: the LLM (per AI service), the retriever tool, the MCP client and the metrics write; everything else (router, service, resolver, execution stack, checkpointer, PostgreSQL) is real.
- LangGraph checkpoint tables are not part of `Base.metadata`, so they survive the test schema drop. Assertions on threads must be relative to a baseline taken at the start of the test, not absolute counts.
- Concurrency: `test_chat_isolation_concurrency.py` runs overlapping turns through `httpx.AsyncClient` + `ASGITransport` with one session per request (`get_db` not overridden, data committed and purged afterwards) and a fake model that parks every call on per-turn gates, so overlap is deterministic and asserted, not timed.
- Model switch: `test_chat_model_switch.py` switches provider, service and model between turns of one conversation (summarization, small windows, images, tools, retired models, failure paths, the stamp). It runs the router, services, real checkpointer, real `SummarizationMiddleware`, the real normaliser and PostgreSQL; only the LLM boundary is replaced by `_provider_sim.py`, subclasses of the real LangChain model classes that validate the request with each provider's own installed converter and answer with the message shapes the real adapters produce. **No real provider API is called**: "accepted" means the installed converter takes the messages and tool calls are paired, not that the API would. Capability, context-window and error rejections are hand-written rules. Unit tests: `tests/unit/tools/middleware/test_history_normalizer.py` and `test_summary_input_bound.py`.
- Temp silo visibility: `test_chat_temp_silo_visibility.py` includes a **route-enumeration guard**. A new route that takes a silo or repository id must pass it (hidden temp silos answer 404 like a missing one).
- Code interpreter: `test_chat_code_interpreter.py` (router, service, resolver, execution/streaming, session service, skill loader and PostgreSQL are real; only the LLM and the sandbox **provider class** are in-memory fakes). Unit files: `test_sandbox_output_pull.py`, `test_sandbox_session_limits.py`, `test_sandbox_bounded_read.py`, `test_chat_turn_sandbox_lease.py`, `test_outputs_skipped_metadata.py`, `test_resolved_config_code_interpreter.py`. The App switch API is covered by the integration file `tests/integration/routers/internal/test_app_chat_code_interpreter_switch.py`. **No real sandbox provider is called.** Details per file: [Testing Guide](../testing/README.md#chat-tests-and-langgraph-checkpoints).
- Step limit, removal and migrations: `test_chat_step_limit.py` (both routes; conversation kept, next turn continues, the agent limit is not used by the Chat, tool-call log lines carry names and outcomes only), `test_orphan_sweep_exact_prefix.py`, `test_collaborator_removal_cleanup.py` (removed/left member's data of that App gone, others untouched, a cleanup failure never fails the removal), `tests/integration/test_ichat004_migration.py`, `tests/unit/tools/middleware/test_summarization_contract.py`. Details: [Testing Guide](../testing/README.md#chat-tests-and-langgraph-checkpoints).
- Query budget: `test_chat_query_budget.py` counts the SQL statements of the listing/options endpoints and of a whole turn (no N+1, absolute ceiling).
- Frontend: Vitest + Testing Library render tests in `frontend/tests/ui` (`npm run test:ui`).

See [Testing Guide](../testing/README.md).

## See Also

- [Chat in an App](../guides/chat-bot/app-chat.md) — end-user guide
- [Agent System](agent-system.md) — agent execution, memory, skills
- [MCP Integration](mcp-integration.md) — MCP configs consumed as tools
- [Internal API](../api/internal-api.md) — endpoint overview
- [Human approval in the public API](../guides/human-approval.md) — why the Chat does not take part
- [Agent Metrics](../guides/agent-metrics.md) — channels and dashboards
