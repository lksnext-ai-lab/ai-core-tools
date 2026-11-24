"""The request's pooled DB connection is NOT held while attachment indexing runs (pool of ONE, real engines).

The shared-transaction harness of the other Chat tests cannot show this, so here the app's ``get_db`` is overridden with
sessions of a DEDICATED engine (``pool_size=1, max_overflow=0, pool_timeout=0.5``) and the indexing worker's sessions
come from a second engine. While the indexing job is gated, the request engine must have nothing checked out and a
second request through the same pool of one must succeed.
"""
import asyncio
import os
import threading

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from models.app import App
from services.playground_media_service import PlaygroundMediaService
from tests.integration.internal_chat._chat_support import selection
from tests.integration.internal_chat.test_chat_isolation_concurrency import (  # noqa: F401  (fixtures)
    cworld,
    stack,
    threads,
)


@pytest.fixture
def pools(test_engine, cworld, monkeypatch):
    from db.database import get_db
    from main import app

    uri = os.environ["SQLALCHEMY_DATABASE_URI"]
    request_engine = create_engine(uri, pool_size=1, max_overflow=0, pool_timeout=0.5)
    worker_engine = create_engine(uri, pool_size=3, max_overflow=0)
    request_sessions = sessionmaker(autocommit=False, autoflush=False, bind=request_engine)
    worker_sessions = sessionmaker(autocommit=False, autoflush=False, bind=worker_engine)

    def get_db_from_the_small_pool():
        session = request_sessions()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = get_db_from_the_small_pool
    monkeypatch.setattr("services.chat_attachment_service.SessionLocal", worker_sessions)
    monkeypatch.setattr("db.database.SessionLocal", worker_sessions)
    with Session(test_engine) as s:
        s.get(App, cworld.app_id).default_embedding_service_id = cworld.emb
        s.commit()
    yield request_engine
    app.dependency_overrides.pop(get_db, None)
    request_engine.dispose()
    worker_engine.dispose()


@pytest.fixture
def gate(monkeypatch, pools):
    """Replace the real indexing by a job that records the request pool's state and blocks until released."""
    state = {"entered": threading.Event(), "release": threading.Event(), "checked_out": None, "calls": 0}

    def gated(**kwargs):
        state["calls"] += 1
        state["checked_out"] = pools.pool.checkedout()  # observed from the worker thread, request still in flight
        state["entered"].set()
        state["release"].wait(15)
        return True

    monkeypatch.setattr(PlaygroundMediaService, "vectorize_uploaded_file", staticmethod(gated))
    yield state
    state["release"].set()


async def _wait(event: threading.Event):
    assert await asyncio.to_thread(event.wait, 15), "the indexing job was never reached"


@pytest.mark.parametrize("flow", ["upload", "/messages", "/stream"])
async def test_no_pooled_connection_is_held_while_files_are_indexed(stack, pools, gate, flow):
    w = stack.w
    cid = await stack.new_conversation("bob", selection(w.ai["x"]))
    file = ("note.txt", b"some text content to index", "text/plain")

    async def first_request():
        if flow == "upload":
            return await stack.client.post(
                stack.url(f"/conversations/{cid}/files"), headers=w.h["bob"], files={"file": file})
        return await stack.send("bob", "T", selection(w.ai["x"]), cid, flow, files=[("files", file)])

    async def scenario():
        task = stack.spawn(first_request())
        await _wait(gate["entered"])
        # the request is inside the (gated) indexing: its connection must already be back in the pool
        assert gate["checked_out"] == 0 and pools.pool.checkedout() == 0
        # and a second request still gets a connection from the pool of ONE (pool_timeout is 0.5 s)
        second = await stack.get("bob", "/options")
        assert second.status_code == 200, second.text
        gate["release"].set()
        first = await task
        assert first.status_code == 200, first.text
        assert pools.pool.checkedout() == 0
        return first

    await stack.run(scenario)
    assert gate["calls"] == 1
