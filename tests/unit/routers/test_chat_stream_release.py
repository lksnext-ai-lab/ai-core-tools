"""The stream response releases the turn's claim even when its generator never starts (item: busy marker leak)."""
import pytest

from routers.internal.internal_chat import _ClaimReleasingStreamingResponse


def _response(finish, started):
    async def generator():
        started.append(True)  # only runs if the body is iterated
        yield "data: x\n\n"
        yield "data: y\n\n"

    return _ClaimReleasingStreamingResponse(generator(), media_type="text/event-stream", on_finish=finish)


SCOPE = {"type": "http", "asgi": {"spec_version": "2.3"}, "method": "POST", "headers": []}


async def _receive():
    return {"type": "http.disconnect"}  # the client is gone


async def test_a_failure_on_response_start_still_releases_though_the_generator_never_started():
    finished, started = [], []

    async def finish():
        finished.append(True)

    async def send(message):
        raise ConnectionResetError("client gone before the first chunk")

    response = _response(finish, started)
    with pytest.raises(ConnectionResetError):
        await response(SCOPE, _receive, send)
    assert finished == [True]
    assert started == []  # proof of the scenario: the generator body (and its ``finally``) never ran


async def test_a_normal_response_releases_once_it_has_been_sent():
    finished, sent = [], []

    async def finish():
        finished.append(True)

    async def send(message):
        sent.append(message["type"])

    async def receive():
        import asyncio

        await asyncio.sleep(10)  # the client stays connected

    await _response(finish, []) (SCOPE, receive, send)
    assert sent[0] == "http.response.start" and finished == [True]


async def test_a_cancelled_response_releases_too():
    import asyncio

    finished = []

    async def finish():
        finished.append(True)

    async def send(message):
        await asyncio.sleep(10)

    async def receive():
        await asyncio.sleep(10)

    task = asyncio.create_task(_response(finish, [])(SCOPE, receive, send))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished == [True]
