import asyncio

import pytest

from tools.stream_guard import SSE_HEARTBEAT, guarded_stream


async def _collect(stream):
    return [chunk async for chunk in stream]


@pytest.mark.asyncio
async def test_forwards_chunks_in_order():
    async def source():
        yield "a"
        yield "b"

    assert await _collect(guarded_stream(source(), timeout_seconds=5, on_timeout=lambda: "timeout")) == ["a", "b"]


@pytest.mark.asyncio
async def test_sends_heartbeats_while_the_source_is_silent():
    async def source():
        await asyncio.sleep(0.35)
        yield "done"

    chunks = await _collect(
        guarded_stream(source(), timeout_seconds=5, on_timeout=lambda: "timeout", heartbeat_seconds=0.1)
    )

    assert chunks[-1] == "done"
    assert chunks.count(SSE_HEARTBEAT) >= 2


@pytest.mark.asyncio
async def test_stops_the_source_when_the_turn_takes_too_long():
    cancelled = asyncio.Event()

    async def source():
        try:
            yield "first"
            await asyncio.sleep(10)
            yield "never"
        except asyncio.CancelledError:
            cancelled.set()
            raise

    chunks = await _collect(
        guarded_stream(source(), timeout_seconds=0.2, on_timeout=lambda: "timeout", heartbeat_seconds=0.05)
    )

    assert chunks[0] == "first"
    assert chunks[-1] == "timeout"
    assert "never" not in chunks
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_closing_the_consumer_cancels_the_source():
    cancelled = asyncio.Event()

    async def source():
        try:
            yield "first"
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    stream = guarded_stream(source(), timeout_seconds=5, on_timeout=lambda: "timeout")
    assert await stream.__anext__() == "first"
    await stream.aclose()

    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_source_errors_reach_the_consumer():
    async def source():
        yield "a"
        raise ValueError("boom")

    stream = guarded_stream(source(), timeout_seconds=5, on_timeout=lambda: "timeout")
    with pytest.raises(ValueError, match="boom"):
        await _collect(stream)
