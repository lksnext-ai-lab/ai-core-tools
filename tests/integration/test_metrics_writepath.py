"""
Integration test: write-path instrumentation for agent metrics.

AgentExecutionService._execute_agent_async records one metrics event per run
(success or error), and persist_metrics_payload stores it in the real schema.

LangGraph / LLM calls are mocked to avoid real API calls.
"""
import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_fake_agent(app_id: int, agent_id: int) -> MagicMock:
    """Build a minimal Agent mock that _execute_agent_async can use."""
    agent = MagicMock()
    agent.agent_id = agent_id
    agent.app_id = app_id
    agent.name = "Fake Agent"
    agent.type = "agent"
    agent.has_memory = False
    agent.silo_id = None
    agent.output_parser_id = None
    agent.ai_service = None
    agent.ai_service_id = None
    agent.is_frozen = False
    agent.request_count = 0
    agent.app = MagicMock()
    agent.app.langsmith_api_key = None
    return agent


def _make_fake_result() -> dict:
    """Return a plausible LangGraph result dict with usage metadata."""
    ai_msg = AIMessage(content="Hello from mock LLM!")
    ai_msg.usage_metadata = {
        "input_tokens": 50,
        "output_tokens": 25,
        "total_tokens": 75,
    }
    return {"messages": [ai_msg]}


async def _drain_tasks():
    """Yield control to the event loop to let pending tasks run."""
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.fixture
def captured_payloads():
    """Capture metrics payloads instead of writing them."""
    captured = []

    async def _capture(payload):
        captured.append(payload)

    with patch("services.agent_metrics_recorder.persist_metrics_payload", new=_capture):
        yield captured


async def _run_agent(fake_app, fake_agent, chain, user_context):
    from services.agent_execution_service import AgentExecutionService

    with patch("tools.agentTools.create_agent", new=AsyncMock(return_value=(chain, None))), \
         patch("tools.agentTools.prepare_agent_config", return_value={"configurable": {}}), \
         patch("tools.agentTools.build_human_message", return_value=MagicMock()):
        svc = AgentExecutionService.__new__(AgentExecutionService)
        try:
            await svc._execute_agent_async(
                fresh_agent=_make_fake_agent(fake_app.app_id, fake_agent.agent_id),
                message="Hello",
                user_context=user_context,
            )
        finally:
            await _drain_tasks()


# ── Tests ────────────────────────────────────────────────────────────────────


class TestWritePathSuccess:

    @pytest.mark.asyncio
    async def test_success_payload(self, fake_app, fake_agent, captured_payloads):
        chain = MagicMock()
        chain.ainvoke = AsyncMock(return_value=_make_fake_result())

        await _run_agent(fake_app, fake_agent, chain, user_context={})

        assert len(captured_payloads) == 1, "Exactly one event per execution"
        event = captured_payloads[0]["event"]
        assert event["status"] == "SUCCESS"
        assert event["caller_type"] == "INTERNAL_PLAYGROUND"
        assert event["duration_ms"] is not None
        assert event["agent_id"] == fake_agent.agent_id
        assert event["app_id"] == fake_app.app_id
        assert event["input_tokens"] == 50
        assert event["output_tokens"] == 25
        assert event["total_tokens"] == 75

    @pytest.mark.asyncio
    async def test_public_api_caller(self, fake_app, fake_agent, captured_payloads):
        chain = MagicMock()
        chain.ainvoke = AsyncMock(return_value=_make_fake_result())

        await _run_agent(fake_app, fake_agent, chain, user_context={"api_key_id": 42})

        assert len(captured_payloads) == 1
        assert captured_payloads[0]["event"]["caller_type"] == "PUBLIC_API"

    @pytest.mark.asyncio
    async def test_caller_user_context_is_not_mutated(self, fake_app, fake_agent, captured_payloads):
        chain = MagicMock()
        chain.ainvoke = AsyncMock(return_value=_make_fake_result())
        user_context = {"user_id": 1}

        await _run_agent(fake_app, fake_agent, chain, user_context=user_context)

        assert user_context == {"user_id": 1}


class TestWritePathError:

    @pytest.mark.asyncio
    async def test_error_payload(self, fake_app, fake_agent, captured_payloads):
        chain = MagicMock()
        chain.ainvoke = AsyncMock(side_effect=ValueError("provider down"))

        with pytest.raises(ValueError, match="provider down"):
            await _run_agent(fake_app, fake_agent, chain, user_context={})

        assert len(captured_payloads) == 1, "An event is recorded even on error"
        event = captured_payloads[0]["event"]
        assert event["status"] == "ERROR"
        assert event["error_code"] == "ValueError"
        assert event["duration_ms"] is not None


class TestPersistMetricsPayload:
    """The payload fits the real schema (FKs, enums, UUIDs)."""

    @pytest.mark.asyncio
    async def test_persists_root_and_sub_agent_events(self, db, fake_app, fake_agent):
        from models.agent_execution_event import AgentExecutionEvent
        from services.agent_metrics_recorder import build_metrics_payload, persist_metrics_payload

        root_id, sub_id = str(uuid.uuid4()), str(uuid.uuid4())
        common = dict(
            fresh_agent=fake_agent, started_at=datetime(2026, 1, 1, 12), finished_at=datetime(2026, 1, 1, 12, 0, 1),
            duration_ms=1000, status="SUCCESS", error_code=None, error_message=None,
            result=_make_fake_result(), image_files=[], message="hi",
        )
        # The sub-agent finishes (and is written) before its parent.
        sub = build_metrics_payload(
            event_id=sub_id,
            user_context={"parent_execution_id": root_id, "caller_type_override": "AGENT_AS_TOOL"},
            **common,
        )
        root = build_metrics_payload(
            event_id=root_id, user_context={"user_id": "apikey_abc", "api_key": "k"}, **common,
        )

        with patch("db.database.SessionLocal", return_value=db):
            await persist_metrics_payload(sub)
            await persist_metrics_payload(root)

        rows = {str(r.event_id): r for r in db.query(AgentExecutionEvent).all()}
        assert set(rows) == {root_id, sub_id}
        assert str(rows[sub_id].parent_execution_id) == root_id
        assert rows[root_id].user_id is None
        assert rows[root_id].caller_type.value == "PUBLIC_API"
        assert rows[root_id].total_tokens == 75
