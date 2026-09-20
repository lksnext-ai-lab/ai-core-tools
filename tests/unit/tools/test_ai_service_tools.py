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


def _ai_service(endpoint: str | None = None) -> SimpleNamespace:
    """Minimal stand-in for an AIService row, with only the fields the builder reads."""
    return SimpleNamespace(
        description="gpt-5.5",
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
