"""Unit tests for the metrics payload builder and caller-type detection logic.

These tests do NOT require a database connection or plugin installation.
"""
import sys
import os
from datetime import datetime
from unittest.mock import MagicMock

import pytest

# Ensure backend is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'backend'))

from services.agent_execution_service import _build_metrics_payload


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
    return _build_metrics_payload(**defaults)


# ── Token extraction ──────────────────────────────────────────────────────────

class TestTokenExtraction:
    def _make_message_with_usage(self, input_tokens, output_tokens, total_tokens):
        msg = MagicMock()
        msg.usage_metadata = {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': total_tokens,
        }
        msg.content = "response text"
        msg.tool_calls = None
        return msg

    def test_happy_path_tokens(self):
        msg = self._make_message_with_usage(100, 50, 150)
        result = {'messages': [msg]}
        payload = _make_payload(result=result)
        event = payload['event']
        assert event['input_tokens'] == 100
        assert event['output_tokens'] == 50
        assert event['total_tokens'] == 150

    def test_missing_usage_metadata(self):
        msg = MagicMock()
        msg.usage_metadata = None
        msg.content = "text"
        msg.tool_calls = None
        result = {'messages': [msg]}
        payload = _make_payload(result=result)
        event = payload['event']
        assert event['input_tokens'] is None
        assert event['output_tokens'] is None
        assert event['total_tokens'] is None

    def test_empty_messages_list(self):
        result = {'messages': []}
        payload = _make_payload(result=result)
        event = payload['event']
        assert event['input_tokens'] is None
        assert event['output_tokens'] is None
        assert event['total_tokens'] is None


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
