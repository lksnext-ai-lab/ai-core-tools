"""Unit tests: ``stream_agent_events`` for flexible-chat turns (turn_config) vs standard turns."""
from __future__ import annotations

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

from models.hitl_approval import ApprovalChannel
from services.internal_chat.resolved_config import InternalChatSessionError, ResolvedChatConfig


def _cfg():
    return ResolvedChatConfig(
        app_id=1, ai_service=MagicMock(), ai_service_id=77, ai_service_name="S",
        ai_service_is_system=False, ai_service_provider="Anthropic", ai_service_model="claude-x",
        silo=None, silo_id=None, silo_name=None, skills=(), skill_ids=(), skill_names=(),
        mcp_connections=(), mcp_config_ids=(), mcp_config_names=(), system_prompt="p",
    )


def _ctx(turn_config=None):
    return SimpleNamespace(
        agent_id=1, agent=SimpleNamespace(name="A", has_memory=True),
        fresh_agent=SimpleNamespace(agent_id=1, has_memory=True, app=None, app_id=1, is_internal_chat=turn_config is not None),
        effective_conv_id=297, conversation=SimpleNamespace(conversation_id=297, session_id="conv_1_x"),
        session_id_for_cache="conv_1_x", user_context={"user_id": "u1"}, image_files=[], processed_files=[],
        enhanced_message="hello", search_params={}, working_dir="/tmp/w", sandbox_handle=None,
        sandbox_provider=None, sandbox_session_key=None, turn_config=turn_config,
    )


def _chain(chunks, state_messages=()):
    async def _gen():
        for c in chunks:
            yield c

    chain = MagicMock()
    chain.astream.return_value = _gen()
    chain.aget_state = AsyncMock(return_value=SimpleNamespace(tasks=[], values={"messages": list(state_messages)}))
    return chain


CHUNKS = [
    ("messages", (AIMessageChunk(content="Hi"), {})),
    ("updates", {"SummarizationMiddleware.before_model": {"messages": [AIMessage(content="old", id="older-turn")]}}),
    ("updates", {"model": {"messages": [AIMessage(content="Hi", id="run-1")]}}),
]


async def _run(ctx, chain, *, turn_config=None, hook=None, hitl=False, redact=False, pause=None,
               create_agent=None, finalize=None, channel=None, extra=()):
    if channel is None:
        channel = ApprovalChannel.INTERNAL_CHAT if turn_config is not None else ApprovalChannel.PLAYGROUND
    from services.agent_streaming_service import AgentStreamingService

    order = []
    svc = AgentStreamingService()
    es = MagicMock()
    es._prepare_turn = AsyncMock(return_value=ctx)
    es._begin_sandbox_turn = MagicMock(return_value=False)
    es._end_sandbox_turn = MagicMock()
    es._reject_in_place = AsyncMock()

    async def _finalize(c, raw, db, **kw):
        order.append("finalize")
        result = {"parsed_response": "Hi", "effective_conv_id": 297, "files_data": [],
                  "assistant_message_id": kw.get("assistant_message_id")}
        if kw.get("on_turn_completed"):
            result["turn"] = await kw["on_turn_completed"](SimpleNamespace(assistant_message_id=kw.get("assistant_message_id")))
        return result

    es._finalize_turn = AsyncMock(side_effect=finalize or _finalize)
    es._pull_outputs = AsyncMock()
    svc.execution_service = es
    recorded = {}
    create = create_agent or AsyncMock(return_value=(chain, None))
    pre_check = MagicMock(return_value=None)
    with ExitStack() as st:
        for p in [
            patch("services.agent_streaming_service.create_agent", create),
            patch("services.agent_streaming_service.prepare_agent_config", return_value={"configurable": {}}),
            patch("services.agent_streaming_service.build_human_message", return_value=SimpleNamespace(content="h")),
            patch("services.agent_streaming_service.resolve_langsmith_settings", return_value=None),
            patch("services.agent_streaming_service.record_agent_execution", side_effect=lambda **k: recorded.update(k)),
            patch("services.agent_streaming_service.human_in_the_loop_config", return_value=MagicMock() if hitl else None),
            patch("tools.middleware.factory.human_in_the_loop_config", return_value=MagicMock() if hitl else None),
            patch("services.agent_streaming_service.redacts_output", return_value=redact),
            patch("services.agent_streaming_service._read_pause", AsyncMock(return_value=pause)),
            patch("services.agent_streaming_service.approvals.check_conversation_free", pre_check),
            *extra,
        ]:
            st.enter_context(p)
        events = [
            ev async for ev in svc.stream_agent_events(
                agent_id=1, message="hi", user_context={"user_id": "u1"}, conversation_id=297,
                db=MagicMock(), channel=channel, turn_config=turn_config, on_turn_completed=hook,
            )
        ]
    return events, es, recorded, create, pre_check, order


def _types(events):
    return [e.type for e in events]


@pytest.mark.asyncio
async def test_chat_turn_event_contract():
    calls = []

    async def hook(event):
        calls.append(event)
        return {"turn_index": 1}

    cfg = _cfg()
    events, es, rec, create, _, order = await _run(
        _ctx(cfg), _chain(CHUNKS), turn_config=cfg, hook=hook, channel=ApprovalChannel.INTERNAL_CHAT)
    assert len(calls) == 1 and order == ["finalize"]
    assert _types(events)[0] == "metadata" and _types(events)[-1] == "done"
    meta, done = events[0].data, events[-1].data
    assert meta["turn_config"] == cfg.to_client_summary()
    assert meta["turn_config"]["warnings"] == []  # always present
    # the hidden shared agent's ids / name and the thread's session id never reach the client
    assert not {"session_id", "agent_id", "agent_name"} & set(meta)
    assert meta["conversation_id"] == 297 and "has_memory" in meta
    assert done["assistant_message_id"] == "run-1" and done["turn"] == {"turn_index": 1}
    assert create.call_args.kwargs["turn_config"] is cfg
    assert rec["ai_service_override"] == cfg.metrics_service()
    kw = es._finalize_turn.call_args.kwargs
    assert kw["assistant_message_id"] == "run-1" and kw["on_turn_completed"] is hook
    chain_state_reads = es._prepare_turn.call_args.kwargs["turn_config"]
    assert chain_state_reads is cfg


@pytest.mark.asyncio
async def test_standard_turn_has_no_chat_keys():
    events, es, rec, create, _, _ = await _run(_ctx(), _chain(CHUNKS))
    assert "turn_config" not in events[0].data
    assert {"session_id", "agent_id", "agent_name"} <= set(events[0].data)  # the playground keeps them
    assert "assistant_message_id" not in events[-1].data and "turn" not in events[-1].data
    assert rec["ai_service_override"] is None
    assert es._finalize_turn.call_args.kwargs == {}


@pytest.mark.asyncio
async def test_run_local_message_id_beats_a_concurrent_thread_head():
    other = AIMessage(content="B's answer", id="other-turn")
    cfg = _cfg()
    events, *_ = await _run(_ctx(cfg), _chain(CHUNKS, [other]), turn_config=cfg)
    assert events[-1].data["assistant_message_id"] == "run-1"


@pytest.mark.asyncio
async def test_checkpoint_fallback_when_stream_produced_no_ai_message():
    cfg = _cfg()
    chunks = [("messages", (AIMessageChunk(content="Hi"), {}))]
    events, *_ = await _run(_ctx(cfg), _chain(chunks, [AIMessage(content="Hi", id="cp-1")]), turn_config=cfg)
    assert events[-1].data["assistant_message_id"] == "cp-1"


@pytest.mark.asyncio
async def test_fallback_failure_returns_none_with_warning(caplog):
    from services.agent_streaming_service import _final_answer_message_id
    chain = MagicMock()
    chain.aget_state = AsyncMock(side_effect=RuntimeError("db down"))
    with patch("services.agent_streaming_service.logger") as log:
        assert await _final_answer_message_id(chain, {"configurable": {"checkpoint_id": "x"}}) is None
    log.warning.assert_called_once()
    chain.aget_state.assert_awaited_once()
    assert "checkpoint_id" not in chain.aget_state.call_args.args[0]["configurable"]


@pytest.mark.asyncio
async def test_chat_turn_skips_hitl_precheck_and_pii_buffering_standard_keeps_them():
    cfg = _cfg()
    final = [AIMessage(content="redacted", id="x")]
    ev_chat, _, _, _, pre_chat, _ = await _run(
        _ctx(cfg), _chain(CHUNKS, final), turn_config=cfg, hitl=True, redact=True)
    ev_std, _, _, _, pre_std, _ = await _run(_ctx(), _chain(CHUNKS, final), hitl=True, redact=True)
    pre_chat.assert_not_called()
    pre_std.assert_called_once()
    assert "token" in _types(ev_chat)          # not buffered
    assert "token" not in _types(ev_std)       # buffered (PII redaction)


@pytest.mark.asyncio
async def test_chat_turn_interrupt_is_rejected_not_finalized():
    cfg = _cfg()
    approval = MagicMock(id="ap", actions=[{"name": "tool"}])
    open_approval = AsyncMock(return_value=approval)
    events, es, *_ = await _run(
        _ctx(cfg), _chain(CHUNKS), turn_config=cfg, pause=object(),
        channel=ApprovalChannel.INTERNAL_CHAT,
        extra=[patch("services.agent_streaming_service.approvals.open_approval", open_approval)])
    assert open_approval.call_args.kwargs["answerable"] is False
    es._reject_in_place.assert_awaited_once()
    es._finalize_turn.assert_not_called()
    assert _types(events)[-1] == "error" and events[-1].extra["error_kind"] == "approval"


@pytest.mark.asyncio
async def test_session_error_is_an_error_event_not_a_fallback():
    cfg = _cfg()
    create = AsyncMock(side_effect=InternalChatSessionError("no session"))
    events, es, *_ = await _run(_ctx(cfg), _chain([]), turn_config=cfg, create_agent=create)
    assert _types(events)[-1] == "error" and events[-1].extra["error_kind"] == "agent_failure"
    assert "no session" not in str(events[-1].data)
    es._finalize_turn.assert_not_called()


@pytest.mark.asyncio
async def test_resume_with_turn_config_is_rejected():
    from services.agent_streaming_service import AgentStreamingService
    with pytest.raises(ValueError):
        async for _ in AgentStreamingService().stream_agent_events(
            agent_id=1, message="", turn_config=_cfg(), resume=MagicMock()
        ):
            pass


@pytest.mark.asyncio
async def test_chat_turn_on_another_channel_is_rejected():
    from services.agent_streaming_service import AgentStreamingService
    with pytest.raises(ValueError):
        async for _ in AgentStreamingService().stream_agent_events(
            agent_id=1, message="", turn_config=_cfg(), channel=ApprovalChannel.PLAYGROUND
        ):
            pass


@pytest.mark.asyncio
async def test_finalize_survives_anyio_cancellation_redelivered_every_loop_turn():
    """Starlette cancels the response task group on disconnect (cancellation re-delivered)."""
    import asyncio
    import anyio
    from services.agent_streaming_service import AgentStreamingService

    log = []

    async def finalize_turn(*a, **k):
        log.append("finalize start")
        await asyncio.sleep(0.2)
        log.append("hook done")
        return {"ok": True}

    svc = AgentStreamingService()
    svc.execution_service = MagicMock(_finalize_turn=AsyncMock(side_effect=finalize_turn), _pull_outputs=AsyncMock())

    async def consumer():
        try:
            await svc._finalize(MagicMock(), "r", MagicMock(), True, {})
        finally:
            log.append("consumer cleanup (db.close)")

    async with anyio.create_task_group() as tg:
        tg.start_soon(consumer)
        await asyncio.sleep(0.05)
        tg.cancel_scope.cancel()
    assert log == ["finalize start", "hook done", "consumer cleanup (db.close)"]


@pytest.mark.asyncio
async def test_finalize_deadline_marks_turn_not_finalized():
    from services import agent_streaming_service as mod

    async def hang(*a, **k):
        import asyncio
        await asyncio.sleep(5)

    svc = mod.AgentStreamingService()
    svc.execution_service = MagicMock(_finalize_turn=AsyncMock(side_effect=hang), _pull_outputs=AsyncMock())
    with patch.object(mod, "FINALIZE_GRACE_S", 0.05):
        with pytest.raises(TimeoutError):
            await svc._finalize(MagicMock(), "r", MagicMock(), True, {})
