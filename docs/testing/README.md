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

The test database is a separate PostgreSQL instance that lives only in memory (nothing is saved to disk). Start it with:

```bash
docker-compose --profile test up -d db_test
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

Example: testing that `POST /internal/auth/dev-login` returns a token is an integration test — it needs to actually look up a user in the DB.

**Pros:** Catches bugs that unit tests miss (wrong SQL, missing foreign keys, auth issues).

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
