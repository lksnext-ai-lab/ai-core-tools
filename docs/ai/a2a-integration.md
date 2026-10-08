# A2A Integration

> Part of [Mattin AI Documentation](../README.md)

## Overview

**Agent2Agent (A2A)** is an open protocol for letting external agent frameworks call Mattin agents as peers, the same way [MCP Integration](mcp-integration.md) lets Mattin agents call external tools. A2A is **opt-in per agent** (the "A2A" tab in the agent form) and served over the **JSON-RPC binding only** — there is no REST (HTTP+JSON) or gRPC binding, and no push-notification support.

Mattin speaks protocol **v1.0**, with optional **v0.3 compatibility** for older clients (`A2A_ENABLE_V0_3_COMPAT`, default `true`). A client that sends the `A2A-Version: 1.0` header is served as v1.0; a client that omits it is treated as v0.3.

A global kill switch, `A2A_ENABLED` (default `true`), disables every A2A route (cards, catalog, root card, JSON-RPC) with a uniform 404 when set to `false`. The background retention/maintenance worker keeps running even when the switch is off, so existing data is still cleaned up.

Server-side implementation lives in `backend/services/a2a_server/` and `backend/routers/a2a_server/`. By convention **no module under `backend/` is ever named `a2a`**, because `backend/` is on `sys.path` and would shadow the `a2a-sdk` package.

## URLs

| Purpose | URL |
|---------|-----|
| Per-agent JSON-RPC endpoint | `POST /a2a/v1/apps/{app_slug}/agents/{agent_id}` |
| Public agent card | `GET /a2a/v1/apps/{app_slug}/agents/{agent_id}/.well-known/agent-card.json` |
| App catalog (Mattin-specific) | `GET /a2a/v1/apps/{app_slug}/agents` |
| Root card | `GET /.well-known/agent-card.json` |

- The agent card is compatible with the SDK's `A2ACardResolver` given the base URL.
- The app catalog is **not** part of the A2A standard; it is a Mattin convenience that lists the agents visible to the caller (`agent_id` ascending), each with absolute `card_url` and `rpc_url`. An empty result (including a missing app) is the same uniform 404 as any other not-found case.
- The root card is served only when `A2A_ROOT_AGENT=app_slug/agent_id` is set and that agent has **public** visibility. Unset, malformed, or pointing at a disabled/hidden/`api_key`-only agent — all 404.
- An app needs a slug to be reachable over A2A at all; agents of a slug-less app have no card or RPC URL.
- `agent_id` in the path is numeric; a non-numeric value falls into the same uniform 404 (never FastAPI's 422).

All absolute URLs in cards and the catalog are built from `A2A_PUBLIC_BASE_URL`. If it is unset, they fall back to `FRONTEND_URL`, then to the inbound request's `Host` header. That last fallback is **client-supplied and forgeable by any caller** — not only one sitting behind an untrusted proxy, since `Host` is just a request header anyone can set — so a card built from it can point external clients, and the API keys they then use, at an attacker-controlled host if the card is ever cached or shared. Always set `A2A_PUBLIC_BASE_URL` (or `FRONTEND_URL`) explicitly outside local development. The resolved base always has its trailing slash stripped.

## Enabling an agent

Each agent has its own **A2A** tab in the agent form (`AgentA2ASettings`), available once the agent has been saved at least once:

- **Enable A2A** — toggles `a2a_enabled`.
- **Visibility**:
  - `public` — the card and catalog entry are readable by **anyone**, with no key; the RPC endpoint still requires a valid `X-API-KEY` of the same app for every method.
  - `api_key` — the card, the catalog entry **and** the RPC endpoint are all hidden (uniform 404) from anyone without a valid key of that app.
- **Name / description overrides** — shown on the card instead of the agent's own name/description when set.
- **Skill tags** and **Examples** — tags appear on every card skill; examples appear **only on the extended card** (`GetExtendedAgentCard`), never on the public one.
- Read-only **card URL** and **RPC URL**, with copy buttons.
- Editing any of these fields requires the same minimum role as any other agent edit (an app VIEWER gets 403).

An agent is **discoverable** only when all of these hold: the global switch is on, the app exists and has a slug, the agent belongs to it, `a2a_enabled=true`, and neither the agent nor the app is frozen. A `public`-visibility discoverable agent is visible to anyone; an `api_key`-visibility one is visible only to a valid key of that same app.

**Before enabling A2A on an agent**, understand what it exposes: an enabled agent is reachable by **every holder of an app API key** (any `api_key`-visibility restriction is per-app, not per-caller), and the call reaches that agent's full configuration — its tools, MCP servers, agent-as-tool sub-agents, code interpreter and RAG silo — with caller-controlled message text, DataPart JSON and file content flowing straight into the model (the same prompt-injection surface as any other LLM input channel). A FilePart URI also makes the server perform an outbound fetch on the caller's behalf (SSRF-guarded, but still attacker-directed). Only enable A2A on agents whose tools and data access are safe to trigger from untrusted external input, and issue a dedicated, revocable API key per external integration rather than reusing a key with broader scope.

## Auth

RPC calls authenticate with an app **API key** in `X-API-KEY`, the same keys used by the [Public API](../api/public-api.md).

- A **visible** agent called without a key, or with an invalid/revoked/other-app key, gets **401** `{"detail": "Valid X-API-KEY required"}` with `WWW-Authenticate: ApiKey header="X-API-KEY"`.
- An `api_key`-visibility agent called without a valid key is **indistinguishable from a nonexistent agent**: uniform **404**.
- Card/catalog/RPC requests for a missing app, a missing agent, an agent of another app, a disabled agent/app, a frozen agent/app, or `A2A_ENABLED=false` all return the **same** 404 status and body — `{"detail": "Not Found"}` — so a caller can never tell these cases apart (non-enumeration). The origin check on the RPC route runs only **after** the API key is validated, so a CORS rejection can never leak app existence either.
- An API key belonging to a different app counts as no key at all.

## Methods supported

| Method | Consumes execution budget? |
|--------|------|
| `SendMessage` | Yes |
| `SendStreamingMessage` | Yes |
| `GetTask` | No |
| `ListTasks` | No |
| `CancelTask` | No |
| `SubscribeToTask` | No |
| `GetExtendedAgentCard` | No |

Their v0.3-compat equivalents (`message/send`, `message/stream`, `tasks/get`, `tasks/cancel`, `tasks/resubscribe`) are served identically when `A2A_ENABLE_V0_3_COMPAT=true`.

**Not supported**: push notifications (`CreateTaskPushNotificationConfig` and friends return the SDK's push-not-supported error — the card advertises `push_notifications: false`), any auth scheme other than the API key, and the REST/gRPC bindings. These are deliberate design limits, never masked by rewriting task status.

## Semantics

- Each `SendMessage`/`SendStreamingMessage` without a `taskId` creates a new task. A task ends in exactly one terminal state — `completed`, `failed` or `canceled` — and **never** emits `input_required`.
- `contextId` maps to exactly one Mattin Conversation per (app, agent, API key). An unknown `contextId` is accepted and bound to a fresh conversation for that caller; it never joins or reveals another caller's conversation. `taskId`/`contextId` must be at most 36 characters of `[A-Za-z0-9._:-]` (the SDK's own column width).
- A message naming a `taskId` that is already terminal, belongs to another owner, or whose `contextId` doesn't match the task's own is rejected before anything executes.
- Two concurrent turns on the same `contextId` both execute and both append to memory in completion order — same as two concurrent public-API calls on one conversation.
- `return_immediately=true` returns the task in a non-terminal state right away; the turn keeps running in the background and a later `GetTask` shows the terminal result.
- `GetTask` honors `historyLength`.
- **Cancellation** works whether `CancelTask` lands on the same worker that is executing the task or a different one. A keepalive status update (`A2A_KEEPALIVE_SECONDS`, default 1.0 s) plus coalesced token flushing (`A2A_STREAM_COALESCE_MS`, default 250 ms) bound how long a remote cancel takes to land — typically **around one second**. Cancelling an already-terminal task returns a not-cancelable error instead of re-running cleanup.

## Inputs

- **TextPart** → appended to the message text.
- **DataPart** → serialized as a fenced JSON code block appended to the message.
- **FilePart with bytes** → decoded and passed through the same chat file pipeline used by the Public API (memory-aware, ephemeral references cleaned up after the turn).
- **FilePart with a URI** → `http`/`https` only, fetched through the shared SSRF guard (`backend/utils/ssrf_guard.py`):
  - blocks loopback, link-local, private, reserved, multicast, unspecified, CGNAT (100.64.0.0/10), NAT64, Teredo, deprecated IPv6 site-local, and IPv4-compatible IPv6 ranges, including IPv4-mapped/6to4/Teredo-embedded addresses, on **every** resolved IP;
  - TLS verification is always on, with no insecure-retry fallback;
  - every redirect hop is re-validated, up to 3 hops;
  - the whole fetch (DNS + every hop) is bounded by one timeout (`A2A_URI_FETCH_TIMEOUT_SECONDS`, default 15 s).
- Any fetch/decode failure fails the task with an error naming the offending part. **No placeholder content is ever substituted.**
- A message with zero parts, or with only whitespace text, is rejected as invalid params before a task is created.
- Size caps: per-file bytes come from the app's `max_file_size_mb` if set (> 0), else `A2A_MAX_FILE_MB`; the whole request body is capped by `A2A_MAX_REQUEST_MB` (enforced on bytes actually read, not just `Content-Length`, so a chunked body with no length header is still bounded); the number of parts is capped by `A2A_MAX_PARTS` and `A2A_MAX_FILE_PARTS`.

## Outputs

- The agent's response streams into one `response` artifact with `append=True` chunks; their concatenation equals the final text exactly.
- Structured `OutputParser` output is returned as an additional `application/json` DataPart.
- Files the agent produces come back as `FilePart`s:
  - **≤ `A2A_INLINE_FILE_MAX_BYTES`** (default 5 MiB) → inline bytes, with filename and media type;
  - **larger** → a `/static` URI carrying a new **expiring** signature (`generate_expiring_signature`/`verify_expiring_signature` in `backend/utils/security.py`), valid for `A2A_FILE_URL_TTL_SECONDS` (default 3600 s, hard-capped at `A2A_FILE_URL_MAX_TTL_SECONDS`, default 86400 s — a value above the cap is clamped with a startup warning, not silently honored).
  - Besides the per-file threshold, one turn's **aggregate** inline budget also starts at `A2A_INLINE_FILE_MAX_BYTES` and is debited by every file actually inlined (`ResponseArtifactMapper` in `backend/services/a2a_server/output_mapper.py`): once that running budget is exhausted, later files in the same turn fall back to the signed-URL form even if each one is individually under the per-file cap. This bounds the total bytes one turn can inline regardless of how many small files it produces.
- A2A **never** emits a non-expiring `/static` link. The existing non-expiring signatures used by the playground, the Public API, the marketplace and scheduled tasks keep working unchanged — `/static` accepts both formats.
- These file URLs are **bearer links**: anyone who has the URL before it expires can download the file. Share them (and any task/transcript containing them) with the same care as the API key itself.

## Limits & rate limiting

- The app's `agent_rate_limit` execution budget is consumed **only** by `SendMessage`/`SendStreamingMessage` (and their v0.3 equivalents). `GetTask`, `ListTasks`, `CancelTask`, `SubscribeToTask` and `GetExtendedAgentCard` still require a valid key but never touch that budget, so a client polling for task status cannot drain it.
- Card and catalog requests are rate-limited **per client IP**, before any auth or DB work, through a separate budget (`A2A_DISCOVERY_RATE_LIMIT_PER_MINUTE`, default 60/min) that never shares a bucket with an app's execution budget.
- The RPC endpoint also has its own pre-auth, per-IP limiter (`A2A_RPC_PREAUTH_RATE_LIMIT_PER_MINUTE`, default 300/min) that bounds raw request volume before any app/agent resolution — it doesn't replace the execution budget above, only bounds abuse against it.
- Concurrent **streams** (`SendStreamingMessage`/`SubscribeToTask`) are bounded by a bulkhead: per app (`A2A_MAX_CONCURRENT_STREAMS_PER_APP`, default 10), per API key (`A2A_MAX_CONCURRENT_STREAMS_PER_KEY`, default 5) and per worker process (`A2A_MAX_CONCURRENT_STREAMS_WORKER`, default 40, auto-clamped below `UVICORN_LIMIT_CONCURRENCY`). Exceeding any of them returns a retryable JSON-RPC error with a retry hint instead of a raw failure.
- A streamed response also has a hard wall-clock cap (`A2A_STREAM_MAX_SECONDS`, default 1800 s) and a liveness re-check against the task store while waiting for the next event (`A2A_STREAM_LIVENESS_SECONDS`, default 5 s), so a remote "tail" of another worker's task can't poll forever once that worker is gone.
- **Known limitation**: every in-memory limiter in this codebase (the discovery limiter, the RPC pre-auth limiter, the stream bulkhead's per-app/per-key counters, and `agent_rate_limit` itself) is **per worker process**. With `UVICORN_WORKERS=N`, the effective limit across the whole deployment is approximately `N ×` the configured value. This is shared with the existing Public API limiter and is not fixed by A2A.

## Data & retention

A2A protocol state lives in three SDK-owned tables, created and dropped **only by Alembic** (never by the SDK's own `create_table`): `a2a_tasks`, `a2a_task_events` and `a2a_task_versions`. A Mattin-owned `a2a_context_link` table binds `contextId` to a Conversation (see below).

### SDK pin and upgrade procedure

The SDK is **exactly pinned**: `a2a-sdk = {version = "==1.2.2", extras = ["http-server"]}` (`pyproject.toml`). There is no `postgresql` extra — the SDK's DB stores run on Mattin's own psycopg async engine, so the SDK's asyncpg extra is never installed. The pin is exact (not a range) because `backend/services/a2a_server/storage.py` overrides three private SDK attributes (`task_model`'s public property plus `_event_model`/`_version_model`) to route the SDK's stores onto the `a2a_*`-prefixed tables instead of its own `tasks`/`task_events`/`task_versions` defaults — any patch release could rename or repurpose those attributes.

To bump the pin:

1. Change the version in `pyproject.toml`, re-lock, re-install.
2. Run the contract suite: `tests/integration/a2a_server/test_sdk_contract.py` — it asserts the installed SDK version, the store/stream constructor signatures, and that the registry classes from `backend/services/a2a_server/sdk_models.py` are actually the ones in use (not the SDK's own default models).
3. Run the schema-drift test: `tests/integration/a2a_server/test_a2a_schema_matches_sdk.py` — it reflects the migrated `a2a_*` tables and compares them against the SDK's own mixins.
4. Review `backend/services/a2a_server/storage.py` (`_bind_models`) for any change in the attributes it touches.
5. Only merge the bump once both suites are green.

### Retention and lifecycle

- `A2A_TASK_RETENTION_DAYS` (default 30): how long a terminal task, its versions, its events and its `a2a_context_link` row are kept before a periodic sweep deletes them.
- `A2A_TASK_TIMEOUT_SECONDS` (default 900): a non-terminal task with no progress for longer than this is marked `failed` by the same sweep (covers a worker crash/restart).
- `A2A_EVENT_RETENTION_MINUTES` (default 15): a **much shorter**, separate window after which a *terminal* task's own events (already-consumed streaming history — the highest write-volume data in the whole system) are purged, independently of the task row's own 30-day retention.
- `A2A_SWEEP_INTERVAL_SECONDS` (default 600): how often the leader-locked sweep runs. Leadership uses a Postgres session-level advisory lock, so it is safe across multiple backend replicas. The very first sweep after startup is delayed by a random 30–90 s jitter, so replicas restarted together don't all contend for the lock at the same instant.
- **Deletion**: deleting an agent (`AgentService.delete_agent`) or an app (`AppService.delete_app`) schedules an async purge of that owner's A2A rows. The purge first cancels any in-flight tasks, waits a grace period (`A2A_PURGE_GRACE_SECONDS`, default 5 s, auto-raised to cover keepalive + coalesce + 1 s — a shorter grace lets a still-mid-turn remote worker's next save recreate the just-purged task), then deletes. A purge failure is logged and never blocks the deletion; the periodic sweep's orphan pass is the backstop that eventually catches anything missed.
- **Conversations are never purged by A2A retention** (Conversations and their checkpointer memory follow the normal conversation lifecycle). A later reuse of a purged `contextId` is simply treated as unknown and gets a fresh conversation.

### contextId ↔ Conversation

- Each `(app, agent, API key, contextId)` combination maps to exactly one Conversation, created with `source=A2A` the first time that combination is seen — including for agents **without** memory (they still get a stable `contextId` and task history; they simply don't get prior-turn injection).
- Two different API keys of the same app using the same `contextId` each get their **own** conversation; neither can see the other's history.
- Deleting the bound Conversation cascades the link row away; the next use of that `contextId` is treated as unknown and gets a brand-new conversation with no prior memory.

## Observability

- Every RPC call emits one structured log line (`a2a.rpc`) after the response finishes, with `app_id`, `agent_id`, `api_key_id` (never the raw key or hash), `method`, `task_id`, `context_id`, `conversation_id`, `latency_ms` and `outcome`. Discovery requests log `app_slug`, `agent_id`, the visibility outcome and reason, and the client IP — never a key.
- Metrics dashboards show A2A calls under their own channel, `A2A`, alongside the Public API, MCP and other channels (see [Agent Metrics](../guides/agent-metrics.md)).
- LangSmith tracing behaves exactly as it does for the Public API (per-app key, or the global fallback).

## Environment variables

Almost all variables are read in exactly one place, `backend/utils/a2a_config.py`, and are documented with the same defaults in `docker/.env.example`. For those, every value is optional and a malformed one falls back to its default with a startup warning rather than failing to start. Three variables are the exception, read directly where they're used instead of through `a2a_config.py`:

- `A2A_FILE_URL_MAX_TTL_SECONDS` — read **per call** in `backend/utils/security.py:17-19` via `int(os.getenv(...))`. A malformed (non-integer) value raises a `ValueError` on the next signature generation or verification instead of falling back to the default — it does not fail soft.
- `A2A_DISCOVERY_MAX_TRACKED_KEYS` and `A2A_DISCOVERY_OVERFLOW_MULTIPLIER` — read once, **at import time**, in `backend/services/rate_limit_service.py:21-34`. They size the per-IP key-namespace limiter's tracked-key cap and its shared overflow bucket's budget multiplier, used by both the A2A discovery limiter and the A2A RPC pre-auth limiter (and by nothing else). A malformed value raises at import (process startup), the same failure mode as any other bad env var parsed with a bare `int(...)`.

| Variable | Default | Purpose |
|----------|---------|---------|
| `A2A_ENABLED` | `true` | Global kill switch for every A2A route. |
| `A2A_ENABLE_V0_3_COMPAT` | `true` | Serve clients that omit `A2A-Version: 1.0` as v0.3. |
| `A2A_ROOT_AGENT` | unset | `app_slug/agent_id` published at `/.well-known/agent-card.json`. |
| `A2A_PUBLIC_BASE_URL` | unset | Base for absolute card/RPC URLs. Falls back to `FRONTEND_URL`, then the request `Host` header. |
| `A2A_DISCOVERY_RATE_LIMIT_PER_MINUTE` | `60` | Per-IP limit on card/catalog requests. `<= 0` = unlimited. |
| `A2A_RPC_PREAUTH_RATE_LIMIT_PER_MINUTE` | `300` | Per-IP limit on the RPC route, before auth/DB work. |
| `A2A_DISCOVERY_MAX_TRACKED_KEYS`¹ | `100000` | Cap on distinct client IPs the discovery/RPC-preauth limiters track individually before new ones share an overflow bucket. |
| `A2A_DISCOVERY_OVERFLOW_MULTIPLIER`¹ | `100` | Budget multiplier for that shared overflow bucket, relative to one caller's normal per-minute limit. |
| `A2A_MAX_REQUEST_MB` | `32` | Body size cap for `SendMessage`/`SendStreamingMessage`. |
| `A2A_NON_SEND_MAX_BODY_BYTES` | `65536` | Body size cap for every other method. |
| `A2A_MAX_FILE_MB` | `10` | Per-file cap used when the app's `max_file_size_mb` is 0. |
| `A2A_INLINE_FILE_MAX_BYTES` | `5242880` | Threshold below which an output file is inlined instead of linked. |
| `A2A_FILE_URL_TTL_SECONDS` | `3600` | TTL of an output file's signed `/static` URL. |
| `A2A_FILE_URL_MAX_TTL_SECONDS`¹ | `86400` | Hard ceiling on `verify_expiring_signature`'s TTL (`backend/utils/security.py`) — independent of the variable above, coincidentally sharing its default. |
| `A2A_URI_FETCH_TIMEOUT_SECONDS` | `15` | Total timeout (including redirects) for a FilePart URI fetch. |
| `A2A_MAX_PARTS` | `64` | Max parts accepted per inbound Message. |
| `A2A_MAX_FILE_PARTS` | `10` | Max FileParts accepted per inbound Message. |
| `A2A_TASK_RETENTION_DAYS` | `30` | How long terminal tasks/events/versions/links are kept. |
| `A2A_TASK_TIMEOUT_SECONDS` | `900` | Staleness threshold for the sweep to fail a stuck non-terminal task. |
| `A2A_TURN_MAX_SECONDS` | `900` | Hard wall-clock cap on one turn's streaming section (bridge side). |
| `A2A_SWEEP_INTERVAL_SECONDS` | `600` | How often the leader-locked retention/stale sweep runs. |
| `A2A_EVENT_RETENTION_MINUTES` | `15` | Shorter purge window for a terminal task's own events. |
| `A2A_EVENT_POLL_SECONDS` | `0.5` | Poll interval of the SDK's DB event stream. |
| `A2A_STREAM_COALESCE_MS` | `250` | Token-coalescing window for one SSE artifact chunk. `0` disables coalescing. |
| `A2A_KEEPALIVE_SECONDS` | `1.0` | Silent-period keepalive status interval (bounds remote-cancel latency). |
| `A2A_PURGE_GRACE_SECONDS` | `5` | Grace period before a scheduled purge runs; auto-raised above keepalive + coalesce + 1s. |
| `A2A_STREAM_MAX_SECONDS` | `1800` | Hard wall-clock cap on one SSE response (`SendStreamingMessage`/`SubscribeToTask`). |
| `A2A_STREAM_LIVENESS_SECONDS` | `5.0` | How often an open SSE response re-checks task liveness via the store. |
| `A2A_MAX_CONCURRENT_STREAMS_PER_APP` | `10` | Bulkhead cap per app. `0` = unlimited. |
| `A2A_MAX_CONCURRENT_STREAMS_PER_KEY` | `5` | Bulkhead cap per API key. `0` = unlimited. |
| `A2A_MAX_CONCURRENT_STREAMS_WORKER` | `40` | Bulkhead cap per worker process; auto-clamped below `UVICORN_LIMIT_CONCURRENCY`. |
| `A2A_STATUS_UPDATES` | `false` | Include thinking/tool-start/tool-end status messages in task history. |
| `A2A_SDK_DEBUG` | `false` | Raise the `a2a`/`a2a.server` loggers to DEBUG (off by default: the SDK logs full request bodies at DEBUG). |

¹ Not read through `a2a_config.py` — see the exceptions listed above the table.

Deployment-related variables (`UVICORN_*`, `CADDY_TRUSTED_PROXIES`, `ALEMBIC_LOCK_TIMEOUT`, ...) are covered in [Operations / deployment runbook](#operations--deployment-runbook) below and documented in `docker/.env.example`.

## Manual conformance (a2a-tck)

A2A's spec conformance is verified manually with the [a2a-tck](https://github.com/a2aproject/a2a-tck) test compatibility kit; it is not run in CI.

1. Install the TCK, pinning a version that targets protocol v1.0 — check its README for the current recommended version/tag, since the flag names below may change between TCK releases.
2. Bring up the local stack: `cd docker && docker compose up -d --build`.
3. Create an app with a slug, an agent with A2A enabled (`public` visibility), and an app API key.
4. Point the TCK at `http://localhost/a2a/v1/apps/<slug>/agents/<id>`, configuring it to send the `X-API-KEY` header with the created key (consult the TCK's own README for the exact flag/config key it uses for a static auth header — this changes between TCK releases, so it is deliberately not hard-coded here).
5. Expect, and do not try to "fix", failures in these deliberately unsupported categories: push notifications, any auth scheme other than API key, the REST/gRPC bindings, and `input_required` multi-turn flows. **Never** change task-status semantics to make the TCK pass; a masked failure is a worse outcome than a documented one.

## Operations / deployment runbook

### Caddy routing

`docker/Caddyfile` routes `/a2a/*` and `/.well-known/agent-card.json` to the backend in their **own** `handle` block, separate from the rest of the backend routes, so that:

- SSE responses (`SendStreamingMessage`/`SubscribeToTask`) are never gzip/zstd-encoded or buffered — `encode` is not applied to this block, and the reverse proxy uses `flush_interval -1`.
- The route gets its own request-body ceiling (`A2A_CADDY_MAX_REQUEST_BODY`, default `40MB`) as a blunt perimeter guard above `A2A_MAX_REQUEST_MB` — the backend's own `read_body_capped` is the precise, authoritative cap; Caddy's only needs enough headroom not to reject a legitimate request before the backend's own 413 does.
- There is deliberately **no** per-route request-body read timeout in Caddy: Go's `http.Server` only has a connection-wide read timeout, which would cut off slow uploads and long-lived A2A SSE streams alike. Time-bounding A2A requests is the backend's job (`A2A_TURN_MAX_SECONDS`, `A2A_STREAM_MAX_SECONDS`), not Caddy's.

### Trusted proxies and a load balancer/CDN in front of Caddy

The default single-host deployment has Caddy as the only ingress, with `backend:8000` never published to the host — only Caddy (and other containers on the same Docker network) can reach it. In that default setup:

- Caddy's `trusted_proxies` is left unset, which makes Caddy **overwrite** any inbound `X-Forwarded-For` with the real TCP peer address before forwarding, rather than appending to it.
- uvicorn is started with `--proxy-headers --forwarded-allow-ips=${UVICORN_FORWARDED_ALLOW_IPS:-<RFC1918 ranges>}` so `request.client.host` reflects the real client IP rather than Caddy's. `request.client.host` is what the A2A discovery and RPC-preauth per-IP limiters key on, and it is also what the LOCAL-mode login throttle reads — the A2A stream bulkhead is **not** affected by it, since it keys its per-app/per-key counters on `app_id`/`api_key_id` from the resolved call scope, never on the client IP. **Never set this to `*`**: uvicorn would then trust whatever `X-Forwarded-For` any client sends, letting it spoof its own IP against every IP-keyed limiter.

If a TLS-terminating load balancer or CDN sits **in front of** Caddy (not the default topology):

- Set `CADDY_TRUSTED_PROXIES` to that LB's CIDR(s) so Caddy trusts and preserves the LB's `X-Forwarded-For` instead of overwriting it with the LB's own address.
- If the LB's own address is **outside RFC1918** (a public IP), also append that CIDR to `UVICORN_FORWARDED_ALLOW_IPS` — Caddy forwards `"client, lb_ip"` and uvicorn reads right-to-left, so without this every client behind that LB would again collapse onto one shared IP (and therefore one rate-limit bucket) from the backend's point of view.
- The load balancer **must overwrite** `X-Forwarded-For`, never append a second untrusted value to it — `backend/services/auth/login_throttle.py`'s LOCAL-mode lockout reads the **leftmost** entry directly, and an appending LB makes that entry spoofable.
- **Never** set `CADDY_TRUSTED_PROXIES` to `0.0.0.0/0`, to "all private ranges", or to any range that end users (not just the LB) can connect from — doing so lets any client spoof its own IP against the A2A limiters and the login throttle alike.
- Set `A2A_PUBLIC_BASE_URL` (or `FRONTEND_URL`) to the real public `https://` URL — not `http://localhost` — since cards built from the wrong scheme/host would otherwise be unusable by external A2A clients.

### TLS before exposing A2A beyond localhost

Everything above assumes TLS terminates somewhere in front of the backend. Before letting any A2A traffic reach this stack from outside `localhost`, terminate TLS — either turn on Caddy's automatic HTTPS (see `docker/README.md`, "Paso a HTTPS") or put a TLS-terminating load balancer in front of Caddy as described above — and set `A2A_PUBLIC_BASE_URL` to that `https://` origin. Over plain HTTP, both the `X-API-KEY` header on every RPC call and the signed `/static` file URLs A2A hands out travel in cleartext, so anything on the network path between a caller and the backend can read (and, for the API key, replay) them. This applies to **every** non-local deployment, not just the LB/CDN topology above.

### IPv6 shared-bucket caveat

This stack's compose file publishes `${HTTP_PORT:-80}:80` without pinning a family, so Docker also listens on `[::]:80`. Docker's userland-proxy NATs that IPv6 traffic through the bridge's IPv4 gateway, so Caddy sees **all** inbound IPv6 clients as the same source address — they all share one rate-limit bucket with each other (though not with IPv4 clients). This is a documented limitation, not something A2A changes; isolating IPv6 clients for real requires either a native IPv6 Docker network or publishing IPv4 only and serving IPv6 from a separate front end that forwards the real client IP (which then falls under the load-balancer case above).

### Graceful shutdown pairing

On `SIGTERM`, uvicorn stops accepting new connections and gives in-flight ones — including open A2A SSE streams — up to `UVICORN_GRACEFUL_SHUTDOWN_SECONDS` (default 20 s) before forcing them closed; FastAPI's lifespan `shutdown` (which includes `close_runtime`, writing a `FAILED` status for every task still owned by this worker, with its own ~10 s internal timeout) runs **after** that window. Two things must hold for this to actually happen:

- The backend container's `CMD` must `exec` uvicorn as the final step (see `backend/Dockerfile`) so uvicorn — not a wrapping `sh` — is PID 1 and receives `SIGTERM` directly; otherwise `docker stop` waits out the full grace period and then `SIGKILL`s without the lifespan ever running.
- Docker Compose's `stop_grace_period` for the backend service (45 s) must stay **above** `UVICORN_GRACEFUL_SHUTDOWN_SECONDS` plus `close_runtime`'s own timeout plus margin for the rest of the lifespan — raising one without raising the other reintroduces the same failure.

### Per-worker in-memory limiter caveat

Every rate limiter and bulkhead counter described above (discovery, RPC pre-auth, the execution `agent_rate_limit` budget, and the stream bulkhead's per-app/per-key counters) lives **in one worker process's memory**. With `UVICORN_WORKERS=N`, the real cross-deployment limit is approximately `N ×` the configured value. Only the per-worker stream cap (`A2A_MAX_CONCURRENT_STREAMS_WORKER`) is inherently worker-scoped by design (it protects that one process's event loop), so it is not affected by this caveat the same way.

### Kubernetes / Helm notes

This repository does not ship Kubernetes manifests or Helm charts — they live in a separate `mattinai-infra` repository. If/when porting this deployment to a Helm chart, carry these constraints over:

- `terminationGracePeriodSeconds >= 45` on the backend pod (matching the Compose `stop_grace_period` above), so Kubernetes doesn't `SIGKILL` the pod before uvicorn's own graceful-shutdown window plus `close_runtime` finish.
- **Always set `UVICORN_FORWARDED_ALLOW_IPS` explicitly** to the ingress controller's own pod IPs/CIDR — **never leave this repo's RFC1918 default in a cluster**: in a Kubernetes cluster the pod/service CIDR is itself typically RFC1918, so that default would trust `X-Forwarded-For` from *every* pod and VPC peer, not just the ingress, letting any workload in the cluster spoof a client IP against the A2A limiters and the LOCAL-mode login throttle.
- Pair that with a `NetworkPolicy` restricting the backend Service's inbound traffic to the ingress controller only, so nothing else in the cluster can reach the backend directly to exploit that trust in the first place.
- The ingress controller **must overwrite** `X-Forwarded-For`, never append a second value to an already-present one — same reasoning as the LB case above: the LOCAL-mode login throttle reads the **leftmost** entry directly, and an appending ingress makes that entry spoofable by whatever sent the original request.
- Disable ingress response buffering and raise the body size limit for `/a2a/*` at the ingress controller (the equivalent of this repo's Caddy `handle @a2a` block) — an ingress that buffers SSE responses or caps the body below `A2A_MAX_REQUEST_MB` breaks streaming and large sends respectively.
- Route `/.well-known/agent-card.json` to the backend service, not to a default/catch-all backend (the frontend, typically) — it is easy to miss since it has no `/a2a/` prefix.

## Troubleshooting

| Symptom | Likely cause |
|---------|---------------|
| 404 on every A2A endpoint | `A2A_ENABLED=false`; check the app slug; check `a2a_enabled` and visibility on the agent; check the app/agent isn't frozen. |
| 401 on the RPC endpoint | Missing, invalid, revoked or other-app `X-API-KEY` on a `public`-visibility agent (an `api_key`-visibility agent with no valid key is 404, not 401). |
| 413 on `SendMessage`/`SendStreamingMessage` | Body over `A2A_MAX_REQUEST_MB`, or a single file over the effective per-file cap. |
| 413/empty response on `GetTask`/`CancelTask`/etc. | Body over `A2A_NON_SEND_MAX_BODY_BYTES` — these methods only ever need a short `params.id`. |
| 429 on discovery (card/catalog) | Over `A2A_DISCOVERY_RATE_LIMIT_PER_MINUTE` for that client IP; does not affect the app's execution budget. |
| 429 on the RPC endpoint before auth | Over `A2A_RPC_PREAUTH_RATE_LIMIT_PER_MINUTE` for that client IP. |
| 429 (JSON-RPC error with a retry hint) on a stream | The per-app/per-key/per-worker stream bulkhead is full; retry shortly. |
| Task stuck non-terminal past `A2A_TASK_TIMEOUT_SECONDS` | Expect the next sweep (`A2A_SWEEP_INTERVAL_SECONDS`) to mark it `failed`; if the owning worker crashed before ever calling `start_work()`, the task may have no `last_updated` at all — see known limitations below. |

## Known limitations

These are documented, deliberate trade-offs — not bugs to silently work around:

- **No push notifications.** The card advertises `push_notifications: false`; the push-config methods return the SDK's not-supported error.
- **API-key auth only.** No OAuth2/OIDC/mTLS security scheme.
- **JSON-RPC binding only.** No REST (HTTP+JSON) or gRPC binding.
- **Per-worker in-memory limiters.** See the dedicated section above.
- **SDK 1.2.2 known behaviours**: a rejected `SendMessage` naming an already-terminal `taskId` leaks two `EventQueueSource` tasks per SDK internals — Mattin's router pre-checks and rejects such sends **before** dispatch (RB-5) specifically to avoid hitting this path. Task row rewrites include the full artifact/history JSON on every save, so very long-running turns with verbose output put non-trivial write load on Postgres; coalescing (`A2A_STREAM_COALESCE_MS`) and disabling status spam (`A2A_STATUS_UPDATES=false` by default) bound this, and the dedicated event-retention window (`A2A_EVENT_RETENTION_MINUTES`) keeps terminal-task event history from accumulating indefinitely.
- **Zombie tasks with no `last_updated`.** A task that crashes before its executor ever calls `start_work()` (or one resurrected by the SDK's `ensure_task_id` after a race with a purge) can have no `last_updated` timestamp at all. Neither the stale-task sweep nor the retention sweep currently matches rows with a `NULL` timestamp, so such a task is not automatically cleaned up today; the periodic orphan pass (which matches by owner, not by timestamp) is the only backstop that eventually removes it if its owning agent/app is deleted. A future migration adding a Mattin-owned `created_at` column (with `COALESCE(last_updated, created_at)` in both sweeps) would close this gap.
- **Downgrading the `a2a001` migration is a maintenance-window operation on a large installation.** It rewrites every row of `Conversation` and the agent-execution-event table under an `ACCESS EXCLUSIVE` lock (to recreate the native PG enums without the `A2A` value) and permanently relabels any A2A-sourced rows back to `API`/`PUBLIC_API` — that relabeling cannot be undone by re-upgrading. The preferred rollback path for a bad A2A release is deploying the previous backend image with the **schema left at `a2a001`**, not running `alembic downgrade`. Multi-replica deployments that each run `alembic upgrade head` on startup can race on this (and any other) migration; a single-runner migration job or a Postgres advisory lock around the upgrade step is the standard fix, pre-existing and not specific to A2A.

## See Also

- [Public API](../api/public-api.md) — The API-key auth and rate-limiting model A2A reuses
- [MCP Integration](mcp-integration.md) — The other external-tool-facing protocol Mattin supports
- [Agent System](agent-system.md) — Agent execution engine that both surfaces drive
- [Agent Metrics](../guides/agent-metrics.md) — Where the `A2A` channel shows up in dashboards
- [Deployment Guide](../guides/deployment.md) — Docker Compose topology, Caddy, and uvicorn configuration
- [A2A Protocol specification](https://a2aproject.github.io/A2A/) — Official protocol documentation
- [a2a-tck](https://github.com/a2aproject/a2a-tck) — The test compatibility kit used for manual conformance checks
