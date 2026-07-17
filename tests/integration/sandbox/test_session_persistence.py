"""
Integration tests for SandboxSessionService DB persistence (Phase 2, step 2.9).

Uses SubprocessProvider — no external services required.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from services.sandbox_session_service import SandboxSessionService
from tools.sandbox.subprocess_provider import SubprocessProvider


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
def subprocess_provider():
    """A fresh SubprocessProvider instance."""
    return SubprocessProvider()


@pytest.fixture()
def sandbox_session_service():
    """A fresh SandboxSessionService instance (not the global singleton)."""
    return SandboxSessionService()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_sandbox_session_id_populated_after_create(
    db, fake_agent, fake_conversation, subprocess_provider, sandbox_session_service
):
    """Conversation.sandbox_session_id is set after get_or_create."""
    key = SandboxSessionService.session_key(fake_agent.agent_id, fake_conversation.conversation_id)
    handle = sandbox_session_service.get_or_create(
        session_key=key,
        provider=subprocess_provider,
        working_dir="/tmp/sandbox_test_create",
        conversation=fake_conversation,
        db=db,
    )

    db.refresh(fake_conversation)
    assert fake_conversation.sandbox_session_id == handle.sandbox_id
    assert fake_conversation.sandbox_state is not None


def test_sandbox_state_loaded_after_cache_eviction(
    db, fake_agent, fake_conversation, subprocess_provider, sandbox_session_service
):
    """After cache eviction, get_or_create loads state from DB and passes existing_sandbox_id."""
    key = SandboxSessionService.session_key(fake_agent.agent_id, fake_conversation.conversation_id)
    # First call — creates and persists
    handle_first = sandbox_session_service.get_or_create(
        session_key=key,
        provider=subprocess_provider,
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
        subprocess_provider, "create_sandbox", wraps=subprocess_provider.create_sandbox
    ) as mock_create:
        sandbox_session_service.get_or_create(
            session_key=key,
            provider=subprocess_provider,
            working_dir="/tmp/sandbox_test_evict",
            conversation=fake_conversation,
            db=db,
        )
        mock_create.assert_called_once()
        _, kwargs = mock_create.call_args
        assert kwargs.get("existing_sandbox_id") == handle_first.sandbox_id


def test_reset_clears_sandbox_session_id_and_state(
    db, fake_agent, fake_conversation, subprocess_provider, sandbox_session_service
):
    """Destroying a sandbox and clearing DB state leaves conversation clean."""
    key = SandboxSessionService.session_key(fake_agent.agent_id, fake_conversation.conversation_id)
    sandbox_session_service.get_or_create(
        session_key=key,
        provider=subprocess_provider,
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
    db, fake_agent, fake_conversation, subprocess_provider, sandbox_session_service
):
    """destroy_all_for_agent() now destroys sessions registered under conv_... keys."""
    key = SandboxSessionService.session_key(fake_agent.agent_id, fake_conversation.conversation_id)
    sandbox_session_service.get_or_create(
        session_key=key,
        provider=subprocess_provider,
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
