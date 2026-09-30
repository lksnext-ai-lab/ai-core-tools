"""Unit tests for MonitoringMiddleware in isolation (mirrors test_guardrails_middleware.py)."""
import logging

import pytest
from langchain_core.messages import AIMessage

from tools.middleware import monitoring as monitoring_module
from tools.middleware.monitoring import MonitoringMiddleware, build_monitoring_log_line


class TestBuildMonitoringLogLine:
    def test_all_metrics_enabled_emits_all(self):
        usage = {"gpt-4": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}}
        line = build_monitoring_log_line(1, usage, call_count=1, metrics_cfg={})
        assert "input_tokens=100" in line
        assert "output_tokens=50" in line
        assert "total_tokens=150" in line
        assert "models=" in line
        assert "llm_calls=1" in line

    def test_output_tokens_disabled(self):
        usage = {"gpt-4": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}}
        line = build_monitoring_log_line(
            1, usage, call_count=1,
            metrics_cfg={"input_tokens": True, "output_tokens": False, "total_tokens": True, "models": True, "llm_calls": True},
        )
        assert "output_tokens" not in line
        assert "input_tokens=100" in line

    def test_no_config_all_on(self):
        """Absent config means all metrics enabled."""
        usage = {"gpt-4": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}
        line = build_monitoring_log_line(1, usage, call_count=1, metrics_cfg={})
        assert "input_tokens=10" in line

    def test_all_flags_false_emits_nothing(self):
        usage = {"gpt-4": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}
        line = build_monitoring_log_line(
            1, usage, call_count=1,
            metrics_cfg={"input_tokens": False, "output_tokens": False, "total_tokens": False, "models": False, "llm_calls": False},
        )
        assert line is None

    def test_subset_metrics(self):
        usage = {"gpt-4": {"input_tokens": 200, "output_tokens": 100, "total_tokens": 300}}
        line = build_monitoring_log_line(
            1, usage, call_count=2,
            metrics_cfg={"models": True, "llm_calls": True, "input_tokens": False, "output_tokens": False, "total_tokens": False},
        )
        assert "models=" in line
        assert "llm_calls=2" in line
        assert "input_tokens" not in line


class _FakeResponse:
    def __init__(self, result):
        self.result = result


def _ai_message(tokens: int, model_name: str = "gpt-4"):
    return AIMessage(
        content="hi",
        usage_metadata={"input_tokens": tokens, "output_tokens": tokens, "total_tokens": tokens * 2},
        response_metadata={"model_name": model_name},
    )


def _capture_after_agent(mw) -> list[str]:
    records: list[str] = []

    class ListHandler(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = ListHandler()
    monitoring_module.logger.addHandler(handler)
    try:
        mw.after_agent({}, None)
    finally:
        monitoring_module.logger.removeHandler(handler)
    return records


class TestMonitoringMiddlewareAwrapModelCall:
    @pytest.mark.asyncio
    async def test_accumulates_usage_and_counts_call(self):
        mw = MonitoringMiddleware(agent_id=1, config={})

        async def handler(request):
            return _FakeResponse(result=[_ai_message(10)])

        response = await mw.awrap_model_call(request=None, handler=handler)

        assert response.result[0].content == "hi"
        assert mw.call_count == 1
        assert mw.usage_by_model["gpt-4"]["input_tokens"] == 10

    @pytest.mark.asyncio
    async def test_accumulates_across_multiple_calls_same_model(self):
        mw = MonitoringMiddleware(agent_id=1, config={})

        async def handler_a(request):
            return _FakeResponse(result=[_ai_message(10)])

        async def handler_b(request):
            return _FakeResponse(result=[_ai_message(20)])

        await mw.awrap_model_call(None, handler_a)
        await mw.awrap_model_call(None, handler_b)

        assert mw.call_count == 2
        assert mw.usage_by_model["gpt-4"]["input_tokens"] == 30

    @pytest.mark.asyncio
    async def test_counts_call_even_without_usage_metadata(self):
        """Some providers/fakes don't populate usage_metadata — the call still happened."""
        mw = MonitoringMiddleware(agent_id=1, config={})

        async def handler(request):
            return _FakeResponse(result=[AIMessage(content="hi")])

        await mw.awrap_model_call(None, handler)

        assert mw.call_count == 1
        assert mw.usage_by_model == {}


class TestMonitoringMiddlewareAfterAgent:
    def test_logs_accumulated_metrics(self):
        mw = MonitoringMiddleware(agent_id=42, config={})
        mw.usage_by_model = {"gpt-4": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}
        mw.call_count = 1

        records = _capture_after_agent(mw)

        assert len(records) == 1
        assert "[Monitoring] agent_id=42" in records[0]
        assert "llm_calls=1" in records[0]

    def test_silent_when_all_metrics_disabled(self):
        mw = MonitoringMiddleware(
            agent_id=1,
            config={"metrics": {"models": False, "input_tokens": False, "output_tokens": False, "total_tokens": False, "llm_calls": False}},
        )
        mw.usage_by_model = {"gpt-4": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}
        mw.call_count = 1

        records = _capture_after_agent(mw)

        assert records == []


class TestMonitoringMiddlewareHitlPauseResume:
    """A HITL interrupt rebuilds the whole chain (fresh MonitoringMiddleware
    instance) to resume — these totals must survive that gap via _PENDING_STATE."""

    def teardown_method(self):
        monitoring_module._PENDING_STATE.clear()

    @pytest.mark.asyncio
    async def test_pending_state_survives_interrupt_and_merges_on_resume(self):
        # Pre-interrupt half: one model call decides to invoke a tool, then the
        # graph pauses — after_agent never runs, so this instance is abandoned.
        pre_interrupt = MonitoringMiddleware(agent_id=7, config={}, thread_id="thread_7_sess1")

        async def handler(request):
            return _FakeResponse(result=[_ai_message(10)])

        await pre_interrupt.awrap_model_call(None, handler)
        assert monitoring_module._PENDING_STATE["thread_7_sess1"]["call_count"] == 1

        # Resume: create_agent() rebuilds the chain, constructing a NEW instance
        # with the same thread_id — it must pick up where the old one left off.
        post_resume = MonitoringMiddleware(agent_id=7, config={}, thread_id="thread_7_sess1")
        assert post_resume.call_count == 1
        assert post_resume.usage_by_model["gpt-4"]["input_tokens"] == 10

        async def handler_2(request):
            return _FakeResponse(result=[_ai_message(20)])

        await post_resume.awrap_model_call(None, handler_2)

        records = _capture_after_agent(post_resume)

        assert post_resume.call_count == 2
        assert post_resume.usage_by_model["gpt-4"]["input_tokens"] == 30
        assert "llm_calls=2" in records[0]
        # The turn is done — nothing should be left pending for the next turn.
        assert "thread_7_sess1" not in monitoring_module._PENDING_STATE
