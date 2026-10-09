"""
Integration tests for the middlewares endpoints.

Endpoints under test:
  - GET    /internal/apps/{app_id}/middlewares               (list middlewares)
  - GET    /internal/apps/{app_id}/middlewares/{middleware_id} (get middleware details)
  - POST   /internal/apps/{app_id}/middlewares/{middleware_id} (create or update middleware)
  - DELETE /internal/apps/{app_id}/middlewares/{middleware_id} (delete middleware)

Also covers per-type config validation, tenant isolation of referenced AI services,
the agent's middleware selection rules and cascade deletion of agents/apps that use
middlewares.
"""

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def middlewares_url(app_id: int, middleware_id) -> str:
    return f"/internal/apps/{app_id}/middlewares/{middleware_id}"


def middlewares_list_url(app_id: int) -> str:
    return f"/internal/apps/{app_id}/middlewares"


def middleware_payload(
    name: str = "Test Middleware",
    description: str = "A test middleware",
    middleware_type: str = "guardrails",
    config: dict = None,
) -> dict:
    return {
        "name": name,
        "description": description,
        "middleware_type": middleware_type,
        "config": config,
    }


@pytest.fixture
def other_app(db, fake_user):
    """A second App, distinct from fake_app, owned by the same fake_user."""
    from models.app import App

    app_obj = App(
        name="Other Workspace",
        slug="other-workspace-fixture",
        owner_id=fake_user.user_id,
        agent_rate_limit=0,
        max_file_size_mb=10,
    )
    db.add(app_obj)
    db.flush()
    return app_obj


@pytest.fixture
def outsider_headers(db):
    """Auth headers for a user with NO relationship to fake_app at all (not the
    owner, not a collaborator) — used to assert role enforcement actually
    rejects unaffiliated users, as opposed to auth_headers/fake_user, who
    is always the OWNER of fake_app via App.owner_id."""
    from models.user import User
    from utils.local_auth_tokens import mint_access_token

    user = User(email="outsider@mattin-test.com", name="Outsider", is_active=True, platform_role="editor")
    db.add(user)
    db.flush()

    token, _ = mint_access_token(user.user_id, user.email, user.name)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# List middlewares
# ---------------------------------------------------------------------------

class TestListMiddlewares:
    def test_list_returns_empty_for_new_app(self, client, fake_app, owner_headers, db):
        db.flush()
        response = client.get(middlewares_list_url(fake_app.app_id), headers=owner_headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_list_requires_authentication(self, client, fake_app, db):
        db.flush()
        response = client.get(middlewares_list_url(fake_app.app_id))
        assert response.status_code in (401, 403)

    def test_list_does_not_leak_other_apps_middlewares(
        self, client, fake_app, other_app, owner_headers, db
    ):
        """A middleware created in other_app must not show up when listing fake_app."""
        db.flush()
        create_resp = client.post(
            middlewares_url(other_app.app_id, 0),
            json=middleware_payload(name="Other App Middleware"),
            headers=owner_headers,
        )
        assert create_resp.status_code == 200

        list_resp = client.get(middlewares_list_url(fake_app.app_id), headers=owner_headers)
        assert list_resp.status_code == 200
        assert list_resp.json() == []


# ---------------------------------------------------------------------------
# Get middleware
# ---------------------------------------------------------------------------

class TestGetMiddleware:
    def test_get_id_zero_is_not_found(self, client, fake_app, owner_headers, db):
        db.flush()
        response = client.get(middlewares_url(fake_app.app_id, 0), headers=owner_headers)
        assert response.status_code == 404

    def test_get_returns_404_for_missing_middleware(self, client, fake_app, owner_headers, db):
        db.flush()
        response = client.get(middlewares_url(fake_app.app_id, 99999), headers=owner_headers)
        assert response.status_code == 404

    def test_get_returns_404_for_other_apps_middleware(
        self, client, fake_app, other_app, owner_headers, db
    ):
        """A middleware belonging to other_app must 404 when fetched via fake_app's URL."""
        db.flush()
        create_resp = client.post(
            middlewares_url(other_app.app_id, 0),
            json=middleware_payload(name="Other App Middleware"),
            headers=owner_headers,
        )
        other_middleware_id = create_resp.json()["middleware_id"]

        response = client.get(middlewares_url(fake_app.app_id, other_middleware_id), headers=owner_headers)
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Create / update middleware
# ---------------------------------------------------------------------------

class TestCreateOrUpdateMiddleware:
    def test_create_returns_200_with_expected_fields(self, client, fake_app, owner_headers, db):
        db.flush()
        response = client.post(
            middlewares_url(fake_app.app_id, 0),
            json=middleware_payload(name="Guardrails", middleware_type="guardrails", config={"custom_prompt": "be nice"}),
            headers=owner_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Guardrails"
        assert data["middleware_type"] == "guardrails"
        # Stored config is the validated, normalised shape (defaults filled in).
        assert data["config"]["custom_prompt"] == "be nice"
        assert data["config"]["input"]["block_jailbreak"] is True
        assert data["middleware_id"] != 0

    def test_update_existing_middleware(self, client, fake_app, owner_headers, db):
        db.flush()
        create_resp = client.post(
            middlewares_url(fake_app.app_id, 0),
            json=middleware_payload(name="Original name"),
            headers=owner_headers,
        )
        middleware_id = create_resp.json()["middleware_id"]

        update_resp = client.post(
            middlewares_url(fake_app.app_id, middleware_id),
            json=middleware_payload(name="Renamed"),
            headers=owner_headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "Renamed"
        assert update_resp.json()["middleware_id"] == middleware_id

    def test_invalid_middleware_type_returns_422(self, client, fake_app, owner_headers, db):
        db.flush()
        response = client.post(
            middlewares_url(fake_app.app_id, 0),
            json=middleware_payload(middleware_type="not_a_real_type"),
            headers=owner_headers,
        )
        assert response.status_code == 422

    def test_create_requires_administrator_role(self, client, fake_app, outsider_headers, db):
        """A user with no app affiliation (plain authenticated user) must be rejected."""
        db.flush()
        response = client.post(
            middlewares_url(fake_app.app_id, 0),
            json=middleware_payload(),
            headers=outsider_headers,
        )
        assert response.status_code == 403

    def test_create_requires_authentication(self, client, fake_app, db):
        db.flush()
        response = client.post(
            middlewares_url(fake_app.app_id, 0),
            json=middleware_payload(),
        )
        assert response.status_code in (401, 403)

    def test_update_returns_404_for_other_apps_middleware(
        self, client, fake_app, other_app, owner_headers, db
    ):
        """Attempting to update other_app's middleware via fake_app's URL must 404,
        not silently update it."""
        db.flush()
        create_resp = client.post(
            middlewares_url(other_app.app_id, 0),
            json=middleware_payload(name="Other App Middleware"),
            headers=owner_headers,
        )
        other_middleware_id = create_resp.json()["middleware_id"]

        response = client.post(
            middlewares_url(fake_app.app_id, other_middleware_id),
            json=middleware_payload(name="Hijacked"),
            headers=owner_headers,
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Config validation and tenant isolation of referenced resources
# ---------------------------------------------------------------------------

class TestConfigValidation:
    @pytest.mark.parametrize("mw_type,config", [
        ("model_call_limit", {"max_calls": "abc"}),
        ("tool_call_limit", {"max_calls": -5}),
        ("tool_call_limit", None),
        ("pii", {"pii_types": ["dni_es"]}),
        ("pii", {"pii_types": ["email"], "apply_to_input": False, "apply_to_output": False,
                 "apply_to_tool_results": False}),
        ("human_in_the_loop", {"interrupt_on": {}}),
        ("human_in_the_loop", {"interrupt_on": {"search": {"allowed_decisions": ["foo"]}}}),
        ("summarization", {"trigger_tokens": 10}),
        ("guardrails", {"unknown_flag": True}),
        ("custom", {}),
        ("monitoring", {}),
    ])
    def test_invalid_config_returns_422(self, client, fake_app, owner_headers, db, mw_type, config):
        db.flush()
        response = client.post(
            middlewares_url(fake_app.app_id, 0),
            json=middleware_payload(middleware_type=mw_type, config=config),
            headers=owner_headers,
        )
        assert response.status_code == 422

    @pytest.mark.parametrize("name", ["", "   ", "x" * 101])
    def test_invalid_name_returns_422(self, client, fake_app, owner_headers, db, name):
        db.flush()
        response = client.post(middlewares_url(fake_app.app_id, 0), json=middleware_payload(name=name),
                               headers=owner_headers)
        assert response.status_code == 422

    def test_duplicate_name_returns_422(self, client, fake_app, owner_headers, db):
        db.flush()
        assert client.post(middlewares_url(fake_app.app_id, 0), json=middleware_payload(name="Same"),
                           headers=owner_headers).status_code == 200
        response = client.post(middlewares_url(fake_app.app_id, 0), json=middleware_payload(name="Same"),
                               headers=owner_headers)
        assert response.status_code == 422
        assert "already exists" in response.json()["detail"]

    def test_type_cannot_change_on_update(self, client, fake_app, owner_headers, db):
        db.flush()
        mid = client.post(middlewares_url(fake_app.app_id, 0), json=middleware_payload(),
                          headers=owner_headers).json()["middleware_id"]
        response = client.post(
            middlewares_url(fake_app.app_id, mid),
            json=middleware_payload(middleware_type="model_call_limit", config={"max_calls": 3}),
            headers=owner_headers,
        )
        assert response.status_code == 422

    def test_ai_service_of_same_app_is_accepted(self, client, fake_app, fake_ai_service, owner_headers, db):
        db.flush()
        response = client.post(
            middlewares_url(fake_app.app_id, 0),
            json=middleware_payload(
                middleware_type="summarization",
                config={"summarization_model": f"ai_service:{fake_ai_service.service_id}"},
            ),
            headers=owner_headers,
        )
        assert response.status_code == 200

    def test_ai_service_of_other_app_is_rejected(self, client, fake_app, other_app, owner_headers, db):
        from models.ai_service import AIService

        foreign = AIService(name="Foreign", provider="OpenAI", api_key="sk-x",  # pragma: allowlist secret
                            app_id=other_app.app_id)
        db.add(foreign)
        db.flush()
        response = client.post(
            middlewares_url(fake_app.app_id, 0),
            json=middleware_payload(
                middleware_type="pii",
                config={"pii_types": ["email"],
                        "llm_detector": {"enabled": True, "ai_service": f"ai_service:{foreign.service_id}"}},
            ),
            headers=owner_headers,
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Agent middleware selection and cascade deletion
# ---------------------------------------------------------------------------

def _agent_payload(fake_ai_service, middleware_ids, has_memory=False):
    return {
        "name": "Agent with middlewares",
        "service_id": fake_ai_service.service_id,
        "has_memory": has_memory,
        "middleware_ids": middleware_ids,
    }


class TestAgentMiddlewareSelection:
    def _create(self, client, app_id, headers, **kw):
        response = client.post(middlewares_url(app_id, 0), json=middleware_payload(**kw), headers=headers)
        assert response.status_code == 200, response.text
        return response.json()["middleware_id"]

    def test_order_is_preserved(self, client, fake_app, fake_ai_service, owner_headers, db):
        db.flush()
        a = self._create(client, fake_app.app_id, owner_headers, name="Guard")
        b = self._create(client, fake_app.app_id, owner_headers, name="Limit",
                         middleware_type="tool_call_limit", config={"max_calls": 5})
        response = client.post(f"/internal/apps/{fake_app.app_id}/agents/0",
                               json=_agent_payload(fake_ai_service, [b, a]), headers=owner_headers)
        assert response.status_code in (200, 201), response.text
        assert response.json()["middleware_ids"] == [b, a]

    def test_same_type_twice_is_rejected(self, client, fake_app, fake_ai_service, owner_headers, db):
        db.flush()
        a = self._create(client, fake_app.app_id, owner_headers, name="Guard A")
        b = self._create(client, fake_app.app_id, owner_headers, name="Guard B")
        response = client.post(f"/internal/apps/{fake_app.app_id}/agents/0",
                               json=_agent_payload(fake_ai_service, [a, b]), headers=owner_headers)
        assert response.status_code == 400
        assert "Only one guardrails" in response.json()["detail"]

    def test_middleware_of_other_app_is_rejected(
        self, client, fake_app, other_app, fake_ai_service, owner_headers, db
    ):
        db.flush()
        foreign = self._create(client, other_app.app_id, owner_headers, name="Foreign")
        response = client.post(f"/internal/apps/{fake_app.app_id}/agents/0",
                               json=_agent_payload(fake_ai_service, [foreign]), headers=owner_headers)
        assert response.status_code == 400

    def test_hitl_requires_memory(self, client, fake_app, fake_ai_service, owner_headers, db):
        db.flush()
        hitl = self._create(client, fake_app.app_id, owner_headers, name="Approve",
                            middleware_type="human_in_the_loop",
                            config={"interrupt_on": {"search": {"allowed_decisions": ["approve", "reject"]}}})
        url = f"/internal/apps/{fake_app.app_id}/agents/0"
        assert client.post(url, json=_agent_payload(fake_ai_service, [hitl]),
                           headers=owner_headers).status_code == 400
        assert client.post(url, json=_agent_payload(fake_ai_service, [hitl], has_memory=True),
                           headers=owner_headers).status_code in (200, 201)

    def test_omitting_middleware_ids_keeps_selection(self, client, fake_app, fake_ai_service, owner_headers, db):
        db.flush()
        a = self._create(client, fake_app.app_id, owner_headers, name="Guard")
        agent = client.post(f"/internal/apps/{fake_app.app_id}/agents/0",
                            json=_agent_payload(fake_ai_service, [a]), headers=owner_headers).json()
        payload = _agent_payload(fake_ai_service, None)
        payload.pop("middleware_ids")
        payload["name"] = "Renamed"
        response = client.post(f"/internal/apps/{fake_app.app_id}/agents/{agent['agent_id']}",
                               json=payload, headers=owner_headers)
        assert response.json()["middleware_ids"] == [a]


class TestCascadeDeletion:
    def test_delete_agent_with_middlewares(self, client, fake_app, fake_ai_service, owner_headers, db):
        db.flush()
        mid = client.post(middlewares_url(fake_app.app_id, 0), json=middleware_payload(),
                          headers=owner_headers).json()["middleware_id"]
        agent = client.post(f"/internal/apps/{fake_app.app_id}/agents/0",
                            json=_agent_payload(fake_ai_service, [mid]), headers=owner_headers).json()

        response = client.delete(f"/internal/apps/{fake_app.app_id}/agents/{agent['agent_id']}",
                                 headers=owner_headers)

        assert response.status_code == 200, response.text
        # The middleware itself survives; only the association is gone.
        assert client.get(middlewares_url(fake_app.app_id, mid), headers=owner_headers).status_code == 200

    def test_delete_middleware_used_by_agent(self, client, fake_app, fake_ai_service, owner_headers, db):
        db.flush()
        mid = client.post(middlewares_url(fake_app.app_id, 0), json=middleware_payload(),
                          headers=owner_headers).json()["middleware_id"]
        agent = client.post(f"/internal/apps/{fake_app.app_id}/agents/0",
                            json=_agent_payload(fake_ai_service, [mid]), headers=owner_headers).json()

        assert client.delete(middlewares_url(fake_app.app_id, mid), headers=owner_headers).status_code == 200
        detail = client.get(f"/internal/apps/{fake_app.app_id}/agents/{agent['agent_id']}",
                            headers=owner_headers).json()
        assert detail["middleware_ids"] == []

    def test_delete_app_with_middlewares(self, client, fake_app, fake_ai_service, owner_headers, db):
        db.flush()
        mid = client.post(middlewares_url(fake_app.app_id, 0), json=middleware_payload(),
                          headers=owner_headers).json()["middleware_id"]
        client.post(f"/internal/apps/{fake_app.app_id}/agents/0",
                    json=_agent_payload(fake_ai_service, [mid]), headers=owner_headers)

        response = client.delete(f"/internal/apps/{fake_app.app_id}", headers=owner_headers)

        assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# Delete middleware
# ---------------------------------------------------------------------------

class TestDeleteMiddleware:
    def test_delete_removes_middleware(self, client, fake_app, owner_headers, db):
        db.flush()
        create_resp = client.post(
            middlewares_url(fake_app.app_id, 0),
            json=middleware_payload(),
            headers=owner_headers,
        )
        middleware_id = create_resp.json()["middleware_id"]

        delete_resp = client.delete(middlewares_url(fake_app.app_id, middleware_id), headers=owner_headers)
        assert delete_resp.status_code == 200

        get_resp = client.get(middlewares_url(fake_app.app_id, middleware_id), headers=owner_headers)
        assert get_resp.status_code == 404

    def test_delete_returns_404_for_missing_middleware(self, client, fake_app, owner_headers, db):
        db.flush()
        response = client.delete(middlewares_url(fake_app.app_id, 99999), headers=owner_headers)
        assert response.status_code == 404

    def test_delete_returns_404_for_other_apps_middleware(
        self, client, fake_app, other_app, owner_headers, db
    ):
        db.flush()
        create_resp = client.post(
            middlewares_url(other_app.app_id, 0),
            json=middleware_payload(name="Other App Middleware"),
            headers=owner_headers,
        )
        other_middleware_id = create_resp.json()["middleware_id"]

        response = client.delete(middlewares_url(fake_app.app_id, other_middleware_id), headers=owner_headers)
        assert response.status_code == 404

    def test_delete_requires_administrator_role(self, client, fake_app, outsider_headers, owner_headers, db):
        db.flush()
        create_resp = client.post(
            middlewares_url(fake_app.app_id, 0),
            json=middleware_payload(),
            headers=owner_headers,
        )
        middleware_id = create_resp.json()["middleware_id"]

        response = client.delete(middlewares_url(fake_app.app_id, middleware_id), headers=outsider_headers)
        assert response.status_code == 403
