"""
Integration tests for public API origin (CORS allow-list) enforcement.

Origin validation is enforced by `enforce_allowed_origins` on the
POST /public/v1/app/{app_id}/chat/{agent_id}/call endpoint.

NOTE: These tests mock the agent execution (LLM call) so no real LLM
      API key is needed. Origin checks happen before execution.
"""
from unittest.mock import patch, AsyncMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def chat_url(app_ref, agent_id: int) -> str:
    return f"/public/v1/app/{app_ref}/chat/{agent_id}/call"


def chat_payload(message: str = "Hello") -> dict:
    return {"message": message}


def api_key_headers(key: str, origin: str | None = None) -> dict:
    headers = {"X-API-KEY": key}
    if origin is not None:
        headers["Origin"] = origin
    return headers


MOCK_RESPONSE = {
    "response": "ok",
    "agent_id": 1,
    "metadata": {"agent_name": "T", "agent_type": "agent",
                 "files_processed": 0, "has_memory": False},
}


# ---------------------------------------------------------------------------
# Origin enforcement
# ---------------------------------------------------------------------------


class TestOriginEnforcement:
    def test_disallowed_origin_is_rejected(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        fake_app.agent_cors_origins = "https://good.example.com"
        db.flush()

        url = chat_url(fake_app.app_id, fake_agent.agent_id)
        headers = api_key_headers(fake_api_key.key, origin="https://evil.example.com")

        response = client.post(url, data=chat_payload(), headers=headers)
        assert response.status_code == 403

    def test_allowed_origin_passes_through(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        fake_app.agent_cors_origins = "https://good.example.com"
        db.flush()

        url = chat_url(fake_app.app_id, fake_agent.agent_id)
        headers = api_key_headers(fake_api_key.key, origin="https://good.example.com")

        with patch(
            "services.agent_execution_service.AgentExecutionService.execute_agent_chat_with_file_refs",
            new=AsyncMock(return_value=MOCK_RESPONSE),
        ):
            response = client.post(url, data=chat_payload(), headers=headers)

        assert response.status_code != 403

    def test_no_allowed_origins_configured_allows_any_origin(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        fake_app.agent_cors_origins = ""
        db.flush()

        url = chat_url(fake_app.app_id, fake_agent.agent_id)
        headers = api_key_headers(fake_api_key.key, origin="https://anything.example.com")

        with patch(
            "services.agent_execution_service.AgentExecutionService.execute_agent_chat_with_file_refs",
            new=AsyncMock(return_value=MOCK_RESPONSE),
        ):
            response = client.post(url, data=chat_payload(), headers=headers)

        assert response.status_code != 403

    def test_x_app_id_header_on_403_reflects_the_url_path_reference(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        """
        Regression guard (step_006 review): `check_allowed_origin`'s `app_ref`
        parameter must make the public wire contract byte-identical to before the
        apply_*/check_* extraction. The `X-App-ID` header on a 403 must echo back
        the exact reference used in the URL path -- including when that reference
        is a slug, not the app's numeric id.
        """
        fake_app.agent_cors_origins = "https://good.example.com"
        db.flush()

        # Numeric id in the path -> header echoes the numeric id string.
        url_by_id = chat_url(fake_app.app_id, fake_agent.agent_id)
        headers = api_key_headers(fake_api_key.key, origin="https://evil.example.com")
        response_by_id = client.post(url_by_id, data=chat_payload(), headers=headers)
        assert response_by_id.status_code == 403
        assert response_by_id.headers["X-App-ID"] == str(fake_app.app_id)

        # Slug in the path -> header echoes the slug, not the numeric app_id.
        url_by_slug = chat_url(fake_app.slug, fake_agent.agent_id)
        response_by_slug = client.post(url_by_slug, data=chat_payload(), headers=headers)
        assert response_by_slug.status_code == 403
        assert response_by_slug.headers["X-App-ID"] == fake_app.slug
        assert response_by_slug.headers["X-App-ID"] != str(fake_app.app_id)
