"""No raw API key (or its hash) ever reaches the logs during an A2A turn.

Drives a real `SendMessage` over HTTP through the router, runtime, executor
bridge and `AgentStreamingService.stream_agent_events`, including the real
`AgentExecutionService._prepare_turn` (where a removed access-check stub used
to log the whole user context, API key included). Only the LLM chain is
faked, so no provider is called.

Mattin's loggers do not propagate to the root logger, so `caplog` would miss
them; records are captured at `logging.Logger.handle` instead, which every
emitted record on every logger goes through.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessageChunk

from services.agent_execution_service import AgentExecutionService
from utils.a2a_config import get_a2a_config

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clear_a2a_config_cache():
    get_a2a_config.cache_clear()
    yield
    get_a2a_config.cache_clear()


def _fake_chain():
    async def _gen():
        yield ("messages", (AIMessageChunk(content="Hello"), {}))
        yield ("messages", (AIMessageChunk(content=" world"), {}))

    chain = MagicMock()
    chain.astream.side_effect = lambda *args, **kwargs: _gen()
    return chain


def _record_text(record: logging.LogRecord) -> str:
    parts = [record.getMessage()]
    parts.extend(repr(value) for key, value in vars(record).items() if key not in ("msg", "args"))
    return "\n".join(parts)


def test_an_a2a_turn_never_logs_the_raw_key_or_its_hash(client, a2a_committed_world, monkeypatch):
    world = a2a_committed_world
    raw_key = world.key_1_raw
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    monkeypatch.setattr(
        "services.agent_streaming_service.create_agent", AsyncMock(return_value=(_fake_chain(), None))
    )
    original_prepare_turn = AgentExecutionService._prepare_turn
    calls: list = []

    async def _spy_prepare_turn(self, *args, **kwargs):
        calls.append(kwargs.get("user_context"))
        return await original_prepare_turn(self, *args, **kwargs)

    monkeypatch.setattr(AgentExecutionService, "_prepare_turn", _spy_prepare_turn)

    records: list[logging.LogRecord] = []
    original_handle = logging.Logger.handle

    def _capturing_handle(self, record):
        records.append(record)
        return original_handle(self, record)

    monkeypatch.setattr(logging.Logger, "handle", _capturing_handle)
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "SendMessage",
        "params": {
            "message": {
                "messageId": str(uuid.uuid4()),
                "role": "ROLE_USER",
                "parts": [{"text": "hello"}],
            }
        },
    }
    resp = client.post(
        f"/a2a/v1/apps/{world.app_slug}/agents/{world.agent_public_id}",
        json=payload,
        headers={"A2A-Version": "1.0", "X-API-KEY": raw_key},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert "error" not in body, body
    assert body["result"]["task"]["status"]["state"] == "TASK_STATE_COMPLETED"
    # The real _prepare_turn ran with the API-key user context.
    assert len(calls) == 1
    assert calls[0]["api_key"] == raw_key

    assert records, "expected the turn to log something"
    for record in records:
        text = _record_text(record)
        assert raw_key not in text, f"raw API key logged by {record.name}: {record.getMessage()!r}"
        assert key_hash not in text, f"API key hash logged by {record.name}: {record.getMessage()!r}"
