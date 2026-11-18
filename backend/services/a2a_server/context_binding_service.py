"""contextId <-> Conversation binding (AD-9).

`bind_context` is the entry point the A2A executor bridge (step_016) calls
once per turn to resolve a client-supplied or server-generated `contextId`
into exactly one Mattin `Conversation`, scoped to
`(app_id, agent_id, api_key_hash)`.

**Security note (carried from the step_007 architecture review).**
`a2a_context_link` has no DB constraint tying `agent_id` to `app_id` --
nothing at the schema level rejects a row where the agent actually belongs to
a different app. This module therefore never trusts a caller-supplied
`app_id` for that pairing: `bind_context` loads the `Agent` row by
`agent_id`, verifies it belongs to the given `app_id`, and from that point on
uses `Agent.app_id` (the DB value) -- never the raw `app_id` parameter -- for
every query, insert and Conversation creation.

**Concurrency design (review round 1).** `bind_context` is optimistic and
retries a bounded number of times rather than taking any lock: each attempt
either succeeds outright, or discovers -- via a conditional UPDATE/INSERT
whose WHERE clause re-checks the exact state the attempt last observed --
that another concurrent call changed that state first, in which case it
discards anything it created and retries once more from a fresh read. The
three windows review round 1 found and that the retry loop closes:
  - **touch-vs-cascade-delete**: between reading a link and touching it,
    the Conversation it points at may have been deleted (cascading the link
    row away). `A2AContextLinkRepository.touch` re-checks
    `conversation_id == expected`, so a miss is distinguishable from success
    and the attempt retries (falling through to the unknown-tuple path,
    AC-37) instead of handing back a `conversation_id` that no longer
    exists;
  - **repair lost-update**: a link with `conversation_id IS NULL` repaired
    by N concurrent callers must produce exactly one surviving Conversation,
    not N (with N-1 silently orphaned). `set_conversation_id`'s
    `WHERE conversation_id IS NULL` guard means only the first UPDATE
    matches; every loser discards its own Conversation and retries;
  - **vanished winner**: after losing the insert race, re-reading the
    winner's link can (rarely) come back empty if that Conversation was
    deleted in the meantime. Rather than raising, the attempt retries --
    the next attempt sees an unknown tuple and creates a fresh Conversation.

**Why not one atomic transaction.** `ConversationService.create_conversation`
commits internally (it has no flush-only mode) and the link upsert needs
the Conversation's id to exist first, so there genuinely is a window between
"Conversation exists" and "link points at it" that cannot be closed without
changing that shared service -- out of this step's scope, and risky to
change for every other caller. The retry loop is the chosen mitigation:
every orphan window is bounded to a handful of statements, and a lost race
always converges on one Conversation per tuple, never leaks a dangling link,
and never returns a nonexistent id. `bind_context` commits internally and
must therefore be called on a session dedicated to this turn (per AD-8/
FR-16, the executor already opens and closes its own `SessionLocal()` per
turn) -- never on a shared or fixture-rolled-back session.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Optional

from sqlalchemy.orm import Session

from models.agent import Agent
from models.conversation import ConversationSource
from repositories.a2a_context_link_repository import A2AContextLinkRepository
from services.conversation_service import ConversationService
from utils.logger import get_logger
from utils.security import hash_api_key

logger = get_logger(__name__)

# AD-7: client-supplied contextId/taskId must be at most 36 characters (the SDK
# columns are String(36)) and drawn from this charset.
_CONTEXT_ID_MAX_LENGTH = 36
_CONTEXT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")

_MAX_BIND_ATTEMPTS = 4  # bounds the optimistic retry loop; see module docstring


class A2AContextBindingError(LookupError):
    """Raised when `agent_id` does not resolve to a real Agent scoped to
    `app_id`, or when the binding could not converge after repeated
    concurrent writes. The message is intentionally generic -- it carries no
    ids -- so callers can surface it directly without leaking internal
    identifiers; details are logged server-side at the raise site."""


class A2AInvalidContextIdError(ValueError):
    """Raised when a client-supplied `context_id` violates AD-7's shape
    (length <= 36, charset `[A-Za-z0-9._:-]`). Callers map this to the SDK's
    `InvalidParamsError`. The message is generic for the same reason as
    `A2AContextBindingError`."""


@dataclass(frozen=True)
class ContextBinding:
    conversation_id: int
    created: bool


def _validate_context_id(context_id: str) -> None:
    """AD-7 shape check, enforced again here as defense in depth before any
    DB write (the SDK's own `A2ARequestContextBuilder`, step_012, is expected
    to reject a malformed contextId before a task is even created)."""
    if (
        not context_id
        or len(context_id) > _CONTEXT_ID_MAX_LENGTH
        or not _CONTEXT_ID_PATTERN.match(context_id)
    ):
        logger.warning(
            "a2a.context_binding.invalid_context_id length=%s",
            len(context_id) if context_id else 0,
        )
        raise A2AInvalidContextIdError("invalid contextId")


def _load_scoped_agent(db: Session, *, app_id: int, agent_id: int) -> Agent:
    """Load `Agent` and verify it belongs to `app_id` before anything derived
    from the request is trusted. The caller must read `app_id` off the
    returned row (`agent.app_id`), never off its own parameter, for every
    subsequent link/Conversation operation."""
    agent = db.get(Agent, agent_id)
    if agent is None or agent.app_id != app_id:
        logger.warning(
            "a2a.context_binding.agent_app_mismatch agent_id=%s requested_app_id=%s",
            agent_id, app_id,
        )
        raise A2AContextBindingError("agent not found for the given app")
    return agent


def _ensure_user_context_key_matches(user_context: Dict, key_hash: str) -> None:
    """One source of truth for the caller's identity: the hash written to the
    link/Conversation (`key_hash`, derived from `api_key_raw`) must be the
    same hash `ConversationService.create_conversation` derives from
    `user_context["api_key"]`. Without this check a caller that passed a
    mismatched pair would get a Conversation whose `api_key_hash` does not
    match the link it is bound through."""
    user_context_key = user_context.get("api_key")
    if user_context_key is None or hash_api_key(user_context_key) != key_hash:
        logger.warning("a2a.context_binding.user_context_key_mismatch")
        raise A2AContextBindingError("user_context api_key does not match the caller's API key")


def _create_a2a_conversation(db: Session, *, agent_id: int, user_context: Dict):
    """Always create the conversation, even for has_memory=False agents (DEV-3)."""
    return ConversationService.create_conversation(
        db, agent_id=agent_id, user_context=user_context, title=None, source=ConversationSource.A2A
    )


def _try_bind_once(
    db: Session,
    *,
    app_id: int,
    agent_id: int,
    key_hash: str,
    context_id: str,
    user_context: Dict,
) -> Optional[ContextBinding]:
    """One optimistic attempt. Returns a `ContextBinding` on success, or
    `None` to signal that concurrent state changed under us and the caller
    should re-read and try again (see module docstring)."""
    link = A2AContextLinkRepository.get(
        db, app_id=app_id, agent_id=agent_id, key_hash=key_hash, context_id=context_id
    )

    if link is not None and link.conversation_id is not None:
        conversation_id = link.conversation_id  # capture before commit; no reload needed
        touched = A2AContextLinkRepository.touch(
            db, link_id=link.id, expected_conversation_id=conversation_id
        )
        db.commit()
        if touched:
            return ContextBinding(conversation_id=conversation_id, created=False)
        return None  # link vanished or was repaired concurrently; retry

    if link is not None and link.conversation_id is None:
        conversation = _create_a2a_conversation(db, agent_id=agent_id, user_context=user_context)
        conversation_id = conversation.conversation_id
        repaired = A2AContextLinkRepository.set_conversation_id(
            db, link_id=link.id, conversation_id=conversation_id
        )
        if repaired:
            db.commit()
            logger.info(
                "a2a.context_binding.repaired agent_id=%s conversation_id=%s", agent_id, conversation_id
            )
            return ContextBinding(conversation_id=conversation_id, created=True)
        # Lost the repair race: another caller already attached a Conversation to
        # this link (or it was deleted). Ours is brand new -- no turns, no
        # checkpointer state -- so a plain delete is enough; the async
        # ConversationService.delete_conversation would try to tear down state
        # that was never created.
        db.delete(conversation)
        db.commit()
        return None

    # Unknown tuple.
    conversation = _create_a2a_conversation(db, agent_id=agent_id, user_context=user_context)
    conversation_id = conversation.conversation_id
    inserted = A2AContextLinkRepository.insert_if_absent(
        db,
        app_id=app_id,
        agent_id=agent_id,
        key_hash=key_hash,
        context_id=context_id,
        conversation_id=conversation_id,
    )
    if inserted:
        db.commit()
        logger.info(
            "a2a.context_binding.created agent_id=%s conversation_id=%s", agent_id, conversation_id
        )
        return ContextBinding(conversation_id=conversation_id, created=True)

    # Lost the insert race: a concurrent caller already inserted the link for
    # this exact tuple. Discard our Conversation (same reasoning as above).
    db.delete(conversation)
    db.commit()

    winner = A2AContextLinkRepository.get(
        db, app_id=app_id, agent_id=agent_id, key_hash=key_hash, context_id=context_id
    )
    if winner is not None and winner.conversation_id is not None:
        winner_conversation_id = winner.conversation_id
        touched = A2AContextLinkRepository.touch(
            db, link_id=winner.id, expected_conversation_id=winner_conversation_id
        )
        db.commit()
        if touched:
            logger.info(
                "a2a.context_binding.race_lost agent_id=%s conversation_id=%s",
                agent_id, winner_conversation_id,
            )
            return ContextBinding(conversation_id=winner_conversation_id, created=False)

    # The winner vanished (its Conversation was deleted between our failed
    # insert and this re-read) or our touch lost yet another race. Signal a
    # retry instead of raising -- the next attempt re-reads from scratch.
    return None


def bind_context(
    db: Session,
    *,
    app_id: int,
    agent_id: int,
    api_key_raw: str,
    context_id: str,
    user_context: Dict,
) -> ContextBinding:
    """Resolve `context_id` to exactly one Conversation for this (app, agent, key).

    Args:
        db: Sync session; the caller owns its lifecycle (opened/closed per
            turn by the executor bridge, FR-16/NFR-4) and must not reuse a
            session shared with other work -- this function commits.
        app_id: The app id the caller believes the agent belongs to. Only
            used to validate the `Agent` row (see module docstring); the
            value actually persisted is always re-derived from that row.
        agent_id: The agent id from the A2A route path.
        api_key_raw: The raw API key string (never logged or persisted; only
            its SHA-256 hash is stored, via `utils.security.hash_api_key`).
        context_id: The SDK `contextId`, client-supplied or server-generated.
            Validated against AD-7's shape before any DB access.
        user_context: Passed straight through to
            `ConversationService.create_conversation`; must carry an
            `api_key` that hashes to the same value as `api_key_raw` (see
            `_ensure_user_context_key_matches`).

    Returns:
        ContextBinding(conversation_id, created).

    Raises:
        A2AInvalidContextIdError: `context_id` violates AD-7's shape.
        A2AContextBindingError: `agent_id` is not a real agent of `app_id`,
            `user_context["api_key"]` does not match `api_key_raw`, or the
            binding could not converge after `_MAX_BIND_ATTEMPTS` retries
            (only expected under pathological, sustained contention).
    """
    _validate_context_id(context_id)

    agent = _load_scoped_agent(db, app_id=app_id, agent_id=agent_id)
    resolved_app_id = agent.app_id  # authoritative from here on; never the raw parameter

    key_hash = hash_api_key(api_key_raw)
    _ensure_user_context_key_matches(user_context, key_hash)

    for _ in range(_MAX_BIND_ATTEMPTS):
        binding = _try_bind_once(
            db,
            app_id=resolved_app_id,
            agent_id=agent_id,
            key_hash=key_hash,
            context_id=context_id,
            user_context=user_context,
        )
        if binding is not None:
            return binding

    logger.error(
        "a2a.context_binding.exhausted_retries agent_id=%s attempts=%s", agent_id, _MAX_BIND_ATTEMPTS
    )
    raise A2AContextBindingError("could not bind context after repeated concurrent writes")
