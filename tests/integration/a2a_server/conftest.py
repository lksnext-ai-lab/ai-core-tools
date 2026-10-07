"""Fixtures for the a2a-sdk contract suite (step_002) and the SDK runtime (step_012).

`a2a_sdk_tables` asserts the `a2a_*` SDK tables exist on the test DB. As of
step_007, `tests/conftest.py`'s session-scoped `test_engine` fixture is the
sole owner of their lifecycle: it creates them (via
`services.a2a_server.sdk_models.get_sdk_metadata()`, the same registry
`services/a2a_server/storage.py` binds the SDK store/stream to) right after
`Base.metadata.create_all`, and drops them at session teardown. This fixture
therefore no longer creates or drops anything itself (RB-10) -- that would
race with `test_engine`'s ownership of the same tables.

`a2a_committed_world` and `a2a_runtime_factory` (step_012) are the committed
fixtures every later A2A integration test that runs the bridge or the SDK
store is expected to use (plan.md's shared conventions): the `db` fixture's
savepoint-rollback session is invisible to code that opens its own
`SessionLocal()` or uses `async_engine` (the bridge, the SDK store), so
those tests need rows that are genuinely committed -- and cleaned up
explicitly, since there is no outer transaction to roll back.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Optional

import pytest
from a2a.server.agent_execution.agent_executor import AgentExecutor
from sqlalchemy import inspect

from db.database import SessionLocal
from models.a2a_context_link import A2AContextLink
from models.agent import Agent
from models.ai_service import AIService
from models.api_key import APIKey
from models.app import App
from models.conversation import Conversation
from models.user import User
from services.a2a_server.identity import owner_prefix
from services.a2a_server.sdk_models import EVENTS_TABLE, TASKS_TABLE, VERSIONS_TABLE, get_sdk_models
from services.api_key_service import APIKeyService
from utils.logger import get_logger

logger = get_logger(__name__)


@pytest.fixture(scope="session")
def a2a_sdk_tables(test_engine):
    """Asserts the `a2a_tasks`/`a2a_task_events`/`a2a_task_versions` tables exist.

    `test_engine` (session-scoped, `tests/conftest.py`) already created them.
    This fixture is purely a guard so a test that depends on it fails with a
    clear message rather than a confusing "relation does not exist" error if
    that assumption ever breaks.
    """
    inspector = inspect(test_engine)
    for table in (TASKS_TABLE, EVENTS_TABLE, VERSIONS_TABLE):
        assert inspector.has_table(table), (
            f"{table!r} does not exist on the test DB; tests/conftest.py's test_engine "
            "fixture should have created it via get_sdk_metadata()"
        )
    yield


class A2ACommittedWorld:
    """A committed (User, App, AIService, Agents, APIKeys) fixture world (step_012).

    Agents, by label:
      - ``agent_public``: ``a2a_enabled=True``, ``a2a_card_visibility='public'``.
      - ``agent_api_key``: ``a2a_enabled=True``, ``a2a_card_visibility='api_key'``.
      - ``agent_disabled``: ``a2a_enabled=False``.
      - ``agent_frozen``: ``a2a_enabled=True``, ``is_frozen=True``.
      - ``other_agent``: a second app's agent, ``a2a_enabled=True``, public.

    Keys: ``key_1``/``key_2`` belong to ``app_id``; ``other_key`` belongs to
    ``other_app_id``. Raw key strings are on the matching ``*_raw`` attribute.
    """

    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


def _create_agent(session, *, app_id: int, service_id: int, label: str, **a2a_fields) -> Agent:
    agent = Agent(
        app_id=app_id,
        service_id=service_id,
        name=f"A2A {label} {uuid.uuid4().hex[:8]}",
        type="agent",
        has_memory=False,
        **a2a_fields,
    )
    session.add(agent)
    return agent


def _create_api_key(session, *, app_id: int, user_id: int, name: str) -> APIKey:
    key = APIKey(
        key=APIKeyService.generate_api_key(),
        name=name,
        app_id=app_id,
        user_id=user_id,
        is_active=True,
        created_at=datetime.utcnow(),
    )
    session.add(key)
    return key


@pytest.fixture
def a2a_committed_world(a2a_sdk_tables):
    """Builds a committed world of (User, App, AIService, Agents, APIKeys) for
    step_012+ integration tests that exercise the bridge or the SDK store
    directly (both use their own `SessionLocal()`/`async_engine`, invisible
    to the `db` fixture's rolled-back transaction).

    Cleans up after itself: deletes the `a2a_*` SDK rows for this world's
    owner prefixes first (so FK-free registry tables never outlive the Agent
    rows they were scoped under), then the Mattin rows in dependency order.
    """
    session = SessionLocal()
    try:
        label = uuid.uuid4().hex[:8]
        user = User(email=f"a2a-world-{label}@example.com", name=f"A2A World {label}")
        session.add(user)
        session.flush()

        app = App(name=f"A2A World App {label}", slug=f"acme-{label}")
        other_app = App(name=f"A2A World Other App {label}", slug=f"acme-other-{label}")
        session.add_all([app, other_app])
        session.flush()

        # Each app gets its own AIService (item 10 of the step_012 fix round):
        # `other_agent` previously pointed at `app`'s AIService even though it
        # belongs to `other_app` -- not FK-enforced, but a referential
        # inconsistency a cascade-delete fallback should not have to special-case.
        ai_service = AIService(name=f"A2A World AIService {label}", provider="OpenAI", app_id=app.app_id)
        other_ai_service = AIService(
            name=f"A2A World Other AIService {label}", provider="OpenAI", app_id=other_app.app_id
        )
        session.add_all([ai_service, other_ai_service])
        session.flush()

        agent_public = _create_agent(
            session, app_id=app.app_id, service_id=ai_service.service_id, label="public",
            a2a_enabled=True, a2a_card_visibility="public",
        )
        agent_api_key = _create_agent(
            session, app_id=app.app_id, service_id=ai_service.service_id, label="api_key",
            a2a_enabled=True, a2a_card_visibility="api_key",
        )
        agent_disabled = _create_agent(
            session, app_id=app.app_id, service_id=ai_service.service_id, label="disabled",
            a2a_enabled=False,
        )
        agent_frozen = _create_agent(
            session, app_id=app.app_id, service_id=ai_service.service_id, label="frozen",
            a2a_enabled=True, a2a_card_visibility="public", is_frozen=True,
        )
        other_agent = _create_agent(
            session, app_id=other_app.app_id, service_id=other_ai_service.service_id, label="other",
            a2a_enabled=True, a2a_card_visibility="public",
        )
        session.flush()

        key_1 = _create_api_key(session, app_id=app.app_id, user_id=user.user_id, name="key-1")
        key_2 = _create_api_key(session, app_id=app.app_id, user_id=user.user_id, name="key-2")
        other_key = _create_api_key(session, app_id=other_app.app_id, user_id=user.user_id, name="other-key")
        session.commit()

        world = A2ACommittedWorld(
            user_id=user.user_id,
            app_id=app.app_id,
            app_slug=app.slug,
            other_app_id=other_app.app_id,
            other_app_slug=other_app.slug,
            ai_service_id=ai_service.service_id,
            other_ai_service_id=other_ai_service.service_id,
            agent_public_id=agent_public.agent_id,
            agent_api_key_id=agent_api_key.agent_id,
            agent_disabled_id=agent_disabled.agent_id,
            agent_frozen_id=agent_frozen.agent_id,
            other_agent_id=other_agent.agent_id,
            key_1_id=key_1.key_id,
            key_1_raw=key_1.key,
            key_2_id=key_2.key_id,
            key_2_raw=key_2.key,
            other_key_id=other_key.key_id,
            other_key_raw=other_key.key,
        )
    finally:
        session.close()

    try:
        yield world
    finally:
        _cleanup_committed_world(world)


def _purge_sdk_rows(world: A2ACommittedWorld) -> None:
    """Purges `a2a_*` SDK rows for this world's owner prefixes, in their own
    committed transaction, **before** any Mattin row is touched (item 10):
    these tables have no FK to `Agent`/`App`, so nothing requires this
    ordering structurally, but doing it first means a registry row can never
    outlive the Agent it was scoped under even if the Mattin-row cleanup
    below fails partway and raises.
    """
    session = SessionLocal()
    try:
        models = get_sdk_models()
        for app_id in (world.app_id, world.other_app_id):
            # "%" is not a meaningful character in an AD-3 owner string (the
            # charset is digits, ":" and the lowercase-hex key hash), so the
            # prefix needs no escaping for a LIKE pattern (RB-11: owner-prefix
            # LIKE match, no raw table SQL).
            prefix = owner_prefix(app_id)
            for model in (models.version, models.event, models.task):
                session.query(model).filter(model.owner.like(f"{prefix}%")).delete(
                    synchronize_session=False
                )
        session.commit()
    finally:
        session.close()


def _manual_delete_app(session, app_id: int) -> None:
    """Dependency-ordered fallback delete for one app's rows, scoped entirely
    by `app_id` (never by the world's cached id lists, so it stays correct
    even if a test mutated/added rows under that app)."""
    agent_ids = [row.agent_id for row in session.query(Agent.agent_id).filter(Agent.app_id == app_id).all()]
    if agent_ids:
        session.query(A2AContextLink).filter(A2AContextLink.agent_id.in_(agent_ids)).delete(
            synchronize_session=False
        )
        session.query(Conversation).filter(Conversation.agent_id.in_(agent_ids)).delete(
            synchronize_session=False
        )
    session.query(APIKey).filter(APIKey.app_id == app_id).delete(synchronize_session=False)
    session.query(Agent).filter(Agent.app_id == app_id).delete(synchronize_session=False)
    session.query(AIService).filter(AIService.app_id == app_id).delete(synchronize_session=False)
    session.query(App).filter(App.app_id == app_id).delete(synchronize_session=False)


def _delete_app_with_fallback(app_id: int, errors: list) -> None:
    """Tries `AppService.delete_app` (the real cascade every other app-deletion
    path uses); falls back to `_manual_delete_app` if it does not fit this
    fixture's minimal world (item 10). Logs and records -- never silently
    swallows -- whichever path fails."""
    session = SessionLocal()
    try:
        from services.app_service import AppService

        if AppService(session).delete_app(app_id):
            session.commit()
            return
        logger.warning("a2a_committed_world cleanup: AppService.delete_app(%s) returned False", app_id)
    except Exception as exc:  # noqa: BLE001 - this is best-effort test cleanup, not app code
        session.rollback()
        logger.warning(
            "a2a_committed_world cleanup: AppService.delete_app(%s) raised %r; falling back to a "
            "manual delete", app_id, exc,
        )
    finally:
        session.close()

    session = SessionLocal()
    try:
        _manual_delete_app(session, app_id)
        session.commit()
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.error("a2a_committed_world cleanup: manual fallback delete for app %s failed: %r", app_id, exc)
        errors.append(exc)
    finally:
        session.close()


def _cleanup_committed_world(world: A2ACommittedWorld) -> None:
    """Cleans up a committed world: SDK rows first (own transaction), then the
    Mattin rows per app (own transaction each), then the user. Every step is
    try/log'd independently so one failure does not prevent the rest of the
    cleanup from running; any collected errors are re-raised together at the
    end so a broken cleanup still fails the test run instead of silently
    leaking rows into the shared test DB.
    """
    errors: list = []

    try:
        _purge_sdk_rows(world)
    except Exception as exc:  # noqa: BLE001
        logger.error("a2a_committed_world cleanup: failed to purge SDK rows: %r", exc)
        errors.append(exc)

    for app_id in (world.app_id, world.other_app_id):
        _delete_app_with_fallback(app_id, errors)

    session = SessionLocal()
    try:
        session.query(User).filter(User.user_id == world.user_id).delete(synchronize_session=False)
        session.commit()
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.error("a2a_committed_world cleanup: failed to delete user %s: %r", world.user_id, exc)
        errors.append(exc)
    finally:
        session.close()

    if errors:
        raise RuntimeError(f"a2a_committed_world cleanup hit {len(errors)} error(s): {errors!r}")


@pytest.fixture
async def a2a_runtime_factory():
    """Builds `A2ARuntime`s (step_012) against the shared async engine (which, under
    pytest-env, points at the test DB).

    An **async** fixture (item 5): it builds/tears down in the same event
    loop the test itself runs in (pytest-asyncio, `asyncio_mode = auto`),
    rather than a second loop spun up just for teardown -- avoiding any
    cross-loop object-ownership surprise with the asyncpg connections the
    SDK store/stream hold.

    `executor` defaults to a minimal `AgentExecutor` that does nothing (`execute`
    raises `NotImplementedError` if a test forgets to override it, so a silent
    no-op never masks a bug); most callers pass their own scripted executor.

    Teardown closes every built runtime independently, each under its own
    10s `asyncio.wait_for`; if any `aclose()` raises or times out, the
    fixture still attempts the rest and then fails the test with all
    collected errors (never silently swallows a close failure).
    """
    from services.a2a_server.runtime import build_a2a_runtime

    built: list = []

    class _UnimplementedExecutor(AgentExecutor):
        async def execute(self, context, event_queue) -> None:
            raise NotImplementedError("a2a_runtime_factory() was not given an executor")

        async def cancel(self, context, event_queue) -> None:
            raise NotImplementedError("a2a_runtime_factory() was not given an executor")

    def _factory(executor: Optional[AgentExecutor] = None, *, engine=None):
        rt = build_a2a_runtime(executor or _UnimplementedExecutor(), engine=engine)
        built.append(rt)
        return rt

    yield _factory

    errors: list = []
    for rt in built:
        try:
            await asyncio.wait_for(rt.handler.aclose(), timeout=10)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
    if errors:
        raise RuntimeError(f"a2a_runtime_factory: {len(errors)} runtime(s) failed to close cleanly: {errors!r}")
