"""Output repositories against PostgreSQL: app isolation of id reads and SKIP LOCKED."""

import pytest
from db.database import SessionLocal
from models.app import App
from models.output_delivery import (
    OutputDelivery,
    OutputDestination,
    ScheduledTaskOutputBinding,
)
from models.scheduled_task import ScheduledTask, ScheduledTaskRun
from repositories.output_delivery_repository import OutputDeliveryRepository
from repositories.output_destination_repository import OutputDestinationRepository
from repositories.scheduled_task_output_binding_repository import (
    ScheduledTaskOutputBindingRepository,
)
from services.output_channels import deliveries
from services.output_channels.bindings import replace_task_bindings
from sqlalchemy.exc import OperationalError
from utils.clock import utcnow_naive

from tests.integration.connectors.helpers import past

pytestmark = pytest.mark.integration


@pytest.fixture
def two_apps(db, fake_user, fake_app, fake_agent):
    """fake_app owns a destination, a task, a run, a binding and a delivery; other_app owns nothing."""
    other_app = App(name="Other Workspace", slug="other-workspace-fixture", owner_id=fake_user.user_id,
                    agent_rate_limit=0, max_file_size_mb=10)
    db.add(other_app)
    destination = OutputDestination(
        app_id=fake_app.app_id, name="dest", provider_key="webhook", webhook_url="https://hooks.example.com/x",
    )
    task = ScheduledTask(
        name="task", agent_id=fake_agent.agent_id, app_id=fake_app.app_id, created_by=fake_user.user_id,
        orchestrator_schedule_name="sched-repo-iso", cron_expression="0 8 * * *",
    )
    db.add_all([destination, task])
    db.flush()
    run = ScheduledTaskRun(
        scheduled_task_id=task.id, orchestrator_run_id="run-repo-iso", scheduled_time=utcnow_naive(), status="succeeded",
    )
    binding = ScheduledTaskOutputBinding(scheduled_task_id=task.id, destination_id=destination.id)
    db.add_all([run, binding])
    db.flush()
    delivery = OutputDelivery(
        run_id=run.id, binding_id=binding.id, destination_id=destination.id, event_type="succeeded", status="pending",
    )
    db.add(delivery)
    db.flush()
    other_destination = OutputDestination(
        app_id=other_app.app_id, name="dest-b", provider_key="webhook", webhook_url="https://hooks.example.com/b",
    )
    other_task = ScheduledTask(
        name="task-b", agent_id=fake_agent.agent_id, app_id=other_app.app_id, created_by=fake_user.user_id,
        orchestrator_schedule_name="sched-repo-iso-b", cron_expression="0 8 * * *",
    )
    db.add_all([other_destination, other_task])
    db.flush()
    other_run = ScheduledTaskRun(
        scheduled_task_id=other_task.id, orchestrator_run_id="run-repo-iso-b", scheduled_time=utcnow_naive(),
        status="succeeded",
    )
    other_binding = ScheduledTaskOutputBinding(scheduled_task_id=other_task.id, destination_id=other_destination.id)
    db.add_all([other_run, other_binding])
    db.flush()
    other_delivery = OutputDelivery(
        run_id=other_run.id, binding_id=other_binding.id, destination_id=other_destination.id,
        event_type="succeeded", status="pending",
    )
    db.add(other_delivery)
    db.flush()
    return {"app": fake_app, "other_app": other_app, "destination": destination, "task": task, "run": run,
            "delivery": delivery, "other_destination": other_destination, "other_task": other_task,
            "other_run": other_run, "other_delivery": other_delivery}


def test_destination_read_is_scoped_by_app(db, two_apps):
    destination, app, other = two_apps["destination"], two_apps["app"], two_apps["other_app"]
    assert OutputDestinationRepository.get_by_id_and_app_id(db, destination.id, app.app_id) is destination
    assert OutputDestinationRepository.get_by_id_and_app_id(db, destination.id, other.app_id) is None
    assert OutputDestinationRepository.get_by_id_and_app_id(
        db, two_apps["other_destination"].id, app.app_id,
    ) is None
    assert OutputDestinationRepository.list_enabled_by_app(db, other.app_id) == [two_apps["other_destination"]]
    assert OutputDestinationRepository.list_enabled_by_app(db, app.app_id) == [destination]


def test_scoped_delivery_read_requires_matching_app_task_and_run(db, two_apps):
    delivery, app, other = two_apps["delivery"], two_apps["app"], two_apps["other_app"]
    task, run = two_apps["task"], two_apps["run"]
    found = OutputDeliveryRepository.get_scoped(
        db, app_id=app.app_id, task_id=task.id, run_id=run.id, delivery_id=delivery.id,
    )
    assert found is delivery
    assert OutputDeliveryRepository.get_scoped(
        db, app_id=other.app_id, task_id=task.id, run_id=run.id, delivery_id=delivery.id,
    ) is None
    assert OutputDeliveryRepository.get_scoped(
        db, app_id=app.app_id, task_id=task.id + 1000, run_id=run.id, delivery_id=delivery.id,
    ) is None
    assert OutputDeliveryRepository.get_scoped(
        db, app_id=app.app_id, task_id=task.id, run_id=run.id + 1000, delivery_id=delivery.id,
    ) is None


def test_mixed_real_ids_never_cross_apps(db, two_apps):
    app, task, run, delivery = two_apps["app"], two_apps["task"], two_apps["run"], two_apps["delivery"]
    other_run, other_delivery = two_apps["other_run"], two_apps["other_delivery"]
    assert OutputDeliveryRepository.get_scoped(
        db, app_id=app.app_id, task_id=task.id, run_id=other_run.id, delivery_id=other_delivery.id,
    ) is None
    assert OutputDeliveryRepository.get_scoped(
        db, app_id=app.app_id, task_id=task.id, run_id=run.id, delivery_id=other_delivery.id,
    ) is None
    assert deliveries.list_run_deliveries(db, task, other_run.id) is None
    assert [item["id"] for item in deliveries.list_run_deliveries(db, task, run.id)] == [delivery.id]
    with pytest.raises(ValueError, match="Output destination not found"):
        replace_task_bindings(
            db, task=task, app_id=app.app_id, bindings=[{"destination_id": two_apps["other_destination"].id}],
        )


def test_binding_views_are_scoped_by_app(db, two_apps):
    task, other = two_apps["task"], two_apps["other_app"]
    assert ScheduledTaskOutputBindingRepository.list_enabled_view(db, task.id, other.app_id) == []
    assert ScheduledTaskOutputBindingRepository.list_enabled_with_enabled_destination(db, task.id, other.app_id) == []
    assert len(ScheduledTaskOutputBindingRepository.list_enabled_view(db, task.id, two_apps["app"].app_id)) == 1


def test_cancel_pending_only_touches_target_destination_and_open_states(db, two_apps):
    destination, delivery = two_apps["destination"], two_apps["delivery"]
    retry = OutputDelivery(
        run_id=delivery.run_id, binding_id=delivery.binding_id, destination_id=destination.id,
        event_type="e-retry", status="retry_wait",
    )
    accepted = OutputDelivery(
        run_id=delivery.run_id, binding_id=delivery.binding_id, destination_id=destination.id,
        event_type="e-accepted", status="accepted",
    )
    db.add_all([retry, accepted])
    db.flush()
    OutputDeliveryRepository.cancel_pending_for_destination(db, destination.id)
    db.expire_all()
    assert delivery.status == "cancelled" and retry.status == "cancelled"
    assert accepted.status == "accepted"
    assert two_apps["other_delivery"].status == "pending"


class TestLockDueForReconcileSkipLocked:
    def test_locked_row_is_skipped(self, committed_outbox):
        locked_id = committed_outbox.make_delivery("webhook", status="pending", updated_at=past(1000))
        free_id = committed_outbox.make_delivery("webhook", status="pending", updated_at=past(1000))
        holder = SessionLocal()
        contender = SessionLocal()
        try:
            assert OutputDeliveryRepository.get_for_update(holder, locked_id) is not None
            rows = OutputDeliveryRepository.lock_due_for_reconcile(contender, utcnow_naive())
            ids = {row.id for row in rows}
            assert free_id in ids
            assert locked_id not in ids
            # The contender holds an exclusive (FOR UPDATE) lock on the row it took, not a shared one.
            third = SessionLocal()
            try:
                with pytest.raises(OperationalError):
                    third.query(OutputDelivery).filter_by(id=free_id).with_for_update(nowait=True).one()
            finally:
                third.rollback()
                third.close()
        finally:
            contender.rollback()
            contender.close()
            holder.rollback()
            holder.close()
