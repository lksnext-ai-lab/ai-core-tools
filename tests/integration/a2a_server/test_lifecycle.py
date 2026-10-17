"""Integration coverage for step_018 (AD-10): deletion hooks, purge queue, retention, the stale-task
sweep, the orphan pass and the sweep leader lock.

Drives real `A2ARuntime`s and the pinned a2a-sdk store against committed test-DB rows (no HTTP, no
LLM). The maintenance worker is started/stopped inside each test's own event loop.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import suppress
from datetime import datetime, timedelta

import pytest
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.cluster.version import TaskVersion
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import a2a_pb2 as pb
from a2a.utils.errors import TaskNotFoundError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from db.database import SessionLocal, async_engine
from models.a2a_context_link import A2AContextLink
from models.agent import Agent
from models.conversation import Conversation, ConversationSource
from repositories.a2a_task_repository import A2ATaskRepository
from services.a2a_server import maintenance_worker
from services.a2a_server import runtime as runtime_module
from services.a2a_server.identity import context_for_owner, owner_for, owner_prefix
from services.a2a_server.sdk_models import get_sdk_models
from utils.a2a_config import get_a2a_config
from utils.security import hash_api_key

pytestmark = pytest.mark.integration

_KEY_HASH = "b" * 64


@pytest.fixture(autouse=True)
def _clear_a2a_config_cache():
    get_a2a_config.cache_clear()
    yield
    get_a2a_config.cache_clear()


@pytest.fixture
def fast_grace(monkeypatch):
    """Shortest legal grace: keepalive 0.2s + coalesce 0ms -> clamp floor ceil(0.2) + 1 = 2s."""
    monkeypatch.setenv("A2A_KEEPALIVE_SECONDS", "0.2")
    monkeypatch.setenv("A2A_STREAM_COALESCE_MS", "0")
    monkeypatch.setenv("A2A_PURGE_GRACE_SECONDS", "0")
    get_a2a_config.cache_clear()
    cfg = get_a2a_config()
    assert cfg.purge_grace_seconds == 2
    assert cfg.purge_grace_seconds > cfg.keepalive_seconds + cfg.stream_coalesce_ms / 1000
    return cfg


class _ActiveGlobalRuntime:
    """Registers `rt` as the module-level runtime for the `with` block's duration."""

    def __init__(self, rt) -> None:
        self._rt = rt
        self._previous = None

    def __enter__(self):
        self._previous = runtime_module.get_runtime()
        runtime_module.set_runtime(self._rt)
        return self._rt

    def __exit__(self, *exc_info) -> None:
        runtime_module.set_runtime(self._previous)


class _RunningMaintenanceWorker:
    async def __aenter__(self):
        self._task = maintenance_worker.start_a2a_maintenance_worker()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await maintenance_worker.stop_a2a_maintenance_worker(self._task)


class _SlowExecutor(AgentExecutor):
    """Stays WORKING, emitting a keepalive every `keepalive_s`, until cancelled (or `max_s` elapses)."""

    def __init__(self, *, keepalive_s: float = 0.2, max_s: float = 30.0) -> None:
        self._keepalive_s = keepalive_s
        self._max_s = max_s
        self.cancelled = asyncio.Event()

    async def execute(self, context, event_queue) -> None:
        if context.current_task is None:
            await event_queue.enqueue_event(
                pb.Task(
                    id=context.task_id,
                    context_id=context.context_id,
                    status=pb.TaskStatus(state=pb.TaskState.TASK_STATE_SUBMITTED),
                )
            )
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.start_work()
        try:
            elapsed = 0.0
            while elapsed < self._max_s:
                await asyncio.sleep(self._keepalive_s)
                elapsed += self._keepalive_s
                await updater.update_status(pb.TaskState.TASK_STATE_WORKING)
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        await updater.complete()

    async def cancel(self, context, event_queue) -> None:
        self.cancelled.set()
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        with suppress(Exception):
            await updater.cancel()


async def _save_new_task(
    rt, *, owner: str, task_id: str, state: int, status_time: datetime | None = None
) -> None:
    task = pb.Task(id=task_id, context_id=f"ctx-{task_id}"[:36], status=pb.TaskStatus(state=state))
    if status_time is not None:
        task.status.timestamp.FromDatetime(status_time)
    await rt.store.save(
        task, event=task, prev=None, prev_version=TaskVersion.MISSING, context=context_for_owner(owner)
    )


def _short_id(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:12]}"


async def _count(model, prefix: str) -> int:
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(
            select(func.count()).select_from(model).where(model.owner.like(f"{prefix}%"))
        )
        return result.scalar_one()


async def _counts(prefix: str) -> tuple[int, int, int]:
    models = get_sdk_models()
    return (
        await _count(models.task, prefix),
        await _count(models.event, prefix),
        await _count(models.version, prefix),
    )


def _set_last_updated(task_ids: list[str], when: datetime) -> None:
    models = get_sdk_models()
    db = SessionLocal()
    try:
        db.query(models.task).filter(models.task.id.in_(task_ids)).update(
            {"last_updated": when}, synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


def _event_count_for(task_ids: list[str]) -> int:
    models = get_sdk_models()
    db = SessionLocal()
    try:
        return db.query(models.event).filter(models.event.task_id.in_(task_ids)).count()
    finally:
        db.close()


def _row_exists(model, task_id: str) -> bool:
    db = SessionLocal()
    try:
        return db.query(model).filter(model.task_id == task_id).first() is not None
    finally:
        db.close()


def _create_links(world, *, agent_id: int, count: int, updated_at: datetime) -> list[int]:
    db = SessionLocal()
    try:
        links = [
            A2AContextLink(
                app_id=world.app_id,
                agent_id=agent_id,
                conversation_id=None,
                api_key_hash=hash_api_key(world.key_1_raw),
                context_id=_short_id("lnk"),
                created_at=updated_at,
                updated_at=updated_at,
            )
            for _ in range(count)
        ]
        db.add_all(links)
        db.commit()
        return [link.id for link in links]
    finally:
        db.close()


def _link_count(*, ids: list[int] | None = None, agent_id: int | None = None) -> int:
    db = SessionLocal()
    try:
        query = db.query(A2AContextLink)
        if ids is not None:
            query = query.filter(A2AContextLink.id.in_(ids))
        if agent_id is not None:
            query = query.filter(A2AContextLink.agent_id == agent_id)
        return query.count()
    finally:
        db.close()


class TestAgentDeletionPurge:
    """AC-35: delete_agent returns immediately; after the grace period the agent's A2A rows are gone and
    the in-flight task was cancelled through the handler."""

    async def test_deletes_agent_and_cancels_then_purges_after_grace(
        self, a2a_committed_world, a2a_runtime_factory, fast_grace, monkeypatch,
    ):
        world = a2a_committed_world
        executor = _SlowExecutor(keepalive_s=fast_grace.keepalive_seconds)
        rt = a2a_runtime_factory(executor)
        owner = owner_for(world.app_id, world.agent_public_id, hash_api_key(world.key_1_raw))
        prefix = owner_prefix(world.app_id, world.agent_public_id)
        completed_id = _short_id("ac35-done")

        cancelled_ids: list[str] = []
        original_cancel = rt.handler.on_cancel_task

        async def _spy_cancel(request, ctx):
            cancelled_ids.append(request.id)
            return await original_cancel(request, ctx)

        monkeypatch.setattr(rt.handler, "on_cancel_task", _spy_cancel)

        with _ActiveGlobalRuntime(rt):
            await _save_new_task(rt, owner=owner, task_id=completed_id, state=pb.TaskState.TASK_STATE_COMPLETED)
            in_flight = await rt.handler.on_message_send(
                pb.SendMessageRequest(
                    message=pb.Message(
                        message_id=str(uuid.uuid4()), role=pb.ROLE_USER, parts=[pb.Part(text="hi")]
                    ),
                    configuration=pb.SendMessageConfiguration(return_immediately=True),
                ),
                context_for_owner(owner),
            )
            in_flight_id = in_flight.id
            _create_links(world, agent_id=world.agent_public_id, count=1, updated_at=datetime.utcnow())
            assert _link_count(agent_id=world.agent_public_id) == 1

            tasks_before, events_before, versions_before = await _counts(prefix)
            assert tasks_before == 2
            assert events_before >= 2
            assert versions_before == 2

            async with _RunningMaintenanceWorker():
                db = SessionLocal()
                try:
                    from services.agent_service import AgentService

                    deleted = AgentService().delete_agent(db, world.agent_public_id)
                    agent_gone = db.query(Agent).filter(Agent.agent_id == world.agent_public_id).first() is None
                finally:
                    db.close()
                assert deleted is True
                assert agent_gone is True
                # Deletion returned before the (async, grace-delayed) purge ran.
                assert (await _counts(prefix))[0] == 2
                # Link rows go immediately through the FK cascade.
                assert _link_count(agent_id=world.agent_public_id) == 0

                await maintenance_worker.wait_idle()

            assert cancelled_ids == [in_flight_id]
            assert executor.cancelled.is_set()
            assert await _counts(prefix) == (0, 0, 0)
            for task_id in (completed_id, in_flight_id):
                with pytest.raises(TaskNotFoundError):
                    await rt.handler.on_get_task(pb.GetTaskRequest(id=task_id), context_for_owner(owner))


class TestAppDeletionPurge:
    """AC-36: delete_app removes all of the app's A2A tasks, events and versions."""

    async def test_deletes_app_and_purges_every_agent_prefix(
        self, a2a_committed_world, a2a_runtime_factory, fast_grace,
    ):
        world = a2a_committed_world
        rt = a2a_runtime_factory()
        owner = owner_for(world.other_app_id, world.other_agent_id, hash_api_key(world.other_key_raw))
        prefix = owner_prefix(world.other_app_id)

        with _ActiveGlobalRuntime(rt):
            for _ in range(3):
                await _save_new_task(
                    rt, owner=owner, task_id=_short_id("ac36"), state=pb.TaskState.TASK_STATE_COMPLETED
                )
            tasks_before, events_before, versions_before = await _counts(prefix)
            assert tasks_before == 3
            assert events_before == 3
            assert versions_before == 3

            async with _RunningMaintenanceWorker():
                db = SessionLocal()
                try:
                    from services.app_service import AppService

                    deleted = AppService(db).delete_app(world.other_app_id)
                finally:
                    db.close()
                assert deleted is True
                await maintenance_worker.wait_idle()

            assert await _counts(prefix) == (0, 0, 0)


class TestStaleSweepAndLeaderLock:
    """AC-38: the leader-gated sweep purges old rows and fails stale tasks; a non-leader does nothing."""

    async def test_run_sweep_once_purges_old_rows_and_fails_stale_tasks(
        self, a2a_committed_world, a2a_runtime_factory,
    ):
        world = a2a_committed_world
        rt = a2a_runtime_factory()
        owner = owner_for(world.app_id, world.agent_public_id, hash_api_key(world.key_1_raw))
        models = get_sdk_models()
        old_id, stale_id, fresh_id = _short_id("ac38-old"), _short_id("ac38-stale"), _short_id("ac38-fresh")
        long_ago = datetime.utcnow() - timedelta(seconds=1000)

        with _ActiveGlobalRuntime(rt):
            await _save_new_task(rt, owner=owner, task_id=old_id, state=pb.TaskState.TASK_STATE_COMPLETED)
            await _save_new_task(
                rt, owner=owner, task_id=stale_id, state=pb.TaskState.TASK_STATE_WORKING, status_time=long_ago
            )
            # Old `last_updated` column but a fresh stored status timestamp: the reload check must skip it.
            await _save_new_task(
                rt, owner=owner, task_id=fresh_id, state=pb.TaskState.TASK_STATE_WORKING,
                status_time=datetime.utcnow(),
            )
            _set_last_updated([old_id], datetime.utcnow() - timedelta(days=40))
            _set_last_updated([stale_id, fresh_id], long_ago)
            stale_events_before = _event_count_for([stale_id])

            assert await maintenance_worker.run_sweep_once() is True

            db = SessionLocal()
            try:
                assert db.query(models.task).filter(models.task.id == old_id).first() is None
                assert _event_count_for([old_id]) == 0
                assert _row_exists(models.version, old_id) is False
                stale_row = db.query(models.task).filter(models.task.id == stale_id).one()
                assert stale_row.status["state"] == "TASK_STATE_FAILED"
                fresh_row = db.query(models.task).filter(models.task.id == fresh_id).one()
                assert fresh_row.status["state"] == "TASK_STATE_WORKING"
            finally:
                db.close()
            assert _event_count_for([stale_id]) == stale_events_before + 1

    async def test_lock_is_released_after_a_sweep(self, a2a_committed_world):
        assert await maintenance_worker.run_sweep_once() is True
        async with async_engine.connect() as other:
            acquired = (
                await other.execute(select(func.pg_try_advisory_lock(maintenance_worker.LEADER_LOCK_KEY)))
            ).scalar()
            assert acquired is True
            released = (
                await other.execute(select(func.pg_advisory_unlock(maintenance_worker.LEADER_LOCK_KEY)))
            ).scalar()
            assert released is True

    async def test_run_sweep_once_is_a_noop_while_another_connection_holds_the_leader_lock(
        self, a2a_committed_world, a2a_runtime_factory,
    ):
        world = a2a_committed_world
        rt = a2a_runtime_factory()
        owner = owner_for(world.app_id, world.agent_public_id, hash_api_key(world.key_1_raw))
        models = get_sdk_models()
        old_id = _short_id("ac38-lock")

        with _ActiveGlobalRuntime(rt):
            await _save_new_task(rt, owner=owner, task_id=old_id, state=pb.TaskState.TASK_STATE_COMPLETED)
            _set_last_updated([old_id], datetime.utcnow() - timedelta(days=40))

            async with async_engine.connect() as holder_conn:
                acquired = (
                    await holder_conn.execute(
                        select(func.pg_try_advisory_lock(maintenance_worker.LEADER_LOCK_KEY))
                    )
                ).scalar()
                assert acquired is True
                try:
                    assert await maintenance_worker.run_sweep_once() is False
                    db = SessionLocal()
                    try:
                        assert db.query(models.task).filter(models.task.id == old_id).first() is not None
                    finally:
                        db.close()
                finally:
                    await holder_conn.execute(
                        select(func.pg_advisory_unlock(maintenance_worker.LEADER_LOCK_KEY))
                    )
                    await holder_conn.commit()


class TestBatchedPurgesTerminate:
    """Every batched purge with more rows than its batch size terminates and removes every row."""

    async def test_event_only_retention_with_more_terminal_tasks_than_batch(
        self, a2a_committed_world, a2a_runtime_factory,
    ):
        world = a2a_committed_world
        rt = a2a_runtime_factory()
        owner = owner_for(world.app_id, world.agent_public_id, hash_api_key(world.key_1_raw))
        prefix = owner_prefix(world.app_id, world.agent_public_id)
        old_terminal = [_short_id("rb6-old") for _ in range(7)]
        recent_terminal = _short_id("rb6-recent")
        old_working = _short_id("rb6-working")

        with _ActiveGlobalRuntime(rt):
            for task_id in old_terminal:
                await _save_new_task(rt, owner=owner, task_id=task_id, state=pb.TaskState.TASK_STATE_COMPLETED)
            await _save_new_task(rt, owner=owner, task_id=recent_terminal, state=pb.TaskState.TASK_STATE_FAILED)
            await _save_new_task(rt, owner=owner, task_id=old_working, state=pb.TaskState.TASK_STATE_WORKING)
            an_hour_ago = datetime.utcnow() - timedelta(hours=1)
            _set_last_updated(old_terminal + [old_working], an_hour_ago)
            old_events = _event_count_for(old_terminal)
            assert old_events == 7

            purged = await asyncio.wait_for(
                A2ATaskRepository.purge_terminal_events_older_than(
                    datetime.utcnow() - timedelta(minutes=15), batch=3
                ),
                timeout=30,
            )

            assert purged == old_events
            assert _event_count_for(old_terminal) == 0
            assert _event_count_for([recent_terminal]) == 1
            assert _event_count_for([old_working]) == 1
            # Event-only: task and version rows are untouched.
            tasks, _, versions = await _counts(prefix)
            assert tasks == 9
            assert versions == 9

    async def test_purge_prefix_with_more_rows_than_batch(self, a2a_committed_world, a2a_runtime_factory):
        world = a2a_committed_world
        rt = a2a_runtime_factory()
        owner = owner_for(world.app_id, world.agent_api_key_id, hash_api_key(world.key_1_raw))
        prefix = owner_prefix(world.app_id, world.agent_api_key_id)
        models = get_sdk_models()

        with _ActiveGlobalRuntime(rt):
            for _ in range(7):
                await _save_new_task(
                    rt, owner=owner, task_id=_short_id("pfx"), state=pb.TaskState.TASK_STATE_COMPLETED
                )
            # Owner-scoped event/version rows whose task row is already gone.
            db = SessionLocal()
            try:
                for _ in range(4):
                    dangling = _short_id("dangling")
                    db.add(models.event(task_id=dangling, owner=owner, task_version=1, event_data=b"x"))
                    db.add(models.version(task_id=dangling, owner=owner, version=1))
                db.commit()
            finally:
                db.close()
            assert await _counts(prefix) == (7, 11, 11)

            purged = await asyncio.wait_for(A2ATaskRepository.purge_prefix(prefix, batch=3), timeout=30)

            assert purged == 7
            assert await _counts(prefix) == (0, 0, 0)

    async def test_purge_older_than_with_more_rows_than_batch(self, a2a_committed_world, a2a_runtime_factory):
        world = a2a_committed_world
        rt = a2a_runtime_factory()
        owner = owner_for(world.app_id, world.agent_disabled_id, hash_api_key(world.key_1_raw))
        prefix = owner_prefix(world.app_id, world.agent_disabled_id)
        old_ids = [_short_id("old") for _ in range(7)]
        keep_id = _short_id("keep")

        with _ActiveGlobalRuntime(rt):
            for task_id in old_ids + [keep_id]:
                await _save_new_task(rt, owner=owner, task_id=task_id, state=pb.TaskState.TASK_STATE_COMPLETED)
            _set_last_updated(old_ids, datetime.utcnow() - timedelta(days=40))

            purged = await asyncio.wait_for(
                A2ATaskRepository.purge_older_than(datetime.utcnow() - timedelta(days=30), batch=3), timeout=30
            )

            assert purged >= 7
            assert await _counts(prefix) == (1, 1, 1)

    async def test_link_retention_with_more_rows_than_batch(self, a2a_committed_world, monkeypatch):
        world = a2a_committed_world
        monkeypatch.setattr(maintenance_worker, "_LINK_PURGE_BATCH", 2)
        old_ids = _create_links(
            world, agent_id=world.agent_frozen_id, count=5, updated_at=datetime.utcnow() - timedelta(days=60)
        )
        fresh_ids = _create_links(world, agent_id=world.agent_frozen_id, count=1, updated_at=datetime.utcnow())

        deleted = await asyncio.to_thread(
            maintenance_worker._delete_old_links_sync, datetime.utcnow() - timedelta(days=30)
        )

        assert deleted >= 5
        assert _link_count(ids=old_ids) == 0
        assert _link_count(ids=fresh_ids) == 1


class TestOrphanSweep:
    """AD-10 (c): owners whose agent no longer exists are purged; existing agents' rows are kept."""

    async def _seed(self, rt, world) -> tuple[str, str, str, str]:
        real_owner = owner_for(world.app_id, world.agent_public_id, _KEY_HASH)
        missing_agent_id = 2_000_000_000 + int(uuid.uuid4().int % 100_000_000)
        orphan_owner = owner_for(world.app_id, missing_agent_id, _KEY_HASH)
        await _save_new_task(rt, owner=real_owner, task_id=_short_id("real"), state=pb.TaskState.TASK_STATE_COMPLETED)
        await _save_new_task(
            rt, owner=orphan_owner, task_id=_short_id("orphan"), state=pb.TaskState.TASK_STATE_COMPLETED
        )
        return (
            real_owner,
            orphan_owner,
            owner_prefix(world.app_id, world.agent_public_id),
            owner_prefix(world.app_id, missing_agent_id),
        )

    async def test_only_the_orphan_owner_is_purged(self, a2a_committed_world, a2a_runtime_factory):
        world = a2a_committed_world
        rt = a2a_runtime_factory()
        with _ActiveGlobalRuntime(rt):
            _, _, real_prefix, orphan_prefix = await self._seed(rt, world)
            assert await maintenance_worker.run_sweep_once() is True
            assert await _counts(orphan_prefix) == (0, 0, 0)
            assert await _counts(real_prefix) == (1, 1, 1)

    async def test_orphans_are_purged_when_every_observed_agent_was_deleted(
        self, a2a_committed_world, a2a_runtime_factory, monkeypatch,
    ):
        # None of the observed agents exist, but the Agent table is not empty: a real deletion,
        # not a broken lookup, so the guard must not trip.
        world = a2a_committed_world
        rt = a2a_runtime_factory()
        monkeypatch.setattr(maintenance_worker, "_existing_agent_ids_sync", lambda candidate_ids: set())
        with _ActiveGlobalRuntime(rt):
            _, _, real_prefix, orphan_prefix = await self._seed(rt, world)
            assert await maintenance_worker.run_sweep_once() is True
            assert await _counts(orphan_prefix) == (0, 0, 0)
            assert await _counts(real_prefix) == (0, 0, 0)

    async def test_empty_existing_lookup_purges_nothing(
        self, a2a_committed_world, a2a_runtime_factory, monkeypatch, caplog,
    ):
        world = a2a_committed_world
        rt = a2a_runtime_factory()
        monkeypatch.setattr(maintenance_worker, "_existing_agent_ids_sync", lambda candidate_ids: set())
        monkeypatch.setattr(maintenance_worker, "_any_agent_exists_sync", lambda: False)
        caplog.set_level(logging.WARNING)
        maintenance_worker.logger.addHandler(caplog.handler)
        try:
            with _ActiveGlobalRuntime(rt):
                _, _, real_prefix, orphan_prefix = await self._seed(rt, world)
                assert await maintenance_worker.run_sweep_once() is True
        finally:
            maintenance_worker.logger.removeHandler(caplog.handler)
        assert await _counts(orphan_prefix) == (1, 1, 1)
        assert await _counts(real_prefix) == (1, 1, 1)
        assert any("orphan_guard_tripped" in r.getMessage() for r in caplog.records)


class TestConversationAndCheckpointerNeverPurged:
    """AC-47: the retention sweep removes the `a2a_context_link` row but never the Conversation (RD-3)."""

    async def test_retention_sweep_deletes_the_link_row_but_keeps_the_conversation(self, a2a_committed_world):
        world = a2a_committed_world
        db = SessionLocal()
        try:
            conversation = Conversation(
                agent_id=world.agent_public_id,
                user_id=world.user_id,
                source=ConversationSource.A2A,
                session_id=f"ac47-session-{uuid.uuid4().hex}",
            )
            db.add(conversation)
            db.flush()
            link = A2AContextLink(
                app_id=world.app_id,
                agent_id=world.agent_public_id,
                conversation_id=conversation.conversation_id,
                api_key_hash=hash_api_key(world.key_1_raw),
                context_id="ac47-ctx",
                created_at=datetime.utcnow() - timedelta(days=60),
                updated_at=datetime.utcnow() - timedelta(days=60),
            )
            db.add(link)
            db.commit()
            conversation_id = conversation.conversation_id
            link_id = link.id
        finally:
            db.close()

        await maintenance_worker.run_sweep_once()

        db = SessionLocal()
        try:
            assert db.query(A2AContextLink).filter(A2AContextLink.id == link_id).first() is None
            kept = db.query(Conversation).filter(Conversation.conversation_id == conversation_id).first()
            assert kept is not None, "AC-47/RD-3: the retention sweep must never touch Conversation"
        finally:
            db.query(Conversation).filter(Conversation.conversation_id == conversation_id).delete()
            db.commit()
            db.close()


class TestPurgeFailureIsLoggedAtWarning:
    """A purge failure is logged at WARNING with both ids, and deletion still succeeds."""

    async def test_purge_prefix_failure_is_logged_and_deletion_still_succeeds(
        self, a2a_committed_world, a2a_runtime_factory, fast_grace, monkeypatch, caplog,
    ):
        world = a2a_committed_world
        rt = a2a_runtime_factory()

        async def _boom(*args, **kwargs):
            raise RuntimeError("simulated purge failure")

        monkeypatch.setattr(A2ATaskRepository, "purge_prefix", staticmethod(_boom))
        # `maintenance_worker.logger` has propagate=False (utils/logger.py); attach caplog's handler.
        caplog.set_level(logging.WARNING)
        maintenance_worker.logger.addHandler(caplog.handler)
        try:
            with _ActiveGlobalRuntime(rt):
                async with _RunningMaintenanceWorker():
                    db = SessionLocal()
                    try:
                        from services.agent_service import AgentService

                        deleted = AgentService().delete_agent(db, world.agent_frozen_id)
                    finally:
                        db.close()
                    await maintenance_worker.wait_idle()
        finally:
            maintenance_worker.logger.removeHandler(caplog.handler)

        assert deleted is True
        warnings = [r for r in caplog.records if r.levelname == "WARNING" and "purge_failed" in r.getMessage()]
        assert len(warnings) == 1
        message = warnings[0].getMessage()
        assert f"app_id={world.app_id}" in message
        assert f"agent_id={world.agent_frozen_id}" in message
