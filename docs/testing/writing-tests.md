# Writing Tests

This guide explains how to add new tests to the Mattin AI project. It assumes you have read the [Testing Overview](README.md).

---

## Deciding What Kind of Test to Write

Ask yourself: **does my code need a database or external service?**

| Code I'm testing | Type | Location |
|-----------------|------|----------|
| Pure logic (math, string formatting, validation) | Unit | `tests/unit/` |
| A service that uses a repository/DB | Unit (mock the repo) | `tests/unit/services/` |
| An API endpoint (needs HTTP + DB) | Integration | `tests/integration/routers/` |
| A full user flow (login → create → chat) | E2E (future) | `tests/e2e/` |

**When in doubt, write a unit test first.** They are faster to write and faster to run.

---

## Writing a Unit Test

Unit tests mock any external dependency (database, LLM, other services).

### Example: Testing a Service

Say you want to test `ConversationService.create_conversation()`. That method needs a DB session. Instead of using a real DB, you mock it:

```python
# tests/unit/services/test_conversation_service.py
import pytest
from unittest.mock import MagicMock
from services.conversation_service import ConversationService


def test_create_conversation_assigns_agent_id(mocker):
    # 1. Create a fake DB session (won't actually call the DB)
    mock_db = MagicMock()

    # 2. Create a fake repository that returns what we want
    mock_conversation = MagicMock()
    mock_conversation.conversation_id = 42
    mock_conversation.agent_id = 1

    # 3. Patch the repository's create method
    mocker.patch(
        "services.conversation_service.ConversationRepository.create",
        return_value=mock_conversation
    )

    # 4. Call the real code
    service = ConversationService()
    result = service.create_conversation(db=mock_db, agent_id=1, user_context={})

    # 5. Assert what you expect
    assert result.agent_id == 1
```

### The `mocker` Fixture

`mocker` comes from `pytest-mock` (installed automatically). Use it to replace real code with fakes:

```python
# Replace a function entirely
mocker.patch("services.some_service.SomeRepository.get", return_value=None)

# Replace a method on an object
mock_repo = mocker.MagicMock()
mock_repo.find_by_id.return_value = some_object

# Spy on a method (runs real code but records calls)
spy = mocker.spy(MyService, "my_method")
```

### Testing Async Code

Many services use `async def`. Mark the test with `@pytest.mark.asyncio` and use `AsyncMock`:

```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_async_method():
    mock_llm = AsyncMock(return_value="LLM response")
    # ... rest of test
```

> **Note:** `asyncio_mode = "auto"` is set in `pyproject.toml`, so you don't always need the decorator. But it's good practice to include it for clarity.

---

## Writing an Integration Test

Integration tests use a real database and make real HTTP requests to the app. They rely on fixtures from `conftest.py`.

### Example: Testing an API Endpoint

```python
# tests/integration/routers/internal/test_agents.py


class TestCreateAgent:
    def test_create_agent_returns_201(self, client, owner_headers, fake_app, db):
        # fake_app already exists in the test DB (via fixture)
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents",
            json={
                "name": "My New Agent",
                "system_prompt": "You are helpful.",
                "service_id": None,  # fill with a real service_id in real tests
            },
            headers=owner_headers,  # authenticated as owner
        )
        assert response.status_code == 201
        assert response.json()["name"] == "My New Agent"

    def test_create_agent_requires_auth(self, client, fake_app):
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents",
            json={"name": "Agent"},
        )
        assert response.status_code in (401, 403)
```

### Key Fixtures You'll Use

| Fixture | What it gives you |
|---------|------------------|
| `client` | A TestClient that talks to the real app (DB overridden) |
| `db` | A database session — add objects with `db.add(obj); db.flush()` |
| `fake_user` | A User already in the DB |
| `fake_app` | An App owned by `fake_user` |
| `fake_agent` | An Agent in `fake_app` |
| `fake_api_key` | An API key for `fake_app` |
| `auth_headers` | `{"Authorization": "Bearer ..."}` — logged in as `fake_user` |
| `owner_headers` | Same as `auth_headers` but also with OWNER role for `fake_app` |

See [Fixtures Reference](fixtures-reference.md) for details on every fixture.

### Adding Your Own Test Data

Inside a test or fixture, use `db.add()` + `db.flush()`:

```python
def test_something(client, db, fake_app, auth_headers):
    from models.skill import Skill

    # Create a Skill in the test DB (only visible within this test)
    skill = Skill(name="My Skill", content="Do something", app_id=fake_app.app_id)
    db.add(skill)
    db.flush()  # ← assigns skill.skill_id without committing to real DB

    response = client.get(
        f"/internal/apps/{fake_app.app_id}/skills",
        headers=auth_headers,
    )
    assert response.status_code == 200
```

> **Why `db.flush()` instead of `db.commit()`?**
> `flush()` makes the data visible within the current test session without actually writing to the real DB. After the test, everything is rolled back automatically.

### Using Factories for Repetitive Setup

When a test needs many objects, use [factory-boy factories](../../tests/factories.py):

```python
from tests.factories import configure_factories, AgentFactory, UserFactory

def test_multiple_agents(client, db, auth_headers):
    configure_factories(db)  # bind factories to the test session

    # Create 5 agents quickly
    agents = [AgentFactory() for _ in range(5)]

    response = client.get("/internal/apps/.../agents", headers=auth_headers)
    assert len(response.json()) >= 5
```

---

## Test Structure Conventions

### File and class naming

```python
# File: tests/unit/services/test_my_service.py
# Class groups related tests; methods describe the specific scenario

class TestHappyPath:
    def test_returns_expected_value(self): ...
    def test_calls_repository_once(self): ...

class TestErrorCases:
    def test_raises_404_when_not_found(self): ...
    def test_raises_400_on_invalid_input(self): ...
```

### Test method names

Use `test_<what>_<when_condition>` format:

```python
def test_login_succeeds_with_valid_email(): ...
def test_login_returns_401_for_unknown_email(): ...
def test_rate_limit_blocks_after_10_requests(): ...
```

### One assertion per test (ideally)

Each test should check one thing. If it fails, you immediately know *what* is broken.

```python
# Good — two separate tests
def test_response_is_200(): assert response.status_code == 200
def test_response_has_token(): assert "access_token" in response.json()

# Acceptable — tightly related assertions in one test
def test_login_response_structure():
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert "user" in response.json()
```

---

## Common Patterns

### Testing that an exception is raised

```python
import pytest
from fastapi import HTTPException

def test_service_raises_404_when_missing(mocker):
    mocker.patch("services.agent_service.AgentRepository.get", return_value=None)
    service = AgentService()

    with pytest.raises(HTTPException) as exc:
        service.get_agent_or_fail(db=MagicMock(), agent_id=999)

    assert exc.value.status_code == 404
```

### Testing that a method was called

```python
def test_repository_create_was_called(mocker):
    mock_repo = mocker.MagicMock()
    service = MyService(repo=mock_repo)

    service.create_something(...)

    mock_repo.create.assert_called_once()
    # Or with specific arguments:
    mock_repo.create.assert_called_once_with(db=mocker.ANY, name="expected")
```

### Parameterized tests (same test with different inputs)

```python
import pytest

@pytest.mark.parametrize("email,expected_status", [
    ("valid@example.com", 200),
    ("not-an-email", 422),
    ("", 422),
])
def test_login_validates_email(client, email, expected_status):
    response = client.post("/internal/auth/dev-login", json={"email": email})
    assert response.status_code == expected_status
```

---

## Checklist Before Submitting

- [ ] Test file is named `test_*.py`
- [ ] Test methods start with `test_`
- [ ] Unit tests do not import or use real DB sessions
- [ ] Integration tests use fixtures from `conftest.py` (not `SessionLocal()` directly)
- [ ] All new code paths have at least one test
- [ ] Tests pass locally: `pytest tests/ -v`
