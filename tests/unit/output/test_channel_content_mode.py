"""Channel content settings apply to every task and prepared delivery."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.database import Base
from models.output_delivery import OutputDelivery, OutputDeliveryAttempt, OutputDestination, ScheduledTaskOutputBinding
from models.scheduled_task import ScheduledTask, ScheduledTaskRun
from output import service
from output import teams_workflow
from schemas.output_provider_schemas import OutputDestinationCreateSchema, OutputDestinationUpdateSchema


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[model.__table__ for model in (
        ScheduledTask, ScheduledTaskRun, OutputDestination, ScheduledTaskOutputBinding,
        OutputDelivery, OutputDeliveryAttempt,
    )])
    monkeypatch.setattr(teams_workflow.socket, "getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, ("20.1.2.3", 443))])
    with Session(engine) as session:
        yield session
    engine.dispose()


def task(task_id):
    return ScheduledTask(id=task_id, app_id=1, agent_id=1, created_by=1, name=f"Task {task_id}",
                         cron_expression="0 8 * * *", orchestrator_schedule_name=f"task-{task_id}")


@pytest.mark.parametrize("provider", ["teams_workflow", "webhook"])
def test_channel_mode_is_shared_by_tasks_and_cannot_be_overridden_by_binding(db, provider):
    destination = service.create_destination(
        db, app_id=1, created_by=1, name="Alerts", webhook_url="https://prod.logic.azure.com/trigger",
        provider_key=provider, content_mode="excerpt", public_config={"auth_mode": "none"} if provider == "webhook" else {},
    )
    tasks = [task(1), task(2)]
    db.add_all(tasks)
    db.commit()
    for current in tasks:
        # Legacy clients cannot overwrite the shared channel mode via task settings.
        service.replace_task_bindings(db, task=current, app_id=1, bindings=[{
            "destination_id": destination.id, "content_mode": "result",
        }])
    assert service.destination_dto(destination)["content_mode"] == "excerpt"

    deliveries = []
    for current in tasks:
        run = ScheduledTaskRun(scheduled_task_id=current.id, status="succeeded", scheduled_time=datetime.utcnow(),
                               orchestrator_run_id=f"run-{current.id}", output_text="x" * 6000)
        db.add(run)
        db.flush()
        deliveries.extend(service.create_deliveries_for_run(db, task=current, run=run))
    db.commit()
    for delivery in deliveries:
        assert delivery.destination_snapshot["content_mode"] == "excerpt"
        if provider == "webhook":
            assert delivery.payload["content"]["mode"] == "excerpt"
            assert len(delivery.payload["content"]["text"]) == 4000
        else:
            text = str(delivery.payload)
            assert "x" * 1199 in text
            assert "x" * 1201 not in text

    service.update_destination(db, destination, {"content_mode": "link_only"})
    for delivery in deliveries:
        assert delivery.destination_snapshot["content_mode"] == "excerpt"
    run = ScheduledTaskRun(scheduled_task_id=1, status="succeeded", scheduled_time=datetime.utcnow(),
                           orchestrator_run_id="new-run", output_text="new output")
    db.add(run)
    db.flush()
    latest = service.create_deliveries_for_run(db, task=tasks[0], run=run)[0]
    assert latest.destination_snapshot["content_mode"] == "link_only"
    if provider == "webhook":
        assert latest.payload["content"]["mode"] == "link_only"
        assert latest.payload["content"]["text"] is None
    else:
        assert "new output" not in str(latest.payload)


def test_mode_validation_and_patch_omission(db):
    with pytest.raises(ValueError):
        OutputDestinationCreateSchema(name="Alerts", webhook_url="https://example.com", content_mode="invalid")
    with pytest.raises(ValueError):
        OutputDestinationUpdateSchema(content_mode="invalid")
    with pytest.raises(ValueError, match="content mode"):
        service.create_destination(db, app_id=1, created_by=1, name="Alerts", webhook_url="https://example.com", content_mode="invalid")
    destination = service.create_destination(db, app_id=1, created_by=1, name="Alerts", webhook_url="https://prod.logic.azure.com/trigger", content_mode="excerpt")
    service.update_destination(db, destination, {"name": "Renamed"})
    assert destination.content_mode == "excerpt"
    assert service.destination_dto(destination)["content_mode"] == "excerpt"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["teams_workflow", "webhook"])
async def test_connection_test_uses_channel_content_mode(db, monkeypatch, provider):
    destination = service.create_destination(db, app_id=1, created_by=1, name="Alerts", webhook_url="https://prod.logic.azure.com/trigger",
                                             provider_key=provider, content_mode="link_only",
                                             public_config={"auth_mode": "none"} if provider == "webhook" else {})
    payloads = []
    async def send(url, payload, **kwargs):
        payloads.append(payload)
        return {"http_status": 202}
    monkeypatch.setattr(service.get_output_provider(provider), "send", send)
    assert await service.test_destination(destination) == {"http_status": 202}
    if provider == "webhook":
        assert payloads[0]["content"]["mode"] == "link_only"
        assert payloads[0]["content"]["text"] is None
    else:
        assert "This is a test notification" not in str(payloads[0])
