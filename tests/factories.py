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

from models.user import User
from models.app import App
from models.ai_service import AIService
from models.agent import Agent
from models.api_key import APIKey
from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
from models.silo import Silo


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
        model = User

    email = factory.Sequence(lambda n: f"user{n}@mattin-test.com")
    name = factory.Faker("name")
    is_active = True
    create_date = factory.LazyFunction(datetime.now)


# ---------------------------------------------------------------------------
# App (Workspace)
# ---------------------------------------------------------------------------

class AppFactory(BaseFactory):
    class Meta:
        model = App

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
        model = AIService

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
        model = Agent

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
        model = APIKey

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
        model = AppCollaborator

    app = factory.SubFactory(AppFactory)
    user = factory.SubFactory(UserFactory)
    role = CollaborationRole.EDITOR
    status = CollaborationStatus.ACCEPTED
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
# Silo
# ---------------------------------------------------------------------------

class SiloFactory(BaseFactory):
    class Meta:
        model = Silo

    name = factory.Sequence(lambda n: f"Test Silo {n}")
    description = "A test silo"
    silo_type = "CUSTOM"
    vector_db_type = "PGVECTOR"
    status = "active"
    app = factory.SubFactory(AppFactory)

    @factory.lazy_attribute
    def app_id(self):
        return self.app.app_id if self.app else None


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
        SiloFactory,
    ]:
        factory_cls._meta.sqlalchemy_session = session
