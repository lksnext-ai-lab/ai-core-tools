"""Integration tests for the metrics dashboards API (system, app and agent scopes).

Requires the test DB (port 5433).
"""
import uuid
from datetime import datetime, timedelta

import pytest

from models.agent import Agent
from models.agent_execution_event import AgentExecutionEvent
from models.agent_tool_call import AgentToolCall
from models.app import App
from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
from tests.factories import UserFactory, configure_factories


def _headers(user):
    from utils.local_auth_tokens import mint_access_token

    token, _ = mint_access_token(user.user_id, user.email, user.name)
    return {"Authorization": f"Bearer {token}"}


def _user_with_role(db, app_id, owner_id, role, email):
    configure_factories(db)
    user = UserFactory(email=email, name=email.split("@")[0])
    db.add(AppCollaborator(
        app_id=app_id, user_id=user.user_id, role=role, status=CollaborationStatus.ACCEPTED,
        invited_by=owner_id, invited_at=datetime.utcnow(), accepted_at=datetime.utcnow(),
    ))
    db.flush()
    return user


def _event(db, app_id, agent_id, *, minutes_ago=30, status="SUCCESS", parent=None, user_id=None,
           caller="INTERNAL_PLAYGROUND", tokens=(100, 50), llm_calls=1, duration=1000, ttft=None,
           model="gpt-5-mini", error_code=None, tools=()):
    event = AgentExecutionEvent(
        event_id=uuid.uuid4(), app_id=app_id, agent_id=agent_id, user_id=user_id,
        caller_type=caller, parent_execution_id=parent,
        started_at=datetime.utcnow() - timedelta(minutes=minutes_ago),
        duration_ms=duration, time_to_first_token_ms=ttft, status=status, error_code=error_code,
        error_message=f"{error_code} happened" if error_code else None,
        model_name=model, provider="OpenAI", llm_calls=llm_calls,
        input_tokens=tokens[0], output_tokens=tokens[1], total_tokens=sum(tokens),
    )
    db.add(event)
    db.flush()
    for name, tool_type, tool_status, ms in tools:
        db.add(AgentToolCall(
            event_id=event.event_id, tool_name=name, tool_type=tool_type, status=tool_status,
            duration_ms=ms, started_at=event.started_at,
        ))
    db.flush()
    return event


@pytest.fixture
def other_agent(db, fake_app, fake_ai_service):
    agent = Agent(name="Helper Agent", description="", system_prompt="", app_id=fake_app.app_id,
                  service_id=fake_ai_service.service_id, has_memory=False, temperature=0.7)
    db.add(agent)
    db.flush()
    return agent


@pytest.fixture
def seeded(db, fake_app, fake_agent, other_agent, fake_user):
    app_id = fake_app.app_id
    root = _event(db, app_id, fake_agent.agent_id, user_id=fake_user.user_id, ttft=400, llm_calls=2,
                  tools=[("retrieve", "RETRIEVER", "SUCCESS", 120), ("helper_agent", "AGENT", "SUCCESS", 900)])
    # Sub-agent run: its own tokens, linked to the root execution.
    _event(db, app_id, other_agent.agent_id, parent=root.event_id, caller="AGENT_AS_TOOL", tokens=(40, 10))
    _event(db, app_id, fake_agent.agent_id, caller="PUBLIC_API", status="ERROR", error_code="RateLimitError",
           tokens=(0, 0), llm_calls=1, tools=[("remote_lookup", "MCP", "ERROR", 50)])
    _event(db, app_id, fake_agent.agent_id, caller="MCP", model="claude-sonnet-5")
    # Previous 24h window, for the comparison.
    _event(db, app_id, fake_agent.agent_id, minutes_ago=60 * 30)
    return root


@pytest.fixture
def platform_admin(db):
    configure_factories(db)
    user = UserFactory(email="platform-admin-metrics@mattin-test.com", name="Platform Admin")
    user.platform_role = "admin"
    db.flush()
    return user


class TestAppScope:

    def test_summary_counts_and_previous_window(self, client, fake_app, seeded, owner_headers):
        resp = client.get(f"/internal/apps/{fake_app.app_id}/metrics/summary?range=24h", headers=owner_headers)
        assert resp.status_code == 200, resp.text
        current, previous = resp.json()["current"], resp.json()["previous"]
        assert current["executions"] == 3          # root runs only
        assert current["subagent_calls"] == 1
        assert current["errors"] == 1
        assert current["error_rate"] == pytest.approx(1 / 3)
        # Tokens sum every run (each records only its own LLM calls): 150 + 50 + 0 + 150.
        assert current["total_tokens"] == 350
        assert current["llm_calls"] == 5
        assert current["ttft_p50_ms"] == 400
        assert current["tool_calls"] == 3 and current["tool_errors"] == 1
        assert current["active_agents"] == 2
        assert previous["executions"] == 1

    def test_timeseries_is_gap_filled(self, client, fake_app, seeded, owner_headers):
        resp = client.get(f"/internal/apps/{fake_app.app_id}/metrics/timeseries?range=24h", headers=owner_headers)
        body = resp.json()
        assert body["bucket"] == "1h"
        assert len(body["points"]) in (24, 25)
        assert sum(p["executions"] for p in body["points"]) == 3
        assert sum(p["subagent_calls"] for p in body["points"]) == 1

    def test_breakdown_by_channel_and_model(self, client, fake_app, seeded, owner_headers):
        base = f"/internal/apps/{fake_app.app_id}/metrics/breakdown"
        channels = {i["key"]: i for i in client.get(f"{base}/channel?range=24h", headers=owner_headers).json()["items"]}
        assert set(channels) == {"INTERNAL_PLAYGROUND", "AGENT_AS_TOOL", "PUBLIC_API", "MCP"}
        assert channels["PUBLIC_API"]["errors"] == 1
        models = {i["key"]: i["runs"] for i in client.get(f"{base}/model?range=24h", headers=owner_headers).json()["items"]}
        assert models == {"gpt-5-mini": 3, "claude-sonnet-5": 1}

    def test_breakdown_by_agent_names_agents(self, client, fake_app, fake_agent, seeded, owner_headers):
        items = client.get(f"/internal/apps/{fake_app.app_id}/metrics/breakdown/agent?range=24h",
                           headers=owner_headers).json()["items"]
        assert items[0]["key"] == str(fake_agent.agent_id)
        assert items[0]["label"] == fake_agent.name
        assert {i["label"] for i in items} == {fake_agent.name, "Helper Agent"}

    def test_app_dimension_not_available_in_app_scope(self, client, fake_app, seeded, owner_headers):
        resp = client.get(f"/internal/apps/{fake_app.app_id}/metrics/breakdown/app", headers=owner_headers)
        assert resp.status_code == 400

    def test_tools(self, client, fake_app, seeded, owner_headers):
        tools = {t["tool_name"]: t for t in client.get(
            f"/internal/apps/{fake_app.app_id}/metrics/tools?range=24h", headers=owner_headers).json()["tools"]}
        assert tools["retrieve"]["tool_type"] == "RETRIEVER"
        assert tools["remote_lookup"]["error_rate"] == 1.0
        assert tools["helper_agent"]["avg_duration_ms"] == 900

    def test_errors(self, client, fake_app, seeded, owner_headers):
        body = client.get(f"/internal/apps/{fake_app.app_id}/metrics/errors?range=24h", headers=owner_headers).json()
        assert body["groups"][0]["error_code"] == "RateLimitError"
        assert body["recent"][0]["caller_type"] == "PUBLIC_API"
        assert body["recent"][0]["agent_name"]

    def test_invalid_range_rejected(self, client, fake_app, owner_headers):
        resp = client.get(f"/internal/apps/{fake_app.app_id}/metrics/summary?range=1y", headers=owner_headers)
        assert resp.status_code == 422

    def test_editor_forbidden(self, client, db, fake_app, fake_user, seeded):
        editor = _user_with_role(db, fake_app.app_id, fake_user.user_id, CollaborationRole.EDITOR,
                                 "editor-metrics@mattin-test.com")
        resp = client.get(f"/internal/apps/{fake_app.app_id}/metrics/summary", headers=_headers(editor))
        assert resp.status_code == 403

    def test_administrator_allowed(self, client, db, fake_app, fake_user, seeded):
        admin = _user_with_role(db, fake_app.app_id, fake_user.user_id, CollaborationRole.ADMINISTRATOR,
                                "admin-metrics@mattin-test.com")
        resp = client.get(f"/internal/apps/{fake_app.app_id}/metrics/summary", headers=_headers(admin))
        assert resp.status_code == 200


class TestAgentScope:

    def test_summary_is_limited_to_the_agent(self, client, fake_app, fake_agent, seeded, owner_headers):
        resp = client.get(f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}/metrics/summary?range=24h",
                          headers=owner_headers)
        current = resp.json()["current"]
        assert current["executions"] == 3
        assert current["subagent_calls"] == 0
        assert current["total_tokens"] == 300

    def test_editor_allowed_viewer_forbidden(self, client, db, fake_app, fake_agent, fake_user, seeded):
        url = f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}/metrics/summary"
        editor = _user_with_role(db, fake_app.app_id, fake_user.user_id, CollaborationRole.EDITOR,
                                 "editor-agent-metrics@mattin-test.com")
        viewer = _user_with_role(db, fake_app.app_id, fake_user.user_id, CollaborationRole.VIEWER,
                                 "viewer-agent-metrics@mattin-test.com")
        assert client.get(url, headers=_headers(editor)).status_code == 200
        assert client.get(url, headers=_headers(viewer)).status_code == 403

    def test_agent_of_another_app_is_404(self, client, db, fake_app, fake_user, owner_headers):
        other = App(name="Other", slug="other-metrics-app", owner_id=fake_user.user_id,
                    agent_rate_limit=0, max_file_size_mb=10)
        db.add(other)
        db.flush()
        foreign = Agent(name="Foreign", description="", system_prompt="", app_id=other.app_id,
                        has_memory=False, temperature=0.7)
        db.add(foreign)
        db.flush()
        resp = client.get(f"/internal/apps/{fake_app.app_id}/agents/{foreign.agent_id}/metrics/summary",
                          headers=owner_headers)
        assert resp.status_code == 404


class TestSystemScope:

    def test_platform_admin_sees_all_apps(self, client, fake_app, seeded, platform_admin):
        resp = client.get("/internal/admin/metrics/summary?range=24h", headers=_headers(platform_admin))
        assert resp.status_code == 200, resp.text
        assert resp.json()["current"]["active_apps"] >= 1
        apps = client.get("/internal/admin/metrics/breakdown/app?range=24h",
                          headers=_headers(platform_admin)).json()["items"]
        assert str(fake_app.app_id) in {i["key"] for i in apps}

    def test_agent_breakdown_carries_app_name(self, client, fake_app, seeded, platform_admin):
        items = client.get("/internal/admin/metrics/breakdown/agent?range=24h",
                           headers=_headers(platform_admin)).json()["items"]
        assert all(i["secondary_label"] == fake_app.name for i in items)

    def test_app_owner_is_not_platform_admin(self, client, seeded, owner_headers):
        assert client.get("/internal/admin/metrics/summary", headers=owner_headers).status_code == 403
