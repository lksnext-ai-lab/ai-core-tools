"""Background workers must end as *cancelled* when cancelled (Sonar python:S7497).

Swallowing CancelledError made the tasks finish as if they had completed normally.
"""

import asyncio
from unittest.mock import patch

import pytest


async def _cancel_soon(coro):
    task = asyncio.create_task(coro)
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    return task


@pytest.mark.asyncio
async def test_sharepoint_worker_propagates_cancellation():
    from services.sharepoint import worker

    task = await _cancel_soon(worker._worker_loop())  # blocks on the empty queue
    assert task.cancelled()


@pytest.mark.asyncio
async def test_crawl_scheduler_propagates_cancellation():
    from services.crawl import worker

    async def never_returns(db):
        await asyncio.Event().wait()

    with patch("db.database.SessionLocal"), patch(
        "services.crawl_scheduler_service.CrawlSchedulerService.run_once", new=never_returns
    ):
        task = await _cancel_soon(worker._scheduler_loop())
    assert task.cancelled()


@pytest.mark.asyncio
async def test_file_cleanup_stop_absorbs_the_cancelled_worker():
    from services.file_cleanup_worker import stop_file_cleanup_worker

    child = asyncio.create_task(asyncio.Event().wait())
    await asyncio.sleep(0)
    with patch("services.file_cleanup_worker._release_leader_lock"):
        await stop_file_cleanup_worker(child)  # must not raise
    assert child.cancelled()


@pytest.mark.asyncio
async def test_file_cleanup_stop_propagates_its_own_cancellation():
    from services.file_cleanup_worker import stop_file_cleanup_worker

    async def stubborn():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await asyncio.sleep(10)  # slow cleanup: the stop call is still awaiting it

    child = asyncio.create_task(stubborn())
    await asyncio.sleep(0)
    with patch("services.file_cleanup_worker._release_leader_lock"):
        stopper = await _cancel_soon(stop_file_cleanup_worker(child))
    assert stopper.cancelled()
    child.cancel()
