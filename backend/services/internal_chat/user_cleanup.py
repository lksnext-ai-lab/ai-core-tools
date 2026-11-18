"""Removal of a deleted user's App Chat conversations (the user deletion flow).

``Conversation.user_id`` is ON DELETE SET NULL, so without this step a deleted user's Chat conversations (their
messages, attachments and the hidden temp silo with the indexed attachment chunks) would stay behind with no owner:
nobody can open or delete them through the Chat API, and the shared internal agent keeps them forever.

Two phases around the user deletion's commit, so the deletion keeps its atomicity (``transfer_apps`` is one
transaction) and never commits early:

1. ``stage`` (same transaction as the user's deletion, no commit): reads the user's Chat conversations as plain
   values and deletes the rows (the state and turn rows go by FK cascade).
2. ``finish`` (after the commit, best effort, never raises): temp silo + repository + vectors, sandbox, stored files
   and the LangGraph thread of each of them. A failure here is logged with ids only; the user is already gone.
"""
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.agent import Agent
from models.conversation import Conversation, ConversationSource
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class StagedChatConversation:
    """Plain values of one staged conversation (the ORM row is deleted; nothing here expires)."""

    conversation_id: int
    agent_id: int
    app_id: int
    session_id: str


def stage_user_chat_conversations(
    db: Session, user_id: int, app_id: Optional[int] = None
) -> List[StagedChatConversation]:
    """Delete the user's Chat conversation rows in the CURRENT transaction (no commit) and return what is left to clean.

    With ``app_id`` only that App's conversations (a collaborator removed from / leaving one App); without it all of
    the user's Chat conversations (the user is deleted).
    """
    query = (
        select(Conversation.conversation_id, Conversation.agent_id, Agent.app_id, Conversation.session_id)
        .join(Agent, Agent.agent_id == Conversation.agent_id)
        .where(Conversation.user_id == user_id, Conversation.source == ConversationSource.INTERNAL_CHAT)
    )
    if app_id is not None:
        query = query.where(Agent.app_id == app_id)
    rows = db.execute(query).all()
    staged = [StagedChatConversation(*row) for row in rows]
    for item in staged:
        conversation = db.get(Conversation, item.conversation_id)
        if conversation is not None:
            db.delete(conversation)
    return staged


def finish_user_chat_conversations(db: Session, user_id: int, staged: List[StagedChatConversation]) -> None:
    """Best-effort cleanup of the storage of conversations deleted by ``stage`` (call after the commit)."""
    if not staged:
        return
    from services.conversation_service import ConversationService
    from services.file_management_service import FileManagementService
    from services.playground_media_service import PlaygroundMediaService
    from services.sandbox_session_service import SandboxSessionService, sandbox_session_service

    file_service = FileManagementService()
    for item in staged:
        try:
            PlaygroundMediaService.cleanup(item.app_id, item.agent_id, item.session_id, db)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.error(
                "User deletion: could not remove the temp silo of chat conversation %s (%s)",
                item.conversation_id, type(exc).__name__,
            )
        try:
            sandbox_session_service.destroy(SandboxSessionService.session_key(item.agent_id, item.conversation_id))
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "User deletion: could not destroy the sandbox of chat conversation %s (%s)",
                item.conversation_id, type(exc).__name__,
            )
        try:
            file_service.delete_conversation_storage(
                item.agent_id,
                {"user_id": user_id, "oauth": True, "app_id": item.app_id},
                str(item.conversation_id),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "User deletion: could not remove the files of chat conversation %s (%s)",
                item.conversation_id, type(exc).__name__,
            )
    try:
        ConversationService.delete_thread_histories_in_background([(i.agent_id, i.session_id) for i in staged])
    except Exception as exc:  # noqa: BLE001
        logger.error("User deletion: could not schedule the deletion of chat threads (%s)", type(exc).__name__)
