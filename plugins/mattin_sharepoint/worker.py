"""SharePoint sync worker — queue-based async worker mirroring crawl/worker.py."""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class ConflictError(Exception):
    """Raised when a source sync is already enqueued."""
    pass


# Module-level queue holder — lazily initialised inside an event loop to avoid
# "Queue bound to a different event loop" errors when the module is imported
# before an event loop is running (e.g. during test collection).
_sync_queue: asyncio.Queue[int] | None = None


def _get_queue() -> asyncio.Queue[int]:
    """Return the module-level sync queue, creating it lazily if needed.

    If the cached queue was created in a different event loop (e.g. between
    test runs), reset it so a fresh queue is created for the current loop.
    """
    global _sync_queue
    if _sync_queue is not None:
        try:
            running_loop = asyncio.get_running_loop()
            # asyncio.Queue stores its loop reference; if it differs we must recreate.
            queue_loop = getattr(_sync_queue, "_loop", None)
            if queue_loop is not None and queue_loop is not running_loop:
                _sync_queue = None
        except RuntimeError:
            # No event loop running — reset so next call after a loop starts creates fresh
            _sync_queue = None
    if _sync_queue is None:
        _sync_queue = asyncio.Queue()
    return _sync_queue


async def enqueue_sync(source_id: int) -> None:
    """Add a source_id to the sync queue.

    Raises ConflictError if source_id is already pending in the queue.
    """
    queue = _get_queue()
    # Check if already queued (asyncio.Queue._queue is a deque internally)
    if source_id in list(queue._queue):  # type: ignore[attr-defined]
        raise ConflictError(f"Source {source_id} is already queued for sync")
    await queue.put(source_id)


async def _worker_loop() -> None:
    while True:
        source_id: int | None = None
        try:
            source_id = await _get_queue().get()
            logger.info(f"SharePoint worker: starting sync for source {source_id}")
            from mattin_sharepoint.service import SharePointSyncService
            await SharePointSyncService.run_sync(source_id)
        except asyncio.CancelledError:
            logger.info("SharePoint worker shutting down")
            break
        except RuntimeError as exc:
            # Break out if the queue is bound to a different event loop —
            # this happens when the worker task outlives a TestClient event loop.
            if "bound to a different event loop" in str(exc):
                logger.info("SharePoint worker: event loop mismatch, shutting down")
                break
            logger.error(
                f"SharePoint worker error for source {source_id}: {exc}", exc_info=True
            )
        except Exception as exc:
            logger.error(
                f"SharePoint worker error for source {source_id}: {exc}", exc_info=True
            )
        finally:
            try:
                _get_queue().task_done()
            except (ValueError, RuntimeError):
                pass  # task_done called more times than put, or loop mismatch — safe to ignore


async def start_sharepoint_worker() -> list[asyncio.Task]:
    """Start the background worker and return its task handles."""
    tasks = [asyncio.create_task(_worker_loop(), name="sharepoint-worker")]
    return tasks


async def stop_sharepoint_worker(tasks: list[asyncio.Task]) -> None:
    """Cancel worker tasks and wait for them to finish cleanly.

    Tasks that were created in a different event loop (e.g. during tests) are
    silently skipped — they are either already dead or will be GC'd.
    """
    current_loop = asyncio.get_running_loop()
    same_loop_tasks = []
    for task in tasks:
        try:
            task_loop = task.get_loop()
            if task_loop is current_loop:
                task.cancel()
                same_loop_tasks.append(task)
        except Exception:
            pass  # task is done or unreachable
    if same_loop_tasks:
        await asyncio.gather(*same_loop_tasks, return_exceptions=True)
