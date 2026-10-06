"""Mattin's model registry for the pinned a2a-sdk (AD-2).

**Why this module exists.** ``a2a-sdk==1.2.2``'s DB stores accept no model
class arguments. ``DatabaseTaskStore.__init__`` calls ``create_task_model``
unless the table name is the SDK default (``'tasks'``);
``VersionedDatabaseTaskStore.__init__`` similarly calls
``create_task_event_model``/``create_task_version_model`` unless the event/
version table names are the SDK defaults (``'task_events'``/
``'task_versions'``). Each of those factories declares a *new* SQLAlchemy
class on the SDK's shared ``a2a.server.models.Base`` every time it is called,
so a second call with the same table name raises
``sqlalchemy.exc.InvalidRequestError: Table already defined``. Mattin's
``VersionedDatabaseTaskStore`` (the request-serving store) and
``DatabaseTaskEventStream`` (the cross-worker event tail) are each built once
per uvicorn worker but can legitimately be built more than once in a single
process (tests build two to simulate two workers sharing one DB; see AC-33).
Calling the factories ourselves, twice, for the same ``a2a_*`` name would hit
that exact collision.

The user rejected a dedicated Postgres ``a2a`` schema (DEV-1), so the SDK
tables must be plain ``public`` tables named ``a2a_tasks``, ``a2a_task_events``
and ``a2a_task_versions``, created **only** by Alembic (never by the SDK's own
``create_table=True`` path).

**The fix.** Declare each model exactly once, memoized for the lifetime of
the process, on a Mattin-owned declarative base (``A2ASdkBase``) with its own
``MetaData`` -- separate from both Mattin's own ``db.database.Base`` and the
SDK's ``a2a.server.models.Base``. ``backend/services/a2a_server/storage.py``
then builds the SDK store/stream objects with their *default* table names (so
the constructors never call a factory at all) and narrowly overrides their
model-class attributes with these memoized classes (AD-2 point 3). This
module is the schema source of truth for the SDK tables: Alembic's migration
mirrors ``A2ASdkBase.metadata`` exactly, and Alembic's ``env.py`` must ignore
these three tables so that autogenerate never proposes dropping them.

**Exact pin.** ``a2a-sdk==1.2.2`` is pinned exactly in ``pyproject.toml``. Any
patch release could rename or repurpose the private attributes that
``storage.py`` writes (``store._event_model``, ``store._version_model``,
``stream._event_model``), or change what the public
``store.as_task_store.task_model`` means. An upgrade must be a deliberate pin
bump that re-runs ``tests/integration/a2a_server/test_sdk_contract.py`` before
it lands.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass

from a2a.server.models import (
    create_task_event_model,
    create_task_model,
    create_task_version_model,
)
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


class A2ASdkBase(DeclarativeBase):
    """Mattin-owned declarative base for the SDK's task/event/version models.

    Deliberately distinct from ``db.database.Base`` (Mattin's own models) and
    from ``a2a.server.models.Base`` (the SDK's default, unused, models). It
    carries its own ``MetaData``, so ``A2ASdkBase.metadata`` is the schema
    source of truth the Alembic migration (step_007) and the schema-drift test
    compare against.
    """


TASKS_TABLE = "a2a_tasks"
EVENTS_TABLE = "a2a_task_events"
VERSIONS_TABLE = "a2a_task_versions"


@dataclass(frozen=True)
class A2ASdkModels:
    """The three memoized SDK model classes bound to the `a2a_*` tables."""

    task: type
    event: type
    version: type


class A2ASdkContractError(RuntimeError):
    """Raised when the installed a2a-sdk no longer matches AD-2's assumptions.

    Only `storage.py`'s `_bind_models` raises this, and only at process
    startup (never at request time), so a contract break fails loudly before
    any A2A traffic is served.
    """


@functools.cache
def get_sdk_models() -> A2ASdkModels:
    """Builds (once per process) the `a2a_*`-named SDK model classes.

    Memoized with `functools.cache` so that calling `storage.build_bound_storage`
    any number of times in one process -- including the two independent
    "worker" instances the contract suite builds to simulate a cluster (AC-33)
    -- never calls the SDK's `create_*_model` factories more than once per
    table name. A second call with the same name on the SDK's own `Base`
    raises `InvalidRequestError`; this cache is what prevents that.
    """
    return A2ASdkModels(
        task=create_task_model(TASKS_TABLE, A2ASdkBase),
        event=create_task_event_model(EVENTS_TABLE, A2ASdkBase),
        version=create_task_version_model(VERSIONS_TABLE, A2ASdkBase),
    )


def get_sdk_metadata() -> MetaData:
    """Returns `A2ASdkBase.metadata`, after guaranteeing the three models exist.

    `A2ASdkBase.metadata` is empty until `get_sdk_models()` actually declares
    the three model classes on it, so callers that only want the metadata
    (Alembic's schema-drift test, `tests/integration/a2a_server/conftest.py`)
    must go through this function rather than reading `A2ASdkBase.metadata`
    directly -- otherwise `create_all`/`drop_all` would silently be a no-op.
    """
    get_sdk_models()
    return A2ASdkBase.metadata
