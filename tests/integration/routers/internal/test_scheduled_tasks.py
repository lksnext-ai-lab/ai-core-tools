"""Integration coverage for the scheduled-task HTTP API and database boundary."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from models.app import App
from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
from models.conversation import Conversation
from models.scheduled_task import ScheduledTask, ScheduledTaskRun
from tests.factories import UserFactory, configure_factories


def payload(**overrides):
    value = {
        "name": "Daily test task",
        "agent_id": None,
        "input": {"message": "hello"},
        "cron_expression": "*/5 * * * *",
        "timezone": "UTC",
        "conversation_mode": "new_per_run",
        "max_concurrent_runs": 1,
    }
    value.update(overrides)
    return value


def _url(app_id, suffix=""):
    return f"/internal/apps/{app_id}/scheduled-tasks{suffix}"


def _headers(user):
    from utils.local_auth_tokens import mint_access_token

    token, _ = mint_access_token(user.user_id, user.email, user.name)
    return {"Authorization": f"Bearer {token}"}


def _member(db, app_id, owner_id, role, email):
    configure_factories(db)
    user = UserFactory(email=email, name=email.split("@")[0])
    db.add(AppCollaborator(
        app_id=app_id, user_id=user.user_id, role=role, status=CollaborationStatus.ACCEPTED,
        invited_by=owner_id, invited_at=datetime.utcnow(), accepted_at=datetime.utcnow(),
    ))
    db.flush()
    return user


def _outsider(db, email="outsider-sched@mattin-test.com"):
    configure_factories(db)
    return UserFactory(email=email, name="outsider")


class _SessionProxy:
    """SessionLocal() stand-in bound to the test session; close() must not end the test transaction."""

    def __init__(self, db):
        self._db = db

    def __getattr__(self, name):
        return getattr(self._db, name)

    def close(self):
        pass


async def _execute(db, task_id, response="Informe diario", files=None, when=None):
    from scheduling import periodic_agent_task as module

    result = {"response": response, "files": files or []}
    with (
        patch.object(module, "SessionLocal", return_value=_SessionProxy(db)),
        patch.object(module, "invoke_agent_step", new=AsyncMock(return_value=result)) as invoke,
    ):
        await module._run_scheduled_task(when or datetime.now(timezone.utc), task_id)
    return invoke


@pytest.fixture
def task(client, db, fake_app, fake_agent, owner_headers):
    response = client.post(_url(fake_app.app_id), json=payload(agent_id=fake_agent.agent_id), headers=owner_headers)
    assert response.status_code == 201, response.text
    return db.get(ScheduledTask, response.json()["id"])


class TestScheduledTaskApi:
    def test_create_list_update_and_delete(self, client, db, fake_app, fake_agent, owner_headers):
        response = client.post(
            _url(fake_app.app_id),
            json=payload(agent_id=fake_agent.agent_id, description="Resumen", marketplace_visibility="private"),
            headers=owner_headers,
        )
        assert response.status_code == 201
        created = response.json()
        assert created["app_id"] == fake_app.app_id
        assert created["status"] == "active"
        assert created["max_runs_retained"] == 10
        assert created["marketplace_visibility"] == "private"
        assert created["description"] == "Resumen"
        task_id = created["id"]

        listed = client.get(_url(fake_app.app_id), headers=owner_headers)
        assert [item["id"] for item in listed.json()] == [task_id]
        assert client.get(_url(fake_app.app_id, f"/{task_id}"), headers=owner_headers).json()["id"] == task_id

        updated = client.patch(
            _url(fake_app.app_id, f"/{task_id}"),
            json={"name": "Renamed", "status": "paused", "max_runs_retained": 3, "marketplace_visibility": "public"},
            headers=owner_headers,
        )
        assert updated.status_code == 200
        body = updated.json()
        assert (body["name"], body["status"], body["max_runs_retained"], body["marketplace_visibility"]) == (
            "Renamed", "paused", 3, "public",
        )

        assert client.delete(_url(fake_app.app_id, f"/{task_id}"), headers=owner_headers).status_code == 204
        assert client.get(_url(fake_app.app_id), headers=owner_headers).json() == []
        assert db.get(ScheduledTask, task_id) is None

    def test_validation_and_not_found_responses(self, client, fake_app, owner_headers):
        invalid = client.post(
            _url(fake_app.app_id), json=payload(agent_id=1, conversation_mode="invalid"), headers=owner_headers,
        )
        assert invalid.status_code == 422
        bad_retention = client.post(
            _url(fake_app.app_id), json=payload(agent_id=1, max_runs_retained=0), headers=owner_headers,
        )
        assert bad_retention.status_code == 422

        missing = client.patch(_url(fake_app.app_id, "/999999"), json={"name": "missing"}, headers=owner_headers)
        assert missing.status_code == 404

    def test_runs_are_scoped_to_the_task_and_paginated(self, client, db, fake_app, task, owner_headers):
        db.add_all([
            ScheduledTaskRun(
                scheduled_task_id=task.id, conversation_id=None, orchestrator_run_id=f"run-{index}",
                scheduled_time=datetime(2026, 1, index, tzinfo=timezone.utc), status="succeeded", attempt_count=1,
            )
            for index in (1, 2, 3)
        ])
        db.flush()

        runs = client.get(_url(fake_app.app_id, f"/{task.id}/runs?page=2&per_page=2"), headers=owner_headers)
        assert runs.status_code == 200
        assert (runs.json()["page"], runs.json()["per_page"], runs.json()["total"]) == (2, 2, 3)
        assert len(runs.json()["items"]) == 1

        missing_run = client.get(_url(fake_app.app_id, f"/{task.id}/runs/999999"), headers=owner_headers)
        assert missing_run.status_code == 404

    def test_run_now_returns_bad_request_without_dbos(self, client, fake_app, task, owner_headers):
        response = client.post(_url(fake_app.app_id, f"/{task.id}/run-now"), headers=owner_headers)
        assert response.status_code == 400
        assert "DBOS" in response.json()["detail"]


class TestPermissions:
    def test_outsider_cannot_see_or_touch_tasks(self, client, db, fake_app, task):
        headers = _headers(_outsider(db))
        assert client.get(_url(fake_app.app_id), headers=headers).status_code == 403
        assert client.get(_url(fake_app.app_id, f"/{task.id}/runs"), headers=headers).status_code == 403
        assert client.delete(_url(fake_app.app_id, f"/{task.id}"), headers=headers).status_code == 403

    def test_viewer_reads_but_cannot_write(self, client, db, fake_app, fake_user, task):
        viewer = _member(db, fake_app.app_id, fake_user.user_id, CollaborationRole.VIEWER, "viewer-sched@mattin-test.com")
        headers = _headers(viewer)
        assert client.get(_url(fake_app.app_id), headers=headers).status_code == 200
        assert client.get(_url(fake_app.app_id, f"/{task.id}/runs"), headers=headers).status_code == 200
        assert client.patch(_url(fake_app.app_id, f"/{task.id}"), json={"name": "x"}, headers=headers).status_code == 403
        assert client.post(_url(fake_app.app_id, f"/{task.id}/run-now"), headers=headers).status_code == 403
        assert client.delete(_url(fake_app.app_id, f"/{task.id}"), headers=headers).status_code == 403

    def test_editor_can_manage(self, client, db, fake_app, fake_user, task):
        editor = _member(db, fake_app.app_id, fake_user.user_id, CollaborationRole.EDITOR, "editor-sched@mattin-test.com")
        response = client.patch(_url(fake_app.app_id, f"/{task.id}"), json={"name": "Edited"}, headers=_headers(editor))
        assert response.status_code == 200

    def test_task_of_another_app_is_not_reachable(self, client, db, fake_user, task, owner_headers):
        other = App(name="Other", slug="other-sched-app", owner_id=fake_user.user_id, agent_rate_limit=0, max_file_size_mb=10)
        db.add(other)
        db.flush()
        assert client.get(_url(other.app_id, f"/{task.id}"), headers=owner_headers).status_code == 404


class TestExecution:
    @pytest.mark.asyncio
    async def test_run_is_owned_by_the_task_and_stores_its_output(self, client, db, fake_app, fake_agent, task, owner_headers):
        files = [{"file_id": "f-1", "filename": "report.csv", "file_type": "csv"}]
        invoke = await _execute(db, task.id, response="Todo en orden ![c](file://f-1)", files=files)

        run = db.query(ScheduledTaskRun).filter_by(scheduled_task_id=task.id).one()
        assert run.status == "succeeded"
        assert run.output_text == "Todo en orden ![c](file://f-1)"
        assert run.output_files == files
        conversation = db.get(Conversation, run.conversation_id)
        assert conversation.user_id is None
        assert conversation.scheduled_task_id == task.id
        assert invoke.await_args.args[3]["caller_type_override"] == "SCHEDULED_TASK"

        # Not in the creator's playground history.
        playground = client.get(f"/internal/conversations?agent_id={fake_agent.agent_id}", headers=owner_headers)
        assert playground.status_code == 200
        assert run.conversation_id not in {c["conversation_id"] for c in playground.json()["conversations"]}

        detail = client.get(_url(fake_app.app_id, f"/{task.id}/runs/{run.id}"), headers=owner_headers).json()
        assert detail["output_text"].startswith("Todo en orden")
        assert detail["output_files"][0]["filename"] == "report.csv"

    @pytest.mark.asyncio
    async def test_file_download_only_serves_files_recorded_on_the_run(self, client, db, fake_app, task, owner_headers):
        await _execute(db, task.id, files=[{"file_id": "f-1", "filename": "report.csv", "file_type": "csv"}])
        run = db.query(ScheduledTaskRun).filter_by(scheduled_task_id=task.id).one()
        response = client.get(
            _url(fake_app.app_id, f"/{task.id}/runs/{run.id}/files/not-mine/download"), headers=owner_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_continuous_mode_reuses_one_conversation(self, client, db, fake_app, fake_agent, owner_headers):
        rejected = client.post(
            _url(fake_app.app_id), json=payload(agent_id=fake_agent.agent_id, conversation_mode="continuous"),
            headers=owner_headers,
        )
        assert rejected.status_code == 400 and "memory" in rejected.json()["detail"]
        fake_agent.has_memory = True
        db.flush()
        created = client.post(
            _url(fake_app.app_id), json=payload(agent_id=fake_agent.agent_id, conversation_mode="continuous"),
            headers=owner_headers,
        ).json()
        await _execute(db, created["id"], response="uno", when=datetime(2026, 1, 1, tzinfo=timezone.utc))
        await _execute(db, created["id"], response="dos", when=datetime(2026, 1, 2, tzinfo=timezone.utc))

        runs = db.query(ScheduledTaskRun).filter_by(scheduled_task_id=created["id"]).all()
        assert len(runs) == 2
        assert len({r.conversation_id for r in runs}) == 1
        assert db.get(ScheduledTask, created["id"]).persistent_conversation_id == runs[0].conversation_id

    @pytest.mark.asyncio
    async def test_retention_keeps_only_the_newest_runs(self, client, db, fake_app, fake_agent, owner_headers):
        created = client.post(
            _url(fake_app.app_id), json=payload(agent_id=fake_agent.agent_id, max_runs_retained=2),
            headers=owner_headers,
        ).json()
        with patch("services.conversation_service.ConversationService.delete_thread_history", new=AsyncMock()):
            for day in (1, 2, 3):
                await _execute(db, created["id"], response=f"día {day}", when=datetime(2026, 1, day, tzinfo=timezone.utc))

        runs = db.query(ScheduledTaskRun).filter_by(scheduled_task_id=created["id"]).all()
        assert sorted(r.output_text for r in runs) == ["día 2", "día 3"]
        conversations = db.query(Conversation).filter_by(scheduled_task_id=created["id"]).all()
        assert {c.conversation_id for c in conversations} == {r.conversation_id for r in runs}

    @pytest.mark.asyncio
    async def test_delete_removes_conversations(self, client, db, fake_app, task, owner_headers):
        await _execute(db, task.id)
        assert db.query(Conversation).filter_by(scheduled_task_id=task.id).count() == 1
        with patch("services.conversation_service.ConversationService.delete_thread_history", new=AsyncMock()) as history:
            assert client.delete(_url(fake_app.app_id, f"/{task.id}"), headers=owner_headers).status_code == 204
        assert db.query(Conversation).filter_by(scheduled_task_id=task.id).count() == 0
        assert db.query(ScheduledTaskRun).filter_by(scheduled_task_id=task.id).count() == 0
        history.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deleting_the_agent_deletes_its_tasks(self, client, db, fake_app, fake_agent, task, owner_headers):
        await _execute(db, task.id)
        task_id = task.id
        from services.agent_service import AgentService

        with patch("services.conversation_service.ConversationService.delete_thread_history", new=AsyncMock()):
            AgentService().delete_agent(db, fake_agent.agent_id)
        assert db.get(ScheduledTask, task_id) is None
        assert db.query(Conversation).filter_by(scheduled_task_id=task_id).count() == 0


class TestMarketplace:
    MARKET = "/internal/marketplace/scheduled-tasks"

    @pytest.mark.asyncio
    async def test_visibility_matches_marketplace_agents(self, client, db, fake_app, fake_user, task, owner_headers):
        await _execute(db, task.id, response="Resultado publicado")
        outsider = _headers(_outsider(db))
        viewer = _headers(_member(db, fake_app.app_id, fake_user.user_id, CollaborationRole.VIEWER, "viewer-mkt@mattin-test.com"))

        # Unpublished: nobody sees it in the marketplace, not even the owner.
        assert client.get(self.MARKET, headers=owner_headers).json()["total"] == 0
        assert client.get(f"{self.MARKET}/{task.id}", headers=owner_headers).status_code == 404

        # Private: members only.
        client.patch(_url(fake_app.app_id, f"/{task.id}"), json={"marketplace_visibility": "private"}, headers=owner_headers)
        assert [t["id"] for t in client.get(self.MARKET, headers=viewer).json()["tasks"]] == [task.id]
        assert client.get(self.MARKET, headers=outsider).json()["total"] == 0
        assert client.get(f"{self.MARKET}/{task.id}/runs", headers=outsider).status_code == 404

        # Public: every logged-in user, read-only results, never the task input.
        client.patch(_url(fake_app.app_id, f"/{task.id}"), json={"marketplace_visibility": "public"}, headers=owner_headers)
        card = client.get(f"{self.MARKET}/{task.id}", headers=outsider).json()
        assert card["run_count"] == 1 and card["last_run_status"] == "succeeded"
        assert "input" not in card
        runs = client.get(f"{self.MARKET}/{task.id}/runs", headers=outsider).json()
        assert runs["items"][0]["output_text"] == "Resultado publicado"
        assert client.get(f"{self.MARKET}?my_apps_only=true", headers=outsider).json()["total"] == 0


class TestMetricsChannel:
    def test_scheduled_task_runs_report_their_own_channel(self):
        from services.agent_metrics_recorder import _detect_caller_type
        from services.scheduled_task_service import task_user_context

        context = task_user_context(ScheduledTask(id=7, app_id=3, created_by=42))
        assert _detect_caller_type(context) == "SCHEDULED_TASK"
