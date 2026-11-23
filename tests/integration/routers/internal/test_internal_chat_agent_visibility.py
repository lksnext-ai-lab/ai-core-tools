"""Integration: the hidden internal chat agent is invisible through the agents API (FR-13, AC-14)."""

import pytest

from models.agent import AGENT_KIND_INTERNAL_CHAT
from tests.factories import AIServiceFactory, AgentFactory, configure_factories


@pytest.fixture
def internal_agent(db, fake_app):
    configure_factories(db)
    ai_service = AIServiceFactory(app=fake_app)
    agent = AgentFactory(
        app=fake_app, ai_service=ai_service, name="__internal_chat__", kind=AGENT_KIND_INTERNAL_CHAT,
    )
    db.flush()
    return agent


def _base(fake_app) -> str:
    return f"/internal/apps/{fake_app.app_id}/agents"


def test_export_internal_agent_matches_missing_agent(client, fake_app, fake_agent, internal_agent, owner_headers, db):
    db.flush()
    missing = client.post(f"{_base(fake_app)}/99999999/export", headers=owner_headers)
    hidden = client.post(f"{_base(fake_app)}/{internal_agent.agent_id}/export", headers=owner_headers)
    assert missing.status_code == 404
    assert hidden.status_code == missing.status_code
    assert hidden.json() == missing.json()


def test_export_standard_agent_still_works(client, fake_app, fake_agent, internal_agent, owner_headers, db):
    db.flush()
    response = client.post(f"{_base(fake_app)}/{fake_agent.agent_id}/export", headers=owner_headers)
    assert response.status_code == 200


def test_listing_excludes_internal_agent(client, fake_app, fake_agent, internal_agent, owner_headers, db):
    db.flush()
    response = client.get(_base(fake_app), headers=owner_headers)
    assert response.status_code == 200
    ids = [a["agent_id"] for a in response.json()]
    assert fake_agent.agent_id in ids
    assert internal_agent.agent_id not in ids


def test_detail_of_internal_agent_is_404(client, fake_app, internal_agent, owner_headers, db):
    db.flush()
    response = client.get(f"{_base(fake_app)}/{internal_agent.agent_id}", headers=owner_headers)
    assert response.status_code == 404


def test_delete_internal_agent_is_404_and_row_survives(client, fake_app, fake_user, internal_agent, owner_headers, db):
    fake_user.platform_role = "editor"
    db.flush()
    response = client.delete(f"{_base(fake_app)}/{internal_agent.agent_id}", headers=owner_headers)
    assert response.status_code == 404
    from models.agent import Agent

    assert db.get(Agent, internal_agent.agent_id) is not None
