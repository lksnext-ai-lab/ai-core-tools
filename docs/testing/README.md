# Testing Guide — Mattin AI

> This guide is for developers who are new to testing. It covers everything from running your first test to writing new ones.

## Overview

The test suite is organized in a **pyramid**:

```
        /\
       /E2E\        ← few, slow (Playwright — Phase 5)
      /------\
     /Integr. \     ← moderate (real PostgreSQL, full HTTP stack)
    /----------\
   /  Unit tests \  ← many, fast (pure Python, no DB)
  /--------------\
```

Tests live in `tests/` and follow a clear directory structure:

```
tests/
├── conftest.py                    ← shared fixtures (the "test helpers" everyone uses)
├── factories.py                   ← quick object builders for test data
├── unit/
│   └── services/
│       ├── test_rate_limit_service.py
│       ├── test_api_key_service.py
│       └── test_agent_execution_service.py
└── integration/
    └── routers/
        ├── internal/
        │   └── test_auth.py
        └── public/
            └── test_rate_limit.py
```

---

## Quick Start

### 1. Install test dependencies

```bash
poetry install --with test
```

### 2. Start the test database

The test database is a separate PostgreSQL instance that lives only in memory (nothing is saved to disk). Easiest way is to use the helper script that starts and stops it automatically:

```bash
./scripts/test.sh -m integration
```

Or start it manually:

```bash
docker compose -f docker/docker-compose.yaml --profile test up -d db_test
```

> **Why a separate database?** We never want tests touching real data. The test DB is on port **5433** (production is 5432) and resets every time Docker restarts it.

### 3. Run the tests

```bash
# Fast unit tests — no database needed, runs in seconds
pytest tests/unit/ -v

# Integration tests — needs the test DB running (step 2)
pytest tests/integration/ -v

# Everything at once, with coverage report
pytest -v --cov=backend --cov-report=term-missing
```

---

## What Each Test Type Does

### Unit tests (`tests/unit/`)

These test **a single piece of logic in isolation**. No database, no HTTP requests, no LLM calls. Everything external is replaced with a "mock" (a fake stand-in).

Example: testing that `RateLimitService` blocks after N requests is a unit test — it's just math and counters, no DB needed.

**Pros:** Very fast (milliseconds each). Run them constantly as you work.

### Integration tests (`tests/integration/`)

These test **the full chain**: HTTP request → router → service → real database → response. They use a real PostgreSQL database but all data is rolled back after each test (so nothing persists).

Example: testing that `POST /internal/auth/login` returns session cookies is an integration test — it needs to look up credentials and write a refresh token row in the DB.

**Pros:** Catches bugs that unit tests miss (wrong SQL, missing foreign keys, auth issues).

### Frontend tests (`frontend/tests/`)

The frontend has two harnesses:

| Harness | Location | Runner | Use for |
|---------|----------|--------|---------|
| Pure logic | `frontend/tests/*.test.cjs` | `node --test` | Functions and modules without a DOM |
| Render tests | `frontend/tests/ui/**/*.test.{ts,tsx}` | Vitest + Testing Library (jsdom; config in `frontend/vitest.config.ts`) | Components and pages (for example the App Chat) |

```bash
cd frontend
npm test            # node --test + type check (test:types) + Vitest
npm run test:ui     # Vitest render tests only
```

### Chat tests and LangGraph checkpoints

Backend tests of the App Chat live in `tests/integration/internal_chat/`, with the shared fakes (LLM, retriever, MCP client, metrics write) and world fixture in `_chat_support.py`. The LangGraph checkpoint tables are not part of `Base.metadata`, so they **survive the test schema drop**: assert on threads relative to a baseline taken at the start of the test, never on absolute counts. Some Chat test files deserve a note:

- `test_chat_isolation_concurrency.py` overlaps real turns through `httpx.AsyncClient` + `ASGITransport` with one database session per request (`get_db` is not overridden, so its data is committed and purged by the test) and a fake model that parks calls on per-turn gates, so the overlap is deterministic.
- `test_chat_model_switch.py` switches provider, AI service and model between turns of one conversation (history adaptation, summarization on a smaller window, images, tools, retired models, failures, the answer stamp). Everything runs for real except the LLM boundary, which is `_provider_sim.py`: subclasses of the real LangChain model classes that validate each request with the provider's own installed converter and answer with the message shapes the real adapters produce. **No real provider API is called**: the tests prove the installed converter takes the history and tool calls stay paired, not that Anthropic signatures, OpenAI Responses item pairing or token accounting would be accepted by the real service. Capability and context-window rejections are hand-written rules.
- `tests/unit/tools/middleware/test_history_normalizer.py` (own vs foreign messages, interrupted tool calls, nothing stored is modified) and `test_summary_input_bound.py` (summary input threshold and target, explicit `trim_tokens`, retry only on transient errors) cover the same two mechanisms offline; they reuse `_provider_sim.py`.
- `test_chat_temp_silo_visibility.py` contains a route-enumeration guard: a new route that takes a silo or repository id must pass it, because conversation temp silos have to answer 404 like a missing one.

See [App Chat](../ai/app-chat.md#testing).

---

## Running Specific Tests

```bash
# Run a single test file
pytest tests/unit/services/test_rate_limit_service.py -v

# Run a single test by name
pytest -k "test_blocks_at_limit" -v

# Run all tests matching a pattern
pytest -k "TestRateLimit" -v

# Stop on the first failure
pytest -x -v

# Show print() output inside tests
pytest -s -v
```

---

## Reading Test Output

When a test fails, pytest shows exactly what went wrong:

```
FAILED tests/unit/services/test_rate_limit_service.py::TestLimited::test_blocks_at_limit
AssertionError: assert 1 == 0
  Left:  1   (actual remaining)
  Right: 0   (expected)
```

Read it bottom-up: the assertion error tells you what was different from what you expected.

---

## Next Steps

- [Writing Tests](writing-tests.md) — how to add new unit and integration tests
- [Fixtures Reference](fixtures-reference.md) — all the shared helpers in `conftest.py`
- [CI/CD](ci.md) — how tests run automatically on GitHub Actions

---

## Copilot Agent

Use the `@test` Copilot agent for help with anything testing-related:

- Writing new unit or integration tests for a feature
- Debugging a failing test
- Understanding which fixtures to use
- Adding test data with factories
- Deciding between unit vs integration for a given scenario

```
@test write integration tests for the new /internal/apps/{id}/widgets endpoint
@test this test is failing with a 403 — why?
@test add a fixture for the Widget model
```
