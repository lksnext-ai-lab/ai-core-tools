"""Integration tests for POST /internal/apps/{app_id}/sandbox-services/{id}/move-usage (real DB)."""

import pytest

from tests.integration.routers.internal._eos_helpers import make_agent, make_app, past, sandbox_service

pytestmark = pytest.mark.integration


def _url(app, service):
    return f"/internal/apps/{app.app_id}/sandbox-services/{service.service_id}/move-usage"


def _body(target, agents=1, apps=1):
    return {"target_service_id": target.service_id, "expected_agent_count": agents, "expected_app_count": apps}


def _state(db, app, direct, inheriting):
    db.expire_all()
    db.refresh(app)
    db.refresh(direct)
    db.refresh(inheriting)
    return app.default_sandbox_service_id, direct.sandbox_service_id, inheriting.sandbox_service_id


@pytest.fixture
def scenario(db, fake_app):
    source = sandbox_service(db, None, "mv-system-source")  # system-wide, shared by both apps
    target = sandbox_service(db, None, "mv-system-target")
    other_app = make_app(db)

    def build(app):
        direct = make_agent(db, app, None, sandbox_service_id=source.service_id, enable_code_interpreter=True)
        inheriting = make_agent(db, app, None, sandbox_service_id=None, enable_code_interpreter=True)
        app.default_sandbox_service_id = source.service_id
        db.flush()
        return direct, inheriting

    a_direct, a_inh = build(fake_app)
    b_direct, b_inh = build(other_app)
    # Commit (releases the session savepoint) so the endpoint's rollback on a 409 only undoes the move,
    # not this fixture data.
    db.commit()
    return dict(source=source, target=target, app=fake_app, other=other_app,
                a=(a_direct, a_inh), b=(b_direct, b_inh))


class TestMoveSandboxUsage:
    def _assert_unchanged(self, db, s):
        src = s["source"].service_id
        assert _state(db, s["app"], *s["a"]) == (src, src, None)
        assert _state(db, s["other"], *s["b"]) == (src, src, None)

    def test_moves_only_direct_agents_and_default_of_the_app(self, client, db, scenario, owner_headers):
        s = scenario
        resp = client.post(_url(s["app"], s["source"]), json=_body(s["target"]), headers=owner_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"moved_agent_ids": [s["a"][0].agent_id], "updated_app_ids": [s["app"].app_id]}
        tgt, src = s["target"].service_id, s["source"].service_id
        assert _state(db, s["app"], *s["a"]) == (tgt, tgt, None)  # inheriting agent stays NULL
        assert _state(db, s["other"], *s["b"]) == (src, src, None)  # other app untouched

    def test_editor_forbidden(self, client, db, scenario, app_editor_headers):
        resp = client.post(_url(scenario["app"], scenario["source"]), json=_body(scenario["target"]),
                           headers=app_editor_headers)
        assert resp.status_code == 403
        self._assert_unchanged(db, scenario)

    def test_administrator_allowed(self, client, scenario, app_admin_headers):
        resp = client.post(_url(scenario["app"], scenario["source"]), json=_body(scenario["target"]),
                           headers=app_admin_headers)
        assert resp.status_code == 200, resp.text

    @pytest.mark.parametrize("agents,apps", [(2, 1), (0, 1)])
    def test_agent_count_mismatch_conflicts_and_changes_nothing(self, client, db, scenario, owner_headers,
                                                                agents, apps):
        resp = client.post(_url(scenario["app"], scenario["source"]),
                           json=_body(scenario["target"], agents, apps), headers=owner_headers)
        assert resp.status_code == 409, resp.text
        self._assert_unchanged(db, scenario)

    @pytest.mark.parametrize("apps", [0, 2])
    def test_app_count_only_mismatch_conflicts_and_changes_nothing(self, client, db, scenario, owner_headers, apps):
        resp = client.post(_url(scenario["app"], scenario["source"]),
                           json=_body(scenario["target"], 1, apps), headers=owner_headers)
        assert resp.status_code == 409, resp.text
        self._assert_unchanged(db, scenario)

    def test_retired_target_rejected(self, client, db, scenario, owner_headers):
        retired = sandbox_service(db, None, "mv-retired", eos=past(2))
        resp = client.post(_url(scenario["app"], scenario["source"]), json=_body(retired), headers=owner_headers)
        assert 400 <= resp.status_code < 500, resp.text
        self._assert_unchanged(db, scenario)

    def test_target_equal_to_source_rejected(self, client, db, scenario, owner_headers):
        resp = client.post(_url(scenario["app"], scenario["source"]), json=_body(scenario["source"]),
                           headers=owner_headers)
        assert 400 <= resp.status_code < 500, resp.text
        self._assert_unchanged(db, scenario)

    def test_target_from_another_app_rejected(self, client, db, scenario, owner_headers):
        foreign = sandbox_service(db, scenario["other"], "mv-foreign")
        resp = client.post(_url(scenario["app"], scenario["source"]), json=_body(foreign), headers=owner_headers)
        assert 400 <= resp.status_code < 500, resp.text
        self._assert_unchanged(db, scenario)

    def test_source_from_another_app_not_found(self, client, db, scenario, owner_headers):
        foreign = sandbox_service(db, scenario["other"], "mv-foreign-src")
        resp = client.post(_url(scenario["app"], foreign), json=_body(scenario["target"]), headers=owner_headers)
        assert resp.status_code == 404, resp.text
        self._assert_unchanged(db, scenario)
