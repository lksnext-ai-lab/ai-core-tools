"""Fixtures for the golden tests (independent from tests/unit/connectors/conftest.py)."""

import socket
import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import database
from models.output_delivery import (
    OutputArtifact, OutputDelivery, OutputDeliveryAttempt, OutputDestination, ScheduledTaskOutputBinding,
)
from models.scheduled_task import ScheduledTask, ScheduledTaskRun

FIXED_TIME = 1790000000.0
RECORDED_HEADERS = ("content-type", "content-length", "authorization", "idempotency-key")


@pytest.fixture
def golden_outbox(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    database.Base.metadata.create_all(engine, tables=[model.__table__ for model in (
        ScheduledTask, ScheduledTaskRun, OutputDestination, ScheduledTaskOutputBinding,
        OutputDelivery, OutputDeliveryAttempt, OutputArtifact,
    )])
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setenv("TMP_BASE_FOLDER", str(tmp_path))
    monkeypatch.setenv("FRONTEND_URL", "https://mattin.example")
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda host, port, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("20.1.2.3", 0))],
    )
    # Same location the service computes: <TMP_BASE_FOLDER>/output-deliveries
    factory.spool = Path(tmp_path).resolve() / "output-deliveries"
    yield factory
    engine.dispose()


@pytest.fixture
def deterministic(monkeypatch):
    """Make ``uuid.uuid4`` sequential (UUID(int=1), 2, ...) and ``time.time`` constant.

    Dependencies (the patch is on the global ``uuid`` / ``time`` modules):
    * modules under test must use ``import uuid`` / ``import time`` and call
      ``uuid.uuid4()`` / ``time.time()``; ``from uuid import uuid4`` or
      ``from time import time`` would silently bypass the patch.
    * nothing else may consume ``uuid.uuid4`` during a test (it would shift the
      sequence and change event ids and multipart boundaries).
    """
    import time

    counter = iter(range(1, 10_000))
    monkeypatch.setattr(uuid, "uuid4", lambda: uuid.UUID(int=next(counter)))
    monkeypatch.setattr(time, "time", lambda: FIXED_TIME)


class HttpRecorder:
    def __init__(self):
        self.requests: list[dict] = []
        self.status_code = 202

    def dump(self) -> list[dict]:
        return [dict(item) for item in self.requests]


@pytest.fixture
def http_recorder(monkeypatch):
    recorder = HttpRecorder()
    real_client = httpx.AsyncClient

    async def handler(request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        headers = {
            name: value for name, value in request.headers.items()
            if name in RECORDED_HEADERS or name.startswith("x-mattin-")
        }
        recorder.requests.append({
            "method": request.method, "url": str(request.url),
            "headers": dict(sorted(headers.items())), "body": body,
        })
        return httpx.Response(recorder.status_code)

    def factory(*args, **kwargs):
        # Guard the SSRF hardening: the stub below replaces the transport, so a
        # refactor that stopped passing these would otherwise go unnoticed.
        assert "transport" in kwargs, "provider must pass the pinned SSRF transport"
        assert kwargs.get("trust_env") is False, "provider must not trust proxy env vars (trust_env=False)"
        assert kwargs.get("follow_redirects") is False, "provider must not follow redirects (secret in URL)"
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return recorder
