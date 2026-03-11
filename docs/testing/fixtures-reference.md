# Fixtures Reference

Fixtures are **reusable helpers** that set up test state. They are defined in [`tests/conftest.py`](../../tests/conftest.py) and automatically available in every test file.

> **What is a fixture?** When you add a parameter with a fixture's name to a test function, pytest automatically runs the fixture and passes its result to your test. You don't call it yourself.

```python
# pytest sees `db` and `fake_user` as fixture names → runs them before the test
def test_something(db, fake_user):
    assert fake_user.email == "testuser@mattin-test.com"
```

---

## Database Fixtures

### `test_engine` — session scope

Creates the test database engine and builds the schema (all tables) once per pytest session.

- **Scope:** `session` — runs once for the entire test run
- **You rarely use this directly** — it's used by `db` internally

### `db` — function scope

Provides a SQLAlchemy session for database operations. **All changes are rolled back after each test** — nothing persists between tests.

```python
def test_create_user(db):
    from models.user import User
    user = User(email="test@example.com", name="Test")
    db.add(user)
    db.flush()  # ← makes the user visible in this test's session
    assert user.user_id is not None  # DB assigned an ID
    # After this test, the user is gone (rolled back)
```

**Rules:**
- Use `db.add(obj)` to insert
- Use `db.flush()` to get auto-generated IDs (like `user_id`) without committing
- Do NOT use `db.commit()` — it's not needed and can interfere with rollback
- Do NOT use `SessionLocal()` directly in tests — always use this fixture

### `client` — function scope

A FastAPI `TestClient` pre-configured to use the test database. Any HTTP request you make through this client will use the same `db` session, so test data you add with `db.add()` will be visible to the app.

```python
def test_get_apps(client, auth_headers):
    response = client.get("/internal/apps", headers=auth_headers)
    assert response.status_code == 200
```

---

## Pre-Built Entity Fixtures

These create common database objects. They are all function-scoped (fresh per test) and rolled back after.

### `fake_user`

A `User` object already in the test DB session.

```python
fake_user.email    # "testuser@mattin-test.com"
fake_user.name     # "Test User"
fake_user.user_id  # auto-assigned integer
fake_user.is_active  # True
```

### `fake_app`

An `App` (workspace) owned by `fake_user`.

```python
fake_app.name           # "Test Workspace"
fake_app.slug           # "test-workspace-fixture"
fake_app.owner_id       # fake_user.user_id
fake_app.agent_rate_limit  # 0 (unlimited)
```

### `fake_ai_service`

An `AIService` (OpenAI provider) linked to `fake_app`. Required when creating Agents.

```python
fake_ai_service.provider     # "OpenAI"
fake_ai_service.service_id   # auto-assigned
```

### `fake_agent`

An `Agent` in `fake_app`, using `fake_ai_service`.

```python
fake_agent.name          # "Test Agent"
fake_agent.agent_id      # auto-assigned
fake_agent.has_memory    # False
fake_agent.temperature   # 0.7
```

### `fake_api_key`

An active `APIKey` for `fake_app`. Use this to test public API endpoints that require `X-API-KEY`.

```python
fake_api_key.key        # "test-api-key-for-integration-tests-only"
fake_api_key.is_active  # True
```

---

## Auth Fixtures

### `auth_headers`

Returns a dict with a valid Bearer token for `fake_user`:

```python
# {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9..."}

def test_list_agents(client, auth_headers, fake_app):
    response = client.get(
        f"/internal/apps/{fake_app.app_id}/agents",
        headers=auth_headers,
    )
    assert response.status_code == 200
```

> **How it works:** Calls `POST /internal/auth/dev-login` with `fake_user.email`, gets a JWT, returns it as headers.

### `owner_headers`

Same as `auth_headers`, but also creates an `AppCollaborator` record with the `OWNER` role for `fake_app`. Use this for endpoints that require ownership permissions.

```python
def test_delete_app(client, owner_headers, fake_app):
    response = client.delete(
        f"/internal/apps/{fake_app.app_id}",
        headers=owner_headers,
    )
    assert response.status_code in (200, 204)
```

> **When to use `auth_headers` vs `owner_headers`?**
> - `auth_headers` — for reading data, or any endpoint that just needs a logged-in user
> - `owner_headers` — for endpoints protected by `@require_min_role(AppRole.OWNER)` or `ADMINISTRATOR`

---

## Dependency Order

Fixtures can depend on each other. Here's the full dependency graph:

```
test_engine
    └── db
         ├── fake_user
         │    └── fake_app
         │         ├── fake_ai_service
         │         │    └── fake_agent
         │         └── fake_api_key
         └── client
              ├── auth_headers  (needs fake_user + client + db)
              └── owner_headers (needs fake_user + fake_app + client + db)
```

When you request `auth_headers`, pytest automatically also creates `fake_user`, `client`, and `db`. You don't need to list all of them.

---

## Adding Your Own Fixtures

Add fixtures to `tests/conftest.py` (shared everywhere) or to a local `conftest.py` in a subdirectory (only available in that directory and below).

```python
# tests/conftest.py or tests/integration/conftest.py

@pytest.fixture
def fake_silo(db, fake_app):
    """A Silo in fake_app for RAG tests."""
    from models.silo import Silo
    silo = Silo(name="Test Silo", app_id=fake_app.app_id)
    db.add(silo)
    db.flush()
    return silo
```

Then use it in tests:

```python
def test_silo_appears_in_list(client, auth_headers, fake_app, fake_silo):
    response = client.get(
        f"/internal/apps/{fake_app.app_id}/silos",
        headers=auth_headers,
    )
    assert any(s["name"] == "Test Silo" for s in response.json())
```

---

## Factories

For creating many objects quickly, use factories from [`tests/factories.py`](../../tests/factories.py):

```python
from tests.factories import configure_factories, UserFactory, AppFactory, AgentFactory

def test_many_agents(client, db, auth_headers):
    configure_factories(db)   # ← must call this first to bind factories to the test session

    agents = [AgentFactory() for _ in range(10)]

    # All 10 agents are now in the test DB, rolled back after test
```

Available factories: `UserFactory`, `AppFactory`, `AIServiceFactory`, `AgentFactory`, `APIKeyFactory`, `AppCollaboratorFactory`.
