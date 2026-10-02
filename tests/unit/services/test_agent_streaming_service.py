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
        conversation=None,
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
        processed_files=[],
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
        conversation=None,
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
        processed_files=[],
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
            "services.agent_streaming_service.CheckpointerCacheService.get_rollback_checkpoint_id",
            new=AsyncMock(return_value="01ARZ3NDEKTSV4RRFFQ69G5FAV"),
        ) as get_rollback_checkpoint_id,
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
    get_rollback_checkpoint_id.assert_awaited_once_with(1, "297")
    # The retry must fork from the prior checkpoint, not delete anything.
    assert second_chain.astream.call_args.kwargs["config"]["configurable"]["checkpoint_id"] == (
        "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    )
    assert any('"done"' in event for event in events)


@pytest.mark.asyncio
async def test_streaming_keeps_checkpoint_when_hitl_interrupt_is_pending():
    """A HITL pause looks like a stale tool-call checkpoint — don't delete it."""
    from services.agent_streaming_service import AgentStreamingService

    ctx = SimpleNamespace(
        effective_conv_id=297,
        conversation=None,
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
        processed_files=[],
    )

    execution_service = MagicMock()
    execution_service._prepare_turn = AsyncMock(return_value=ctx)

    chain = MagicMock()
    chain.astream.return_value = _missing_tool_output_stream()
    chain.aget_state = AsyncMock(return_value=_paused_state())
    create_agent = AsyncMock(return_value=(chain, None, None))

    service = AgentStreamingService()
    service.execution_service = execution_service

    with (
        patch("services.agent_streaming_service.human_in_the_loop_config", return_value=MagicMock()),
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
async def test_pending_approval_falls_back_to_none_on_unreadable_state():
    from services.agent_streaming_service import _pending_approval

    chain = MagicMock()
    chain.aget_state = AsyncMock(side_effect=RuntimeError("checkpointer down"))

    assert await _pending_approval(chain, {"configurable": {}}) is None


@pytest.mark.asyncio
async def test_streaming_fails_cleanly_when_no_checkpoint_to_roll_back_to():
    """When the broken checkpoint is the thread's first ever state, there is
    nothing to fork from — the turn must fail with a clean error instead of
    retrying (and must not fall back to deleting the thread)."""
    from services.agent_streaming_service import AgentStreamingService

    ctx = SimpleNamespace(
        effective_conv_id=297,
        conversation=None,
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
        processed_files=[],
    )

    execution_service = MagicMock()
    execution_service._prepare_turn = AsyncMock(return_value=ctx)
    execution_service._finalize_turn = AsyncMock()

    first_chain = MagicMock()
    first_chain.astream.return_value = _missing_tool_output_stream()
    create_agent = AsyncMock(return_value=(first_chain, None, None))

    service = AgentStreamingService()
    service.execution_service = execution_service

    with (
        patch("services.agent_streaming_service.create_agent", create_agent),
        patch("services.agent_streaming_service.prepare_agent_config", return_value={"configurable": {}}),
        patch("services.agent_streaming_service.build_human_message", return_value=SimpleNamespace(content="hello")),
        patch(
            "services.agent_streaming_service.CheckpointerCacheService.get_rollback_checkpoint_id",
            new=AsyncMock(return_value=None),
        ),
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

    assert len(create_agent.call_args_list) == 1
    assert any('"error"' in event and "resend" in event for event in events)
    execution_service._finalize_turn.assert_not_awaited()


# ---------------------------------------------------------------------------
# Human-in-the-loop pause / resume
# ---------------------------------------------------------------------------

def _paused_state():
    return SimpleNamespace(tasks=[SimpleNamespace(interrupts=[SimpleNamespace(value={
        "action_requests": [{"name": "search", "args": {"q": "x"}, "description": "Needs approval"}],
        "review_configs": [{"action_name": "search", "allowed_decisions": ["approve", "reject"]}],
    })])])


def _hitl_ctx():
    return SimpleNamespace(
        effective_conv_id=7, conversation=None,
        agent=SimpleNamespace(name="Agent", has_memory=True),
        fresh_agent=SimpleNamespace(agent_id=1, has_memory=True),
        search_params={}, session_id_for_cache="7", user_context={"user_id": "u1"},
        working_dir="/tmp/work", sandbox_handle=None, sandbox_provider=None, sandbox_session_key=None,
        enhanced_message="hello", image_files=[], processed_files=[],
    )


async def _empty_stream(*args, **kwargs):
    if False:
        yield None


async def _run_hitl(chain, **kwargs):
    from services.agent_streaming_service import AgentStreamingService

    execution_service = MagicMock()
    execution_service._prepare_turn = AsyncMock(return_value=_hitl_ctx())
    execution_service._finalize_turn = AsyncMock(return_value={
        "parsed_response": "ok", "effective_conv_id": 7, "files_data": []})
    service = AgentStreamingService()
    service.execution_service = execution_service
    with (
        patch("services.agent_streaming_service.human_in_the_loop_config", return_value=MagicMock()),
        patch("services.agent_streaming_service.create_agent", AsyncMock(return_value=(chain, None, None))),
        patch("services.agent_streaming_service.prepare_agent_config", return_value={"configurable": {}}),
        patch("services.agent_streaming_service.build_human_message", return_value=SimpleNamespace(content="hi")),
    ):
        events = [e async for e in service.stream_agent_chat(
            agent_id=1, message="hi", user_context={"user_id": "u1"}, conversation_id=7, db=MagicMock(), **kwargs)]
    return events, execution_service


@pytest.mark.asyncio
async def test_pause_emits_interrupt_and_skips_finalize():
    chain = MagicMock()
    chain.astream.side_effect = _empty_stream
    chain.aget_state = AsyncMock(return_value=_paused_state())

    events, execution_service = await _run_hitl(chain)

    assert any('"hitl_interrupt"' in e and '"search"' in e for e in events)
    assert any('"hitl_paused": true' in e for e in events)
    execution_service._finalize_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_pause_without_approval_ui_is_an_error():
    chain = MagicMock()
    chain.astream.side_effect = _empty_stream
    chain.aget_state = AsyncMock(return_value=_paused_state())

    events, _ = await _run_hitl(chain, approval_ui=False)

    assert any('"error"' in e and "needs human approval" in e for e in events)
    assert not any('"hitl_interrupt"' in e for e in events)


@pytest.mark.asyncio
async def test_resume_with_disallowed_decision_never_reaches_the_graph():
    chain = MagicMock()
    chain.aget_state = AsyncMock(return_value=_paused_state())

    events, _ = await _run_hitl(chain, resume_decisions=[
        {"type": "edit", "edited_action": {"name": "search", "args": {}}}])

    assert any('"error"' in e and "not allowed" in e for e in events)
    chain.astream.assert_not_called()


@pytest.mark.asyncio
async def test_resume_without_pending_approval_is_rejected():
    chain = MagicMock()
    chain.aget_state = AsyncMock(return_value=SimpleNamespace(tasks=[]))

    events, _ = await _run_hitl(chain, resume_decisions=[{"type": "approve"}])

    assert any("no pending approval" in e for e in events)
    chain.astream.assert_not_called()


@pytest.mark.asyncio
async def test_resume_sends_command_with_decisions():
    from langgraph.types import Command

    chain = MagicMock()
    chain.astream.side_effect = _empty_stream
    chain.aget_state = AsyncMock(side_effect=[_paused_state(), SimpleNamespace(tasks=[])])

    events, execution_service = await _run_hitl(chain, resume_decisions=[{"type": "approve"}])

    sent = chain.astream.call_args.args[0]
    assert isinstance(sent, Command) and sent.resume == {"decisions": [{"type": "approve"}]}
    execution_service._finalize_turn.assert_awaited_once()
    assert any('"done"' in e for e in events)
