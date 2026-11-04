"""Shared helpers/fixtures for the service end-of-service enforcement tests (step_012).

Everything here keeps the provider SDKs out of reach: LLM builders, embedding builders and
sandbox providers are replaced by recorders so a test can assert they were (not) built.
"""

import logging
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from tests.integration.routers.internal._eos_helpers import (  # noqa: F401  (re-exported for the test modules)
    ai_service,
    embedding_service,
    future,
    make_agent,
    make_app,
    make_repository,
    make_silo,
    past,
    sandbox_service,
)

LLM_ANSWER = "fake llm answer"


class FakeToolChatModel(FakeListChatModel):
    """Fake chat model that tolerates ``bind_tools`` (the agent chain binds its tools to the model)."""

    def bind_tools(self, tools, **kwargs):
        return self

_LLM_BUILDER_NAMES = (
    "_build_openai_llm",
    "_build_openrouter_llm",
    "_build_anthropic_llm",
    "_build_mistral_llm",
    "_build_custom_llm",
    "_build_azure_llm",
    "_build_google_llm",
    "_build_google_cloud_llm",
    "_build_bedrock_llm",
)


class SessionProxy:
    """``SessionLocal()`` stand-in bound to the test session; ``close()`` must not end the test transaction."""

    def __init__(self, db):
        self._db = db

    def __getattr__(self, name):
        return getattr(self._db, name)

    def close(self):
        pass


@pytest.fixture
def lifecycle_caplog(caplog):
    """The project logger does not propagate to root, so attach caplog's handler to the guard's logger."""
    from utils import service_lifecycle

    service_lifecycle.logger.addHandler(caplog.handler)
    caplog.set_level(logging.DEBUG)
    yield caplog
    service_lifecycle.logger.removeHandler(caplog.handler)


def guard_warnings(caplog):
    """WARNING records of the lifecycle guard (``service_lifecycle.blocked ...``)."""
    return [r for r in caplog.records
            if r.levelno == logging.WARNING and r.getMessage().startswith("service_lifecycle.blocked")]


@pytest.fixture
def llm_builders(monkeypatch):
    """Patch every provider LLM builder; the OpenAI one returns a fake chat model.

    ``llm_builders.all`` are the recorders: assert ``not any(m.called ...)`` for a retired service.
    """
    import tools.aiServiceTools as module

    mocks = {}
    for name in _LLM_BUILDER_NAMES:
        mock = MagicMock(name=name, side_effect=lambda *a, **k: FakeToolChatModel(responses=[LLM_ANSWER]))
        monkeypatch.setattr(module, name, mock)
        mocks[name] = mock

    class _Builders:
        openai = mocks["_build_openai_llm"]
        all = list(mocks.values())

        @property
        def called(self):
            return any(m.called for m in self.all)

        def reset(self):
            for m in self.all:
                m.reset_mock()

    return _Builders()


@pytest.fixture
def embedding_builders(monkeypatch):
    """Patch the embedding provider builders (and the OpenAI one returns a usable fake)."""
    import tools.embeddingTools as module

    fake = SimpleNamespace(embed_query=lambda text: [0.0, 0.1], embed_documents=lambda docs: [[0.0, 0.1]] * len(docs))
    builders = {}
    patched = {}
    for provider, original in module._EMBEDDING_BUILDERS.items():
        mock = MagicMock(name=f"embedding_builder_{provider}", return_value=fake)
        patched[provider] = mock
        builders[provider] = mock
    monkeypatch.setattr(module, "_EMBEDDING_BUILDERS", patched)

    class _Builders:
        all = list(builders.values())
        openai = patched.get("OpenAI")

        @property
        def called(self):
            return any(m.called for m in self.all)

    return _Builders()


@pytest.fixture
def fake_vector_store(monkeypatch):
    """Patch ``services.silo_service._get_vector_store`` with a recorder (no PGVector/Qdrant access)."""
    import services.silo_service as module

    store = MagicMock(name="vector_store")
    store.collection_exists.return_value = True
    store.count_documents.return_value = 0
    store.search_similar_documents.return_value = []
    getter = MagicMock(name="_get_vector_store", return_value=store)
    monkeypatch.setattr(module, "_get_vector_store", getter)
    store.getter = getter
    return store


class FakeSandboxProvider:
    """Records instantiation; everything else is a no-op so the code-interpreter tools can be assembled."""

    PROVIDER_NAME = "opensandbox"
    instances: list = []

    def __init__(self, credentials=None, **kwargs):
        self.credentials = credentials
        FakeSandboxProvider.instances.append(self)
        self.destroyed_ids = []

    def get_supported_languages(self):
        return ["python"]

    def destroy_sandbox_id(self, sandbox_id):
        self.destroyed_ids.append(sandbox_id)

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return MagicMock(name=f"FakeSandboxProvider.{name}")


@pytest.fixture
def fake_sandbox_registry(monkeypatch):
    """Replace every sandbox provider class in the factory registry with a recording fake."""
    from tools.sandbox import factory

    FakeSandboxProvider.instances = []
    registry = {name: FakeSandboxProvider for name in ("opensandbox", "daytona", "e2b")}
    monkeypatch.setattr(factory, "_PROVIDER_REGISTRY", registry)
    monkeypatch.delenv("SANDBOX_ALLOWED_PROVIDERS", raising=False)
    yield FakeSandboxProvider
    FakeSandboxProvider.instances = []


def sse_events(text: str):
    """Parse an SSE body into a list of JSON payloads (``data:`` lines only)."""
    import json

    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            raw = line[len("data:"):].strip()
            if raw:
                try:
                    events.append(json.loads(raw))
                except ValueError:
                    continue
    return events


def api_key_headers(db, app, user):
    """Create an active API key for ``app`` and return the headers using it."""
    from datetime import datetime

    from models.api_key import APIKey

    key = APIKey(key=f"eos-enforcement-key-{uuid.uuid4().hex}",  # pragma: allowlist secret
                 name="eos key", app_id=app.app_id, user_id=user.user_id, is_active=True,
                 created_at=datetime.now())
    db.add(key)
    db.flush()
    return {"X-API-KEY": key.key}
