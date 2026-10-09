"""Integration: System One agents through the internal agents API (real test DB)."""
from datetime import datetime

import pytest

from tests.integration.system_one_helpers import platform_editor  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("platform_editor")]

QUESTIONS = [
    {"key": "urgent", "type": "noul", "instructions": "Is this urgent?"},
    {"key": "area", "type": "choice", "instructions": "Which area?",
     "criteria": [{"key": "billing", "description": "Invoices"}, {"key": "tech"}]},
    {"key": "anger", "type": "score", "instructions": "How angry?", "criteria": ["Calm", "Angry"]},
]


@pytest.fixture
def so_service(db, fake_app):
    from models.system_one_service import SystemOneService

    svc = SystemOneService(name="Nimble", endpoint="http://so.test", description="nimble-latest",
                           extra_config='{"max_concurrency": 1}', app_id=fake_app.app_id, create_date=datetime.now())
    db.add(svc)
    db.flush()
    return svc


def payload(service_id, **kw):
    base = {"name": "Triage", "description": "Classifies tickets", "type": "system_one_agent", "is_tool": True,
            "system_one_service_id": service_id, "questions": QUESTIONS, "max_state_chars": 6000}
    return {**base, **kw}


def agents(app, suffix=""):
    return f"/internal/apps/{app.app_id}/agents/{suffix}"


def create(client, app, headers, service_id, **kw):
    r = client.post(agents(app, "0"), json=payload(service_id, **kw), headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_create_and_read_back(client, fake_app, owner_headers, so_service):
    created = create(client, fake_app, owner_headers, so_service.service_id)
    assert created["type"] == "system_one_agent" and created["is_tool"] is True
    assert created["system_one_service_id"] == so_service.service_id and created["max_state_chars"] == 6000
    assert [q["key"] for q in created["questions"]] == ["urgent", "area", "anger"]
    assert created["questions"][0]["threshold"] == 0.5
    got = client.get(agents(fake_app, str(created["agent_id"])), headers=owner_headers).json()
    assert got["questions"] == created["questions"]
    assert got["system_one_services"] == [{"service_id": so_service.service_id, "name": "Nimble"}]


def test_blank_form_lists_the_apps_system_one_services(client, fake_app, owner_headers, so_service):
    blank = client.get(agents(fake_app, "0"), headers=owner_headers).json()
    assert [s["name"] for s in blank["system_one_services"]] == ["Nimble"]


def test_update_replaces_questions_and_keeps_the_type(client, fake_app, owner_headers, so_service):
    aid = create(client, fake_app, owner_headers, so_service.service_id)["agent_id"]
    r = client.post(agents(fake_app, str(aid)), headers=owner_headers, json=payload(
        so_service.service_id, name="Renamed", max_state_chars=3000,
        questions=[{"key": "only", "type": "noul", "instructions": "q", "threshold": 0.8}]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Renamed" and body["max_state_chars"] == 3000
    assert body["questions"] == [{"key": "only", "type": "noul", "instructions": "q", "threshold": 0.8}]


def test_service_from_another_app_is_rejected(client, db, fake_app, fake_user, owner_headers):
    from models.app import App
    from models.system_one_service import SystemOneService

    other = App(name="Other", slug="other-so-agents", owner_id=fake_user.user_id)
    db.add(other)
    db.flush()
    foreign = SystemOneService(name="Foreign", endpoint="http://x", app_id=other.app_id, create_date=datetime.now())
    db.add(foreign)
    db.flush()
    r = client.post(agents(fake_app, "0"), json=payload(foreign.service_id), headers=owner_headers)
    assert r.status_code == 400 and "System One service" in r.json()["detail"]


@pytest.mark.parametrize("override,expected", [
    ({"questions": []}, 422), ({"questions": [{"key": "a", "type": "noul", "instructions": ""}]}, 422),
    ({"max_state_chars": 10}, 422), ({"system_one_service_id": None}, 400),
])
def test_invalid_payloads(client, fake_app, owner_headers, so_service, override, expected):
    body = payload(so_service.service_id, **override)
    r = client.post(agents(fake_app, "0"), json=body, headers=owner_headers)
    assert r.status_code == expected, r.text


def test_the_type_of_an_existing_agent_cannot_change(client, fake_app, owner_headers, so_service):
    aid = create(client, fake_app, owner_headers, so_service.service_id)["agent_id"]
    r = client.post(agents(fake_app, str(aid)), json={"name": "x", "type": "agent"}, headers=owner_headers)
    assert r.status_code == 400 and "type" in r.json()["detail"]

    normal = client.post(agents(fake_app, "0"), json={"name": "Plain", "type": "agent"}, headers=owner_headers).json()
    r = client.post(agents(fake_app, str(normal["agent_id"])), json=payload(so_service.service_id), headers=owner_headers)
    assert r.status_code == 400 and "type" in r.json()["detail"]


def test_delete_agent_removes_its_rows_and_frees_the_service(client, db, fake_app, owner_headers, so_service):
    from models.system_one_agent import SystemOneAgent

    aid = create(client, fake_app, owner_headers, so_service.service_id)["agent_id"]
    assert client.delete(agents(fake_app, str(aid)), headers=owner_headers).status_code == 200
    assert db.query(SystemOneAgent).filter(SystemOneAgent.agent_id == aid).count() == 0
    assert client.delete(f"/internal/apps/{fake_app.app_id}/system-one-services/{so_service.service_id}",
                         headers=owner_headers).status_code == 200


def test_deleting_the_app_removes_agents_then_services(client, db, fake_app, owner_headers, so_service):
    from models.system_one_agent import SystemOneAgent
    from models.system_one_service import SystemOneService

    aid = create(client, fake_app, owner_headers, so_service.service_id)["agent_id"]
    sid, app_id = so_service.service_id, fake_app.app_id
    r = client.delete(f"/internal/apps/{app_id}", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert db.query(SystemOneAgent).filter(SystemOneAgent.agent_id == aid).count() == 0
    assert db.query(SystemOneService).filter(SystemOneService.service_id == sid).count() == 0
