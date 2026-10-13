"""The global (all backend processes) concurrency slots of a System One service, on real Postgres advisory locks.

Each holder below uses its own connection, as separate backend processes would: an asyncio semaphore could not
limit them, only the database lock can.
"""
import asyncio

import pytest

from tests.conftest import TEST_DATABASE_URL
from tools.system_one_limiter import global_slot

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
DSN = TEST_DATABASE_URL


async def _hold(service_id, cap, counter, seconds=0.15, dsn=DSN):
    async with global_slot(service_id, cap, dsn=dsn):
        counter["now"] += 1
        counter["peak"] = max(counter["peak"], counter["now"])
        await asyncio.sleep(seconds)
        counter["now"] -= 1


async def test_no_more_holders_than_the_cap_at_the_same_time():
    counter = {"now": 0, "peak": 0}
    await asyncio.gather(*[_hold(9101, 2, counter) for _ in range(6)])
    assert counter["peak"] == 2


async def test_a_cap_of_one_serializes_everything():
    counter = {"now": 0, "peak": 0}
    await asyncio.gather(*[_hold(9102, 1, counter, 0.05) for _ in range(4)])
    assert counter["peak"] == 1


async def test_services_do_not_share_slots():
    counter = {"now": 0, "peak": 0}
    await asyncio.gather(_hold(9103, 1, counter), _hold(9104, 1, counter))
    assert counter["peak"] == 2


async def test_a_slot_is_freed_when_the_holder_fails():
    with pytest.raises(RuntimeError):
        async with global_slot(9105, 1, dsn=DSN):
            raise RuntimeError("boom")
    async with asyncio.timeout(2):           # would hang if the slot had leaked
        async with global_slot(9105, 1, dsn=DSN):
            pass


async def test_a_slot_is_freed_when_the_holder_is_cancelled():
    async def holder():
        async with global_slot(9106, 1, dsn=DSN):
            await asyncio.sleep(30)

    task = asyncio.create_task(holder())
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with asyncio.timeout(2):
        async with global_slot(9106, 1, dsn=DSN):
            pass


async def test_when_the_database_is_unreachable_the_call_goes_ahead_without_the_global_limit():
    # System One must not depend on the lock: a broken limiter is worse than no limiter.
    counter = {"now": 0, "peak": 0}
    bad = "postgresql://nobody:nothing@127.0.0.1:1/none"
    await asyncio.gather(*[_hold(9107, 1, counter, 0.05, dsn=bad) for _ in range(3)])
    assert counter["peak"] == 3


async def test_a_service_that_is_not_saved_yet_is_not_limited():
    counter = {"now": 0, "peak": 0}
    await asyncio.gather(*[_hold(-1, 1, counter, 0.05) for _ in range(3)])
    assert counter["peak"] == 3
