"""Unit tests: per-turn ResolvedChatConfig threading (step_006). Mock-based, no DB."""
import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.hitl_approval import INTERACTIVE_CHANNELS, ApprovalChannel
from services import hitl_approval_service as approvals
from services.agent_execution_context import AgentExecutionContext
from services.agent_execution_service import AgentExecutionService, last_ai_message_id
from services.agent_metrics_recorder import build_metrics_payload
from services.internal_chat.resolved_config import ResolvedChatConfig


def _config(app_id=1, service_app_id=None):
    svc = MagicMock(service_id=77, provider="Anthropic", description="claude-x", app_id=service_app_id)
    return ResolvedChatConfig(
        app_id=app_id, ai_service=svc, ai_service_id=77, ai_service_name="S",
        ai_service_is_system=service_app_id is None, ai_service_provider="Anthropic",
        ai_service_model="claude-x",
        silo=None, silo_id=None, silo_name=None, skills=(), skill_ids=(), skill_names=(),
        mcp_connections=(), mcp_config_ids=(), mcp_config_names=(), system_prompt="p",
    )


def _agent(internal):
    a = MagicMock()
    a.is_internal_chat = internal
    a.is_frozen = False
    a.name, a.type, a.has_memory, a.app_id = "A", "agent", True, 1
    return a


def _ctx(internal, turn_config=None, _unused=None):
    agent = _agent(internal)
    fresh = _agent(internal)
    fresh.ai_service = MagicMock(app_id=None)
    return AgentExecutionContext(
        agent_id=1, agent=agent, fresh_agent=fresh, enhanced_message="m", image_files=[],
        conversation=None, effective_conv_id=5, user_context={"user_id": 3},
        turn_config=turn_config,
    )


def _svc():
    svc = AgentExecutionService.__new__(AgentExecutionService)
    svc.session_service = MagicMock()
    svc._update_request_count = MagicMock()
    return svc


def _payload(**kw):
    return build_metrics_payload(
        event_id="e", user_context={"caller_type_override": "INTERNAL_CHAT"},
        started_at=datetime.utcnow(), finished_at=None, duration_ms=1, status="SUCCESS",
        error_code=None, error_message=None, result=None, image_files=[], message="x", **kw,
    )["event"]


class TestMetrics:
    def test_override_service_is_recorded(self):
        fresh = SimpleNamespace(app_id=1, agent_id=9, service_id=None, ai_service=None, output_parser_id=None)
        ev = _payload(fresh_agent=fresh, ai_service_override=_config().ai_service)
        assert (ev["ai_service_id"], ev["provider"], ev["model_name"]) == (77, "Anthropic", "claude-x")
        assert ev["caller_type"] == "INTERNAL_CHAT"

    def test_without_override_uses_agent_service(self):
        own = SimpleNamespace(provider="OpenAI", description="gpt")
        fresh = SimpleNamespace(app_id=1, agent_id=9, service_id=4, ai_service=own, output_parser_id=None)
        ev = _payload(fresh_agent=fresh)
        assert (ev["ai_service_id"], ev["provider"]) == (4, "OpenAI")


class _FakeDb:
    """Session double: real savepoint semantics for the hook (rollback recorded, exception propagates)."""

    def __init__(self):
        self.events = []

    def begin_nested(self):
        from contextlib import contextmanager

        @contextmanager
        def _sp():
            self.events.append("savepoint")
            try:
                yield
            except BaseException:
                self.events.append("savepoint_rollback")
                raise
            self.events.append("savepoint_release")

        return _sp()

    def commit(self):
        self.events.append("commit")

    def rollback(self):
        self.events.append("rollback")


class _Exploding:
    """An expired/deleted ORM object: any attribute access raises (like ObjectDeletedError)."""

    def __getattribute__(self, name):
        raise RuntimeError("ObjectDeletedError")


class TestFinalize:
    def _run(self, ctx, db=None, hook=None, increment=None):
        with patch("services.agent_execution_service.FileManagementService"), \
             patch("services.agent_execution_service._ensure_local_workspace_layout"), \
             patch("tools.agentTools.parse_agent_response", return_value="ok"):
            svc = _svc()
            res = asyncio.run(svc._finalize_turn(
                ctx, "ok", db, assistant_message_id="m-1", on_turn_completed=hook))
        return svc, res

    def test_internal_agent_never_updates_request_count_and_uses_turn_service(self):
        ctx = _ctx(True, _config(service_app_id=5))
        ctx.fresh_agent.ai_service = MagicMock(app_id=None)
        with patch("services.usage_tracking_service.UsageTrackingService.record_system_llm_call") as rec:
            svc, res = self._run(ctx, db=MagicMock())
        svc._update_request_count.assert_not_called()
        assert res["assistant_message_id"] == "m-1"
        rec.assert_not_called()

    def test_quota_bills_turn_service_when_system(self):
        ctx = _ctx(True, _config(service_app_id=None))
        ctx.fresh_agent.ai_service = MagicMock(app_id=5)
        with patch("services.usage_tracking_service.UsageTrackingService.record_system_llm_call") as rec:
            self._run(ctx, db=MagicMock())
        rec.assert_called_once()

    def test_deleted_service_object_does_not_break_finalize_or_metrics(self):
        cfg = _config(service_app_id=None)
        object.__setattr__(cfg, "ai_service", _Exploding())  # frozen+slots: bypass for the test
        ctx = _ctx(True, cfg)
        with patch("services.usage_tracking_service.UsageTrackingService.record_system_llm_call") as rec:
            _, res = self._run(ctx, db=MagicMock())
        rec.assert_called_once()
        assert res["response"] == "ok"
        fresh = SimpleNamespace(app_id=1, agent_id=9, service_id=None, ai_service=None, output_parser_id=None)
        ev = _payload(fresh_agent=fresh, ai_service_override=cfg.metrics_service())
        assert (ev["ai_service_id"], ev["provider"], ev["model_name"]) == (77, "Anthropic", "claude-x")

    def test_standard_agent_still_updates_count_and_has_no_chat_keys(self):
        svc, res = self._run(_ctx(False))
        svc._update_request_count.assert_called_once()
        assert "assistant_message_id" not in res and "turn" not in res

    def test_hook_gets_plain_event_inside_savepoint_and_is_committed(self):
        db = _FakeDb()
        seen = []

        async def hook(event):
            seen.append(event)
            db.events.append("hook")
            return {"turn_index": 1}

        _, res = self._run(_ctx(True, _config(), hook), db=db, hook=hook)
        assert len(seen) == 1
        assert (seen[0].conversation_id, seen[0].assistant_message_id) == (5, "m-1")
        assert res["turn"] == {"turn_index": 1}
        assert db.events[-4:] == ["savepoint", "hook", "savepoint_release", "commit"]

    def test_hook_failure_rolls_back_only_the_savepoint_and_keeps_later_result(self):
        db = _FakeDb()

        async def boom(event):
            raise RuntimeError("x")

        with patch("services.usage_tracking_service.UsageTrackingService.record_system_llm_call") as rec:
            ctx = _ctx(True, _config(service_app_id=None), boom)
            ctx.fresh_agent.ai_service = MagicMock(app_id=None)
            _, res = self._run(ctx, db=db, hook=boom)
        rec.assert_called_once()  # usage increment ran before the hook
        assert res["response"] == "ok" and res["turn"] is None
        # earlier writes committed BEFORE the savepoint; then savepoint rolled back, tx ended
        assert db.events.index("commit") < db.events.index("savepoint")
        assert db.events.index("savepoint_rollback") < db.events.index("rollback")

    def test_cancelled_hook_rolls_back_savepoint_and_propagates(self):
        db = _FakeDb()

        async def cancelled(event):
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            self._run(_ctx(True, _config()), db=db, hook=cancelled)
        assert "savepoint_rollback" in db.events and "rollback" in db.events

    def test_hung_hook_times_out_and_does_not_fail_the_turn(self):
        db = _FakeDb()

        async def hang(event):
            await asyncio.sleep(5)

        with patch("services.agent_execution_service.HOOK_TIMEOUT_S", 0.05):
            _, res = self._run(_ctx(True, _config()), db=db, hook=hang)
        assert res["response"] == "ok" and res["turn"] is None
        assert "savepoint_rollback" in db.events

    def test_non_json_turn_is_dropped_with_warning(self, caplog):
        async def bad(event):
            return {"x": object()}

        _, res = self._run(_ctx(True, _config()), db=_FakeDb(), hook=bad)
        assert res["turn"] is None

    def test_no_hook_gives_no_turn(self):
        _, res = self._run(_ctx(True, _config()), db=_FakeDb())
        assert res["turn"] is None


class TestLastAiMessageId:
    def _m(self, type_, id_, content="x", tool_calls=None):
        return SimpleNamespace(type=type_, id=id_, content=content, tool_calls=tool_calls or [])

    def test_prefers_last_answer_over_tool_call_message(self):
        msgs = [self._m("ai", "a1"), self._m("ai", "a2", content="", tool_calls=[{"name": "t"}]),
                self._m("tool", "t1")]
        assert last_ai_message_id({"messages": msgs}) == "a1"

    def test_several_ai_messages_takes_last_answer(self):
        assert last_ai_message_id({"messages": [self._m("ai", "a1"), self._m("ai", "a2")]}) == "a2"

    def test_falls_back_to_last_ai_with_id_when_only_tool_calls(self):
        msgs = [self._m("ai", "a1", content="", tool_calls=[{"name": "t"}]), self._m("tool", "t1")]
        assert last_ai_message_id({"messages": msgs}) == "a1"

    def test_current_turn_only_ignores_earlier_turns(self):
        msgs = [self._m("human", "h1"), self._m("ai", "old"), self._m("human", "h2"),
                self._m("ai", "new-empty", content="")]
        assert last_ai_message_id({"messages": msgs}) == "old"  # whole thread: older answer wins
        assert last_ai_message_id({"messages": msgs}, current_turn_only=True) == "new-empty"
        assert last_ai_message_id({"messages": msgs[:3]}, current_turn_only=True) is None

    def test_no_id_or_no_ai_or_structured_response_only(self):
        assert last_ai_message_id({"messages": [self._m("ai", None)]}) is None
        assert last_ai_message_id({"messages": [self._m("human", "h")]}) is None
        assert last_ai_message_id({"structured_response": object()}) is None
        assert last_ai_message_id("text") is None and last_ai_message_id(None) is None


class TestPrepareTurnGuards:
    def _svc(self, agent):
        svc = AgentExecutionService.__new__(AgentExecutionService)
        svc.agent_service = MagicMock(get_agent=MagicMock(return_value=agent))
        svc.session_service = MagicMock()
        return svc

    def test_cross_tenant_config_is_404_before_side_effects(self):
        from services.agent_execution_service import AgentUnavailableError
        agent = _agent(True)
        agent.app_id = 1
        svc = self._svc(agent)
        with patch("services.conversation_service.ConversationService.get_conversation") as g:
            with pytest.raises(AgentUnavailableError):
                asyncio.run(svc._prepare_turn(agent_id=1, message="m", conversation_id=5, db=MagicMock(),
                                              user_context={"app_id": 1}, turn_config=_config(app_id=2)))
            with pytest.raises(AgentUnavailableError):
                asyncio.run(svc._prepare_turn(agent_id=1, message="m", conversation_id=5, db=MagicMock(),
                                              user_context={"app_id": 2}, turn_config=_config(app_id=1)))
        g.assert_not_called()

    def test_conversation_without_session_id_raises(self):
        from services.internal_chat.resolved_config import InternalChatSessionError
        agent = _agent(True)
        agent.app_id = 1
        svc = self._svc(agent)
        conv = MagicMock(conversation_id=5, session_id=None)
        with patch("services.conversation_service.ConversationService.get_conversation", return_value=conv):
            with pytest.raises(InternalChatSessionError):
                asyncio.run(svc._prepare_turn(agent_id=1, message="m", conversation_id=5, db=MagicMock(),
                                              user_context={"app_id": 1}, turn_config=_config(app_id=1)))


class TestSyncEntryPoint:
    def _run(self, exc, turn_config):
        svc = _svc()
        svc.agent_service = MagicMock()
        svc._prepare_turn = AsyncMock(side_effect=exc)
        return asyncio.run(svc.execute_agent_chat_with_file_refs(
            agent_id=1, message="m", conversation_id=5, db=MagicMock(),
            user_context={"user_id": 1}, turn_config=turn_config,
            channel=ApprovalChannel.INTERNAL_CHAT if turn_config is not None else ApprovalChannel.INTERNAL_SYNC))

    def test_session_error_is_500_not_a_fallback(self):
        from fastapi import HTTPException
        from services.internal_chat.resolved_config import InternalChatSessionError
        with pytest.raises(HTTPException) as e:
            self._run(InternalChatSessionError("no session"), _config())
        assert e.value.status_code == 500 and "no session" not in str(e.value.detail)

    def test_chat_turn_error_detail_is_generic(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as e:
            self._run(RuntimeError("https://mcp.internal/secret"), _config())
        assert e.value.detail == "Agent execution failed"

    def test_standard_turn_error_detail_unchanged(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as e:
            self._run(RuntimeError("boom"), None)
        assert e.value.detail == "Agent execution failed: boom"

    def test_resume_with_turn_config_is_rejected(self):
        svc = _svc()
        with pytest.raises(ValueError):
            asyncio.run(svc.execute_agent_chat_with_file_refs(
                agent_id=1, message="", turn_config=_config(), resume_approval=MagicMock(),
                resume_decisions=[], channel=ApprovalChannel.INTERNAL_CHAT))

    def test_chat_turn_on_another_channel_is_rejected(self):
        svc = _svc()
        with pytest.raises(ValueError):
            asyncio.run(svc.execute_agent_chat_with_file_refs(
                agent_id=1, message="m", conversation_id=5, turn_config=_config(),
                channel=ApprovalChannel.PLAYGROUND))


class TestPrepareTurnSession:
    def test_uses_conversation_session_even_if_memory_session_expired(self, tmp_path):
        svc = AgentExecutionService.__new__(AgentExecutionService)
        agent = _agent(True)
        agent.agent_id = 1
        svc.agent_service = MagicMock(get_agent=MagicMock(return_value=agent))
        svc.session_service = MagicMock(get_user_session=AsyncMock(return_value=None))
        svc.agent_execution_repo = MagicMock()
        fresh = _agent(True)
        fresh.agent_id = 1
        fresh.enable_code_interpreter = False
        svc.agent_execution_repo.get_agent_with_relationships.return_value = fresh
        conv = MagicMock(conversation_id=5, session_id="conv_1_abc")
        svc._index_turn_uploads = AsyncMock()
        svc._select_message_files = MagicMock(return_value=[])
        with patch("services.conversation_service.ConversationService.get_conversation", return_value=conv) as g, \
             patch("services.agent_execution_service.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}):
            cfg = _config()
            ctx = asyncio.run(svc._prepare_turn(
                agent_id=1, message="hi", conversation_id=5, db=MagicMock(),
                user_context={"user_id": 3, "app_id": 1}, turn_config=cfg,
            ))
        assert ctx.session_id_for_cache == "conv_1_abc"
        assert ctx.turn_config is cfg
        assert ctx.sandbox_handle is None
        svc.session_service.get_user_session.assert_not_called()
        assert g.call_args.kwargs["include_internal_chat"] is True


class TestApprovalChannel:
    def test_internal_chat_is_not_interactive(self):
        assert ApprovalChannel.INTERNAL_CHAT not in INTERACTIVE_CHANNELS
        assert not approvals.is_interactive(ApprovalChannel.INTERNAL_CHAT)

    def test_pause_on_internal_chat_is_rejected_immediately(self):
        svc = _svc()
        ctx = _ctx(True, _config())
        ctx.conversation = MagicMock(conversation_id=5)
        approval = MagicMock(id="ap", actions=[{"name": "tool"}])
        svc._reject_in_place = AsyncMock()
        paused = MagicMock()
        with patch.object(approvals, "open_approval", new=AsyncMock(return_value=approval)) as op, \
             patch("tools.middleware.factory.human_in_the_loop_config", return_value=None):
            with pytest.raises(approvals.ApprovalNotSupportedError):
                asyncio.run(svc._handle_pause(ctx, paused, MagicMock(), ApprovalChannel.INTERNAL_CHAT))
        assert op.call_args.kwargs["answerable"] is False
        svc._reject_in_place.assert_awaited_once()


class TestTracing:
    def _build(self, **kw):
        from tools import langsmith_config as ls
        settings = SimpleNamespace(api_key="k", endpoint=None, project_name="proj", source="app")
        agent = SimpleNamespace(agent_id=1, name="n", type="agent", app=None, has_memory=True)
        with patch.object(ls, "get_langsmith_client"), patch.object(ls, "LangChainTracer"):
            return ls.build_tracing_config(settings, agent=agent, **kw)[1]

    def test_without_extras_is_unchanged(self):
        ov = self._build()
        assert ov["tags"] == ["agent:1", "app:proj", "agent_type:agent"]
        assert "chat_ai_service_id" not in ov["metadata"]

    def test_extra_metadata_and_tags_and_standard_key_wins(self):
        from services.agent_execution_context import tracing_kwargs
        kw = tracing_kwargs(_config())
        kw["extra_metadata"]["agent_id"] = 999  # clashing key
        ov = self._build(**kw)
        assert ov["metadata"]["chat_ai_service_id"] == 77
        assert ov["metadata"]["agent_id"] == 1
        assert "internal_chat" in ov["tags"] and "ai_service:77" in ov["tags"]

    def test_metadata_alone_adds_no_tag(self):
        assert "internal_chat" not in self._build(extra_metadata={"k": 1})["tags"]


class TestHistoryMessageIds:
    @pytest.mark.parametrize("flag", [False, True])
    def test_message_id_only_when_requested(self, flag):
        from langchain_core.messages import AIMessage, HumanMessage
        from services.agent_cache_service import CheckpointerCacheService
        cp = MagicMock()
        cp.aget_tuple = AsyncMock(return_value=SimpleNamespace(checkpoint={"channel_values": {"messages": [
            HumanMessage(content="q", id="h1"), AIMessage(content="a", id="a1")]}}))
        with patch.object(CheckpointerCacheService, "get_async_checkpointer", AsyncMock(return_value=cp)):
            hist = asyncio.run(CheckpointerCacheService.get_conversation_history_async(
                1, "s", include_message_ids=flag))
        assert [("message_id" in h) for h in hist] == [flag, flag]
        if flag:
            assert [h["message_id"] for h in hist] == ["h1", "a1"]


