"""Data access for `a2a_context_link` (AD-9).

`A2AContextLink` is the race-safe join between an
`(app_id, agent_id, api_key_hash, context_id)` tuple and the Mattin
`Conversation` created for it the first time that tuple is seen. All methods
here are flush-only; the caller (`services/a2a_server/context_binding_service.py`)
owns the transaction -- same convention as `refresh_token_repository.py`.

Both `touch` and `set_conversation_id` are **conditional** UPDATEs (their
WHERE clause re-checks the exact state the caller last observed, not just
the row's id). This matters for two concurrency windows review round 1
found:
  - `touch`: between the caller's `get()` and its `touch()`, another request
    may have deleted the Conversation, which cascades the link row away. An
    unconditional `UPDATE ... WHERE id=:id` would silently match 0 rows and
    look identical to success; a caller that then returns the (now
    nonexistent) `conversation_id` from the stale ORM object hands out a
    conversation that no longer exists (`ObjectDeletedError` downstream).
    Re-checking `conversation_id == expected` makes "0 rows" distinguishable
    from "touched", so the service can fall through to treating the tuple as
    unknown again (AC-37) instead of propagating a dangling id.
  - `set_conversation_id`: this repairs a link whose `conversation_id` is
    still NULL. Two concurrent repairs for the *same* link would otherwise
    both see NULL, both create a Conversation, and both unconditionally
    write -- a lost update: the second write silently overwrites the first,
    orphaning the first repair's Conversation with no link pointing at it
    (reproduced with real threads: 4 concurrent repairs -> 4 Conversations,
    3 orphaned, callers split across 2 different ids). The `WHERE
    conversation_id IS NULL` guard means only the first repair's UPDATE
    matches; every loser gets `False` back and must discard its own
    Conversation instead of trusting its write.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from models.a2a_context_link import A2AContextLink


class A2AContextLinkRepository:

    @staticmethod
    def get(
        db: Session,
        *,
        app_id: int,
        agent_id: int,
        key_hash: str,
        context_id: str,
    ) -> Optional[A2AContextLink]:
        """Look up the link for one (app, agent, api_key_hash, context_id) tuple."""
        return db.execute(
            select(A2AContextLink).where(
                A2AContextLink.app_id == app_id,
                A2AContextLink.agent_id == agent_id,
                A2AContextLink.api_key_hash == key_hash,
                A2AContextLink.context_id == context_id,
            )
        ).scalar_one_or_none()

    @staticmethod
    def insert_if_absent(
        db: Session,
        *,
        app_id: int,
        agent_id: int,
        key_hash: str,
        context_id: str,
        conversation_id: Optional[int],
    ) -> bool:
        """Race-safe insert on the `uq_a2a_context_link_owner_ctx` unique constraint.

        Returns True if this call inserted the row, False if a concurrent
        writer already won the race for the same tuple (AD-9 step 3/4).
        """
        now = datetime.utcnow()
        stmt = (
            pg_insert(A2AContextLink)
            .values(
                app_id=app_id,
                agent_id=agent_id,
                api_key_hash=key_hash,
                context_id=context_id,
                conversation_id=conversation_id,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(constraint="uq_a2a_context_link_owner_ctx")
            .returning(A2AContextLink.id)
        )
        result = db.execute(stmt)
        db.flush()
        return result.first() is not None

    @staticmethod
    def touch(db: Session, *, link_id: int, expected_conversation_id: int) -> bool:
        """Conditionally bump `updated_at`.

        Returns True only if the link still exists with
        `conversation_id == expected_conversation_id`, i.e. nothing removed
        or repaired it between the caller's read and this call. False means
        the caller must not trust `expected_conversation_id` any further
        (the link may be gone -- cascaded away by a concurrent Conversation
        delete -- or have been repaired to a different id) and should
        re-resolve the tuple from scratch.
        """
        result = db.execute(
            update(A2AContextLink)
            .where(
                A2AContextLink.id == link_id,
                A2AContextLink.conversation_id == expected_conversation_id,
            )
            .values(updated_at=datetime.utcnow())
            .returning(A2AContextLink.id)
        )
        db.flush()
        return result.first() is not None

    @staticmethod
    def set_conversation_id(db: Session, *, link_id: int, conversation_id: int) -> bool:
        """Conditionally repair a link whose `conversation_id` is still NULL.

        The `WHERE conversation_id IS NULL` guard makes this safe against
        concurrent repairs of the same link: only the first writer's UPDATE
        matches. Returns True if this call won that repair, False if another
        writer already repaired it (or the link was deleted) first -- in
        which case the caller must discard its own, now-orphaned,
        Conversation rather than trust this write.
        """
        result = db.execute(
            update(A2AContextLink)
            .where(
                A2AContextLink.id == link_id,
                A2AContextLink.conversation_id.is_(None),
            )
            .values(conversation_id=conversation_id, updated_at=datetime.utcnow())
            .returning(A2AContextLink.id)
        )
        db.flush()
        return result.first() is not None

    @staticmethod
    def delete(db: Session, link: A2AContextLink) -> None:
        """Plain delete. Used by step_018's purge/retention paths."""
        db.delete(link)
        db.flush()

    @staticmethod
    def delete_older_than(db: Session, cutoff: datetime, batch: int = 1000) -> int:
        """Delete link rows whose `updated_at` predates `cutoff` (step_018 retention).

        Two-step batched delete: select up to `batch` candidate ids with
        `FOR UPDATE SKIP LOCKED` (so a concurrent sweeper -- or the next
        batch of this same sweep -- never blocks on, or re-selects, a row
        another worker already has locked), then delete by those ids while
        **re-checking `updated_at < cutoff` in the DELETE's own WHERE**. That
        second check closes the gap between the SELECT and the DELETE: if
        some other request `touch()`-ed the row in between (because it is
        still alive and was just reused), its `updated_at` is no longer
        older than `cutoff` and the DELETE silently skips it instead of
        purging a link that is actually still in use.
        """
        candidate_ids = db.execute(
            select(A2AContextLink.id)
            .where(A2AContextLink.updated_at < cutoff)
            .order_by(A2AContextLink.id)
            .limit(batch)
            .with_for_update(skip_locked=True)
        ).scalars().all()
        if not candidate_ids:
            return 0
        result = db.execute(
            delete(A2AContextLink)
            .where(
                A2AContextLink.id.in_(candidate_ids),
                A2AContextLink.updated_at < cutoff,
            )
            .returning(A2AContextLink.id)
        )
        db.flush()
        return len(result.fetchall())
