"""Busy marker: renewed right before the model runs, and a first turn that fails to claim leaves nothing behind."""
from unittest.mock import patch

import pytest

from models.internal_chat import ChatConversationState
from repositories.internal_chat_repository import ChatConversationStateRepository
from services.internal_chat.chat_service import InternalChatService
from services.internal_chat.errors import ChatConversationBusyError
from tests.integration.internal_chat._chat_support import internal_conversations, selection, send


@pytest.mark.parametrize("path", ["/messages", "/stream"])
def test_the_marker_is_renewed_once_before_the_model_runs_and_released_after(client, db, world, fakes, path):
    calls = []
    real = ChatConversationStateRepository.renew_busy

    def spy(session, conversation_id, token, ttl):
        # at renewal time the model has not been called yet
        calls.append((conversation_id, len(fakes.calls)))
        return real(session, conversation_id, token, ttl)

    with patch.object(ChatConversationStateRepository, "renew_busy", staticmethod(spy)):
        response = send(client, world, "hello", selection(world["ai_a"]), path=path)
    assert response.status_code == 200, response.text
    assert len(calls) == 1 and calls[0][1] == 0, calls
    db.expire_all()
    state = db.query(ChatConversationState).filter_by(conversation_id=calls[0][0]).one()
    assert state.busy_token is None and state.busy_until is None


@pytest.mark.parametrize("path", ["/messages", "/stream"])
def test_a_first_turn_that_cannot_claim_its_new_conversation_leaves_no_empty_conversation(
    client, db, world, fakes, path
):
    before = internal_conversations(db, world["app_id"])

    def busy(self, conversation_id):
        raise ChatConversationBusyError()

    with patch.object(InternalChatService, "_claim_conversation", busy):
        response = send(client, world, "hello", selection(world["ai_a"]), path=path)
    assert response.status_code == 409 and response.json()["error_code"] == "CONVERSATION_BUSY"
    db.expire_all()
    assert internal_conversations(db, world["app_id"]) == before
    assert fakes.calls == []  # the model never ran
