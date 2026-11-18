"""Streaming: a retired service ends the turn with one `error` event (kind service_retired)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.unit.services.test_agent_stream_events import _make_chain, _make_ctx, _run_events
from langchain_core.messages import AIMessageChunk

from utils import service_lifecycle
from utils.service_lifecycle import ServiceRetiredError, get_service_call_context


@pytest.mark.asyncio
async def test_retired_service_yields_single_error_event():
    svc = SimpleNamespace(
        service_id=7, app_id=3, name="gpt-old", end_of_service_at=datetime.now(timezone.utc) - timedelta(days=1),
        deprecation_notice="Use gpt-new.",
    )
    exc = ServiceRetiredError(svc, "ai")
    create_agent = AsyncMock(side_effect=exc)

    events, harness = await _run_events(ctx=_make_ctx(), create_agent_mock=create_agent)

    errors = [e for e in events if e.type == "error"]
    assert len(errors) == 1 and events[-1] is errors[0]
    assert errors[0].data == {"message": exc.message, "code": "service_retired"}
    assert errors[0].extra["error_kind"] == "service_retired"
    assert errors[0].extra["error_code"] == "SERVICE_RETIRED"
    assert errors[0].extra["detail"] == exc.message
    assert "Use gpt-new." in exc.message
    assert harness.recorded_kwargs["status"] == "ERROR"
    assert harness.recorded_kwargs["error_code"] == "SERVICE_RETIRED"
    assert not [e for e in events if e.type == "done"]


@pytest.mark.asyncio
async def test_retired_mid_stream_after_a_token_yields_one_error_no_done():
    svc = SimpleNamespace(
        service_id=7, app_id=3, name="emb-old", end_of_service_at=datetime.now(timezone.utc) - timedelta(days=1),
        deprecation_notice=None,
    )
    exc = ServiceRetiredError(svc, "embedding")

    async def _gen():
        yield ("messages", (AIMessageChunk(content="Hel"), {}))
        raise exc

    chain = _make_chain([])
    chain.astream.return_value = _gen()
    create_agent = AsyncMock(return_value=(chain, None))

    # Reset the ContextVar token afterwards so the assertion can't pass on leftover state.
    token = service_lifecycle._call_context.set(None)
    try:
        events, harness = await _run_events(ctx=_make_ctx(), create_agent_mock=create_agent)
        ctx_after = get_service_call_context()
    finally:
        service_lifecycle._call_context.reset(token)

    assert [e.type for e in events].count("error") == 1
    assert events[-1].type == "error" and events[-1].extra["error_kind"] == "service_retired"
    assert not [e for e in events if e.type == "done"]
    assert harness.recorded_kwargs["error_code"] == "SERVICE_RETIRED"
    assert ctx_after["channel"] == "playground" and ctx_after["resource_type"] == "agent"
