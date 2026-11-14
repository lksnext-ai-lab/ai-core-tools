"""Unit tests: rejection of the hidden internal chat agent on exposure surfaces (AD-6 points 4-9, 12-14).

Mock-based, no database.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Query, Session

from models.agent import AGENT_KIND_INTERNAL_CHAT, AGENT_KIND_STANDARD
from models.conversation import ConversationSource
from services.agent_execution_service import AgentExecutionService, AgentUnavailableError


def _agent(kind: str) -> MagicMock:
    agent = MagicMock()
    agent.kind = kind
    agent.is_internal_chat = kind == AGENT_KIND_INTERNAL_CHAT
    agent.is_frozen = False
    agent.app_id = 1
    return agent


def _service(agent) -> AgentExecutionService:
    """Service whose agent_service mimics the real default filter (internal agents need include_internal)."""
    service = AgentExecutionService.__new__(AgentExecutionService)
    service.agent_service = MagicMock()

    def _get_agent(db, agent_id, agent_type="basic", include_internal=False):
        if agent is not None and agent.is_internal_chat and not include_internal:
            return None
        return agent

    service.agent_service.get_agent.side_effect = _get_agent
    return service


def _cfg(app_id=1):
    """Minimal stand-in for a ResolvedChatConfig: only app_id is read before the conversation lookup."""
    from types import SimpleNamespace
    return SimpleNamespace(app_id=app_id)


class _Reached(Exception):
    """Sentinel raised by a patched next step to prove the choke point let the turn through."""


class TestPrepareTurnChokePoint:
    def test_internal_agent_without_turn_config_is_404(self):
        service = _service(_agent(AGENT_KIND_INTERNAL_CHAT))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(service._prepare_turn(agent_id=1, message="hi", db=MagicMock()))
        assert exc.value.status_code == 404
        assert exc.value.detail == "Agent not found"
        service.agent_service.get_agent.assert_called_once()
        assert service.agent_service.get_agent.call_args.kwargs["include_internal"] is True

    def test_frozen_internal_agent_without_turn_config_is_404_not_403(self):
        agent = _agent(AGENT_KIND_INTERNAL_CHAT)
        agent.is_frozen = True
        service = _service(agent)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(service._prepare_turn(agent_id=1, message="hi", db=MagicMock()))
        assert (exc.value.status_code, exc.value.detail) == (404, "Agent not found")

    def test_standard_agent_with_turn_config_is_404(self):
        service = _service(_agent(AGENT_KIND_STANDARD))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(service._prepare_turn(
                agent_id=1, message="hi", db=MagicMock(), conversation_id=3, turn_config=_cfg()
            ))
        assert exc.value.status_code == 404
        assert exc.value.detail == "Agent not found"

    def test_missing_agent_same_detail(self):
        service = _service(None)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(service._prepare_turn(agent_id=1, message="hi", db=MagicMock()))
        assert (exc.value.status_code, exc.value.detail) == (404, "Agent not found")

    def test_internal_agent_with_turn_config_passes_the_kind_check(self):
        """The conversation lookup is the first step after the choke point; it must see include_internal_chat."""
        service = _service(_agent(AGENT_KIND_INTERNAL_CHAT))
        with patch("services.conversation_service.ConversationService") as conv_svc:
            conv_svc.get_conversation.side_effect = _Reached
            with pytest.raises(_Reached):
                asyncio.run(service._prepare_turn(
                    agent_id=1, message="hi", db=MagicMock(), conversation_id=3,
                    user_context={"user_id": 1}, turn_config=_cfg(),
                ))
        assert conv_svc.get_conversation.call_args.kwargs["include_internal_chat"] is True

    def test_standard_agent_conversation_lookup_excludes_internal_chat(self):
        service = _service(_agent(AGENT_KIND_STANDARD))
        with patch("services.conversation_service.ConversationService") as conv_svc:
            conv_svc.get_conversation.side_effect = _Reached
            with pytest.raises(_Reached):
                asyncio.run(service._prepare_turn(
                    agent_id=1, message="hi", db=MagicMock(), conversation_id=3, user_context={"user_id": 1},
                ))
        assert conv_svc.get_conversation.call_args.kwargs["include_internal_chat"] is False

    def test_turn_config_without_conversation_never_auto_creates_one(self):
        service = _service(_agent(AGENT_KIND_INTERNAL_CHAT))
        with patch("services.conversation_service.ConversationService") as conv_svc:
            with pytest.raises(HTTPException) as exc:
                asyncio.run(service._prepare_turn(
                    agent_id=1, message="hi", db=MagicMock(), user_context={"user_id": 1}, turn_config=_cfg(),
                ))
        assert exc.value.status_code == 400
        conv_svc.create_conversation.assert_not_called()

    def test_reset_rejects_internal_agent(self):
        service = _service(_agent(AGENT_KIND_INTERNAL_CHAT))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(service.reset_agent_conversation(agent_id=1, user_context={"user_id": 1}, db=MagicMock()))
        assert (exc.value.status_code, exc.value.detail) == (404, "Agent not found")
        assert "include_internal" not in service.agent_service.get_agent.call_args.kwargs

    def test_history_of_internal_agent_is_empty_like_a_missing_agent(self):
        """get_conversation_history swallows errors into [] (existing behaviour): no history leaks."""
        internal = _service(_agent(AGENT_KIND_INTERNAL_CHAT))
        missing = _service(None)
        args = dict(agent_id=1, user_context={"user_id": 1}, db=MagicMock())
        assert asyncio.run(internal.get_conversation_history(**args)) == []
        assert asyncio.run(missing.get_conversation_history(**args)) == []


class TestConversationsRouter:
    def _call(self, fn_name, **kwargs):
        from routers.internal import conversations as router

        user = MagicMock()
        user.identity.id = "7"
        user.identity.email = "u@x.com"
        return asyncio.run(getattr(router, fn_name)(db=MagicMock(), current_user=user, **kwargs))

    @pytest.mark.parametrize("agent_state", ["internal", "missing"])
    def test_post_is_404_and_creates_nothing(self, agent_state):
        with patch("routers.internal.conversations.AgentService") as svc, patch(
            "routers.internal.conversations.ConversationService"
        ) as conv_svc:
            svc.return_value.get_agent.return_value = None  # the default lookup hides the internal agent
            with pytest.raises(HTTPException) as exc:
                self._call("create_conversation", agent_id=5, title=None)
            assert (exc.value.status_code, exc.value.detail) == (404, "Agent not found")
            assert svc.return_value.get_agent.call_args.kwargs.get("include_internal", False) is False
            conv_svc.create_conversation.assert_not_called()

    @pytest.mark.parametrize(
        "fn_name,service_method,extra",
        [
            ("get_conversation", "get_conversation", {}),
            ("update_conversation", "update_conversation", {"update_data": MagicMock()}),
            ("delete_conversation", "delete_conversation", {}),
        ],
    )
    def test_hidden_conversation_maps_to_404(self, fn_name, service_method, extra):
        """The service (default include_internal_chat=False) reports App Chat conversations as missing."""
        with patch("routers.internal.conversations.ConversationService") as conv_svc:
            setattr(conv_svc, service_method, AsyncMock(return_value=None) if fn_name == "delete_conversation"
                    else MagicMock(return_value=None))
            with pytest.raises(HTTPException) as exc:
                self._call(fn_name, conversation_id=3, **extra)
            assert (exc.value.status_code, exc.value.detail) == (404, "Conversation not found")
            assert "include_internal_chat" not in getattr(conv_svc, service_method).call_args.kwargs


class TestConversationServiceHidesInternalChat:
    def _sqls(self, include):
        from services.conversation_service import ConversationService

        sqls = []

        def rec(self_, *a, **kw):
            sqls.append(str(self_.statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})))
            return None

        with patch.object(Query, "first", rec):
            ConversationService.get_conversation(Session(), 3, {"user_id": 1}, include_internal_chat=include)
        return sqls[0]

    def test_default_excludes_by_source_and_owning_agent(self):
        sql = self._sqls(False)
        assert "INTERNAL_CHAT" in sql and "\"Agent\".kind = 'standard'" in sql

    def test_include_flag_lifts_the_filter(self):
        sql = self._sqls(True)
        assert "INTERNAL_CHAT" not in sql and "'standard'" not in sql

    def test_list_excludes_internal_by_default(self):
        from services.conversation_service import ConversationService

        sqls = []

        def rec_count(self_, *a, **kw):
            sqls.append(str(self_.statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})))
            return 0

        with patch.object(Query, "count", rec_count), patch.object(Query, "all", lambda self_: []):
            ConversationService.list_conversations(Session(), 5, {"user_id": 1})
        assert "INTERNAL_CHAT" in sqls[0] and "'standard'" in sqls[0]


class TestHitlResumeAgentUnavailable:
    def _run(self, exc):
        from models.hitl_approval import ApprovalChannel, ApprovalStatus
        from services import agent_execution_service as mod

        service = AgentExecutionService.__new__(AgentExecutionService)
        service.execute_agent_chat_with_file_refs = AsyncMock(side_effect=exc)
        resume = MagicMock()
        resume.approval.id = "appr-1"
        with patch.object(mod, "approvals") as approvals:
            approvals.ApprovalStaleError.code = "stale"
            approvals.ApprovalNotSupportedError.code = "unsupported"
            with pytest.raises(HTTPException):
                asyncio.run(service.resume_approval(MagicMock(), resume, {"user_id": 1}, ApprovalChannel.INTERNAL_SYNC))
        return approvals, ApprovalStatus

    def test_agent_not_found_cancels_terminally(self):
        approvals, status = self._run(AgentUnavailableError())
        approvals.release.assert_not_called()
        assert approvals.finish.call_args.args[2] == status.CANCELLED
        assert approvals.finish.call_args.kwargs["reason"] == "agent_unavailable"

    def test_same_detail_plain_404_still_releases(self):
        """Classification is by type, not by matching the detail string."""
        approvals, _ = self._run(HTTPException(status_code=404, detail="Agent not found"))
        approvals.release.assert_called_once()
        approvals.finish.assert_not_called()

    def test_server_error_still_releases(self):
        approvals, _ = self._run(HTTPException(status_code=500, detail="boom"))
        approvals.release.assert_called_once()
        approvals.finish.assert_not_called()


class TestHitlCancelIgnoresInternal:
    def test_internal_ids_are_dropped_with_warning(self):
        from services import hitl_approval_service as svc

        db = MagicMock()
        with patch.object(svc.AgentRepository, "get_internal_chat_ids", return_value={9}), patch.object(
            svc.HITLApprovalRepository, "list_open_ids_for_agents", return_value=[]
        ) as listing, patch.object(svc, "logger") as log:
            assert svc.cancel_pending_for_agents(db, [1, 9], "approval_rules_changed") == 0
        listing.assert_called_once_with(db, [1])
        log.warning.assert_called_once()


class TestSurfaceFiltersCompiled:
    """Every surface query carries the visible-agent predicate."""

    def _sql(self):
        sqls = []

        def _rec(self_, *a, **kw):
            sqls.append(str(self_.statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})))
            return None

        return sqls, _rec

    def test_scheduled_task_agent_lookup(self):
        from services.scheduled_task_service import ScheduledTaskService

        sqls, rec = self._sql()
        service = ScheduledTaskService.__new__(ScheduledTaskService)
        service.db = Session()
        with patch.object(Query, "one_or_none", rec), pytest.raises(ValueError, match="Agent not found"):
            service._agent(1, 1)
        assert '"Agent".kind = \'standard\'' in sqls[0]

    def test_mcp_server_tool_agents(self):
        from services.mcp_server_service import MCPServerService

        sqls, _ = self._sql()

        def rec_all(self_, *a, **kw):
            sqls.append(str(self_.statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})))
            return []

        with patch.object(Query, "all", rec_all):
            MCPServerService.get_tool_agents(Session(), 1)
        assert '"Agent".kind = \'standard\'' in sqls[0]

    def test_a2a_repository_queries(self):
        from repositories import a2a_agent_repository as repo

        captured = []
        db = MagicMock()
        db.execute.side_effect = lambda stmt: captured.append(
            str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        ) or MagicMock()
        repo.get_agent_for_app(db, 1, 2)
        repo.list_enabled_agents_for_app(db, 1)
        assert all('"Agent".kind = \'standard\'' in sql for sql in captured) and len(captured) == 2

    def test_metrics_check_agent_in_app(self):
        from services.metrics_query_service import MetricsQueryService

        sqls, rec = self._sql()
        with patch.object(Query, "first", rec), pytest.raises(HTTPException) as exc:
            MetricsQueryService.check_agent_in_app(Session(), 1, 2)
        assert exc.value.status_code == 404
        assert '"Agent".kind = \'standard\'' in sqls[0]


class TestStreamingResumeAgentUnavailable:
    def _drive(self, exc):
        from services.agent_streaming_service import AgentStreamingService

        service = AgentStreamingService()
        service.execution_service = MagicMock()
        service.execution_service._prepare_turn = AsyncMock(side_effect=exc)
        resume = MagicMock()
        resume.approval.id = "appr-1"

        async def _go():
            return [
                ev async for ev in service.stream_agent_events(
                    agent_id=1, message="", user_context={"user_id": 1}, conversation_id=3,
                    db=MagicMock(), resume=resume,
                )
            ]

        with patch("services.agent_streaming_service.approvals") as stream_appr, patch(
            "services.agent_execution_service.approvals"
        ) as exec_appr:
            events = asyncio.run(_go())
        return events, stream_appr, exec_appr

    def test_agent_unavailable_finishes_cancelled_and_does_not_release(self):
        from models.hitl_approval import ApprovalStatus

        events, stream_appr, exec_appr = self._drive(AgentUnavailableError())
        stream_appr.release.assert_not_called()
        exec_appr.release.assert_not_called()
        assert exec_appr.finish.call_args.args[2] == ApprovalStatus.CANCELLED
        assert exec_appr.finish.call_args.kwargs["reason"] == "agent_unavailable"
        assert events[-1].type == "error"

    def test_other_http_errors_still_release(self):
        events, stream_appr, exec_appr = self._drive(HTTPException(status_code=403, detail="Agent is frozen"))
        stream_appr.release.assert_called_once()
        exec_appr.finish.assert_not_called()
        assert events[-1].type == "error"


class TestMetricsHidesInternalAgent:
    def test_agent_dimension_carries_its_own_filter(self):
        from services.metrics_query_service import _dimension

        *_, extra = _dimension("agent")
        assert len(extra) == 1
        assert "'standard'" in str(extra[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        assert _dimension("app")[-1] == [] and _dimension("channel")[-1] == []

    def test_recent_errors_blank_the_internal_agent_identity(self):
        from services.metrics_query_service import MetricsQueryService, MetricsScope

        captured = []

        def rec(self_, *a, **kw):
            captured.append(str(self_.statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})))
            return []

        with patch.object(Query, "all", rec):
            MetricsQueryService.errors(Session(), MetricsScope(app_id=1), "24h")
        assert any("CASE WHEN" in sql and "'internal_chat'" in sql for sql in captured)
