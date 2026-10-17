"""Mattin's contextId <-> Conversation binding (AD-9).

The a2a-sdk has no notion of Mattin's `Conversation`; `contextId` is the SDK's
own client-chosen string. `A2AContextLink` is the race-safe join between an
(app, agent, api_key_hash, context_id) tuple and the Conversation created for
it the first time that tuple is seen (`source=A2A`). `conversation_id` stays
nullable at the schema level per DEV-3 (resolved): even no-memory agents get a
Conversation for bookkeeping, but defense in depth (and future flexibility)
keeps the column nullable rather than assuming that will always hold.

No ORM relationships back from Agent/App/Conversation: the DB FK cascades
(ON DELETE CASCADE on all three) handle deletion without the ORM ever loading
rows into memory first (AD-9, AC-41).
"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, Index

from db.database import Base


class A2AContextLink(Base):
    __tablename__ = 'a2a_context_link'

    id = Column(Integer, primary_key=True)
    # No index=True here: app_id is already the leftmost column of
    # uq_a2a_context_link_owner_ctx, so a separate single-column index on it
    # would be redundant (Postgres can use the unique constraint's index for
    # an app_id-only lookup too). agent_id and conversation_id each get their
    # own index below since they are not leftmost in that constraint.
    app_id = Column(Integer, ForeignKey('App.app_id', ondelete='CASCADE'), nullable=False)
    agent_id = Column(Integer, ForeignKey('Agent.agent_id', ondelete='CASCADE'), nullable=False, index=True)
    conversation_id = Column(
        Integer, ForeignKey('Conversation.conversation_id', ondelete='CASCADE'), nullable=True, index=True
    )
    api_key_hash = Column(String(64), nullable=False)
    context_id = Column(String(36), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('app_id', 'agent_id', 'api_key_hash', 'context_id', name='uq_a2a_context_link_owner_ctx'),
        Index('ix_a2a_context_link_updated_at', 'updated_at'),
    )
