"""
Integration tests for the App-level metrics endpoints.

These tests require the test DB (port 5433) and the metrics plugin router
to be mounted (it is loaded automatically via entry-point in the test env).
"""
import uuid
import pytest
from datetime import datetime, timedelta
from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
from models.agent_execution_event import AgentExecutionEvent
from tests.factories import configure_factories, UserFactory


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_collab(db, app_id, user_id, role: CollaborationRole, invited_by):
    from datetime import datetime
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


def _seed_events(db, app_id, agent_id, user_id, count=7):
    """Insert a handful of AgentExecutionEvent rows for the given app/agent."""
    now = datetime.utcnow()
    events = []
    statuses = ["SUCCESS", "SUCCESS", "SUCCESS", "SUCCESS", "ERROR", "SUCCESS", "ERROR"]
    # First insert a parent event so sub-calls can reference it
    parent_id = uuid.uuid4()
    parent = AgentExecutionEvent(
        event_id=parent_id,
        app_id=app_id,
        agent_id=agent_id,
        user_id=user_id,
        caller_type="INTERNAL_PLAYGROUND",
        parent_execution_id=None,
        started_at=now - timedelta(hours=count + 1),
        finished_at=now - timedelta(hours=count + 1) + timedelta(seconds=3),
        duration_ms=3000,
        status="SUCCESS",
        input_tokens=200,
        output_tokens=100,
        total_tokens=300,
    )
    db.add(parent)
    db.flush()

    for i in range(count):
        caller = "INTERNAL_PLAYGROUND" if i % 3 != 0 else "AGENT_AS_TOOL"
        parent_ref = parent_id if caller == "AGENT_AS_TOOL" else None
        evt = AgentExecutionEvent(
            event_id=uuid.uuid4(),
            app_id=app_id,
            agent_id=agent_id,
            user_id=user_id,
            caller_type=caller,
            parent_execution_id=parent_ref,
            started_at=now - timedelta(hours=i),
            finished_at=now - timedelta(hours=i) + timedelta(seconds=2),
            duration_ms=2000 + i * 100,
            status=statuses[i % len(statuses)],
            error_code="ValueError" if statuses[i % len(statuses)] == "ERROR" else None,
            input_tokens=100 + i * 10,
            output_tokens=50 + i * 5,
            total_tokens=150 + i * 15,
        )
        db.add(evt)
        events.append(evt)
    db.flush()
    return events


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def admin_headers(db, client, fake_app, fake_user):
    configure_factories(db)
    admin_user = UserFactory(email="admin-metrics@mattin-test.com", name="Admin User")
    _make_collab(db, fake_app.app_id, admin_user.user_id,
                 CollaborationRole.ADMINISTRATOR, fake_user.user_id)
    return _login(client, admin_user.email)


@pytest.fixture
def viewer_headers(db, client, fake_app, fake_user):
    configure_factories(db)
    viewer_user = UserFactory(email="viewer-metrics@mattin-test.com", name="Viewer User")
    _make_collab(db, fake_app.app_id, viewer_user.user_id,
                 CollaborationRole.VIEWER, fake_user.user_id)
    return _login(client, viewer_user.email)


@pytest.fixture
def editor_headers(db, client, fake_app, fake_user):
    configure_factories(db)
    editor_user = UserFactory(email="editor-metrics@mattin-test.com", name="Editor User")
    _make_collab(db, fake_app.app_id, editor_user.user_id,
                 CollaborationRole.EDITOR, fake_user.user_id)
    return _login(client, editor_user.email)


@pytest.fixture
def seeded_events(db, fake_app, fake_agent, fake_user):
    return _seed_events(db, fake_app.app_id, fake_agent.agent_id, fake_user.user_id)


# ── Tests ──────────────────────────────────────────────────────────────────


class TestAppSummaryEndpoint:
    def test_ok_administrator(self, client, fake_app, seeded_events, admin_headers):
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/metrics/summary?range=7d",
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total_executions"] > 0
        assert isinstance(data["error_rate"], float)

    def test_viewer_forbidden(self, client, fake_app, seeded_events, viewer_headers):
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/metrics/summary?range=7d",
            headers=viewer_headers,
        )
        assert resp.status_code == 403

    def test_editor_forbidden(self, client, fake_app, seeded_events, editor_headers):
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/metrics/summary?range=7d",
            headers=editor_headers,
        )
        assert resp.status_code == 403

    def test_owner_ok(self, client, fake_app, seeded_events, owner_headers):
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/metrics/summary?range=7d",
            headers=owner_headers,
        )
        assert resp.status_code == 200

    def test_invalid_range(self, client, fake_app, admin_headers):
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/metrics/summary?range=bad",
            headers=admin_headers,
        )
        assert resp.status_code == 400
        assert "Invalid range" in resp.json().get("detail", "")


class TestAppExecutionsEndpoint:
    def test_ok(self, client, fake_app, seeded_events, admin_headers):
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/metrics/executions?range=7d",
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "series" in data
        assert isinstance(data["series"], list)
        if data["series"]:
            item = data["series"][0]
            assert "ts" in item
            assert "root" in item
            assert "sub" in item
            assert "errors" in item


class TestAppAgentsEndpoint:
    def test_sorted_by_executions(self, client, fake_app, seeded_events, admin_headers):
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/metrics/agents?range=7d",
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        agents = data["agents"]
        # If there are multiple agents, verify descending sort
        if len(agents) > 1:
            for i in range(len(agents) - 1):
                assert agents[i]["executions"] >= agents[i + 1]["executions"]


class TestAppUsersEndpoint:
    def test_limit(self, client, fake_app, seeded_events, admin_headers):
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/metrics/users?range=7d",
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "users" in data
        assert len(data["users"]) <= 20
