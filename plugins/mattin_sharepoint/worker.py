"""SharePoint sync worker — queue-based async worker mirroring crawl/worker.py."""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class ConflictError(Exception):
    """Raised when a source sync is already enqueued."""
    pass


# Module-level queue — rebuilt on each process startup
_sync_queue: asyncio.Queue[int] = asyncio.Queue()


async def enqueue_sync(source_id: int) -> None:
    """Add a source_id to the sync queue.

    Raises ConflictError if source_id is already pending in the queue.
    """
    # Check if already queued (asyncio.Queue._queue is a deque internally)
    if source_id in list(_sync_queue._queue):  # type: ignore[attr-defined]
        raise ConflictError(f"Source {source_id} is already queued for sync")
    await _sync_queue.put(source_id)


async def _worker_loop() -> None:
    while True:
        source_id: int | None = None
        try:
            source_id = await _sync_queue.get()
            logger.info(f"SharePoint worker: starting sync for source {source_id}")
            from mattin_sharepoint.service import SharePointSyncService
            await SharePointSyncService.run_sync(source_id)
        except asyncio.CancelledError:
            logger.info("SharePoint worker shutting down")
            break
        except Exception as exc:
            logger.error(
                f"SharePoint worker error for source {source_id}: {exc}", exc_info=True
            )
        finally:
            try:
                _sync_queue.task_done()
            except ValueError:
                pass  # task_done called more times than put — safe to ignore


async def start_sharepoint_worker() -> list[asyncio.Task]:
    """Start the background worker and return its task handles."""
    tasks = [asyncio.create_task(_worker_loop(), name="sharepoint-worker")]
    return tasks


async def stop_sharepoint_worker(tasks: list[asyncio.Task]) -> None:
    """Cancel worker tasks and wait for them to finish cleanly."""
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
