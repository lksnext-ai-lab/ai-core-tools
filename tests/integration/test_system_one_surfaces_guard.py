"""System One agents are evaluators, not chat agents: they must stay out of the chat, MCP and scheduler surfaces."""
from datetime import datetime

import pytest

from tests.integration.system_one_helpers import platform_editor  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("platform_editor")]


@pytest.fixture
def so_agent(db, fake_app):
    from models.system_one_agent import SystemOneAgent
    from models.system_one_service import SystemOneService

    svc = SystemOneService(name="Nimble", endpoint="http://so.test", app_id=fake_app.app_id, create_date=datetime.now())
    db.add(svc)
    db.flush()
    agent = SystemOneAgent(name="Triage", app_id=fake_app.app_id, system_one_service_id=svc.service_id, is_tool=True,
                           questions=[{"key": "u", "type": "noul", "instructions": "q"}], create_date=datetime.now())
    db.add(agent)
    db.flush()
    return agent


# ------------------------------------------------------------------------ MCP

def test_mcp_tool_agent_list_does_not_offer_system_one_agents(client, fake_app, fake_agent, so_agent, owner_headers, db):
    fake_agent.is_tool = True
    db.flush()
    r = client.get(f"/internal/apps/{fake_app.app_id}/mcp-servers/tool-agents", headers=owner_headers)
    assert r.status_code == 200
    ids = {a["agent_id"] for a in r.json()}
    assert fake_agent.agent_id in ids and so_agent.agent_id not in ids


def test_an_mcp_server_cannot_be_given_a_system_one_agent(client, fake_app, fake_agent, so_agent, owner_headers, db):
    fake_agent.is_tool = True
    db.flush()
    r = client.post(f"/internal/apps/{fake_app.app_id}/mcp-servers/", headers=owner_headers,
                    json={"name": "srv", "agent_ids": [fake_agent.agent_id, so_agent.agent_id]})
    assert r.status_code == 201, r.text
    assert [a["agent_id"] for a in r.json()["agents"]] == [fake_agent.agent_id]


# ---------------------------------------------------------------------- openai

def test_the_openai_model_list_does_not_offer_system_one_agents(client, db, fake_app, fake_agent, so_agent, fake_api_key):
    fake_app.enable_openai_api = True
    db.flush()
    r = client.get(f"/public/v1/app/{fake_app.app_id}/openai/v1/models", headers={"X-API-KEY": fake_api_key.key})
    assert r.status_code == 200
    ids = {m["id"] for m in r.json()["data"]}
    assert str(fake_agent.agent_id) in ids and str(so_agent.agent_id) not in ids


# ------------------------------------------------------------------------ chat

def test_the_public_chat_route_rejects_a_system_one_agent_with_a_pointer_to_evaluate(client, fake_app, so_agent, fake_api_key):
    r = client.post(f"/public/v1/app/{fake_app.app_id}/chat/{so_agent.agent_id}/call",
                    headers={"X-API-KEY": fake_api_key.key}, data={"message": "hello"})
    assert r.status_code == 400
    assert "evaluate" in r.json()["detail"].lower()


# ------------------------------------------------------------------- scheduler

def test_a_scheduled_task_cannot_target_a_system_one_agent(db, fake_app, fake_user, so_agent):
    from services.scheduled_task_service import ScheduledTaskService

    with pytest.raises(ValueError, match="System One"):
        ScheduledTaskService(db).create(app_id=fake_app.app_id, created_by=fake_user.user_id, data={
            "name": "nightly", "agent_id": so_agent.agent_id, "cron_expression": "0 3 * * *"})


# ------------------------------------------------ public generic update stays off System One agents

def test_the_generic_public_update_refuses_a_system_one_agent(client, fake_app, so_agent, fake_api_key, db):
    r = client.put(f"/public/v1/app/{fake_app.app_id}/agents/{so_agent.agent_id}",
                   headers={"X-API-KEY": fake_api_key.key}, json={"name": "Renamed"})
    assert r.status_code == 400
    assert "system one" in r.json()["detail"].lower()
    db.refresh(so_agent)
    assert so_agent.name == "Triage" and so_agent.is_tool is True
