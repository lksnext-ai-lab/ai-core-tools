"""
Integration tests for SandboxSessionService DB persistence (Phase 2, step 2.9).

Uses OpenSandboxProvider with the SDK boundary mocked (per the pattern in
``test_opensandbox_lifecycle.py``) — no real OpenSandbox server required.
The intent (session persistence across cache eviction / backend restart)
is provider-agnostic; OpenSandboxProvider is the only remaining provider
that supports resume, so it is the most representative real-world stand-in
now that ``SubprocessProvider`` has been removed.

NOTE on fixtures: ``SandboxSessionService`` persistence always opens its own
dedicated ``SessionLocal()`` rather than writing through a caller-supplied
session (see ``_persist_sandbox_state``'s docstring — required so REPL/tool-
executor threads never share a SQLAlchemy Session with the request-serving
thread). That means the shared, rollback-based ``db``/``fake_agent`` fixtures
from ``tests/conftest.py`` don't work here: rows only ``flush()``ed on that
fixture's connection are invisible to a genuinely separate connection/session
under Postgres's default isolation. This file therefore uses its own
real-commit-plus-manual-cleanup setup, mirroring the established pattern in
``tests/integration/test_crawl_executor.py`` for the same class of problem.
"""

from __future__ import annotations

import itertools
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from db.database import SessionLocal
from services.sandbox_session_service import SandboxSessionService
from tools.sandbox.opensandbox_provider import OpenSandboxProvider, _META_SANDBOX
from tools.sandbox.provider import SandboxHandle


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def real_agent_and_conversation(test_engine):
    """A really-committed Agent + Conversation, cleaned up via cascade delete.

    Depends on ``test_engine`` (from ``tests/conftest.py``) purely to trigger
    that session-scoped fixture's schema creation — this fixture uses its own
    ``SessionLocal()`` connections, not ``test_engine`` directly, exactly like
    ``tests/integration/test_crawl_executor.py``.

    Returns a ``SimpleNamespace(agent_id=..., conversation=...)`` where
    ``conversation`` is a plain, session-independent object exposing exactly
    the attributes ``SandboxSessionService`` reads/writes
    (``conversation_id``, ``sandbox_state``, ``sandbox_session_id``) — not a
    live ORM instance, so it can be freely read/mutated across multiple
    ``get_or_create``/``destroy`` calls without any session-lifecycle
    concerns, while still round-tripping through the SUT's real DB writes
    (which mirror the up-to-date fields back onto this same object — see
    ``_persist_sandbox_state``).
    """
    from models.user import User
    from models.app import App
    from models.ai_service import AIService
    from models.agent import Agent
    from models.conversation import Conversation

    setup_db = SessionLocal()
    unique = uuid.uuid4().hex

    user = User(
        email=f"sandbox-persistence-{unique}@mattin-test.com",
        name="Sandbox Persistence Test User",
        is_active=True,
    )
    setup_db.add(user)
    setup_db.flush()

    app = App(name=f"Sandbox Persistence Test App {unique}", owner_id=user.user_id)
    setup_db.add(app)
    setup_db.flush()

    ai_service = AIService(
        name="Sandbox Persistence Test AI Service",
        provider="OpenAI",
        api_key="sk-test-key",  # pragma: allowlist secret
        app_id=app.app_id,
    )
    setup_db.add(ai_service)
    setup_db.flush()

    agent = Agent(
        name="Sandbox Persistence Test Agent",
        description="Agent for sandbox persistence integration tests",
        system_prompt="You are a helpful test assistant.",
        app_id=app.app_id,
        service_id=ai_service.service_id,
        has_memory=False,
        temperature=0.7,
    )
    setup_db.add(agent)
    setup_db.flush()

    conversation = Conversation(
        agent_id=agent.agent_id,
        session_id=f"conv_{agent.agent_id}_{unique}",
    )
    setup_db.add(conversation)
    setup_db.commit()  # real commit so SandboxSessionService's own SessionLocal() can see it

    agent_id = agent.agent_id
    conversation_id = conversation.conversation_id
    app_id = app.app_id
    setup_db.close()

    conversation_ref = SimpleNamespace(
        conversation_id=conversation_id,
        sandbox_state=None,
        sandbox_session_id=None,
    )

    yield SimpleNamespace(agent_id=agent_id, conversation=conversation_ref)

    cleanup_db = SessionLocal()
    try:
        app_row = cleanup_db.query(App).filter(App.app_id == app_id).first()
        if app_row:
            cleanup_db.delete(app_row)  # cascades to Agent -> Conversation
            cleanup_db.commit()
    finally:
        cleanup_db.close()


def _load_conversation_from_db(conversation_id: int):
    """Read a fresh copy of the Conversation row from a brand-new session."""
    from models.conversation import Conversation

    verify_db = SessionLocal()
    try:
        return verify_db.query(Conversation).filter(
            Conversation.conversation_id == conversation_id
        ).first()
    finally:
        verify_db.close()


@pytest.fixture()
def opensandbox_provider():
    """OpenSandboxProvider with the SDK boundary mocked — no real server needed.

    ``SandboxSync`` is replaced with a MagicMock so ``_can_resume``/``_can_renew``
    are always True, and ``_setup_sandbox_handle`` is replaced with a lightweight
    stand-in that skips real ``CodeInterpreterSync`` context creation while still
    returning a fully populated ``SandboxHandle`` carrying the SDK sandbox mock.
    """
    with patch("tools.sandbox.opensandbox_provider.SandboxSync") as mock_sdk:
        provider = OpenSandboxProvider()
        provider._connection_config = {}

        counter = itertools.count()

        def _fake_create(*_args, **_kwargs):
            sandbox = MagicMock()
            sandbox.id = f"sbx_{next(counter)}"
            return sandbox

        def _fake_resume(sandbox_id, **_kwargs):
            sandbox = MagicMock()
            sandbox.id = sandbox_id
            return sandbox

        mock_sdk.create.side_effect = _fake_create
        mock_sdk.resume.side_effect = _fake_resume

        def _fake_setup_sandbox_handle(sandbox, working_dir, session_key):
            return SandboxHandle(
                sandbox_id=sandbox.id,
                working_dir=working_dir,
                provider_name=provider.PROVIDER_NAME,
                session_key=session_key,
                metadata={_META_SANDBOX: sandbox},
            )

        with patch.object(
            provider, "_setup_sandbox_handle", side_effect=_fake_setup_sandbox_handle
        ):
            yield provider


@pytest.fixture()
def sandbox_session_service():
    """A fresh SandboxSessionService instance (not the global singleton)."""
    return SandboxSessionService()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_sandbox_session_id_populated_after_create(
    real_agent_and_conversation, opensandbox_provider, sandbox_session_service
):
    """Conversation.sandbox_session_id is set after get_or_create."""
    conversation = real_agent_and_conversation.conversation
    key = SandboxSessionService.session_key(
        real_agent_and_conversation.agent_id, conversation.conversation_id
    )
    handle = sandbox_session_service.get_or_create(
        session_key=key,
        provider=opensandbox_provider,
        working_dir="/tmp/sandbox_test_create",
        conversation=conversation,
    )

    row = _load_conversation_from_db(conversation.conversation_id)
    assert row.sandbox_session_id == handle.sandbox_id
    assert row.sandbox_state is not None
    # Mirrored back onto the caller's in-memory object too.
    assert conversation.sandbox_session_id == handle.sandbox_id
    assert conversation.sandbox_state is not None


def test_sandbox_state_loaded_after_cache_eviction(
    real_agent_and_conversation, opensandbox_provider, sandbox_session_service
):
    """After cache eviction, get_or_create loads state from DB and passes existing_sandbox_id."""
    conversation = real_agent_and_conversation.conversation
    key = SandboxSessionService.session_key(
        real_agent_and_conversation.agent_id, conversation.conversation_id
    )
    # First call — creates and persists
    handle_first = sandbox_session_service.get_or_create(
        session_key=key,
        provider=opensandbox_provider,
        working_dir="/tmp/sandbox_test_evict",
        conversation=conversation,
    )
    assert conversation.sandbox_session_id == handle_first.sandbox_id

    # Evict the in-memory cache entry
    sandbox_session_service._sessions.pop(key, None)

    # Second call — should load from DB (via the mirrored-back `conversation`
    # object) and pass existing_sandbox_id to create_sandbox
    with patch.object(
        opensandbox_provider, "create_sandbox", wraps=opensandbox_provider.create_sandbox
    ) as mock_create:
        sandbox_session_service.get_or_create(
            session_key=key,
            provider=opensandbox_provider,
            working_dir="/tmp/sandbox_test_evict",
            conversation=conversation,
        )
        mock_create.assert_called_once()
        _, kwargs = mock_create.call_args
        assert kwargs.get("existing_sandbox_id") == handle_first.sandbox_id


def test_reset_clears_sandbox_session_id_and_state(
    real_agent_and_conversation, opensandbox_provider, sandbox_session_service
):
    """Destroying a sandbox and clearing DB state leaves conversation clean."""
    conversation = real_agent_and_conversation.conversation
    key = SandboxSessionService.session_key(
        real_agent_and_conversation.agent_id, conversation.conversation_id
    )
    sandbox_session_service.get_or_create(
        session_key=key,
        provider=opensandbox_provider,
        working_dir="/tmp/sandbox_test_reset",
        conversation=conversation,
    )
    assert conversation.sandbox_session_id is not None

    # Simulate what reset_agent_conversation does: destroy the in-process
    # session, then clear the persisted DB state via a fresh session (mirrors
    # the real caller in agent_execution_service.py).
    sandbox_session_service.destroy(key)

    from models.conversation import Conversation

    clear_db = SessionLocal()
    try:
        row = clear_db.query(Conversation).filter(
            Conversation.conversation_id == conversation.conversation_id
        ).first()
        row.sandbox_session_id = None
        row.sandbox_state = None
        clear_db.add(row)
        clear_db.commit()
    finally:
        clear_db.close()

    row = _load_conversation_from_db(conversation.conversation_id)
    assert row.sandbox_session_id is None
    assert row.sandbox_state is None
    assert key not in sandbox_session_service._sessions


def test_destroy_all_for_agent_matches_conv_keys(
    real_agent_and_conversation, opensandbox_provider, sandbox_session_service
):
    """destroy_all_for_agent() now destroys sessions registered under conv_... keys."""
    conversation = real_agent_and_conversation.conversation
    key = SandboxSessionService.session_key(
        real_agent_and_conversation.agent_id, conversation.conversation_id
    )
    sandbox_session_service.get_or_create(
        session_key=key,
        provider=opensandbox_provider,
        working_dir="/tmp/sandbox_test_destroy_all",
        conversation=conversation,
    )
    assert key in sandbox_session_service._sessions

    sandbox_session_service.destroy_all_for_agent(real_agent_and_conversation.agent_id)

    assert key not in sandbox_session_service._sessions


def test_session_key_helper():
    """Unit-test the session_key() static helper."""
    assert SandboxSessionService.session_key(1, 42) == "conv_1_42"
    assert SandboxSessionService.session_key(1, None, "abc-session") == "thread_1_abc-session"
    assert SandboxSessionService.session_key(1, None, None) == "anon_1"
    # conversation_id takes precedence over session_id
    assert SandboxSessionService.session_key(1, 42, "abc") == "conv_1_42"
