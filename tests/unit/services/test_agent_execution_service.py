"""
Unit tests for AgentExecutionService.

Tests cover execute_agent_chat_with_file_refs (the primary execution path),
_prepare_turn, _finalize_turn, and the file-snapshotting behaviour.

All external dependencies are mocked so tests run without a database, LLM
connection, or LangGraph.
"""

import os

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import HTTPException

from services.agent_execution_service import AgentExecutionService
from services.agent_execution_context import AgentExecutionContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_agent(
    agent_id: int = 1,
    has_memory: bool = False,
    agent_type: str = "agent",
    name: str = "Test Agent",
    is_frozen: bool = False,
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
    agent.is_frozen = is_frozen  # SaaS mode: must be explicitly False to avoid MagicMock truthiness
    agent.ai_service = None
    agent.a2a_config = None
    agent.prompt_template = MagicMock()
    agent.prompt_template.format.return_value = "formatted message"
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


def make_context(agent=None, fresh_agent=None, **kwargs) -> AgentExecutionContext:
    """Build a minimal AgentExecutionContext for _finalize_turn tests."""
    _agent = agent or make_agent()
    _fresh_agent = fresh_agent or _agent
    defaults = dict(
        agent_id=1,
        agent=_agent,
        fresh_agent=_fresh_agent,
        enhanced_message="hello",
        image_files=[],
        session=None,
        conversation=None,
        effective_conv_id=None,
        session_id_for_cache=None,
        working_dir=None,
        pre_existing_files=set(),
        processed_files=[],
        search_params=None,
        user_context=None,
    )
    defaults.update(kwargs)
    return AgentExecutionContext(**defaults)


# ---------------------------------------------------------------------------
# Agent not found — _prepare_turn raises 404
# ---------------------------------------------------------------------------


class TestAgentNotFound:
    @pytest.mark.asyncio
    async def test_raises_404_when_agent_not_found(self):
        svc, _ = make_service(agent=None)
        with pytest.raises(HTTPException) as exc_info:
            await svc.execute_agent_chat_with_file_refs(
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
            patch("services.agent_execution_service.get_app_config",
                  return_value={"TMP_BASE_FOLDER": "/tmp"}),
        ):
            svc.agent_execution_repo.get_agent_with_relationships.return_value = None
            with pytest.raises(HTTPException) as exc_info:
                await svc.execute_agent_chat_with_file_refs(
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

        ctx = make_context(agent=agent)

        with (
            patch.object(svc, "_prepare_turn", new=AsyncMock(return_value=ctx)),
            patch.object(svc, "_execute_agent_async", new=AsyncMock(return_value="Agent reply")),
            patch.object(svc, "_finalize_turn", new=AsyncMock(return_value={
                "response": "Agent reply",
                "agent_id": 1,
                "conversation_id": None,
                "metadata": {"agent_name": "Test Agent", "agent_type": "agent",
                             "files_processed": 0, "has_memory": False},
                "parsed_response": "Agent reply",
                "effective_conv_id": None,
                "files_data": [],
            })),
        ):
            result = await svc.execute_agent_chat_with_file_refs(
                agent_id=1, message="hello", db=MagicMock()
            )

        assert result["response"] == "Agent reply"
        assert result["agent_id"] == 1
        assert "metadata" in result

    @pytest.mark.asyncio
    async def test_metadata_contains_expected_keys(self):
        agent = make_agent(agent_id=1, has_memory=False)
        svc, _ = make_service(agent=agent)

        ctx = make_context(agent=agent)

        with (
            patch.object(svc, "_prepare_turn", new=AsyncMock(return_value=ctx)),
            patch.object(svc, "_execute_agent_async", new=AsyncMock(return_value="ok")),
            patch.object(svc, "_finalize_turn", new=AsyncMock(return_value={
                "response": "ok",
                "agent_id": 1,
                "conversation_id": None,
                "metadata": {"agent_name": "Test Agent", "agent_type": "agent",
                             "files_processed": 0, "has_memory": False},
                "parsed_response": "ok",
                "effective_conv_id": None,
                "files_data": [],
            })),
        ):
            result = await svc.execute_agent_chat_with_file_refs(
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

        ctx = make_context(agent=agent, processed_files=[])

        with (
            patch.object(svc, "_prepare_turn", new=AsyncMock(return_value=ctx)),
            patch.object(svc, "_execute_agent_async", new=AsyncMock(return_value="ok")),
            patch.object(svc, "_finalize_turn", new=AsyncMock(return_value={
                "response": "ok",
                "agent_id": 1,
                "conversation_id": None,
                "metadata": {"agent_name": "Test Agent", "agent_type": "agent",
                             "files_processed": 0, "has_memory": False},
                "parsed_response": "ok",
                "effective_conv_id": None,
                "files_data": [],
            })),
        ):
            result = await svc.execute_agent_chat_with_file_refs(
                agent_id=1, message="hello", db=MagicMock()
            )

        assert result["metadata"]["files_processed"] == 0

    @pytest.mark.asyncio
    async def test_routes_a2a_agents_to_a2a_executor(self):
        agent = make_agent(agent_id=1, has_memory=False)
        agent.a2a_config = MagicMock(card_url="https://example.com/.well-known/agent-card.json")
        svc, _ = make_service(agent=agent)

        with patch("services.agent_execution_service.A2AExecutorService.execute", new=AsyncMock(return_value="Remote reply")) as mock_execute:
            result = await svc._execute_agent_async(
                agent,
                "hello",
                user_context={"user_id": 1},
            )

        assert result == "Remote reply"
        mock_execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# Memory-enabled agents — tested via _prepare_turn
# ---------------------------------------------------------------------------


class TestMemoryEnabledAgent:
    @pytest.mark.asyncio
    async def test_gets_session_for_memory_agent(self):
        agent = make_agent(agent_id=1, has_memory=True)
        svc, _ = make_service(agent=agent)

        ctx = make_context(agent=agent, session=MagicMock(id="sess"))

        with (
            patch.object(svc, "_prepare_turn", new=AsyncMock(return_value=ctx)) as mock_prepare,
            patch.object(svc, "_execute_agent_async", new=AsyncMock(return_value="ok")),
            patch.object(svc, "_finalize_turn", new=AsyncMock(return_value={
                "response": "ok", "agent_id": 1, "conversation_id": None,
                "metadata": {}, "parsed_response": "ok",
                "effective_conv_id": None, "files_data": [],
            })),
        ):
            await svc.execute_agent_chat_with_file_refs(
                agent_id=1, message="hello", user_context={"user_id": 5}, db=MagicMock()
            )

        mock_prepare.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_touches_session_after_execution(self):
        agent = make_agent(agent_id=1, has_memory=True)
        mock_session = MagicMock(id="sess-abc")
        svc, _ = make_service(agent=agent, session=mock_session)

        ctx = make_context(agent=agent, session=mock_session)

        with (
            patch.object(svc, "_prepare_turn", new=AsyncMock(return_value=ctx)),
            patch.object(svc, "_execute_agent_async", new=AsyncMock(return_value="ok")),
            patch.object(svc, "_finalize_turn", new=AsyncMock(return_value={
                "response": "ok", "agent_id": 1, "conversation_id": None,
                "metadata": {}, "parsed_response": "ok",
                "effective_conv_id": None, "files_data": [],
            })) as mock_finalize,
        ):
            await svc.execute_agent_chat_with_file_refs(
                agent_id=1, message="hello", db=MagicMock()
            )

        mock_finalize.assert_awaited_once()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_wraps_unexpected_exceptions_in_500(self):
        agent = make_agent()
        svc, _ = make_service(agent=agent)

        ctx = make_context(agent=agent)

        with (
            patch.object(svc, "_prepare_turn", new=AsyncMock(return_value=ctx)),
            patch.object(
                svc,
                "_execute_agent_async",
                new=AsyncMock(side_effect=RuntimeError("LLM timeout")),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await svc.execute_agent_chat_with_file_refs(
                    agent_id=1, message="hi", db=MagicMock()
                )

        assert exc_info.value.status_code == 500
        assert "Agent execution failed" in exc_info.value.detail


# ---------------------------------------------------------------------------
# File snapshotting — only newly created files are registered
# ---------------------------------------------------------------------------


class TestFileSnapshotting:
    @pytest.mark.asyncio
    async def test_pre_existing_files_excluded_from_sync(self, tmp_path):
        """
        Files that existed before execution are passed as exclude_filenames
        so sync_output_files does not register them as new output.
        """
        agent = make_agent(agent_id=1, has_memory=False)
        svc, _ = make_service(agent=agent)

        # Create a working dir with a pre-existing file
        working_dir = tmp_path / "conversations" / "42"
        working_dir.mkdir(parents=True)
        (working_dir / "old_report.pdf").write_text("stale")

        mock_sync = AsyncMock(return_value=[])

        with (
            patch.object(svc, "_validate_agent_access", new=AsyncMock()),
            patch.object(svc, "_prepare_message_with_files", return_value=("hello", [])),
            patch.object(svc, "_execute_agent_async", new=AsyncMock(return_value="ok")),
            patch.object(svc, "_update_request_count"),
            patch("tools.agentTools.parse_agent_response", return_value="ok"),
            patch("services.agent_execution_service.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}),
            patch("services.agent_execution_service.FileManagementService") as mock_fms_cls,
            patch("os.path.isdir", side_effect=lambda p: p == str(working_dir) or os.path.isdir(p)),
            patch("os.listdir", side_effect=lambda p: ["old_report.pdf"] if p == str(working_dir) else os.listdir(p)),
        ):
            mock_fms_cls.return_value.sync_output_files = mock_sync

            await svc.execute_agent_chat_with_file_refs(
                agent_id=1,
                message="hello",
                conversation_id=42,
                db=MagicMock(),
            )

            mock_sync.assert_awaited_once()
            call_kwargs = mock_sync.call_args.kwargs if mock_sync.call_args.kwargs else {}
            if not call_kwargs:
                # positional or keyword — check both forms
                call_kwargs = dict(zip(
                    ["working_dir", "agent_id", "user_context", "conversation_id", "exclude_filenames"],
                    mock_sync.call_args.args,
                ))
                call_kwargs.update(mock_sync.call_args.kwargs)
            assert "old_report.pdf" in call_kwargs["exclude_filenames"]

    @pytest.mark.asyncio
    async def test_new_files_trigger_inject_markers(self, tmp_path):
        """
        When sync_output_files returns new files, _inject_file_markers is called.
        """
        agent = make_agent(agent_id=1, has_memory=False)
        svc, _ = make_service(agent=agent)

        mock_file_ref = MagicMock()
        mock_file_ref.file_id = "new_123"
        mock_file_ref.filename = "chart.png"
        mock_sync = AsyncMock(return_value=[mock_file_ref])

        with (
            patch.object(svc, "_validate_agent_access", new=AsyncMock()),
            patch.object(svc, "_prepare_message_with_files", return_value=("hello", [])),
            patch.object(svc, "_execute_agent_async", new=AsyncMock(return_value="ok")),
            patch.object(svc, "_update_request_count"),
            patch("tools.agentTools.parse_agent_response", return_value="ok"),
            patch("services.agent_execution_service.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}),
            patch("services.agent_execution_service.FileManagementService") as mock_fms_cls,
            patch("services.agent_execution_service._inject_file_markers", return_value="ok with files") as mock_inject,
            patch("os.path.isdir", return_value=False),
        ):
            mock_fms_cls.return_value.sync_output_files = mock_sync

            await svc.execute_agent_chat_with_file_refs(
                agent_id=1,
                message="hello",
                conversation_id=42,
                db=MagicMock(),
            )

            mock_inject.assert_called_once_with("ok", [mock_file_ref])
