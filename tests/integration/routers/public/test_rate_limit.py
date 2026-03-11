"""
Integration tests for public API rate limiting.

Rate limiting is enforced by the in-memory RateLimitService on the
POST /public/v1/agents/{agent_id}/chat endpoint.

NOTE: These tests mock the agent execution (LLM call) so no real LLM
      API key is needed. Rate limit checks happen before execution.
"""

import pytest
from unittest.mock import patch, AsyncMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CHAT_URL = "/public/v1/agents/{agent_id}/chat"


def chat_payload(message: str = "Hello") -> dict:
    return {"message": message}


def api_key_headers(key: str) -> dict:
    return {"X-API-KEY": key}


# ---------------------------------------------------------------------------
# API key authentication
# ---------------------------------------------------------------------------


class TestApiKeyAuth:
    def test_missing_api_key_returns_401_or_403(
        self, client, fake_agent, db
    ):
        url = CHAT_URL.format(agent_id=fake_agent.agent_id)
        response = client.post(url, json=chat_payload())
        assert response.status_code in (401, 403)

    def test_invalid_api_key_returns_401_or_403(
        self, client, fake_agent, db
    ):
        url = CHAT_URL.format(agent_id=fake_agent.agent_id)
        response = client.post(
            url,
            json=chat_payload(),
            headers=api_key_headers("completely-invalid-key"),
        )
        assert response.status_code in (401, 403)

    def test_inactive_api_key_is_rejected(
        self, client, fake_agent, fake_api_key, db
    ):
        """Deactivate the key and verify it's rejected."""
        fake_api_key.is_active = False
        db.flush()

        url = CHAT_URL.format(agent_id=fake_agent.agent_id)
        response = client.post(
            url,
            json=chat_payload(),
            headers=api_key_headers(fake_api_key.key),
        )
        assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class TestRateLimit:
    def test_rate_limit_blocks_after_limit_exceeded(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        """
        Set app rate limit to 2, make 3 requests → 3rd should return 429.
        The agent execution is mocked so no LLM call happens.
        """
        fake_app.agent_rate_limit = 2
        db.flush()

        url = CHAT_URL.format(agent_id=fake_agent.agent_id)
        headers = api_key_headers(fake_api_key.key)

        mock_response = {
            "response": "ok",
            "agent_id": fake_agent.agent_id,
            "metadata": {"agent_name": "Test", "agent_type": "agent",
                         "files_processed": 0, "has_memory": False},
        }

        with patch(
            "services.agent_execution_service.AgentExecutionService.execute_agent_chat",
            new=AsyncMock(return_value=mock_response),
        ):
            r1 = client.post(url, json=chat_payload("msg1"), headers=headers)
            r2 = client.post(url, json=chat_payload("msg2"), headers=headers)
            r3 = client.post(url, json=chat_payload("msg3"), headers=headers)

        # First two should succeed (or fail for other reasons but not rate limit)
        assert r1.status_code != 429
        assert r2.status_code != 429
        # Third should be rate-limited
        assert r3.status_code == 429

    def test_rate_limit_zero_means_unlimited(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        """app.agent_rate_limit = 0 → unlimited requests allowed."""
        fake_app.agent_rate_limit = 0
        db.flush()

        url = CHAT_URL.format(agent_id=fake_agent.agent_id)
        headers = api_key_headers(fake_api_key.key)

        mock_response = {
            "response": "ok",
            "agent_id": fake_agent.agent_id,
            "metadata": {"agent_name": "T", "agent_type": "agent",
                         "files_processed": 0, "has_memory": False},
        }

        with patch(
            "services.agent_execution_service.AgentExecutionService.execute_agent_chat",
            new=AsyncMock(return_value=mock_response),
        ):
            responses = [
                client.post(url, json=chat_payload(f"msg{i}"), headers=headers)
                for i in range(5)
            ]

        rate_limited = [r for r in responses if r.status_code == 429]
        assert len(rate_limited) == 0

    def test_rate_limit_headers_present_in_response(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        """Responses should include X-RateLimit-* headers (if implemented)."""
        fake_app.agent_rate_limit = 10
        db.flush()

        url = CHAT_URL.format(agent_id=fake_agent.agent_id)
        headers = api_key_headers(fake_api_key.key)

        mock_response = {
            "response": "ok",
            "agent_id": fake_agent.agent_id,
            "metadata": {"agent_name": "T", "agent_type": "agent",
                         "files_processed": 0, "has_memory": False},
        }

        with patch(
            "services.agent_execution_service.AgentExecutionService.execute_agent_chat",
            new=AsyncMock(return_value=mock_response),
        ):
            response = client.post(url, json=chat_payload(), headers=headers)

        # Rate limit headers may or may not be present depending on implementation
        # This test serves as documentation — update assertions when headers are added
        if response.status_code == 200:
            # If rate limit headers are implemented, they should look like this:
            # assert "X-RateLimit-Limit" in response.headers
            # assert "X-RateLimit-Remaining" in response.headers
            pass  # Currently no rate-limit headers in responses
