from models.conversation_message import ConversationMessage

class ConversationMessageService:
    @staticmethod
    def create(
        db,
        conversation_id,
        role,
        content,
        message_type="text",
        audio_file_id=None
    ):
        message = ConversationMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
            message_type=message_type,
            audio_file_id=audio_file_id
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        return message
    
    @staticmethod
    def get_conversation_messages(db, conversation_id):
        return (
            db.query(ConversationMessage)
            .filter(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at.asc())
            .all()
        )