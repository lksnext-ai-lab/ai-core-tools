# CI/CD — Automated Tests

Tests run automatically on every push and pull request via GitHub Actions ([`.github/workflows/test.yaml`](../../.github/workflows/test.yaml)).

---

## Jobs

### `unit-tests`

Runs all tests in `tests/unit/`. No database is needed.

- Triggers on: every push to `main`, `develop`, `feat/**`, `fix/**`
- Also runs on pull requests to `main` and `develop`
- Output: coverage report uploaded to Codecov (flag: `unit`)

### `integration-tests`

Runs all tests in `tests/integration/`. Spins up a PostgreSQL + pgvector container.

- Same triggers as unit tests
- The DB container is managed by GitHub Actions `services:` — you don't need to start it manually
- Output: coverage report uploaded to Codecov (flag: `integration`)

### `frontend-lint`

Runs `npm run lint` on the frontend. No tests yet — frontend testing is Phase 5.

---

## Reading CI Results

When a PR is open, GitHub shows a check for each job. Click "Details" on a failing check to see the full log.

Common failure patterns:

| Symptom | Likely cause |
|---------|-------------|
| `ModuleNotFoundError` | Missing import or wrong `pythonpath` |
| `connection refused` | Test DB not ready (integration tests) |
| `AssertionError: assert 404 == 200` | Wrong URL or missing fixture data |
| `sqlalchemy.exc.OperationalError` | DB schema mismatch (run `Base.metadata.create_all` in test) |

---

## Running CI Checks Locally

Before pushing, run the same checks locally:

```bash
# Unit tests (fast — run these constantly)
pytest tests/unit/ -v

# Integration tests (needs test DB)
docker-compose --profile test up -d db_test
pytest tests/integration/ -v

# Full suite with coverage
pytest -v --cov=backend --cov-report=term-missing

# Lint frontend
cd frontend && npm run lint
```

---

## Coverage Targets

| Phase | Target |
|-------|--------|
| After unit tests (now) | ≥ 40% backend |
| After integration tests (now) | ≥ 65% backend |
| After frontend tests (Phase 5) | Meaningful on `api.ts`, hooks, key components |

View coverage locally after a test run:

```bash
pytest --cov=backend --cov-report=html
open htmlcov/index.html
```
