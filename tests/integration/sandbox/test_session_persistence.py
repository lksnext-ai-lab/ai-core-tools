"""
Integration tests for SandboxSessionService DB persistence (Phase 2, step 2.9).

Uses OpenSandboxProvider with the SDK boundary mocked (per the pattern in
``test_opensandbox_lifecycle.py``) — no real OpenSandbox server required.
The intent (session persistence across cache eviction / backend restart)
is provider-agnostic; OpenSandboxProvider is the only remaining provider
that supports resume, so it is the most representative real-world stand-in
now that ``SubprocessProvider`` has been removed.
"""

from __future__ import annotations

import itertools
import uuid
from unittest.mock import MagicMock, patch

import pytest

from services.sandbox_session_service import SandboxSessionService
from tools.sandbox.opensandbox_provider import OpenSandboxProvider, _META_SANDBOX
from tools.sandbox.provider import SandboxHandle


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_conversation(db, fake_agent):
    """A minimal Conversation linked to fake_agent."""
    from models.conversation import Conversation

    conv = Conversation(
        agent_id=fake_agent.agent_id,
        session_id=f"conv_{fake_agent.agent_id}_{uuid.uuid4().hex}",
    )
    db.add(conv)
    db.flush()
    return conv


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
    db, fake_agent, fake_conversation, opensandbox_provider, sandbox_session_service
):
    """Conversation.sandbox_session_id is set after get_or_create."""
    key = SandboxSessionService.session_key(fake_agent.agent_id, fake_conversation.conversation_id)
    handle = sandbox_session_service.get_or_create(
        session_key=key,
        provider=opensandbox_provider,
        working_dir="/tmp/sandbox_test_create",
        conversation=fake_conversation,
        db=db,
    )

    db.refresh(fake_conversation)
    assert fake_conversation.sandbox_session_id == handle.sandbox_id
    assert fake_conversation.sandbox_state is not None


def test_sandbox_state_loaded_after_cache_eviction(
    db, fake_agent, fake_conversation, opensandbox_provider, sandbox_session_service
):
    """After cache eviction, get_or_create loads state from DB and passes existing_sandbox_id."""
    key = SandboxSessionService.session_key(fake_agent.agent_id, fake_conversation.conversation_id)
    # First call — creates and persists
    handle_first = sandbox_session_service.get_or_create(
        session_key=key,
        provider=opensandbox_provider,
        working_dir="/tmp/sandbox_test_evict",
        conversation=fake_conversation,
        db=db,
    )
    db.refresh(fake_conversation)
    assert fake_conversation.sandbox_session_id == handle_first.sandbox_id

    # Evict the in-memory cache entry
    sandbox_session_service._sessions.pop(key, None)

    # Second call — should load from DB and pass existing_sandbox_id to create_sandbox
    with patch.object(
        opensandbox_provider, "create_sandbox", wraps=opensandbox_provider.create_sandbox
    ) as mock_create:
        sandbox_session_service.get_or_create(
            session_key=key,
            provider=opensandbox_provider,
            working_dir="/tmp/sandbox_test_evict",
            conversation=fake_conversation,
            db=db,
        )
        mock_create.assert_called_once()
        _, kwargs = mock_create.call_args
        assert kwargs.get("existing_sandbox_id") == handle_first.sandbox_id


def test_reset_clears_sandbox_session_id_and_state(
    db, fake_agent, fake_conversation, opensandbox_provider, sandbox_session_service
):
    """Destroying a sandbox and clearing DB state leaves conversation clean."""
    key = SandboxSessionService.session_key(fake_agent.agent_id, fake_conversation.conversation_id)
    sandbox_session_service.get_or_create(
        session_key=key,
        provider=opensandbox_provider,
        working_dir="/tmp/sandbox_test_reset",
        conversation=fake_conversation,
        db=db,
    )
    db.refresh(fake_conversation)
    assert fake_conversation.sandbox_session_id is not None

    # Simulate what reset_agent_conversation does: destroy + clear DB state
    sandbox_session_service.destroy(key)
    fake_conversation.sandbox_session_id = None
    fake_conversation.sandbox_state = None
    db.add(fake_conversation)
    db.commit()

    db.refresh(fake_conversation)
    assert fake_conversation.sandbox_session_id is None
    assert fake_conversation.sandbox_state is None
    assert key not in sandbox_session_service._sessions


def test_destroy_all_for_agent_matches_conv_keys(
    db, fake_agent, fake_conversation, opensandbox_provider, sandbox_session_service
):
    """destroy_all_for_agent() now destroys sessions registered under conv_... keys."""
    key = SandboxSessionService.session_key(fake_agent.agent_id, fake_conversation.conversation_id)
    sandbox_session_service.get_or_create(
        session_key=key,
        provider=opensandbox_provider,
        working_dir="/tmp/sandbox_test_destroy_all",
        conversation=fake_conversation,
        db=db,
    )
    assert key in sandbox_session_service._sessions

    sandbox_session_service.destroy_all_for_agent(fake_agent.agent_id)

    assert key not in sandbox_session_service._sessions


def test_session_key_helper():
    """Unit-test the session_key() static helper."""
    assert SandboxSessionService.session_key(1, 42) == "conv_1_42"
    assert SandboxSessionService.session_key(1, None, "abc-session") == "thread_1_abc-session"
    assert SandboxSessionService.session_key(1, None, None) == "anon_1"
    # conversation_id takes precedence over session_id
    assert SandboxSessionService.session_key(1, 42, "abc") == "conv_1_42"
