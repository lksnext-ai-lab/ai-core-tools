"""
Integration tests for per-agent metrics endpoints.

Tests:
  1. EDITOR can access per-agent metrics (200)
  2. VIEWER is forbidden (403)
  3. Cross-app agent lookup returns 404
  4-10. Response structure checks for each per-agent endpoint
  10. Invalid range returns 400
"""
import uuid
import pytest
from datetime import datetime, timedelta
from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
from models.agent_execution_event import AgentExecutionEvent
from tests.factories import configure_factories, UserFactory, AppFactory, AIServiceFactory, AgentFactory


# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_collab(db, app_id, user_id, role: CollaborationRole, invited_by):
    collab = AppCollaborator(
        app_id=app_id,
        user_id=user_id,
        role=role,
        status=CollaborationStatus.ACCEPTED,
        invited_by=invited_by,
        invited_at=datetime.utcnow(),
        accepted_at=datetime.utcnow(),
    )
    db.add(collab)
    db.flush()
    return collab


def _login(client, email):
    resp = client.post("/internal/auth/dev-login", json={"email": email})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _seed_events(db, app_id, agent_id, user_id, count=6):
    """Insert AgentExecutionEvent rows for the given app/agent."""
    now = datetime.utcnow()
    statuses = ["SUCCESS", "SUCCESS", "ERROR", "SUCCESS", "SUCCESS", "ERROR"]
    parent_id = uuid.uuid4()
    parent = AgentExecutionEvent(
        event_id=parent_id,
        app_id=app_id,
        agent_id=agent_id,
        user_id=user_id,
        caller_type="INTERNAL_PLAYGROUND",
        parent_execution_id=None,
        started_at=now - timedelta(hours=count + 1),
        finished_at=now - timedelta(hours=count + 1) + timedelta(seconds=2),
        duration_ms=2000,
        status="SUCCESS",
        input_tokens=200,
        output_tokens=100,
        total_tokens=300,
    )
    db.add(parent)
    db.flush()

    for i in range(count):
        caller = "AGENT_AS_TOOL" if i % 3 == 0 else "INTERNAL_PLAYGROUND"
        parent_ref = parent_id if caller == "AGENT_AS_TOOL" else None
        evt = AgentExecutionEvent(
            event_id=uuid.uuid4(),
            app_id=app_id,
            agent_id=agent_id,
            user_id=user_id,
            caller_type=caller,
            parent_execution_id=parent_ref,
            started_at=now - timedelta(hours=i),
            finished_at=now - timedelta(hours=i) + timedelta(seconds=1 + i),
            duration_ms=1000 + i * 200,
            status=statuses[i % len(statuses)],
            error_code="ValueError" if statuses[i % len(statuses)] == "ERROR" else None,
            input_tokens=100 + i * 10,
            output_tokens=50 + i * 5,
            total_tokens=150 + i * 15,
        )
        db.add(evt)
    db.flush()


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def editor_user(db, fake_app, fake_user):
    configure_factories(db)
    user = UserFactory(email="editor-agent-metrics@mattin-test.com", name="Editor User")
    _make_collab(db, fake_app.app_id, user.user_id,
                 CollaborationRole.EDITOR, fake_user.user_id)
    return user


@pytest.fixture
def editor_headers(db, client, fake_app, fake_user):
    configure_factories(db)
    user = UserFactory(email="editor-agent-metrics2@mattin-test.com", name="Editor User 2")
    _make_collab(db, fake_app.app_id, user.user_id,
                 CollaborationRole.EDITOR, fake_user.user_id)
    return _login(client, user.email)


@pytest.fixture
def viewer_headers(db, client, fake_app, fake_user):
    configure_factories(db)
    user = UserFactory(email="viewer-agent-metrics@mattin-test.com", name="Viewer User")
    _make_collab(db, fake_app.app_id, user.user_id,
                 CollaborationRole.VIEWER, fake_user.user_id)
    return _login(client, user.email)


@pytest.fixture
def seeded_events(db, fake_app, fake_agent, fake_user):
    _seed_events(db, fake_app.app_id, fake_agent.agent_id, fake_user.user_id)


# ── Tests ─────────────────────────────────────────────────────────────────


class TestAgentSummaryEndpoint:
    def test_editor_ok(self, client, fake_app, fake_agent, seeded_events, editor_headers):
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}/metrics/summary?range=7d",
            headers=editor_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "executions" in data
        assert isinstance(data["error_rate"], float)
        assert "total_tokens" in data

    def test_viewer_forbidden(self, client, fake_app, fake_agent, viewer_headers):
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}/metrics/summary?range=7d",
            headers=viewer_headers,
        )
        assert resp.status_code == 403

    def test_cross_app_404(self, client, db, fake_app, fake_agent, fake_user):
        """An agent belonging to App A queried via App B's URL returns 404."""
        configure_factories(db)
        # Create a second app with a different owner
        other_user = UserFactory(email="other-owner-metrics@mattin-test.com", name="Other Owner")
        other_app = AppFactory(owner=other_user, owner_id=other_user.user_id)
        # Create a cross-app editor: a user who is an EDITOR in both apps
        cross_user = UserFactory(email="cross-editor-metrics@mattin-test.com", name="Cross Editor")
        _make_collab(db, fake_app.app_id, cross_user.user_id,
                     CollaborationRole.EDITOR, fake_user.user_id)
        _make_collab(db, other_app.app_id, cross_user.user_id,
                     CollaborationRole.EDITOR, other_user.user_id)
        # Log in as cross_user (who has EDITOR access to other_app)
        cross_headers = _login(client, cross_user.email)
        # Query fake_agent (which belongs to fake_app) via other_app's URL
        # The service should return 404 since fake_agent.app_id != other_app.app_id
        resp = client.get(
            f"/internal/apps/{other_app.app_id}/agents/{fake_agent.agent_id}/metrics/summary?range=7d",
            headers=cross_headers,
        )
        assert resp.status_code == 404


class TestAgentExecutionsEndpoint:
    def test_series_structure(self, client, fake_app, fake_agent, seeded_events, editor_headers):
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}/metrics/executions?range=7d",
            headers=editor_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "series" in data
        assert isinstance(data["series"], list)
        if data["series"]:
            item = data["series"][0]
            assert "ts" in item
            assert "root" in item
            assert "as_tool" in item


class TestAgentTokensEndpoint:
    def test_series_structure(self, client, fake_app, fake_agent, seeded_events, editor_headers):
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}/metrics/tokens?range=7d",
            headers=editor_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "series" in data
        assert isinstance(data["series"], list)
        if data["series"]:
            item = data["series"][0]
            assert "ts" in item
            assert "input" in item
            assert "output" in item


class TestAgentErrorsEndpoint:
    def test_structure(self, client, fake_app, fake_agent, seeded_events, editor_headers):
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}/metrics/errors?range=7d",
            headers=editor_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "series" in data
        assert "by_code" in data
        assert isinstance(data["series"], list)
        assert isinstance(data["by_code"], list)


class TestAgentLatencyEndpoint:
    def test_structure(self, client, fake_app, fake_agent, seeded_events, editor_headers):
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}/metrics/latency?range=7d",
            headers=editor_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "series" in data
        assert isinstance(data["series"], list)
        if data["series"]:
            item = data["series"][0]
            assert "ts" in item
            assert "p50" in item
            assert "p95" in item
            assert "p99" in item


class TestAgentToolsEndpoint:
    def test_structure(self, client, fake_app, fake_agent, seeded_events, editor_headers):
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}/metrics/tools?range=7d",
            headers=editor_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "tools" in data
        assert isinstance(data["tools"], list)
        # If tools are present, verify structure
        for tool in data["tools"]:
            assert "tool_name" in tool
            assert "tool_type" in tool
            assert "calls" in tool


class TestAgentUsersEndpoint:
    def test_structure(self, client, fake_app, fake_agent, seeded_events, editor_headers):
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}/metrics/users?range=7d",
            headers=editor_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "users" in data
        assert isinstance(data["users"], list)


class TestInvalidRangePerAgent:
    def test_invalid_range(self, client, fake_app, fake_agent, editor_headers):
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}/metrics/summary?range=invalid",
            headers=editor_headers,
        )
        assert resp.status_code == 400
        assert "Invalid range" in resp.json().get("detail", "")
