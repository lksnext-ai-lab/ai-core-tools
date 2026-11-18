"""Integration coverage for step_013: contextId <-> Conversation binding (AD-9).

`step_012` (committed `a2a_committed_world` fixture) is not merged yet, so
this module builds its own minimal committed fixture, following the same
pattern as `tests/integration/test_oidc_duplicate_user_race.py`: real
`SessionLocal()` sessions that genuinely commit to the test DB (port 5433),
not the savepoint-rollback `db` fixture, because the race test needs a real
UNIQUE-constraint conflict (`uq_a2a_context_link_owner_ctx`) visible across
two independent DB transactions.

Covers (plan step_013 task 4 / spec AC-17, AC-18, AC-19, AC-37):
  - a new context creates a Conversation with source=A2A and api_key_hash set;
  - the same context returns the same conversation;
  - a different API key with the same context_id gets a different conversation (AC-18);
  - an unknown client-supplied context_id is bound (AC-19);
  - deleting the Conversation cascades the link away, so the next bind for
    that context gets a fresh Conversation with no prior memory (AC-37);
  - the concurrent race: two separate sessions binding the same brand-new
    context converge on exactly one Conversation.
"""

from __future__ import annotations

import threading
import uuid

from sqlalchemy import text

from db.database import SessionLocal
from models.a2a_context_link import A2AContextLink
from models.agent import Agent
from models.app import App
from models.conversation import Conversation, ConversationSource
from services.a2a_server.context_binding_service import bind_context
from utils.security import hash_api_key


def _unique_slug(label: str) -> str:
    return f"a2a-ctx-{label}-{uuid.uuid4().hex[:8]}"


class _World:
    """Minimal committed (App, Agent) pair plus two raw API keys for it."""

    def __init__(self, app_id: int, agent_id: int, other_app_id: int, other_agent_id: int):
        self.app_id = app_id
        self.agent_id = agent_id
        self.other_app_id = other_app_id
        self.other_agent_id = other_agent_id
        self.key_1 = f"a2a-test-key-1-{uuid.uuid4().hex}"
        self.key_2 = f"a2a-test-key-2-{uuid.uuid4().hex}"

    def user_context(self, raw_key: str) -> dict:
        return {"api_key": raw_key, "oauth": False}


def _build_world(label: str) -> _World:
    session = SessionLocal()
    try:
        app = App(name=_unique_slug(label))
        other_app = App(name=_unique_slug(f"{label}-other"))
        session.add_all([app, other_app])
        session.flush()

        agent = Agent(app_id=app.app_id, name=f"A2A Test Agent {label}", type="agent")
        other_agent = Agent(app_id=other_app.app_id, name=f"A2A Other Agent {label}", type="agent")
        session.add_all([agent, other_agent])
        session.commit()

        return _World(
            app_id=app.app_id,
            agent_id=agent.agent_id,
            other_app_id=other_app.app_id,
            other_agent_id=other_agent.agent_id,
        )
    finally:
        session.close()


def _cleanup_world(world: _World) -> None:
    """Best-effort teardown: delete links, conversations, agents and apps for
    both (app, agent) pairs created by `_build_world`, in dependency order."""
    session = SessionLocal()
    try:
        for agent_id in (world.agent_id, world.other_agent_id):
            session.query(A2AContextLink).filter(A2AContextLink.agent_id == agent_id).delete()
            session.query(Conversation).filter(Conversation.agent_id == agent_id).delete()
        session.query(Agent).filter(Agent.agent_id.in_([world.agent_id, world.other_agent_id])).delete(
            synchronize_session=False
        )
        session.query(App).filter(App.app_id.in_([world.app_id, world.other_app_id])).delete(
            synchronize_session=False
        )
        session.commit()
    finally:
        session.close()


class TestBindContextNewAndRepeatedContext:
    def test_new_context_creates_a2a_conversation(self, test_engine):
        world = _build_world("new-ctx")
        try:
            session = SessionLocal()
            try:
                binding = bind_context(
                    session,
                    app_id=world.app_id,
                    agent_id=world.agent_id,
                    api_key_raw=world.key_1,
                    context_id="ctx-new-1",
                    user_context=world.user_context(world.key_1),
                )
                assert binding.created is True

                conversation = session.get(Conversation, binding.conversation_id)
                assert conversation is not None
                assert conversation.source == ConversationSource.A2A
                assert conversation.api_key_hash == hash_api_key(world.key_1)
            finally:
                session.close()
        finally:
            _cleanup_world(world)

    def test_same_context_returns_same_conversation(self, test_engine):
        """AC-17 (service level): a follow-up with the same contextId reuses
        the same Conversation."""
        world = _build_world("repeat-ctx")
        try:
            session = SessionLocal()
            try:
                first = bind_context(
                    session,
                    app_id=world.app_id,
                    agent_id=world.agent_id,
                    api_key_raw=world.key_1,
                    context_id="ctx-repeat-1",
                    user_context=world.user_context(world.key_1),
                )
                second = bind_context(
                    session,
                    app_id=world.app_id,
                    agent_id=world.agent_id,
                    api_key_raw=world.key_1,
                    context_id="ctx-repeat-1",
                    user_context=world.user_context(world.key_1),
                )
            finally:
                session.close()

            assert first.created is True
            assert second.created is False
            assert second.conversation_id == first.conversation_id
        finally:
            _cleanup_world(world)


class TestBindContextPerKeyIsolation:
    def test_different_key_same_context_gets_different_conversation(self, test_engine):
        """AC-18: K2 with the same contextId as K1 gets its own Conversation;
        K1's conversation is not reused or exposed."""
        world = _build_world("per-key")
        try:
            session = SessionLocal()
            try:
                k1_binding = bind_context(
                    session,
                    app_id=world.app_id,
                    agent_id=world.agent_id,
                    api_key_raw=world.key_1,
                    context_id="ctx-shared",
                    user_context=world.user_context(world.key_1),
                )
                k2_binding = bind_context(
                    session,
                    app_id=world.app_id,
                    agent_id=world.agent_id,
                    api_key_raw=world.key_2,
                    context_id="ctx-shared",
                    user_context=world.user_context(world.key_2),
                )
            finally:
                session.close()

            assert k1_binding.conversation_id != k2_binding.conversation_id
        finally:
            _cleanup_world(world)


class TestBindContextUnknownClientContext:
    def test_unknown_client_supplied_context_is_bound(self, test_engine):
        """AC-19: an unknown client-supplied contextId is accepted and bound
        for that owner, not rejected."""
        world = _build_world("unknown-ctx")
        try:
            session = SessionLocal()
            try:
                binding = bind_context(
                    session,
                    app_id=world.app_id,
                    agent_id=world.agent_id,
                    api_key_raw=world.key_1,
                    context_id="client-chosen-unknown-ctx",
                    user_context=world.user_context(world.key_1),
                )
            finally:
                session.close()

            assert binding.created is True
            assert binding.conversation_id is not None
        finally:
            _cleanup_world(world)


class TestBindContextDeletedConversationCascades:
    def test_deleting_conversation_cascades_link_and_rebinds_fresh(self, test_engine):
        """AC-37: deleting the bound Conversation cascades the link row away
        (ON DELETE CASCADE); a later bind for the same contextId creates a
        brand-new Conversation rather than erroring or reviving the old one."""
        world = _build_world("cascade")
        try:
            session = SessionLocal()
            try:
                first = bind_context(
                    session,
                    app_id=world.app_id,
                    agent_id=world.agent_id,
                    api_key_raw=world.key_1,
                    context_id="ctx-cascade",
                    user_context=world.user_context(world.key_1),
                )

                # Delete the Conversation directly (not via the service) to isolate the
                # DB-level FK cascade from any application-level cleanup logic.
                session.query(Conversation).filter(
                    Conversation.conversation_id == first.conversation_id
                ).delete()
                session.commit()

                remaining_links = (
                    session.query(A2AContextLink)
                    .filter(A2AContextLink.context_id == "ctx-cascade")
                    .count()
                )
                assert remaining_links == 0, "deleting the Conversation must cascade the link away"

                second = bind_context(
                    session,
                    app_id=world.app_id,
                    agent_id=world.agent_id,
                    api_key_raw=world.key_1,
                    context_id="ctx-cascade",
                    user_context=world.user_context(world.key_1),
                )
            finally:
                session.close()

            assert second.created is True
            assert second.conversation_id != first.conversation_id
        finally:
            _cleanup_world(world)


class TestBindContextAppAgentMismatchRejected:
    def test_agent_from_another_app_is_rejected(self, test_engine):
        """The step_007 review requirement: app_id must come from the loaded
        Agent row, never from request input. An agent that is real but
        belongs to a different app must be rejected, not silently bound."""
        from services.a2a_server.context_binding_service import A2AContextBindingError

        world = _build_world("mismatch")
        try:
            session = SessionLocal()
            try:
                import pytest

                with pytest.raises(A2AContextBindingError):
                    bind_context(
                        session,
                        app_id=world.app_id,
                        agent_id=world.other_agent_id,  # belongs to world.other_app_id, not world.app_id
                        api_key_raw=world.key_1,
                        context_id="ctx-mismatch",
                        user_context=world.user_context(world.key_1),
                    )

                leftover_links = (
                    session.query(A2AContextLink)
                    .filter(A2AContextLink.context_id == "ctx-mismatch")
                    .count()
                )
                assert leftover_links == 0
                leftover_conversations = (
                    session.query(Conversation)
                    .filter(Conversation.agent_id == world.other_agent_id)
                    .count()
                )
                assert leftover_conversations == 0
            finally:
                session.close()
        finally:
            _cleanup_world(world)


class TestBindContextConcurrentRace:
    def test_concurrent_binds_converge_to_single_conversation(self, test_engine):
        """Reproduces the AD-9 step 3/4 race: two separate sessions both see
        the context as unknown and race to create+insert. Mirrors
        `test_oidc_duplicate_user_race.py`'s deterministic strategy: Session B
        is bumped to REPEATABLE READ before its first read, fixing its MVCC
        snapshot before Session A's commit, so the real unique constraint
        (not timing) decides the race."""
        world = _build_world("race")
        try:
            session_a = SessionLocal()
            session_b = SessionLocal()
            try:
                session_b.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
                # Touch the table under B's snapshot so it is fixed before A commits.
                session_b.query(A2AContextLink).filter(
                    A2AContextLink.context_id == "ctx-race"
                ).count()

                binding_a = bind_context(
                    session_a,
                    app_id=world.app_id,
                    agent_id=world.agent_id,
                    api_key_raw=world.key_1,
                    context_id="ctx-race",
                    user_context=world.user_context(world.key_1),
                )
                assert binding_a.created is True

                # Session B still cannot see A's commit (frozen snapshot), so its own
                # A2AContextLinkRepository.get() returns None and it creates a second
                # Conversation + attempts the insert -- which collides with the real
                # uq_a2a_context_link_owner_ctx constraint. bind_context must recover:
                # delete its own Conversation, re-read the winner, and return its id.
                binding_b = bind_context(
                    session_b,
                    app_id=world.app_id,
                    agent_id=world.agent_id,
                    api_key_raw=world.key_1,
                    context_id="ctx-race",
                    user_context=world.user_context(world.key_1),
                )

                assert binding_b.created is False, (
                    "the losing call must converge on the winner's Conversation, "
                    "not create a second one"
                )
                assert binding_b.conversation_id == binding_a.conversation_id
            finally:
                session_a.close()
                session_b.close()

            verify_session = SessionLocal()
            try:
                link_count = (
                    verify_session.query(A2AContextLink)
                    .filter(A2AContextLink.context_id == "ctx-race")
                    .count()
                )
                # Not filtered by conversation_id: counting only "does binding_a's id
                # exist" would be tautologically 1 even if a second, orphaned
                # Conversation also existed for this agent. Filtering by agent_id
                # alone (this world's agent is used by nothing else) is the real
                # invariant: exactly one Conversation must exist for it.
                conversation_count = (
                    verify_session.query(Conversation)
                    .filter(Conversation.agent_id == world.agent_id)
                    .count()
                )
                assert link_count == 1, f"Expected exactly 1 link row, found {link_count}"
                assert conversation_count == 1, f"Expected exactly 1 Conversation row, found {conversation_count}"
            finally:
                verify_session.close()
        finally:
            _cleanup_world(world)


class TestBindContextRepairRaceWithRealThreads:
    """Review round 1, MEDIUM-1: a link whose `conversation_id` is still NULL
    (a pending repair) that gets repaired by N concurrent *real threads* must
    converge on exactly one Conversation, every thread returning the same
    `conversation_id`, with zero orphaned Conversations.

    Pre-fix, `set_conversation_id` was an unconditional UPDATE: 4 concurrent
    repairs produced 4 Conversations (3 orphaned, no link pointing at them)
    with the threads splitting across whichever id each one's own UPDATE
    happened to see last. The conditional `WHERE conversation_id IS NULL`
    guard plus the retry loop in `bind_context` fixes that.
    """

    def test_concurrent_repairs_converge_to_single_conversation(self, test_engine):
        from repositories.a2a_context_link_repository import A2AContextLinkRepository

        world = _build_world("repair-race")
        try:
            # Seed a link with conversation_id=NULL directly (bypassing bind_context)
            # so this test isolates the repair path from the unknown-tuple insert path.
            seed_session = SessionLocal()
            try:
                inserted = A2AContextLinkRepository.insert_if_absent(
                    seed_session,
                    app_id=world.app_id,
                    agent_id=world.agent_id,
                    key_hash=hash_api_key(world.key_1),
                    context_id="ctx-repair-race",
                    conversation_id=None,
                )
                seed_session.commit()
                assert inserted is True
            finally:
                seed_session.close()

            n_threads = 4
            barrier = threading.Barrier(n_threads)
            results: list = [None] * n_threads
            errors: list = [None] * n_threads

            def _worker(index: int) -> None:
                session = SessionLocal()
                try:
                    barrier.wait(timeout=10)
                    results[index] = bind_context(
                        session,
                        app_id=world.app_id,
                        agent_id=world.agent_id,
                        api_key_raw=world.key_1,
                        context_id="ctx-repair-race",
                        user_context=world.user_context(world.key_1),
                    )
                except Exception as exc:  # noqa: BLE001 -- surfaced via `errors`, not swallowed
                    errors[index] = exc
                finally:
                    session.close()

            threads = [threading.Thread(target=_worker, args=(i,)) for i in range(n_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

            assert all(e is None for e in errors), f"worker errors: {errors}"
            assert all(r is not None for r in results)

            conversation_ids = {r.conversation_id for r in results}
            assert len(conversation_ids) == 1, (
                f"all {n_threads} concurrent repairs must converge on the same conversation_id, "
                f"got {conversation_ids}"
            )

            verify_session = SessionLocal()
            try:
                conversation_count = (
                    verify_session.query(Conversation)
                    .filter(Conversation.agent_id == world.agent_id)
                    .count()
                )
                link_count = (
                    verify_session.query(A2AContextLink)
                    .filter(A2AContextLink.context_id == "ctx-repair-race")
                    .count()
                )
                assert conversation_count == 1, (
                    f"expected exactly 1 Conversation (no orphans), found {conversation_count}"
                )
                assert link_count == 1
            finally:
                verify_session.close()
        finally:
            _cleanup_world(world)


class TestBindContextUnknownTupleRealThreadBarrier:
    """Review round 1, MEDIUM-3: a true thread race (Barrier-synchronized, not
    the REPEATABLE-READ simulation used above) on a brand-new, unknown
    context_id must also converge on exactly one Conversation and one link,
    with exactly one of the 8 threads reporting `created=True`."""

    def test_eight_threads_same_unknown_context_converge(self, test_engine):
        world = _build_world("barrier-unknown")
        try:
            n_threads = 8
            barrier = threading.Barrier(n_threads)
            results: list = [None] * n_threads
            errors: list = [None] * n_threads

            def _worker(index: int) -> None:
                session = SessionLocal()
                try:
                    barrier.wait(timeout=10)
                    results[index] = bind_context(
                        session,
                        app_id=world.app_id,
                        agent_id=world.agent_id,
                        api_key_raw=world.key_1,
                        context_id="ctx-barrier-unknown",
                        user_context=world.user_context(world.key_1),
                    )
                except Exception as exc:  # noqa: BLE001
                    errors[index] = exc
                finally:
                    session.close()

            threads = [threading.Thread(target=_worker, args=(i,)) for i in range(n_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

            assert all(e is None for e in errors), f"worker errors: {errors}"
            assert all(r is not None for r in results)

            conversation_ids = {r.conversation_id for r in results}
            assert len(conversation_ids) == 1, (
                f"all {n_threads} concurrent binds for the same unknown context must converge on "
                f"the same conversation_id, got {conversation_ids}"
            )
            assert sum(1 for r in results if r.created) == 1, "exactly one thread must report created=True"

            verify_session = SessionLocal()
            try:
                conversation_count = (
                    verify_session.query(Conversation)
                    .filter(Conversation.agent_id == world.agent_id)
                    .count()
                )
                link_count = (
                    verify_session.query(A2AContextLink)
                    .filter(A2AContextLink.context_id == "ctx-barrier-unknown")
                    .count()
                )
                assert conversation_count == 1, f"expected 1 Conversation, found {conversation_count}"
                assert link_count == 1, f"expected 1 link, found {link_count}"
            finally:
                verify_session.close()
        finally:
            _cleanup_world(world)


class TestDeleteOlderThanRespectsRecentlyTouchedLinks:
    """LOW-7: `delete_older_than` must not purge a link that is actually
    still in use -- the DELETE's own WHERE re-checks `updated_at < cutoff`,
    not just the ids an earlier SELECT picked as candidates."""

    def test_only_the_stale_link_is_deleted(self, test_engine):
        from datetime import datetime, timedelta

        from repositories.a2a_context_link_repository import A2AContextLinkRepository

        world = _build_world("retention")
        try:
            session = SessionLocal()
            try:
                inserted_stale = A2AContextLinkRepository.insert_if_absent(
                    session,
                    app_id=world.app_id,
                    agent_id=world.agent_id,
                    key_hash=hash_api_key(world.key_1),
                    context_id="ctx-stale",
                    conversation_id=None,
                )
                inserted_fresh = A2AContextLinkRepository.insert_if_absent(
                    session,
                    app_id=world.app_id,
                    agent_id=world.agent_id,
                    key_hash=hash_api_key(world.key_1),
                    context_id="ctx-fresh",
                    conversation_id=None,
                )
                session.commit()
                assert inserted_stale and inserted_fresh

                long_ago = datetime.utcnow() - timedelta(days=60)
                session.query(A2AContextLink).filter(
                    A2AContextLink.context_id == "ctx-stale"
                ).update({"updated_at": long_ago})
                session.commit()

                cutoff = datetime.utcnow() - timedelta(days=30)
                deleted = A2AContextLinkRepository.delete_older_than(session, cutoff)
                session.commit()

                assert deleted == 1

                remaining = {
                    row.context_id
                    for row in session.query(A2AContextLink)
                    .filter(A2AContextLink.context_id.in_(["ctx-stale", "ctx-fresh"]))
                    .all()
                }
                assert remaining == {"ctx-fresh"}
            finally:
                session.close()
        finally:
            _cleanup_world(world)
