"""AD-10: the async maintenance worker for A2A cancel+purge, retention, stale-task sweep and orphans.

Started unconditionally from `main.py`'s lifespan (even with `A2A_ENABLED=false`, so retention keeps
running). Two duties run concurrently in one worker task:

1. **Purge queue** (`enqueue_purge` -> `_drain_queue`). The deletion hooks call
   `lifecycle_service.schedule_owner_purge` after their commit, which hands an item to this worker's
   queue via `loop.call_soon_threadsafe`. Each item runs in its own task: cancel the prefix's
   non-terminal tasks, wait `A2A_PURGE_GRACE_SECONDS`, purge the prefix. DB phases are bounded by a
   module-level semaphore (`_PURGE_CONCURRENCY`) so purges never crowd out live A2A traffic, and an
   app-wide item coalesces (drops) the per-agent items of the same app. Not leader-gated: the queue is
   local to the worker that received the delete.
2. **Leader-locked periodic sweep** (`run_sweep_once`): fail stale tasks, purge terminal events,
   purge expired tasks and context links, purge orphaned owners. Each phase has its own time budget.

**Leader election.** `services/file_cleanup_worker.py` uses a host-local `filelock.FileLock`, which is
enough for host-local files but not for tables shared by every replica. This sweep therefore holds a
Postgres **session-level** advisory lock (`pg_try_advisory_lock`) on one dedicated connection in
AUTOCOMMIT mode for the duration of one sweep. The session form is used instead of the
transaction-scoped helper in `db/advisory_lock.py` so that the lock connection is never left idle in
a transaction for the length of a sweep. The unlock runs shielded; if it fails or returns false,
the connection is invalidated so a lock-holding connection never returns to the pool.

RD-3/AC-47: this module never touches `Conversation` or checkpointer rows.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Dict, List, Optional, Set, Tuple

from a2a.types.a2a_pb2 import CancelTaskRequest
from a2a.utils.errors import TaskNotCancelableError, TaskNotFoundError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection

from db.advisory_lock import derive_lock_key
from db.database import SessionLocal, async_engine
from repositories.a2a_context_link_repository import A2AContextLinkRepository
from repositories.a2a_task_repository import A2ATaskRepository
from repositories.agent_repository import AgentRepository
from services.a2a_server import identity
from services.a2a_server.runtime import get_runtime
from services.a2a_server.task_states import fail_task_cas
from utils.a2a_config import get_a2a_config
from utils.clock import utcnow_naive
from utils.logger import get_logger

logger = get_logger(__name__)

#: Advisory-lock name for the sweep leader; distinct from every other advisory-lock caller.
LEADER_LOCK_KEY_NAME = "mattin:a2a_maintenance_sweep"
#: The signed 64-bit key passed to `pg_try_advisory_lock` (public for tests).
LEADER_LOCK_KEY = derive_lock_key(LEADER_LOCK_KEY_NAME)

_TIMEOUT_MESSAGE_TEXT = "Task timed out"

# Per-phase budget: one slow phase can never starve the phases after it.
_PHASE_BUDGET_SECONDS = 120.0
_CANCEL_TIMEOUT_SECONDS = 10.0
_STOP_WAIT_SECONDS = 2.0
_INITIAL_SWEEP_DELAY_RANGE_SECONDS = (30.0, 90.0)
_PURGE_CONCURRENCY = 2
_STALE_SWEEP_BATCH = 500
_LINK_PURGE_BATCH = 1000
_LINK_PURGE_MAX_BATCHES = 1000
_ORPHAN_PAGE_SIZE = 1000
_ORPHAN_MAX_PAGES = 100
_EXISTING_IDS_CHUNK = 1000

#: Bounds concurrent purge-item DB phases per worker. Created in `start_a2a_maintenance_worker`
#: (bound to the running loop); `_get_purge_semaphore` creates it lazily otherwise.
_purge_semaphore: Optional[asyncio.Semaphore] = None


@dataclass(frozen=True)
class _PurgeItem:
    app_id: int
    agent_id: Optional[int]


@dataclass
class _MaintenanceState:
    """The running worker's loop, queue and purge bookkeeping.

    `queue.task_done()` is called when an item's task finishes (or when it is coalesced away), so
    `wait_idle()` (`queue.join()`) returns only after every enqueued item is fully processed.
    """

    loop: asyncio.AbstractEventLoop
    queue: "asyncio.Queue[_PurgeItem]" = field(default_factory=asyncio.Queue)
    pending_purge_tasks: Set[asyncio.Task] = field(default_factory=set)
    #: app_id -> number of app-wide items pending/in flight (they cover that app's agent items).
    app_items: Dict[int, int] = field(default_factory=dict)


_state: Optional[_MaintenanceState] = None


def _get_purge_semaphore() -> asyncio.Semaphore:
    global _purge_semaphore
    if _purge_semaphore is None:
        _purge_semaphore = asyncio.Semaphore(_PURGE_CONCURRENCY)
    return _purge_semaphore


# ---------------------------------------------------------------------------
# Purge queue (AD-10 duty 1)
# ---------------------------------------------------------------------------


def enqueue_purge(app_id: int, agent_id: Optional[int] = None) -> None:
    """Enqueues a purge item from any thread. No-op (debug log) if no worker is running.

    The periodic orphan sweep is the backstop for anything dropped here.
    """
    state = _state
    if state is None:
        logger.debug(
            "a2a.maintenance.no_worker_running app_id=%s agent_id=%s; relying on the orphan sweep",
            app_id, agent_id,
        )
        return
    item = _PurgeItem(app_id=app_id, agent_id=agent_id)
    try:
        state.loop.call_soon_threadsafe(state.queue.put_nowait, item)
    except Exception:
        logger.warning("a2a.maintenance.enqueue_failed app_id=%s agent_id=%s", app_id, agent_id, exc_info=True)


def _covered_by_app_item(state: _MaintenanceState, item: _PurgeItem) -> bool:
    """True for an agent item whose app has an app-wide item pending or in flight."""
    return item.agent_id is not None and state.app_items.get(item.app_id, 0) > 0


async def _cancel_nonterminal_tasks(prefix: str) -> None:
    # Only the listing holds a purge permit: local cancels wait for bridge teardown and must not
    # starve other purge items or the orphan phase.
    try:
        async with _get_purge_semaphore():
            nonterminal = await A2ATaskRepository.list_nonterminal_by_prefix(prefix)
    except Exception:
        logger.warning("a2a.maintenance.list_nonterminal_failed prefix=%s", prefix, exc_info=True)
        return

    rt = get_runtime()
    if rt is None:
        return
    for task_id, owner in nonterminal:
        try:
            await asyncio.wait_for(
                rt.handler.on_cancel_task(CancelTaskRequest(id=task_id), identity.context_for_owner(owner)),
                timeout=_CANCEL_TIMEOUT_SECONDS,
            )
        except (TaskNotFoundError, TaskNotCancelableError):
            continue
        except asyncio.TimeoutError:
            logger.warning("a2a.maintenance.cancel_timed_out task_id=%s prefix=%s", task_id, prefix)
        except Exception:
            logger.warning("a2a.maintenance.cancel_failed task_id=%s prefix=%s", task_id, prefix, exc_info=True)


async def _process_purge_item(state: _MaintenanceState, item: _PurgeItem) -> None:
    """Cancels the prefix's non-terminal tasks, waits out the grace period, then purges the prefix.

    A cancellation during the grace sleep (worker shutdown) propagates: nothing is purged and the
    orphan sweep picks the prefix up later.
    """
    prefix = identity.owner_prefix(item.app_id, item.agent_id)
    semaphore = _get_purge_semaphore()

    if _covered_by_app_item(state, item):
        return
    await _cancel_nonterminal_tasks(prefix)

    # AD-10: SDK 1.2.2 recreates a deleted task if a remote producer saves after the purge, so wait
    # for in-flight producers (keepalive + coalesce, enforced by the config clamp) to observe the cancel.
    await asyncio.sleep(get_a2a_config().purge_grace_seconds)

    if _covered_by_app_item(state, item):
        return
    async with semaphore:
        try:
            purged = await A2ATaskRepository.purge_prefix(prefix)
        except Exception:
            logger.warning(
                "a2a.maintenance.purge_failed app_id=%s agent_id=%s prefix=%s",
                item.app_id, item.agent_id, prefix, exc_info=True,
            )
            return
    if purged:
        logger.info(
            "a2a.maintenance.purged app_id=%s agent_id=%s purged=%s", item.app_id, item.agent_id, purged
        )


def _spawn_purge(state: _MaintenanceState, item: _PurgeItem) -> None:
    if item.agent_id is None:
        state.app_items[item.app_id] = state.app_items.get(item.app_id, 0) + 1
    task = asyncio.ensure_future(_process_purge_item(state, item))
    state.pending_purge_tasks.add(task)

    def _on_done(finished: asyncio.Task) -> None:
        state.pending_purge_tasks.discard(finished)
        if item.agent_id is None:
            remaining = state.app_items.get(item.app_id, 0) - 1
            if remaining > 0:
                state.app_items[item.app_id] = remaining
            else:
                state.app_items.pop(item.app_id, None)
        state.queue.task_done()
        if finished.cancelled():
            logger.info("a2a.maintenance.purge_cancelled app_id=%s agent_id=%s", item.app_id, item.agent_id)
            return
        exc = finished.exception()
        if exc is not None:
            logger.error(
                "a2a.maintenance.purge_item_crashed app_id=%s agent_id=%s",
                item.app_id, item.agent_id, exc_info=exc,
            )

    task.add_done_callback(_on_done)


async def _drain_queue(state: _MaintenanceState) -> None:
    """Forever: take everything currently queued, coalesce it, spawn one task per surviving item."""
    while True:
        items: List[_PurgeItem] = [await state.queue.get()]
        while True:
            try:
                items.append(state.queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        batch_apps = {item.app_id for item in items if item.agent_id is None}
        seen: Set[_PurgeItem] = set()
        for item in items:
            redundant = item in seen or (
                item.agent_id is not None
                and (item.app_id in batch_apps or _covered_by_app_item(state, item))
            )
            seen.add(item)
            if redundant:
                logger.debug(
                    "a2a.maintenance.purge_coalesced app_id=%s agent_id=%s", item.app_id, item.agent_id
                )
                state.queue.task_done()
                continue
            _spawn_purge(state, item)


# ---------------------------------------------------------------------------
# Periodic leader-locked sweep (AD-10 duty 2)
# ---------------------------------------------------------------------------


async def _try_acquire_leader_lock(conn: AsyncConnection) -> Optional[bool]:
    """Non-blocking session-level `pg_try_advisory_lock` on `conn`.

    Returns:
        True if acquired, False if another session holds it, None if the attempt itself failed.
    """
    try:
        result = await conn.execute(select(func.pg_try_advisory_lock(LEADER_LOCK_KEY)))
        return bool(result.scalar())
    except Exception:
        logger.warning("a2a.maintenance.leader_lock_acquire_failed", exc_info=True)
        return None


async def _release_and_close(conn: AsyncConnection, *, lock_held: bool, discard: bool) -> None:
    """Unlocks (if held) and closes `conn`; invalidates it if the unlock did not verifiably succeed."""
    try:
        if lock_held:
            released = False
            try:
                result = await conn.execute(select(func.pg_advisory_unlock(LEADER_LOCK_KEY)))
                released = bool(result.scalar())
            except Exception:
                logger.warning("a2a.maintenance.leader_lock_release_failed", exc_info=True)
            if not released:
                logger.warning("a2a.maintenance.leader_lock_not_released; invalidating the connection")
                discard = True
        if discard:
            await conn.invalidate()
    except Exception:
        logger.warning("a2a.maintenance.leader_connection_invalidate_failed", exc_info=True)
    finally:
        try:
            await conn.close()
        except Exception:
            logger.warning("a2a.maintenance.leader_connection_close_failed", exc_info=True)


async def _run_phase(name: str, phase: Callable[[], Awaitable[None]]) -> None:
    """Runs one sweep phase under its own budget; logs (never raises) failures and timeouts."""
    try:
        await asyncio.wait_for(phase(), timeout=_PHASE_BUDGET_SECONDS)
    except asyncio.TimeoutError:
        logger.warning("a2a.maintenance.phase_timed_out phase=%s budget_s=%s", name, _PHASE_BUDGET_SECONDS)
    except Exception:
        logger.warning("a2a.maintenance.phase_failed phase=%s", name, exc_info=True)


async def _sweep_stale_tasks() -> None:
    """(a) CAS-fails non-terminal tasks whose stored status timestamp is older than the task timeout."""
    rt = get_runtime()
    if rt is None:
        logger.warning("a2a.maintenance.sweep_stale_no_runtime")
        return
    cutoff = utcnow_naive() - timedelta(seconds=get_a2a_config().task_timeout_seconds)
    stale = await A2ATaskRepository.list_stale_nonterminal(cutoff, limit=_STALE_SWEEP_BATCH)
    for task_id, owner in stale:
        try:
            if await fail_task_cas(rt.store, task_id, owner, _TIMEOUT_MESSAGE_TEXT, stale_before=cutoff):
                logger.info("a2a.maintenance.stale_task_failed task_id=%s", task_id)
        except Exception:
            logger.warning("a2a.maintenance.stale_task_error task_id=%s", task_id, exc_info=True)


async def _sweep_terminal_events() -> None:
    """(b1) RB-6: purges events of terminal tasks after `A2A_EVENT_RETENTION_MINUTES`."""
    cutoff = utcnow_naive() - timedelta(minutes=get_a2a_config().event_retention_minutes)
    purged = await A2ATaskRepository.purge_terminal_events_older_than(cutoff)
    if purged:
        logger.info("a2a.maintenance.terminal_events_purged count=%s", purged)


async def _sweep_expired_tasks() -> None:
    """(b2) Purges tasks (with events/versions) older than `A2A_TASK_RETENTION_DAYS`."""
    cutoff = utcnow_naive() - timedelta(days=get_a2a_config().task_retention_days)
    purged = await A2ATaskRepository.purge_older_than(cutoff)
    if purged:
        logger.info("a2a.maintenance.tasks_purged count=%s", purged)


def _delete_old_links_sync(cutoff: datetime) -> int:
    """Batched link-retention delete (one commit per batch), run via `asyncio.to_thread`."""
    db = SessionLocal()
    total = 0
    try:
        for _ in range(_LINK_PURGE_MAX_BATCHES):
            candidates, deleted = A2AContextLinkRepository.delete_older_than_batch(db, cutoff, _LINK_PURGE_BATCH)
            db.commit()
            total += deleted
            if candidates == 0:
                break
        else:
            logger.warning("a2a.maintenance.links_purge_batch_cap_reached batches=%s", _LINK_PURGE_MAX_BATCHES)
        return total
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def _sweep_expired_links() -> None:
    """(b3) Purges `a2a_context_link` rows not used for `A2A_TASK_RETENTION_DAYS`."""
    cutoff = utcnow_naive() - timedelta(days=get_a2a_config().task_retention_days)
    purged = await asyncio.to_thread(_delete_old_links_sync, cutoff)
    if purged:
        logger.info("a2a.maintenance.links_purged count=%s", purged)


def _existing_agent_ids_sync(candidate_ids: List[int]) -> Set[int]:
    db = SessionLocal()
    try:
        existing: Set[int] = set()
        for start in range(0, len(candidate_ids), _EXISTING_IDS_CHUNK):
            existing |= AgentRepository.existing_ids(db, candidate_ids[start:start + _EXISTING_IDS_CHUNK])
        return existing
    finally:
        db.close()


def _any_agent_exists_sync() -> bool:
    db = SessionLocal()
    try:
        return AgentRepository.any_exists(db)
    finally:
        db.close()


async def _sweep_orphans() -> None:
    """(c) Purges owner prefixes whose `agent_id` no longer exists in `Agent`.

    Guard: if the `Agent` table looks empty while task owners exist, the lookup is suspect (wrong
    DB, missing schema); log a WARNING and purge nothing. When every observed agent was really
    deleted but other agents exist, the orphans are purged normally.
    """
    pairs: List[Tuple[int, int]] = []
    after: Optional[Tuple[int, int]] = None
    for _ in range(_ORPHAN_MAX_PAGES):
        page = await A2ATaskRepository.list_owner_agent_ids(after=after, limit=_ORPHAN_PAGE_SIZE)
        pairs.extend(page)
        if len(page) < _ORPHAN_PAGE_SIZE:
            break
        after = page[-1]
    if not pairs:
        return

    candidate_ids = sorted({agent_id for _, agent_id in pairs})
    existing = await asyncio.to_thread(_existing_agent_ids_sync, candidate_ids)
    if not existing and not await asyncio.to_thread(_any_agent_exists_sync):
        logger.warning(
            "a2a.maintenance.orphan_guard_tripped observed_agents=%s existing=0; purging nothing",
            len(candidate_ids),
        )
        return

    semaphore = _get_purge_semaphore()
    for app_id, agent_id in pairs:
        if agent_id in existing:
            continue
        try:
            async with semaphore:
                purged = await A2ATaskRepository.purge_prefix(identity.owner_prefix(app_id, agent_id))
        except Exception:
            # One failing prefix must not stop the rest of the pass; the next sweep retries it.
            logger.warning(
                "a2a.maintenance.orphan_purge_failed app_id=%s agent_id=%s", app_id, agent_id, exc_info=True
            )
            continue
        logger.info("a2a.maintenance.orphan_purged app_id=%s agent_id=%s purged=%s", app_id, agent_id, purged)


_SWEEP_PHASES: Tuple[Tuple[str, Callable[[], Awaitable[None]]], ...] = (
    ("stale_tasks", _sweep_stale_tasks),
    ("terminal_events", _sweep_terminal_events),
    ("expired_tasks", _sweep_expired_tasks),
    ("expired_links", _sweep_expired_links),
    ("orphans", _sweep_orphans),
)


async def run_sweep_once() -> bool:
    """Runs one leader-gated sweep pass. Never raises (except on cancellation).

    Returns:
        True if this call held the leader lock and ran the phases, False otherwise.
    """
    try:
        conn = await async_engine.connect()
    except Exception:
        logger.warning("a2a.maintenance.leader_connection_failed", exc_info=True)
        return False
    lock_held = False
    discard = False
    try:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        acquired = await _try_acquire_leader_lock(conn)
        if acquired is None:
            discard = True
            return False
        if not acquired:
            logger.debug("a2a.maintenance.sweep_skipped_not_leader")
            return False
        lock_held = True
        for name, phase in _SWEEP_PHASES:
            await _run_phase(name, phase)
        return True
    except asyncio.CancelledError:
        raise
    except Exception:
        discard = True
        logger.warning("a2a.maintenance.sweep_unexpected_error", exc_info=True)
        return False
    finally:
        await asyncio.shield(_release_and_close(conn, lock_held=lock_held, discard=discard))


async def _periodic_sweep() -> None:
    # Jittered first run: replicas restarted together do not all contend for the lock at boot.
    await asyncio.sleep(random.uniform(*_INITIAL_SWEEP_DELAY_RANGE_SECONDS))  # noqa: S311 - not security
    while True:
        try:
            await run_sweep_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("a2a.maintenance.periodic_sweep_error", exc_info=True)
        await asyncio.sleep(get_a2a_config().sweep_interval_seconds)


# ---------------------------------------------------------------------------
# Lifecycle (started/stopped from backend/main.py's lifespan)
# ---------------------------------------------------------------------------


async def _worker_loop(state: _MaintenanceState) -> None:
    cfg = get_a2a_config()
    logger.info(
        "a2a.maintenance.worker_starting sweep_interval_s=%s purge_grace_s=%s task_retention_days=%s "
        "event_retention_minutes=%s task_timeout_s=%s",
        cfg.sweep_interval_seconds, cfg.purge_grace_seconds, cfg.task_retention_days,
        cfg.event_retention_minutes, cfg.task_timeout_seconds,
    )
    try:
        await asyncio.gather(_drain_queue(state), _periodic_sweep())
    except asyncio.CancelledError:
        logger.info("a2a.maintenance.worker_shutting_down")
        raise


def start_a2a_maintenance_worker() -> asyncio.Task:
    """Starts the AD-10 maintenance worker in the running loop (never gated by `A2A_ENABLED`)."""
    global _state, _purge_semaphore
    _purge_semaphore = asyncio.Semaphore(_PURGE_CONCURRENCY)
    state = _MaintenanceState(loop=asyncio.get_running_loop())
    _state = state
    return asyncio.create_task(_worker_loop(state), name="a2a-maintenance-worker")


async def stop_a2a_maintenance_worker(task: Optional[asyncio.Task]) -> None:
    """Cancels the worker and its in-flight purge items, waiting at most `_STOP_WAIT_SECONDS` for each.

    Purge items cancelled during their grace period do not purge; the orphan sweep is the backstop.
    """
    global _state
    state, _state = _state, None

    if task is not None:
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=_STOP_WAIT_SECONDS)
        if task not in done:
            logger.warning("a2a.maintenance.worker_stop_timed_out wait_s=%s", _STOP_WAIT_SECONDS)
        elif not task.cancelled() and task.exception() is not None:
            logger.warning("a2a.maintenance.worker_shutdown_error", exc_info=task.exception())

    if state is not None and state.pending_purge_tasks:
        pending = set(state.pending_purge_tasks)
        for pending_task in pending:
            pending_task.cancel()
        _, still_running = await asyncio.wait(pending, timeout=_STOP_WAIT_SECONDS)
        if still_running:
            logger.warning("a2a.maintenance.purge_items_stop_timed_out count=%s", len(still_running))


async def wait_idle() -> None:
    """Test helper: waits until every enqueued purge item has fully finished. No-op without a worker.

    Yields once first so `call_soon_threadsafe`-scheduled `put_nowait` callbacks already pending on
    this loop run before `queue.join()` checks for unfinished items.
    """
    state = _state
    if state is None:
        return
    await asyncio.sleep(0)
    await state.queue.join()


__all__ = [
    "LEADER_LOCK_KEY",
    "LEADER_LOCK_KEY_NAME",
    "enqueue_purge",
    "run_sweep_once",
    "start_a2a_maintenance_worker",
    "stop_a2a_maintenance_worker",
    "wait_idle",
]
