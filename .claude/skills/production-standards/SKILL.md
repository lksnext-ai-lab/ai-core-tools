---
name: production-standards
description: Best-practice rubric for production readiness in Mattin AI — concurrency, fault tolerance/resilience, isolation, observability, and operations. Background reference for reliability-auditor, production-readiness-analyst, and implementation experts.
user-invocable: false
allowed-tools: Read, Grep, Glob
---

# production-standards — Best-practice rubric

The standard each reliability/production finding is held against. Concrete, stack-specific (FastAPI async · SQLAlchemy 2.x · PostgreSQL · LangChain/LangGraph 1.x · Qdrant · Docker/Caddy/K8s · multi-tenant by `app_id`). A finding states which rule below it violates and the conforming pattern.

## A. Concurrency

| # | Standard | Conforming pattern in this stack |
|---|---|---|
| C1 | **No check-then-act on shared state.** | Counters/quotas (`UsageRecord`, `MarketplaceUsage`, request counts, `TierConfig` limits): atomic `UPDATE t SET n = n + :d WHERE ...` or an optimistic `version` column, **not** read→`+1`→write in Python. |
| C2 | **Guard contended rows.** | `select(...).with_for_update()` (pessimistic) or optimistic concurrency for rows multiple requests mutate; keep the locked transaction short. |
| C3 | **One session per request/task.** | `Depends(get_db)` async session scoped to the request; never share a session across `await` fan-out or across `asyncio` tasks; never reuse across replicas. |
| C4 | **Pool sized for concurrency.** | DB/HTTP pool size ≥ expected concurrent requests per replica; fail-fast/timeout on pool checkout; surface pool exhaustion in metrics. |
| C5 | **Never block the event loop.** | All I/O `await`ed and async-native; CPU/blocking work offloaded (thread/process executor or a task); no sync DB driver / `requests` / blocking file ops in `async def`. |
| C6 | **Bound fan-out.** | `asyncio.gather` over user-sized inputs is wrapped with a `Semaphore`; batch embedding/vectorization has a concurrency cap. |
| C7 | **Idempotent external writes.** | Public/MCP write operations tolerate retries (idempotency key or natural idempotency); no duplicate side effects on client retry. |
| C8 | **Single-runner for scheduled work.** | Crawl/cron/scheduler jobs in a multi-replica (K8s) deployment use a distributed lock / leader election, not "every replica runs it". |
| C9 | **Per-thread checkpointer safety.** | Concurrent messages on the same `thread_{agent_id}_{session_id}` are serialized; no interleaved checkpoint writes corrupting memory. |

## B. Fault tolerance / resilience

| # | Standard | Conforming pattern |
|---|---|---|
| F1 | **Timeout every external call.** | Explicit timeouts on LLM, embeddings, Qdrant/PGVector, web scraping, SharePoint, outbound MCP, and DB statements. No unbounded waits. |
| F2 | **Retry transient failures only.** | Exponential backoff + jitter, bounded attempts, only for idempotent/transient errors (`.with_retry()` for LangChain runnables). No retry on 4xx/validation. |
| F3 | **Fallbacks for provider outages.** | `.with_fallbacks()` for model/provider failure; degrade gracefully (silo/RAG down → answer without retrieval) rather than hard-failing the request. |
| F4 | **Bulkhead slow dependencies.** | A slow/blocked dependency cannot exhaust the shared pool or event loop for unrelated traffic; separate limits per dependency where it matters. |
| F5 | **Handle partial failure.** | Batch uploads / multi-file vectorization / crawl jobs continue on per-item failure and record it (dead-letter/error capture); they do not abort the whole batch silently. |
| F6 | **Graceful lifecycle.** | FastAPI `lifespan` startup fails fast on missing critical deps; SIGTERM drains in-flight requests, flushes checkpoints, and closes pools before exit. |
| F7 | **Health signals.** | Liveness + readiness endpoints (readiness reflects DB/vector/critical-dep health) wired to the Compose/Helm health checks. |
| F8 | **Clean client errors.** | `HTTPException` with correct codes; never leak stack traces/internals; `Retry-After` on rate-limit/`429`. |

## C. Isolation

| # | Standard | Conforming pattern |
|---|---|---|
| I1 | **Tenant data isolation.** | Every query filtered by `app_id`; vector collections `silo_{id}`; signed static URLs scoped; no cross-tenant bleed via caches or the checkpointer. |
| I2 | **Resource isolation / no noisy neighbor.** | Per-app rate limits (`App.agent_rate_limit`) and tier quotas (`TierConfig`) enforced on `/public/v1` and `/mcp/v1`; per-request timeouts; max payload/file size (`App.max_file_size_mb`). |
| I3 | **Fault isolation.** | One tenant/agent/provider failure is contained — it does not degrade other tenants or take down the process. |
| I4 | **Network isolation.** | Only Caddy publishes port 80; backend/DB/Qdrant stay on the internal network; CORS restricted to `App.agent_cors_origins` (never `*` in prod); secrets never sent to clients. |
| I5 | **Runtime isolation / statelessness.** | App is stateless for horizontal scaling — no in-process mutable global that breaks across replicas; shared state lives in PostgreSQL/cache. |
| I6 | **Resource limits.** | Container CPU/memory requests+limits set in the Helm charts; sensible Uvicorn/worker counts; no unbounded in-memory growth. |

## D. Observability & operations (cross-cut)

| # | Standard | Conforming pattern |
|---|---|---|
| O1 | **Structured logging.** | Project logger (never `print`); right levels; request/correlation context; no secrets/keys/PII in logs. |
| O2 | **Tracing.** | LangSmith per-app (`App.langsmith_api_key`) + global fallback via `backend/tools/langsmith_config.py`; failures are traceable end-to-end. |
| O3 | **Config & secrets.** | All config via env/settings (`backend/utils/config.py`), documented in `.env.example`, validated at startup; no secrets in code/images/logs. |
| O4 | **Migrations.** | Every schema change has an Alembic migration with a tested `downgrade`; no irreversible destructive step without a documented plan/backfill. |
| O5 | **Deploy & rollback.** | Docker/Compose + Helm current; image tags pinned; a rollback path exists; per-environment values correct. |

## Severity guidance

CRITICAL/HIGH: data races on counters (C1/C2), missing timeouts (F1), no fallback on the core chat path (F3), cross-tenant leaks (I1), unenforced rate limits/quotas (I2), event-loop blocking on a hot path (C5). MEDIUM: missing bulkheads, partial-failure gaps, missing readiness probe. LOW: tuning (pool sizes, retry caps) without evidence of a problem.
