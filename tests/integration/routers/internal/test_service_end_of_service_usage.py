"""Integration tests for assignment guard, used-by, bulk move and lifecycle warnings (step_011).

Covers AC-14 (API), AC-17, AC-18, AC-19, NFR-1, NFR-3. Requires the test DB on port 5433.
"""

import pytest
from sqlalchemy import event

from models.agent import Agent
from models.ocr_agent import OCRAgent
from tests.integration.routers.internal._eos_helpers import (
    ai_service,
    attach_middleware,
    embedding_service,
    future,
    make_agent,
    make_app,
    make_repository,
    make_silo,
    make_summarization_middleware,
    make_task,
    past,
    same_instant,
)

pytestmark = pytest.mark.integration


def _agent_body(agent, **over):
    body = {
        "name": agent.name, "description": agent.description, "system_prompt": agent.system_prompt,
        "type": "agent", "service_id": agent.service_id, "temperature": 0.5,
    }
    body.update(over)
    return body


class TestRetiredAssignmentGuard:
    """AC-17."""

    def test_changing_agent_service_to_retired_is_400(self, client, fake_app, owner_headers, db):
        active, retired = ai_service(db, fake_app, "act"), ai_service(db, fake_app, "ret-svc", eos=past(3))
        agent = make_agent(db, fake_app, active)
        resp = client.post(f"/internal/apps/{fake_app.app_id}/agents/{agent.agent_id}",
                           json=_agent_body(agent, service_id=retired.service_id), headers=owner_headers)
        assert resp.status_code == 400, resp.text
        assert "ret-svc" in resp.json()["detail"] and "retired" in resp.json()["detail"]
        db.refresh(agent)
        assert agent.service_id == active.service_id

    def test_rename_while_referencing_retired_service_is_ok(self, client, fake_app, owner_headers, db):
        retired = ai_service(db, fake_app, "ret-keep", eos=past(3))
        agent = make_agent(db, fake_app, retired)
        resp = client.post(f"/internal/apps/{fake_app.app_id}/agents/{agent.agent_id}",
                           json=_agent_body(agent, name="renamed agent"), headers=owner_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "renamed agent"
        assert resp.json()["service_id"] == retired.service_id

    def test_creating_agent_with_retired_service_is_400(self, client, fake_app, owner_headers, db):
        retired = ai_service(db, fake_app, "ret-new", eos=past(3))
        resp = client.post(f"/internal/apps/{fake_app.app_id}/agents/0",
                           json={"name": "new", "service_id": retired.service_id, "temperature": 0.5},
                           headers=owner_headers)
        assert resp.status_code == 400, resp.text

    def test_silo_creation_with_retired_embedding_service_is_rejected(self, client, fake_app, owner_headers, db):
        retired = embedding_service(db, fake_app, "ret-emb", eos=past(3))
        resp = client.post(f"/internal/apps/{fake_app.app_id}/silos/",
                           json={"name": "silo-new", "embedding_service_id": retired.service_id},
                           headers=owner_headers)
        assert 400 <= resp.status_code < 500, resp.text
        assert "ret-emb" in resp.text

    def test_repository_creation_with_retired_embedding_service_is_rejected(self, client, fake_app, owner_headers, db):
        retired = embedding_service(db, fake_app, "ret-emb-repo", eos=past(3))
        resp = client.post(f"/internal/apps/{fake_app.app_id}/repositories/",
                           json={"name": "repo-new", "embedding_service_id": retired.service_id},
                           headers=owner_headers)
        assert 400 <= resp.status_code < 500, resp.text


def _populate_ai_usage(db, app, service, user_id):
    """Every kind of dependency on ``service`` inside ``app``."""
    other_llm = ai_service(db, app, f"other-llm-{app.app_id}")
    llm = make_agent(db, app, service, name=f"llm-{app.app_id}")
    ocr = make_agent(db, app, other_llm, cls=OCRAgent, name=f"ocr-{app.app_id}", vision_service_id=service.service_id)
    trans = make_agent(db, app, other_llm, name=f"trans-{app.app_id}", transcription_service_id=service.service_id)
    video = make_agent(db, app, other_llm, name=f"video-{app.app_id}", video_ai_service_id=service.service_id)
    silo = make_silo(db, app, name=f"silo-{app.app_id}", transcription_service_id=service.service_id)
    repo = make_repository(db, app, silo, name=f"repo-{app.app_id}")
    mw = make_summarization_middleware(db, app, service, name=f"mw-{app.app_id}")
    attach_middleware(db, llm, mw)
    task = make_task(db, app, llm, user_id)
    return dict(llm=llm, ocr=ocr, trans=trans, video=video, silo=silo, repo=repo, mw=mw, task=task)


class TestUsedBy:
    """AC-18 / NFR-1."""

    def test_app_scope_lists_roles_and_only_own_resources(self, client, fake_app, fake_user, owner_headers, db):
        other_app = make_app(db)
        service = ai_service(db, fake_app, "used-svc")
        mine = _populate_ai_usage(db, fake_app, service, fake_user.user_id)
        # Same shape of dependencies in another app, using the same service id (must never leak).
        _populate_ai_usage(db, other_app, service, fake_user.user_id)

        resp = client.get(f"/internal/apps/{fake_app.app_id}/ai-services/{service.service_id}/used-by",
                          headers=owner_headers)
        assert resp.status_code == 200, resp.text
        usage = resp.json()
        assert usage["kind"] == "ai" and usage["is_system"] is False

        roles = {a["agent_id"]: set(a["roles"]) for a in usage["agents"]}
        assert roles == {
            mine["llm"].agent_id: {"llm"},
            mine["ocr"].agent_id: {"ocr_vision"},
            mine["trans"].agent_id: {"transcription"},
            mine["video"].agent_id: {"video"},
        }
        assert {a["app_id"] for a in usage["agents"]} == {fake_app.app_id}
        assert all(a["app_name"] is None for a in usage["agents"])
        assert [s["silo_id"] for s in usage["silos"]] == [mine["silo"].silo_id]
        assert usage["silos"][0]["roles"] == ["transcription"]
        assert [r["repository_id"] for r in usage["repositories"]] == [mine["repo"].repository_id]
        assert [m["middleware_id"] for m in usage["middlewares"]] == [mine["mw"].middleware_id]
        assert usage["middlewares"][0]["agent_ids"] == [mine["llm"].agent_id]
        assert [t["task_id"] for t in usage["scheduled_tasks"]] == [mine["task"].id]

    def test_other_apps_service_is_404(self, client, fake_app, owner_headers, db):
        other_app = make_app(db)
        foreign = ai_service(db, other_app, "foreign-svc")
        resp = client.get(f"/internal/apps/{fake_app.app_id}/ai-services/{foreign.service_id}/used-by",
                          headers=owner_headers)
        assert resp.status_code == 404

    def test_system_service_from_app_lists_only_calling_app(self, client, fake_app, fake_user, owner_headers, db):
        other_app = make_app(db)
        system = ai_service(db, None, "sys-used")
        mine = _populate_ai_usage(db, fake_app, system, fake_user.user_id)
        theirs = _populate_ai_usage(db, other_app, system, fake_user.user_id)

        resp = client.get(f"/internal/apps/{fake_app.app_id}/ai-services/{system.service_id}/used-by",
                          headers=owner_headers)
        assert resp.status_code == 200, resp.text
        usage = resp.json()
        assert usage["is_system"] is True
        ids = {a["agent_id"] for a in usage["agents"]}
        assert mine["llm"].agent_id in ids and theirs["llm"].agent_id not in ids
        assert {a["app_id"] for a in usage["agents"]} == {fake_app.app_id}
        assert {s["silo_id"] for s in usage["silos"]} == {mine["silo"].silo_id}
        assert {t["task_id"] for t in usage["scheduled_tasks"]} == {mine["task"].id}

    def test_admin_lists_across_apps_with_app_names(self, client, fake_app, fake_user, admin_headers, db):
        other_app = make_app(db)
        system = ai_service(db, None, "sys-admin-used")
        mine = _populate_ai_usage(db, fake_app, system, fake_user.user_id)
        theirs = _populate_ai_usage(db, other_app, system, fake_user.user_id)

        resp = client.get(f"/internal/admin/system-ai-services/{system.service_id}/used-by", headers=admin_headers)
        assert resp.status_code == 200, resp.text
        usage = resp.json()
        by_id = {a["agent_id"]: a for a in usage["agents"]}
        assert {mine["llm"].agent_id, theirs["llm"].agent_id} <= set(by_id)
        assert by_id[mine["llm"].agent_id]["app_id"] == fake_app.app_id
        assert by_id[mine["llm"].agent_id]["app_name"] == fake_app.name
        assert by_id[theirs["llm"].agent_id]["app_name"] == other_app.name
        assert {s["app_id"] for s in usage["silos"]} == {fake_app.app_id, other_app.app_id}
        assert {t["app_id"] for t in usage["scheduled_tasks"]} == {fake_app.app_id, other_app.app_id}

    def test_admin_endpoint_rejects_non_admin(self, client, fake_app, owner_headers, db):
        system = ai_service(db, None, "sys-403")
        emb = embedding_service(db, None, "sys-emb-403")
        assert client.get(f"/internal/admin/system-ai-services/{system.service_id}/used-by",
                          headers=owner_headers).status_code == 403
        assert client.get(f"/internal/admin/system-embedding-services/{emb.service_id}/used-by",
                          headers=owner_headers).status_code == 403

    def test_admin_endpoint_404_for_app_service(self, client, fake_app, admin_headers, db):
        svc = ai_service(db, fake_app, "not-system")
        assert client.get(f"/internal/admin/system-ai-services/{svc.service_id}/used-by",
                          headers=admin_headers).status_code == 404

    def test_viewer_can_read_app_used_by(self, client, fake_app, app_viewer_headers, db):
        svc = ai_service(db, fake_app, "viewer-svc")
        resp = client.get(f"/internal/apps/{fake_app.app_id}/ai-services/{svc.service_id}/used-by",
                          headers=app_viewer_headers)
        assert resp.status_code == 200
        assert resp.json()["agents"] == []

    def test_embedding_used_by_lists_silos_repositories_and_agents(self, client, fake_app, owner_headers, db):
        other_app = make_app(db)
        emb = embedding_service(db, fake_app, "emb-used")
        llm = ai_service(db, fake_app, "emb-llm")
        silo = make_silo(db, fake_app, embedding_service_id=emb.service_id)
        repo = make_repository(db, fake_app, silo)
        agent = make_agent(db, fake_app, llm, silo_id=silo.silo_id)
        media_agent = make_agent(db, fake_app, llm, media_embedding_service_id=emb.service_id)
        # Same service id referenced from another app (must not appear).
        other_silo = make_silo(db, other_app, embedding_service_id=emb.service_id)

        resp = client.get(f"/internal/apps/{fake_app.app_id}/embedding-services/{emb.service_id}/used-by",
                          headers=owner_headers)
        assert resp.status_code == 200, resp.text
        usage = resp.json()
        assert [s["silo_id"] for s in usage["silos"]] == [silo.silo_id]
        assert [r["repository_id"] for r in usage["repositories"]] == [repo.repository_id]
        roles = {a["agent_id"]: set(a["roles"]) for a in usage["agents"]}
        assert roles == {agent.agent_id: {"silo_embedding"}, media_agent.agent_id: {"media_embedding"}}
        assert other_silo.silo_id not in {s["silo_id"] for s in usage["silos"]}


def _move_url(app, svc):
    return f"/internal/apps/{app.app_id}/ai-services/{svc.service_id}/move-agents"


class TestMoveAgents:
    """AC-19."""

    def _setup(self, db, app):
        a, b = ai_service(db, app, "move-a"), ai_service(db, app, "move-b")
        agents = [make_agent(db, app, a) for _ in range(3)]
        return a, b, agents

    def test_administrator_moves_all_agents(self, client, fake_app, app_admin_headers, db):
        a, b, agents = self._setup(db, fake_app)
        other_app = make_app(db)
        foreign_agent = make_agent(db, other_app, a)
        resp = client.post(_move_url(fake_app, a), json={"target_service_id": b.service_id, "expected_count": 3},
                           headers=app_admin_headers)
        assert resp.status_code == 200, resp.text
        assert sorted(resp.json()["moved_agent_ids"]) == sorted(x.agent_id for x in agents)
        assert resp.json()["count"] == 3
        db.expire_all()
        assert all(x.service_id == b.service_id for x in agents)
        assert foreign_agent.service_id == a.service_id

    def test_expected_count_mismatch_is_409_and_nothing_changes(self, client, fake_app, owner_headers, db):
        a, b, agents = self._setup(db, fake_app)
        resp = client.post(_move_url(fake_app, a), json={"target_service_id": b.service_id, "expected_count": 2},
                           headers=owner_headers)
        assert resp.status_code == 409, resp.text
        db.expire_all()
        assert all(x.service_id == a.service_id for x in agents)

    def test_retired_target_is_400_and_nothing_changes(self, client, fake_app, owner_headers, db):
        a, _, agents = self._setup(db, fake_app)
        retired = ai_service(db, fake_app, "move-retired", eos=past(2))
        resp = client.post(_move_url(fake_app, a), json={"target_service_id": retired.service_id},
                           headers=owner_headers)
        assert resp.status_code == 400, resp.text
        db.expire_all()
        assert all(x.service_id == a.service_id for x in agents)

    def test_target_from_another_app_is_rejected_and_nothing_changes(self, client, fake_app, owner_headers, db):
        a, _, agents = self._setup(db, fake_app)
        foreign = ai_service(db, make_app(db), "move-foreign")
        resp = client.post(_move_url(fake_app, a), json={"target_service_id": foreign.service_id},
                           headers=owner_headers)
        assert 400 <= resp.status_code < 500, resp.text
        db.expire_all()
        assert all(x.service_id == a.service_id for x in agents)

    def test_system_service_target_is_allowed(self, client, fake_app, owner_headers, db):
        a, _, agents = self._setup(db, fake_app)
        system = ai_service(db, None, "move-system")
        resp = client.post(_move_url(fake_app, a), json={"target_service_id": system.service_id},
                           headers=owner_headers)
        assert resp.status_code == 200, resp.text
        db.expire_all()
        assert all(x.service_id == system.service_id for x in agents)

    def test_editor_is_403(self, client, fake_app, app_editor_headers, db):
        a, b, agents = self._setup(db, fake_app)
        resp = client.post(_move_url(fake_app, a), json={"target_service_id": b.service_id},
                           headers=app_editor_headers)
        assert resp.status_code == 403
        db.expire_all()
        assert all(x.service_id == a.service_id for x in agents)

    def test_zero_agents_is_200_count_zero(self, client, fake_app, owner_headers, db):
        a, b = ai_service(db, fake_app, "empty-a"), ai_service(db, fake_app, "empty-b")
        resp = client.post(_move_url(fake_app, a), json={"target_service_id": b.service_id, "expected_count": 0},
                           headers=owner_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"moved_agent_ids": [], "count": 0}


class TestLifecycleWarningsApi:
    """AC-14 (API): warnings on agent, silo, repository and scheduled task payloads."""

    @pytest.fixture
    def scenario(self, db, fake_app, fake_user):
        llm = ai_service(db, fake_app, "warn-llm", eos=future(5), notice="Switch to the new LLM")
        emb = embedding_service(db, fake_app, "warn-emb", eos=past(2), notice="Re-index please")
        mw_model = ai_service(db, fake_app, "warn-mw-model", eos=past(1))
        silo = make_silo(db, fake_app, name="warn-silo", embedding_service_id=emb.service_id)
        repo = make_repository(db, fake_app, silo, name="warn-repo")
        mw = make_summarization_middleware(db, fake_app, mw_model, name="warn-mw")
        agent = make_agent(db, fake_app, llm, silo_id=silo.silo_id, name="warn-agent")
        attach_middleware(db, agent, mw)
        task = make_task(db, fake_app, agent, fake_user.user_id)
        return dict(llm=llm, emb=emb, mw_model=mw_model, silo=silo, repo=repo, agent=agent, task=task)

    @staticmethod
    def _by_role(warnings):
        return {(w["role"]): w for w in warnings}

    def _check_agent_like(self, warnings, s):
        by_role = self._by_role(warnings)
        assert set(by_role) == {"llm", "silo_embedding", "middleware"}
        llm = by_role["llm"]
        assert (llm["kind"], llm["lifecycle_status"], llm["service_id"], llm["service_name"]) == (
            "ai", "deprecated", s["llm"].service_id, "warn-llm")
        assert llm["deprecation_notice"] == "Switch to the new LLM" and llm["via"] is None
        assert same_instant(llm["end_of_service_at"], future(5))
        emb = by_role["silo_embedding"]
        assert (emb["kind"], emb["lifecycle_status"], emb["via"]) == ("embedding", "retired", "warn-silo")
        assert emb["deprecation_notice"] == "Re-index please"
        mw = by_role["middleware"]
        assert (mw["kind"], mw["lifecycle_status"], mw["via"], mw["service_name"]) == (
            "ai", "retired", "warn-mw", "warn-mw-model")

    def test_agent_list_and_detail(self, client, fake_app, owner_headers, scenario):
        base = f"/internal/apps/{fake_app.app_id}/agents"
        listed = {a["agent_id"]: a for a in client.get(base + "/", headers=owner_headers).json()}
        self._check_agent_like(listed[scenario["agent"].agent_id]["lifecycle_warnings"], scenario)
        detail = client.get(f"{base}/{scenario['agent'].agent_id}", headers=owner_headers)
        assert detail.status_code == 200, detail.text
        self._check_agent_like(detail.json()["lifecycle_warnings"], scenario)

    def test_scheduled_task_list_and_detail(self, client, fake_app, owner_headers, scenario):
        base = f"/internal/apps/{fake_app.app_id}/scheduled-tasks"
        listed = {t["id"]: t for t in client.get(base, headers=owner_headers).json()}
        self._check_agent_like(listed[scenario["task"].id]["lifecycle_warnings"], scenario)
        detail = client.get(f"{base}/{scenario['task'].id}", headers=owner_headers)
        assert detail.status_code == 200, detail.text
        self._check_agent_like(detail.json()["lifecycle_warnings"], scenario)

    def test_silo_list_and_detail(self, client, fake_app, owner_headers, scenario):
        base = f"/internal/apps/{fake_app.app_id}/silos"
        listed = {s["silo_id"]: s for s in client.get(base + "/", headers=owner_headers).json()}
        warnings = listed[scenario["silo"].silo_id]["lifecycle_warnings"]
        assert [(w["role"], w["kind"], w["lifecycle_status"], w["service_id"]) for w in warnings] == [
            ("embedding", "embedding", "retired", scenario["emb"].service_id)]
        detail = client.get(f"{base}/{scenario['silo'].silo_id}", headers=owner_headers)
        assert detail.status_code == 200, detail.text
        assert [w["role"] for w in detail.json()["lifecycle_warnings"]] == ["embedding"]

    def test_repository_list_and_detail(self, client, fake_app, owner_headers, scenario):
        base = f"/internal/apps/{fake_app.app_id}/repositories"
        listed = {r["repository_id"]: r for r in client.get(base + "/", headers=owner_headers).json()}
        warnings = listed[scenario["repo"].repository_id]["lifecycle_warnings"]
        assert [(w["role"], w["lifecycle_status"], w["deprecation_notice"]) for w in warnings] == [
            ("embedding", "retired", "Re-index please")]
        detail = client.get(f"{base}/{scenario['repo'].repository_id}", headers=owner_headers)
        assert detail.status_code == 200, detail.text
        assert [w["role"] for w in detail.json()["lifecycle_warnings"]] == ["embedding"]

    def test_active_services_produce_no_warnings(self, client, fake_app, owner_headers, db):
        agent = make_agent(db, fake_app, ai_service(db, fake_app, "healthy", eos=future(400)))
        listed = {a["agent_id"]: a for a in
                  client.get(f"/internal/apps/{fake_app.app_id}/agents/", headers=owner_headers).json()}
        assert listed[agent.agent_id]["lifecycle_warnings"] == []


class TestAgentListQueryCountApi:
    """NFR-3 through the HTTP endpoint: statement count does not grow with the number of agents."""

    def _count(self, db, client, url, headers):
        statements = []
        connection = db.get_bind()

        def on_execute(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(connection, "before_cursor_execute", on_execute)
        try:
            db.flush()
            resp = client.get(url, headers=headers)
        finally:
            event.remove(connection, "before_cursor_execute", on_execute)
        assert resp.status_code == 200, resp.text
        return len(statements), resp.json()

    def test_statement_count_constant_for_2_vs_20_agents(self, client, fake_app, owner_headers, db):
        llm = ai_service(db, fake_app, "qc-llm", eos=future(5))
        emb = embedding_service(db, fake_app, "qc-emb", eos=past(1))
        silo = make_silo(db, fake_app, embedding_service_id=emb.service_id)
        mw = make_summarization_middleware(db, fake_app, llm)
        url = f"/internal/apps/{fake_app.app_id}/agents/"

        def add(n):
            for i in range(n):
                agent = make_agent(db, fake_app, llm, silo_id=silo.silo_id, cls=OCRAgent if i % 3 == 0 else Agent,
                                   **({"vision_service_id": llm.service_id} if i % 3 == 0 else {}))
                if i % 2 == 0:
                    attach_middleware(db, agent, mw)

        add(2)
        small, small_body = self._count(db, client, url, owner_headers)
        add(18)
        big, big_body = self._count(db, client, url, owner_headers)
        assert (len(small_body), len(big_body)) == (2, 20)
        assert big == small
        assert all(a["lifecycle_warnings"] for a in big_body)
