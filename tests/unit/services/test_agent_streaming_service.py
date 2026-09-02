from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


async def _empty_stream():
    if False:
        yield None


async def _missing_tool_output_stream():
    raise RuntimeError(
        "Error code: 400 - No tool output found for function call call_stale"
    )
    if False:
        yield None


@pytest.mark.asyncio
async def test_streaming_agent_passes_sandbox_session_key_to_tool_builder():
    from services.agent_streaming_service import AgentStreamingService

    ctx = SimpleNamespace(
        effective_conv_id=297,
        agent=SimpleNamespace(name="Agent", has_memory=True),
        fresh_agent=SimpleNamespace(agent_id=1, has_memory=True),
        search_params={},
        session_id_for_cache="297",
        user_context={"user_id": "u1"},
        working_dir="/tmp/work",
        sandbox_handle=MagicMock(),
        sandbox_provider=MagicMock(),
        sandbox_session_key="conv_1_297",
        enhanced_message="hello",
        image_files=[],
    )

    execution_service = MagicMock()
    execution_service._prepare_turn = AsyncMock(return_value=ctx)
    execution_service._finalize_turn = AsyncMock(
        return_value={
            "parsed_response": "done",
            "effective_conv_id": 297,
            "files_data": [],
        }
    )

    agent_chain = MagicMock()
    agent_chain.astream.return_value = _empty_stream()
    create_agent = AsyncMock(return_value=(agent_chain, None, None))

    service = AgentStreamingService()
    service.execution_service = execution_service
    db = MagicMock()

    with (
        patch("services.agent_streaming_service.create_agent", create_agent),
        patch("services.agent_streaming_service.prepare_agent_config", return_value={"configurable": {}}),
        patch("services.agent_streaming_service.build_human_message", return_value=SimpleNamespace(content="hello")),
    ):
        events = [
            event
            async for event in service.stream_agent_chat(
                agent_id=1,
                message="hello",
                file_references=[],
                user_context={"user_id": "u1"},
                conversation_id=297,
                db=db,
            )
        ]

    assert events
    assert create_agent.call_args.kwargs["sandbox_session_key"] == "conv_1_297"
    execution_service._begin_sandbox_turn.assert_called_once_with(
        ctx,
        db=db,
    )
    execution_service._end_sandbox_turn.assert_called_once_with(
        ctx,
        db=db,
    )


@pytest.mark.asyncio
async def test_streaming_resets_stale_tool_call_checkpoint_and_retries():
    from services.agent_streaming_service import AgentStreamingService

    ctx = SimpleNamespace(
        effective_conv_id=297,
        agent=SimpleNamespace(name="Agent", has_memory=True),
        fresh_agent=SimpleNamespace(agent_id=1, has_memory=True),
        search_params={},
        session_id_for_cache="297",
        user_context={"user_id": "u1"},
        working_dir="/tmp/work",
        sandbox_handle=MagicMock(),
        sandbox_provider=MagicMock(),
        sandbox_session_key="conv_1_297",
        enhanced_message="hello",
        image_files=[],
    )

    execution_service = MagicMock()
    execution_service._prepare_turn = AsyncMock(return_value=ctx)
    execution_service._finalize_turn = AsyncMock(
        return_value={
            "parsed_response": "done",
            "effective_conv_id": 297,
            "files_data": [],
        }
    )

    first_chain = MagicMock()
    first_chain.astream.return_value = _missing_tool_output_stream()
    first_chain.aget_state = AsyncMock(return_value=SimpleNamespace(tasks=[]))
    second_chain = MagicMock()
    second_chain.astream.return_value = _empty_stream()
    create_agent = AsyncMock(
        side_effect=[
            (first_chain, None, None),
            (second_chain, None, None),
        ]
    )

    service = AgentStreamingService()
    service.execution_service = execution_service

    with (
        patch("services.agent_streaming_service.create_agent", create_agent),
        patch("services.agent_streaming_service.prepare_agent_config", return_value={"configurable": {}}),
        patch("services.agent_streaming_service.build_human_message", return_value=SimpleNamespace(content="hello")),
        patch(
            "services.agent_streaming_service.CheckpointerCacheService.invalidate_checkpointer_async",
            new=AsyncMock(),
        ) as invalidate_checkpoint,
    ):
        events = [
            event
            async for event in service.stream_agent_chat(
                agent_id=1,
                message="hello",
                file_references=[],
                user_context={"user_id": "u1"},
                conversation_id=297,
                db=MagicMock(),
            )
        ]

    assert len(create_agent.call_args_list) == 2
    invalidate_checkpoint.assert_awaited_once_with(1, "297")
    assert any('"done"' in event for event in events)


@pytest.mark.asyncio
async def test_streaming_keeps_checkpoint_when_hitl_interrupt_is_pending():
    """A HITL pause looks like a stale tool-call checkpoint — don't delete it."""
    from services.agent_streaming_service import AgentStreamingService

    ctx = SimpleNamespace(
        effective_conv_id=297,
        agent=SimpleNamespace(name="Agent", has_memory=True),
        fresh_agent=SimpleNamespace(agent_id=1, has_memory=True),
        search_params={},
        session_id_for_cache="297",
        user_context={"user_id": "u1"},
        working_dir="/tmp/work",
        sandbox_handle=MagicMock(),
        sandbox_provider=MagicMock(),
        sandbox_session_key="conv_1_297",
        enhanced_message="hello",
        image_files=[],
    )

    execution_service = MagicMock()
    execution_service._prepare_turn = AsyncMock(return_value=ctx)

    chain = MagicMock()
    chain.astream.return_value = _missing_tool_output_stream()
    chain.aget_state = AsyncMock(
        return_value=SimpleNamespace(
            tasks=[SimpleNamespace(interrupts=[SimpleNamespace(value={})])]
        )
    )
    create_agent = AsyncMock(return_value=(chain, None, None))

    service = AgentStreamingService()
    service.execution_service = execution_service

    with (
        patch("services.agent_streaming_service.create_agent", create_agent),
        patch("services.agent_streaming_service.prepare_agent_config", return_value={"configurable": {}}),
        patch("services.agent_streaming_service.build_human_message", return_value=SimpleNamespace(content="hello")),
        patch(
            "services.agent_streaming_service.CheckpointerCacheService.invalidate_checkpointer_async",
            new=AsyncMock(),
        ) as invalidate_checkpoint,
    ):
        events = [
            event
            async for event in service.stream_agent_chat(
                agent_id=1,
                message="hello",
                file_references=[],
                user_context={"user_id": "u1"},
                conversation_id=297,
                db=MagicMock(),
            )
        ]

    invalidate_checkpoint.assert_not_awaited()
    assert len(create_agent.call_args_list) == 1
    assert any('"error"' in event for event in events)


@pytest.mark.asyncio
async def test_has_pending_interrupt_falls_back_to_false_on_unreadable_state():
    from services.agent_streaming_service import _has_pending_interrupt

    chain = MagicMock()
    chain.aget_state = AsyncMock(side_effect=RuntimeError("checkpointer down"))

    assert await _has_pending_interrupt(chain, {"configurable": {}}) is False
