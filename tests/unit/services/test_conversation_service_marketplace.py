from unittest.mock import MagicMock, patch

from services.conversation_service import ConversationService


def test_get_marketplace_conversation_returns_record_when_found():
    conversation = MagicMock()
    db = MagicMock()

    with patch(
        "services.conversation_service.ConversationRepository.get_marketplace_conversation",
        return_value=conversation,
    ) as mock_repo:
        result = ConversationService.get_marketplace_conversation(
            db=db,
            conversation_id=10,
            user_id=7,
        )

    assert result is conversation
    mock_repo.assert_called_once_with(db, 10, 7)


def test_get_marketplace_conversation_returns_none_when_missing():
    db = MagicMock()

    with patch(
        "services.conversation_service.ConversationRepository.get_marketplace_conversation",
        return_value=None,
    ) as mock_repo:
        result = ConversationService.get_marketplace_conversation(
            db=db,
            conversation_id=999,
            user_id=7,
        )

    assert result is None
    mock_repo.assert_called_once_with(db, 999, 7)
