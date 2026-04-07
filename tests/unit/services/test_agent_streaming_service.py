from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.a2a_executor_service import A2AMemoryContext
from services.agent_execution_context import AgentExecutionContext
from services.agent_streaming_service import AgentStreamingService


def _make_a2a_agent() -> MagicMock:
    agent = MagicMock()
    agent.agent_id = 9
    agent.name = "Remote Agent"
    agent.has_memory = True
    agent.a2a_config = MagicMock(
        remote_skill_id="skill-9",
        card_url="https://example.com/.well-known/agent-card.json",
    )
    return agent


@pytest.mark.asyncio
async def test_stream_agent_chat_persists_a2a_remote_state_from_final_event():
    default_db = MagicMock()
    effective_db = MagicMock()
    service = AgentStreamingService(db=default_db)
    service.execution_service = MagicMock()

    fresh_agent = _make_a2a_agent()
    conversation = MagicMock(conversation_id=77)
    ctx = AgentExecutionContext(
        agent_id=9,
        agent=fresh_agent,
        fresh_agent=fresh_agent,
        enhanced_message="hello",
        image_files=[],
        session=None,
        conversation=conversation,
        effective_conv_id=77,
        session_id_for_cache="conv_9_abc",
        working_dir=None,
        pre_existing_files=set(),
        processed_files=[],
        search_params=None,
        user_context={"user_id": 1},
        a2a_memory_context=A2AMemoryContext(
            remote_task_id="old-task",
            remote_context_id="old-context",
            remote_task_state="input-required",
        ),
    )
    service.execution_service._prepare_turn = AsyncMock(return_value=ctx)
    service.execution_service._persist_a2a_history = AsyncMock()
    service.execution_service._finalize_turn = AsyncMock(
        return_value={
            "parsed_response": "parsed remote reply",
            "effective_conv_id": 77,
            "files_data": [],
        }
    )

    async def fake_stream(*args, **kwargs):
        yield {
            "type": "final",
            "data": {
                "content": "remote final reply",
                "remote_task_id": "task-22",
                "remote_context_id": "ctx-22",
                "remote_task_state": "input-required",
            },
        }

    with (
        patch("services.agent_streaming_service.A2AExecutorService.stream", new=fake_stream),
        patch("services.agent_streaming_service.A2AService.update_health"),
        patch(
            "services.agent_streaming_service.format_sse_event",
            side_effect=lambda event, data: {"event": event, "data": data},
        ),
    ):
        events = []
        async for event in service.stream_agent_chat(
            agent_id=9,
            message="hello",
            user_context={"user_id": 1},
            conversation_id=77,
            db=effective_db,
        ):
            events.append(event)

    assert events[0]["event"] == "metadata"
    assert events[1]["event"] == "final"
    assert events[2]["event"] == "done"
    service.execution_service._apply_a2a_remote_state.assert_called_once()
    applied_result = service.execution_service._apply_a2a_remote_state.call_args.args[1]
    assert applied_result.remote_task_id == "task-22"
    assert applied_result.remote_context_id == "ctx-22"
    assert applied_result.remote_task_state == "input-required"
    service.execution_service._persist_a2a_history.assert_awaited_once_with(
        ctx,
        "remote final reply",
    )
    service.execution_service._finalize_turn.assert_awaited_once_with(
        ctx,
        "remote final reply",
        effective_db,
    )
