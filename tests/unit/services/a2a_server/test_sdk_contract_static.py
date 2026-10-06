"""Static (no-DB) half of the a2a-sdk contract suite for `services/a2a_server` (AD-2).

**Why this suite exists.** `a2a-sdk==1.2.2` is exact-pinned because
`storage.py` writes three private attributes
(`store._event_model`, `store._version_model`, `stream._event_model`) and
relies on the meaning of one public one (`store.as_task_store.task_model`). A
patch release could rename or repurpose any of them. This suite is the gate
that must pass again before the pin is ever bumped (see the comment above
the `a2a-sdk` line in `pyproject.toml`).

Every assertion message says: "a2a-sdk contract changed; review
services/a2a_server/storage.py before bumping the pin" so a failure points
straight at the file to review.

These tests need no DB and run fast: they check the installed SDK's version
and shape only. The behavioural half (real test DB, `build_bound_storage`,
AD-6 cancellation end-to-end) lives in
`tests/integration/a2a_server/test_sdk_contract.py`.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import inspect
import uuid

import pytest
import sqlalchemy as sa
from a2a.server import models as a2a_sdk_models
from a2a.server.cluster.database_event_stream import DatabaseTaskEventStream
from a2a.server.cluster.database_task_store import VersionedDatabaseTaskStore
from services.a2a_server.sdk_models import (
    EVENTS_TABLE,
    TASKS_TABLE,
    VERSIONS_TABLE,
    get_sdk_models,
)
from services.a2a_server.storage import build_bound_storage
from sqlalchemy.ext.asyncio import create_async_engine

_CONTRACT_MSG = (
    "a2a-sdk contract changed; review services/a2a_server/storage.py before bumping the pin"
)


def _test_owner_resolver(_context) -> str:
    """A fixed, AD-3-shaped owner. These tests never execute a real task, so
    the resolver's return value is never read -- it only has to satisfy
    `build_bound_storage`'s now-required `owner_resolver` parameter."""
    return "a2a:static-contract-test:owner"


class TestStaticContract:
    """Shape/version checks against the installed a2a-sdk. No DB required."""

    def test_pinned_sdk_version(self) -> None:
        assert importlib.metadata.version("a2a-sdk") == "1.2.2", (
            f"{_CONTRACT_MSG}: installed a2a-sdk version changed"
        )

    def test_versioned_task_store_constructor_signature(self) -> None:
        params = inspect.signature(VersionedDatabaseTaskStore.__init__).parameters
        names = list(params)[1:]  # drop `self`
        assert names == [
            "engine",
            "create_table",
            "table_name",
            "owner_resolver",
            "core_to_model_conversion",
            "model_to_core_conversion",
            "event_table_name",
            "version_table_name",
            "max_attempts",
            "retry_delay_s",
        ], f"{_CONTRACT_MSG}: VersionedDatabaseTaskStore.__init__ signature changed"
        assert params["table_name"].default == "tasks", _CONTRACT_MSG
        assert params["event_table_name"].default == "task_events", _CONTRACT_MSG
        assert params["version_table_name"].default == "task_versions", _CONTRACT_MSG
        assert params["create_table"].default is True, _CONTRACT_MSG

    def test_database_task_event_stream_constructor_signature(self) -> None:
        params = inspect.signature(DatabaseTaskEventStream.__init__).parameters
        names = list(params)[1:]
        assert names == [
            "engine",
            "create_table",
            "table_name",
            "poll_interval_s",
        ], f"{_CONTRACT_MSG}: DatabaseTaskEventStream.__init__ signature changed"
        assert params["table_name"].default == "task_events", _CONTRACT_MSG
        assert params["create_table"].default is True, _CONTRACT_MSG

    def test_model_factory_signatures(self) -> None:
        for factory_name, default_table in (
            ("create_task_model", "tasks"),
            ("create_task_event_model", "task_events"),
            ("create_task_version_model", "task_versions"),
        ):
            factory = getattr(a2a_sdk_models, factory_name)
            params = inspect.signature(factory).parameters
            assert list(params) == ["table_name", "base"], (
                f"{_CONTRACT_MSG}: {factory_name} signature changed"
            )
            assert params["table_name"].default == default_table, _CONTRACT_MSG

    def test_fresh_store_and_stream_use_sdk_default_models(self) -> None:
        """An unbound store/stream takes the no-factory branch (AD-2 point 2)."""
        engine = create_async_engine("postgresql+psycopg://user:pass@localhost/unused")
        try:
            store = VersionedDatabaseTaskStore(engine, create_table=False)
            stream = DatabaseTaskEventStream(engine, create_table=False)
            assert store.as_task_store.task_model is a2a_sdk_models.TaskModel, _CONTRACT_MSG
            # contract: test_sdk_contract_static.py::test_fresh_store_and_stream_use_sdk_default_models
            assert store._event_model is a2a_sdk_models.TaskEventModel, _CONTRACT_MSG
            assert store._version_model is a2a_sdk_models.TaskVersionModel, _CONTRACT_MSG
            assert stream._event_model is a2a_sdk_models.TaskEventModel, _CONTRACT_MSG
        finally:
            asyncio.run(engine.dispose())

    def test_bound_storage_attributes(self) -> None:
        engine = create_async_engine("postgresql+psycopg://user:pass@localhost/unused")
        try:
            store, stream = build_bound_storage(engine=engine, owner_resolver=_test_owner_resolver)
            models = get_sdk_models()
            assert store.as_task_store.task_model is models.task, _CONTRACT_MSG
            assert store._event_model is models.event, _CONTRACT_MSG  # contract: test_sdk_contract_static.py::test_bound_storage_attributes
            assert store._version_model is models.version, _CONTRACT_MSG  # contract: test_sdk_contract_static.py::test_bound_storage_attributes
            assert stream._event_model is models.event, _CONTRACT_MSG  # contract: test_sdk_contract_static.py::test_bound_storage_attributes
            assert store.as_task_store.task_model.__tablename__ == TASKS_TABLE, _CONTRACT_MSG
            assert store._event_model.__tablename__ == EVENTS_TABLE, _CONTRACT_MSG
            assert store._version_model.__tablename__ == VERSIONS_TABLE, _CONTRACT_MSG
        finally:
            asyncio.run(engine.dispose())

    def test_build_bound_storage_is_idempotent_across_calls(self) -> None:
        engine = create_async_engine("postgresql+psycopg://user:pass@localhost/unused")
        try:
            store1, stream1 = build_bound_storage(engine=engine, owner_resolver=_test_owner_resolver)
            store2, stream2 = build_bound_storage(engine=engine, owner_resolver=_test_owner_resolver)
            assert store1.as_task_store.task_model is store2.as_task_store.task_model, _CONTRACT_MSG
            assert store1._event_model is store2._event_model, _CONTRACT_MSG  # contract: test_sdk_contract_static.py::test_build_bound_storage_is_idempotent_across_calls
            assert store1._version_model is store2._version_model, _CONTRACT_MSG  # contract: test_sdk_contract_static.py::test_build_bound_storage_is_idempotent_across_calls
            assert stream1._event_model is stream2._event_model, _CONTRACT_MSG  # contract: test_sdk_contract_static.py::test_build_bound_storage_is_idempotent_across_calls
        finally:
            asyncio.run(engine.dispose())

    def test_calling_sdk_factories_directly_for_the_same_name_collides(self) -> None:
        """Collision proof: documents *why* the registry in `sdk_models.py` exists.

        Uses a throwaway, uuid-suffixed table name (never `a2a_task_events`) so
        the real registry is never polluted, and so that reruns of this test
        within the same process -- it declares a *new* SDK-`Base`-backed class
        every time -- never collide with a previous run's leftover class.
        """
        throwaway_name = f"a2a_dup_events_contract_test_{uuid.uuid4().hex}"
        engine = create_async_engine("postgresql+psycopg://user:pass@localhost/unused")
        try:
            store = VersionedDatabaseTaskStore(
                engine, create_table=False, event_table_name=throwaway_name
            )
            del store
            with pytest.raises(sa.exc.InvalidRequestError):
                DatabaseTaskEventStream(engine, create_table=False, table_name=throwaway_name)
        finally:
            asyncio.run(engine.dispose())

    def test_task_and_version_model_primary_keys(self) -> None:
        """The task PK is `id`; the version PK is `task_id`.

        The clustered event tail (`DatabaseTaskEventStream`) relies on global
        `task_id` uniqueness across all owners to resolve a cursor and replay
        events for a single task -- if either PK ever grew an `owner` column,
        the event tail's single-column `task_id` lookups would silently
        become ambiguous across owners.
        """
        models = get_sdk_models()
        task_pk = [c.name for c in models.task.__table__.primary_key.columns]
        version_pk = [c.name for c in models.version.__table__.primary_key.columns]
        assert task_pk == ["id"], (
            f"{_CONTRACT_MSG}: a2a_tasks primary key changed to {task_pk} -- the event tail "
            "relies on global task_id uniqueness"
        )
        assert version_pk == ["task_id"], (
            f"{_CONTRACT_MSG}: a2a_task_versions primary key changed to {version_pk} -- the "
            "event tail relies on global task_id uniqueness"
        )
