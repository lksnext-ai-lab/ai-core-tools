"""Keep agent SSE streams alive and bounded.

The agent generator runs in a single producer task (LangGraph keeps context variables
across steps, so its steps must not be spread over different tasks) and feeds a queue.
The consumer forwards events, sends an SSE comment while the agent is silent so proxies
do not drop the connection, and cancels the producer when the turn exceeds its time
budget. Cancelling the consumer (client gone) cancels the producer too.
"""
import asyncio
from contextlib import suppress
from typing import AsyncIterator, Callable

from tools.streaming_utils import format_sse_event
from utils.config import Config

SSE_HEARTBEAT = ": ping\n\n"
HEARTBEAT_SECONDS = 15.0
# Upper bound for one agent turn (model + tools): a hung provider or tool cannot block forever.
AGENT_RUN_TIMEOUT_SECONDS: int = Config.get_int_env_var("AICT_AGENT_RUN_TIMEOUT_SECONDS", default=600)
RUN_TIMEOUT_MESSAGE = "The agent took too long to answer and was stopped. Please try again."

_END = object()


async def _pump(source: AsyncIterator[str], queue: asyncio.Queue) -> None:
    """Move every chunk of ``source`` (or the exception it raised) into ``queue``, then ``_END``."""
    try:
        async for chunk in source:
            queue.put_nowait(chunk)
    except Exception as exc:
        queue.put_nowait(exc)
    finally:
        queue.put_nowait(_END)


async def _stop(producer: asyncio.Task) -> None:
    if not producer.done():
        producer.cancel()
        with suppress(asyncio.CancelledError):
            await producer


async def guarded_stream(
    source: AsyncIterator[str],
    *,
    timeout_seconds: float,
    on_timeout: Callable[[], str],
    heartbeat_seconds: float = HEARTBEAT_SECONDS,
) -> AsyncIterator[str]:
    """Yield ``source``'s chunks with heartbeats; on timeout stop it and yield ``on_timeout()``."""
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    producer = asyncio.create_task(_pump(source, queue))
    try:
        while (remaining := deadline - loop.time()) > 0:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=min(heartbeat_seconds, remaining))
            except asyncio.TimeoutError:
                if deadline - loop.time() > 0:
                    yield SSE_HEARTBEAT
                continue
            if item is _END:
                return
            if isinstance(item, Exception):
                raise item
            yield item
        await _stop(producer)
        yield on_timeout()
    finally:
        await _stop(producer)


def guard_agent_stream(source: AsyncIterator[str]) -> AsyncIterator[str]:
    """``guarded_stream`` with the agent turn budget and a ``run_timeout`` error event."""
    return guarded_stream(
        source,
        timeout_seconds=AGENT_RUN_TIMEOUT_SECONDS,
        on_timeout=lambda: format_sse_event("error", {"code": "run_timeout", "message": RUN_TIMEOUT_MESSAGE}),
    )
