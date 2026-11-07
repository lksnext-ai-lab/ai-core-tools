"""FK cascade / router-delete characterization for the output-channel tables.

Uses the SAVEPOINT-isolated ``db`` fixture (nothing is committed for real).
Existence is checked with ``select(count)`` queries rather than ``db.get`` so a
stale identity map can never mask a Core DELETE.
"""

import pytest
from models.output_delivery import (
    OutputArtifact,
    OutputDelivery,
    OutputDeliveryAttempt,
    OutputDestination,
    ScheduledTaskOutputBinding,
)
from models.scheduled_task import ScheduledTask, ScheduledTaskRun
from sqlalchemy import delete, func, select
from utils.clock import utcnow_naive

pytestmark = pytest.mark.integration


@pytest.fixture
def graph(db, fake_app, fake_agent, fake_user):
    """task, run, destination, binding, delivery, attempt and artifact (flushed)."""
    task = ScheduledTask(
        name="t", agent_id=fake_agent.agent_id, app_id=fake_app.app_id, created_by=fake_user.user_id,
        orchestrator_schedule_name="sched-cascade-test", cron_expression="0 8 * * *",
    )
    db.add(task)
    db.flush()
    run = ScheduledTaskRun(
        scheduled_task_id=task.id, orchestrator_run_id="run-cascade", scheduled_time=utcnow_naive(), status="succeeded",
    )
    dest = OutputDestination(app_id=fake_app.app_id, name="d", provider_key="webhook", webhook_url="https://hooks.example.com/x")
    db.add_all([run, dest])
    db.flush()
    binding = ScheduledTaskOutputBinding(scheduled_task_id=task.id, destination_id=dest.id)
    db.add(binding)
    db.flush()
    delivery = OutputDelivery(run_id=run.id, binding_id=binding.id, destination_id=dest.id, status="pending")
    artifact = OutputArtifact(
        run_id=run.id, file_id="f1", filename="a.txt", content_type="text/plain", size_bytes=1, sha256="0" * 64, object_key="k",
    )
    db.add_all([delivery, artifact])
    db.flush()
    attempt = OutputDeliveryAttempt(delivery_id=delivery.id, attempt_number=1)
    db.add(attempt)
    db.flush()
    objs = {
        "task": task, "run": run, "dest": dest, "binding": binding,
        "delivery": delivery, "attempt": attempt, "artifact": artifact,
    }
    # Plain ids: ORM instances become unusable once their row is deleted/expired.
    objs["ids"] = {key: obj.id for key, obj in objs.items()}
    return objs


def _count(db, model, column, value) -> int:
    return db.execute(select(func.count()).select_from(model).where(column == value)).scalar_one()


def _counts(db, g) -> dict[str, int]:
    ids = g["ids"]
    return {
        "destination": _count(db, OutputDestination, OutputDestination.id, ids["dest"]),
        "binding": _count(db, ScheduledTaskOutputBinding, ScheduledTaskOutputBinding.id, ids["binding"]),
        "delivery": _count(db, OutputDelivery, OutputDelivery.id, ids["delivery"]),
        "attempt": _count(db, OutputDeliveryAttempt, OutputDeliveryAttempt.id, ids["attempt"]),
        "artifact": _count(db, OutputArtifact, OutputArtifact.id, ids["artifact"]),
        "run": _count(db, ScheduledTaskRun, ScheduledTaskRun.id, ids["run"]),
    }


class TestAppDelete:
    def test_delete_app_removes_the_whole_output_graph(self, db, fake_app, graph):
        from services.app_service import AppService

        ids = graph["ids"]
        assert all(v == 1 for v in _counts(db, graph).values())

        assert AppService(db).delete_app(fake_app.app_id) is True
        db.expire_all()

        assert _count(db, OutputDestination, OutputDestination.id, ids["dest"]) == 0
        assert _count(db, ScheduledTaskOutputBinding, ScheduledTaskOutputBinding.id, ids["binding"]) == 0
        assert _count(db, ScheduledTaskRun, ScheduledTaskRun.id, ids["run"]) == 0
        assert _count(db, OutputDelivery, OutputDelivery.id, ids["delivery"]) == 0
        assert _count(db, OutputDeliveryAttempt, OutputDeliveryAttempt.id, ids["attempt"]) == 0
        assert _count(db, OutputArtifact, OutputArtifact.id, ids["artifact"]) == 0
        assert _count(db, ScheduledTask, ScheduledTask.id, ids["task"]) == 0


class TestDeliveryDelete:
    def test_orm_delete_removes_attempts(self, db, graph):
        db.delete(graph["delivery"])
        db.flush()
        counts = _counts(db, graph)
        assert counts["delivery"] == 0
        assert counts["attempt"] == 0
        # Siblings untouched.
        assert counts["binding"] == counts["destination"] == counts["artifact"] == 1

    def test_core_delete_cascades_attempts_in_the_database(self, db, graph):
        db.execute(delete(OutputDelivery).where(OutputDelivery.id == graph["ids"]["delivery"]))
        db.expire_all()
        counts = _counts(db, graph)
        assert counts["delivery"] == 0
        assert counts["attempt"] == 0  # FK ON DELETE CASCADE
        assert counts["binding"] == counts["destination"] == 1


class TestDestinationDelete:
    def test_core_delete_cascades_bindings_deliveries_and_attempts(self, db, graph):
        """Deleting a destination removes bindings (CASCADE), which removes the
        deliveries attached via ``binding_id`` (CASCADE) and their attempts.

        ``OutputDelivery.destination_id`` is ``ON DELETE SET NULL`` but that
        never becomes observable: the binding cascade deletes the delivery row
        first, so no delivery survives with ``destination_id IS NULL``.
        """
        db.execute(delete(OutputDestination).where(OutputDestination.id == graph["ids"]["dest"]))
        db.expire_all()
        counts = _counts(db, graph)
        assert counts["destination"] == 0
        assert counts["binding"] == 0
        assert counts["delivery"] == 0
        assert counts["attempt"] == 0
        # The run and its artifacts are independent of the destination.
        assert counts["run"] == 1
        assert counts["artifact"] == 1

    def test_orm_delete_has_the_same_effect(self, db, graph):
        """ORM ``db.delete(destination)`` cascades through the relationships
        (bindings -> deliveries -> attempts); end state equals the Core delete."""
        db.delete(graph["dest"])
        db.flush()
        db.expire_all()
        counts = _counts(db, graph)
        assert counts == {
            "destination": 0, "binding": 0, "delivery": 0, "attempt": 0, "artifact": 1, "run": 1,
        }


class TestRouterDelete:
    async def test_delete_with_bindings_disables_instead_of_deleting(self, db, fake_app, graph):
        from routers.internal.output_providers import delete_output_destination

        dest, binding = graph["dest"], graph["binding"]
        pending = graph["delivery"]
        retry = OutputDelivery(
            run_id=graph["run"].id, binding_id=binding.id, destination_id=dest.id,
            event_type="retry-case", status="retry_wait",
        )
        accepted = OutputDelivery(
            run_id=graph["run"].id, binding_id=binding.id, destination_id=dest.id,
            event_type="accepted-case", status="accepted",
        )
        db.add_all([retry, accepted])
        db.flush()

        result = await delete_output_destination(
            app_id=fake_app.app_id, destination_id=dest.id, role=None, db=db,
        )
        assert result is None

        db.expire_all()
        assert _count(db, OutputDestination, OutputDestination.id, dest.id) == 1
        assert db.get(OutputDestination, dest.id).enabled is False
        assert db.get(ScheduledTaskOutputBinding, binding.id).enabled is False
        assert db.get(OutputDelivery, pending.id).status == "cancelled"
        assert db.get(OutputDelivery, retry.id).status == "cancelled"
        assert db.get(OutputDelivery, accepted.id).status == "accepted"

    async def test_delete_without_bindings_removes_the_row(self, db, fake_app, graph):
        from routers.internal.output_providers import delete_output_destination

        lonely = OutputDestination(app_id=fake_app.app_id, name="lonely", provider_key="webhook", webhook_url="https://hooks.example.com/l")
        db.add(lonely)
        db.flush()
        lonely_id = lonely.id
        await delete_output_destination(app_id=fake_app.app_id, destination_id=lonely_id, role=None, db=db)
        db.expire_all()
        assert _count(db, OutputDestination, OutputDestination.id, lonely_id) == 0
