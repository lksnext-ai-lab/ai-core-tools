"""
Unit tests for AgentExecutionService.execute_agent_chat().

All external dependencies are mocked (agent_service, session_service,
agent_execution_repo, _execute_agent_async, parse_agent_response) so tests
run without a database, LLM connection, or LangGraph.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import HTTPException

from services.agent_execution_service import AgentExecutionService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_agent(
    agent_id: int = 1,
    has_memory: bool = False,
    agent_type: str = "agent",
    name: str = "Test Agent",
) -> MagicMock:
    """Create a minimal Agent mock."""
    agent = MagicMock()
    agent.agent_id = agent_id
    agent.name = name
    agent.type = agent_type
    agent.has_memory = has_memory
    agent.silo_id = None
    agent.output_parser_id = None
    agent.request_count = 0
    return agent


def make_service(
    agent=None,
    fresh_agent=None,
    session=None,
    llm_response: str = "Hello from the agent",
) -> AgentExecutionService:
    """
    Build an AgentExecutionService with all external collaborators mocked.
    """
    svc = AgentExecutionService.__new__(AgentExecutionService)
    svc.db = MagicMock()

    # Mock agent_service
    svc.agent_service = MagicMock()
    svc.agent_service.get_agent.return_value = agent

    # Mock session_service
    svc.session_service = MagicMock()
    mock_session = session or MagicMock(id="test-session-id")
    svc.session_service.get_user_session = AsyncMock(return_value=mock_session)
    svc.session_service.touch_session = AsyncMock()

    # Mock agent_execution_repo
    svc.agent_execution_repo = MagicMock()
    svc.agent_execution_repo.get_agent_with_relationships.return_value = (
        fresh_agent or agent
    )

    return svc, llm_response


# ---------------------------------------------------------------------------
# Agent not found
# ---------------------------------------------------------------------------


class TestAgentNotFound:
    @pytest.mark.asyncio
    async def test_raises_404_when_agent_not_found(self):
        svc, _ = make_service(agent=None)
        with pytest.raises(HTTPException) as exc_info:
            await svc.execute_agent_chat(
                agent_id=99, message="hello", db=MagicMock()
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_raises_404_when_fresh_agent_not_found(self):
        """
        agent_service.get_agent succeeds but agent_execution_repo returns None
        (could happen in a race condition — agent deleted between checks).
        """
        agent = make_agent(agent_id=1)
        svc, _ = make_service(agent=agent, fresh_agent=None)

        with (
            patch.object(svc, "_validate_agent_access", new=AsyncMock()),
            patch.object(svc, "_prepare_message_with_files", return_value=("msg", [])),
        ):
            svc.agent_execution_repo.get_agent_with_relationships.return_value = None
            with pytest.raises(HTTPException) as exc_info:
                await svc.execute_agent_chat(
                    agent_id=1, message="hello", db=MagicMock()
                )
            assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Successful execution — no memory, no files
# ---------------------------------------------------------------------------


class TestSuccessfulExecution:
    @pytest.mark.asyncio
    async def test_returns_structured_response(self):
        agent = make_agent(agent_id=1, has_memory=False)
        svc, _ = make_service(agent=agent)

        with (
            patch.object(svc, "_validate_agent_access", new=AsyncMock()),
            patch.object(svc, "_prepare_message_with_files", return_value=("hello", [])),
            patch.object(svc, "_execute_agent_async", new=AsyncMock(return_value="Agent reply")),
            patch.object(svc, "_update_request_count"),
            patch("services.agent_execution_service.parse_agent_response", return_value="Agent reply"),
        ):
            result = await svc.execute_agent_chat(
                agent_id=1, message="hello", db=MagicMock()
            )

        assert result["response"] == "Agent reply"
        assert result["agent_id"] == 1
        assert "metadata" in result

    @pytest.mark.asyncio
    async def test_metadata_contains_expected_keys(self):
        agent = make_agent(agent_id=1, has_memory=False)
        svc, _ = make_service(agent=agent)

        with (
            patch.object(svc, "_validate_agent_access", new=AsyncMock()),
            patch.object(svc, "_prepare_message_with_files", return_value=("hello", [])),
            patch.object(svc, "_execute_agent_async", new=AsyncMock(return_value="ok")),
            patch.object(svc, "_update_request_count"),
            patch("services.agent_execution_service.parse_agent_response", return_value="ok"),
        ):
            result = await svc.execute_agent_chat(
                agent_id=1, message="hello", db=MagicMock()
            )

        meta = result["metadata"]
        assert "agent_name" in meta
        assert "agent_type" in meta
        assert "files_processed" in meta
        assert "has_memory" in meta

    @pytest.mark.asyncio
    async def test_files_processed_is_zero_without_attachments(self):
        agent = make_agent()
        svc, _ = make_service(agent=agent)

        with (
            patch.object(svc, "_validate_agent_access", new=AsyncMock()),
            patch.object(svc, "_prepare_message_with_files", return_value=("hello", [])),
            patch.object(svc, "_execute_agent_async", new=AsyncMock(return_value="ok")),
            patch.object(svc, "_update_request_count"),
            patch("services.agent_execution_service.parse_agent_response", return_value="ok"),
        ):
            result = await svc.execute_agent_chat(
                agent_id=1, message="hello", db=MagicMock()
            )

        assert result["metadata"]["files_processed"] == 0


# ---------------------------------------------------------------------------
# Memory-enabled agents
# ---------------------------------------------------------------------------


class TestMemoryEnabledAgent:
    @pytest.mark.asyncio
    async def test_gets_session_for_memory_agent(self):
        agent = make_agent(agent_id=1, has_memory=True)
        svc, _ = make_service(agent=agent)

        with (
            patch.object(svc, "_validate_agent_access", new=AsyncMock()),
            patch.object(svc, "_prepare_message_with_files", return_value=("hello", [])),
            patch.object(svc, "_execute_agent_async", new=AsyncMock(return_value="ok")),
            patch.object(svc, "_update_request_count"),
            patch("services.agent_execution_service.parse_agent_response", return_value="ok"),
        ):
            await svc.execute_agent_chat(
                agent_id=1,
                message="hello",
                user_context={"user_id": 5},
                db=MagicMock(),
            )

        svc.session_service.get_user_session.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_does_not_get_session_for_memoryless_agent(self):
        agent = make_agent(agent_id=1, has_memory=False)
        svc, _ = make_service(agent=agent)

        with (
            patch.object(svc, "_validate_agent_access", new=AsyncMock()),
            patch.object(svc, "_prepare_message_with_files", return_value=("hello", [])),
            patch.object(svc, "_execute_agent_async", new=AsyncMock(return_value="ok")),
            patch.object(svc, "_update_request_count"),
            patch("services.agent_execution_service.parse_agent_response", return_value="ok"),
        ):
            await svc.execute_agent_chat(
                agent_id=1, message="hello", db=MagicMock()
            )

        svc.session_service.get_user_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_touches_session_after_execution(self):
        agent = make_agent(agent_id=1, has_memory=True)
        mock_session = MagicMock(id="sess-abc")
        svc, _ = make_service(agent=agent, session=mock_session)

        with (
            patch.object(svc, "_validate_agent_access", new=AsyncMock()),
            patch.object(svc, "_prepare_message_with_files", return_value=("hello", [])),
            patch.object(svc, "_execute_agent_async", new=AsyncMock(return_value="ok")),
            patch.object(svc, "_update_request_count"),
            patch("services.agent_execution_service.parse_agent_response", return_value="ok"),
        ):
            await svc.execute_agent_chat(
                agent_id=1, message="hello", db=MagicMock()
            )

        svc.session_service.touch_session.assert_awaited_once_with("sess-abc")


# ---------------------------------------------------------------------------
# File processing
# ---------------------------------------------------------------------------


class TestFileProcessing:
    @pytest.mark.asyncio
    async def test_process_files_called_when_files_provided(self):
        agent = make_agent()
        svc, _ = make_service(agent=agent)

        mock_files = [MagicMock()]

        with (
            patch.object(svc, "_validate_agent_access", new=AsyncMock()),
            patch.object(
                svc,
                "_process_files_for_agent",
                new=AsyncMock(return_value=[{"filename": "file.pdf", "content": "text"}]),
            ) as mock_process,
            patch.object(
                svc,
                "_prepare_message_with_files",
                return_value=("hello + file.pdf: text", []),
            ),
            patch.object(svc, "_execute_agent_async", new=AsyncMock(return_value="ok")),
            patch.object(svc, "_update_request_count"),
            patch("services.agent_execution_service.parse_agent_response", return_value="ok"),
        ):
            result = await svc.execute_agent_chat(
                agent_id=1, message="hello", files=mock_files, db=MagicMock()
            )

        mock_process.assert_awaited_once()
        assert result["metadata"]["files_processed"] == 1


# ---------------------------------------------------------------------------
# Request count
# ---------------------------------------------------------------------------


class TestRequestCount:
    @pytest.mark.asyncio
    async def test_update_request_count_is_called(self):
        agent = make_agent()
        svc, _ = make_service(agent=agent)

        with (
            patch.object(svc, "_validate_agent_access", new=AsyncMock()),
            patch.object(svc, "_prepare_message_with_files", return_value=("hi", [])),
            patch.object(svc, "_execute_agent_async", new=AsyncMock(return_value="ok")),
            patch.object(svc, "_update_request_count") as mock_update,
            patch("services.agent_execution_service.parse_agent_response", return_value="ok"),
        ):
            await svc.execute_agent_chat(agent_id=1, message="hi", db=MagicMock())

        mock_update.assert_called_once()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_wraps_unexpected_exceptions_in_500(self):
        agent = make_agent()
        svc, _ = make_service(agent=agent)

        with (
            patch.object(svc, "_validate_agent_access", new=AsyncMock()),
            patch.object(svc, "_prepare_message_with_files", return_value=("hi", [])),
            patch.object(
                svc,
                "_execute_agent_async",
                new=AsyncMock(side_effect=RuntimeError("LLM timeout")),
            ),
            patch.object(svc, "_update_request_count"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await svc.execute_agent_chat(agent_id=1, message="hi", db=MagicMock())

        assert exc_info.value.status_code == 500
        assert "Agent execution failed" in exc_info.value.detail
