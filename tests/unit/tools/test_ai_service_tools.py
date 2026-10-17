"""Unit tests for ``tools.aiServiceTools._build_openai_llm``.

Reasoning models (o-series, gpt-5.x) reject function tools on
/v1/chat/completions, and every agent in this codebase is built with tools, so
the OpenAI provider must talk to the Responses API. A custom endpoint, however,
is an OpenAI-compatible gateway: those speak /v1/chat/completions and not
necessarily /v1/responses, so they must keep the old surface.

Tests verify:
- No endpoint (OpenAI itself) selects the Responses API.
- A custom endpoint keeps the chat completions API.
"""

from __future__ import annotations

from types import SimpleNamespace


import pytest


def _ai_service(endpoint: str | None = None, model: str = "gpt-5.5") -> SimpleNamespace:
    """Minimal stand-in for an AIService row, with only the fields the builder reads."""
    return SimpleNamespace(
        description=model,
        api_key="sk-test-key",
        endpoint=endpoint,
    )


class TestBuildOpenAILLM:
    def test_uses_responses_api_when_no_custom_endpoint(self):
        from tools.aiServiceTools import _build_openai_llm

        llm = _build_openai_llm(_ai_service(endpoint=None), temperature=0)

        assert llm.use_responses_api is True

    def test_keeps_chat_completions_for_custom_endpoint(self):
        from tools.aiServiceTools import _build_openai_llm

        llm = _build_openai_llm(
            _ai_service(endpoint="https://gateway.example.com/v1"), temperature=0
        )

        assert llm.use_responses_api is False


class TestOpenAITemperature:
    """Reasoning models reject `temperature`; it must not reach the request at all."""

    @pytest.mark.parametrize("model", ["gpt-6-luna", "gpt-5.6-luna", "gpt-5.5", "gpt-10", "o3-mini", "o1", "GPT-6-terra"])
    def test_reasoning_models_send_no_temperature(self, model):
        from tools.aiServiceTools import _build_openai_llm

        llm = _build_openai_llm(_ai_service(model=model), temperature=0.7)

        assert "temperature" not in llm._get_request_payload([("user", "hi")])

    @pytest.mark.parametrize("model", ["gpt-4o", "gpt-4.1-mini", "gpt-3.5-turbo", "gpt-5-chat-latest"])
    def test_other_models_keep_the_agent_temperature(self, model):
        from tools.aiServiceTools import _build_openai_llm

        llm = _build_openai_llm(_ai_service(model=model), temperature=0.7)

        assert llm._get_request_payload([("user", "hi")])["temperature"] == 0.7
