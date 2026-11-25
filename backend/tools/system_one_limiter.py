"""Concurrency slots shared by every backend process, for one System One service.

A System One server accepts a fixed number of requests at once (Nimble: 4) and answers 529 above it. A semaphore
inside each backend process cannot honor that when several processes run, so the slots live in Postgres: a call
holds one of ``cap`` advisory locks for its whole duration.

The lock is held by a **dedicated connection owned here, never one from the SQLAlchemy pool**. Session-level advisory
locks on pooled connections leak to unrelated sessions (see ``db/advisory_lock.py``); on a private connection the lock
dies with it, so a crashed or cancelled call can never leave a slot taken. Nothing but a service id and a slot number is
stored: no texts, no results.
"""
import asyncio
import random
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import psycopg

from config import DATABASE_URL
from utils.logger import get_logger

logger = get_logger(__name__)

_NAMESPACE = 0x5331                 # "S1": keeps our keys away from every other advisory lock of the application
_MAX_SLOTS = 4096                   # slot number must fit its 12 bits of the key
_POLL_S = 0.1
# How long a call may wait for a slot. Every waiting request keeps a database session, so waits must not pile up
# without bound: past this the caller is told the service is busy (the same answer as the server's own 529).
MAX_WAIT_S = 20.0


class SlotWaitTimeout(Exception):
    """No slot became free in time."""


def _key(service_id: int, slot: int) -> int:
    return (_NAMESPACE << 40) | (service_id << 12) | slot


async def _try_take_a_slot(conn: "psycopg.AsyncConnection", service_id: int, cap: int) -> bool:
    for slot in range(min(cap, _MAX_SLOTS)):
        row = await (await conn.execute("SELECT pg_try_advisory_lock(%s)", (_key(service_id, slot),))).fetchone()
        if row and row[0]:
            return True
    return False


@asynccontextmanager
async def global_slot(service_id: int, cap: int, *, dsn: Optional[str] = None,
                      max_wait_s: float = MAX_WAIT_S) -> AsyncIterator[None]:
    """Wait (at most ``max_wait_s``, else ``SlotWaitTimeout``) for one of ``cap`` slots, hold it for the block, release it on exit.

    No limit (the block just runs) for a service that is not saved yet, or when the database cannot be reached: System
    One must not depend on this limiter, and the per-process cap still applies.
    """
    dsn = dsn or DATABASE_URL
    if service_id < 0 or not dsn:
        yield
        return
    try:
        conn = await psycopg.AsyncConnection.connect(dsn, autocommit=True, connect_timeout=5)
    except Exception as exc:
        logger.warning("[system_one] global concurrency limit unavailable (%s): continuing without it", type(exc).__name__)
        yield
        return
    try:
        deadline = asyncio.get_running_loop().time() + max_wait_s
        while not await _try_take_a_slot(conn, service_id, cap):
            if asyncio.get_running_loop().time() >= deadline:
                raise SlotWaitTimeout()
            await asyncio.sleep(_POLL_S * (0.5 + random.random()))
        yield
    finally:
        # Closing the connection releases the lock. Shielded: a cancelled call must still free its slot.
        await asyncio.shield(conn.close())
