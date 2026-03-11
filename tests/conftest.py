"""
Shared pytest fixtures for Mattin AI test suite.

Architecture:
  - test_engine  (session-scoped): creates the test DB schema once per session
  - db           (function-scoped): per-test session with connection-level rollback
  - client       (function-scoped): FastAPI TestClient with get_db overridden
  - fake_user / fake_app / fake_agent: convenience fixtures for common entities
  - auth_headers : Bearer token for fake_user via /internal/auth/dev-login

Transaction isolation strategy:
  Each test gets a fresh connection with an explicit BEGIN. The Session is created
  with join_transaction_mode="create_savepoint" so that service-level session.commit()
  calls emit SAVEPOINT / RELEASE SAVEPOINT rather than committing to the DB.
  After the test, connection.rollback() undoes ALL changes — nothing persists between tests.

  Note: Session(bind=connection) uses the SA 2.x deprecated `bind` kwarg, which
  remains functional in 2.x and is the standard pattern for this use-case.
  It will be replaced with the SA 3.0 API when that version is adopted.
"""

import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = os.environ.get(
    "SQLALCHEMY_DATABASE_URI",
    "postgresql://test_user:test_pass@localhost:5433/test_db",
)


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_engine():
    """
    Create a SQLAlchemy engine pointing to the test DB and set up the schema.
    Runs once for the entire pytest session.
    Schema is created via Base.metadata.create_all (faster than alembic for tests).
    """
    # Import models so SQLAlchemy registers them with Base.metadata
    import models  # noqa: F401 — registers all ORM models
    from db.database import Base

    engine = create_engine(
        TEST_DATABASE_URL,
        pool_size=5,
        max_overflow=2,
        pool_pre_ping=True,
        echo=False,
    )

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db(test_engine):
    """
    Per-test database session with automatic rollback after each test.

    Uses a connection-level transaction so that service commits (session.commit())
    only emit SAVEPOINTs. The outer BEGIN is rolled back unconditionally at teardown,
    leaving the DB in the same state as before the test.
    """
    connection = test_engine.connect()
    transaction = connection.begin()

    # SA 2.x: bind= is deprecated but functional; join_transaction_mode ensures
    # session.commit() uses SAVEPOINTs within our outer transaction.
    session = Session(  # noqa: SA20-deprecated-bind
        bind=connection,
        join_transaction_mode="create_savepoint",
        autocommit=False,
        autoflush=True,
    )

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(db):
    """
    FastAPI TestClient with the get_db dependency overridden to use the test session.

    All HTTP requests made through this client will share the same test DB session,
    making test-inserted data visible to the app without committing to the real DB.
    """
    from backend.main import app
    from db.database import get_db

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client

    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Entity fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def fake_user(db):
    """A persisted (but not committed to real DB) test User."""
    from models.user import User

    user = User(
        email="testuser@mattin-test.com",
        name="Test User",
        is_active=True,
    )
    db.add(user)
    db.flush()  # assigns user_id without committing the outer transaction
    return user


@pytest.fixture(scope="function")
def fake_app(db, fake_user):
    """A test App owned by fake_user."""
    from models.app import App

    app_obj = App(
        name="Test Workspace",
        slug="test-workspace-fixture",
        owner_id=fake_user.user_id,
        agent_rate_limit=0,
        max_file_size_mb=10,
    )
    db.add(app_obj)
    db.flush()
    return app_obj


@pytest.fixture(scope="function")
def fake_ai_service(db, fake_app):
    """A test AIService (OpenAI provider) linked to fake_app."""
    from models.ai_service import AIService

    svc = AIService(
        name="Test OpenAI Service",
        provider="OpenAI",
        api_key="sk-test-key",  # pragma: allowlist secret
        app_id=fake_app.app_id,
    )
    db.add(svc)
    db.flush()
    return svc


@pytest.fixture(scope="function")
def fake_agent(db, fake_app, fake_ai_service):
    """A minimal test Agent in fake_app."""
    from models.agent import Agent

    agent = Agent(
        name="Test Agent",
        description="Agent for testing",
        system_prompt="You are a helpful test assistant.",
        app_id=fake_app.app_id,
        service_id=fake_ai_service.service_id,
        has_memory=False,
        temperature=0.7,
    )
    db.add(agent)
    db.flush()
    return agent


@pytest.fixture(scope="function")
def fake_api_key(db, fake_app, fake_user):
    """An active APIKey for fake_app."""
    from models.api_key import APIKey
    from datetime import datetime

    key = APIKey(
        key="test-api-key-for-integration-tests-only",  # pragma: allowlist secret
        name="Test API Key",
        app_id=fake_app.app_id,
        user_id=fake_user.user_id,
        is_active=True,
        created_at=datetime.now(),
    )
    db.add(key)
    db.flush()
    return key


# ---------------------------------------------------------------------------
# Auth fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def auth_headers(fake_user, client, db):
    """
    Bearer token headers for fake_user obtained via /internal/auth/dev-login.

    Because client uses the same test session (db) as fake_user, the endpoint
    can find the user without it being committed to the real DB.
    """
    db.flush()
    response = client.post(
        "/internal/auth/dev-login",
        json={"email": fake_user.email},
    )
    assert response.status_code == 200, (
        f"Dev login failed ({response.status_code}): {response.text}"
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def owner_headers(fake_user, fake_app, client, db):
    """
    Auth headers for fake_user who is the owner of fake_app.
    Ensures the AppCollaborator OWNER record exists so RBAC checks pass.
    """
    from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
    from datetime import datetime

    collab = AppCollaborator(
        app_id=fake_app.app_id,
        user_id=fake_user.user_id,
        role=CollaborationRole.OWNER,
        invited_by=fake_user.user_id,
        status=CollaborationStatus.ACCEPTED,
        accepted_at=datetime.now(),
    )
    db.add(collab)
    db.flush()

    response = client.post(
        "/internal/auth/dev-login",
        json={"email": fake_user.email},
    )
    assert response.status_code == 200, (
        f"Dev login failed ({response.status_code}): {response.text}"
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
