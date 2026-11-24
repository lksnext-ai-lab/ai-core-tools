"""Unit tests: a rejected pause is always closed, and non-chat turns keep logging the error text as before."""
import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.hitl_approval import ApprovalStatus
from services.agent_execution_service import AgentExecutionService, RunPausedForApproval

SECRET = "TOPSECRET-PROMPT-TEXT"


class TestRejectInPlaceAlwaysCloses:
    def _paused(self, chain):
        return RunPausedForApproval(chain, {"configurable": {"thread_id": "t", "checkpoint_id": "c"}})

    def _approval(self):
        return SimpleNamespace(id="ap1", actions=[{"name": "tool"}])

    @pytest.mark.asyncio
    @pytest.mark.parametrize("error", [RuntimeError("llm down"), TimeoutError("slow")])
    async def test_a_failing_resume_still_finishes_cancelled_and_propagates(self, error):
        chain = MagicMock()
        chain.ainvoke = AsyncMock(side_effect=error)
        chain.aget_state = AsyncMock(side_effect=RuntimeError("state unavailable"))  # best-effort close fails too
        db = MagicMock()
        with patch("services.agent_execution_service.approvals.finish") as finish, \
                patch("repositories.internal_chat_repository.set_local_timeouts") as timeouts:
            with pytest.raises(type(error)):
                await AgentExecutionService()._reject_in_place(self._paused(chain), self._approval(), db)
        finish.assert_called_once()
        args, kwargs = finish.call_args
        assert args[1:3] == ("ap1", ApprovalStatus.CANCELLED) and kwargs["reason"] == "channel_not_interactive"
        db.rollback.assert_called_once()
        timeouts.assert_called_once()  # a dead DB cannot block the loop for the pool timeout

    @pytest.mark.asyncio
    async def test_a_cancelled_resume_still_finishes_cancelled(self):
        import asyncio

        chain = MagicMock()
        chain.ainvoke = AsyncMock(side_effect=asyncio.CancelledError())
        with patch("services.agent_execution_service.approvals.finish") as finish, \
                patch("repositories.internal_chat_repository.set_local_timeouts"):
            with pytest.raises(asyncio.CancelledError):
                await AgentExecutionService()._reject_in_place(self._paused(chain), self._approval(), MagicMock())
        finish.assert_called_once()

    @pytest.mark.asyncio
    async def test_a_failing_finish_does_not_mask_the_original_error(self):
        chain = MagicMock()
        chain.ainvoke = AsyncMock(side_effect=RuntimeError("llm down"))
        with patch("services.agent_execution_service.approvals.finish", side_effect=ValueError("db gone SECRETDB")), \
                patch("repositories.internal_chat_repository.set_local_timeouts"), \
                patch("services.agent_execution_service.logger") as log:
            with pytest.raises(RuntimeError, match="llm down"):
                await AgentExecutionService()._reject_in_place(self._paused(chain), self._approval(), MagicMock())
        logged = " ".join(str(a) for call in log.error.call_args_list for a in call.args)
        assert "ValueError" in logged and "SECRETDB" not in logged, "the class name, not the text"

    @pytest.mark.asyncio
    async def test_unanswered_tool_calls_are_answered_with_a_rejection_when_the_resume_fails(self):
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        ai = AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": "c1"}, {"name": "t", "args": {}, "id": "c2"}])
        chain = MagicMock()
        chain.ainvoke = AsyncMock(side_effect=RuntimeError("down"))
        chain.aget_state = AsyncMock(return_value=SimpleNamespace(values={"messages": [
            HumanMessage(content="hi"), ai, ToolMessage(content="ok", tool_call_id="c1"),
        ]}))
        chain.aupdate_state = AsyncMock()
        approval = SimpleNamespace(id="ap1", actions=[{"name": "t", "action_id": "c2"}])
        with patch("services.agent_execution_service.approvals.finish"), \
                patch("repositories.internal_chat_repository.set_local_timeouts"):
            with pytest.raises(RuntimeError, match="down"):
                await AgentExecutionService()._reject_in_place(self._paused(chain), approval, MagicMock())
        update = chain.aupdate_state.await_args.args[1]["messages"]
        assert [m.tool_call_id for m in update] == ["c2"] and update[0].status == "error"

    @pytest.mark.asyncio
    async def test_gated_calls_get_the_rejection_text_and_others_a_neutral_one(self):
        from langchain_core.messages import AIMessage, HumanMessage

        from services.hitl_approval_service import NOT_INTERACTIVE_MESSAGE

        ai = AIMessage(content="", tool_calls=[{"name": "g", "args": {}, "id": "gated"}, {"name": "u", "args": {}, "id": "free"}])
        chain = MagicMock()
        chain.aget_state = AsyncMock(return_value=SimpleNamespace(values={"messages": [HumanMessage(content="hi"), ai]}))
        chain.aupdate_state = AsyncMock()
        await AgentExecutionService._close_unanswered_tool_calls(chain, {}, gated_ids={"gated"})
        texts = {m.tool_call_id: m.content for m in chain.aupdate_state.await_args.args[1]["messages"]}
        assert texts == {"gated": NOT_INTERACTIVE_MESSAGE, "free": "The tool call did not complete."}

    @pytest.mark.asyncio
    async def test_a_failing_finish_rolls_the_session_back_again(self):
        chain = MagicMock()
        chain.ainvoke = AsyncMock(side_effect=RuntimeError("llm down"))
        chain.aget_state = AsyncMock(side_effect=RuntimeError("x"))
        db = MagicMock()
        with patch("services.agent_execution_service.approvals.finish", side_effect=ValueError("db gone")), \
                patch("repositories.internal_chat_repository.set_local_timeouts"):
            with pytest.raises(RuntimeError, match="llm down"):
                await AgentExecutionService()._reject_in_place(self._paused(chain), self._approval(), db)
        assert db.rollback.call_count == 2  # before the timeouts, and after the failed finish

    @pytest.mark.asyncio
    async def test_a_hanging_state_read_is_bounded_and_never_raises(self):
        async def hang(*a, **k):
            await asyncio.sleep(3600)

        chain = MagicMock()
        chain.aget_state = hang
        with patch("services.agent_execution_service.asyncio.timeout", lambda s: asyncio.timeout(0.05)):
            await AgentExecutionService._close_unanswered_tool_calls(chain, {})

    @pytest.mark.asyncio
    async def test_success_finishes_once_without_rollback(self):
        chain = MagicMock()
        chain.ainvoke = AsyncMock()
        db = MagicMock()
        with patch("services.agent_execution_service.approvals.read_pause", AsyncMock(return_value=None)), \
                patch("services.agent_execution_service.approvals.finish") as finish:
            await AgentExecutionService()._reject_in_place(self._paused(chain), self._approval(), db)
        finish.assert_called_once()
        db.rollback.assert_not_called()


@pytest.fixture
def captured():
    """Records of the services' own loggers (they do not propagate to the root logger)."""
    records: list[logging.LogRecord] = []

    class _Handler(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Handler(logging.DEBUG)
    targets = [logging.getLogger("services.agent_execution_service"), logging.getLogger("services.agent_streaming_service")]
    for lg in targets:
        lg.addHandler(handler)
    yield records
    for lg in targets:
        lg.removeHandler(handler)


class TestNonChatTurnsLogAsBefore:
    """The playground / public API keep logging the provider text with its traceback."""

    @pytest.mark.asyncio
    async def test_execution_service_logs_the_error_text_with_traceback(self, captured):
        service = AgentExecutionService()
        service._prepare_turn = AsyncMock(side_effect=RuntimeError(f"provider echoes {SECRET}"))
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as raised:
            await service.execute_agent_chat_with_file_refs(1, "hi", db=MagicMock())
        record = next(r for r in captured if r.getMessage().startswith("Error executing agent chat"))
        assert record.getMessage() == f"Error executing agent chat: provider echoes {SECRET}"
        assert record.exc_info is not None
        assert raised.value.detail == f"Agent execution failed: provider echoes {SECRET}"

    @pytest.mark.asyncio
    async def test_streaming_service_logs_the_error_text_with_traceback(self, captured):
        from services.agent_streaming_service import AgentStreamingService

        service = AgentStreamingService(db=MagicMock())
        service.execution_service = MagicMock()
        service.execution_service._prepare_turn = AsyncMock(side_effect=RuntimeError(f"provider echoes {SECRET}"))
        events = [e async for e in service.stream_agent_events(agent_id=1, message="hi", db=MagicMock())]
        assert events[-1].type == "error"
        record = next(r for r in captured if r.getMessage().startswith("Error in streaming agent chat"))
        assert record.getMessage() == f"Error in streaming agent chat: provider echoes {SECRET}"
        assert record.exc_info is not None
