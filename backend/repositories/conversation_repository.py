from typing import Optional

from sqlalchemy.orm import Session

from models.conversation import Conversation, ConversationSource


class ConversationRepository:

    @staticmethod
    def get_marketplace_conversation(
        db: Session,
        conversation_id: int,
        user_id: int,
    ) -> Optional[Conversation]:
        """Get a marketplace conversation owned by a specific user."""
        return (
            db.query(Conversation)
            .filter(
                Conversation.conversation_id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.source == ConversationSource.MARKETPLACE,
            )
            .first()
        )
