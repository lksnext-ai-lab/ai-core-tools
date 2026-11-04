"""Integration tests for sandbox service end-of-service (step_011): AC-22, AC-25, AC-26, AC-27.

Requires the test DB on port 5433.
"""

import pytest

from tests.integration.routers.internal._eos_helpers import (
    ai_service,
    future,
    iso,
    make_agent,
    make_app,
    make_task,
    past,
    same_instant,
    sandbox_payload,
    sandbox_service,
)

pytestmark = pytest.mark.integration


def _base(app):
    return f"/internal/apps/{app.app_id}/sandbox-services"


class TestSandboxServiceCrud:
    """AC-22."""

    def test_app_create_list_detail_update_round_trip(self, client, fake_app, owner_headers):
        eos = future(90)
        resp = client.post(f"{_base(fake_app)}/0", json=sandbox_payload(end_of_service_at=iso(eos),
                                                                         deprecation_notice="Move to Daytona"),
                           headers=owner_headers)
        assert resp.status_code == 200, resp.text
        sid = resp.json()["service_id"]
        assert same_instant(resp.json()["end_of_service_at"], eos)
        assert resp.json()["deprecation_notice"] == "Move to Daytona"
        assert resp.json()["lifecycle_status"] == "active"

        listed = {s["service_id"]: s for s in client.get(_base(fake_app) + "/", headers=owner_headers).json()}
        assert same_instant(listed[sid]["end_of_service_at"], eos)
        assert listed[sid]["deprecation_notice"] == "Move to Daytona"
        detail = client.get(f"{_base(fake_app)}/{sid}", headers=owner_headers).json()
        assert same_instant(detail["end_of_service_at"], eos) and detail["lifecycle_status"] == "active"

        soon = future(4)
        resp = client.post(f"{_base(fake_app)}/{sid}", json=sandbox_payload(end_of_service_at=iso(soon),
                                                                             lifecycle_status="retired"),
                           headers=owner_headers)
        assert resp.status_code == 200, resp.text
        assert same_instant(resp.json()["end_of_service_at"], soon)
        assert resp.json()["lifecycle_status"] == "deprecated"  # client-sent status ignored

        resp = client.post(f"{_base(fake_app)}/{sid}", json=sandbox_payload(end_of_service_at=None,
                                                                             deprecation_notice=None),
                           headers=owner_headers)
        assert resp.json()["end_of_service_at"] is None and resp.json()["lifecycle_status"] == "active"

    def test_editor_403_administrator_ok_on_update(self, client, fake_app, app_editor_headers, app_admin_headers, db):
        svc = sandbox_service(db, fake_app)
        url = f"{_base(fake_app)}/{svc.service_id}"
        body = sandbox_payload(end_of_service_at=iso(future(10)))
        assert client.post(url, json=body, headers=app_editor_headers).status_code == 403
        resp = client.post(url, json=body, headers=app_admin_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["end_of_service_at"] is not None

    def test_copy_has_null_fields(self, client, fake_app, owner_headers, db):
        svc = sandbox_service(db, fake_app, eos=future(2), notice="soon")
        resp = client.post(f"{_base(fake_app)}/{svc.service_id}/copy", headers=owner_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["service_id"] != svc.service_id
        assert resp.json()["end_of_service_at"] is None
        assert resp.json()["deprecation_notice"] is None
        assert resp.json()["lifecycle_status"] == "active"

    def test_admin_system_create_get_list_update_round_trip(self, client, admin_headers):
        base = "/internal/admin/system-sandbox-services"
        eos = future(90)
        resp = client.post(base, json=sandbox_payload(end_of_service_at=iso(eos), deprecation_notice="sys"),
                           headers=admin_headers)
        assert resp.status_code == 201, resp.text
        sid = resp.json()["service_id"]
        assert same_instant(resp.json()["end_of_service_at"], eos) and resp.json()["lifecycle_status"] == "active"

        listed = {s["service_id"]: s for s in client.get(base, headers=admin_headers).json()}
        assert listed[sid]["deprecation_notice"] == "sys"
        got = client.get(f"{base}/{sid}", headers=admin_headers).json()
        assert same_instant(got["end_of_service_at"], eos) and got["deprecation_notice"] == "sys"

        soon = future(3)
        resp = client.put(f"{base}/{sid}", json=sandbox_payload(end_of_service_at=iso(soon),
                                                                 deprecation_notice="changed"),
                          headers=admin_headers)
        assert resp.status_code == 200, resp.text
        assert same_instant(resp.json()["end_of_service_at"], soon)
        assert resp.json()["lifecycle_status"] == "deprecated"

    def test_admin_endpoints_reject_app_administrator(self, client, app_admin_headers):
        assert client.get("/internal/admin/system-sandbox-services", headers=app_admin_headers).status_code == 403


class TestSandboxLifecycleWarnings:
    """AC-25."""

    def _warnings(self, client, fake_app, headers, agent):
        listed = {a["agent_id"]: a for a in
                  client.get(f"/internal/apps/{fake_app.app_id}/agents/", headers=headers).json()}
        detail = client.get(f"/internal/apps/{fake_app.app_id}/agents/{agent.agent_id}", headers=headers).json()
        assert listed[agent.agent_id]["lifecycle_warnings"] == detail["lifecycle_warnings"]
        return detail["lifecycle_warnings"]

    def test_own_deprecated_sandbox_service(self, client, fake_app, owner_headers, db):
        sb = sandbox_service(db, fake_app, "sb-own", eos=future(5), notice="Moving on")
        agent = make_agent(db, fake_app, ai_service(db, fake_app, "sbw-llm"), enable_code_interpreter=True,
                           sandbox_service_id=sb.service_id)
        warnings = self._warnings(client, fake_app, owner_headers, agent)
        assert len(warnings) == 1
        w = warnings[0]
        assert (w["kind"], w["role"], w["via"], w["lifecycle_status"], w["service_id"], w["service_name"]) == (
            "sandbox", "sandbox", None, "deprecated", sb.service_id, "sb-own")
        assert w["deprecation_notice"] == "Moving on"
        assert same_instant(w["end_of_service_at"], future(5))

    def test_inherited_app_default(self, client, fake_app, owner_headers, db):
        sb = sandbox_service(db, fake_app, "sb-default", eos=past(1))
        fake_app.default_sandbox_service_id = sb.service_id
        db.flush()
        agent = make_agent(db, fake_app, ai_service(db, fake_app, "sbw-llm2"), enable_code_interpreter=True)
        warnings = self._warnings(client, fake_app, owner_headers, agent)
        assert [(w["kind"], w["role"], w["via"], w["lifecycle_status"]) for w in warnings] == [
            ("sandbox", "sandbox", "app default", "retired")]

    def test_no_entry_when_code_interpreter_disabled(self, client, fake_app, owner_headers, db):
        sb = sandbox_service(db, fake_app, "sb-off", eos=past(1))
        fake_app.default_sandbox_service_id = sb.service_id
        db.flush()
        agent = make_agent(db, fake_app, ai_service(db, fake_app, "sbw-llm3"), enable_code_interpreter=False,
                           sandbox_service_id=sb.service_id)
        assert self._warnings(client, fake_app, owner_headers, agent) == []

    def test_scheduled_task_warnings_follow_agent(self, client, fake_app, fake_user, owner_headers, db):
        own = sandbox_service(db, fake_app, "sb-task-own", eos=future(5))
        default = sandbox_service(db, fake_app, "sb-task-default", eos=past(1))
        fake_app.default_sandbox_service_id = default.service_id
        db.flush()
        llm = ai_service(db, fake_app, "sbw-llm4")
        own_agent = make_agent(db, fake_app, llm, enable_code_interpreter=True, sandbox_service_id=own.service_id)
        inh_agent = make_agent(db, fake_app, llm, enable_code_interpreter=True)
        plain_agent = make_agent(db, fake_app, llm, enable_code_interpreter=False)
        tasks = {t.id: a for t, a in ((make_task(db, fake_app, x, fake_user.user_id), x)
                                     for x in (own_agent, inh_agent, plain_agent))}
        base = f"/internal/apps/{fake_app.app_id}/scheduled-tasks"
        listed = {t["id"]: t for t in client.get(base, headers=owner_headers).json()}
        by_agent = {tasks[tid].agent_id: listed[tid]["lifecycle_warnings"] for tid in tasks}
        assert [(w["role"], w["via"], w["lifecycle_status"]) for w in by_agent[own_agent.agent_id]] == [
            ("sandbox", None, "deprecated")]
        assert [(w["role"], w["via"], w["lifecycle_status"]) for w in by_agent[inh_agent.agent_id]] == [
            ("sandbox", "app default", "retired")]
        assert by_agent[plain_agent.agent_id] == []
        one = next(tid for tid, a in tasks.items() if a is inh_agent)
        detail = client.get(f"{base}/{one}", headers=owner_headers).json()
        assert [w["via"] for w in detail["lifecycle_warnings"]] == ["app default"]


class TestSandboxUsedBy:
    """AC-26."""

    @pytest.fixture
    def scenario(self, db, fake_app, fake_user):
        other_app = make_app(db)
        sb = sandbox_service(db, None, "sb-system-used")  # system-wide so another app can use it too
        llm = ai_service(db, fake_app, "sbu-llm")
        other_llm = ai_service(db, other_app, "sbu-llm-other")
        direct = make_agent(db, fake_app, llm, enable_code_interpreter=True, sandbox_service_id=sb.service_id)
        inheriting = make_agent(db, fake_app, llm, enable_code_interpreter=True)
        no_ci = make_agent(db, fake_app, llm, enable_code_interpreter=False)
        fake_app.default_sandbox_service_id = sb.service_id
        other_app.default_sandbox_service_id = sb.service_id
        other_direct = make_agent(db, other_app, other_llm, enable_code_interpreter=True,
                                  sandbox_service_id=sb.service_id)
        other_inheriting = make_agent(db, other_app, other_llm, enable_code_interpreter=True)
        task = make_task(db, fake_app, direct, fake_user.user_id)
        other_task = make_task(db, other_app, other_direct, fake_user.user_id)
        db.flush()
        return dict(sb=sb, other_app=other_app, direct=direct, inheriting=inheriting, no_ci=no_ci,
                    other_direct=other_direct, other_inheriting=other_inheriting, task=task, other_task=other_task)

    def test_app_scope(self, client, fake_app, owner_headers, scenario):
        s = scenario
        resp = client.get(f"{_base(fake_app)}/{s['sb'].service_id}/used-by", headers=owner_headers)
        assert resp.status_code == 200, resp.text
        usage = resp.json()
        assert usage["kind"] == "sandbox"
        roles = {a["agent_id"]: a["roles"] for a in usage["agents"]}
        assert roles == {s["direct"].agent_id: ["sandbox"], s["inheriting"].agent_id: ["sandbox_app_default"]}
        assert usage["apps_using_as_default"] == [{"app_id": fake_app.app_id, "app_name": fake_app.name}]
        assert [t["task_id"] for t in usage["scheduled_tasks"]] == [s["task"].id]
        assert usage["silos"] == [] and usage["repositories"] == [] and usage["middlewares"] == []

    def test_admin_scope_across_apps(self, client, fake_app, admin_headers, scenario):
        s = scenario
        resp = client.get(f"/internal/admin/system-sandbox-services/{s['sb'].service_id}/used-by",
                          headers=admin_headers)
        assert resp.status_code == 200, resp.text
        usage = resp.json()
        roles = {a["agent_id"]: a["roles"] for a in usage["agents"]}
        assert roles == {
            s["direct"].agent_id: ["sandbox"], s["inheriting"].agent_id: ["sandbox_app_default"],
            s["other_direct"].agent_id: ["sandbox"], s["other_inheriting"].agent_id: ["sandbox_app_default"],
        }
        assert s["no_ci"].agent_id not in roles
        assert all(a["app_name"] for a in usage["agents"])
        assert {a["app_id"] for a in usage["apps_using_as_default"]} == {fake_app.app_id, s["other_app"].app_id}
        assert {t["task_id"] for t in usage["scheduled_tasks"]} == {s["task"].id, s["other_task"].id}

    def test_non_admin_403_on_admin_endpoint(self, client, owner_headers, scenario):
        resp = client.get(f"/internal/admin/system-sandbox-services/{scenario['sb'].service_id}/used-by",
                          headers=owner_headers)
        assert resp.status_code == 403

    def test_foreign_app_service_is_404(self, client, fake_app, owner_headers, scenario, db):
        foreign = sandbox_service(db, scenario["other_app"], "sb-foreign")
        assert client.get(f"{_base(fake_app)}/{foreign.service_id}/used-by", headers=owner_headers).status_code == 404

    def test_viewer_can_read(self, client, fake_app, app_viewer_headers, db):
        sb = sandbox_service(db, fake_app, "sb-viewer")
        assert client.get(f"{_base(fake_app)}/{sb.service_id}/used-by", headers=app_viewer_headers).status_code == 200


class TestRetiredSandboxAssignment:
    """AC-27."""

    def _agent_body(self, agent, **over):
        return {"name": agent.name, "description": "d", "system_prompt": "s", "type": "agent",
                "service_id": agent.service_id, "temperature": 0.5, "enable_code_interpreter": True, **over}

    def test_retired_sandbox_on_agent_is_400_and_unchanged_reference_is_ok(self, client, fake_app, owner_headers, db):
        retired = sandbox_service(db, fake_app, "sb-retired", eos=past(2))
        active = sandbox_service(db, fake_app, "sb-active")
        llm = ai_service(db, fake_app, "sba-llm")
        agent = make_agent(db, fake_app, llm, enable_code_interpreter=True, sandbox_service_id=active.service_id)
        url = f"/internal/apps/{fake_app.app_id}/agents/{agent.agent_id}"

        resp = client.post(url, json=self._agent_body(agent, sandbox_service_id=retired.service_id),
                           headers=owner_headers)
        assert resp.status_code == 400, resp.text
        assert "sb-retired" in resp.json()["detail"]
        db.refresh(agent)
        assert agent.sandbox_service_id == active.service_id

        # An agent already on the retired service can still be edited.
        keeper = make_agent(db, fake_app, llm, enable_code_interpreter=True, sandbox_service_id=retired.service_id)
        resp = client.post(f"/internal/apps/{fake_app.app_id}/agents/{keeper.agent_id}",
                           json=self._agent_body(keeper, name="keeper renamed",
                                                 sandbox_service_id=retired.service_id), headers=owner_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "keeper renamed"

    def test_retired_default_on_app_is_422_and_unchanged_reference_is_ok(self, client, fake_app, owner_headers, db):
        retired = sandbox_service(db, fake_app, "sb-app-retired", eos=past(2))
        url = f"/internal/apps/{fake_app.app_id}"
        resp = client.put(url, json={"name": fake_app.name, "default_sandbox_service_id": retired.service_id},
                          headers=owner_headers)
        assert resp.status_code == 422, resp.text
        db.refresh(fake_app)
        assert fake_app.default_sandbox_service_id is None

        fake_app.default_sandbox_service_id = retired.service_id
        db.flush()
        resp = client.put(url, json={"name": "renamed workspace", "default_sandbox_service_id": retired.service_id},
                          headers=owner_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "renamed workspace"
        assert resp.json()["default_sandbox_service_id"] == retired.service_id
