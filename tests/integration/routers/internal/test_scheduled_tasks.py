"""Integration coverage for the scheduled-task HTTP API and database boundary."""

from datetime import datetime, timezone

from models.scheduled_task import ScheduledTaskRun


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


class TestScheduledTaskApi:
    def test_create_list_update_and_soft_delete(self, client, db, fake_app, fake_agent, owner_headers):
        response = client.post(
            f"/internal/scheduled-tasks?app_id={fake_app.app_id}",
            json=payload(agent_id=fake_agent.agent_id),
            headers=owner_headers,
        )
        assert response.status_code == 201
        created = response.json()
        assert created["app_id"] == fake_app.app_id
        assert created["status"] == "active"
        task_id = created["id"]

        listed = client.get(
            f"/internal/scheduled-tasks?app_id={fake_app.app_id}", headers=owner_headers
        )
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [task_id]

        updated = client.patch(
            f"/internal/scheduled-tasks/{task_id}?app_id={fake_app.app_id}",
            json={"name": "Renamed", "status": "paused"},
            headers=owner_headers,
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Renamed"
        assert updated.json()["status"] == "paused"

        deleted = client.delete(
            f"/internal/scheduled-tasks/{task_id}?app_id={fake_app.app_id}",
            headers=owner_headers,
        )
        assert deleted.status_code == 204
        assert client.get(
            f"/internal/scheduled-tasks?app_id={fake_app.app_id}", headers=owner_headers
        ).json() == []

    def test_validation_and_not_found_responses(self, client, fake_app, owner_headers):
        invalid = client.post(
            f"/internal/scheduled-tasks?app_id={fake_app.app_id}",
            json=payload(agent_id=1, conversation_mode="invalid"),
            headers=owner_headers,
        )
        assert invalid.status_code == 422

        missing = client.patch(
            f"/internal/scheduled-tasks/999999?app_id={fake_app.app_id}",
            json={"name": "missing"},
            headers=owner_headers,
        )
        assert missing.status_code == 400
        assert "not found" in missing.json()["detail"].lower()

    def test_runs_are_scoped_to_the_task_and_paginated(
        self, client, db, fake_app, fake_agent, owner_headers
    ):
        response = client.post(
            f"/internal/scheduled-tasks?app_id={fake_app.app_id}",
            json=payload(agent_id=fake_agent.agent_id),
            headers=owner_headers,
        )
        assert response.status_code == 201
        task_id = response.json()["id"]
        db.add_all(
            [
                ScheduledTaskRun(
                    scheduled_task_id=task_id,
                    conversation_id=None,
                    orchestrator_run_id=f"run-{index}",
                    scheduled_time=datetime(2026, 1, index, tzinfo=timezone.utc),
                    status="succeeded",
                    attempt_count=1,
                )
                for index in (1, 2, 3)
            ]
        )
        db.flush()

        runs = client.get(
            f"/internal/scheduled-tasks/{task_id}/runs?app_id={fake_app.app_id}&page=2&per_page=2",
            headers=owner_headers,
        )
        assert runs.status_code == 200
        assert runs.json()["page"] == 2
        assert runs.json()["per_page"] == 2
        assert runs.json()["total"] == 3
        assert len(runs.json()["items"]) == 1

        missing_run = client.get(
            f"/internal/scheduled-tasks/{task_id}/runs/999999?app_id={fake_app.app_id}",
            headers=owner_headers,
        )
        assert missing_run.status_code == 404

    def test_run_now_returns_bad_request_without_dbos(self, client, fake_app, fake_agent, owner_headers):
        created = client.post(
            f"/internal/scheduled-tasks?app_id={fake_app.app_id}",
            json=payload(agent_id=fake_agent.agent_id),
            headers=owner_headers,
        )
        assert created.status_code == 201
        task_id = created.json()["id"]
        response = client.post(
            f"/internal/scheduled-tasks/{task_id}/run-now?app_id={fake_app.app_id}",
            headers=owner_headers,
        )
        assert response.status_code == 400
        assert "DBOS" in response.json()["detail"]
