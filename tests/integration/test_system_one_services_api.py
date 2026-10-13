"""Integration tests: /internal/apps/{app_id}/system-one-services (real test DB)."""
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from tests.integration.system_one_helpers import platform_editor, viewer_headers  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("platform_editor")]


def payload(**kw):
    base = {"name": "Nimble local", "endpoint": "http://172.16.59.1:8100", "api_key": "secret-token-1234",
            "model": "nimble-latest", "max_concurrency": 1}
    return {**base, **kw}


def url(app, suffix=""):
    return f"/internal/apps/{app.app_id}/system-one-services/{suffix}"


def _create(client, app, headers, **kw):
    r = client.post(url(app, "0"), json=payload(**kw), headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


class TestCrud:
    def test_create_list_get_update_copy_delete(self, client, fake_app, owner_headers):
        created = _create(client, fake_app, owner_headers)
        sid = created["service_id"]
        assert created["endpoint"] == "http://172.16.59.1:8100" and created["api_key"] == "****1234"

        listed = client.get(url(fake_app), headers=owner_headers).json()
        assert [s["name"] for s in listed] == ["Nimble local"]
        assert "secret-token" not in client.get(url(fake_app), headers=owner_headers).text

        got = client.get(url(fake_app, str(sid)), headers=owner_headers)
        assert got.status_code == 200 and "secret-token" not in got.text and got.json()["model"] == "nimble-latest"

        upd = client.post(url(fake_app, str(sid)), json=payload(name="Renamed", api_key="****1234", max_concurrency=2),
                          headers=owner_headers)
        assert upd.status_code == 200 and upd.json()["name"] == "Renamed" and upd.json()["max_concurrency"] == 2

        copy = client.post(url(fake_app, f"{sid}/copy"), headers=owner_headers)
        assert copy.status_code == 200 and copy.json()["name"] == "Renamed Copy"

        assert client.delete(url(fake_app, str(sid)), headers=owner_headers).status_code == 200
        assert client.get(url(fake_app, str(sid)), headers=owner_headers).status_code == 404

    def test_new_service_template(self, client, fake_app, owner_headers):
        r = client.get(url(fake_app, "0"), headers=owner_headers)
        assert r.status_code == 200 and r.json()["model"] == "" and r.json()["service_id"] == 0

    def test_bad_endpoint_is_400(self, client, fake_app, owner_headers):
        r = client.post(url(fake_app, "0"), json=payload(endpoint="ftp://x"), headers=owner_headers)
        assert r.status_code == 400

    def test_invalid_body_is_422(self, client, fake_app, owner_headers):
        assert client.post(url(fake_app, "0"), json=payload(max_concurrency=0), headers=owner_headers).status_code == 422

    def test_unknown_service_is_404(self, client, fake_app, owner_headers):
        assert client.get(url(fake_app, "987654"), headers=owner_headers).status_code == 404
        assert client.post(url(fake_app, "987654"), json=payload(), headers=owner_headers).status_code == 404
        assert client.delete(url(fake_app, "987654"), headers=owner_headers).status_code == 404

    def test_service_of_another_app_is_not_visible(self, client, db, fake_app, fake_user, owner_headers):
        from models.app import App
        from models.system_one_service import SystemOneService

        other = App(name="Other", slug="other-so", owner_id=fake_user.user_id)
        db.add(other)
        db.flush()
        svc = SystemOneService(name="Foreign", endpoint="http://x", app_id=other.app_id, create_date=datetime.now())
        db.add(svc)
        db.flush()
        assert client.get(url(fake_app, str(svc.service_id)), headers=owner_headers).status_code == 404
        assert client.delete(url(fake_app, str(svc.service_id)), headers=owner_headers).status_code == 404


class TestPermissions:
    def test_requires_authentication(self, client, fake_app):
        assert client.get(url(fake_app)).status_code in (401, 403)

    def test_viewer_can_read_but_not_write(self, client, fake_app, owner_headers, viewer_headers):
        sid = _create(client, fake_app, owner_headers)["service_id"]
        assert client.get(url(fake_app), headers=viewer_headers).status_code == 200
        assert client.get(url(fake_app, str(sid)), headers=viewer_headers).status_code == 200
        assert client.post(url(fake_app, "0"), json=payload(), headers=viewer_headers).status_code == 403
        assert client.post(url(fake_app, f"{sid}/copy"), headers=viewer_headers).status_code == 403
        assert client.delete(url(fake_app, str(sid)), headers=viewer_headers).status_code == 403
        assert client.post(url(fake_app, f"{sid}/test"), headers=viewer_headers).status_code == 403
        assert client.post(url(fake_app, "test-connection"), json=payload(), headers=viewer_headers).status_code == 403


class TestDeleteInUse:
    def _agent_using(self, db, fake_app, service_id, name="Triage"):
        from models.system_one_agent import SystemOneAgent

        agent = SystemOneAgent(name=name, app_id=fake_app.app_id, system_one_service_id=service_id,
                               questions=[{"key": "u", "type": "noul", "instructions": "q"}],
                               create_date=datetime.now())
        db.add(agent)
        db.flush()
        return agent

    def test_deleting_a_service_in_use_detaches_its_agents_instead_of_refusing(self, client, db, fake_app, owner_headers):
        sid = _create(client, fake_app, owner_headers)["service_id"]
        agent = self._agent_using(db, fake_app, sid, "Triage")
        r = client.delete(url(fake_app, str(sid)), headers=owner_headers)
        assert r.status_code == 200
        assert r.json()["detached_agents"] == [{"agent_id": agent.agent_id, "name": "Triage"}]
        assert client.get(url(fake_app, str(sid)), headers=owner_headers).status_code == 404
        db.expire_all()
        db.refresh(agent)
        assert agent.system_one_service_id is None and agent.questions       # still there, just without a service

    def test_the_list_warns_how_many_agents_use_each_service(self, client, db, fake_app, owner_headers):
        sid = _create(client, fake_app, owner_headers)["service_id"]
        self._agent_using(db, fake_app, sid, "Triage")
        self._agent_using(db, fake_app, sid, "Validator")
        (item,) = client.get(url(fake_app), headers=owner_headers).json()
        assert item["agent_count"] == 2

    def test_deleting_a_free_service_detaches_nothing(self, client, fake_app, owner_headers):
        sid = _create(client, fake_app, owner_headers)["service_id"]
        r = client.delete(url(fake_app, str(sid)), headers=owner_headers)
        assert r.status_code == 200 and r.json()["detached_agents"] == []


class TestConnection:
    PROBE_OK = {"ok": True, "message": "Connection successful", "models": ["nimble-latest"],
                "limits": {"max_concurrent_requests": 4, "max_questions": 64}}

    def test_test_connection_with_config_returns_models_and_limits_without_the_token(self, client, fake_app, owner_headers):
        with patch("services.system_one_service_service.system_one_client.probe", AsyncMock(return_value=self.PROBE_OK)):
            r = client.post(url(fake_app, "test-connection"), json=payload(), headers=owner_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "success" and body["models"] == ["nimble-latest"]
        assert body["limits"]["max_concurrent_requests"] == 4 and "secret-token" not in r.text

    def test_the_model_list_can_be_requested_with_only_the_url_and_the_token(self, client, fake_app, owner_headers):
        # Step 2 of the wizard lists the models before any model, name or cap exists.
        with patch("services.system_one_service_service.system_one_client.probe", AsyncMock(return_value=self.PROBE_OK)):
            r = client.post(url(fake_app, "test-connection"),
                            json={"endpoint": "http://so.test", "api_key": "tok"}, headers=owner_headers)
        assert r.status_code == 200 and r.json()["models"] == ["nimble-latest"]

    def test_a_server_with_no_model_listing_is_checked_with_one_real_call(self, client, fake_app, owner_headers):
        bare = {"ok": True, "message": "The server answered, but it has no health or model endpoints", "models": [],
                "limits": None, "can_list_models": False}
        check = AsyncMock(return_value={"ok": True, "message": "Connection verified with a real test call"})
        with patch("services.system_one_service_service.system_one_client.probe", AsyncMock(return_value=bare)), \
             patch("services.system_one_service_service.system_one_client.check_model", check):
            r = client.post(url(fake_app, "test-connection"),
                            json={"endpoint": "http://so.test/the-model", "api_key": "tok", "model": "the-model"},
                            headers=owner_headers)
        assert r.status_code == 200 and r.json()["status"] == "success" and r.json()["checked_with_call"] is True
        assert check.await_args.args[0].model == "the-model" and "tok" not in r.text

    def test_edit_mode_recovers_the_stored_token(self, client, fake_app, owner_headers):
        sid = _create(client, fake_app, owner_headers, api_key="stored-token-9999")["service_id"]
        probe = AsyncMock(return_value=self.PROBE_OK)
        with patch("services.system_one_service_service.system_one_client.probe", probe):
            r = client.post(url(fake_app, "test-connection") + f"?service_id={sid}",
                            json=payload(api_key="****9999"), headers=owner_headers)
        assert r.status_code == 200
        probe.assert_awaited_once_with("http://172.16.59.1:8100", "stored-token-9999")

    def test_saved_service_test(self, client, fake_app, owner_headers):
        sid = _create(client, fake_app, owner_headers)["service_id"]
        failing = AsyncMock(return_value={"ok": False, "message": "Cannot connect to the System One server",
                                          "models": [], "limits": None})
        with patch("services.system_one_service_service.system_one_client.probe", failing):
            r = client.post(url(fake_app, f"{sid}/test"), headers=owner_headers)
        assert r.status_code == 200 and r.json()["status"] == "error"
        assert client.post(url(fake_app, "987654/test"), headers=owner_headers).status_code == 404
