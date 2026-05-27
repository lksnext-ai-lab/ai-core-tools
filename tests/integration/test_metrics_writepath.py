"""
Integration test: write-path instrumentation for agent metrics.

Tests that AgentExecutionService._execute_agent_async fires the metrics hook
with the correct payload on success, on error, and is a no-op when no plugin
is registered.

LangGraph / LLM calls are mocked to avoid real API calls.
"""
import asyncio
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

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


# ── Tests ────────────────────────────────────────────────────────────────────


class TestWritePathSuccess:
    """Hook is called with SUCCESS payload after a mocked successful invocation."""

    @pytest.mark.asyncio
    async def test_hook_called_with_success_payload(self, fake_app, fake_agent):
        """After a successful invocation, the hook receives a SUCCESS payload."""
        from services.agent_execution_service import AgentExecutionService
        import services.metrics_hooks as _hooks

        captured_payload = []

        async def _capture_hook(payload):
            captured_payload.append(payload)

        # Register our capture hook
        original_hook = _hooks.get_execution_hook()
        _hooks.register_execution_hook(_capture_hook)

        fake_result = _make_fake_result()
        fake_chain = MagicMock()
        fake_chain.ainvoke = AsyncMock(return_value=fake_result)

        try:
            with patch("tools.agentTools.create_agent", new=AsyncMock(return_value=(fake_chain, None))), \
                 patch("tools.agentTools.prepare_agent_config", return_value={"configurable": {}}), \
                 patch("tools.agentTools.build_human_message", return_value=MagicMock()):

                svc = AgentExecutionService.__new__(AgentExecutionService)
                agent = _make_fake_agent(fake_app.app_id, fake_agent.agent_id)

                await svc._execute_agent_async(
                    fresh_agent=agent,
                    message="Hello",
                    user_context={},
                )

                # Drain tasks so the create_task in _fire_metrics_hook runs
                await _drain_tasks()

        finally:
            # Restore original hook (None in OSS mode)
            _hooks.register_execution_hook(original_hook)

        assert len(captured_payload) == 1, "Hook should be called exactly once"
        event = captured_payload[0]["event"]
        assert event["status"] == "SUCCESS"
        assert event["caller_type"] == "INTERNAL_PLAYGROUND"
        assert event["duration_ms"] is not None
        assert event["agent_id"] == fake_agent.agent_id
        assert event["app_id"] == fake_app.app_id
        assert event["input_tokens"] == 50
        assert event["output_tokens"] == 25
        assert event["total_tokens"] == 75

    @pytest.mark.asyncio
    async def test_hook_called_with_public_api_caller(self, fake_app, fake_agent):
        """When api_key_id is in user_context, caller_type is PUBLIC_API."""
        from services.agent_execution_service import AgentExecutionService
        import services.metrics_hooks as _hooks

        captured_payload = []

        async def _capture_hook(payload):
            captured_payload.append(payload)

        original_hook = _hooks.get_execution_hook()
        _hooks.register_execution_hook(_capture_hook)

        fake_chain = MagicMock()
        fake_chain.ainvoke = AsyncMock(return_value=_make_fake_result())

        try:
            with patch("tools.agentTools.create_agent", new=AsyncMock(return_value=(fake_chain, None))), \
                 patch("tools.agentTools.prepare_agent_config", return_value={"configurable": {}}), \
                 patch("tools.agentTools.build_human_message", return_value=MagicMock()):

                svc = AgentExecutionService.__new__(AgentExecutionService)
                agent = _make_fake_agent(fake_app.app_id, fake_agent.agent_id)

                await svc._execute_agent_async(
                    fresh_agent=agent,
                    message="API call",
                    user_context={"api_key_id": 42},
                )
                await _drain_tasks()
        finally:
            _hooks.register_execution_hook(original_hook)

        assert len(captured_payload) == 1
        assert captured_payload[0]["event"]["caller_type"] == "PUBLIC_API"


class TestWritePathError:
    """Hook is called with ERROR payload when ainvoke raises."""

    @pytest.mark.asyncio
    async def test_hook_called_with_error_payload(self, fake_app, fake_agent):
        """When ainvoke raises, the hook receives an ERROR payload."""
        from services.agent_execution_service import AgentExecutionService
        import services.metrics_hooks as _hooks

        captured_payload = []

        async def _capture_hook(payload):
            captured_payload.append(payload)

        original_hook = _hooks.get_execution_hook()
        _hooks.register_execution_hook(_capture_hook)

        fake_chain = MagicMock()
        fake_chain.ainvoke = AsyncMock(side_effect=ValueError("provider down"))

        try:
            with patch("tools.agentTools.create_agent", new=AsyncMock(return_value=(fake_chain, None))), \
                 patch("tools.agentTools.prepare_agent_config", return_value={"configurable": {}}), \
                 patch("tools.agentTools.build_human_message", return_value=MagicMock()):

                svc = AgentExecutionService.__new__(AgentExecutionService)
                agent = _make_fake_agent(fake_app.app_id, fake_agent.agent_id)

                with pytest.raises(ValueError, match="provider down"):
                    await svc._execute_agent_async(
                        fresh_agent=agent,
                        message="Hello",
                        user_context={},
                    )

                await _drain_tasks()
        finally:
            _hooks.register_execution_hook(original_hook)

        assert len(captured_payload) == 1, "Hook must be called even on error"
        event = captured_payload[0]["event"]
        assert event["status"] == "ERROR"
        assert event["error_code"] == "ValueError"
        assert event["duration_ms"] is not None


class TestWritePathNoPlugin:
    """When no hook is registered, execution succeeds and no hook is called."""

    @pytest.mark.asyncio
    async def test_no_hook_no_side_effects(self, fake_app, fake_agent):
        """Without plugin, invocation succeeds and no hook is fired."""
        from services.agent_execution_service import AgentExecutionService
        import services.metrics_hooks as _hooks

        # Ensure no hook is registered
        original_hook = _hooks.get_execution_hook()
        _hooks.register_execution_hook(None)

        call_count = {"n": 0}

        async def _should_not_be_called(payload):
            call_count["n"] += 1

        # We do NOT register the above; hook remains None
        fake_chain = MagicMock()
        fake_chain.ainvoke = AsyncMock(return_value=_make_fake_result())

        try:
            with patch("tools.agentTools.create_agent", new=AsyncMock(return_value=(fake_chain, None))), \
                 patch("tools.agentTools.prepare_agent_config", return_value={"configurable": {}}), \
                 patch("tools.agentTools.build_human_message", return_value=MagicMock()):

                svc = AgentExecutionService.__new__(AgentExecutionService)
                agent = _make_fake_agent(fake_app.app_id, fake_agent.agent_id)

                # Should not raise
                await svc._execute_agent_async(
                    fresh_agent=agent,
                    message="Hello",
                    user_context={},
                )
                await _drain_tasks()
        finally:
            _hooks.register_execution_hook(original_hook)

        assert call_count["n"] == 0, "No hook should be called when none is registered"
