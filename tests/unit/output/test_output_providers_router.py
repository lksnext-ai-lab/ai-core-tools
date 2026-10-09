"""Output destination and delivery endpoints, called directly against the SQLite outbox."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from models.output_delivery import OutputDelivery, OutputDestination, ScheduledTaskOutputBinding
from routers.internal import output_providers as router
from schemas.output_provider_schemas import (
    OutputDestinationCreateSchema,
    OutputDestinationUpdateSchema,
    ScheduledTaskOutputBindingsRequestSchema,
)

from .factories import TEAMS_URL, make_destination, make_run, make_task

AUTH = SimpleNamespace(identity=SimpleNamespace(id="7"))


@pytest.fixture
def db(outbox):
    with outbox() as session:
        session.add_all([make_task(), make_run(), make_destination(1, name="Alerts")])
        session.commit()
        yield session


def _delivery(db, *, status="failed", destination_id=1):
    binding = db.query(ScheduledTaskOutputBinding).filter_by(destination_id=destination_id).one_or_none()
    if binding is None:
        binding = ScheduledTaskOutputBinding(scheduled_task_id=1, destination_id=destination_id)
        db.add(binding)
        db.flush()
    delivery = OutputDelivery(run_id=1, binding_id=binding.id, destination_id=destination_id, status=status,
                              destination_snapshot={"name": "Alerts", "provider_key": "teams_workflow"})
    db.add(delivery)
    db.commit()
    return delivery


async def _status_of(coroutine):
    with pytest.raises(HTTPException) as caught:
        await coroutine
    return caught.value.status_code


@pytest.mark.asyncio
async def test_lists_registered_providers():
    providers = await router.list_output_providers(app_id=1, role=None)
    assert {item["key"] for item in providers} == {"teams_workflow", "webhook"}
    assert all(item["content_modes"] for item in providers)


@pytest.mark.asyncio
async def test_destination_crud(db):
    created = await router.create_output_destination(
        app_id=1, payload=OutputDestinationCreateSchema(name="Ops", webhook_url=TEAMS_URL), auth=AUTH, role=None, db=db,
    )
    assert created["name"] == "Ops" and db.get(OutputDestination, created["id"]).created_by == 7

    listed = await router.list_output_destinations(app_id=1, role=None, db=db)
    assert [item["name"] for item in listed] == ["Alerts", "Ops"]

    patched = await router.patch_output_destination(
        app_id=1, destination_id=created["id"], payload=OutputDestinationUpdateSchema(name="Ops 2"), role=None, db=db,
    )
    assert patched["name"] == "Ops 2"

    await router.delete_output_destination(app_id=1, destination_id=created["id"], role=None, db=db)
    assert db.get(OutputDestination, created["id"]) is None


@pytest.mark.asyncio
async def test_destination_errors_map_to_http_statuses(db):
    duplicate = OutputDestinationCreateSchema(name="Alerts", webhook_url=TEAMS_URL)
    assert await _status_of(router.create_output_destination(app_id=1, payload=duplicate, auth=AUTH, role=None, db=db)) == 400
    rename = OutputDestinationUpdateSchema(name="New")
    assert await _status_of(router.patch_output_destination(app_id=1, destination_id=99, payload=rename, role=None, db=db)) == 404
    other_workflow = OutputDestinationUpdateSchema(content_mode="link_only", webhook_url="https://prod.logic.azure.com/other")
    assert await _status_of(router.patch_output_destination(app_id=1, destination_id=1, payload=other_workflow, role=None, db=db)) == 400
    assert await _status_of(router.delete_output_destination(app_id=2, destination_id=1, role=None, db=db)) == 404


@pytest.mark.asyncio
async def test_deleting_a_bound_destination_keeps_history_and_cancels_pending(db):
    pending = _delivery(db, status="pending")
    accepted = OutputDelivery(run_id=1, binding_id=pending.binding_id, destination_id=1, status="accepted", event_type="other")
    db.add(accepted)
    db.commit()

    await router.delete_output_destination(app_id=1, destination_id=1, role=None, db=db)

    db.expire_all()
    destination = db.get(OutputDestination, 1)
    assert destination.enabled is False and destination.bindings[0].enabled is False
    assert db.get(OutputDelivery, pending.id).status == "cancelled"
    assert db.get(OutputDelivery, accepted.id).status == "accepted"


@pytest.mark.asyncio
async def test_connection_test_outcomes(db, monkeypatch):
    async def accepted(destination):
        return {"http_status": 202}

    monkeypatch.setattr(router, "test_destination", accepted)
    assert await router.test_output_destination(app_id=1, destination_id=1, role=None, db=db) == {"accepted": True, "http_status": 202}
    assert await _status_of(router.test_output_destination(app_id=1, destination_id=99, role=None, db=db)) == 400

    async def unreachable(destination):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(router, "test_destination", unreachable)
    assert await _status_of(router.test_output_destination(app_id=1, destination_id=1, role=None, db=db)) == 502


@pytest.mark.asyncio
async def test_task_output_bindings(db):
    payload = ScheduledTaskOutputBindingsRequestSchema(bindings=[{"destination_id": 1}])
    response = await router.put_task_outputs(app_id=1, task_id=1, payload=payload, role=None, db=db)
    assert [item["destination_id"] for item in response["bindings"]] == [1]
    assert (await router.get_task_outputs(app_id=1, task_id=1, role=None, db=db))["bindings"] == response["bindings"]

    missing = ScheduledTaskOutputBindingsRequestSchema(bindings=[{"destination_id": 99}])
    assert await _status_of(router.put_task_outputs(app_id=1, task_id=1, payload=missing, role=None, db=db)) == 400
    assert await _status_of(router.get_task_outputs(app_id=2, task_id=1, role=None, db=db)) == 404


@pytest.mark.asyncio
async def test_run_deliveries_listing(db):
    delivery = _delivery(db)
    listed = await router.list_run_deliveries(app_id=1, task_id=1, run_id=1, role=None, db=db)
    assert [item["id"] for item in listed["deliveries"]] == [delivery.id]
    assert await _status_of(router.list_run_deliveries(app_id=1, task_id=1, run_id=99, role=None, db=db)) == 404


@pytest.mark.asyncio
async def test_manual_retry(db, monkeypatch):
    queued = []
    monkeypatch.setattr(router, "enqueue_delivery", lambda delivery_id, generation: queued.append((delivery_id, generation)) or "wf-1")
    delivery = _delivery(db)

    response = await router.retry_run_delivery(app_id=1, task_id=1, run_id=1, delivery_id=delivery.id, role=None, db=db)

    assert response == {"delivery_id": delivery.id, "status": "queued", "workflow_id": "wf-1"}
    assert queued == [(delivery.id, 1)]
    # Now pending: a second manual retry is a conflict.
    assert await _status_of(router.retry_run_delivery(app_id=1, task_id=1, run_id=1, delivery_id=delivery.id, role=None, db=db)) == 409
    assert await _status_of(router.retry_run_delivery(app_id=1, task_id=1, run_id=1, delivery_id=999, role=None, db=db)) == 404


@pytest.mark.asyncio
async def test_manual_retry_without_queue_is_unavailable(db, monkeypatch):
    def unavailable(delivery_id, generation):
        raise RuntimeError("DBOS output delivery is not available")

    monkeypatch.setattr(router, "enqueue_delivery", unavailable)
    delivery = _delivery(db)
    assert await _status_of(router.retry_run_delivery(app_id=1, task_id=1, run_id=1, delivery_id=delivery.id, role=None, db=db)) == 503
