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
async def test_read_pause_falls_back_to_none_on_unreadable_state():
    from services.agent_streaming_service import _read_pause

    chain = MagicMock()
    chain.aget_state = AsyncMock(side_effect=RuntimeError("checkpointer down"))

    assert await _read_pause(chain, {"configurable": {}}) is None


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

def _paused_state(interrupt_id="i1"):
    from langchain_core.messages import AIMessage

    return SimpleNamespace(
        tasks=[SimpleNamespace(interrupts=[SimpleNamespace(id=interrupt_id, value={
            "action_requests": [{"name": "search", "args": {"q": "x"}, "description": "Needs approval"}],
            "review_configs": [{"action_name": "search", "allowed_decisions": ["approve", "reject"]}],
        })])],
        values={"messages": [AIMessage(content="", tool_calls=[{"name": "search", "args": {"q": "x"}, "id": "call_1"}])]},
    )


def _hitl_ctx():
    return SimpleNamespace(
        effective_conv_id=7, conversation=SimpleNamespace(conversation_id=7, session_id="conv_1_7"),
        agent=SimpleNamespace(name="Agent", has_memory=True),
        fresh_agent=SimpleNamespace(agent_id=1, app_id=3, has_memory=True),
        search_params={}, session_id_for_cache="7", user_context={"user_id": 5},
        working_dir="/tmp/work", sandbox_handle=None, sandbox_provider=None, sandbox_session_key=None,
        enhanced_message="hello", image_files=[], processed_files=[],
    )


def _approval(interrupt_id="i1"):
    from datetime import datetime, timedelta, timezone
    from models.hitl_approval import HITLApproval

    now = datetime.now(timezone.utc)
    return HITLApproval(
        id="appr-1", app_id=3, agent_id=1, conversation_id=7, thread_id="thread_1_conv_1_7",
        interrupt_id=interrupt_id, channel="playground", status="pending",
        actions=[{"action_id": "call_1", "name": "search", "args": {"q": "x"},
                  "description": "Needs approval", "allowed_decisions": ["approve", "reject"]}],
        requested_by_user_id=5, created_at=now, expires_at=now + timedelta(hours=1),
    )


async def _empty_stream(*args, **kwargs):
    if False:
        yield None


async def _run_hitl(chain, *, approvals_overrides=None, **kwargs):
    from services.agent_streaming_service import AgentStreamingService

    execution_service = MagicMock()
    execution_service._prepare_turn = AsyncMock(return_value=_hitl_ctx())
    execution_service._finalize_turn = AsyncMock(return_value={
        "parsed_response": "ok", "effective_conv_id": 7, "files_data": []})
    execution_service._reject_in_place = AsyncMock()
    service = AgentStreamingService()
    service.execution_service = execution_service
    fakes = {
        "check_conversation_free": MagicMock(return_value=None),
        "open_approval": AsyncMock(return_value=_approval()),
        "finish": MagicMock(),
        "release": MagicMock(),
        **(approvals_overrides or {}),
    }
    kwargs.setdefault("message", "hi")
    with (
        patch("services.agent_streaming_service.human_in_the_loop_config", return_value=MagicMock()),
        patch("services.agent_streaming_service.create_agent", AsyncMock(return_value=(chain, None, None))),
        patch("services.agent_streaming_service.prepare_agent_config", return_value={"configurable": {}}),
        patch("services.agent_streaming_service.build_human_message", return_value=SimpleNamespace(content="hi")),
        patch.multiple("services.agent_streaming_service.approvals", **fakes),
    ):
        events = [e async for e in service.stream_agent_chat(
            agent_id=1, user_context={"user_id": 5}, conversation_id=7, db=MagicMock(), **kwargs)]
    return events, execution_service, fakes


def _resume(interrupt_id="i1"):
    from models.hitl_approval import ApprovalStatus
    from services.hitl_approval_service import ResumeRequest

    return ResumeRequest(_approval(interrupt_id), [{"type": "approve"}], ApprovalStatus.APPROVED)


@pytest.mark.asyncio
async def test_pause_records_approval_and_emits_interrupt():
    from models.hitl_approval import ApprovalChannel

    chain = MagicMock()
    chain.astream.side_effect = _empty_stream
    chain.aget_state = AsyncMock(return_value=_paused_state())

    events, execution_service, fakes = await _run_hitl(chain)

    assert fakes["open_approval"].await_args.kwargs["channel"] == ApprovalChannel.PLAYGROUND
    assert fakes["open_approval"].await_args.kwargs["answerable"] is True
    assert any('"hitl_interrupt"' in e and '"approval_id": "appr-1"' in e and '"call_1"' in e for e in events)
    assert any('"requires_approval"' in e and '"hitl_paused": true' in e for e in events)
    execution_service._finalize_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_pause_in_non_interactive_channel_is_rejected_in_place():
    from models.hitl_approval import ApprovalChannel

    chain = MagicMock()
    chain.astream.side_effect = _empty_stream
    chain.aget_state = AsyncMock(return_value=_paused_state())

    events, execution_service, fakes = await _run_hitl(chain, channel=ApprovalChannel.PLATFORM_CHATBOT)

    # Recorded already claimed: a reload must never show a pause nobody can answer.
    assert fakes["open_approval"].await_args.kwargs["answerable"] is False
    execution_service._reject_in_place.assert_awaited_once()
    assert any('"error"' in e and "approval_not_supported_in_channel" in e for e in events)
    assert not any('"hitl_interrupt"' in e for e in events)


@pytest.mark.asyncio
async def test_new_message_on_a_paused_conversation_is_refused():
    from services.hitl_approval_service import ApprovalPendingError

    chain = MagicMock()
    refused = MagicMock(side_effect=ApprovalPendingError("waiting", approval_id="appr-1"))

    events, _, _ = await _run_hitl(chain, approvals_overrides={"check_conversation_free": refused})

    assert any('"error"' in e and "approval_pending" in e for e in events)
    chain.astream.assert_not_called()


@pytest.mark.asyncio
async def test_resume_on_a_stale_pause_is_cancelled_without_running():
    from models.hitl_approval import ApprovalStatus

    chain = MagicMock()
    chain.aget_state = AsyncMock(return_value=_paused_state(interrupt_id="another"))

    events, _, fakes = await _run_hitl(chain, message="", resume=_resume())

    chain.astream.assert_not_called()
    assert fakes["finish"].call_args.args[2] == ApprovalStatus.CANCELLED
    assert any("approval_stale" in e for e in events)


@pytest.mark.asyncio
async def test_resume_sends_command_and_records_outcome():
    from langgraph.types import Command
    from models.hitl_approval import ApprovalStatus

    chain = MagicMock()
    chain.astream.side_effect = _empty_stream
    chain.aget_state = AsyncMock(side_effect=[_paused_state(), SimpleNamespace(tasks=[], values={})])

    events, execution_service, fakes = await _run_hitl(chain, message="", resume=_resume())

    sent = chain.astream.call_args.args[0]
    assert isinstance(sent, Command) and sent.resume == {"decisions": [{"type": "approve"}]}
    assert fakes["finish"].call_args.args[2] == ApprovalStatus.APPROVED
    fakes["release"].assert_not_called()
    execution_service._finalize_turn.assert_awaited_once()
    assert any('"done"' in e and '"completed"' in e for e in events)


@pytest.mark.asyncio
async def test_failed_resume_gives_the_claim_back():
    async def broken_stream(*args, **kwargs):
        raise RuntimeError("provider down")
        yield None

    chain = MagicMock()
    chain.astream.side_effect = broken_stream
    chain.aget_state = AsyncMock(return_value=_paused_state())

    events, _, fakes = await _run_hitl(chain, message="", resume=_resume())

    fakes["release"].assert_called_once()
    fakes["finish"].assert_not_called()
    assert any('"error"' in e for e in events)
