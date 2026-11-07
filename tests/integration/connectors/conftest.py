"""Fixtures for the PostgreSQL characterization tests of the output-channel outbox.

``committed_outbox`` commits REAL rows (independent ``SessionLocal()`` sessions,
no SAVEPOINT) because the concurrency tests need genuinely separate
connections. Teardown deletes everything it created, step by step, even when a
test failed; a cleanup step that fails is reported at the end of teardown
instead of silently leaking rows.

Only stable entry points are used (``scheduling.output_delivery`` and the
models) so these tests survive the later move of ``backend/output/``.
"""

import itertools
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from db.database import SessionLocal, engine
from models.agent import Agent
from models.ai_service import AIService
from models.app import App
from models.output_delivery import (
    OutputArtifact,
    OutputDelivery,
    OutputDeliveryAttempt,
    OutputDestination,
    ScheduledTaskOutputBinding,
)
from models.scheduled_task import ScheduledTask, ScheduledTaskRun
from models.user import User
from sqlalchemy import delete, event, or_, select
from utils.clock import utcnow_naive

TEAMS_URL = "https://prod.logic.azure.com/workflows/abc/triggers/manual?sig=secret"
WEBHOOK_URL = "https://hooks.example.com/mattin"
WEBHOOK_PUBLIC_CONFIG = {
    "schema_version": "1",
    "auth_mode": "none",
    "receiver_deduplicates": False,
    "include_attachments": False,
}

_counter = itertools.count(1)
logger = logging.getLogger(__name__)

LOCK_TIMEOUT = "10s"


@pytest.fixture(autouse=True)
def db_lock_timeout(test_engine):
    """DB-side ``lock_timeout`` for EVERY connection of the app engine.

    A blocked psycopg2 call freezes its thread (and an event loop, if it is the
    loop thread), so neither ``asyncio.wait_for`` nor a thread join can bound it.
    PostgreSQL itself aborts the lock wait after ``LOCK_TIMEOUT`` instead, which
    covers the code under test, the tests' own sessions and the cleanup.
    """
    def on_connect(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
        cursor.close()
        dbapi_connection.commit()

    event.listen(engine, "connect", on_connect)
    engine.dispose()  # pooled connections are re-created with the setting
    try:
        yield
    finally:
        event.remove(engine, "connect", on_connect)
        engine.dispose()


def _assert_no_foreign_eligible_rows() -> None:
    now = utcnow_naive()
    with SessionLocal() as session:
        stray = session.execute(
            select(OutputDelivery.id).where(or_(
                OutputDelivery.status.in_(["pending", "retry_wait"]),
                (OutputDelivery.status == "sending")
                & (OutputDelivery.lease_until.is_(None) | (OutputDelivery.lease_until <= now)),
            )).limit(5)
        ).scalars().all()
    if stray:
        pytest.fail(
            f"Outbox rows {stray} (pending / retry_wait / stale sending) exist before this fixture "
            "created anything: reset the test schema (the reconciler tests sweep the whole table)."
        )


@dataclass
class Outbox:
    """Ids of the committed graph plus helpers bound to it."""

    user_id: int | None = None
    app_id: int | None = None
    ai_service_id: int | None = None
    agent_id: int | None = None
    task_id: int | None = None
    run_id: int | None = None
    teams_destination_id: int | None = None
    webhook_destination_id: int | None = None
    teams_binding_id: int | None = None
    webhook_binding_id: int | None = None
    make_delivery: Callable[..., int] = field(default=None, repr=False)


def _cleanup(ob: Outbox) -> None:
    """Delete in FK order with the ORM/Core; each step in its own transaction."""
    errors: list[str] = []

    def step(label: str, statement) -> None:
        session = SessionLocal()
        try:
            session.execute(statement)
            session.commit()
        except Exception as exc:  # noqa: BLE001 - keep going: later steps still need to run
            session.rollback()
            errors.append(f"{label}: {exc!r}")
        finally:
            session.close()

    if ob.run_id is not None or ob.task_id is not None:
        run_ids = select(ScheduledTaskRun.id).where(ScheduledTaskRun.scheduled_task_id == ob.task_id)
        delivery_ids = select(OutputDelivery.id).where(OutputDelivery.run_id.in_(run_ids))
        step("attempts", delete(OutputDeliveryAttempt).where(OutputDeliveryAttempt.delivery_id.in_(delivery_ids)))
        step("deliveries", delete(OutputDelivery).where(OutputDelivery.run_id.in_(run_ids)))
        step("artifacts", delete(OutputArtifact).where(OutputArtifact.run_id.in_(run_ids)))
    if ob.task_id is not None:
        step("bindings", delete(ScheduledTaskOutputBinding).where(ScheduledTaskOutputBinding.scheduled_task_id == ob.task_id))
    if ob.app_id is not None:
        step("destinations", delete(OutputDestination).where(OutputDestination.app_id == ob.app_id))
    if ob.task_id is not None:
        step("runs", delete(ScheduledTaskRun).where(ScheduledTaskRun.scheduled_task_id == ob.task_id))
        step("task", delete(ScheduledTask).where(ScheduledTask.id == ob.task_id))
    if ob.agent_id is not None:
        step("agent", delete(Agent).where(Agent.agent_id == ob.agent_id))
    if ob.ai_service_id is not None:
        step("ai_service", delete(AIService).where(AIService.service_id == ob.ai_service_id))
    if ob.app_id is not None:
        step("app", delete(App).where(App.app_id == ob.app_id))
    if ob.user_id is not None:
        step("user", delete(User).where(User.user_id == ob.user_id))
    if errors:
        raise RuntimeError("committed_outbox cleanup left rows behind: " + "; ".join(errors))


@pytest.fixture
def committed_outbox(test_engine, monkeypatch, tmp_path):
    """A committed graph: app, task, succeeded run, Teams + webhook destinations/bindings."""
    monkeypatch.setenv("TMP_BASE_FOLDER", str(tmp_path))
    monkeypatch.setenv("FRONTEND_URL", "https://mattin.example")
    _assert_no_foreign_eligible_rows()
    ob = Outbox()
    tag = uuid.uuid4().hex[:12]
    session = SessionLocal()
    try:
        try:
            user = User(email=f"outbox-{tag}@mattin-test.com", name="Outbox User", is_active=True, platform_role="editor")
            session.add(user)
            session.flush()
            ob.user_id = user.user_id
            app = App(name=f"Outbox {tag}", slug=f"outbox-{tag}", owner_id=user.user_id, agent_rate_limit=0, max_file_size_mb=10)
            session.add(app)
            session.flush()
            ob.app_id = app.app_id
            ai = AIService(name=f"ai-{tag}", provider="OpenAI", api_key="sk-test-key", app_id=app.app_id)  # pragma: allowlist secret
            session.add(ai)
            session.flush()
            ob.ai_service_id = ai.service_id
            agent = Agent(
                name=f"agent-{tag}", description="outbox", system_prompt="x",
                app_id=app.app_id, service_id=ai.service_id, has_memory=False, temperature=0.7,
            )
            session.add(agent)
            session.flush()
            ob.agent_id = agent.agent_id
            task = ScheduledTask(
                name=f"task-{tag}", agent_id=agent.agent_id, app_id=app.app_id, created_by=user.user_id,
                orchestrator_schedule_name=f"sched-{tag}", cron_expression="0 8 * * *",
            )
            session.add(task)
            session.flush()
            ob.task_id = task.id
            run = ScheduledTaskRun(
                scheduled_task_id=task.id, orchestrator_run_id=f"run-{tag}",
                scheduled_time=utcnow_naive(), status="succeeded",
            )
            session.add(run)
            teams = OutputDestination(
                app_id=app.app_id, name=f"teams-{tag}", provider_key="teams_workflow", webhook_url=TEAMS_URL,
            )
            hook = OutputDestination(
                app_id=app.app_id, name=f"hook-{tag}", provider_key="webhook", webhook_url=WEBHOOK_URL,
                public_config=dict(WEBHOOK_PUBLIC_CONFIG),
            )
            session.add_all([teams, hook])
            session.flush()
            ob.run_id = run.id
            ob.teams_destination_id = teams.id
            ob.webhook_destination_id = hook.id
            tb = ScheduledTaskOutputBinding(scheduled_task_id=task.id, destination_id=teams.id)
            hb = ScheduledTaskOutputBinding(scheduled_task_id=task.id, destination_id=hook.id)
            session.add_all([tb, hb])
            session.flush()
            ob.teams_binding_id = tb.id
            ob.webhook_binding_id = hb.id
            session.commit()
        except BaseException:
            session.rollback()
            session.close()
            try:
                _cleanup(ob)
            except Exception:
                logger.exception("committed_outbox cleanup after a failed setup also failed")
            raise
        session.close()

        def make_delivery(kind: str = "webhook", *, snapshot: dict | None = None,
                          attempts: list[dict] | None = None, **fields) -> int:
            """Insert + commit an OutputDelivery. ``event_type`` is unique per call
            (the table is unique on run/binding/event_type)."""
            if kind == "webhook":
                base_snapshot = {
                    "provider_key": "webhook", "name": "hook", "content_mode": "result",
                    **WEBHOOK_PUBLIC_CONFIG, "content_type": "application/json",
                }
                defaults = {
                    "binding_id": ob.webhook_binding_id, "destination_id": ob.webhook_destination_id,
                    "payload": {"event_id": "evt-1", "event_type": "task.run.succeeded"},
                    "request_body": b'{"event_id":"evt-1"}',
                }
            elif kind == "teams":
                base_snapshot = {"provider_key": "teams_workflow", "name": "teams", "content_mode": "result"}
                defaults = {
                    "binding_id": ob.teams_binding_id, "destination_id": ob.teams_destination_id,
                    "payload": {"type": "message", "attachments": []},
                }
            else:
                raise ValueError(kind)
            values = {**defaults, **fields}
            values.setdefault("event_type", f"evt{next(_counter)}")
            values["destination_snapshot"] = {**base_snapshot, **(snapshot or {})}
            with SessionLocal() as s:
                delivery = OutputDelivery(run_id=ob.run_id, **values)
                s.add(delivery)
                s.flush()
                for number, attempt in enumerate(attempts or [], start=1):
                    s.add(OutputDeliveryAttempt(delivery_id=delivery.id, attempt_number=number, **attempt))
                s.commit()
                return delivery.id

        ob.make_delivery = make_delivery
        yield ob
    finally:
        _cleanup(ob)


class WebhookHttp:
    """Records requests that reach the (mocked) network."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.handler: Callable[[httpx.Request], Any] = self._ok

    @staticmethod
    async def _ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    async def dispatch(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return await self.handler(request)


@pytest.fixture
def webhook_http(monkeypatch):
    """Patch the global ``httpx.AsyncClient`` so every client uses a MockTransport."""
    mock = WebhookHttp()
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("transport", None)  # drop the SSRF-pinned transport
        return real_client(*args, transport=httpx.MockTransport(mock.dispatch), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return mock


@pytest.fixture
def enqueued(monkeypatch):
    """Capture ``enqueue_delivery`` calls and neutralize the spool sweep."""
    from scheduling import output_delivery

    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(output_delivery, "enqueue_delivery", lambda delivery_id, generation: calls.append((delivery_id, generation)))
    monkeypatch.setattr(output_delivery, "cleanup_spool_files", lambda db, **kw: 0)
    return calls
