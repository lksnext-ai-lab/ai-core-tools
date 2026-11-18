"""
Integration tests for public API rate limiting.

Rate limiting is enforced by the in-memory RateLimitService on the
POST /public/v1/app/{app_id}/chat/{agent_id}/call endpoint.

NOTE: These tests mock the agent execution (LLM call) so no real LLM
      API key is needed. Rate limit checks happen before execution.
"""

import pytest
from unittest.mock import patch, AsyncMock

from models.agent import Agent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def chat_url(app_id: int, agent_id: int) -> str:
    return f"/public/v1/app/{app_id}/chat/{agent_id}/call"


def chat_payload(message: str = "Hello") -> dict:
    return {"message": message}


def api_key_headers(key: str) -> dict:
    return {"X-API-KEY": key}


# ---------------------------------------------------------------------------
# API key authentication
# ---------------------------------------------------------------------------


class TestApiKeyAuth:
    def test_missing_api_key_returns_401_or_403(
        self, client, fake_app, fake_agent, db
    ):
        url = chat_url(fake_app.app_id, fake_agent.agent_id)
        response = client.post(url, data=chat_payload())
        assert response.status_code in (401, 403)

    def test_invalid_api_key_returns_401_or_403(
        self, client, fake_app, fake_agent, db
    ):
        url = chat_url(fake_app.app_id, fake_agent.agent_id)
        response = client.post(
            url,
            data=chat_payload(),
            headers=api_key_headers("completely-invalid-key"),
        )
        assert response.status_code in (401, 403)

    def test_inactive_api_key_is_rejected(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        """Deactivate the key and verify it's rejected."""
        fake_api_key.is_active = False
        db.flush()

        url = chat_url(fake_app.app_id, fake_agent.agent_id)
        response = client.post(
            url,
            data=chat_payload(),
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
        Set app rate limit to 3, make 3 requests -> all succeed; the 4th returns 429.
        """
        fake_app.agent_rate_limit = 3
        db.flush()

        url = chat_url(fake_app.app_id, fake_agent.agent_id)
        headers = api_key_headers(fake_api_key.key)

        mock_response = {
            "response": "ok",
            "agent_id": fake_agent.agent_id,
            "metadata": {"agent_name": "Test", "agent_type": "agent",
                         "files_processed": 0, "has_memory": False},
        }

        with patch(
            "services.agent_execution_service.AgentExecutionService.execute_agent_chat_with_file_refs",
            new=AsyncMock(return_value=mock_response),
        ):
            r1 = client.post(url, data=chat_payload("msg1"), headers=headers)
            r2 = client.post(url, data=chat_payload("msg2"), headers=headers)
            r3 = client.post(url, data=chat_payload("msg3"), headers=headers)
            r4 = client.post(url, data=chat_payload("msg4"), headers=headers)

        assert [r.status_code for r in (r1, r2, r3)] == [200, 200, 200]
        assert r4.status_code == 429

    def test_limit_is_independent_per_agent_in_the_same_app(
        self, client, fake_app, fake_agent, fake_ai_service, fake_api_key, db
    ):
        fake_app.agent_rate_limit = 1
        other_agent = Agent(
            name="Other test agent",
            description="Second agent in the same app",
            system_prompt="You are a helpful test assistant.",
            app_id=fake_app.app_id,
            service_id=fake_ai_service.service_id,
            has_memory=False,
            temperature=0.7,
        )
        db.add(other_agent)
        db.flush()

        headers = api_key_headers(fake_api_key.key)
        mock_response = {
            "response": "ok",
            "agent_id": fake_agent.agent_id,
            "metadata": {"agent_name": "Test", "agent_type": "agent",
                         "files_processed": 0, "has_memory": False},
        }

        with patch(
            "services.agent_execution_service.AgentExecutionService.execute_agent_chat_with_file_refs",
            new=AsyncMock(return_value=mock_response),
        ):
            list_response = client.get(
                f"/public/v1/app/{fake_app.app_id}/agents/",
                headers=headers,
            )
            first_agent_call = client.post(
                chat_url(fake_app.app_id, fake_agent.agent_id),
                data=chat_payload("agent 1"),
                headers=headers,
            )
            second_agent_call = client.post(
                chat_url(fake_app.app_id, other_agent.agent_id),
                data=chat_payload("agent 2"),
                headers=headers,
            )
            repeated_first_agent_call = client.post(
                chat_url(fake_app.app_id, fake_agent.agent_id),
                data=chat_payload("agent 1 again"),
                headers=headers,
            )

        assert list_response.status_code == 200
        assert first_agent_call.status_code == 200
        assert second_agent_call.status_code == 200
        assert repeated_first_agent_call.status_code == 429

    def test_rate_limit_zero_means_unlimited(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        """app.agent_rate_limit = 0 -> unlimited requests allowed."""
        fake_app.agent_rate_limit = 0
        db.flush()

        url = chat_url(fake_app.app_id, fake_agent.agent_id)
        headers = api_key_headers(fake_api_key.key)

        mock_response = {
            "response": "ok",
            "agent_id": fake_agent.agent_id,
            "metadata": {"agent_name": "T", "agent_type": "agent",
                         "files_processed": 0, "has_memory": False},
        }

        with patch(
            "services.agent_execution_service.AgentExecutionService.execute_agent_chat_with_file_refs",
            new=AsyncMock(return_value=mock_response),
        ):
            responses = [
                client.post(url, data=chat_payload(f"msg{i}"), headers=headers)
                for i in range(5)
            ]

        rate_limited = [r for r in responses if r.status_code == 429]
        assert len(rate_limited) == 0

    def test_rate_limit_headers_present_in_response(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        """Responses include headers for the selected agent's rate-limit bucket."""
        fake_app.agent_rate_limit = 10
        db.flush()

        url = chat_url(fake_app.app_id, fake_agent.agent_id)
        headers = api_key_headers(fake_api_key.key)

        mock_response = {
            "response": "ok",
            "agent_id": fake_agent.agent_id,
            "metadata": {"agent_name": "T", "agent_type": "agent",
                         "files_processed": 0, "has_memory": False},
        }

        with patch(
            "services.agent_execution_service.AgentExecutionService.execute_agent_chat_with_file_refs",
            new=AsyncMock(return_value=mock_response),
        ):
            response = client.post(url, data=chat_payload(), headers=headers)

        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "10"
        assert response.headers["X-RateLimit-Remaining"] == "9"
        assert "X-RateLimit-Reset" in response.headers
