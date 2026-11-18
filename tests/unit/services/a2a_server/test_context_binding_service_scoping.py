"""Unit coverage for `context_binding_service._load_scoped_agent` (no DB).

This is the piece that carries the step_007 architecture-review requirement:
`a2a_context_link` has no DB constraint tying `agent_id` to `app_id`, so
`bind_context` must never trust a caller-supplied `app_id` for that pairing.
It must load the `Agent` row and treat `Agent.app_id` as authoritative,
rejecting anything else before touching the link table or creating a
Conversation. These tests exercise that guard directly with a mocked
session; the full binding flow (which needs the real unique constraint and a
real Conversation) is covered in
`tests/integration/a2a_server/test_context_binding_service.py`.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.a2a_server.context_binding_service import (
    A2AContextBindingError,
    A2AInvalidContextIdError,
    _load_scoped_agent,
    bind_context,
)
from utils.security import hash_api_key


def _fake_agent(agent_id: int, app_id: int) -> SimpleNamespace:
    return SimpleNamespace(agent_id=agent_id, app_id=app_id)


class TestLoadScopedAgent:
    def test_returns_agent_when_app_matches(self):
        db = MagicMock()
        db.get.return_value = _fake_agent(agent_id=42, app_id=7)

        agent = _load_scoped_agent(db, app_id=7, agent_id=42)

        assert agent.app_id == 7
        db.get.assert_called_once()

    def test_raises_when_agent_missing(self):
        db = MagicMock()
        db.get.return_value = None

        with pytest.raises(A2AContextBindingError):
            _load_scoped_agent(db, app_id=7, agent_id=42)

    def test_raises_when_agent_belongs_to_a_different_app(self):
        """The caller-supplied app_id must never be trusted on its own: an agent
        that is real but belongs to another app must still be rejected."""
        db = MagicMock()
        db.get.return_value = _fake_agent(agent_id=42, app_id=999)

        with pytest.raises(A2AContextBindingError):
            _load_scoped_agent(db, app_id=7, agent_id=42)


class TestBindContextRejectsMismatchedApp:
    def test_bind_context_raises_before_touching_the_link_repository(self, monkeypatch):
        """A mismatched (app_id, agent_id) pair must fail fast, before any
        a2a_context_link query, insert or Conversation creation runs."""
        db = MagicMock()
        db.get.return_value = _fake_agent(agent_id=42, app_id=999)

        link_repo = MagicMock()
        monkeypatch.setattr(
            "services.a2a_server.context_binding_service.A2AContextLinkRepository", link_repo
        )
        conversation_service = MagicMock()
        monkeypatch.setattr(
            "services.a2a_server.context_binding_service.ConversationService", conversation_service
        )

        with pytest.raises(A2AContextBindingError):
            bind_context(
                db,
                app_id=7,
                agent_id=42,
                api_key_raw="raw-key",
                context_id="ctx-1",
                user_context={"api_key": "raw-key"},
            )

        link_repo.get.assert_not_called()
        link_repo.insert_if_absent.assert_not_called()
        conversation_service.create_conversation.assert_not_called()


class TestBindContextValidatesContextIdBeforeAnyDbAccess:
    """AD-7 shape check (<=36 chars, `[A-Za-z0-9._:-]`), enforced as defense in
    depth before any DB access -- not just by the SDK's own request-context
    builder (step_012)."""

    @pytest.mark.parametrize(
        "bad_context_id",
        [
            "",
            "x" * 37,
            "has a space",
            "has/a/slash",
            "emoji-\U0001F600",
        ],
    )
    def test_rejects_malformed_context_id_before_loading_the_agent(self, monkeypatch, bad_context_id):
        db = MagicMock()

        with pytest.raises(A2AInvalidContextIdError):
            bind_context(
                db,
                app_id=7,
                agent_id=42,
                api_key_raw="raw-key",
                context_id=bad_context_id,
                user_context={"api_key": "raw-key"},
            )

        db.get.assert_not_called()

    def test_accepts_the_max_length_allowed_charset(self):
        db = MagicMock()
        db.get.return_value = None  # agent lookup fails next; proves validation ran first and passed

        with pytest.raises(A2AContextBindingError):
            bind_context(
                db,
                app_id=7,
                agent_id=42,
                api_key_raw="raw-key",
                context_id="A" * 36,
                user_context={"api_key": "raw-key"},
            )
        db.get.assert_called_once()


class TestBindContextRequiresMatchingApiKey:
    """LOW-4: the hash written to the link/Conversation must come from the
    same input as `user_context["api_key"]` -- one source of truth for the
    caller's identity."""

    def test_raises_when_user_context_key_does_not_match_raw_key(self, monkeypatch):
        db = MagicMock()
        db.get.return_value = _fake_agent(agent_id=42, app_id=7)

        link_repo = MagicMock()
        monkeypatch.setattr(
            "services.a2a_server.context_binding_service.A2AContextLinkRepository", link_repo
        )

        with pytest.raises(A2AContextBindingError):
            bind_context(
                db,
                app_id=7,
                agent_id=42,
                api_key_raw="raw-key-one",
                context_id="ctx-1",
                user_context={"api_key": "a-different-raw-key"},
            )

        link_repo.get.assert_not_called()

    def test_raises_when_user_context_has_no_api_key(self, monkeypatch):
        db = MagicMock()
        db.get.return_value = _fake_agent(agent_id=42, app_id=7)

        link_repo = MagicMock()
        monkeypatch.setattr(
            "services.a2a_server.context_binding_service.A2AContextLinkRepository", link_repo
        )

        with pytest.raises(A2AContextBindingError):
            bind_context(
                db,
                app_id=7,
                agent_id=42,
                api_key_raw="raw-key-one",
                context_id="ctx-1",
                user_context={},
            )

        link_repo.get.assert_not_called()

    def test_passes_when_user_context_key_hashes_to_the_same_value(self, monkeypatch):
        db = MagicMock()
        db.get.return_value = _fake_agent(agent_id=42, app_id=7)

        link_repo = MagicMock()
        link_repo.get.return_value = None
        monkeypatch.setattr(
            "services.a2a_server.context_binding_service.A2AContextLinkRepository", link_repo
        )
        conversation = SimpleNamespace(conversation_id=123)
        conversation_service = MagicMock()
        conversation_service.create_conversation.return_value = conversation
        monkeypatch.setattr(
            "services.a2a_server.context_binding_service.ConversationService", conversation_service
        )
        link_repo.insert_if_absent.return_value = True

        binding = bind_context(
            db,
            app_id=7,
            agent_id=42,
            api_key_raw="raw-key-one",
            context_id="ctx-1",
            user_context={"api_key": "raw-key-one"},
        )

        assert binding.conversation_id == 123
        assert binding.created is True
        # sanity: the hash actually used matches hash_api_key("raw-key-one")
        _, kwargs = link_repo.insert_if_absent.call_args
        assert kwargs["key_hash"] == hash_api_key("raw-key-one")
