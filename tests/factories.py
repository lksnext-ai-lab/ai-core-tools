"""
factory-boy factories for Mattin AI ORM models.

Usage in tests:
    from tests.factories import UserFactory, AppFactory

    user = UserFactory(db=session)          # creates and flushes a User
    app  = AppFactory(db=session, owner=user)

All factories accept a `db` keyword argument (SQLAlchemy session).
Objects are added and flushed (not committed) so they're visible within
the current test transaction but do not persist after rollback.
"""

import factory
from datetime import datetime
from factory.alchemy import SQLAlchemyModelFactory


# ---------------------------------------------------------------------------
# Base factory — all factories inherit from this
# ---------------------------------------------------------------------------

class BaseFactory(SQLAlchemyModelFactory):
    class Meta:
        abstract = True
        sqlalchemy_session_persistence = "flush"  # flush after create, no commit


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class UserFactory(BaseFactory):
    class Meta:
        model = "models.user.User"  # resolved lazily

    email = factory.Sequence(lambda n: f"user{n}@mattin-test.com")
    name = factory.Faker("name")
    is_active = True
    create_date = factory.LazyFunction(datetime.now)


# ---------------------------------------------------------------------------
# App (Workspace)
# ---------------------------------------------------------------------------

class AppFactory(BaseFactory):
    class Meta:
        model = "models.app.App"

    name = factory.Sequence(lambda n: f"Test App {n}")
    slug = factory.Sequence(lambda n: f"test-app-{n}")
    agent_rate_limit = 0
    max_file_size_mb = 10
    create_date = factory.LazyFunction(datetime.now)
    owner = factory.SubFactory(UserFactory)

    @factory.lazy_attribute
    def owner_id(self):
        return self.owner.user_id if self.owner else None


# ---------------------------------------------------------------------------
# AIService
# ---------------------------------------------------------------------------

class AIServiceFactory(BaseFactory):
    class Meta:
        model = "models.ai_service.AIService"

    name = factory.Sequence(lambda n: f"AI Service {n}")
    provider = "OpenAI"
    api_key = "sk-test-key"  # pragma: allowlist secret
    endpoint = None
    app = factory.SubFactory(AppFactory)

    @factory.lazy_attribute
    def app_id(self):
        return self.app.app_id if self.app else None


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class AgentFactory(BaseFactory):
    class Meta:
        model = "models.agent.Agent"

    name = factory.Sequence(lambda n: f"Agent {n}")
    description = "A test agent"
    system_prompt = "You are a helpful test assistant."
    has_memory = False
    temperature = 0.7
    request_count = 0
    is_tool = False
    app = factory.SubFactory(AppFactory)
    ai_service = factory.SubFactory(AIServiceFactory)

    @factory.lazy_attribute
    def app_id(self):
        return self.app.app_id if self.app else None

    @factory.lazy_attribute
    def service_id(self):
        return self.ai_service.service_id if self.ai_service else None


# ---------------------------------------------------------------------------
# APIKey
# ---------------------------------------------------------------------------

class APIKeyFactory(BaseFactory):
    class Meta:
        model = "models.api_key.APIKey"

    key = factory.Sequence(lambda n: f"test-api-key-{n:04d}-integration-only")  # pragma: allowlist secret
    name = factory.Sequence(lambda n: f"Test Key {n}")
    is_active = True
    created_at = factory.LazyFunction(datetime.now)
    app = factory.SubFactory(AppFactory)
    user = factory.SubFactory(UserFactory)

    @factory.lazy_attribute
    def app_id(self):
        return self.app.app_id if self.app else None

    @factory.lazy_attribute
    def user_id(self):
        return self.user.user_id if self.user else None


# ---------------------------------------------------------------------------
# AppCollaborator
# ---------------------------------------------------------------------------

class AppCollaboratorFactory(BaseFactory):
    class Meta:
        model = "models.app_collaborator.AppCollaborator"

    app = factory.SubFactory(AppFactory)
    user = factory.SubFactory(UserFactory)
    role = factory.LazyAttribute(lambda _: __import__(
        "models.app_collaborator", fromlist=["CollaborationRole"]
    ).CollaborationRole.EDITOR)
    status = factory.LazyAttribute(lambda _: __import__(
        "models.app_collaborator", fromlist=["CollaborationStatus"]
    ).CollaborationStatus.ACCEPTED)
    invited_by = factory.LazyAttribute(lambda obj: obj.user.user_id)
    invited_at = factory.LazyFunction(datetime.now)
    accepted_at = factory.LazyFunction(datetime.now)

    @factory.lazy_attribute
    def app_id(self):
        return self.app.app_id if self.app else None

    @factory.lazy_attribute
    def user_id(self):
        return self.user.user_id if self.user else None


# ---------------------------------------------------------------------------
# Helper: bind factories to a session at test time
# ---------------------------------------------------------------------------

def configure_factories(session) -> None:
    """
    Bind all factories to a SQLAlchemy session.
    Call this at the start of a test or fixture that uses factories.

    Example:
        def test_something(db):
            configure_factories(db)
            user = UserFactory()
            app  = AppFactory(owner=user)
    """
    for factory_cls in [
        UserFactory,
        AppFactory,
        AIServiceFactory,
        AgentFactory,
        APIKeyFactory,
        AppCollaboratorFactory,
    ]:
        factory_cls._meta.sqlalchemy_session = session
