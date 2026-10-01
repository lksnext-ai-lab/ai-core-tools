"""Unit tests for the agent metrics payload builder and caller-type detection.

These tests do NOT require a database connection.
"""
import sys
import os
from datetime import datetime
from unittest.mock import MagicMock

import pytest

# Ensure backend is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'backend'))

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from services.agent_metrics_collector import AgentMetricsCollector
from services.agent_metrics_recorder import build_metrics_payload, record_agent_execution


def _fake_agent(agent_id=1, app_id=2, ai_service_id=None, ai_service=None,
                output_parser_id=None):
    agent = MagicMock()
    agent.agent_id = agent_id
    agent.app_id = app_id
    agent.ai_service_id = ai_service_id
    agent.ai_service = ai_service
    agent.output_parser_id = output_parser_id
    return agent


def _make_payload(**kwargs):
    defaults = dict(
        event_id="test-event-id",
        fresh_agent=_fake_agent(),
        user_context={},
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        finished_at=datetime(2026, 1, 1, 12, 0, 5),
        duration_ms=5000,
        status="SUCCESS",
        error_code=None,
        error_message=None,
        result=None,
        image_files=[],
        message="Hello agent",
    )
    defaults.update(kwargs)
    return build_metrics_payload(**defaults)


# ── Token extraction ──────────────────────────────────────────────────────────

class TestTokenExtraction:
    """Without a collector (sub-agent runs), usage is summed over this turn's AI messages."""

    @staticmethod
    def _ai(inp, out, content="response text", model=None):
        return AIMessage(
            content=content,
            usage_metadata={'input_tokens': inp, 'output_tokens': out, 'total_tokens': inp + out},
            response_metadata={'model_name': model} if model else {},
        )

    def test_sums_every_llm_call_of_the_turn(self):
        # A tool loop: two model calls in the same turn.
        result = {'messages': [
            HumanMessage(content="q"),
            self._ai(100, 20, content=""),
            ToolMessage(content="tool out", tool_call_id="t1"),
            self._ai(150, 50, model="gpt-5-mini"),
        ]}
        event = _make_payload(result=result)['event']
        assert (event['input_tokens'], event['output_tokens'], event['total_tokens']) == (250, 70, 320)
        assert event['llm_calls'] == 2
        assert event['model_name'] == "gpt-5-mini"

    def test_ignores_restored_history(self):
        result = {'messages': [
            HumanMessage(content="old question"),
            self._ai(999, 999),
            HumanMessage(content="new question"),
            self._ai(10, 5),
        ]}
        event = _make_payload(result=result)['event']
        assert (event['input_tokens'], event['output_tokens']) == (10, 5)

    def test_missing_usage_metadata(self):
        result = {'messages': [HumanMessage(content="q"), AIMessage(content="text")]}
        event = _make_payload(result=result)['event']
        assert event['input_tokens'] is None
        assert event['total_tokens'] is None
        assert event['llm_calls'] == 1

    def test_empty_messages_list(self):
        event = _make_payload(result={'messages': []})['event']
        assert event['input_tokens'] is None
        assert event['llm_calls'] == 0


class TestCollectorPayload:
    def test_collector_is_the_source_when_given(self):
        collector = AgentMetricsCollector()
        collector.llm_calls, collector._usage_seen = 3, True
        collector.input_tokens, collector.output_tokens, collector.total_tokens = 30, 12, 42
        collector._models["claude-sonnet-5"] += 3
        collector.tool_calls.append({
            "tool_name": "retrieve_from_knowledge_base", "tool_type": "RETRIEVER", "sub_agent_id": None,
            "mcp_config_id": None, "status": "SUCCESS", "error_message": None,
            "duration_ms": 120, "started_at": "2026-01-01T12:00:00",
        })
        payload = _make_payload(collector=collector, time_to_first_token_ms=800)
        event = payload['event']
        assert (event['llm_calls'], event['total_tokens'], event['model_name']) == (3, 42, "claude-sonnet-5")
        assert event['time_to_first_token_ms'] == 800
        assert payload['tool_calls'][0]['tool_type'] == "RETRIEVER"
        assert event['tool_calls'] == [
            {"tool_name": "retrieve_from_knowledge_base", "tool_type": "RETRIEVER", "status": "SUCCESS"}
        ]

    def test_falls_back_to_configured_model_and_service(self):
        agent = _fake_agent()
        agent.service_id = 7
        agent.ai_service = MagicMock(description="gpt-4.1", provider="OpenAI")
        event = _make_payload(fresh_agent=agent)['event']
        assert (event['model_name'], event['provider'], event['ai_service_id']) == ("gpt-4.1", "OpenAI", 7)


# ── Caller type detection ─────────────────────────────────────────────────────

class TestCallerTypeDetection:
    def test_playground_default(self):
        payload = _make_payload(user_context={})
        assert payload['event']['caller_type'] == "INTERNAL_PLAYGROUND"

    def test_public_api(self):
        payload = _make_payload(user_context={'api_key_id': 5})
        assert payload['event']['caller_type'] == "PUBLIC_API"

    def test_mcp(self):
        payload = _make_payload(user_context={'mcp_caller': True})
        assert payload['event']['caller_type'] == "MCP"

    def test_agent_as_tool(self):
        payload = _make_payload(user_context={'parent_execution_id': 'some-uuid'})
        assert payload['event']['caller_type'] == "AGENT_AS_TOOL"

    def test_override_takes_priority(self):
        payload = _make_payload(user_context={
            'caller_type_override': 'AGENT_AS_TOOL',
            'api_key_id': 5,
        })
        assert payload['event']['caller_type'] == "AGENT_AS_TOOL"


# ── Current entry-point contexts ──────────────────────────────────────────────

class TestEntryPointContexts:
    def test_public_api_context_is_public_api_without_string_user_id(self):
        # create_api_key_user_context() sets user_id="apikey_<hash>" and the raw key.
        payload = _make_payload(user_context={'user_id': 'apikey_abc123', 'api_key': 'secret', 'app_id': 2})
        event = payload['event']
        assert event['caller_type'] == "PUBLIC_API"
        assert event['user_id'] is None
        assert 'secret' not in repr(payload)

    def test_mcp_server_context_is_mcp(self):
        # server_handler sets source="mcp" together with api_key_id.
        payload = _make_payload(user_context={'api_key_id': 7, 'mcp_server_id': 3, 'source': 'mcp'})
        assert payload['event']['caller_type'] == "MCP"
        assert payload['event']['api_key_id'] == 7

    def test_internal_context_keeps_integer_ids(self):
        payload = _make_payload(user_context={'user_id': 42, 'conversation_id': 9})
        assert payload['event']['user_id'] == 42
        assert payload['event']['conversation_id'] == 9


class TestRecordAgentExecution:
    def test_without_event_loop_drops_silently(self):
        # Sync tool paths (_run) have no running loop; recording must not raise.
        record_agent_execution(
            event_id="00000000-0000-0000-0000-000000000000",
            fresh_agent=_fake_agent(), user_context={}, started_at=datetime(2026, 1, 1),
            finished_at=datetime(2026, 1, 1), duration_ms=0, status="SUCCESS",
            error_code=None, error_message=None, result=None, image_files=[], message="hi",
        )
